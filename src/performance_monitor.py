"""
Performance Monitor for DEM Elevation Service
Tracks response times, thread pool usage, and system performance metrics
"""
import time
import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

@dataclass
class PerformanceMetric:
    """Single performance measurement"""
    endpoint: str
    response_time_ms: float
    timestamp: float
    success: bool
    error_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class PerformanceMonitor:
    """
    Performance monitoring system for elevation service
    
    Features:
    - Response time tracking with percentiles
    - Performance alerting when targets are exceeded
    - Thread pool utilization monitoring
    - Cache hit rate tracking
    - Batch processing efficiency metrics
    """
    
    def __init__(self, target_response_ms: float = 100, alert_threshold_ms: float = 500):
        """Initialize performance monitor"""
        self.target_response_ms = target_response_ms
        self.alert_threshold_ms = alert_threshold_ms
        
        # Metrics storage (keep last 1000 measurements)
        self.metrics: deque = deque(maxlen=1000)
        self.alerts_enabled = True
        
        # Per-endpoint statistics
        self.endpoint_stats = defaultdict(list)
        
        # Performance counters
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.alerts_triggered = 0
        
        logger.info(f"Performance monitor initialized (target: {target_response_ms}ms, alert: {alert_threshold_ms}ms)")
    
    async def track_async_operation(self, endpoint: str, operation, *args, **kwargs):
        """
        Track performance of an async operation with robust exception handling
        
        Args:
            endpoint: Name of the operation/endpoint
            operation: Async function to execute
            *args, **kwargs: Arguments for the operation
            
        Returns:
            Result of the operation
        """
        start_time = time.perf_counter()
        success = True
        error_type = None
        result = None
        exception_to_reraise = None
        
        try:
            result = await operation(*args, **kwargs)
            self.successful_requests += 1
        except Exception as e:
            success = False
            error_type = type(e).__name__
            self.failed_requests += 1
            exception_to_reraise = e
            logger.error(f"Operation {endpoint} failed: {error_type}: {e}")
        finally:
            # Record metrics regardless of success/failure - this ALWAYS runs
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.total_requests += 1
            
            # Create performance metric
            metric = PerformanceMetric(
                endpoint=endpoint,
                response_time_ms=duration_ms,
                timestamp=time.time(),
                success=success,
                error_type=error_type
            )
            
            # Store metric
            self.metrics.append(metric)
            self.endpoint_stats[endpoint].append(duration_ms)
            
            # Keep only recent measurements per endpoint
            if len(self.endpoint_stats[endpoint]) > 100:
                self.endpoint_stats[endpoint] = self.endpoint_stats[endpoint][-100:]
            
            # Check for performance alerts (both slow operations AND failures)
            if self.alerts_enabled and (duration_ms > self.alert_threshold_ms or not success):
                await self._trigger_performance_alert(endpoint, duration_ms, success, error_type)
        
        # Re-raise exception AFTER metrics are recorded
        if exception_to_reraise:
            raise exception_to_reraise
            
        return result
    
    async def _trigger_performance_alert(self, endpoint: str, duration_ms: float, success: bool, error_type: str = None):
        """Trigger performance alert for slow operations or failures"""
        self.alerts_triggered += 1
        
        if not success:
            status = f"FAILED ({error_type})" if error_type else "FAILED"
            logger.warning(
                f"🚨 PERFORMANCE ALERT: {endpoint} {status} in {duration_ms:.2f}ms "
                f"[Target: {self.target_response_ms}ms, Alert: {self.alert_threshold_ms}ms]"
            )
        else:
            status = "SLOW"
            logger.warning(
                f"🚨 PERFORMANCE ALERT: {endpoint} took {duration_ms:.2f}ms ({status}) "
                f"[Target: {self.target_response_ms}ms, Alert: {self.alert_threshold_ms}ms]"
            )
        
        # Additional context for performance debugging
        recent_avg = self.get_endpoint_average(endpoint, last_n=10)
        if recent_avg:
            logger.warning(f"📊 Recent average for {endpoint}: {recent_avg:.2f}ms (last 10 requests)")
    
    def get_endpoint_average(self, endpoint: str, last_n: int = None) -> Optional[float]:
        """Get average response time for specific endpoint"""
        if endpoint not in self.endpoint_stats:
            return None
        
        measurements = self.endpoint_stats[endpoint]
        if not measurements:
            return None
        
        # Use last N measurements if specified
        if last_n:
            measurements = measurements[-last_n:]
        
        return sum(measurements) / len(measurements)
    
    def get_endpoint_percentiles(self, endpoint: str) -> Optional[Dict[str, float]]:
        """Get response time percentiles for specific endpoint"""
        if endpoint not in self.endpoint_stats or not self.endpoint_stats[endpoint]:
            return None
        
        measurements = sorted(self.endpoint_stats[endpoint])
        n = len(measurements)
        
        return {
            "P50": measurements[int(n * 0.5)],
            "P90": measurements[int(n * 0.9)],
            "P95": measurements[int(n * 0.95)],
            "P99": measurements[int(n * 0.99)]
        }
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary"""
        now = time.time()
        recent_metrics = [m for m in self.metrics if now - m.timestamp < 300]  # Last 5 minutes
        
        # Overall statistics
        total_time = sum(m.response_time_ms for m in recent_metrics)
        avg_response_time = total_time / len(recent_metrics) if recent_metrics else 0
        
        success_rate = (self.successful_requests / self.total_requests * 100 
                       if self.total_requests > 0 else 0)
        
        # Per-endpoint breakdown
        endpoint_summary = {}
        for endpoint, measurements in self.endpoint_stats.items():
            if measurements:
                endpoint_summary[endpoint] = {
                    "count": len(measurements),
                    "avg_ms": sum(measurements) / len(measurements),
                    "min_ms": min(measurements),
                    "max_ms": max(measurements),
                    "percentiles": self.get_endpoint_percentiles(endpoint)
                }
        
        return {
            "performance_targets": {
                "target_response_ms": self.target_response_ms,
                "alert_threshold_ms": self.alert_threshold_ms
            },
            "overall_stats": {
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "success_rate": f"{success_rate:.1f}%",
                "alerts_triggered": self.alerts_triggered,
                "avg_response_time_ms": f"{avg_response_time:.2f}"
            },
            "recent_performance": {
                "last_5min_requests": len(recent_metrics),
                "last_5min_avg_ms": f"{avg_response_time:.2f}"
            },
            "endpoint_breakdown": endpoint_summary,
            "status": self._get_overall_status()
        }
    
    def _get_overall_status(self) -> str:
        """Determine overall system performance status"""
        if not self.endpoint_stats:
            return "initializing"
        
        # Calculate overall average
        all_times = []
        for measurements in self.endpoint_stats.values():
            all_times.extend(measurements[-20:])  # Recent measurements only
        
        if not all_times:
            return "no_data"
        
        avg_time = sum(all_times) / len(all_times)
        
        if avg_time <= self.target_response_ms:
            return "excellent"
        elif avg_time <= self.alert_threshold_ms:
            return "good"
        else:
            return "degraded"
    
    def reset_statistics(self):
        """Reset all performance statistics"""
        self.metrics.clear()
        self.endpoint_stats.clear()
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.alerts_triggered = 0
        logger.info("Performance statistics reset")

# Global performance monitor instance
_performance_monitor: Optional[PerformanceMonitor] = None

def get_performance_monitor() -> PerformanceMonitor:
    """Get global performance monitor instance"""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor

async def track_elevation_performance(endpoint: str, operation, *args, **kwargs):
    """Convenience function for tracking elevation operations"""
    monitor = get_performance_monitor()
    return await monitor.track_async_operation(endpoint, operation, *args, **kwargs)