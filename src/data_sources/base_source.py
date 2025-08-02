"""
Base Data Source for Phase 2 Unified Architecture
Provides abstract base class and result models for the unified provider system
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class ElevationResult:
    """Standardized elevation result for Phase 2 unified architecture"""
    elevation: Optional[float]
    source: str
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class BaseDataSource(ABC):
    """
    Abstract base class for Phase 2 unified data sources.
    
    This is simpler than the legacy DataSource interface and designed
    specifically for the unified architecture with discriminated unions.
    """
    
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    async def get_elevation(self, lat: float, lon: float) -> ElevationResult:
        """Get elevation data for coordinates"""
        pass
    
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the data source"""
        pass
    
    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check health status"""
        pass
    
    @abstractmethod
    async def coverage_info(self) -> Dict[str, Any]:
        """Get coverage information"""
        pass
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get usage statistics (optional)"""
        return {"source": self.name}