"""
Dependency Injection Container for DEM Backend Services.

This module implements a proper dependency injection pattern, replacing the
global service locator approach with a more testable and maintainable solution.
"""

import logging
from typing import Optional
from functools import lru_cache

from .config import Settings, get_settings
from .dataset_manager import DatasetManager
from .contour_service import ContourService
from .unified_elevation_service import UnifiedElevationService
from .dem_service import DEMService

logger = logging.getLogger(__name__)


class ServiceContainer:
    """
    Dependency injection container that manages service lifecycle and dependencies.
    
    This container follows the dependency injection pattern, constructing the full
    dependency graph at startup and providing clean interfaces for testing.
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self._dataset_manager: Optional[DatasetManager] = None
        self._contour_service: Optional[ContourService] = None
        self._elevation_service: Optional[UnifiedElevationService] = None
        self._dem_service: Optional[DEMService] = None
        
        logger.info("ServiceContainer initialized")
    
    @property
    def dataset_manager(self) -> DatasetManager:
        """Get or create the DatasetManager instance."""
        if self._dataset_manager is None:
            self._dataset_manager = DatasetManager(self.settings)
            logger.info("DatasetManager created and injected")
        return self._dataset_manager
    
    @property 
    def contour_service(self) -> ContourService:
        """Get or create the ContourService instance with DatasetManager dependency."""
        if self._contour_service is None:
            self._contour_service = ContourService(self.dataset_manager)
            logger.info("ContourService created with DatasetManager dependency")
        return self._contour_service
    
    @property
    def elevation_service(self) -> UnifiedElevationService:
        """Get or create the UnifiedElevationService instance."""
        if self._elevation_service is None:
            self._elevation_service = UnifiedElevationService(self.settings)
            # Inject dataset manager if the service supports it
            if hasattr(self._elevation_service, 'set_dataset_manager'):
                self._elevation_service.set_dataset_manager(self.dataset_manager)
            logger.info("UnifiedElevationService created with dependencies")
        return self._elevation_service
    
    @property
    def dem_service(self) -> DEMService:
        """Get or create the DEMService instance with all dependencies."""
        if self._dem_service is None:
            # Create DEMService but override its internal service creation with our managed instances
            self._dem_service = DEMService(self.settings)
            
            # Replace DEMService's internal services with our managed instances
            self._dem_service.dataset_manager = self.dataset_manager
            self._dem_service.contour_service = self.contour_service
            self._dem_service.elevation_service = self.elevation_service
            
            logger.info("DEMService created with injected dependencies")
        return self._dem_service
    
    async def close(self):
        """Close all managed services and clean up resources."""
        services_to_close = [
            ("dem_service", self._dem_service),
            ("elevation_service", self._elevation_service),
            ("dataset_manager", self._dataset_manager),
        ]
        
        for service_name, service in services_to_close:
            if service and hasattr(service, 'close'):
                try:
                    if hasattr(service.close, '__await__'):
                        await service.close()
                    else:
                        service.close()
                    logger.info(f"Closed {service_name}")
                except Exception as e:
                    logger.warning(f"Error closing {service_name}: {e}")
        
        logger.info("ServiceContainer closed all managed services")


# Global container instance (initialized at startup)
_service_container: Optional[ServiceContainer] = None


def get_service_container() -> ServiceContainer:
    """Get the global service container instance."""
    if _service_container is None:
        raise RuntimeError("Service container not initialized. Call init_service_container() first.")
    return _service_container


def init_service_container(settings: Settings) -> ServiceContainer:
    """Initialize the global service container with settings."""
    global _service_container
    try:
        _service_container = ServiceContainer(settings)
        logger.info("Service container initialized successfully")
        return _service_container
    except Exception as e:
        logger.error(f"Failed to initialize service container: {e}")
        raise


async def close_service_container():
    """Close the global service container and clean up all resources."""
    global _service_container
    if _service_container:
        try:
            await _service_container.close()
            _service_container = None
            logger.info("Service container closed and reset")
        except Exception as e:
            logger.error(f"Error closing service container: {e}")
            raise


# FastAPI dependency functions
@lru_cache()
def get_settings_cached() -> Settings:
    """Cached settings dependency to avoid re-reading configuration."""
    return get_settings()


def get_dataset_manager() -> DatasetManager:
    """FastAPI dependency to get DatasetManager instance."""
    return get_service_container().dataset_manager


def get_contour_service() -> ContourService:
    """FastAPI dependency to get ContourService instance."""
    return get_service_container().contour_service


def get_elevation_service() -> UnifiedElevationService:
    """FastAPI dependency to get UnifiedElevationService instance."""
    return get_service_container().elevation_service


def get_dem_service() -> DEMService:
    """FastAPI dependency to get DEMService instance."""
    return get_service_container().dem_service