"""
Unified Elevation Service - Consolidates all source selection logic
This addresses the code review feedback about scattered source selection logic
"""
import logging
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass

from .enhanced_source_selector import EnhancedSourceSelector
from .source_selector import DEMSourceSelector
from .config import Settings
from .dem_exceptions import (
    DEMServiceError, DEMSourceError, DEMAPIError, DEMS3Error,
    DEMCoordinateError, DEMConfigurationError
)
from .gpxz_client import GPXZConfig

logger = logging.getLogger(__name__)

@dataclass
class ElevationResult:
    """Standardized elevation result across all sources"""
    elevation_m: Optional[float]
    dem_source_used: str
    message: Optional[str]
    metadata: Optional[Dict[str, Any]] = None

class UnifiedElevationService:
    """
    Unified interface for elevation queries that consolidates all source selection logic.
    
    This class addresses the code review feedback by:
    1. Centralizing all source selection logic in one place
    2. Providing a single, clean interface for elevation queries
    3. Hiding complexity from the DEMService class
    4. Supporting both legacy and enhanced source selectors
    """
    
    def __init__(self, settings: Settings):
        try:
            self.settings = settings
            
            # Initialize appropriate source selector based on configuration
            use_s3 = getattr(settings, 'USE_S3_SOURCES', False)
            use_apis = getattr(settings, 'USE_API_SOURCES', False)
            
            if use_s3 or use_apis:
                logger.info("Initializing enhanced source selector with S3/API support")
                
                # Prepare configurations for external services
                gpxz_config = GPXZConfig(api_key=settings.GPXZ_API_KEY) if settings.GPXZ_API_KEY else None
                google_api_key = settings.GOOGLE_ELEVATION_API_KEY
                aws_creds = {
                    "access_key_id": settings.AWS_ACCESS_KEY_ID,
                    "secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
                    "region": settings.AWS_DEFAULT_REGION
                } if settings.AWS_ACCESS_KEY_ID else None

                self.source_selector = EnhancedSourceSelector(
                    config=settings.DEM_SOURCES,
                    use_s3=use_s3,
                    use_apis=use_apis,
                    gpxz_config=gpxz_config,
                    google_api_key=google_api_key,
                    aws_credentials=aws_creds
                )
                self.using_enhanced_selector = True
            else:
                logger.info("Initializing legacy source selector")
                self.source_selector = DEMSourceSelector(settings.DEM_SOURCES)
                self.using_enhanced_selector = False
                
        except (AttributeError, KeyError, ValueError) as e:
            logger.error(f"Configuration error initializing elevation service: {e}")
            raise DEMConfigurationError(f"Invalid configuration: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error initializing elevation service: {e}")
            raise DEMServiceError(f"Failed to initialize elevation service: {e}") from e
    
    async def get_elevation(self, latitude: float, longitude: float, 
                          dem_source_id: Optional[str] = None) -> ElevationResult:
        """
        Get elevation at a single point with unified source selection.
        
        This is the single entry point for all elevation queries, handling:
        - Automatic source selection
        - Fallback chain execution (S3 → GPXZ → Google → Local)
        - Error handling and recovery
        - Result standardization
        
        Args:
            latitude: Point latitude in WGS84
            longitude: Point longitude in WGS84
            dem_source_id: Optional specific source ID (overrides auto-selection)
            
        Returns:
            ElevationResult with elevation, source used, and any messages
        """
        # Validate coordinates
        if not (-90 <= latitude <= 90):
            raise DEMCoordinateError(f"Invalid latitude: {latitude}. Must be between -90 and 90.")
        if not (-180 <= longitude <= 180):
            raise DEMCoordinateError(f"Invalid longitude: {longitude}. Must be between -180 and 180.")
        
        try:
            if self.using_enhanced_selector:
                return await self._get_elevation_enhanced(latitude, longitude, dem_source_id)
            else:
                return await self._get_elevation_legacy(latitude, longitude, dem_source_id)
                
        except DEMCoordinateError:
            # Re-raise coordinate errors as-is
            raise
        except DEMSourceError as e:
            logger.error(f"Source selection error: {e}")
            return ElevationResult(
                elevation_m=None,
                dem_source_used="source_error",
                message=f"Source selection failed: {str(e)}"
            )
        except (DEMAPIError, DEMS3Error) as e:
            logger.error(f"External service error: {e}")
            return ElevationResult(
                elevation_m=None,
                dem_source_used="external_error",
                message=f"External service failed: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Unexpected elevation service error: {e}")
            return ElevationResult(
                elevation_m=None,
                dem_source_used="unknown_error",
                message=f"Unexpected error: {str(e)}"
            )
    
    async def _get_elevation_enhanced(self, lat: float, lon: float, 
                                    source_id: Optional[str]) -> ElevationResult:
        """Handle elevation queries using enhanced source selector"""
        try:
            if source_id:
                # This path is not fully implemented in the enhanced selector yet
                # and would bypass the main resilience logic.
                # For now, we log a warning and use the main fallback.
                logger.warning(f"Specific source_id '{source_id}' requested, but enhanced selector prioritizes the fallback chain. Ignoring for now.")

            # Use automatic source selection with full fallback chain
            result = await self.source_selector.get_elevation_with_resilience(lat, lon)
            
            # Enhanced response with campaign information
            source_used = result.get('source', 'unknown')
            campaign_info = result.get('campaign_info', {})
            
            # Create detailed message with campaign intelligence
            attempted_sources = result.get('attempted_sources', [])
            if campaign_info and source_used != 'gpxz_api' and source_used != 'google_api':
                # Campaign-based message with performance info
                speedup_factor = campaign_info.get('speedup_factor', 'unknown')
                provider = campaign_info.get('provider', 'unknown')
                resolution = campaign_info.get('resolution_m', 'unknown')
                year = campaign_info.get('campaign_year', 'unknown')
                
                message = (f"Campaign: {source_used} | Provider: {provider} | "
                          f"Resolution: {resolution}m | Year: {year} | "
                          f"Performance: {speedup_factor}")
            else:
                # Standard fallback message
                message = f"Attempted sources: {attempted_sources}"
            
            return ElevationResult(
                elevation_m=result.get('elevation_m'),
                dem_source_used=source_used,
                message=message,
                metadata={
                    **(result.get('metadata', {})),
                    'campaign_info': campaign_info,
                    'attempted_sources': attempted_sources
                }
            )
            
        except Exception as e:
            logger.error(f"Enhanced elevation query failed: {e}", exc_info=True)
            return ElevationResult(
                elevation_m=None,
                dem_source_used="enhanced_error",
                message=f"Enhanced selector error: {str(e)}"
            )
    
    async def _get_elevation_legacy(self, lat: float, lon: float, 
                                   source_id: Optional[str]) -> ElevationResult:
        """Handle elevation queries using legacy source selector"""
        try:
            if source_id:
                # Use specific source
                selected_source = {'id': source_id}
            else:
                # Auto-select best source
                selected_source = self.source_selector.select_best_source(lat, lon)
            
            # This would need to be integrated with the existing DEM file reading logic
            # For now, return a placeholder that indicates legacy mode
            return ElevationResult(
                elevation_m=None,
                dem_source_used=selected_source['id'],
                message="Legacy mode - elevation extraction not implemented in unified service yet"
            )
            
        except Exception as e:
            logger.error(f"Legacy elevation query failed: {e}")
            return ElevationResult(
                elevation_m=None,
                dem_source_used="legacy_error", 
                message=f"Legacy selector error: {str(e)}"
            )
    
    async def get_elevations_batch(self, points: List[Tuple[float, float]], 
                                 dem_source_id: Optional[str] = None) -> List[ElevationResult]:
        """
        Get elevations for multiple points efficiently.
        
        This consolidates the batch processing logic and can optimize for:
        - Same source usage across multiple points
        - Bulk API calls where supported
        - Connection pooling and rate limiting
        """
        results = []
        
        # For now, process sequentially - could be optimized for batch operations
        for lat, lon in points:
            result = await self.get_elevation(lat, lon, dem_source_id)
            results.append(result)
        
        return results
    
    def get_available_sources(self) -> List[Dict[str, Any]]:
        """Get list of available DEM sources"""
        if self.using_enhanced_selector:
            return list(self.settings.DEM_SOURCES.values())
        else:
            return list(self.source_selector.dem_sources.values())
    
    def get_coverage_summary(self) -> Dict[str, Any]:
        """Get coverage summary for all sources""" 
        if hasattr(self.source_selector, 'get_coverage_summary'):
            return self.source_selector.get_coverage_summary()
        else:
            return {
                "message": "Coverage summary not available for this source selector",
                "source_count": len(self.get_available_sources())
            }
    
    async def close(self):
        """Clean up resources"""
        if hasattr(self.source_selector, 'close'):
            try:
                await self.source_selector.close()
                logger.info("Unified elevation service closed successfully")
            except Exception as e:
                logger.warning(f"Error closing unified elevation service: {e}")
