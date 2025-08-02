"""
Unified Elevation Provider
Supports both legacy and unified v2.0 architecture with feature flag control
"""
import logging
from typing import Dict, List, Optional, Any
import asyncio

from ..config import get_settings
from ..data_sources.base_source import BaseDataSource, ElevationResult
from ..data_sources.unified_s3_source import UnifiedS3Source
from ..data_sources.composite_source import FallbackDataSource
from ..data_sources.circuit_breaker_source import CircuitBreakerWrappedDataSource
from ..s3_client_factory import S3ClientFactory
from ..circuit_breakers.redis_circuit_breaker import RedisCircuitBreaker
from ..circuit_breakers.memory_circuit_breaker import InMemoryCircuitBreaker

logger = logging.getLogger(__name__)

class UnifiedElevationProvider:
    """
    Provider that manages both legacy and unified elevation systems
    Feature flag controlled for safe deployment
    """
    
    def __init__(self, s3_client_factory: Optional[S3ClientFactory] = None):
        """
        Initialize unified elevation provider
        
        Args:
            s3_client_factory: S3 client factory for AWS access
        """
        self.settings = get_settings()
        self.s3_client_factory = s3_client_factory
        
        # Core data source
        self.elevation_source: Optional[BaseDataSource] = None
        
        # Legacy fallback components (for compatibility)
        self.legacy_source: Optional[BaseDataSource] = None
        
        self.initialized = False
        
        logger.info(f"UnifiedElevationProvider initialized (unified={self.settings.USE_UNIFIED_SPATIAL_INDEX})")
    
    async def initialize(self) -> bool:
        """Initialize the elevation provider based on feature flags"""
        try:
            logger.info("🚀 Initializing UnifiedElevationProvider...")
            
            if self.settings.USE_UNIFIED_SPATIAL_INDEX:
                success = await self._initialize_unified_system()
            else:
                success = await self._initialize_legacy_system()
            
            if success:
                self.initialized = True
                logger.info("✅ UnifiedElevationProvider initialized successfully")
            else:
                logger.error("❌ UnifiedElevationProvider initialization failed")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to initialize UnifiedElevationProvider: {e}")
            return False
    
    async def _initialize_unified_system(self) -> bool:
        """Initialize the new unified v2.0 system"""
        logger.info("🔄 Initializing unified v2.0 elevation system...")
        
        try:
            # Create unified S3 source
            unified_s3_source = UnifiedS3Source(
                use_unified_index=True,
                unified_index_key=self.settings.UNIFIED_INDEX_PATH,
                s3_client_factory=self.s3_client_factory
            )
            
            # Initialize API sources for fallback (if enabled)
            # TODO: Temporarily disabled until API sources are adapted to BaseDataSource interface
            api_sources = []
            if self.settings.USE_API_SOURCES:
                logger.info("API sources temporarily disabled for Phase 2 - S3 sources only")
                # api_sources = await self._create_api_sources()
            
            # Create fallback chain: S3 → APIs
            sources = [unified_s3_source] + api_sources
            
            if len(sources) == 1:
                # Single source - no fallback needed
                self.elevation_source = unified_s3_source
            else:
                # Multiple sources - use composite pattern
                self.elevation_source = FallbackDataSource(
                    sources=sources,
                    name="unified_primary"
                )
            
            # Initialize the source
            success = await self.elevation_source.initialize()
            
            if success:
                logger.info("✅ Unified v2.0 system initialized successfully")
            else:
                logger.error("❌ Unified v2.0 system initialization failed")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to initialize unified system: {e}")
            return False
    
    async def _initialize_legacy_system(self) -> bool:
        """Initialize the legacy system as fallback"""
        logger.info("📊 Initializing legacy elevation system...")
        
        # TODO: This would import and initialize the existing SourceProvider/EnhancedSourceSelector
        # For now, we'll create a placeholder that indicates legacy mode
        
        logger.warning("Legacy system initialization not implemented in this demo")
        logger.info("📊 Legacy system would be initialized here")
        
        # Return True to allow testing of the unified system
        return False
    
    async def _create_api_sources(self) -> List[BaseDataSource]:
        """Create API sources with circuit breaker protection"""
        logger.info("Creating API sources with circuit breaker protection...")
        
        api_sources = []
        
        try:
            # Create circuit breaker
            if self.settings.APP_ENV == "production":
                circuit_breaker = RedisCircuitBreaker(
                    redis_url=self.settings.REDIS_URL,
                    failure_threshold=5,
                    recovery_timeout=60,
                    state_timeout=300
                )
            else:
                circuit_breaker = InMemoryCircuitBreaker(
                    failure_threshold=3,
                    recovery_timeout=30
                )
            
            # Import API sources dynamically to avoid circular imports
            from ..data_sources.gpxz_source import GPXZSource
            from ..data_sources.google_source import GoogleSource
            
            # Create GPXZ source with circuit breaker
            if hasattr(self.settings, 'GPXZ_API_KEY') and self.settings.GPXZ_API_KEY:
                gpxz_source = GPXZSource(
                    api_key=self.settings.GPXZ_API_KEY,
                    daily_limit=self.settings.GPXZ_DAILY_LIMIT,
                    rate_limit=self.settings.GPXZ_RATE_LIMIT
                )
                
                cb_gpxz_source = CircuitBreakerWrappedDataSource(
                    wrapped_source=gpxz_source,
                    circuit_breaker=circuit_breaker,
                    name="cb_gpxz"
                )
                
                api_sources.append(cb_gpxz_source)
                logger.info("✅ Added GPXZ source with circuit breaker")
            
            # Create Google source with circuit breaker (if configured)
            if hasattr(self.settings, 'GOOGLE_API_KEY') and self.settings.GOOGLE_API_KEY:
                google_source = GoogleSource(api_key=self.settings.GOOGLE_API_KEY)
                
                cb_google_source = CircuitBreakerWrappedDataSource(
                    wrapped_source=google_source,
                    circuit_breaker=circuit_breaker,
                    name="cb_google"
                )
                
                api_sources.append(cb_google_source)
                logger.info("✅ Added Google source with circuit breaker")
            
        except Exception as e:
            logger.warning(f"Failed to create some API sources: {e}")
        
        logger.info(f"Created {len(api_sources)} API sources")
        return api_sources
    
    async def get_elevation(self, lat: float, lon: float) -> ElevationResult:
        """Get elevation using the configured system"""
        if not self.initialized or not self.elevation_source:
            return ElevationResult(
                elevation=None,
                error="Provider not initialized",
                source="unified_provider",
                metadata={"initialized": self.initialized}
            )
        
        try:
            return await self.elevation_source.get_elevation(lat, lon)
            
        except Exception as e:
            logger.error(f"Error in unified elevation lookup: {e}")
            return ElevationResult(
                elevation=None,
                error=f"Provider error: {e}",
                source="unified_provider",
                metadata={}
            )
    
    async def health_check(self) -> Dict[str, Any]:
        """Get health status of the provider"""
        health = {
            "status": "unknown",
            "provider": "unified",
            "initialized": self.initialized,
            "unified_mode": self.settings.USE_UNIFIED_SPATIAL_INDEX,
            "unified_index_path": self.settings.UNIFIED_INDEX_PATH
        }
        
        if self.elevation_source:
            try:
                source_health = await self.elevation_source.health_check()
                health["source_health"] = source_health
                health["status"] = source_health.get("status", "unknown")
            except Exception as e:
                health["source_health"] = {"error": str(e)}
                health["status"] = "error"
        else:
            health["status"] = "not_initialized"
        
        return health
    
    async def coverage_info(self) -> Dict[str, Any]:
        """Get coverage information"""
        if not self.elevation_source:
            return {"error": "Provider not initialized"}
        
        try:
            return await self.elevation_source.coverage_info()
        except Exception as e:
            return {"error": str(e)}
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get provider statistics"""
        stats = {
            "provider_type": "unified",
            "unified_mode": self.settings.USE_UNIFIED_SPATIAL_INDEX,
            "initialized": self.initialized
        }
        
        if self.elevation_source:
            try:
                stats["source_stats"] = self.elevation_source.get_statistics()
            except Exception as e:
                stats["source_stats"] = {"error": str(e)}
        
        return stats
    
    async def reload_configuration(self) -> bool:
        """Reload configuration and reinitialize if needed"""
        logger.info("Reloading UnifiedElevationProvider configuration...")
        
        # Reload settings
        self.settings = get_settings()
        
        # Reinitialize
        self.initialized = False
        return await self.initialize()