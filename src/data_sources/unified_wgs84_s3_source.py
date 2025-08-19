"""
Unified WGS84 S3 Source - Gemini Architectural Solution

Implements the complete unified architecture with WGS84 standardized bounds,
native CRS metadata, and country-agnostic collection handling.

This is the integration point that brings together:
1. UnifiedWGS84SpatialIndex (data contract)  
2. UnifiedCollectionHandler (query logic)
3. CRSTransformationService (coordinate transformations)
4. Existing GDAL elevation extraction (unchanged)
"""

import json
import logging
import math
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import asyncio
from datetime import datetime

from ..models.unified_wgs84_models import UnifiedWGS84SpatialIndex, UnifiedDataCollection
from ..handlers.unified_collection_handler import UnifiedCollectionHandler
from ..s3_client_factory import S3ClientFactory
from .base_source import BaseDataSource, ElevationResult

logger = logging.getLogger(__name__)


class UnifiedWGS84S3Source(BaseDataSource):
    """
    Unified S3 source using WGS84 standardized bounds and country-agnostic architecture
    
    This is the production implementation of Gemini's architectural recommendations
    """
    
    def __init__(self, 
                 unified_index_key: str = "indexes/unified_spatial_index_v2_wgs84_standard.json",
                 s3_client_factory: Optional[S3ClientFactory] = None,
                 crs_service=None):
        """
        Initialize unified WGS84 S3 source
        
        Args:
            unified_index_key: S3 key for WGS84 unified index (schema version 2.0)
            s3_client_factory: S3 client factory for AWS access
            crs_service: CRS transformation service for native CRS transformations
        """
        super().__init__("unified_wgs84_s3")
        self.unified_index_key = unified_index_key
        self.s3_client_factory = s3_client_factory
        
        # Core components - unified architecture
        self.unified_index: Optional[UnifiedWGS84SpatialIndex] = None
        self.unified_handler = UnifiedCollectionHandler(crs_service)
        
        # Local fallback
        self.config_dir = Path("config")
        
        logger.info(f"UnifiedWGS84S3Source initialized - schema v2.0 WGS84 standardized")
    
    async def initialize(self) -> bool:
        """Initialize the source by loading WGS84 unified spatial index"""
        try:
            logger.info("Loading WGS84 unified spatial index (schema v2.0)...")
            success = await self._load_unified_index_from_s3()
            if not success:
                logger.warning("S3 loading failed, falling back to filesystem")
                success = self._load_unified_index_from_filesystem()
            
            if success:
                count = len(self.unified_index.data_collections) if self.unified_index else 0
                schema_version = self.unified_index.schema_metadata.schema_version if self.unified_index else "unknown"
                bounds_format = self.unified_index.schema_metadata.bounds_format if self.unified_index else "unknown"
                
                logger.info(f"✅ Unified WGS84 index loaded: {count} collections (schema {schema_version}, bounds {bounds_format})")
                
                # Validate schema version
                if schema_version != "2.0":
                    logger.warning(f"Expected schema version 2.0, got {schema_version}")
                
                if bounds_format != "wgs84_unified":
                    logger.warning(f"Expected bounds format wgs84_unified, got {bounds_format}")
                
                return True
            else:
                logger.error("Failed to load unified WGS84 index from both S3 and filesystem")
                return False
                
        except Exception as e:
            logger.error(f"Failed to initialize UnifiedWGS84S3Source: {e}")
            return False
    
    async def get_elevation(self, lat: float, lon: float) -> ElevationResult:
        """
        Get elevation using unified WGS84 architecture with CRS-aware transformations
        
        This implements the complete Gemini architectural solution:
        1. Universal WGS84 bounds checking for all collections
        2. CRS transformation at query time (not index time)
        3. Country-agnostic collection handling
        4. Transform-Once pattern for efficiency
        """
        start_time = time.time()
        
        try:
            if not self.unified_index:
                return ElevationResult(
                    elevation_m=None,
                    source_info={"error": "Unified index not loaded"},
                    processing_time_ms=time.time() - start_time
                )
            
            # Step 1: Find best collections using universal WGS84 bounds checking
            collections_count = len(self.unified_index.data_collections) if self.unified_index.data_collections else 0
            logger.debug(f"Searching {collections_count} collections for ({lat}, {lon})")
            
            best_collections = self.unified_handler.find_best_collections(
                self.unified_index, lat, lon, max_collections=5
            )
            
            if not best_collections:
                processing_time = (time.time() - start_time) * 1000
                return ElevationResult(
                    elevation_m=None,
                    source_info={
                        "message": "No collections found for coordinate",
                        "collections_searched": len(self.unified_index.data_collections) if self.unified_index.data_collections else 0,
                        "coordinates": {"lat": lat, "lon": lon}
                    },
                    processing_time_ms=processing_time
                )
            
            # Step 2: Try elevation extraction from highest priority collection
            for collection, priority in best_collections:
                try:
                    logger.info(f"Attempting elevation extraction from collection {collection.id} (priority: {priority:.2f})")
                    
                    # Step 3: Find files in the collection
                    candidate_files = self.unified_handler.find_files_for_coordinate(collection, lat, lon)
                    if not candidate_files:
                        logger.debug(f"No files found in collection {collection.id}")
                        continue
                    
                    # Step 4: Transform coordinates to native CRS and extract elevation
                    elevation = await self._extract_elevation_from_collection(collection, lat, lon, candidate_files[0])
                    
                    if elevation is not None:
                        processing_time = (time.time() - start_time) * 1000
                        
                        return ElevationResult(
                            elevation_m=elevation,
                            source_info={
                                "message": "Success via unified WGS84 architecture",
                                "collection_id": collection.id,
                                "collection_type": collection.collection_type,
                                "country": collection.country,
                                "native_crs": collection.native_crs,
                                "file_used": candidate_files[0]["filename"],
                                "priority": priority,
                                "resolution_m": collection.resolution_m,
                                "data_type": collection.data_type
                            },
                            processing_time_ms=processing_time
                        )
                    else:
                        logger.debug(f"Elevation extraction failed for collection {collection.id}")
                        continue
                        
                except Exception as e:
                    logger.error(f"Error processing collection {collection.id}: {e}")
                    continue
            
            # Step 5: No elevation found in any collection
            processing_time = (time.time() - start_time) * 1000
            return ElevationResult(
                elevation_m=None,
                source_info={
                    "message": "No elevation found in available files",
                    "collections_found": len(best_collections),
                    "collections_tried": [c.id for c, _ in best_collections]
                },
                processing_time_ms=processing_time
            )
            
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            logger.error(f"Error in get_elevation for ({lat}, {lon}): {e}")
            return ElevationResult(
                elevation_m=None,
                source_info={"error": str(e)},
                processing_time_ms=processing_time
            )
    
    async def _extract_elevation_from_collection(self, collection: UnifiedDataCollection, 
                                               lat: float, lon: float, file_info: dict) -> Optional[float]:
        """
        Extract elevation from a specific collection using CRS-aware coordinate transformation
        
        This integrates with the existing GDAL/rasterio elevation extraction logic
        """
        try:
            # Step 1: Transform coordinates to native CRS if needed
            native_crs = collection.native_crs
            
            if native_crs == "EPSG:4326":
                # Already in WGS84, no transformation needed
                target_lat, target_lon = lat, lon
            else:
                # Transform WGS84 to native CRS using existing CRS service
                if not self.unified_handler.crs_service:
                    logger.error(f"CRS service required for transformation to {native_crs}")
                    return None
                
                try:
                    # Use existing Transform-Once pattern
                    from ..models.coordinates import QueryPoint, PointWGS84
                    query_point = QueryPoint(wgs84=PointWGS84(lat=lat, lon=lon))
                    projected_point = query_point.get_or_create_projection(native_crs, self.unified_handler.crs_service)
                    
                    # Note: For GDAL, we need (x, y) = (lon, lat) in the native CRS
                    target_lon, target_lat = projected_point.x, projected_point.y
                    
                    logger.debug(f"🔍 Transform: ({lat}, {lon}) WGS84 → ({target_lon}, {target_lat}) {native_crs}")
                except Exception as e:
                    logger.error(f"Failed to transform coordinates to {native_crs}: {e}")
                    return None
            
            # Step 2: Extract elevation using existing GDAL logic
            file_path = file_info["file"]
            
            # Convert S3 path to GDAL VSI format if needed
            if file_path.startswith("s3://"):
                vsi_path = file_path.replace("s3://", "/vsis3/")
            else:
                vsi_path = file_path
            
            # Use existing elevation extraction method
            elevation = self._extract_elevation_sync(vsi_path, target_lat, target_lon, native_crs)
            
            if elevation is not None:
                logger.info(f"✅ Elevation extracted: {elevation}m from {file_info['filename']}")
            
            return elevation
            
        except Exception as e:
            logger.error(f"Failed to extract elevation from collection {collection.id}: {e}")
            return None
    
    def _extract_elevation_sync(self, file_path: str, lat: float, lon: float, target_crs: str) -> Optional[float]:
        """
        Synchronous elevation extraction using GDAL/rasterio
        
        This reuses the existing elevation extraction logic from the original UnifiedS3Source
        """
        try:
            import os
            import rasterio
            from rasterio.errors import RasterioIOError
            
            # DEBUGGING PROTOCOL PHASE 3 FIX: Set environment variables directly
            # Railway environment may not properly pass credentials through Env() context manager
            original_env = {}
            # Store original values to restore later
            for key in ['AWS_REGION', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY']:
                original_env[key] = os.environ.get(key)
            
            try:
                # Set environment variables directly (more reliable than Env context manager)
                os.environ['AWS_REGION'] = 'ap-southeast-2'
                if 'AWS_ACCESS_KEY_ID' not in os.environ:
                    os.environ['AWS_ACCESS_KEY_ID'] = 'AKIA5SIDYET7N3U4JQ5H'
                if 'AWS_SECRET_ACCESS_KEY' not in os.environ:
                    os.environ['AWS_SECRET_ACCESS_KEY'] = '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'
                
                # Open rasterio dataset with S3 credentials
                with rasterio.open(file_path) as dataset:
                    # Sample the dataset at the given coordinates
                    # Note: rasterio.sample expects (x, y) = (lon, lat)
                    samples = list(dataset.sample([(lon, lat)]))
                    
                    if samples and len(samples[0]) > 0:
                        elevation = float(samples[0][0])  # First band, first sample
                        
                        # Check for nodata values
                        if dataset.nodata is not None and elevation == dataset.nodata:
                            return None
                        
                        # Sanity check: elevation should be reasonable
                        if -1000 <= elevation <= 10000:  # -1000m to 10000m is reasonable range
                            return elevation
                        else:
                            logger.warning(f"Elevation {elevation}m outside reasonable range")
                            return None
                    else:
                        return None
                        
            finally:
                # Restore original environment variables
                for key, value in original_env.items():
                    if value is not None:
                        os.environ[key] = value
                    elif key in os.environ:
                        del os.environ[key]
                        
        except RasterioIOError as e:
            if "NoCredentialsError" in str(e) or "CredentialsNotFound" in str(e):
                logger.error(f"AWS credentials error for {file_path}: {e}")
            else:
                logger.error(f"Rasterio IO error for {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to extract elevation from {file_path}: {e}")
            return None
    
    async def _load_unified_index_from_s3(self) -> bool:
        """Load WGS84 unified index from S3"""
        if not self.s3_client_factory:
            logger.warning("No S3 client factory available")
            return False
        
        try:
            # Get S3 client for main bucket using async context manager
            async with self.s3_client_factory.get_client("private", "ap-southeast-2") as s3_client:
                # Download unified index
                response = await s3_client.get_object(
                    Bucket="road-engineering-elevation-data",
                    Key=self.unified_index_key
                )
                
                # Read the content  
                content_bytes = await response['Body'].read()
                index_data = json.loads(content_bytes.decode('utf-8'))
                
                # Parse with WGS84 Pydantic models
                self.unified_index = UnifiedWGS84SpatialIndex(**index_data)
                
                # Safe collection count (data_collections might be None before conversion)
                collections_count = len(self.unified_index.data_collections) if self.unified_index.data_collections else 0
                logger.info(f"✅ Loaded WGS84 unified index from S3: {collections_count} collections")
                return True
            
        except Exception as e:
            logger.warning(f"Failed to load WGS84 unified index from S3: {e}")
            return False
    
    def _load_unified_index_from_filesystem(self) -> bool:
        """Load WGS84 unified index from local filesystem"""
        index_file = self.config_dir / "unified_spatial_index_v2_wgs84_standard.json"
        
        if not index_file.exists():
            logger.warning(f"WGS84 unified index file not found: {index_file}")
            return False
        
        try:
            with open(index_file, 'r') as f:
                index_data = json.load(f)
            
            self.unified_index = UnifiedWGS84SpatialIndex(**index_data)
            
            collections_count = len(self.unified_index.data_collections) if self.unified_index.data_collections else 0
            logger.info(f"✅ Loaded WGS84 unified index from filesystem: {collections_count} collections")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load WGS84 unified index from filesystem: {e}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check with WGS84 unified index information"""
        health = {
            "status": "healthy" if self.unified_index else "unhealthy",
            "unified_index_loaded": self.unified_index is not None,
            "use_unified_index": True,
            "schema_version": "2.0",
            "bounds_format": "wgs84_unified",
            "architecture": "country_agnostic_unified"
        }
        
        if self.unified_index:
            health.update({
                "collection_count": len(self.unified_index.data_collections) if self.unified_index.data_collections else 0,
                "total_files": self.unified_index.schema_metadata.total_files if self.unified_index.schema_metadata else 0,
                "countries": self.unified_index.schema_metadata.countries if self.unified_index.schema_metadata else [],
                "collection_types": self.unified_index.schema_metadata.collection_types if self.unified_index.schema_metadata else []
            })
        
        return health
    
    async def coverage_info(self) -> Dict[str, Any]:
        """Get coverage information for WGS84 unified index"""
        if not self.unified_index:
            return {"error": "WGS84 unified index not loaded"}
        
        coverage = {
            "version": self.unified_index.version,
            "schema_version": self.unified_index.schema_metadata.schema_version if self.unified_index.schema_metadata else "unknown",
            "bounds_format": self.unified_index.schema_metadata.bounds_format if self.unified_index.schema_metadata else "unknown",
            "generated_at": self.unified_index.schema_metadata.generated_at if self.unified_index.schema_metadata else "unknown",
            "total_collections": len(self.unified_index.data_collections) if self.unified_index.data_collections else 0,
            "total_files": self.unified_index.schema_metadata.total_files if self.unified_index.schema_metadata else 0,
            "countries": {}
        }
        
        # Group by country
        if self.unified_index.schema_metadata:
            for country in self.unified_index.schema_metadata.countries:
                country_collections = self.unified_index.get_collections_by_country(country)
                coverage["countries"][country] = {
                    "collection_count": len(country_collections),
                    "file_count": sum(c.file_count for c in country_collections),
                    "collection_types": list(set(c.collection_type for c in country_collections))
                }
        
        return coverage