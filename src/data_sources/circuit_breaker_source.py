"""
Circuit Breaker Data Source Decorator
Implements Gemini's recommended Decorator pattern for circuit breaker logic
"""
import logging
from typing import Dict, Any, Optional
import asyncio
from datetime import datetime

from data_sources.base_source import BaseDataSource, ElevationResult
from circuit_breakers.base_circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

class CircuitBreakerWrappedDataSource(BaseDataSource):
    """
    Decorator that wraps any DataSource with circuit breaker protection
    Implements the Decorator pattern for ultimate decoupling
    """
    
    def __init__(self, 
                 wrapped_source: BaseDataSource,
                 circuit_breaker: CircuitBreaker,
                 name: Optional[str] = None):
        """
        Initialize circuit breaker wrapped data source
        
        Args:
            wrapped_source: The data source to wrap
            circuit_breaker: Circuit breaker instance for protection
            name: Optional name for this wrapped source
        """
        super().__init__()
        self.wrapped_source = wrapped_source
        self.circuit_breaker = circuit_breaker
        self.name = name or f"cb_{wrapped_source.__class__.__name__}"
        
        # Statistics
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "circuit_open_blocks": 0,
            "circuit_half_open_attempts": 0
        }
        
        logger.info(f"CircuitBreakerWrappedDataSource initialized: {self.name}")
    
    async def initialize(self) -> bool:
        """Initialize the wrapped source"""
        try:
            logger.debug(f"Initializing wrapped source: {self.wrapped_source.__class__.__name__}")
            result = await self.wrapped_source.initialize()
            
            if result:
                logger.info(f"✅ Wrapped source {self.wrapped_source.__class__.__name__} initialized")
            else:
                logger.warning(f"⚠️ Wrapped source {self.wrapped_source.__class__.__name__} failed to initialize")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Wrapped source initialization error: {e}")
            return False
    
    async def get_elevation(self, lat: float, lon: float) -> ElevationResult:
        """
        Get elevation with circuit breaker protection
        Implements the classic ask-tell circuit breaker pattern
        """
        self.stats["total_requests"] += 1
        service_name = f"elevation_{self.wrapped_source.__class__.__name__}"
        
        # ASK: Check if circuit breaker allows the call
        can_proceed = await self.circuit_breaker.can_proceed(service_name)
        
        if not can_proceed:
            self.stats["circuit_open_blocks"] += 1
            logger.debug(f"Circuit breaker OPEN for {service_name} - blocking request")
            
            return ElevationResult(
                elevation=None,
                error=f"Circuit breaker open for {service_name}",
                source=f"cb_{self.wrapped_source.__class__.__name__}",
                metadata={
                    "circuit_breaker": {
                        "status": "open",
                        "service": service_name,
                        "blocked_request": True
                    },
                    "wrapped_source": self.wrapped_source.__class__.__name__
                }
            )
        
        # Circuit breaker allows the call - proceed
        start_time = datetime.now()
        
        try:
            # Call the wrapped source
            result = await self.wrapped_source.get_elevation(lat, lon)
            
            # TELL: Report success or failure to circuit breaker
            if result.elevation is not None:
                # Success
                await self.circuit_breaker.record_success(service_name)
                self.stats["successful_requests"] += 1
                
                # Enhance metadata with circuit breaker info
                result.metadata = result.metadata or {}
                result.metadata["circuit_breaker"] = {
                    "status": "closed",
                    "service": service_name,
                    "protected_call": True
                }
                
                logger.debug(f"✅ Circuit breaker SUCCESS for {service_name}")
                
            else:
                # Failure (no elevation data)
                await self.circuit_breaker.record_failure(service_name)
                self.stats["failed_requests"] += 1
                
                # Enhance metadata
                result.metadata = result.metadata or {}
                result.metadata["circuit_breaker"] = {
                    "status": "closed",
                    "service": service_name,
                    "failure_recorded": True
                }
                
                logger.debug(f"⚠️ Circuit breaker FAILURE recorded for {service_name}: no elevation data")
            
            return result
            
        except Exception as e:
            # Exception occurred - record failure
            elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            await self.circuit_breaker.record_failure(service_name)
            self.stats["failed_requests"] += 1
            
            logger.warning(f"❌ Circuit breaker EXCEPTION for {service_name}: {e}")
            
            return ElevationResult(
                elevation=None,
                error=f"Circuit breaker protected call failed: {e}",
                source=f"cb_{self.wrapped_source.__class__.__name__}",
                metadata={
                    "circuit_breaker": {
                        "status": "closed",
                        "service": service_name,
                        "exception_recorded": True,
                        "elapsed_ms": elapsed_ms
                    },
                    "wrapped_source": self.wrapped_source.__class__.__name__,
                    "original_error": str(e)
                }
            )
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of wrapped source and circuit breaker"""
        try:
            # Get wrapped source health
            wrapped_health = await self.wrapped_source.health_check()
            
            # Get circuit breaker status
            service_name = f"elevation_{self.wrapped_source.__class__.__name__}"
            cb_status = await self.circuit_breaker.get_service_status(service_name)
            
            # Determine overall health
            overall_status = "healthy"
            if cb_status.get("state") == "open":
                overall_status = "circuit_open"
            elif wrapped_health.get("status") != "healthy":
                overall_status = wrapped_health.get("status", "unknown")
            
            return {
                "status": overall_status,
                "wrapped_source": {
                    "type": self.wrapped_source.__class__.__name__,
                    "health": wrapped_health
                },
                "circuit_breaker": {
                    "service": service_name,
                    "status": cb_status,
                    "can_proceed": await self.circuit_breaker.can_proceed(service_name)
                },
                "statistics": self.stats
            }
            
        except Exception as e:
            logger.error(f"Health check failed for {self.name}: {e}")
            return {
                "status": "error",
                "error": str(e),
                "wrapped_source": self.wrapped_source.__class__.__name__
            }
    
    async def coverage_info(self) -> Dict[str, Any]:
        """Get coverage info from wrapped source"""
        try:
            coverage = await self.wrapped_source.coverage_info()
            
            # Add circuit breaker metadata
            coverage["circuit_breaker_protected"] = True
            coverage["wrapped_source"] = self.wrapped_source.__class__.__name__
            
            return coverage
            
        except Exception as e:
            return {
                "error": f"Coverage info failed: {e}",
                "wrapped_source": self.wrapped_source.__class__.__name__
            }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics including circuit breaker metrics"""
        wrapped_stats = {}
        try:
            wrapped_stats = self.wrapped_source.get_statistics()
        except Exception as e:
            wrapped_stats = {"error": str(e)}
        
        return {
            "source_type": f"circuit_breaker_wrapped",
            "wrapped_source": self.wrapped_source.__class__.__name__,
            "circuit_breaker_stats": self.stats,
            "success_rate": (
                self.stats["successful_requests"] / max(self.stats["total_requests"], 1)
            ) * 100,
            "wrapped_source_stats": wrapped_stats
        }
    
    async def reset_circuit_breaker(self) -> bool:
        """Reset the circuit breaker for this source"""
        try:
            service_name = f"elevation_{self.wrapped_source.__class__.__name__}"
            await self.circuit_breaker.reset_service(service_name)
            logger.info(f"Circuit breaker reset for {service_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to reset circuit breaker: {e}")
            return False
    
    async def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """Get detailed circuit breaker status"""
        service_name = f"elevation_{self.wrapped_source.__class__.__name__}"
        try:
            return await self.circuit_breaker.get_service_status(service_name)
        except Exception as e:
            return {"error": str(e)}