"""
Circuit breaker implementations for DEM Backend.

Phase 3B.3: AbstractCircuitBreaker protocol with concrete implementations.
Provides dependency injection pattern for circuit breaker functionality.
"""

from .redis_circuit_breaker import RedisCircuitBreaker
from .memory_circuit_breaker import InMemoryCircuitBreaker

__all__ = ['RedisCircuitBreaker', 'InMemoryCircuitBreaker']