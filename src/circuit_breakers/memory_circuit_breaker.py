"""
In-Memory Circuit Breaker implementation.

Phase 3B.3: Concrete implementation of CircuitBreaker protocol for testing and development.
Provides simple in-memory circuit breaker functionality without external dependencies.
"""

import asyncio
import logging
import time
from typing import Dict, Optional

from ..interfaces import CircuitBreaker

logger = logging.getLogger(__name__)


class InMemoryCircuitBreaker(CircuitBreaker):
    """
    In-memory circuit breaker for testing and single-process development.
    
    NOT suitable for production multi-worker environments as state is not shared.
    Primarily used for unit testing and development convenience.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        
        # Service state tracking
        self._failures: Dict[str, int] = {}
        self._opened_times: Dict[str, float] = {}
        self._lock = asyncio.Lock()
    
    async def is_open(self, service_name: str) -> bool:
        """
        Check if circuit breaker is open for service.
        
        Circuit breaker is open if:
        1. Failure count >= threshold AND
        2. Recovery timeout has not elapsed since opening
        """
        async with self._lock:
            # Check if circuit breaker was explicitly opened
            if service_name in self._opened_times:
                opened_time = self._opened_times[service_name]
                current_time = time.time()
                
                # Check if recovery timeout has elapsed
                if (current_time - opened_time) < self.recovery_timeout:
                    return True
                else:
                    # Recovery timeout elapsed, close circuit breaker
                    await self._close_circuit(service_name)
                    return False
            
            # Check failure count
            failures = self._failures.get(service_name, 0)
            return failures >= self.failure_threshold
    
    async def record_success(self, service_name: str) -> None:
        """Record successful operation and close circuit breaker if open."""
        async with self._lock:
            # Reset failure count on success
            self._failures[service_name] = 0
            if service_name in self._opened_times:
                del self._opened_times[service_name]
            
            logger.debug(f"Circuit breaker success recorded for {service_name}")
    
    async def record_failure(self, service_name: str) -> None:
        """Record failed operation and open circuit breaker if threshold exceeded."""
        async with self._lock:
            # Increment failure count
            current_failures = self._failures.get(service_name, 0)
            self._failures[service_name] = current_failures + 1
            
            failure_count = self._failures[service_name]
            
            # Open circuit breaker if threshold exceeded
            if failure_count >= self.failure_threshold:
                await self._open_circuit(service_name)
                logger.warning(
                    f"Circuit breaker OPENED for {service_name} "
                    f"(failures: {failure_count}/{self.failure_threshold})"
                )
            else:
                logger.debug(
                    f"Circuit breaker failure recorded for {service_name} "
                    f"({failure_count}/{self.failure_threshold})"
                )
    
    async def get_failure_count(self, service_name: str) -> int:
        """Get current failure count for service."""
        async with self._lock:
            return self._failures.get(service_name, 0)
    
    async def _open_circuit(self, service_name: str) -> None:
        """Open circuit breaker for service."""
        self._opened_times[service_name] = time.time()
        logger.info(f"Circuit breaker opened for {service_name} (recovery in {self.recovery_timeout}s)")
    
    async def _close_circuit(self, service_name: str) -> None:
        """Close circuit breaker for service."""
        if service_name in self._opened_times:
            del self._opened_times[service_name]
        self._failures[service_name] = 0
        logger.info(f"Circuit breaker closed for {service_name} (recovery timeout elapsed)")
    
    async def get_status(self, service_name: str) -> dict:
        """Get detailed circuit breaker status for monitoring."""
        async with self._lock:
            is_open = await self.is_open(service_name)
            failure_count = self._failures.get(service_name, 0)
            
            status = {
                'service_name': service_name,
                'is_open': is_open,
                'failure_count': failure_count,
                'failure_threshold': self.failure_threshold,
                'recovery_timeout': self.recovery_timeout
            }
            
            if service_name in self._opened_times:
                opened_time = self._opened_times[service_name]
                time_until_recovery = max(0, self.recovery_timeout - (time.time() - opened_time))
                status['opened_timestamp'] = opened_time
                status['recovery_in_seconds'] = time_until_recovery
            
            return status
    
    async def reset(self, service_name: str) -> None:
        """Reset circuit breaker for service (admin operation)."""
        async with self._lock:
            self._failures[service_name] = 0
            if service_name in self._opened_times:
                del self._opened_times[service_name]
            logger.info(f"Circuit breaker reset for {service_name}")
    
    async def get_all_statuses(self) -> dict:
        """Get status for all tracked services."""
        async with self._lock:
            services = set(self._failures.keys()) | set(self._opened_times.keys())
            statuses = {}
            
            for service in services:
                statuses[service] = await self.get_status(service)
            
            return statuses
    
    def get_tracked_services(self) -> list:
        """Get list of all services being tracked."""
        return list(set(self._failures.keys()) | set(self._opened_times.keys()))
    
    # Additional properties for compatibility with existing code
    @property
    def failure_count(self) -> int:
        """Compatibility property - returns total failures across all services."""
        return sum(self._failures.values())