"""
Dependency Injection Container for DEM Backend Services.

This module implements a proper dependency injection pattern, replacing the
global service locator approach with a more testable and maintainable solution.
"""

import logging
from typing import Optional
from functools import lru_cache

from fastapi import Request
from .config import Settings, get_settings
from .dataset_manager import DatasetManager
from .contour_service import ContourService
from .unified_elevation_service import UnifiedElevationService
from .dem_service import DEMService
from .redis_state_manager import RedisStateManager
from .unified_index_loader import UnifiedIndexLoader
from .source_provider import SourceProvider
from .services.crs_service import CRSTransformationService
from .services.thread_pool_service import ThreadPoolService
from .services.spatial_index_service import SpatialIndexService
from .campaign_dataset_selector import CampaignDatasetSelector

logger = logging.getLogger(__name__)


class ServiceContainer:
    """
    Dependency injection container that manages service lifecycle and dependencies.
    
    This container follows the dependency injection pattern, constructing the full
    dependency graph at startup and providing clean interfaces for testing.
    """
    
    def __init__(self, settings: Settings, source_provider: Optional[SourceProvider] = None, enhanced_selector=None, unified_provider=None):
        """
        Initialize ServiceContainer with optional providers.
        
        Phase 3A-Fix: Added SourceProvider parameter for dependency injection.
        Phase 3B.5: Added enhanced_selector parameter for lifespan-initialized selector.
        Phase 3B.5: Added unified_provider parameter for Phase 2 unified architecture.
        """
        self.settings = settings
        self.source_provider = source_provider
        self.enhanced_selector = enhanced_selector
        self.unified_provider = unified_provider
        self._dataset_manager: Optional[DatasetManager] = None
        self._contour_service: Optional[ContourService] = None
        self._elevation_service: Optional[UnifiedElevationService] = None
        self._dem_service: Optional[DEMService] = None
        
        # Initialize Redis state manager for process-safe operations
        self._redis_manager: Optional[RedisStateManager] = None
        
        # Initialize UnifiedIndexLoader for enhanced index management (Phase 1)
        self._unified_index_loader: Optional[UnifiedIndexLoader] = None
        
        # Initialize CRS transformation service for CRS-aware spatial queries (Phase 5)
        self._crs_service: Optional[CRSTransformationService] = None
        
        # Initialize CampaignDatasetSelector for campaign-based queries (Performance Fix Phase 1.1)
        self._campaign_selector: Optional[CampaignDatasetSelector] = None
        
        # Initialize ThreadPoolService for CPU-intensive operations (Performance Fix Phase 2.1)
        self._thread_pool_service: Optional[ThreadPoolService] = None
        
        # Initialize SpatialIndexService for O(log N) spatial queries (Performance Fix Phase 3)
        self._spatial_index_service: Optional[SpatialIndexService] = None
        
        logger.info(f"ServiceContainer initialized with Redis state management, SourceProvider: {source_provider is not None}, UnifiedProvider: {unified_provider is not None}")
    
    @property
    def redis_manager(self) -> RedisStateManager:
        """
        Get or create the Redis state manager instance.
        
        Phase 3B.1: Pass app_env for production safety checks.
        """
        if self._redis_manager is None:
            self._redis_manager = RedisStateManager(app_env=self.settings.APP_ENV)
            logger.info(f"RedisStateManager created for process-safe state (env: {self.settings.APP_ENV})")
        return self._redis_manager
    
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
        """
        Get or create the UnifiedElevationService instance.
        
        Phase 3A-Fix: Injects SourceProvider if available.
        """
        if self._elevation_service is None:
            # Log detailed provider state for debugging integration issue
            logger.info(f"Creating UnifiedElevationService with providers - UnifiedProvider: {self.unified_provider is not None}, SourceProvider: {self.source_provider is not None}, EnhancedSelector: {self.enhanced_selector is not None}")
            
            self._elevation_service = UnifiedElevationService(
                self.settings, 
                redis_manager=self.redis_manager,
                source_provider=self.source_provider,
                enhanced_selector=self.enhanced_selector,
                unified_provider=self.unified_provider
            )
            # Inject dataset manager if the service supports it
            if hasattr(self._elevation_service, 'set_dataset_manager'):
                self._elevation_service.set_dataset_manager(self.dataset_manager)
            logger.info(f"✅ UnifiedElevationService created successfully with UnifiedProvider: {self.unified_provider is not None}")
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
    
    @property
    def unified_index_loader(self) -> UnifiedIndexLoader:
        """Get UnifiedIndexLoader (Phase 1 - for enhanced index management)"""
        if self._unified_index_loader is None:
            self._unified_index_loader = UnifiedIndexLoader()
            logger.info("UnifiedIndexLoader created with data-driven configuration")
        return self._unified_index_loader
    
    @property
    def crs_service(self) -> CRSTransformationService:
        """Get CRS transformation service (Phase 5 - for CRS-aware spatial queries)"""
        if self._crs_service is None:
            self._crs_service = CRSTransformationService()
            logger.info("CRSTransformationService created for data-driven coordinate transformations")
        return self._crs_service
    
    @property
    def campaign_selector(self) -> CampaignDatasetSelector:
        """Get CampaignDatasetSelector singleton (Performance Fix Phase 1.1)"""
        if self._campaign_selector is None:
            # Use same config_dir logic as dataset_endpoints.py
            from pathlib import Path
            config_dir = Path(__file__).parent / "config"
            self._campaign_selector = CampaignDatasetSelector(config_dir)
            logger.info("CampaignDatasetSelector created as singleton to prevent re-initialization")
        return self._campaign_selector
    
    @property
    def thread_pool_service(self) -> ThreadPoolService:
        """Get ThreadPoolService singleton for CPU-intensive operations (Performance Fix Phase 2.1)"""
        if self._thread_pool_service is None:
            self._thread_pool_service = ThreadPoolService()
            logger.info("ThreadPoolService created for optimized CPU/I-O task execution")
        return self._thread_pool_service
    
    @property
    def spatial_index_service(self) -> SpatialIndexService:
        """Get SpatialIndexService singleton for O(log N) spatial queries (Performance Fix Phase 3)"""
        if self._spatial_index_service is None:
            self._spatial_index_service = SpatialIndexService()
            logger.info("SpatialIndexService created for high-performance spatial queries")
        return self._spatial_index_service
    
    async def close(self):
        """Close all managed services and clean up resources."""
        services_to_close = [
            ("dem_service", self._dem_service),
            ("elevation_service", self._elevation_service),
            ("dataset_manager", self._dataset_manager),
            ("redis_manager", self._redis_manager),
            ("crs_service", self._crs_service),
            ("campaign_selector", self._campaign_selector),
            ("thread_pool_service", self._thread_pool_service),
            ("spatial_index_service", self._spatial_index_service),
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


def init_service_container(settings: Settings, source_provider: Optional[SourceProvider] = None, enhanced_selector=None, unified_provider=None) -> ServiceContainer:
    """
    Initialize the global service container with settings and optional providers.
    
    Phase 3A-Fix: Added SourceProvider parameter for dependency injection.
    Phase 3B.5: Added enhanced_selector parameter for lifespan-initialized selector.
    Phase 3B.5: Added unified_provider parameter for Phase 2 unified architecture.
    """
    global _service_container
    try:
        _service_container = ServiceContainer(
            settings, 
            source_provider=source_provider, 
            enhanced_selector=enhanced_selector,
            unified_provider=unified_provider
        )
        logger.info("Service container initialized successfully with provider support")
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
def get_settings_cached() -> Settings:
    """Get settings from the service container to ensure consistency."""
    return get_service_container().settings


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


def get_enhanced_selector_from_app_state(request: Request):
    """FastAPI dependency to get pre-initialized EnhancedSourceSelector from app.state."""
    if hasattr(request.app.state, 'enhanced_selector'):
        return request.app.state.enhanced_selector
    return None


def get_crs_service() -> CRSTransformationService:
    """FastAPI dependency to get CRSTransformationService instance."""
    return get_service_container().crs_service


def get_campaign_selector() -> CampaignDatasetSelector:
    """FastAPI dependency to get CampaignDatasetSelector singleton."""
    return get_service_container().campaign_selector


def get_thread_pool_service() -> ThreadPoolService:
    """FastAPI dependency to get ThreadPoolService singleton."""
    return get_service_container().thread_pool_service


def get_spatial_index_service() -> SpatialIndexService:
    """FastAPI dependency to get SpatialIndexService singleton."""
    return get_service_container().spatial_index_service