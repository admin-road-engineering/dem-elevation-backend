"""
SourceProvider: Production-Ready Async Data Loading

Implements Gemini's approved SourceProvider pattern to resolve critical startup issues:
- Moves all I/O operations out of Settings class
- Uses aioboto3 for true async S3 operations  
- Provides coordinated loading with asyncio.Event
- Enables production-ready non-blocking startup (<500ms target)
"""

import asyncio
import logging
from typing import Dict, Any, Optional
import json
from dataclasses import dataclass

import aioboto3
import aiofiles

logger = logging.getLogger(__name__)

@dataclass
class SourceProviderConfig:
    """Configuration for SourceProvider - static config only, no I/O"""
    s3_bucket_name: str
    campaign_index_key: str
    nz_index_key: str
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = "ap-southeast-2"
    enable_nz_sources: bool = False


class SourceProvider:
    """
    Production-ready async data provider implementing Gemini's approved pattern.
    
    Responsibilities:
    - Load campaign and NZ indexes from S3 asynchronously
    - Coordinate startup with asyncio.Event pattern
    - Provide data to services via dependency injection
    - Handle graceful degradation on load failures
    """
    
    def __init__(self, config: SourceProviderConfig):
        """
        Initialize SourceProvider with static configuration only.
        No I/O operations in constructor - all async loading in load_all_sources().
        """
        self.config = config
        
        # Data containers - populated by load_all_sources()
        self.campaign_index: Optional[Dict[str, Any]] = None
        self.nz_index: Optional[Dict[str, Any]] = None
        self.dem_sources: Optional[Dict[str, Any]] = None
        
        # Coordination for startup
        self._loading_complete = asyncio.Event()
        self._loading_started = False
        self._load_success = False
        self._load_errors = []
        
        logger.info(f"SourceProvider initialized with bucket: {config.s3_bucket_name}")
    
    async def load_all_sources(self) -> bool:
        """
        Load all data sources concurrently using aioboto3.
        
        This method BLOCKS until all critical data is loaded, ensuring
        FastAPI startup completes with all required data available.
        
        Returns:
            bool: True if critical sources loaded successfully
        """
        if self._loading_started:
            logger.warning("load_all_sources() called multiple times - waiting for completion")
            await self._loading_complete.wait()
            return self._load_success
        
        self._loading_started = True
        logger.info("Starting async data loading with aioboto3...")
        
        try:
            # Create aioboto3 session for true async operations
            session = aioboto3.Session(
                aws_access_key_id=self.config.aws_access_key_id,
                aws_secret_access_key=self.config.aws_secret_access_key,
                region_name=self.config.aws_region
            )
            
            # Load all indexes concurrently
            tasks = [
                self._load_campaign_index(session),
            ]
            
            # Add NZ loading if enabled
            if self.config.enable_nz_sources:
                tasks.append(self._load_nz_index(session))
            
            # Execute all loading tasks concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            campaign_success = False
            nz_success = True  # Default true if not needed
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self._load_errors.append(f"Task {i} failed: {result}")
                    logger.error(f"Loading task {i} failed: {result}")
                elif i == 0:  # Campaign index
                    campaign_success = result
                elif i == 1:  # NZ index (optional)
                    nz_success = result
            
            # Build unified DEM_SOURCES from loaded data
            self._build_dem_sources()
            
            # Determine overall success
            self._load_success = campaign_success and nz_success
            
            if self._load_success:
                source_count = len(self.dem_sources) if self.dem_sources else 0
                logger.info(f"SourceProvider loading completed successfully: {source_count} sources available")
            else:
                logger.error(f"SourceProvider loading had failures: {self._load_errors}")
            
        except Exception as e:
            logger.error(f"Critical error in load_all_sources: {e}", exc_info=True)
            self._load_errors.append(f"Critical error: {e}")
            self._load_success = False
        
        finally:
            # Signal completion regardless of success/failure
            self._loading_complete.set()
        
        return self._load_success
    
    async def _load_campaign_index(self, session: aioboto3.Session) -> bool:
        """Load campaign spatial index from S3 using aioboto3"""
        try:
            logger.info(f"Loading campaign index: s3://{self.config.s3_bucket_name}/{self.config.campaign_index_key}")
            
            async with session.client('s3') as s3_client:
                # Download index file
                response = await s3_client.get_object(
                    Bucket=self.config.s3_bucket_name,
                    Key=self.config.campaign_index_key
                )
                
                # Read and parse JSON
                content = await response['Body'].read()
                self.campaign_index = json.loads(content.decode('utf-8'))
                
                campaign_count = len(self.campaign_index.get('campaigns', {}))
                logger.info(f"Campaign index loaded: {campaign_count} campaigns")
                return True
        
        except Exception as e:
            logger.error(f"Failed to load campaign index: {e}")
            self.campaign_index = {}
            return False
    
    async def _load_nz_index(self, session: aioboto3.Session) -> bool:
        """Load NZ spatial index from S3 using aioboto3"""
        try:
            logger.info(f"Loading NZ index: s3://{self.config.s3_bucket_name}/{self.config.nz_index_key}")
            
            async with session.client('s3') as s3_client:
                # Download index file
                response = await s3_client.get_object(
                    Bucket=self.config.s3_bucket_name,
                    Key=self.config.nz_index_key
                )
                
                # Read and parse JSON
                content = await response['Body'].read()
                self.nz_index = json.loads(content.decode('utf-8'))
                
                region_count = len(self.nz_index.get('regions', {}))
                logger.info(f"NZ index loaded: {region_count} regions")
                return True
        
        except Exception as e:
            logger.warning(f"Failed to load NZ index (non-critical): {e}")
            self.nz_index = {}
            return True  # Non-critical for startup
    
    def _build_dem_sources(self):
        """Build unified DEM_SOURCES dict from loaded indexes"""
        self.dem_sources = {}
        
        # Add campaign sources
        if self.campaign_index:
            campaigns = self.campaign_index.get('campaigns', {})
            for campaign_id, campaign_data in campaigns.items():
                self.dem_sources[campaign_id] = {
                    'source_type': 's3',
                    **campaign_data
                }
        
        # Add NZ sources if enabled and loaded
        if self.config.enable_nz_sources and self.nz_index:
            regions = self.nz_index.get('regions', {})
            for region_id, region_data in regions.items():
                nz_source_id = f"nz_{region_id}"
                self.dem_sources[nz_source_id] = {
                    'source_type': 's3',
                    'bucket_name': 'nz-elevation',
                    **region_data
                }
        
        # Add API sources (static configuration)
        self.dem_sources.update({
            'gpxz_api': {
                'source_type': 'api',
                'name': 'GPXZ.io Global Elevation API',
                'resolution_m': 30.0,
                'accuracy': '±1m',
                'coverage': 'global'
            },
            'google_api': {
                'source_type': 'api', 
                'name': 'Google Elevation API',
                'resolution_m': 30.0,
                'accuracy': '±1m',
                'coverage': 'global'
            }
        })
        
        logger.info(f"Built unified DEM_SOURCES: {len(self.dem_sources)} total sources")
    
    async def wait_for_loading(self) -> bool:
        """Wait for loading to complete - used by dependency injection"""
        await self._loading_complete.wait()
        return self._load_success
    
    def get_dem_sources(self) -> Dict[str, Any]:
        """Get DEM sources dict - replaces Settings.DEM_SOURCES property"""
        if not self._loading_complete.is_set():
            raise RuntimeError("SourceProvider not loaded - call load_all_sources() first")
        
        return self.dem_sources or {}
    
    def get_campaign_index(self) -> Dict[str, Any]:
        """Get campaign spatial index data"""
        return self.campaign_index or {}
    
    def get_nz_index(self) -> Dict[str, Any]:
        """Get NZ spatial index data"""
        return self.nz_index or {}
    
    def is_loading_complete(self) -> bool:
        """Check if loading is complete"""
        return self._loading_complete.is_set()
    
    def is_load_successful(self) -> bool:
        """Check if loading was successful"""
        return self._load_success
    
    def get_load_errors(self) -> list:
        """Get any loading errors"""
        return self._load_errors.copy()
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for monitoring"""
        if not self.dem_sources:
            return {"status": "not_loaded"}
        
        s3_count = sum(1 for source in self.dem_sources.values() if source.get('source_type') == 's3')
        api_count = sum(1 for source in self.dem_sources.values() if source.get('source_type') == 'api')
        
        return {
            "status": "loaded" if self._load_success else "failed",
            "total_sources": len(self.dem_sources),
            "s3_sources": s3_count,
            "api_sources": api_count,
            "campaign_index_loaded": bool(self.campaign_index),
            "nz_index_loaded": bool(self.nz_index) if self.config.enable_nz_sources else "disabled",
            "load_errors": len(self._load_errors)
        }