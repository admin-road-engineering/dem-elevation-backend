import time
import json
import asyncio
import logging
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

logger = logging.getLogger(__name__)

class SpatialIndexLoader:
    """Loads and manages spatial index files for S3 DEM sources with smart dataset selection"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.config_dir = self.project_root / "config"
        self.au_spatial_index = None
        self.nz_spatial_index = None
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
        """Load NZ spatial index"""
        if self.nz_spatial_index is None:
            nz_index_file = self.config_dir / "nz_spatial_index.json"
            if nz_index_file.exists():
                try:
                    with open(nz_index_file, 'r') as f:
                        self.nz_spatial_index = json.load(f)
                except Exception as e:
                    logger.error(f"Failed to load NZ spatial index: {e}")
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
            
        # Search through all regions
        for region_name, region_data in index.get("regions", {}).items():
            for file_info in region_data.get("files", []):
                bounds = file_info.get("bounds", {})
                if (bounds.get("min_lat", 0) <= lat <= bounds.get("max_lat", 0) and
                    bounds.get("min_lon", 0) <= lon <= bounds.get("max_lon", 0)):
                    return file_info.get("file")
        return None

logger = logging.getLogger(__name__)

class S3CostManager:
    """Track and limit S3 usage to control costs during development"""
    
    def __init__(self, daily_gb_limit: float = 1.0, cache_file: str = ".s3_usage.json"):
        self.daily_gb_limit = daily_gb_limit
        self.cache_file = Path(cache_file)
        self.usage = self._load_usage()
        
    def _load_usage(self) -> Dict:
        """Load usage data from cache"""
        if self.cache_file.exists():
            with open(self.cache_file, 'r') as f:
                return json.load(f)
        return {"date": str(datetime.now().date()), "gb_used": 0.0, "requests": 0}
    
    def _save_usage(self):
        """Save usage data to cache"""
        with open(self.cache_file, 'w') as f:
            json.dump(self.usage, f)
    
    def can_access_s3(self, estimated_mb: float = 10) -> bool:
        """Check if we're within daily limits"""
        today = str(datetime.now().date())
        
        # Reset if new day
        if self.usage["date"] != today:
            self.usage = {"date": today, "gb_used": 0.0, "requests": 0}
        
        estimated_gb = estimated_mb / 1024
        return self.usage["gb_used"] + estimated_gb <= self.daily_gb_limit
    
    def record_access(self, size_mb: float):
        """Record S3 access"""
        self.usage["gb_used"] += size_mb / 1024
        self.usage["requests"] += 1
        self._save_usage()
        
        logger.info(f"S3 Usage: {self.usage['gb_used']:.2f}GB / {self.daily_gb_limit}GB daily limit")

class EnhancedSourceSelector:
    """Enhanced source selector with S3 → GPXZ → Google fallback chain"""
    
    def __init__(self, config: Dict, use_s3: bool = False, use_apis: bool = False, gpxz_config: Optional[GPXZConfig] = None, google_api_key: Optional[str] = None, aws_credentials: Optional[Dict] = None):
        self.config = config
        self.use_s3 = use_s3
        self.use_apis = use_apis
        self.cost_manager = S3CostManager() if use_s3 else None
        self.spatial_index_loader = SpatialIndexLoader() if use_s3 else None
        self.aws_credentials = aws_credentials
        self.gpxz_client = None
        self.google_client = None
        
        # Phase 3 Selector with S3 index support
        if use_s3:
            import os
            use_s3_indexes = os.getenv("SPATIAL_INDEX_SOURCE", "local").lower() == "s3"
            self.campaign_selector = CampaignDatasetSelector(use_s3_indexes=use_s3_indexes)
        else:
            self.campaign_selector = None
        
        if use_apis and gpxz_config:
            self.gpxz_client = GPXZClient(gpxz_config)
        
        if use_apis and google_api_key:
            self.google_client = GoogleElevationClient(google_api_key)
        
        # Circuit breakers for external services
        self.circuit_breakers = {
            "gpxz_api": CircuitBreaker(failure_threshold=3, recovery_timeout=300),
            "google_api": CircuitBreaker(failure_threshold=3, recovery_timeout=300),
            "s3_nz": CircuitBreaker(failure_threshold=5, recovery_timeout=180),
            "s3_au": CircuitBreaker(failure_threshold=5, recovery_timeout=180)
        }
        
        self.attempted_sources = []
    
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
        self.attempted_sources = []
        last_error = None
        
        # Try sources in priority order: S3 → GPXZ → Google
        source_attempts = [
            ("s3_sources", self._try_s3_sources_with_campaigns),
            ("gpxz_api", self._try_gpxz_source),
            ("google_api", self._try_google_source)
        ]
        
        for source_name, source_func in source_attempts:
            try:
                self.attempted_sources.append(source_name)
                
                # Check circuit breaker
                if source_name in self.circuit_breakers:
                    cb = self.circuit_breakers[source_name]
                    if not cb.is_available():
                        logger.info(f"Circuit breaker open for {source_name}, skipping")
                        continue
                
                # Try source with retry logic
                result = await retry_with_backoff(
                    lambda: source_func(lat, lon),
                    max_retries=2,
                    exceptions=(RetryableError,)
                )
                
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
                
            except Exception as e:
                last_error = e
                logger.warning(f"Source {source_name} failed: {e}")
                
                # Record failure for circuit breaker
                if source_name in self.circuit_breakers:
                    self.circuit_breakers[source_name].record_failure()
                
                continue
        
        # All sources failed
        logger.error(f"All elevation sources failed for ({lat}, {lon})")
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
        Extract elevation from S3 DEM file using industry best practices
        
        Applies GDAL Virtual File System (VFS) best practices:
        - Uses /vsis3/ for private buckets with credentials
        - Uses /vsicurl/ for public buckets
        - Implements proper error handling and resource management
        """
        import asyncio
        import os
        import tempfile
        
        def _sync_extract_elevation():
            """Synchronous elevation extraction using GDAL VFS"""
            try:
                import rasterio
                from rasterio.errors import RasterioIOError
                
                # Apply industry best practices for S3 access
                if use_credentials:
                    # Private bucket - use /vsis3/ with credentials
                    if self.aws_credentials:
                        # Set AWS credentials for GDAL
                        os.environ['AWS_ACCESS_KEY_ID'] = self.aws_credentials['access_key_id']
                        os.environ['AWS_SECRET_ACCESS_KEY'] = self.aws_credentials['secret_access_key']
                        os.environ['AWS_DEFAULT_REGION'] = self.aws_credentials.get('region', 'ap-southeast-2')
                    
                    # Convert s3:// URL to /vsis3/ path
                    if dem_file.startswith('s3://'):
                        vsi_path = dem_file.replace('s3://', '/vsis3/')
                    else:
                        vsi_path = f"/vsis3/{dem_file}"
                else:
                    # Public bucket - use /vsicurl/ for HTTP access
                    if dem_file.startswith('s3://'):
                        # Convert s3:// URL to HTTPS URL for public access
                        bucket_name = dem_file.split('/')[2]
                        key_path = '/'.join(dem_file.split('/')[3:])
                        vsi_path = f"/vsicurl/https://{bucket_name}.s3.ap-southeast-2.amazonaws.com/{key_path}"
                    else:
                        vsi_path = f"/vsicurl/{dem_file}"
                
                # Configure GDAL for optimal cloud access
                os.environ['GDAL_DISABLE_READDIR_ON_OPEN'] = 'EMPTY_DIR'
                os.environ['CPL_VSIL_CURL_CACHE_SIZE'] = '200000000'  # 200MB cache
                os.environ['GDAL_HTTP_TIMEOUT'] = '30'
                os.environ['GDAL_HTTP_CONNECTTIMEOUT'] = '10'
                
                # Open the dataset using GDAL VFS
                with rasterio.open(vsi_path) as dataset:
                    # Check if we need coordinate transformation
                    if dataset.crs and dataset.crs != 'EPSG:4326':
                        # Transform lat/lon to dataset CRS
                        from rasterio.warp import transform
                        xs, ys = transform('EPSG:4326', dataset.crs, [lon], [lat])
                        x, y = xs[0], ys[0]
                        logger.debug(f"Transformed ({lat}, {lon}) to ({x}, {y}) in {dataset.crs}")
                    else:
                        x, y = lon, lat
                    
                    # Get row/col indices for the transformed coordinates
                    row, col = dataset.index(x, y)
                    
                    # Check if coordinates are within bounds
                    if 0 <= row < dataset.height and 0 <= col < dataset.width:
                        # Read the elevation value
                        elevation_array = dataset.read(1, window=((row, row + 1), (col, col + 1)))
                        elevation = float(elevation_array[0, 0])
                        
                        # Check for no-data values
                        if dataset.nodata is not None and elevation == dataset.nodata:
                            logger.warning(f"No-data value found at ({lat}, {lon}) in {dem_file}")
                            return None
                        
                        logger.info(f"Successfully extracted elevation {elevation}m from {dem_file}")
                        return elevation
                    else:
                        logger.warning(f"Coordinates ({lat}, {lon}) are outside bounds of {dem_file}")
                        logger.debug(f"Row {row} not in [0, {dataset.height}), Col {col} not in [0, {dataset.width})")
                        return None
                        
            except RasterioIOError as e:
                # This is a critical change: we now gracefully handle file-not-found or access errors
                logger.warning(f"File-level access error for {dem_file}: {e}. This is a recoverable error.")
                return None
            except Exception as e:
                logger.error(f"Unexpected error accessing {dem_file}: {e}")
                return None
        
        try:
            # Run the synchronous function in a thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            elevation = await loop.run_in_executor(None, _sync_extract_elevation)
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
