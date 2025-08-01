"""
Redis-backed Circuit Breaker implementation.

Phase 3B.3: Concrete implementation of CircuitBreaker protocol using Redis for shared state.
Provides process-safe circuit breaker functionality across multiple workers.
"""

import asyncio
import logging
import time
from typing import Optional
import redis.asyncio as redis

from ..interfaces import CircuitBreaker

logger = logging.getLogger(__name__)


class RedisCircuitBreaker(CircuitBreaker):
    """
    Redis-backed circuit breaker for multi-worker process safety.
    
    Provides distributed circuit breaker state management using Redis as shared storage.
    Critical for Railway multi-worker deployment where in-memory state is dangerous.
    """
    
    def __init__(
        self,
        redis_client: redis.Redis,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        key_prefix: str = "circuit_breaker"
    ):
        self.redis = redis_client
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.key_prefix = key_prefix
    
    def _failure_key(self, service_name: str) -> str:
        """Generate Redis key for failure count."""
        return f"{self.key_prefix}:failures:{service_name}"
    
    def _opened_key(self, service_name: str) -> str:
        """Generate Redis key for circuit breaker opened timestamp."""
        return f"{self.key_prefix}:opened:{service_name}"
    
    async def is_open(self, service_name: str) -> bool:
        """
        Check if circuit breaker is open for service.
        
        Circuit breaker is open if:
        1. Failure count >= threshold AND
        2. Recovery timeout has not elapsed since opening
        """
        try:
            # Check if circuit breaker was explicitly opened
            opened_timestamp = await self.redis.get(self._opened_key(service_name))
            
            if opened_timestamp:
                opened_time = float(opened_timestamp)
                current_time = time.time()
                
                # Check if recovery timeout has elapsed
                if (current_time - opened_time) < self.recovery_timeout:
                    return True
                else:
                    # Recovery timeout elapsed, close circuit breaker
                    await self._close_circuit(service_name)
                    return False
            
            # Check failure count
            failures = await self.get_failure_count(service_name)
            return failures >= self.failure_threshold
            
        except Exception as e:
            logger.error(f"Error checking circuit breaker for {service_name}: {e}")
            # Fail safe: assume circuit is closed
            return False
    
    async def record_success(self, service_name: str) -> None:
        """Record successful operation and close circuit breaker if open."""
        try:
            # Reset failure count on success
            await self.redis.delete(self._failure_key(service_name))
            await self.redis.delete(self._opened_key(service_name))
            
            logger.debug(f"Circuit breaker success recorded for {service_name}")
            
        except Exception as e:
            logger.error(f"Error recording success for {service_name}: {e}")
    
    async def record_failure(self, service_name: str) -> None:
        """Record failed operation and open circuit breaker if threshold exceeded."""
        try:
            # Increment failure count
            failure_count = await self.redis.incr(self._failure_key(service_name))
            
            # Set expiry on failure count (cleanup old failures)
            await self.redis.expire(self._failure_key(service_name), self.recovery_timeout * 2)
            
            # Open circuit breaker if threshold exceeded
            if failure_count >= self.failure_threshold:
                await self._open_circuit(service_name)
                logger.warning(
                    f"Circuit breaker OPENED for {service_name} "
                    f"(failures: {failure_count}/{self.failure_threshold})"
                )
            else:
                logger.debug(f"Circuit breaker failure recorded for {service_name} ({failure_count}/{self.failure_threshold})")
                
        except Exception as e:
            logger.error(f"Error recording failure for {service_name}: {e}")
    
    async def get_failure_count(self, service_name: str) -> int:
        """Get current failure count for service."""
        try:
            count = await self.redis.get(self._failure_key(service_name))
            return int(count) if count else 0
        except Exception as e:
            logger.error(f"Error getting failure count for {service_name}: {e}")
            return 0
    
    async def _open_circuit(self, service_name: str) -> None:
        """Open circuit breaker for service."""
        try:
            current_time = time.time()
            await self.redis.set(
                self._opened_key(service_name), 
                current_time, 
                ex=self.recovery_timeout
            )
            logger.info(f"Circuit breaker opened for {service_name} (recovery in {self.recovery_timeout}s)")
        except Exception as e:
            logger.error(f"Error opening circuit breaker for {service_name}: {e}")
    
    async def _close_circuit(self, service_name: str) -> None:
        """Close circuit breaker for service."""
        try:
            await self.redis.delete(self._opened_key(service_name))
            await self.redis.delete(self._failure_key(service_name))
            logger.info(f"Circuit breaker closed for {service_name} (recovery timeout elapsed)")
        except Exception as e:
            logger.error(f"Error closing circuit breaker for {service_name}: {e}")
    
    async def get_status(self, service_name: str) -> dict:
        """Get detailed circuit breaker status for monitoring."""
        try:
            is_open = await self.is_open(service_name)
            failure_count = await self.get_failure_count(service_name)
            opened_timestamp = await self.redis.get(self._opened_key(service_name))
            
            status = {
                'service_name': service_name,
                'is_open': is_open,
                'failure_count': failure_count,
                'failure_threshold': self.failure_threshold,
                'recovery_timeout': self.recovery_timeout
            }
            
            if opened_timestamp:
                opened_time = float(opened_timestamp)
                time_until_recovery = max(0, self.recovery_timeout - (time.time() - opened_time))
                status['opened_timestamp'] = opened_time
                status['recovery_in_seconds'] = time_until_recovery
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting circuit breaker status for {service_name}: {e}")
            return {
                'service_name': service_name,
                'is_open': False,
                'failure_count': 0,
                'error': str(e)
            }
    
    async def reset(self, service_name: str) -> None:
        """Reset circuit breaker for service (admin operation)."""
        try:
            await self.redis.delete(self._failure_key(service_name))
            await self.redis.delete(self._opened_key(service_name))
            logger.info(f"Circuit breaker reset for {service_name}")
        except Exception as e:
            logger.error(f"Error resetting circuit breaker for {service_name}: {e}")
    
    async def get_all_statuses(self) -> dict:
        """Get status for all tracked services."""
        try:
            # Find all services with circuit breaker keys
            pattern = f"{self.key_prefix}:*"
            keys = await self.redis.keys(pattern)
            
            services = set()
            for key in keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                parts = key_str.split(':')
                if len(parts) >= 3:
                    services.add(parts[2])  # Extract service name
            
            statuses = {}
            for service in services:
                statuses[service] = await self.get_status(service)
            
            return statuses
            
        except Exception as e:
            logger.error(f"Error getting all circuit breaker statuses: {e}")
            return {}
    
    # Additional properties for compatibility with existing code
    @property 
    def failure_count(self) -> int:
        """Compatibility property - returns 0 as we need service name for actual count."""
        logger.warning("failure_count property called without service name - returning 0")
        return 0