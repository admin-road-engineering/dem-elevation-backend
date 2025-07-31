import time
import json
import asyncio
import logging
import os
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime

from .s3_source_manager import S3SourceManager, DEMMetadata
from .gpxz_client import GPXZClient, GPXZConfig
from .google_elevation_client import GoogleElevationClient
# from .smart_dataset_selector import SmartDatasetSelector
from .campaign_dataset_selector import CampaignDatasetSelector
from .error_handling import (
    CircuitBreaker, RetryableError, NonRetryableError, 
    create_unified_error_response, retry_with_backoff, SourceType
)
from .redis_state_manager import RedisStateManager, RedisS3CostManager, RedisCircuitBreaker
from .unified_index_loader import UnifiedIndexLoader

logger = logging.getLogger(__name__)

class SpatialIndexLoader:
    """Loads and manages spatial index files for S3 DEM sources with smart dataset selection"""
    
    def __init__(self, unified_loader: Optional[UnifiedIndexLoader] = None):
        self.project_root = Path(__file__).parent.parent
        self.config_dir = self.project_root / "config"
        self.au_spatial_index = None
        self.nz_spatial_index = None
        self.unified_loader = unified_loader
        # Initialize smart dataset selector for Phase 2 performance improvements
        # self.smart_selector = SmartDatasetSelector(self.config_dir)
        
    def load_australian_index(self) -> Optional[Dict]:
        """Load Australian spatial index"""
        if self.au_spatial_index is None:
            au_index_file = self.config_dir / "spatial_index.json"
            if au_index_file.exists():
                try:
                    with open(au_index_file, 'r') as f:
                        self.au_spatial_index = json.load(f)
                except Exception as e:
                    logger.error(f"Failed to load Australian spatial index: {e}")
        return self.au_spatial_index
    
    def load_nz_index(self) -> Optional[Dict]:
        """Load NZ spatial index (S3 in production, filesystem in development)"""
        if self.nz_spatial_index is None:
            # Try UnifiedIndexLoader first (production S3 loading)
            if self.unified_loader:
                try:
                    import asyncio
                    import concurrent.futures
                    
                    # Use asyncio.run in a thread pool to avoid "event loop already running" 
                    def load_nz_index_sync():
                        return asyncio.run(self.unified_loader.load_index("nz_spatial_index"))
                    
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(load_nz_index_sync)
                        self.nz_spatial_index = future.result(timeout=30)  # 30 second timeout
                    
                    logger.info("Successfully loaded NZ spatial index from S3 via UnifiedIndexLoader")
                    return self.nz_spatial_index
                except Exception as e:
                    logger.warning(f"Failed to load NZ spatial index from S3: {e}, falling back to filesystem")
            
            # Fallback to filesystem loading (development mode)
            nz_index_file = self.config_dir / "nz_spatial_index.json"
            if nz_index_file.exists():
                try:
                    with open(nz_index_file, 'r') as f:
                        self.nz_spatial_index = json.load(f)
                    logger.info("Successfully loaded NZ spatial index from filesystem")
                except Exception as e:
                    logger.error(f"Failed to load NZ spatial index from filesystem: {e}")
            else:
                logger.warning(f"NZ spatial index file not found: {nz_index_file}")
        return self.nz_spatial_index
    
    def find_au_file_for_coordinate(self, lat: float, lon: float) -> Optional[str]:
        """Find Australian DEM file for given coordinates using smart dataset selection"""
        # Use smart dataset selector for Phase 2 performance improvements
        # Use campaign selector instead of smart selector
        matching_campaigns = self.campaign_selector.get_campaigns_for_coordinate(lat, lon)
        matching_files = []
        for campaign in matching_campaigns[:3]:  # Limit to top 3 campaigns
            matching_files.extend(campaign.get('files', [])[:100])  # Limit files per campaign
        datasets_searched = len(matching_campaigns)
        
        if not matching_files:
            logger.warning(f"No AU DEM files found for coordinates ({lat}, {lon}) in datasets: {datasets_searched}")
            return None
        
        # Prioritize files based on quality indicators
        best_file = self._select_best_file_from_matches(matching_files, lat, lon)
        
        if best_file:
            filename = best_file.get("filename", "unknown")
            key = best_file.get("key", best_file.get("file", ""))
            logger.info(f"Smart selection found file for ({lat}, {lon}): {filename} from datasets {datasets_searched}")
            return key
        
        return None
    
    def _select_best_file_from_matches(self, matching_files: List[Dict], lat: float, lon: float) -> Optional[Dict]:
        """Select the best file from a list of matching files based on quality indicators"""
        if not matching_files:
            return None
        
        # Sort by priority factors:
        # 1. Brisbane area preference for Brisbane coordinates
        # 2. File size (larger often means better coverage)
        # 3. Resolution preference (smaller pixel size)
        
        scored_files = []
        is_brisbane_area = abs(lat + 27.5) < 1.0  # Brisbane area
        
        for file_info in matching_files:
            score = 0.0
            filename = file_info.get("filename", "").lower()
            
            # Brisbane area preference
            if is_brisbane_area and "brisbane" in filename:
                score += 10.0
            
            # File size preference (larger files often have better coverage)
            size_mb = file_info.get("metadata", {}).get("size_mb", 0)
            if size_mb > 0:
                score += min(size_mb / 10.0, 5.0)  # Cap size bonus at 5.0
            
            # Resolution preference (smaller pixel size is better)
            pixel_size = file_info.get("metadata", {}).get("pixel_size_x", 30)
            if pixel_size <= 1.0:
                score += 3.0  # High resolution bonus
            elif pixel_size <= 5.0:
                score += 1.0  # Medium resolution bonus
            
            scored_files.append((score, file_info))
        
        # Return the highest scoring file
        scored_files.sort(key=lambda x: x[0], reverse=True)
        return scored_files[0][1]
    
    def _get_utm_zone_for_coordinate(self, lat: float, lon: float) -> int:
        """Determine UTM zone for given coordinates"""
        # UTM zone calculation for Australia
        # Brisbane area is UTM zone 56
        zone = int((lon + 180) / 6) + 1
        
        # Adjust for Australian specifics
        if -44 <= lat <= -10 and 112 <= lon <= 154:
            # Australian mainland
            if 144 <= lon <= 150:
                return 55  # Victoria, parts of NSW/SA
            elif 150 <= lon <= 156:
                return 56  # Queensland, eastern NSW
            elif 138 <= lon <= 144:
                return 54  # SA, western Victoria
            elif 132 <= lon <= 138:
                return 53  # NT, SA
            elif 126 <= lon <= 132:
                return 52  # WA
            elif 120 <= lon <= 126:
                return 51  # WA
            elif 114 <= lon <= 120:
                return 50  # WA
        
        return zone
    
    def find_nz_file_for_coordinate(self, lat: float, lon: float) -> Optional[str]:
        """Find NZ DEM file for given coordinates"""
        index = self.load_nz_index()
        if not index:
            return None
            
        # Search through all regions and surveys (NZ index structure: regions -> surveys -> files)
        for region_name, region_data in index.get("regions", {}).items():
            # Check if region has surveys (new structure) or files directly (old structure)
            if "surveys" in region_data:
                # New structure: regions -> surveys -> files
                for survey_name, survey_data in region_data.get("surveys", {}).items():
                    for file_info in survey_data.get("files", []):
                        bounds = file_info.get("bounds", {})
                        if (bounds.get("min_lat", 0) <= lat <= bounds.get("max_lat", 0) and
                            bounds.get("min_lon", 0) <= lon <= bounds.get("max_lon", 0)):
                            return file_info.get("file")
            else:
                # Old structure: regions -> files (fallback)
                for file_info in region_data.get("files", []):
                    bounds = file_info.get("bounds", {})
                    if (bounds.get("min_lat", 0) <= lat <= bounds.get("max_lat", 0) and
                        bounds.get("min_lon", 0) <= lon <= bounds.get("max_lon", 0)):
                        return file_info.get("file")
        return None

logger = logging.getLogger(__name__)

# S3CostManager now replaced with RedisS3CostManager for process-safe state management

class EnhancedSourceSelector:
    """Enhanced source selector with S3 → GPXZ → Google fallback chain"""
    
    def __init__(self, config: Dict, use_s3: bool = False, use_apis: bool = False, gpxz_config: Optional[GPXZConfig] = None, google_api_key: Optional[str] = None, aws_credentials: Optional[Dict] = None, redis_manager: Optional[RedisStateManager] = None):
        logger.info("=== EnhancedSourceSelector Initialization ===")
        logger.info(f"Parameters:")
        logger.info(f"  use_s3: {use_s3}")
        logger.info(f"  use_apis: {use_apis}")
        logger.info(f"  config sources: {list(config.keys())}")
        logger.info(f"  gpxz_config: {gpxz_config is not None}")
        logger.info(f"  google_api_key: {'set' if google_api_key else 'missing'}")
        logger.info(f"  aws_credentials: {'set' if aws_credentials else 'missing'}")
        logger.info(f"  redis_manager: {'provided' if redis_manager else 'creating new'}")
        
        self.config = config
        self.use_s3 = use_s3
        self.use_apis = use_apis
        self.aws_credentials = aws_credentials
        self.gpxz_client = None
        self.google_client = None
        
        # Initialize Redis state management
        self.redis_manager = redis_manager if redis_manager else RedisStateManager()
        self.cost_manager = RedisS3CostManager(self.redis_manager) if use_s3 else None
        
        # Initialize UnifiedIndexLoader for Phase 3 NZ S3 integration
        unified_loader = None
        if use_s3:
            try:
                unified_loader = UnifiedIndexLoader()
                logger.info("UnifiedIndexLoader initialized for NZ S3 index loading")
            except Exception as e:
                logger.warning(f"Failed to initialize UnifiedIndexLoader: {e}")
        
        self.spatial_index_loader = SpatialIndexLoader(unified_loader) if use_s3 else None
        
        # Phase 3 Selector with S3 index support
        if use_s3:
            import os
            use_s3_indexes = os.getenv("SPATIAL_INDEX_SOURCE", "local").lower() == "s3"
            logger.info(f"Initializing CampaignDatasetSelector with S3 indexes: {use_s3_indexes}")
            try:
                self.campaign_selector = CampaignDatasetSelector(use_s3_indexes=use_s3_indexes)
                logger.info(f"Campaign selector initialized: {self.campaign_selector is not None}")
                if self.campaign_selector and hasattr(self.campaign_selector, 'campaign_index'):
                    campaign_count = len(self.campaign_selector.campaign_index.get('datasets', {})) if self.campaign_selector.campaign_index else 0
                    logger.info(f"Campaign selector loaded {campaign_count} campaigns")
            except Exception as e:
                logger.error(f"Failed to initialize campaign selector: {e}")
                self.campaign_selector = None
        else:
            self.campaign_selector = None
            logger.info("Campaign selector not initialized (S3 disabled)")
        
        # Initialize GPXZ client with Redis state management
        if use_apis and gpxz_config:
            logger.info("Initializing GPXZ client with Redis state management...")
            try:
                self.gpxz_client = GPXZClient(gpxz_config, redis_manager=self.redis_manager)
                logger.info(f"GPXZ client initialized: {self.gpxz_client is not None}")
            except Exception as e:
                logger.error(f"Failed to initialize GPXZ client: {e}")
                self.gpxz_client = None
        else:
            logger.warning(f"GPXZ client NOT initialized (use_apis={use_apis}, "
                          f"gpxz_config={gpxz_config is not None})")
        
        # Initialize Google client with Redis state management
        if use_apis and google_api_key:
            logger.info("Initializing Google client with Redis state management...")
            try:
                self.google_client = GoogleElevationClient(google_api_key, redis_manager=self.redis_manager)
                logger.info(f"Google client initialized: {self.google_client is not None}")
            except Exception as e:
                logger.error(f"Failed to initialize Google client: {e}")
                self.google_client = None
        else:
            logger.warning(f"Google client NOT initialized (use_apis={use_apis}, "
                          f"google_api_key={'set' if google_api_key else 'missing'})")
        
        # Redis-based circuit breakers for external services (process-safe)
        self.circuit_breakers = {
            "gpxz_api": RedisCircuitBreaker(self.redis_manager, "gpxz_api", failure_threshold=3, recovery_timeout=300),
            "google_api": RedisCircuitBreaker(self.redis_manager, "google_api", failure_threshold=3, recovery_timeout=300),
            "s3_nz": RedisCircuitBreaker(self.redis_manager, "s3_nz", failure_threshold=5, recovery_timeout=180),
            "s3_au": RedisCircuitBreaker(self.redis_manager, "s3_au", failure_threshold=5, recovery_timeout=180)
        }
        logger.info(f"Circuit breakers initialized: {list(self.circuit_breakers.keys())}")
        
        self.attempted_sources = []
        
        # Log GDAL environment variables for debugging
        import os
        logger.info("GDAL environment variables:")
        for key, value in os.environ.items():
            if key.startswith(('GDAL_', 'CPL_', 'AWS_')):
                # Mask sensitive values
                if 'KEY' in key or 'SECRET' in key:
                    value = '***masked***'
                logger.info(f"  {key}={value}")
        
        # Check rasterio/GDAL version compatibility
        try:
            import rasterio
            logger.info(f"Rasterio version: {rasterio.__version__}")
            logger.info(f"GDAL version: {rasterio.__gdal_version__}")
        except ImportError as e:
            logger.error(f"Rasterio not available: {e}")
        
        logger.info("=== Initialization Complete ===")
    
    def _log_circuit_breaker_status(self):
        """Log status of all circuit breakers"""
        logger.info("Circuit breaker status:")
        for name, cb in self.circuit_breakers.items():
            state = "OPEN" if not cb.is_available() else "CLOSED"
            logger.info(f"  {name}: {state} (failures: {cb.failure_count}/{cb.failure_threshold})")
            if not cb.is_available():
                import time
                recovery_time = cb.last_failure_time + cb.recovery_timeout - time.time()
                logger.info(f"    Recovery in: {recovery_time:.1f} seconds")

    def reset_all_circuit_breakers(self):
        """Reset all circuit breakers for debugging"""
        logger.warning("Manually resetting all circuit breakers")
        for name, cb in self.circuit_breakers.items():
            cb.reset()
            logger.info(f"  Reset {name}")
    
    def select_best_source(self, lat: float, lon: float) -> Optional[str]:
        """Select best source using priority-based fallback: S3 → GPXZ → Google"""
        
        # Get sources sorted by priority
        sources_by_priority = self._get_sources_by_priority()
        
        # Try S3 sources first (priority 1)
        if self.use_s3 and 1 in sources_by_priority:
            # Check cost limits
            if self.cost_manager and not self.cost_manager.can_access_s3():
                logger.warning(f"S3 daily limit reached ({self.cost_manager.daily_gb_limit}GB), skipping S3 sources")
            else:
                for source_id in sources_by_priority[1]:
                    source_config = self.config[source_id]
                    if source_config.get('path', '').startswith('s3://'):
                        # Check if this S3 source covers the coordinates
                        if self._source_covers_coordinates(source_id, lat, lon):
                            logger.info(f"Selected S3 source '{source_id}' for ({lat}, {lon}) - priority 1")
                            return source_id
        
        # Try GPXZ API sources (priority 2)
        if self.use_apis and self.gpxz_client and 2 in sources_by_priority:
            for source_id in sources_by_priority[2]:
                source_config = self.config[source_id]
                if source_config.get('path', '').startswith('api://gpxz'):
                    logger.info(f"Selected GPXZ API source '{source_id}' for ({lat}, {lon}) - priority 2")
                    return source_id
        
        # Try Google Elevation API (priority 3)
        if self.use_apis and self.google_client and 3 in sources_by_priority:
            for source_id in sources_by_priority[3]:
                source_config = self.config[source_id]
                if source_config.get('path', '').startswith('api://google'):
                    logger.info(f"Selected Google API source '{source_id}' for ({lat}, {lon}) - priority 3")
                    return source_id
        
        logger.warning(f"No elevation sources available for ({lat}, {lon}) - all sources exhausted")
        return None
    
    async def get_elevation_with_resilience(self, lat: float, lon: float) -> Dict[str, Any]:
        """Get elevation with comprehensive error handling and campaign intelligence"""
        logger.info(f"=== Starting elevation query for ({lat}, {lon}) ===")
        self.attempted_sources = []
        last_error = None
        
        # Try sources in priority order: S3 → GPXZ → Google
        source_attempts = [
            ("s3_sources", self._try_s3_sources_with_campaigns),
            ("gpxz_api", self._try_gpxz_source),
            ("google_api", self._try_google_source)
        ]
        
        logger.info(f"Configured source attempts: {[name for name, func in source_attempts]}")
        logger.info(f"Source functions available:")
        for name, func in source_attempts:
            logger.info(f"  {name}: {func is not None} ({func.__name__ if func else 'None'})")
        
        # Check what's enabled
        logger.info(f"Source availability:")
        logger.info(f"  S3 enabled: {self.use_s3}, campaign_selector: {self.campaign_selector is not None}")
        logger.info(f"  GPXZ enabled: {self.use_apis}, client: {self.gpxz_client is not None}")
        logger.info(f"  Google enabled: {self.use_apis}, client: {self.google_client is not None}")
        
        # Log circuit breaker status
        self._log_circuit_breaker_status()
        
        for source_name, source_func in source_attempts:
            try:
                logger.info(f"--- Attempting source: {source_name} ---")
                self.attempted_sources.append(source_name)
                
                # Check circuit breaker
                if source_name in self.circuit_breakers:
                    cb = self.circuit_breakers[source_name]
                    if not cb.is_available():
                        logger.warning(f"Circuit breaker open for {source_name}, skipping")
                        continue
                
                # Check if source function is available
                if source_func is None:
                    logger.warning(f"Source function not available for {source_name}")
                    continue
                
                # Try source with retry logic
                logger.info(f"Calling {source_name} with retry logic...")
                result = await retry_with_backoff(
                    lambda: source_func(lat, lon),
                    max_retries=2,
                    exceptions=(RetryableError,)
                )
                
                logger.info(f"Result from {source_name}: {type(result)} = {result}")
                
                if result is not None:
                    # Record success for circuit breaker
                    if source_name in self.circuit_breakers:
                        self.circuit_breakers[source_name].record_success()
                    
                    # Handle different result types (campaign info vs simple elevation)
                    if isinstance(result, dict) and 'elevation_m' in result:
                        # Campaign-based result with metadata
                        elevation = result['elevation_m']
                        source_id = result.get('campaign_id', source_name)
                        campaign_info = result.get('campaign_info', {})
                        
                        logger.info(f"Successfully got elevation from campaign {source_id}: {elevation}m")
                        return {
                            "elevation_m": elevation,
                            "success": True,
                            "source": source_id,
                            "campaign_info": campaign_info,
                            "attempted_sources": self.attempted_sources.copy()
                        }
                    else:
                        # Simple elevation value (GPXZ/Google APIs)
                        elevation = result
                        logger.info(f"Successfully got elevation from {source_name}: {elevation}m")
                        return {
                            "elevation_m": elevation,
                            "success": True,
                            "source": source_name,
                            "attempted_sources": self.attempted_sources.copy()
                        }
                else:
                    logger.warning(f"Source {source_name} returned None")
                
            except Exception as e:
                last_error = e
                logger.error(f"Source {source_name} failed: {type(e).__name__}: {e}")
                logger.error(f"Full exception details:", exc_info=True)
                
                # Record failure for circuit breaker
                if source_name in self.circuit_breakers:
                    self.circuit_breakers[source_name].record_failure()
                
                continue
        
        # All sources failed
        logger.error(f"All elevation sources failed for ({lat}, {lon})")
        logger.error(f"Attempted sources: {self.attempted_sources}")
        logger.error(f"Last error: {last_error}")
        return create_unified_error_response(
            last_error or Exception("No sources available"),
            lat, lon, self.attempted_sources
        )
    
    async def _try_s3_sources_with_campaigns(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Try S3 sources using Phase 3 campaign-based selection"""
        if not self.use_s3:
            return None
            
        try:
            # Check cost limits
            if self.cost_manager and not self.cost_manager.can_access_s3():
                raise NonRetryableError("S3 daily cost limit reached", SourceType.S3)
            
            # Phase 3: Use campaign-based smart selection
            if self.campaign_selector:
                return await self._try_campaign_selection(lat, lon)
            
            # Fallback to legacy spatial index approach
            logger.warning("Campaign selector not available, falling back to legacy S3 approach")
            elevation = await self._try_s3_sources_legacy(lat, lon)
            if elevation is not None:
                return {
                    "elevation_m": elevation,
                    "campaign_id": "legacy_s3_fallback",
                    "campaign_info": {
                        "selection_method": "legacy_spatial_index",
                        "resolution_m": "unknown"
                    }
                }
            
            return None
        except Exception as e:
            raise RetryableError(f"S3 campaign source error: {e}", SourceType.S3)
    
    async def _try_campaign_selection(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Use Phase 3 campaign-based selection for maximum performance and intelligence"""
        try:
            # Check if coordinates are in New Zealand first
            if self._is_new_zealand_coordinate(lat, lon):
                logger.info(f"Coordinate ({lat}, {lon}) detected as New Zealand - trying NZ S3 sources")
                nz_elevation = await self._try_nz_source(lat, lon)
                if nz_elevation is not None:
                    return {
                        "elevation_m": nz_elevation,
                        "campaign_id": "nz_s3_source",
                        "campaign_info": {
                            "selection_method": "nz_geographic_routing",
                            "resolution_m": "1m",
                            "source": "nz-elevation S3 bucket"
                        }
                    }
            
            # Get the best campaigns for this coordinate using multi-factor scoring
            campaign_matches = self.campaign_selector.select_campaigns_for_coordinate(lat, lon)
            
            if not campaign_matches:
                logger.info(f"No campaigns found for coordinate ({lat}, {lon})")
                return None
            
            # Try campaigns in order of total score (highest first)
            for campaign_match in campaign_matches[:3]:  # Try top 3 campaigns
                try:
                    logger.info(f"Trying campaign {campaign_match.campaign_id} (score: {campaign_match.total_score:.3f})")
                    
                    # Find files in this campaign for the coordinate
                    matching_files, campaigns_searched = self.campaign_selector.find_files_for_coordinate(
                        lat, lon, max_campaigns=1
                    )
                    
                    if matching_files:
                        # Try to extract elevation from the first matching file
                        for file_info in matching_files[:1]:  # Use the best file
                            s3_path = file_info.get('file', '')
                            if s3_path.startswith('s3://'):
                                elevation = await self._extract_elevation_from_s3_file(
                                    s3_path, lat, lon, use_credentials=True
                                )
                                
                                if elevation is not None:
                                    # Success! Return with full campaign intelligence
                                    campaign_info = campaign_match.campaign_info
                                    speedup_factor = 631556 // max(campaign_match.file_count, 1)
                                    
                                    logger.info(f"SUCCESS: Campaign {campaign_match.campaign_id} "
                                              f"({campaign_match.file_count} files, {speedup_factor}x speedup)")
                                    
                                    return {
                                        "elevation_m": elevation,
                                        "campaign_id": campaign_match.campaign_id,
                                        "campaign_info": {
                                            "provider": campaign_info.get("provider", "unknown"),
                                            "resolution_m": campaign_info.get("resolution_m", "unknown"),
                                            "campaign_year": campaign_info.get("campaign_year", "unknown"),
                                            "confidence_score": campaign_match.confidence_score,
                                            "temporal_score": campaign_match.temporal_score,
                                            "resolution_score": campaign_match.resolution_score,
                                            "total_score": campaign_match.total_score,
                                            "file_count": campaign_match.file_count,
                                            "speedup_factor": f"{speedup_factor}x vs flat search",
                                            "files_searched": campaign_match.file_count,
                                            "files_total": 631556
                                        }
                                    }
                
                except Exception as e:
                    logger.warning(f"Campaign {campaign_match.campaign_id} failed: {e}")
                    continue
            
            logger.info(f"All campaigns failed for coordinate ({lat}, {lon})")
            return None
            
        except Exception as e:
            logger.error(f"Campaign selection failed: {e}")
            raise RetryableError(f"Campaign selection error: {e}", SourceType.S3)

    async def _try_s3_sources_legacy(self, lat: float, lon: float) -> Optional[float]:
        """Legacy S3 sources approach (both NZ and AU) - fallback when campaigns fail"""
        try:
            # Try NZ sources first (free)
            if self.spatial_index_loader:
                nz_elevation = await self._try_nz_source(lat, lon)
                if nz_elevation is not None:
                    return nz_elevation
            
            # Try AU sources with the robust fallback logic
            if self.spatial_index_loader:
                au_elevation = await self._try_s3_au_source_with_fallback(lat, lon)
                if au_elevation is not None:
                    return au_elevation
            
            return None
        except Exception as e:
            raise RetryableError(f"Legacy S3 source error: {e}", SourceType.S3)
    
    async def _try_nz_source(self, lat: float, lon: float) -> Optional[float]:
        """Try NZ Open Data source using industry best practices"""
        if not self.use_s3 or not self.spatial_index_loader:
            return None
            
        try:
            dem_file = self.spatial_index_loader.find_nz_file_for_coordinate(lat, lon)
            if dem_file:
                logger.info(f"Found NZ DEM file: {dem_file}")
                
                # Apply industry best practices for public S3 access
                elevation = await self._extract_elevation_from_s3_file(dem_file, lat, lon, use_credentials=False)
                if elevation is not None:
                    return elevation
                else:
                    # No mock elevation - let the fallback chain handle it
                    logger.info(f"NZ DEM file does not cover coordinates ({lat}, {lon}) - returning None for fallback")
                    return None
            return None
        except Exception as e:
            raise RetryableError(f"NZ S3 source error: {e}", SourceType.S3)
    
    async def _try_gpxz_source(self, lat: float, lon: float) -> Optional[float]:
        """Try GPXZ API source"""
        if not self.gpxz_client:
            return None
            
        try:
            # Check daily limits
            stats = await self.gpxz_client.get_usage_stats()
            if stats["requests_remaining"] <= 0:
                raise NonRetryableError("GPXZ daily limit exceeded", SourceType.API)
            
            elevation = await self.gpxz_client.get_elevation_point(lat, lon)
            return elevation
            
        except Exception as e:
            if "timeout" in str(e).lower():
                raise RetryableError(f"GPXZ timeout: {e}", SourceType.API)
            elif "server error" in str(e).lower():
                raise RetryableError(f"GPXZ server error: {e}", SourceType.API)
            else:
                raise NonRetryableError(f"GPXZ client error: {e}", SourceType.API)
    
    def _is_new_zealand_coordinate(self, lat: float, lon: float) -> bool:
        """Check if coordinates are within New Zealand geographic bounds"""
        # New Zealand bounds: approximately -47.3 to -34.4 latitude, 166.4 to 178.6 longitude
        # Include some buffer for offshore islands
        return (-47.5 <= lat <= -34.0) and (166.0 <= lon <= 179.0)
    
    async def _try_s3_au_source_with_fallback(self, lat: float, lon: float) -> Optional[float]:
        """
        Try Australian S3 sources with a robust Phase 3 -> Phase 2 fallback.
        This implements the critical file-level fallback chain.
        """
        if not self.use_s3 or not self.campaign_selector:
            return None

        # Phase 3: Campaign-based search (high-performance)
        logger.info(f"Starting Phase 3 campaign search for ({lat}, {lon})")
        try:
            # 1. Get candidate files from the Phase 3 selector
            phase3_files, campaigns_searched = self.campaign_selector.find_files_for_coordinate(lat, lon, max_campaigns=3)

            if phase3_files:
                logger.info(f"Phase 3: Found {len(phase3_files)} candidate files in campaigns: {campaigns_searched}")
                # 2. Iterate through candidate files with file-level fallback
                for i, file_info in enumerate(phase3_files):
                    dem_key = file_info.get("key")
                    if not dem_key:
                        continue
                    
                    logger.debug(f"Phase 3: Attempting file {i+1}/{len(phase3_files)}: {dem_key}")
                    elevation = await self._extract_elevation_from_s3_file(dem_key, lat, lon, use_credentials=True)
                    
                    if elevation is not None:
                        logger.info(f"SUCCESS (Phase 3): Found elevation {elevation}m in {dem_key}")
                        if self.cost_manager:
                            self.cost_manager.record_access(file_info.get("size_mb", 10))
                        return elevation
                    # If elevation is None, it means file didn't cover point or had nodata. Continue to next file.
                
                logger.warning(f"Phase 3: Exhausted {len(phase3_files)} candidate files with no elevation found.")
            else:
                logger.info(f"Phase 3: No candidate files found by campaign selector.")

        except Exception as e:
            logger.error(f"Error during Phase 3 campaign search: {e}", exc_info=True)
            # Fall through to Phase 2 on error

        # Phase 2: Grouped dataset fallback (lower-performance)
        logger.info(f"Falling back to Phase 2 grouped dataset search for ({lat}, {lon})")
        try:
            if not self.spatial_index_loader:
                return None

            # 3. Get candidate files from the Phase 2 selector
            # Skip Phase 2 selector - use direct file access instead
            phase2_files = []
            datasets_searched = 0

            if phase2_files:
                logger.info(f"Phase 2: Found {len(phase2_files)} candidate files in datasets: {datasets_searched}")
                # 4. Iterate through candidate files with file-level fallback
                for i, file_info in enumerate(phase2_files):
                    dem_key = file_info.get("key")
                    if not dem_key:
                        continue

                    logger.debug(f"Phase 2: Attempting file {i+1}/{len(phase2_files)}: {dem_key}")
                    elevation = await self._extract_elevation_from_s3_file(dem_key, lat, lon, use_credentials=True)

                    if elevation is not None:
                        logger.info(f"SUCCESS (Phase 2): Found elevation {elevation}m in {dem_key}")
                        if self.cost_manager:
                            self.cost_manager.record_access(file_info.get("size_mb", 10))
                        return elevation
                
                logger.warning(f"Phase 2: Exhausted {len(phase2_files)} candidate files with no elevation found.")
            else:
                logger.info(f"Phase 2: No candidate files found by grouped selector.")

        except Exception as e:
            logger.error(f"Error during Phase 2 grouped search: {e}", exc_info=True)

        logger.warning(f"S3 Search Exhausted: No AU DEM files cover coordinates ({lat}, {lon}). Will fall back to external APIs.")
        return None
    
    async def _try_google_source(self, lat: float, lon: float) -> Optional[float]:
        """Try Google Elevation API source"""
        if not self.google_client:
            return None
            
        try:
            # Check daily limits
            if not self.google_client.can_make_request():
                raise NonRetryableError("Google API daily limit exceeded", SourceType.API)
            
            elevation = await self.google_client.get_elevation_async(lat, lon)
            return elevation
            
        except Exception as e:
            if "timeout" in str(e).lower():
                raise RetryableError(f"Google API timeout: {e}", SourceType.API)
            elif "server error" in str(e).lower():
                raise RetryableError(f"Google API server error: {e}", SourceType.API)
            else:
                raise NonRetryableError(f"Google API client error: {e}", SourceType.API)
    
    async def get_elevation_from_api(self, lat: float, lon: float, source_id: str) -> Optional[float]:
        """Get elevation from API sources"""
        if source_id.startswith("gpxz_") and self.gpxz_client:
            return await self.gpxz_client.get_elevation_point(lat, lon)
        elif source_id == "google_elevation" and self.google_client:
            return await self.google_client.get_elevation_async(lat, lon)
        
        return None
    
    def _get_sources_by_priority(self) -> Dict[int, List[str]]:
        """Get sources grouped by priority level"""
        sources_by_priority = {}
        
        for source_id, source_config in self.config.items():
            priority = source_config.get('priority', 999)  # Default to low priority
            if priority not in sources_by_priority:
                sources_by_priority[priority] = []
            sources_by_priority[priority].append(source_id)
        
        return sources_by_priority
    
    def _source_covers_coordinates(self, source_id: str, lat: float, lon: float) -> bool:
        """Check if a source covers the given coordinates using spatial index"""
        source_config = self.config[source_id]
        path = source_config.get('path', '')
        
        # For unified Australian spatial index source
        if source_id == 'au_spatial_index' and self.spatial_index_loader:
            return self.spatial_index_loader.find_au_file_for_coordinate(lat, lon) is not None
            
        # For Australian S3 sources, use spatial index to find actual file match
        elif path.startswith('s3://road-engineering-elevation-data') and self.spatial_index_loader:
            au_file = self.spatial_index_loader.find_au_file_for_coordinate(lat, lon)
            if au_file:
                # Check if the found file matches this source's directory path
                return au_file.startswith(path) or path.rstrip('/') in au_file
            return False
            
        # For NZ sources, check with spatial index
        elif path.startswith('s3://nz-elevation') and self.spatial_index_loader:
            nz_file = self.spatial_index_loader.find_nz_file_for_coordinate(lat, lon)
            if nz_file:
                return nz_file.startswith(path) or path.rstrip('/') in nz_file
            return False
        
        # For API sources, assume global coverage
        if path.startswith('api://'):
            return True
        
        # For other sources, assume they cover the coordinates
        return True
    
    async def _extract_elevation_from_s3_file(self, dem_file: str, lat: float, lon: float, use_credentials: bool = True) -> Optional[float]:
        """
        Extract elevation from S3 DEM file with comprehensive error logging
        
        IMPORTANT CORRECTION: dem_file is an S3 key, not a full s3:// URL
        """
        import asyncio
        import os
        import boto3
        from botocore.exceptions import ClientError
        import numpy as np
        
        logger.info(f"Starting S3 extraction: key={dem_file} for ({lat}, {lon})")
        
        def _sync_extract_elevation(dem_file_param):
            """Synchronous elevation extraction with enhanced logging"""
            try:
                import rasterio
                from rasterio.errors import RasterioIOError
                import psutil
                
                # Parse bucket name and key from S3 URL or use default
                if dem_file_param.startswith("s3://"):
                    # Full S3 URL: s3://bucket-name/path/to/file
                    parts = dem_file_param[5:].split("/", 1)  # Remove s3:// and split on first /
                    bucket_name = parts[0]
                    file_key = parts[1] if len(parts) > 1 else ""
                    logger.info(f"Parsed S3 URL: bucket={bucket_name}, key={file_key}")
                else:
                    # Assume it's just a key for the default bucket
                    bucket_name = "road-engineering-elevation-data"
                    file_key = dem_file_param
                    logger.info(f"Using default bucket: {bucket_name}, key={file_key}")
                
                # Use the parsed file_key for S3 operations
                dem_file_local = file_key
                
                # Test S3 accessibility
                if use_credentials and bucket_name != "nz-elevation":
                    # Private bucket - requires AWS credentials
                    s3_client = boto3.client('s3', 
                        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                        region_name=os.getenv('AWS_DEFAULT_REGION', 'ap-southeast-2')
                    )
                else:
                    # NZ Open Data bucket or public access - no credentials required
                    from botocore import UNSIGNED
                    from botocore.config import Config
                    s3_client = boto3.client('s3',
                        region_name='ap-southeast-2',
                        config=Config(signature_version=UNSIGNED)
                    )
                
                # Check if file exists
                try:
                    response = s3_client.head_object(Bucket=bucket_name, Key=dem_file_local)
                    logger.info(f"S3 file exists: size={response['ContentLength']} bytes, "
                               f"type={response.get('ContentType', 'unknown')}, "
                               f"modified={response['LastModified']}")
                except ClientError as e:
                    error_code = e.response['Error']['Code']
                    logger.error(f"S3 access error: {error_code} - {e}")
                    if error_code == '404':
                        logger.error(f"File not found in S3: {bucket_name}/{dem_file_local}")
                    elif error_code == '403':
                        logger.error(f"Access denied to S3 file (check IAM permissions)")
                    return None
                
                # Construct VSI path for GDAL
                vsi_path = f"/vsis3/{bucket_name}/{dem_file_local}"
                logger.info(f"Opening rasterio dataset from VSI path: {vsi_path}")
                
                # Monitor memory before opening large file
                process = psutil.Process()
                memory_before = process.memory_info().rss / 1024 / 1024
                logger.info(f"Memory before S3 open: {memory_before:.2f} MB")
                
                # Set AWS environment variables if needed
                if use_credentials:
                    if self.aws_credentials:
                        os.environ['AWS_ACCESS_KEY_ID'] = self.aws_credentials['access_key_id']
                        os.environ['AWS_SECRET_ACCESS_KEY'] = self.aws_credentials['secret_access_key']
                        os.environ['AWS_DEFAULT_REGION'] = self.aws_credentials.get('region', 'ap-southeast-2')
                    else:
                        # Use environment variables directly
                        logger.info("Using AWS credentials from environment variables")
                
                # Configure GDAL for optimal cloud access with connection pooling
                os.environ['GDAL_DISABLE_READDIR_ON_OPEN'] = 'EMPTY_DIR'
                os.environ['CPL_VSIL_CURL_CACHE_SIZE'] = '200000000'  # 200MB cache
                os.environ['GDAL_HTTP_TIMEOUT'] = '8'
                os.environ['GDAL_HTTP_CONNECTTIMEOUT'] = '8'
                os.environ['CPL_VSIL_CURL_ALLOWED_EXTENSIONS'] = '.tif,.tiff,.vrt'
                os.environ['CPL_VSIL_CURL_USE_HEAD'] = 'NO'  # Skip HEAD requests for faster startup
                os.environ['GDAL_HTTP_MAX_RETRY'] = '1'  # Fast fail with single retry
                os.environ['CPL_CURL_VERBOSE'] = 'NO'  # Reduce logging overhead
                
                # Configure GDAL for unsigned S3 access (NZ Open Data bucket)
                if bucket_name == "nz-elevation":
                    os.environ['AWS_NO_SIGN_REQUEST'] = 'YES'
                    logger.info("Configured GDAL for unsigned S3 access (NZ bucket)")
                else:
                    # Remove unsigned access flag for private buckets
                    if 'AWS_NO_SIGN_REQUEST' in os.environ:
                        del os.environ['AWS_NO_SIGN_REQUEST']
                
                with rasterio.open(vsi_path) as dataset:
                    # Log dataset properties
                    logger.info(f"Dataset opened successfully")
                    logger.info(f"  Driver: {dataset.driver}")
                    logger.info(f"  CRS: {dataset.crs}")
                    logger.info(f"  Bounds: {dataset.bounds}")
                    logger.info(f"  Shape: {dataset.shape}")
                    logger.info(f"  Transform: {dataset.transform}")
                    logger.info(f"  Bands: {dataset.count}")
                    logger.info(f"  Data types: {dataset.dtypes}")
                    logger.info(f"  Nodata value: {dataset.nodata}")
                    
                    # Check if coordinate is within bounds
                    if not (dataset.bounds.left <= lon <= dataset.bounds.right and 
                            dataset.bounds.bottom <= lat <= dataset.bounds.top):
                        logger.warning(f"Coordinate ({lat}, {lon}) outside dataset bounds")
                        logger.warning(f"  Bounds: left={dataset.bounds.left}, right={dataset.bounds.right}, "
                                      f"bottom={dataset.bounds.bottom}, top={dataset.bounds.top}")
                        return None
                    
                    # Transform coordinate to pixel indices
                    try:
                        row, col = dataset.index(lon, lat)
                        logger.info(f"Pixel coordinates: row={row}, col={col}")
                        
                        # Validate pixel indices
                        if row < 0 or col < 0 or row >= dataset.shape[0] or col >= dataset.shape[1]:
                            logger.error(f"Pixel indices out of bounds: row={row}, col={col}, "
                                        f"shape={dataset.shape}")
                            return None
                            
                    except Exception as e:
                        logger.error(f"Coordinate transformation failed: {e}")
                        return None
                    
                    # Read elevation value
                    try:
                        elevation = dataset.read(1)[row, col]
                        logger.info(f"Raw elevation value: {elevation}, type: {type(elevation)}")
                        
                        # Check for nodata
                        if dataset.nodata is not None and elevation == dataset.nodata:
                            logger.warning(f"Elevation is nodata value: {dataset.nodata}")
                            return None
                        
                        # Check for invalid values
                        if np.isnan(elevation) or np.isinf(elevation):
                            logger.warning(f"Invalid elevation value: {elevation}")
                            return None
                            
                        return float(elevation)
                        
                    except IndexError as e:
                        logger.error(f"Index error reading elevation: {e}")
                        logger.error(f"Attempted to read row={row}, col={col} from shape={dataset.shape}")
                        return None
                        
            except ImportError as e:
                logger.error(f"Rasterio import error: {e}")
                logger.error("Check if rasterio is installed in requirements.txt")
                return None
            except MemoryError as e:
                memory_current = process.memory_info().rss / 1024 / 1024
                logger.error(f"Memory error: current usage {memory_current:.2f} MB")
                logger.error(f"Memory increase: {memory_current - memory_before:.2f} MB")
                return None
            except Exception as e:
                logger.error(f"S3 extraction failed: {type(e).__name__}: {e}")
                logger.error(f"Full traceback:", exc_info=True)
                return None
            finally:
                # Log memory after operation
                if 'process' in locals():
                    memory_after = process.memory_info().rss / 1024 / 1024
                    logger.info(f"Memory after S3 operation: {memory_after:.2f} MB")
        
        try:
            # Run the synchronous function in a thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            elevation = await loop.run_in_executor(None, _sync_extract_elevation, dem_file)
            return elevation
        except Exception as e:
            logger.error(f"Error in async elevation extraction: {e}")
            return None

    async def close(self):
        """Clean up resources"""
        if self.gpxz_client:
            await self.gpxz_client.close()
        if self.google_client:
            await self.google_client.close()

        logger.info("EnhancedSourceSelector resources cleaned up.")
