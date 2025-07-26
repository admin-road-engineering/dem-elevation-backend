import asyncio
import logging
from typing import Optional, Dict, Any
from enum import Enum
import time

logger = logging.getLogger(__name__)

class SourceType(Enum):
    LOCAL = "local"
    API = "api" 
    S3 = "s3"

class ElevationError(Exception):
    """Base exception for elevation service errors"""
    def __init__(self, message: str, source_type: SourceType = None, recoverable: bool = True):
        self.message = message
        self.source_type = source_type
        self.recoverable = recoverable
        super().__init__(message)

class RetryableError(ElevationError):
    """Error that should trigger retry logic"""
    pass

class NonRetryableError(ElevationError):
    """Error that should not be retried"""
    def __init__(self, message: str, source_type: SourceType = None):
        super().__init__(message, source_type, recoverable=False)

async def retry_with_backoff(
    func,
    max_retries: int = 3,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 30.0,
    exceptions: tuple = (Exception,)
):
    """Retry function with exponential backoff"""
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except exceptions as e:
            if attempt == max_retries:
                logger.error(f"Max retries ({max_retries}) exceeded for {func.__name__}: {e}")
                raise
            
            if isinstance(e, NonRetryableError):
                logger.error(f"Non-retryable error in {func.__name__}: {e}")
                raise
            
            delay = min(base_delay * (backoff_factor ** attempt), max_delay)
            logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {e}. Retrying in {delay:.1f}s")
            await asyncio.sleep(delay)

class CircuitBreaker:
    """Circuit breaker pattern for external services with latency-based triggers"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60, 
                 latency_threshold_ms: float = 2000, slow_request_threshold: int = 3):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.latency_threshold_ms = latency_threshold_ms
        self.slow_request_threshold = slow_request_threshold
        
        self.failure_count = 0
        self.slow_request_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        
        # Track latency history for better decision making
        self.recent_latencies = []
        self.max_latency_history = 10
    
    def is_available(self) -> bool:
        """Check if service is available"""
        if self.state == "CLOSED":
            return True
        
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
                return True
            return False
        
        # HALF_OPEN state
        return True
    
    def record_success(self, response_time_ms: float = None):
        """Record successful operation with optional latency tracking"""
        self.failure_count = 0
        self.slow_request_count = 0
        self.state = "CLOSED"
        
        # Track response time
        if response_time_ms is not None:
            self.recent_latencies.append(response_time_ms)
            if len(self.recent_latencies) > self.max_latency_history:
                self.recent_latencies.pop(0)
    
    def record_failure(self, response_time_ms: float = None):
        """Record failed operation with optional latency tracking"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        # Also track if this was a timeout/slow response
        if response_time_ms is not None and response_time_ms >= self.latency_threshold_ms:
            self.slow_request_count += 1
            logger.warning(f"Slow request detected: {response_time_ms:.2f}ms (threshold: {self.latency_threshold_ms}ms)")
        
        # Open circuit if too many failures OR too many slow requests
        if (self.failure_count >= self.failure_threshold or 
            self.slow_request_count >= self.slow_request_threshold):
            self.state = "OPEN"
            trigger_reason = "failures" if self.failure_count >= self.failure_threshold else "slow_requests"
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures "
                          f"and {self.slow_request_count} slow requests (trigger: {trigger_reason})")
    
    def record_timeout(self, timeout_ms: float):
        """Record timeout as both failure and slow request"""
        logger.warning(f"Request timeout after {timeout_ms:.2f}ms")
        self.record_failure(response_time_ms=timeout_ms)

def create_unified_error_response(
    error: Exception,
    lat: float,
    lon: float,
    attempted_sources: list = None
) -> Dict[str, Any]:
    """Create standardized error response"""
    return {
        "elevation_m": None,
        "success": False,
        "error": {
            "message": "Elevation data unavailable",
            "coordinates": {"lat": lat, "lon": lon},
            "attempted_sources": attempted_sources or [],
            "fallback_attempted": len(attempted_sources or []) > 1,
            "retry_recommended": isinstance(error, RetryableError)
        },
        "metadata": {
            "timestamp": time.time(),
            "service": "dem-backend"
        }
    }