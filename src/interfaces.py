"""
Interfaces and protocols for DEM Backend architecture.

Phase 3B.3: Core architectural decoupling through dependency inversion principle.
Defines abstract protocols for external dependencies to improve testability and maintainability.
"""

from typing import Protocol, Optional, Dict, Any
from abc import ABC, abstractmethod
import asyncio


class ElevationData(Protocol):
    """Protocol for elevation data returned by data sources."""
    elevation: float
    latitude: float
    longitude: float
    source_name: str
    resolution_m: float
    accuracy: str
    data_type: str
    message: str


class CircuitBreaker(Protocol):
    """Protocol for circuit breaker pattern implementation."""
    
    async def is_open(self, service_name: str) -> bool:
        """Check if circuit breaker is open for given service."""
        ...
    
    async def record_success(self, service_name: str) -> None:
        """Record successful operation for service."""
        ...
    
    async def record_failure(self, service_name: str) -> None:
        """Record failed operation for service."""
        ...
    
    async def get_failure_count(self, service_name: str) -> int:
        """Get current failure count for service."""
        ...


class HealthReporter(Protocol):
    """Protocol for health reporting to deployment platforms."""
    
    def signal_ready(self) -> None:
        """Signal that service is ready to receive traffic."""
        ...
    
    def signal_unhealthy(self, reason: str) -> None:
        """Signal that service is unhealthy."""
        ...


class DataSource(ABC):
    """
    Abstract base class for elevation data sources.
    
    Implements the Strategy Pattern for data source fallback chain.
    Each concrete implementation handles a specific data source (S3, GPXZ, Google).
    """
    
    def __init__(self, name: str, timeout_seconds: float, circuit_breaker: CircuitBreaker):
        self.name = name
        self.timeout_seconds = timeout_seconds
        self.circuit_breaker = circuit_breaker
    
    @abstractmethod
    async def get_elevation(self, latitude: float, longitude: float) -> Optional[ElevationData]:
        """
        Get elevation data for coordinates.
        
        Returns None if:
        - Circuit breaker is open
        - Data not available for coordinates
        - Service error/timeout
        
        Implementations should:
        1. Check circuit breaker status
        2. Perform data retrieval with timeout
        3. Record success/failure with circuit breaker
        4. Return structured elevation data or None
        """
        ...
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if data source is healthy and accessible."""
        ...
    
    @abstractmethod
    def get_coverage_info(self) -> Dict[str, Any]:
        """Get information about geographic coverage and capabilities."""
        ...


class StateManager(Protocol):
    """Protocol for distributed state management."""
    
    async def get(self, key: str) -> Optional[str]:
        """Get value for key."""
        ...
    
    async def set(self, key: str, value: str, expiry_seconds: Optional[int] = None) -> None:
        """Set value for key with optional expiry."""
        ...
    
    async def increment(self, key: str) -> int:
        """Increment counter and return new value."""
        ...
    
    async def delete(self, key: str) -> None:
        """Delete key."""
        ...


class ElevationProvider(ABC):
    """
    Abstract elevation provider that orchestrates multiple data sources.
    
    Implements the Chain of Responsibility pattern with ordered list of DataSource strategies.
    """
    
    def __init__(self, sources: list[DataSource]):
        self.sources = sources
    
    @abstractmethod
    async def get_elevation(self, latitude: float, longitude: float) -> Optional[ElevationData]:
        """
        Get elevation using fallback chain of data sources.
        
        Iterates through sources in priority order until one returns data.
        """
        ...
    
    @abstractmethod
    async def get_elevation_batch(self, coordinates: list[tuple[float, float]]) -> list[Optional[ElevationData]]:
        """Get elevation for multiple coordinates efficiently."""
        ...
    
    @abstractmethod
    def get_available_sources(self) -> list[str]:
        """Get list of available data source names."""
        ...
    
    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Get health status of all data sources."""
        ...


class ConfigurationProvider(Protocol):
    """Protocol for configuration management across environments."""
    
    @property
    def app_env(self) -> str:
        """Get application environment (production, development)."""
        ...
    
    @property
    def redis_url(self) -> str:
        """Get Redis connection URL."""
        ...
    
    @property
    def use_s3_sources(self) -> bool:
        """Whether S3 sources are enabled."""
        ...
    
    @property
    def use_api_sources(self) -> bool:
        """Whether API sources are enabled."""
        ...
    
    def get_source_config(self, source_name: str) -> Dict[str, Any]:
        """Get configuration for specific data source."""
        ...


# Type aliases for better readability
Coordinates = tuple[float, float]
ElevationResult = Optional[ElevationData]
HealthStatus = Dict[str, Any]