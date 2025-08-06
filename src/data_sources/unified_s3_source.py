"""
Unified S3 Source with Collection Handler Strategy
Implements Gemini's recommended country-agnostic architecture
"""
import json
import logging
import math
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import asyncio
from datetime import datetime

from ..models.unified_spatial_models import UnifiedSpatialIndex, DataCollection, FileEntry
from ..handlers import CollectionHandlerRegistry
from ..s3_client_factory import S3ClientFactory
from .base_source import BaseDataSource, ElevationResult

logger = logging.getLogger(__name__)

class UnifiedS3Source(BaseDataSource):
    """
    Unified S3 source using discriminated unions and collection handlers
    Country-agnostic elevation data source
    """
    
    def __init__(self, 
                 use_unified_index: bool = False,
                 unified_index_key: str = "indexes/unified_spatial_index_v2.json",
                 s3_client_factory: Optional[S3ClientFactory] = None,
                 crs_service=None,
                 aws_sessions: Optional[Dict[str, Any]] = None):
        """
        Initialize unified S3 source
        
        Args:
            use_unified_index: If True, use unified v2.0 index
            unified_index_key: S3 key for unified index
            s3_client_factory: S3 client factory for AWS access
            crs_service: CRS transformation service for CRS-aware spatial queries
            aws_sessions: Pre-configured AWS sessions for rasterio (singleton pattern)
        """
        super().__init__("unified_s3")
        self.use_unified_index = use_unified_index
        self.unified_index_key = unified_index_key
        self.s3_client_factory = s3_client_factory
        
        # Core components
        self.unified_index: Optional[UnifiedSpatialIndex] = None
        self.handler_registry = CollectionHandlerRegistry(crs_service)
        
        # AWS Sessions (singleton pattern per Gemini recommendation)
        self.aws_sessions = aws_sessions or self._create_default_sessions()
        
        # Local fallback
        self.config_dir = Path("config")
        
        logger.info(f"UnifiedS3Source initialized (unified_index={use_unified_index})")
    
    def _create_default_sessions(self) -> Dict[str, Any]:
        """Create default AWS sessions following Gemini's singleton pattern recommendation"""
        import boto3
        from rasterio.session import AWSSession
        from botocore.client import Config
        from botocore import UNSIGNED
        import os
        
        sessions = {}
        
        try:
            # AU Private Bucket Session (signed)
            access_key = os.environ.get('AWS_ACCESS_KEY_ID', 'AKIA5SIDYET7N3U4JQ5H')
            secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY', '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')
            
            au_boto_session = boto3.Session(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name='ap-southeast-2'
            )
            sessions['au_private'] = AWSSession(au_boto_session)
            
            # NZ Public Bucket Session (unsigned) 
            nz_boto_session = boto3.Session(region_name='ap-southeast-2')
            nz_s3_client = nz_boto_session.client('s3', config=Config(signature_version=UNSIGNED))
            sessions['nz_public'] = AWSSession(session=nz_boto_session, client=nz_s3_client)
            
            logger.info("✅ Created singleton AWS sessions for AU private and NZ public buckets")
            
        except Exception as e:
            logger.error(f"Failed to create AWS sessions: {e}")
            sessions = {}
            
        return sessions
    
    async def initialize(self) -> bool:
        """Initialize the source by loading spatial indexes"""
        try:
            if self.use_unified_index:
                logger.info("🔄 Loading unified spatial index v2.0...")
                success = await self._load_unified_index_from_s3()
                if not success:
                    logger.warning("S3 loading failed, falling back to filesystem")
                    success = self._load_unified_index_from_filesystem()
            else:
                logger.info("📊 Using legacy index mode (unified disabled)")
                success = False  # Force fallback to legacy system
            
            if success:
                count = len(self.unified_index.data_collections) if self.unified_index else 0
                logger.info(f"✅ Unified index loaded: {count} collections")
            else:
                logger.warning("❌ Failed to load unified index")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to initialize UnifiedS3Source: {e}")
            return False
    
    async def get_elevation(self, lat: float, lon: float) -> ElevationResult:
        """Get elevation using unified collection handlers with GDAL thread pool execution"""
        if not self.unified_index:
            return ElevationResult(
                elevation=None,
                error="Unified index not loaded",
                source="unified_s3",
                metadata={}
            )
        
        start_time = time.time()
        collections_tried = []
        
        try:
            # Find best collections for coordinate
            logger.info(f"🔍🔍🔍 UNIFIED S3: Getting elevation for ({lat}, {lon})")
            logger.info(f"  Collections in index: {len(self.unified_index.data_collections)}")
            
            best_collections = self.handler_registry.find_best_collections(
                self.unified_index.data_collections, lat, lon, max_collections=3
            )
            
            logger.info(f"  Best collections returned: {len(best_collections)}")
            
            if not best_collections:
                return ElevationResult(
                    elevation=None,
                    error="No collections found for coordinate",
                    source="unified_s3",
                    metadata={"coordinate": (lat, lon)}
                )
            
            # Try each collection in priority order
            loop = asyncio.get_running_loop()
            
            for collection, priority in best_collections:
                collections_tried.append(collection.id)
                
                try:
                    # Find files within collection
                    candidate_files = self.handler_registry.find_files_for_coordinate(
                        collection, lat, lon
                    )
                    
                    if not candidate_files:
                        continue
                    
                    # Try each file with non-blocking GDAL
                    for file_entry in candidate_files[:3]:  # Limit attempts
                        # FileEntry.file contains the full S3 path like "s3://bucket/key"
                        if file_entry.file.startswith('s3://'):
                            file_path = f"/vsis3/{file_entry.file[5:]}"  # Remove 's3://' prefix
                        else:
                            file_path = f"/vsis3/{file_entry.file}"  # Already without prefix
                        
                        target_crs = getattr(file_entry, 'coordinate_system', None) or "EPSG:4326"
                        
                        # ✅ CRITICAL: Run GDAL in thread pool to prevent event loop blocking
                        logger.debug(f"Attempting elevation extraction: {file_path} for ({lat}, {lon}) with CRS {target_crs}")
                        elevation = await loop.run_in_executor(
                            None,
                            self._extract_elevation_sync,
                            file_path, lat, lon, target_crs
                        )
                        
                        if elevation is not None:
                            processing_time = (time.time() - start_time) * 1000
                            
                            # Use specific file name as source, not generic "unified_s3"
                            source_name = file_entry.filename or file_entry.file.split('/')[-1]
                            
                            return ElevationResult(
                                elevation=elevation,
                                error=None,
                                source=source_name,  # "Brisbane2009LGA" not "unified_s3" 
                                metadata={
                                    "collection_id": collection.id,
                                    "collection_type": collection.collection_type,
                                    "file_path": file_entry.file,
                                    "source_crs": target_crs,
                                    "resolution": getattr(file_entry, 'resolution', None) or "1m",
                                    "grid_resolution_m": 1.0,  # From file metadata
                                    "data_type": getattr(file_entry, 'data_type', None) or "LiDAR",
                                    "accuracy": getattr(file_entry, 'accuracy', None) or "±0.1m",
                                    "processing_time_ms": processing_time,
                                    "collections_tried": len(collections_tried),
                                    "message": f"Unified S3 campaign: {source_name} (resolution: {getattr(file_entry, 'resolution', None) or '1m'})"
                                }
                            )
                
                except Exception as e:
                    logger.warning(f"Error processing collection {collection.id}: {e}")
                    continue
            
            # No elevation found in any collection
            processing_time = (time.time() - start_time) * 1000
            return ElevationResult(
                elevation=None,
                error="No elevation found in available files",
                source="unified_s3",
                metadata={
                    "collections_tried": len(collections_tried),
                    "collection_ids": collections_tried,
                    "processing_time_ms": processing_time
                }
            )
            
        except Exception as e:
            logger.error(f"Unified elevation extraction failed: {e}")
            return ElevationResult(
                elevation=None,
                error=f"Extraction error: {e}",
                source="unified_s3",
                metadata={"collections_tried": len(collections_tried)}
            )
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of unified S3 source"""
        health = {
            "status": "healthy",
            "unified_index_loaded": self.unified_index is not None,
            "use_unified_index": self.use_unified_index,
            "collection_count": 0,
            "total_files": 0,
            "countries": [],
            "collection_types": []
        }
        
        if self.unified_index:
            health.update({
                "collection_count": len(self.unified_index.data_collections),
                "total_files": self.unified_index.schema_metadata.total_files,
                "countries": self.unified_index.schema_metadata.countries,
                "collection_types": self.unified_index.schema_metadata.collection_types
            })
        
        return health
    
    async def coverage_info(self) -> Dict[str, Any]:
        """Get coverage information"""
        if not self.unified_index:
            return {"error": "Unified index not loaded"}
        
        coverage = {
            "version": self.unified_index.version,
            "generated_at": self.unified_index.schema_metadata.generated_at.isoformat(),
            "total_collections": len(self.unified_index.data_collections),
            "total_files": self.unified_index.schema_metadata.total_files,
            "countries": {}
        }
        
        # Group by country
        for country in self.unified_index.schema_metadata.countries:
            country_collections = self.unified_index.get_collections_by_country(country)
            coverage["countries"][country] = {
                "collection_count": len(country_collections),
                "file_count": sum(c.file_count for c in country_collections),
                "collection_types": list(set(c.collection_type for c in country_collections))
            }
        
        return coverage
    
    async def _load_unified_index_from_s3(self) -> bool:
        """Load unified index from S3"""
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
                
                # Parse with Pydantic
                self.unified_index = UnifiedSpatialIndex(**index_data)
                
                logger.info(f"✅ Loaded unified index from S3: {len(self.unified_index.data_collections)} collections")
                return True
            
        except Exception as e:
            logger.warning(f"Failed to load unified index from S3: {e}")
            return False
    
    def _load_unified_index_from_filesystem(self) -> bool:
        """Load unified index from local filesystem"""
        index_file = self.config_dir / "unified_spatial_index_v2.json"
        
        if not index_file.exists():
            logger.warning(f"Unified index file not found: {index_file}")
            return False
        
        try:
            with open(index_file, 'r') as f:
                index_data = json.load(f)
            
            self.unified_index = UnifiedSpatialIndex(**index_data)
            
            logger.info(f"✅ Loaded unified index from filesystem: {len(self.unified_index.data_collections)} collections")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load unified index from filesystem: {e}")
            return False
    
    def _extract_elevation_sync(self, file_path: str, lat: float, lon: float, target_crs: str) -> Optional[float]:
        """
        Synchronous function for all GDAL operations - runs in thread pool
        
        Args:
            file_path: S3 path like /vsis3/bucket/key
            lat, lon: WGS84 coordinates  
            target_crs: Target CRS from file metadata (e.g., "EPSG:7856")
        
        Returns:
            Elevation value or None if extraction fails
        """
        dataset = None
        try:
            # Import GDAL here to avoid import issues in main thread
            try:
                from osgeo import gdal, osr
            except ImportError:
                # Fallback import paths for different environments
                import gdal
                import osr
            
            # Configure GDAL for S3 access
            gdal.SetConfigOption('GDAL_HTTP_MERGE_CONSECUTIVE_RANGES', 'YES')
            gdal.SetConfigOption('VSI_CACHE', 'YES')  
            gdal.SetConfigOption('VSI_CACHE_SIZE', '67108864')  # 64MB cache
            gdal.SetConfigOption('GDAL_DISABLE_READDIR_ON_OPEN', 'YES')
            # REMOVED: AWS_S3_REQUEST_PAYER - causes 403 errors on public/standard buckets
            
            # Configure authentication using bucket-aware environment management
            import os
            from ..utils.bucket_detector import BucketDetector, BucketType
            
            # Detect bucket type for GDAL configuration
            bucket_type = BucketDetector.detect_bucket_type(file_path)
            
            # Set GDAL options based on bucket type directly
            gdal.SetConfigOption('AWS_REGION', os.environ.get('AWS_REGION', 'ap-southeast-2'))
            
            if bucket_type == BucketType.PUBLIC_UNSIGNED:
                # Public bucket - use unsigned requests
                gdal.SetConfigOption('AWS_NO_SIGN_REQUEST', 'YES')
                # Clear AWS credentials to ensure unsigned requests (use empty string, not None)
                gdal.SetConfigOption('AWS_ACCESS_KEY_ID', '')
                gdal.SetConfigOption('AWS_SECRET_ACCESS_KEY', '')
                logger.debug(f"GDAL: Using unsigned requests for public bucket ({bucket_type.value})")
            else:
                # Private bucket - use signed requests
                gdal.SetConfigOption('AWS_NO_SIGN_REQUEST', 'NO')
                # Use fallback credentials if env vars not set
                access_key = os.environ.get('AWS_ACCESS_KEY_ID', 'AKIA5SIDYET7N3U4JQ5H')
                secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY', '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')
                if access_key:
                    gdal.SetConfigOption('AWS_ACCESS_KEY_ID', access_key)
                if secret_key:
                    gdal.SetConfigOption('AWS_SECRET_ACCESS_KEY', secret_key)
                logger.debug(f"GDAL: Using signed requests for private bucket ({bucket_type.value})")
            
            # Open dataset with enhanced logging
            logger.info(f"📡 GDAL: Opening S3 file: {file_path}")
            dataset = gdal.Open(file_path)
            if not dataset:
                logger.error(f"❌ GDAL FAILURE: Could not open dataset: {file_path}")
                logger.error(f"📊 GDAL Error Details: {gdal.GetLastErrorMsg()}")
                return None
            
            logger.info(f"✅ GDAL SUCCESS: Opened {file_path}. Size: {dataset.RasterXSize}x{dataset.RasterYSize}, Bands: {dataset.RasterCount}")
            
            # Transform coordinates from WGS84 to file's native CRS
            source_srs = osr.SpatialReference()
            source_srs.ImportFromEPSG(4326)  # WGS84
            # ✅ CRITICAL FIX: Enforce traditional GIS axis order (Lon/Lat)
            source_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
            
            target_srs = osr.SpatialReference()
            actual_epsg = None
            
            if target_crs and target_crs != "EPSG:4326":
                # Handle common Australian coordinate system names with dynamic UTM zone detection
                if target_crs == "GDA94":
                    # Extract UTM zone from file path (e.g., z55, z56)
                    import re
                    zone_match = re.search(r'/z(\d{2})/', file_path)
                    if zone_match:
                        utm_zone = int(zone_match.group(1))
                        actual_epsg = 28300 + utm_zone  # GDA94 MGA Zone (28354=Zone54, 28355=Zone55, etc.)
                        target_srs.ImportFromEPSG(actual_epsg)
                        logger.debug(f"Using UTM Zone {utm_zone} → EPSG:{actual_epsg}")
                    else:
                        # Fallback to Zone 56 if no zone found
                        actual_epsg = 28356
                        target_srs.ImportFromEPSG(actual_epsg)
                        logger.debug(f"GDA94 fallback to EPSG:{actual_epsg} (no zone detected)")
                elif target_crs == "GDA2020":
                    # Extract UTM zone for GDA2020
                    import re
                    zone_match = re.search(r'/z(\d{2})/', file_path)
                    if zone_match:
                        utm_zone = int(zone_match.group(1))
                        actual_epsg = 7800 + utm_zone  # GDA2020 MGA Zone (7854=Zone54, 7855=Zone55, etc.)
                        target_srs.ImportFromEPSG(actual_epsg)
                        logger.debug(f"Using UTM Zone {utm_zone} → EPSG:{actual_epsg}")
                    else:
                        # Fallback to Zone 56
                        actual_epsg = 7856
                        target_srs.ImportFromEPSG(actual_epsg)
                        logger.debug(f"GDA2020 fallback to EPSG:{actual_epsg} (no zone detected)")
                else:
                    try:
                        target_srs.ImportFromUserInput(target_crs)
                        actual_epsg = target_crs
                    except AttributeError:
                        # Fallback for older OSR versions
                        target_srs.SetFromUserInput(target_crs)
                        actual_epsg = target_crs
            else:
                target_srs.ImportFromEPSG(4326)  # Default to WGS84
                actual_epsg = 4326
            
            # ✅ CRITICAL FIX: Enforce traditional GIS axis order for target CRS
            target_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
            
            transform = osr.CoordinateTransformation(source_srs, target_srs)
            x, y, z = transform.TransformPoint(lon, lat)
            
            # ✅ DEFENSIVE CHECK: Verify transformation succeeded
            import math
            if math.isinf(x) or math.isinf(y):
                logger.error(f"Coordinate transformation failed: ({lat}, {lon}) → (inf, inf) for EPSG:{actual_epsg}")
                return None
            
            # Log the actual transformation result
            logger.info(f"🔍 Transform: ({lat}, {lon}) WGS84 → ({x:.2f}, {y:.2f}) EPSG:{actual_epsg}")
            
            # Convert to pixel coordinates
            gt = dataset.GetGeoTransform()
            inv_gt = gdal.InvGeoTransform(gt)
            px = int(inv_gt[0] + x * inv_gt[1] + y * inv_gt[2])
            py = int(inv_gt[3] + x * inv_gt[4] + y * inv_gt[5])
            
            # Check if pixel coordinates are within bounds
            if not (0 <= px < dataset.RasterXSize and 0 <= py < dataset.RasterYSize):
                logger.debug(f"Coordinate ({lat}, {lon}) → pixel ({px}, {py}) outside raster ({dataset.RasterXSize}x{dataset.RasterYSize})")
                return None
            
            # Read elevation value
            band = dataset.GetRasterBand(1)
            elevation_array = band.ReadAsArray(px, py, 1, 1)
            
            if elevation_array is not None and elevation_array.size > 0:
                elevation = float(elevation_array[0, 0])
                # Check for NODATA values
                nodata = band.GetNoDataValue()
                if nodata is not None and elevation == nodata:
                    logger.debug(f"NODATA value encountered at coordinate")
                    return None
                logger.info(f"✅ SUCCESS: Extracted elevation {elevation}m from {file_path}")
                return elevation
                
            return None
            
        except ImportError as e:
            logger.warning(f"GDAL not available ({e}), falling back to rasterio")
            return self._extract_elevation_rasterio_fallback(file_path, lat, lon)
        except Exception as e:
            logger.error(f"❌ CRITICAL GDAL EXTRACTION FAILURE for {file_path}: {e}", exc_info=True)
            return None
        finally:
            if dataset:
                dataset = None  # Close dataset
    
    def _extract_elevation_rasterio_fallback(self, file_path: str, lat: float, lon: float) -> Optional[float]:
        """Fallback elevation extraction using rasterio when GDAL is not available"""
        try:
            import rasterio
            from rasterio.warp import transform as warp_transform
            import os
            
            logger.info(f"🔍 SIMPLE RASTERIO: Attempting {file_path} with basic environment")
            
            # SIMPLIFICATION: Use basic environment variables approach that worked before
            # Set up environment for S3 access - let rasterio handle the rest
            env_backup = {}
            try:
                # Backup current environment
                aws_vars = ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_DEFAULT_REGION', 'AWS_NO_SIGN_REQUEST']
                for var in aws_vars:
                    env_backup[var] = os.environ.get(var)
                
                # Determine if this is NZ (public) or AU (private) bucket
                if 'nz-elevation' in file_path:
                    # NZ public bucket
                    os.environ['AWS_NO_SIGN_REQUEST'] = 'YES'
                    os.environ['AWS_DEFAULT_REGION'] = 'ap-southeast-2'
                    # Remove credentials for public bucket
                    for key in ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY']:
                        if key in os.environ:
                            del os.environ[key]
                    logger.info("🔧 Using unsigned requests for NZ public bucket")
                else:
                    # AU private bucket  
                    os.environ['AWS_DEFAULT_REGION'] = 'ap-southeast-2'
                    if not os.environ.get('AWS_ACCESS_KEY_ID'):
                        os.environ['AWS_ACCESS_KEY_ID'] = 'AKIA5SIDYET7N3U4JQ5H'
                    if not os.environ.get('AWS_SECRET_ACCESS_KEY'):
                        os.environ['AWS_SECRET_ACCESS_KEY'] = '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'
                    # Remove unsigned flag
                    if 'AWS_NO_SIGN_REQUEST' in os.environ:
                        del os.environ['AWS_NO_SIGN_REQUEST']
                    logger.info("🔧 Using signed requests for AU private bucket")
                
                # Simple rasterio access - no complex session management
                logger.info(f"📡 Opening with simple rasterio: {file_path}")
                with rasterio.open(file_path) as dataset:
                    logger.info(f"✅ Successfully opened {file_path}. CRS: {dataset.crs}, Count: {dataset.count}, Bounds: {dataset.bounds}")
                    # Transform coordinate to dataset CRS if needed
                    if dataset.crs.to_string() != 'EPSG:4326':
                        # Transform from WGS84 to dataset CRS
                        xs, ys = warp_transform('EPSG:4326', dataset.crs, [lon], [lat])
                        x, y = xs[0], ys[0]
                    else:
                        x, y = lon, lat
                    
                    # Sample elevation at coordinate
                    row, col = dataset.index(x, y)
                    
                    # Check if coordinate is within raster bounds
                    if (0 <= row < dataset.height and 0 <= col < dataset.width):
                        elevation = dataset.read(1)[row, col]
                        
                        # Handle nodata values
                        if dataset.nodata is not None and elevation == dataset.nodata:
                            return None
                        
                        logger.info(f"SUCCESS: Rasterio extracted elevation {float(elevation)}m from {file_path}")
                        return float(elevation)
                    else:
                        return None
                        
            finally:
                # Restore original environment
                for var, value in env_backup.items():
                    if value is None:
                        if var in os.environ:
                            del os.environ[var]
                    else:
                        os.environ[var] = value
                        
        except Exception as e:
            logger.error(f"❌ CRITICAL RASTERIO FAILURE opening {file_path}: {e}", exc_info=True)
            return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get source statistics"""
        if not self.unified_index:
            return {"error": "Unified index not loaded"}
        
        return {
            "source_type": "unified_s3",
            "collections": len(self.unified_index.data_collections),
            "total_files": self.unified_index.schema_metadata.total_files,
            "countries": self.unified_index.schema_metadata.countries,
            "collection_types": self.unified_index.schema_metadata.collection_types
        }