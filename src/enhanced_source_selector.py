import time
import json
import asyncio
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime

from src.s3_source_manager import S3SourceManager, DEMMetadata
from src.gpxz_client import GPXZClient, GPXZConfig
from src.error_handling import (
    CircuitBreaker, RetryableError, NonRetryableError, 
    create_unified_error_response, retry_with_backoff, SourceType
)

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
    """Enhanced source selector with APIs, S3 catalog and cost awareness"""
    
    def __init__(self, config: Dict, use_s3: bool = False, use_apis: bool = False, gpxz_config: Optional[GPXZConfig] = None):
        self.config = config
        self.use_s3 = use_s3
        self.use_apis = use_apis
        self.cost_manager = S3CostManager() if use_s3 else None
        self.s3_managers = {}
        self.gpxz_client = None
        
        if use_apis and gpxz_config:
            self.gpxz_client = GPXZClient(gpxz_config)
        
        if use_s3:
            # Initialize S3 managers for different buckets
            self.s3_managers['nz'] = S3SourceManager('nz-elevation')
            self.s3_managers['au'] = S3SourceManager('road-engineering-elevation-data')
        
        # Circuit breakers for external services
        self.circuit_breakers = {
            "gpxz_api": CircuitBreaker(failure_threshold=3, recovery_timeout=300),
            "s3_nz": CircuitBreaker(failure_threshold=5, recovery_timeout=180),
            "s3_au": CircuitBreaker(failure_threshold=5, recovery_timeout=180)
        }
        
        self.attempted_sources = []
    
    def select_best_source(self, lat: float, lon: float, 
                          prefer_local: bool = True) -> Optional[str]:
        """Select best source with cost awareness"""
        
        # In local-only mode, use basic implementation
        if not self.use_s3:
            return self._find_local_source(lat, lon)
        
        # Check local sources first if preferred
        if prefer_local:
            local_source = self._find_local_source(lat, lon)
            if local_source:
                logger.info(f"Selected local source '{local_source}' for ({lat}, {lon}) - preferred local mode")
                return local_source
        
        # Check S3 sources with cost limits
        if self.cost_manager and not self.cost_manager.can_access_s3():
            logger.warning(f"S3 daily limit reached ({self.cost_manager.daily_gb_limit}GB), falling back to local sources for ({lat}, {lon})")
            return self._find_local_source(lat, lon)
        
        # Try NZ Open Data first (free)
        if 'nz' in self.s3_managers:
            nz_source = self.s3_managers['nz'].find_best_source(lat, lon)
            if nz_source:
                logger.info(f"Selected NZ Open Data source '{nz_source}' for ({lat}, {lon}) - free tier, no cost impact")
                return nz_source
        
        # Try our S3 bucket
        if 'au' in self.s3_managers:
            au_source = self.s3_managers['au'].find_best_source(lat, lon)
            if au_source:
                estimated_cost_mb = 10
                logger.info(f"Selected AU S3 source '{au_source}' for ({lat}, {lon}) - estimated cost: {estimated_cost_mb}MB")
                if self.cost_manager:
                    self.cost_manager.record_access(estimated_cost_mb)
                return au_source
        
        # Fall back to local
        fallback_source = self._find_local_source(lat, lon)
        if fallback_source:
            logger.info(f"No external sources available, using local fallback '{fallback_source}' for ({lat}, {lon})")
        else:
            logger.warning(f"No elevation sources available for ({lat}, {lon}) - all sources exhausted")
        return fallback_source
    
    async def get_elevation_with_resilience(self, lat: float, lon: float) -> Dict[str, Any]:
        """Get elevation with comprehensive error handling"""
        self.attempted_sources = []
        last_error = None
        
        # Try sources in priority order
        source_attempts = [
            ("local", self._try_local_source),
            ("nz_open_data", self._try_nz_source),
            ("gpxz_api", self._try_gpxz_source),
            ("s3_au", self._try_s3_au_source)
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
                elevation = await retry_with_backoff(
                    lambda: source_func(lat, lon),
                    max_retries=2,
                    exceptions=(RetryableError,)
                )
                
                if elevation is not None:
                    # Record success for circuit breaker
                    if source_name in self.circuit_breakers:
                        self.circuit_breakers[source_name].record_success()
                    
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
    
    async def _try_local_source(self, lat: float, lon: float) -> Optional[float]:
        """Try local DEM source"""
        try:
            # Implementation for local source
            source_id = self._find_local_source(lat, lon)
            if source_id:
                # Call existing local elevation logic
                return await self._get_elevation_from_local(lat, lon, source_id)
            return None
        except Exception as e:
            raise RetryableError(f"Local source error: {e}", SourceType.LOCAL)
    
    async def _try_nz_source(self, lat: float, lon: float) -> Optional[float]:
        """Try NZ Open Data source"""
        if not self.use_s3 or 'nz' not in self.s3_managers:
            return None
            
        try:
            source_id = self.s3_managers['nz'].find_best_source(lat, lon)
            if source_id:
                # For now, return a mock elevation - real implementation would access S3
                logger.info(f"Would access NZ source: {source_id}")
                return 45.0  # Mock elevation
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
    
    async def _try_s3_au_source(self, lat: float, lon: float) -> Optional[float]:
        """Try Australian S3 source"""
        if not self.use_s3 or 'au' not in self.s3_managers:
            return None
            
        try:
            # Check cost limits
            if self.cost_manager and not self.cost_manager.can_access_s3():
                raise NonRetryableError("S3 daily cost limit reached", SourceType.S3)
            
            source_id = self.s3_managers['au'].find_best_source(lat, lon)
            if source_id:
                # For now, return a mock elevation - real implementation would access S3
                if self.cost_manager:
                    self.cost_manager.record_access(10)
                logger.info(f"Would access AU source: {source_id}")
                return 125.0  # Mock elevation
            return None
        except Exception as e:
            raise RetryableError(f"AU S3 source error: {e}", SourceType.S3)
    
    async def get_elevation_from_api(self, lat: float, lon: float, source_id: str) -> Optional[float]:
        """Get elevation from API sources"""
        if source_id == "gpxz_api" and self.gpxz_client:
            return await self.gpxz_client.get_elevation_point(lat, lon)
        
        return None
    
    async def _get_elevation_from_local(self, lat: float, lon: float, source_id: str) -> Optional[float]:
        """Get elevation from local source (placeholder)"""
        # This would integrate with existing DEM service logic
        # For now, return a mock elevation for local DTM
        if source_id in ["local_dtm", "local_converted"]:
            return 42.5  # Mock elevation
        return None
    
    def _find_local_source(self, lat: float, lon: float) -> Optional[str]:
        """Find local source for coordinates"""
        # Check configured local sources
        for source_id, source_config in self.config.items():
            if "local" in source_id.lower() or not source_config.get("path", "").startswith("s3://"):
                # Assume local sources cover the query point for now
                return source_id
        return None
    
    async def close(self):
        """Clean up resources"""
        if self.gpxz_client:
            await self.gpxz_client.close()