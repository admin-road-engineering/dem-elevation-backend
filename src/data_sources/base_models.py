"""
Base models for data sources.

Phase 3B.3: Shared data models for DataSource Strategy Pattern.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class ElevationData:
    """Structured elevation data returned by data sources."""
    elevation: float
    latitude: float
    longitude: float
    source_name: str
    resolution_m: float
    accuracy: str
    data_type: str
    message: str
    
    # Additional metadata
    bounds: Optional[Dict[str, float]] = None
    provider: Optional[str] = None
    cost_per_query: Optional[float] = None
    query_time_ms: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            'elevation': self.elevation,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'dem_source_used': self.source_name,
            'resolution': self.resolution_m,
            'grid_resolution_m': self.resolution_m,
            'data_type': self.data_type,
            'accuracy': self.accuracy,
            'message': self.message,
            'provider': self.provider,
            'query_time_ms': self.query_time_ms
        }


@dataclass 
class SourceConfig:
    """Configuration for a data source."""
    name: str
    timeout_seconds: float
    priority: int
    enabled: bool = True
    
    # Source-specific configuration
    config: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.config is None:
            self.config = {}


@dataclass
class HealthStatus:
    """Health status for a data source."""
    source_name: str
    is_healthy: bool
    last_check: str
    error_message: Optional[str] = None
    response_time_ms: Optional[float] = None
    circuit_breaker_open: bool = False
    failure_count: int = 0