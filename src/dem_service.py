import logging
import numpy as np
import rasterio
from cachetools import LRUCache
from rasterio.enums import Resampling
from rasterio.env import Env
from pyproj import Transformer, Geod
from typing import Dict, List, Tuple, Optional, Any
from src.config import Settings, DEMSource
import os
import fiona
import threading
# Configure matplotlib to use non-interactive backend before importing pyplot
import matplotlib
matplotlib.use('Agg')  # Use Anti-Grain Geometry backend (no GUI)
from skimage.measure import find_contours
from scipy.interpolate import griddata
from shapely.geometry import Polygon, Point, LineString
from shapely.ops import unary_union
from src.source_selector import DEMSourceSelector
from src.enhanced_source_selector import EnhancedSourceSelector
from src.unified_elevation_service import UnifiedElevationService
from src.dem_exceptions import (
    DEMServiceError, DEMFileError, DEMCacheError, 
    DEMCoordinateError, DEMProcessingError
)
from src.gpxz_client import GPXZConfig
from src.coverage_database import CoverageDatabase
from src.spatial_selector import AutomatedSourceSelector

# Configure GDAL logging to suppress non-critical errors
import rasterio.env
from rasterio.errors import RasterioIOError
import warnings

logger = logging.getLogger(__name__)

class ClosingLRUCache(LRUCache):
    """
    An LRU cache that calls .close() on evicted items.
    This is essential for caches that store objects with open file handles,
    like rasterio datasets, to prevent resource leaks.
    """
    def popitem(self):
        """Evict the least recently used item, closing it if possible."""
        key, value = super().popitem()
        if hasattr(value, 'close') and callable(value.close):
            try:
                value.close()
                logger.info(f"Closed evicted cache item: {key}")
            except Exception as e:
                logger.warning(f"Error closing evicted cache item {key}: {e}")
        return key, value

    def clear(self):
        """Clear the cache and close all remaining items."""
        for key, value in self.items():
            if hasattr(value, 'close') and callable(value.close):
                try:
                    value.close()
                    logger.info(f"Closed cache item on clear: {key}")
                except Exception as e:
                    logger.warning(f"Error closing cache item {key} on clear: {e}")
        super().clear()

class GDALErrorFilter(logging.Filter):
    """Custom filter to suppress known non-critical GDAL errors."""
    
    def __init__(self):
        super().__init__()
        # List of error patterns to suppress
        self.suppress_patterns = [
            'Error occurred in C:\\vcpkg\\buildtrees\\gdal\\src\\v3.9.3-e3a570b154.clean\\ogr\\ogrsf_frmts\\openfilegdb\\filegdbtable.cpp',
            'filegdbtable.cpp at line 1656',
            'filegdbtable.cpp at line 1518',
            'filegdbtable.cpp at line 1427',
            'GDAL signalled an error: err_no=1',
            'OpenFileGDB',
            'FileGDB',
            'ogr\\ogrsf_frmts\\openfilegdb',
            'openfilegdb\\filegdbtable.cpp',
            'Error occurred in C:'
        ]
    
    def filter(self, record):
        """Return False to suppress log records matching our patterns."""
        if hasattr(record, 'msg') and record.msg:
            message = str(record.msg)
            # Suppress messages containing any of our patterns
            for pattern in self.suppress_patterns:
                if pattern in message:
                    return False
        
        # Also check the formatted message
        if hasattr(record, 'getMessage'):
            try:
                formatted_message = record.getMessage()
                for pattern in self.suppress_patterns:
                    if pattern in formatted_message:
                        return False
            except:
                pass
        
        return True

# GDAL error filter will be applied conditionally in DEMService.__init__

class DEMService:
    def __init__(self, settings: Settings):
        self.settings = settings
        # Use size-limited, resource-safe LRU caches
        self._dataset_cache = ClosingLRUCache(maxsize=settings.DATASET_CACHE_SIZE)
        self._transformer_cache = LRUCache(maxsize=settings.DATASET_CACHE_SIZE)
        # Thread lock for thread-safe dataset access
        self._dataset_lock = threading.RLock()
        
        # Set AWS environment variables globally for GDAL/rasterio
        import os
        os.environ['AWS_ACCESS_KEY_ID'] = settings.AWS_ACCESS_KEY_ID
        os.environ['AWS_SECRET_ACCESS_KEY'] = settings.AWS_SECRET_ACCESS_KEY
        os.environ['AWS_DEFAULT_REGION'] = settings.AWS_DEFAULT_REGION
        
        # Initialize unified elevation service that handles all source selection logic
        self.elevation_service = UnifiedElevationService(settings)
        
        # Legacy support - maintain existing source selector for backward compatibility
        # TODO: Migrate remaining methods to use elevation_service and remove this
        use_s3 = getattr(settings, 'USE_S3_SOURCES', False)
        use_apis = getattr(settings, 'USE_API_SOURCES', False)
        
        if use_s3 or use_apis:
            # Use EnhancedSourceSelector for S3 → GPXZ → Google fallback chain
            gpxz_config = None
            if use_apis and hasattr(settings, 'GPXZ_API_KEY') and settings.GPXZ_API_KEY:
                gpxz_config = GPXZConfig(
                    api_key=settings.GPXZ_API_KEY,
                    daily_limit=getattr(settings, 'GPXZ_DAILY_LIMIT', 100),
                    rate_limit_per_second=getattr(settings, 'GPXZ_RATE_LIMIT', 1)
                )
            
            google_api_key = getattr(settings, 'GOOGLE_ELEVATION_API_KEY', None)
            
            # Prepare AWS credentials for S3 access
            aws_credentials = None
            if use_s3 and hasattr(settings, 'AWS_ACCESS_KEY_ID') and settings.AWS_ACCESS_KEY_ID:
                aws_credentials = {
                    'access_key_id': settings.AWS_ACCESS_KEY_ID,
                    'secret_access_key': settings.AWS_SECRET_ACCESS_KEY,
                    'region': settings.AWS_DEFAULT_REGION
                }
            
            self.source_selector = EnhancedSourceSelector(
                config=settings.DEM_SOURCES,
                use_s3=use_s3,
                use_apis=use_apis,
                gpxz_config=gpxz_config,
                google_api_key=google_api_key,
                aws_credentials=aws_credentials
            )
            self.using_spatial_selector = False
            logger.info(f"Initialized enhanced source selector (S3: {use_s3}, APIs: {use_apis})")
        else:
            # For local-only mode, try spatial coverage system first
            try:
                # Load spatial coverage database
                config_path = getattr(settings, 'DEM_SOURCES_CONFIG_PATH', 'config/dem_sources.json')
                coverage_db = CoverageDatabase(config_path)
                
                # Initialize automated source selector
                self.source_selector = AutomatedSourceSelector(coverage_db)
                self.using_spatial_selector = True
                
                logger.info(f"Initialized spatial coverage selector with {len(coverage_db.sources)} sources")
                
                # Log coverage summary
                stats = coverage_db.get_stats()
                logger.info(f"Source statistics: {stats['enabled_sources']} enabled, "
                           f"resolution {stats['resolution_range']['min']}-{stats['resolution_range']['max']}m")
                           
            except Exception as e:
                logger.warning(f"Failed to initialize spatial selector, falling back to basic: {e}")
                
                # Fallback to basic selector system
                self.source_selector = DEMSourceSelector(settings)
                self.using_spatial_selector = False
                logger.info("Initialized basic source selector (local mode)")
        
        # Configure GDAL environment to suppress certain errors
        self._configure_gdal_environment()
        
        # Determine default DEM source
        if settings.DEFAULT_DEM_ID:
            if settings.DEFAULT_DEM_ID not in settings.DEM_SOURCES:
                raise ValueError(f"Default DEM ID '{settings.DEFAULT_DEM_ID}' not found in configured sources")
            self.default_dem_id = settings.DEFAULT_DEM_ID
        else:
            # Use first source as default
            if not settings.DEM_SOURCES:
                raise ValueError("No DEM sources configured")
            self.default_dem_id = next(iter(settings.DEM_SOURCES.keys()))
        
        logger.info(f"DEM Service initialized with default source: {self.default_dem_id}")
        logger.info(f"Auto-select best source: {settings.AUTO_SELECT_BEST_SOURCE}")

        # Proactively load the default DEM dataset during initialization
        if self.default_dem_id:
            logger.info(f"Proactively loading default DEM dataset: {self.default_dem_id}")
            try:
                self._get_dataset(self.default_dem_id)
                self._get_transformer(self.default_dem_id)
                logger.info(f"Default DEM dataset '{self.default_dem_id}' loaded and transformed successfully.")
            except Exception as e:
                logger.error(f"Failed to proactively load default DEM dataset '{self.default_dem_id}': {e}")
                # Depending on desired behavior, you might want to raise this exception
                # or just log it and allow the service to start without the default DEM pre-loaded.
                # For now, we'll log and continue to allow service startup.

    def _configure_gdal_environment(self):
        """Configure GDAL environment to suppress non-critical errors."""
        if self.settings.SUPPRESS_GDAL_ERRORS:
            # Suppress GDAL warnings and errors that don't affect functionality
            os.environ['CPL_LOG_ERRORS'] = 'OFF'
            # Set GDAL to only show critical errors
            os.environ['CPL_DEBUG'] = 'OFF'
            # Suppress specific OpenFileGDB table errors
            os.environ['GDAL_DISABLE_READDIR_ON_OPEN'] = 'EMPTY_DIR'
            # Additional environment variables for FileGDB error suppression
            os.environ['GDAL_DISABLE_OPENFILEGDB_ERROR_REPORTING'] = 'YES'
            os.environ['CPL_LOG'] = '/dev/null'  # Redirect logs to null on Unix-like systems
            
            # Apply logging filter to suppress specific GDAL errors
            gdal_filter = GDALErrorFilter()
            logging.getLogger('rasterio._err').addFilter(gdal_filter)
            logging.getLogger('rasterio').addFilter(gdal_filter)
            logging.getLogger('rasterio._env').addFilter(gdal_filter)
            logging.getLogger('gdal').addFilter(gdal_filter)
            logging.getLogger('osgeo').addFilter(gdal_filter)
            
            # Filter out specific rasterio warnings
            warnings.filterwarnings('ignore', module='rasterio')
            warnings.filterwarnings('ignore', message='.*GDAL signalled an error.*')
            warnings.filterwarnings('ignore', message='.*Error occurred in.*filegdbtable.cpp.*')
            
            logger.info("GDAL environment configured to suppress non-critical errors")
        else:
            logger.info("GDAL error suppression disabled - showing all GDAL messages")

    def _resolve_source_id(self, dem_source_id: str) -> str:
        """
        Resolve spatial source ID to actual DEM source ID in settings.
        
        For spatial sources that aren't directly available in settings,
        we'll return the default source for now (future: API/S3 integration).
        """
        if dem_source_id in self.settings.DEM_SOURCES:
            return dem_source_id
        
        if self.using_spatial_selector:
            # For sources not in settings (like API sources), fall back to default
            logger.warning(f"Spatial source '{dem_source_id}' not available in settings, using default: {self.default_dem_id}")
            return self.default_dem_id
        
        return dem_source_id

    def _get_elevation_from_gpxz_api(self, latitude: float, longitude: float, source_id: str) -> Tuple[Optional[float], str, Optional[str]]:
        """Get elevation from GPXZ API for API sources."""
        logger.warning(f"Using legacy GPXZ client for {source_id} - this should use enhanced source selector")
        try:
            # Create GPXZ client directly if we have the API key
            if hasattr(self.settings, 'GPXZ_API_KEY') and self.settings.GPXZ_API_KEY:
                from src.gpxz_client import GPXZClient, GPXZConfig
                import asyncio
                
                # Create GPXZ config and client
                gpxz_config = GPXZConfig(
                    api_key=self.settings.GPXZ_API_KEY,
                    daily_limit=getattr(self.settings, 'GPXZ_DAILY_LIMIT', 100),
                    rate_limit_per_second=getattr(self.settings, 'GPXZ_RATE_LIMIT', 1)
                )
                gpxz_client = GPXZClient(gpxz_config)
                
                # Create an async wrapper for the synchronous call
                async def get_gpxz_elevation():
                    try:
                        elevation = await gpxz_client.get_elevation_point(latitude, longitude)
                        return elevation
                    finally:
                        # Always close the client
                        await gpxz_client.close()
                
                # Run the async function
                try:
                    loop = asyncio.get_event_loop()
                    elevation = loop.run_until_complete(get_gpxz_elevation())
                except RuntimeError:
                    # If no event loop is running, create a new one
                    elevation = asyncio.run(get_gpxz_elevation())
                
                if elevation is not None:
                    logger.info(f"GPXZ API returned elevation {elevation}m for ({latitude}, {longitude})")
                    return elevation, source_id, None
                else:
                    return None, source_id, "GPXZ API returned no elevation data"
            else:
                return None, source_id, "GPXZ API key not available"
                
        except Exception as e:
            logger.error(f"Error getting elevation from GPXZ API: {e}")
            return None, source_id, f"GPXZ API error: {str(e)}"

    def _detect_geodatabase_path(self, path: str) -> Tuple[str, Optional[str]]:
        """
        Detects if a path is a geodatabase and extracts the base path and layer name.
        Returns the geodatabase path and the layer name if found.
        """
        # Normalize path separators
        path = path.replace('\\', '/')
        
        # Check if the path points to a geodatabase directory
        is_gdb = '.gdb' in path
        
        if is_gdb:
            gdb_path_part = path.split('.gdb')[0] + '.gdb'
            
            # Check if it's a local path and if it exists
            if not gdb_path_part.startswith('s3://') and not os.path.exists(gdb_path_part):
                raise ValueError(f"Geodatabase path does not exist: {gdb_path_part}")
            
            logger.info(f"Detected geodatabase: {gdb_path_part}")

            # Check if a layer is specified in the path
            if '.gdb/' in path and len(path.split('.gdb/')[1]) > 0:
                layer_name = path.split('.gdb/')[1]
                logger.info(f"Layer specified in path: {layer_name}")
                return gdb_path_part, layer_name
            
            # If no layer is specified, try to find one
            logger.info(f"No layer specified in path, searching for raster layers in {gdb_path_part}")
            raster_layer = self._find_raster_layer_in_gdb(gdb_path_part)
            if raster_layer:
                logger.info(f"Found raster layer: {raster_layer}")
                return gdb_path_part, raster_layer
        
        # If not a geodatabase or no layer found, return the original path
        return path, None

    def _find_raster_layer_in_gdb(self, gdb_path: str) -> Optional[str]:
        """Find the first valid raster layer in a File Geodatabase."""
        logger.info(f"Searching for raster layers in: {gdb_path}")

        try:
            # Use fiona to list all layers in the geodatabase
            layer_names = fiona.listlayers(gdb_path)
            logger.info(f"Found {len(layer_names)} total layers: {layer_names}")
        except Exception as e:
            # This is the critical point where "Permission Denied" will likely show up
            logger.error(f"Could not list layers in geodatabase '{gdb_path}': {e}")
            # Returning None will allow the calling function to handle the failure gracefully
            return None

        # Test each layer to see if it's a raster
        for layer_name in layer_names:
            try:
                # Construct the full path for rasterio to open
                rasterio_path = f"{gdb_path}/{layer_name}"
                
                # Use a GDAL environment that doesn't suppress critical errors
                with Env(CPL_LOG_ERRORS='ON', GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR'):
                    with rasterio.open(rasterio_path) as dataset:
                        # Check if the dataset has at least one band
                        if dataset.count > 0:
                            logger.info(f"Confirmed raster layer: '{layer_name}'")
                            return layer_name
            except rasterio.errors.RasterioIOError:
                # This is expected if the layer is not a raster, so we can ignore it
                logger.debug(f"Layer '{layer_name}' is not a raster layer. Skipping.")
                continue
            except Exception as e:
                # Log other unexpected errors
                logger.warning(f"Error when checking layer '{layer_name}': {e}")
                continue
        
        logger.warning(f"No valid raster layers found in geodatabase: {gdb_path}")
        return None

    def _get_dataset(self, dem_source_id: str, lat: float = None, lon: float = None) -> rasterio.DatasetReader:
        """Get or create cached dataset for the given DEM source."""
        # Create cache key that includes coordinates for S3 directory sources
        cache_key = dem_source_id
        if lat is not None and lon is not None:
            # Use coordinates in cache key for S3 directory sources
            dem_source = self.settings.DEM_SOURCES.get(dem_source_id, {})
            source_path = dem_source.get("path", "")
            if source_path.startswith('s3://') and source_path.endswith('/'):
                cache_key = f"{dem_source_id}_{lat:.4f}_{lon:.4f}"
        
        if cache_key not in self._dataset_cache:
            if dem_source_id not in self.settings.DEM_SOURCES:
                raise ValueError(f"DEM source '{dem_source_id}' not found in configuration")
            
            dem_source = self.settings.DEM_SOURCES[dem_source_id]
            
            # Detect geodatabase and get the actual path and layer name
            gdb_path, layer_name = self._detect_geodatabase_path(dem_source["path"])
            
            try:
                # Open the dataset using the detected path and layer
                dataset = self._open_dataset_with_fallbacks(gdb_path, layer_name, lat, lon)
                self._dataset_cache[cache_key] = dataset
                logger.info(f"Successfully opened and cached dataset for source: '{cache_key}'")
                
            except Exception as e:
                dem_path = dem_source["path"]
                logger.error(f"Failed to open DEM from source '{dem_source_id}' at path '{dem_path}': {e}")
                raise ValueError(f"Could not access or open DEM file: {dem_path}. Reason: {e}")
        
        return self._dataset_cache[cache_key]

    def _open_dataset_with_fallbacks(self, path: str, layer_name: Optional[str] = None, lat: float = None, lon: float = None) -> rasterio.DatasetReader:
        """
        Opens a dataset, with specific handling for geodatabases.
        """
        # Construct the full path for rasterio
        if layer_name:
            # For geodatabases, the path should be 'path/to/db.gdb/layer_name'
            rasterio_path = f"{path}/{layer_name}"
        else:
            rasterio_path = path

        logger.info(f"Attempting to open dataset: {rasterio_path}")
        
        try:
            # Handle S3 paths with special directory discovery
            if rasterio_path.startswith('s3://'):
                # Check if this is a directory path that needs file discovery
                if rasterio_path.endswith('/'):
                    logger.info(f"S3 directory detected: {rasterio_path}")
                    # This is handled by _discover_s3_files method
                    discovered_files = self._discover_s3_files(rasterio_path)
                    if discovered_files:
                        # Use coordinate-based file selection if coordinates available
                        selected_file = self._select_best_s3_file(discovered_files, rasterio_path, lat, lon)
                        logger.info(f"Selected S3 file: {selected_file}")
                        rasterio_path = selected_file.replace('s3://', '/vsis3/')
                    else:
                        raise ValueError(f"No DEM files found in S3 directory: {rasterio_path}")
                else:
                    # Single file, convert to /vsis3/ format
                    rasterio_path = rasterio_path.replace('s3://', '/vsis3/')
                    logger.info(f"Converting S3 file: {rasterio_path}")
            
            # Use GDAL environment with error logging and appropriate S3 configuration
            env_config = {'CPL_LOG_ERRORS': 'ON'}
            
            # Configure for unsigned requests if using nz-elevation bucket
            if '/vsis3/nz-elevation/' in rasterio_path:
                env_config['AWS_NO_SIGN_REQUEST'] = 'YES'
                env_config['AWS_DEFAULT_REGION'] = 'ap-southeast-2'
                logger.info(f"Configuring unsigned access for NZ elevation bucket: {rasterio_path}")
            
            with Env(**env_config):
                dataset = rasterio.open(rasterio_path)
                if dataset.count > 0:
                    logger.info(f"Successfully opened dataset: {rasterio_path}")
                    return dataset
                
                # If the dataset opens but has no bands, it's not a valid raster
                dataset.close()
                raise ValueError("Dataset opened but contains no raster bands.")

        except Exception as e:
            logger.error(f"Failed to open dataset '{rasterio_path}'. Error: {e}")
            # Re-raise the exception to be caught by the calling function
            raise

    def _discover_s3_files(self, s3_directory_path: str) -> List[str]:
        """
        Discover DEM files in an S3 directory
        
        Args:
            s3_directory_path: S3 directory path (e.g., 's3://bucket/path/')
            
        Returns:
            List of S3 file paths for DEM files
        """
        try:
            import boto3
            
            # Parse S3 path
            if not s3_directory_path.startswith('s3://'):
                return []
            
            path_parts = s3_directory_path[5:].split('/', 1)  # Remove 's3://'
            bucket_name = path_parts[0]
            prefix = path_parts[1] if len(path_parts) > 1 else ""
            
            logger.info(f"Discovering files in S3: bucket={bucket_name}, prefix={prefix}")
            
            # Create S3 client with appropriate configuration
            if bucket_name == "nz-elevation":
                # NZ Open Data bucket - public access, no signature required
                from botocore import UNSIGNED
                from botocore.config import Config
                s3 = boto3.client(
                    's3',
                    region_name='ap-southeast-2',
                    config=Config(signature_version=UNSIGNED)
                )
            else:
                # Private bucket - requires AWS credentials
                s3 = boto3.client(
                    's3',
                    aws_access_key_id=self.settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=self.settings.AWS_SECRET_ACCESS_KEY,
                    region_name=self.settings.AWS_DEFAULT_REGION
                )
            
            # List objects in the directory
            response = s3.list_objects_v2(
                Bucket=bucket_name,
                Prefix=prefix,
                MaxKeys=1000  # Reasonable limit for DEM tiles
            )
            
            # Filter for DEM files (.tif, .tiff)
            dem_files = []
            for obj in response.get('Contents', []):
                key = obj['Key']
                if key.lower().endswith(('.tif', '.tiff')) and obj['Size'] > 0:
                    full_s3_path = f"s3://{bucket_name}/{key}"
                    dem_files.append(full_s3_path)
            
            logger.info(f"Found {len(dem_files)} DEM files in {s3_directory_path}")
            
            # Log sample files for debugging
            for i, file_path in enumerate(dem_files[:5]):
                logger.info(f"  Sample file {i+1}: {file_path.split('/')[-1]}")
            
            if len(dem_files) > 5:
                logger.info(f"  ... and {len(dem_files) - 5} more files")
            
            return dem_files
            
        except Exception as e:
            logger.error(f"Error discovering S3 files in {s3_directory_path}: {e}")
            return []

    def _select_best_s3_file(self, dem_files: List[str], original_path: str, lat: float = None, lon: float = None) -> str:
        """
        Select the best DEM file from available S3 files
        
        Uses spatial index if available, otherwise falls back to heuristics
        
        Args:
            dem_files: List of S3 DEM file paths
            original_path: Original directory path for context
            lat: Latitude for coordinate-based selection
            lon: Longitude for coordinate-based selection
            
        Returns:
            Selected S3 file path
        """
        if not dem_files:
            raise ValueError("No DEM files provided for selection")
        
        # Try spatial index first if coordinates provided
        if lat is not None and lon is not None:
            spatial_file = self._select_file_from_spatial_index(lat, lon, original_path)
            if spatial_file:
                logger.info(f"Selected file from spatial index: {spatial_file}")
                return spatial_file
        
        # Simple heuristic: prefer files with known geographic terms
        # This could be enhanced with actual coordinate-based selection
        priority_terms = ['bendigo', 'melbourne', 'brisbane', 'sydney']
        
        for term in priority_terms:
            for file_path in dem_files:
                if term.lower() in file_path.lower():
                    logger.info(f"Selected file based on geographic term '{term}': {file_path}")
                    return file_path
        
        # Fallback to first file
        selected = dem_files[0]
        logger.info(f"Selected first available file: {selected}")
        return selected
    
    def _load_spatial_index(self) -> Optional[Dict]:
        """Load spatial index from config file"""
        try:
            import json
            from pathlib import Path
            
            # Check if spatial index exists
            spatial_index_path = Path(self.settings.BASE_DIR) / "config" / "spatial_index.json"
            if not spatial_index_path.exists():
                return None
            
            with open(spatial_index_path, 'r') as f:
                spatial_index = json.load(f)
            
            logger.info(f"Loaded spatial index with {spatial_index.get('file_count', 0)} files")
            return spatial_index
            
        except Exception as e:
            logger.warning(f"Failed to load spatial index: {e}")
            return None
    
    def _select_file_from_spatial_index(self, lat: float, lon: float, s3_directory: str) -> Optional[str]:
        """Select specific file using spatial index"""
        try:
            spatial_index = self._load_spatial_index()
            if not spatial_index:
                return None
            
            # Find files that contain this coordinate
            matching_files = []
            for zone, zone_data in spatial_index.get("utm_zones", {}).items():
                for file_info in zone_data.get("files", []):
                    bounds = file_info.get("bounds", {})
                    if (bounds.get("min_lat", 0) <= lat <= bounds.get("max_lat", 0) and
                        bounds.get("min_lon", 0) <= lon <= bounds.get("max_lon", 0)):
                        
                        # Check if this file belongs to the requested directory
                        file_path = file_info.get("file", "")
                        if s3_directory.rstrip('/') in file_path:
                            matching_files.append(file_info)
            
            if not matching_files:
                return None
            
            # Select best file (highest resolution, most recent)
            best_file = min(matching_files, key=lambda f: (
                self._resolution_to_meters(f.get("resolution", "1m")),
                f.get("last_modified", "1970-01-01")
            ))
            
            logger.info(f"Spatial index selected: {best_file['filename']} for ({lat}, {lon})")
            return best_file["file"]
            
        except Exception as e:
            logger.warning(f"Error using spatial index: {e}")
            return None
    
    def _resolution_to_meters(self, resolution_str: str) -> float:
        """Convert resolution string to meters for comparison"""
        if "cm" in resolution_str:
            return float(resolution_str.replace("cm", "")) / 100
        elif "m" in resolution_str:
            return float(resolution_str.replace("m", ""))
        else:
            return 1.0  # Default

    def _get_transformer(self, dem_source_id: str) -> Transformer:
        """Get or create cached transformer for WGS84 to DEM CRS conversion."""
        if dem_source_id not in self._transformer_cache:
            dataset = self._get_dataset(dem_source_id)
            
            # Try to get CRS from dataset metadata first
            dem_crs = dataset.crs
            if dem_crs is None:
                # Fall back to configured CRS if available
                dem_source = self.settings.DEM_SOURCES[dem_source_id]
                if dem_source.get("crs"):
                    dem_crs = dem_source["crs"]
                else:
                    raise ValueError(f"No CRS information available for DEM source '{dem_source_id}'")
            
            transformer = Transformer.from_crs("EPSG:4326", dem_crs, always_xy=True)
            self._transformer_cache[dem_source_id] = transformer
            logger.info(f"Created transformer for {dem_source_id}: WGS84 -> {dem_crs}")
        
        return self._transformer_cache[dem_source_id]

    async def get_elevation_for_point(self, latitude: float, longitude: float,
                                     dem_source_id: Optional[str] = None) -> Optional[float]:
        """Get elevation with automatic source selection using enhanced multi-source selector"""
        
        # If enhanced source selector is available, use resilient API
        if hasattr(self.source_selector, 'get_elevation_with_resilience'):
            try:
                result = await self.source_selector.get_elevation_with_resilience(latitude, longitude)
                return result.get('elevation_m')
            except Exception as e:
                logger.error(f"Enhanced source selector failed: {e}")
                # Fall back to traditional method
                elevation, _, _ = self.get_elevation_at_point(latitude, longitude, dem_source_id, auto_select=True)
                return elevation
        else:
            # Use traditional method
            elevation, _, _ = self.get_elevation_at_point(latitude, longitude, dem_source_id, auto_select=True)
            return elevation

    async def get_elevation_unified(self, latitude: float, longitude: float, 
                                   dem_source_id: Optional[str] = None) -> Tuple[Optional[float], str, Optional[str]]:
        """
        Get elevation using the unified elevation service (new architecture).
        
        This method demonstrates the cleaner architecture with consolidated source selection.
        Eventually, this will replace get_elevation_at_point once fully tested.
        
        Returns:
            Tuple of (elevation_m, dem_source_used, error_message)
        """
        try:
            result = await self.elevation_service.get_elevation(latitude, longitude, dem_source_id)
            return result.elevation_m, result.dem_source_used, result.message
        except DEMCoordinateError as e:
            logger.warning(f"Invalid coordinates provided: {e}")
            return None, "coordinate_error", str(e)
        except DEMServiceError as e:
            logger.error(f"DEM service error: {e}")
            return None, "service_error", str(e)
        except Exception as e:
            logger.error(f"Unexpected error in unified elevation query: {e}")
            return None, "unexpected_error", str(e)

    async def get_elevations_for_line_unified(self, start_lat: float, start_lon: float,
                                            end_lat: float, end_lon: float, num_points: int,
                                            dem_source_id: Optional[str] = None) -> Tuple[List[Dict[str, Any]], str, Optional[str]]:
        """
        Get elevations for points along a line using the unified elevation service.
        
        Returns:
            Tuple of (point_list, dem_source_used, error_message)
        """
        try:
            # Generate line points
            points = self.generate_line_points(start_lat, start_lon, end_lat, end_lon, num_points)
            
            result_points = []
            primary_source = None
            
            for i, (lat, lon) in enumerate(points):
                elevation, dem_used, message = await self.get_elevation_unified(lat, lon, dem_source_id)
                if primary_source is None:
                    primary_source = dem_used
                    
                result_points.append({
                    "latitude": lat,
                    "longitude": lon,
                    "elevation_m": elevation,
                    "sequence": i,
                    "message": message
                })
            
            return result_points, primary_source or "unknown", None
            
        except DEMCoordinateError as e:
            logger.warning(f"Invalid coordinates in line elevation: {e}")
            raise
        except Exception as e:
            logger.error(f"Error getting elevations for line: {e}")
            return [], dem_source_id or "unknown", str(e)

    async def get_elevations_for_path_unified(self, points: List[Dict[str, Any]], 
                                            dem_source_id: Optional[str] = None) -> Tuple[List[Dict[str, Any]], str, Optional[str]]:
        """
        Get elevations for a list of discrete points using the unified elevation service.
        
        Returns:
            Tuple of (elevation_list, dem_source_used, error_message)
        """
        try:
            result_elevations = []
            primary_source = None
            
            for i, point in enumerate(points):
                lat = point["latitude"]
                lon = point["longitude"]
                point_id = point.get("id", i)
                
                elevation, dem_used, message = await self.get_elevation_unified(lat, lon, dem_source_id)
                if primary_source is None:
                    primary_source = dem_used
                
                result_elevations.append({
                    "input_latitude": lat,
                    "input_longitude": lon,
                    "input_id": point_id,
                    "elevation_m": elevation,
                    "sequence": i,
                    "message": message
                })
            
            return result_elevations, primary_source or "unknown", None
            
        except DEMCoordinateError as e:
            logger.warning(f"Invalid coordinates in path elevation: {e}")
            raise
        except Exception as e:
            logger.error(f"Error getting elevations for path: {e}")
            return [], dem_source_id or "unknown", str(e)

    def get_elevation_at_point(self, latitude: float, longitude: float, dem_source_id: Optional[str] = None, 
                              auto_select: bool = True) -> Tuple[Optional[float], str, Optional[str]]:
        """
        Get elevation at a single point with optional automatic source selection.
        
        Args:
            latitude: Point latitude in WGS84
            longitude: Point longitude in WGS84
            dem_source_id: Specific DEM source to use (overrides auto-selection)
            auto_select: Whether to automatically select the best source
        
        Returns:
            Tuple of (elevation_m, dem_source_used, error_message)
        """
        # Auto-select best source if enabled and no specific source requested
        if auto_select and dem_source_id is None:
            try:
                if self.using_spatial_selector:
                    # Use spatial selector for automated source selection
                    selected_source = self.source_selector.select_best_source(latitude, longitude)
                    dem_source_id = selected_source['id']
                    logger.debug(f"Spatial selector chose '{dem_source_id}' for ({latitude}, {longitude})")
                elif hasattr(self.source_selector, 'get_elevation_with_resilience'):
                    # Use EnhancedSourceSelector for S3 → GPXZ → Google fallback
                    import asyncio
                    try:
                        # Try to get the current event loop
                        loop = asyncio.get_event_loop()
                        result = loop.run_until_complete(self.source_selector.get_elevation_with_resilience(latitude, longitude))
                    except RuntimeError:
                        # If no event loop is running, create a new one
                        result = asyncio.run(self.source_selector.get_elevation_with_resilience(latitude, longitude))
                    
                    if result.get('success') and result.get('elevation_m') is not None:
                        logger.info(f"Enhanced selector returned {result['elevation_m']}m from {result['source']} for ({latitude}, {longitude})")
                        return result['elevation_m'], result['source'], None
                    else:
                        logger.warning(f"Enhanced selector failed for ({latitude}, {longitude}): {result}")
                        return None, "enhanced_selector_failed", "Enhanced selector could not retrieve elevation"
                elif self.settings.AUTO_SELECT_BEST_SOURCE:
                    # Use legacy selector
                    best_source_id, scores = self.source_selector.select_best_source(latitude, longitude)
                    dem_source_id = best_source_id
                    logger.debug(f"Legacy selector chose '{best_source_id}' for point ({latitude}, {longitude})")
            except Exception as e:
                logger.warning(f"Failed to auto-select source, using default: {e}")
                dem_source_id = self.default_dem_id
        
        # Fallback to default if no source specified
        if dem_source_id is None:
            dem_source_id = self.default_dem_id
        
        try:
            # Check if this is an API source that needs special handling
            if dem_source_id in self.settings.DEM_SOURCES:
                dem_source = self.settings.DEM_SOURCES[dem_source_id]
                source_path = dem_source.get("path", "")
                
                # Handle GPXZ API sources
                if source_path == "api://gpxz":
                    return self._get_elevation_from_gpxz_api(latitude, longitude, dem_source_id)
            
            # Use thread lock for thread-safe dataset access (file-based sources)
            with self._dataset_lock:
                # Convert spatial source ID to actual dataset if needed
                actual_source_id = self._resolve_source_id(dem_source_id)
                dataset = self._get_dataset(actual_source_id, latitude, longitude)
                transformer = self._get_transformer(actual_source_id)
                
                # Transform coordinates from WGS84 to DEM CRS
                x, y = transformer.transform(longitude, latitude)
                
                # Check if point is within dataset bounds
                if not (dataset.bounds.left <= x <= dataset.bounds.right and 
                       dataset.bounds.bottom <= y <= dataset.bounds.top):
                    return None, dem_source_id, "Point is outside DEM bounds"
                
                # Sample elevation using bilinear interpolation
                try:
                    # Use rasterio's sample method - updated for rasterio 1.4.x compatibility
                    elevation_values = list(dataset.sample([(x, y)]))
                    elevation = round(float(elevation_values[0][0]), 4)
                    
                    # Check for nodata values
                    if dataset.nodata is not None and elevation == dataset.nodata:
                        return None, dem_source_id, "No elevation data available at this location"
                    
                    return elevation, dem_source_id, None
                    
                except Exception as e:
                    logger.error(f"Error sampling elevation: {e}")
                    return None, dem_source_id, f"Error sampling elevation: {str(e)}"
                
        except Exception as e:
            logger.error(f"Error getting elevation for point ({latitude}, {longitude}): {e}")
            return None, dem_source_id or self.default_dem_id, str(e)

    def generate_line_points(self, start_lat: float, start_lon: float, 
                           end_lat: float, end_lon: float, num_points: int) -> List[Tuple[float, float]]:
        """Generate equally spaced points along a great circle line."""
        if num_points == 2:
            return [(start_lat, start_lon), (end_lat, end_lon)]
        
        # Use pyproj.Geod for great circle calculations
        geod = Geod(ellps='WGS84')
        
        # Calculate the great circle line
        line = geod.inv_intermediate(start_lon, start_lat, end_lon, end_lat, num_points - 2)
        
        # Extract coordinates
        points = [(start_lat, start_lon)]
        
        # Add intermediate points
        for lon, lat in zip(line.lons, line.lats):
            points.append((lat, lon))
        
        # Add end point
        points.append((end_lat, end_lon))
        
        return points

    def get_elevations_for_line(self, start_lat: float, start_lon: float,
                              end_lat: float, end_lon: float, num_points: int,
                              dem_source_id: Optional[str] = None) -> Tuple[List[Dict[str, Any]], str, Optional[str]]:
        """
        Get elevations for points along a line.
        
        Returns:
            Tuple of (point_list, dem_source_used, error_message)
        """
        try:
            points = self.generate_line_points(start_lat, start_lon, end_lat, end_lon, num_points)
            
            result_points = []
            for i, (lat, lon) in enumerate(points):
                elevation, dem_used, message = self.get_elevation_at_point(lat, lon, dem_source_id)
                result_points.append({
                    "latitude": lat,
                    "longitude": lon,
                    "elevation_m": elevation,
                    "sequence": i,
                    "message": message
                })
            
            return result_points, dem_source_id or self.default_dem_id, None
            
        except Exception as e:
            logger.error(f"Error getting elevations for line: {e}")
            return [], dem_source_id or self.default_dem_id, str(e)

    def get_elevations_for_path(self, points: List[Dict[str, Any]], 
                              dem_source_id: Optional[str] = None) -> Tuple[List[Dict[str, Any]], str, Optional[str]]:
        """
        Get elevations for a list of discrete points using optimized batch processing.
        
        Returns:
            Tuple of (elevation_list, dem_source_used, error_message)
        """
        if dem_source_id is None:
            dem_source_id = self.default_dem_id
            
        try:
            result_elevations = []
            
            # Use single lock acquisition for entire batch to improve performance
            with self._dataset_lock:
                dataset = self._get_dataset(dem_source_id)
                transformer = self._get_transformer(dem_source_id)
                
                # Prepare batch coordinates for transformation
                coordinates = [(point["longitude"], point["latitude"]) for point in points]
                
                # Transform all coordinates at once (more efficient)
                transformed_coords = []
                for lon, lat in coordinates:
                    try:
                        x, y = transformer.transform(lon, lat)
                        transformed_coords.append((x, y))
                    except Exception as e:
                        logger.warning(f"Failed to transform coordinates ({lat}, {lon}): {e}")
                        transformed_coords.append(None)
                
                # Process each point with already-loaded dataset and transformer
                for i, point in enumerate(points):
                    lat = point["latitude"]
                    lon = point["longitude"]
                    point_id = point.get("id")
                    
                    try:
                        # Use pre-transformed coordinates
                        if transformed_coords[i] is None:
                            elevation, message = None, "Failed to transform coordinates"
                        else:
                            x, y = transformed_coords[i]
                            
                            # Check if point is within dataset bounds
                            if not (dataset.bounds.left <= x <= dataset.bounds.right and 
                                   dataset.bounds.bottom <= y <= dataset.bounds.top):
                                elevation, message = None, "Point is outside DEM bounds"
                            else:
                                # Sample elevation using bilinear interpolation
                                try:
                                    elevation_values = list(dataset.sample([(x, y)]))
                                    elevation = round(float(elevation_values[0][0]), 4)
                                    
                                    # Check for nodata values
                                    if dataset.nodata is not None and elevation == dataset.nodata:
                                        elevation, message = None, "No elevation data available at this location"
                                    else:
                                        message = None
                                        
                                except Exception as e:
                                    logger.debug(f"Error sampling elevation for point {i}: {e}")
                                    elevation, message = None, f"Error sampling elevation: {str(e)}"
                        
                    except Exception as e:
                        logger.debug(f"Error processing point {i} ({lat}, {lon}): {e}")
                        elevation, message = None, str(e)
                    
                    result_elevations.append({
                        "input_latitude": lat,
                        "input_longitude": lon,
                        "input_id": point_id,
                        "elevation_m": elevation,
                        "sequence": i,
                        "message": message
                    })
            
            # Log statistics for monitoring
            successful_count = sum(1 for elev in result_elevations if elev["elevation_m"] is not None)
            total_count = len(result_elevations)
            success_rate = (successful_count / total_count * 100) if total_count > 0 else 0
            logger.info(f"Batch processing complete: {successful_count}/{total_count} successful elevations ({success_rate:.1f}%)")
            
            return result_elevations, dem_source_id, None
            
        except Exception as e:
            logger.error(f"Error getting elevations for path: {e}")
            return [], dem_source_id or self.default_dem_id, str(e)

    def get_source_info(self, dem_source_id: Optional[str] = None) -> Dict[str, Any]:
        """Get information about a DEM source."""
        if dem_source_id is None:
            dem_source_id = self.default_dem_id
        
        try:
            dataset = self._get_dataset(dem_source_id)
            dem_source = self.settings.DEM_SOURCES[dem_source_id]
            
            # Detect path info
            actual_path, layer_name = self._detect_geodatabase_path(dem_source["path"])
            is_geodatabase = actual_path.lower().endswith('.gdb')
            
            info = {
                "source_id": dem_source_id,
                "path": dem_source["path"],
                "is_geodatabase": is_geodatabase,
                "layer_name": layer_name,
                "driver": dataset.driver,
                "crs": str(dataset.crs),
                "bounds": {
                    "left": dataset.bounds.left,
                    "bottom": dataset.bounds.bottom,
                    "right": dataset.bounds.right,
                    "top": dataset.bounds.top
                },
                "dimensions": {
                    "width": dataset.width,
                    "height": dataset.height
                },
                "band_count": dataset.count,
                "data_types": [str(dataset.dtypes[i]) for i in range(dataset.count)],
                "nodata_values": [dataset.nodatavals[i] for i in range(dataset.count)]
            }
            
            return info
            
        except Exception as e:
            logger.error(f"Error getting source info for {dem_source_id}: {e}")
            return {"error": str(e)}

    def get_dem_points_in_polygon(self, polygon_coords: List[Tuple[float, float]], 
                                max_points: int = 50000,
                                sampling_interval_m: Optional[float] = None,
                                dem_source_id: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str, Optional[str]]:
        """
        Get all native DEM points within a polygon area using sampling method.
        
        Args:
            polygon_coords: List of (latitude, longitude) tuples defining the polygon boundary
            max_points: Maximum number of points to return (safety limit)
            sampling_interval_m: Grid sampling interval in meters. If None, uses DEM pixel resolution
            dem_source_id: DEM source to use (defaults to default source)
        
        Returns:
            Tuple of (dem_points_list, grid_info, dem_source_used, error_message)
        """
        if dem_source_id is None:
            dem_source_id = self.default_dem_id
        
        try:
            from shapely.geometry import Polygon, Point
            
            # Create polygon from coordinates (polygon_coords contains (lat, lon) tuples)
            # Shapely expects (x, y) which is (longitude, latitude)
            poly = Polygon([(lon, lat) for lat, lon in polygon_coords])
            
            with self._dataset_lock:
                dataset = self._get_dataset(dem_source_id)
                transformer = self._get_transformer(dem_source_id)
                
                # Get bounding box in geographic coordinates
                min_lat = min(coord[0] for coord in polygon_coords)
                max_lat = max(coord[0] for coord in polygon_coords)
                min_lon = min(coord[1] for coord in polygon_coords)
                max_lon = max(coord[1] for coord in polygon_coords)
                
                logger.info(f"Geographic bounds: lat=[{min_lat}, {max_lat}], lon=[{min_lon}, {max_lon}]")
                
                # Get actual DEM pixel resolution
                dem_pixel_size_x = abs(dataset.transform[0])  # Pixel width in DEM CRS units
                dem_pixel_size_y = abs(dataset.transform[4])  # Pixel height in DEM CRS units
                dem_resolution_m = max(dem_pixel_size_x, dem_pixel_size_y)  # Use larger dimension for safety
                
                # Use provided sampling interval or default to DEM resolution
                if sampling_interval_m is None:
                    sampling_interval_m = dem_resolution_m
                    logger.info(f"Using DEM native resolution: {sampling_interval_m:.2f}m")
                else:
                    logger.info(f"Using custom sampling interval: {sampling_interval_m:.2f}m (DEM resolution: {dem_resolution_m:.2f}m)")
                
                # Calculate grid resolution in geographic coordinates
                # Transform a small offset to understand the spatial resolution
                try:
                    center_x, center_y = transformer.transform((min_lon + max_lon) / 2, (min_lat + max_lat) / 2)
                    # Test sampling_interval_m offset in DEM CRS
                    offset_x, offset_y = center_x + sampling_interval_m, center_y + sampling_interval_m
                    # Transform back to geographic
                    center_lon, center_lat = transformer.transform(center_x, center_y, direction='INVERSE')
                    offset_lon, offset_lat = transformer.transform(offset_x, offset_y, direction='INVERSE')
                    
                    # Calculate approximate degrees per meter
                    lon_per_meter = abs(offset_lon - center_lon) / sampling_interval_m
                    lat_per_meter = abs(offset_lat - center_lat) / sampling_interval_m
                    
                    logger.info(f"Approximate resolution: {lon_per_meter:.8f} deg/m lon, {lat_per_meter:.8f} deg/m lat")
                    
                except Exception as e:
                    logger.warning(f"Could not calculate precise resolution: {e}")
                    # Fallback approximation (1 meter ≈ 9e-6 degrees at this latitude)
                    lon_per_meter = lat_per_meter = 9e-6
                
                # Create a regular sampling grid in geographic coordinates
                lat_step = lat_per_meter * sampling_interval_m
                lon_step = lon_per_meter * sampling_interval_m
                
                # Calculate number of samples
                lat_range = max_lat - min_lat
                lon_range = max_lon - min_lon
                num_lat_samples = max(1, int(lat_range / lat_step)) + 1
                num_lon_samples = max(1, int(lon_range / lon_step)) + 1
                
                total_samples = num_lat_samples * num_lon_samples
                logger.info(f"Grid sampling: {num_lat_samples} x {num_lon_samples} = {total_samples} total sample points")
                logger.info(f"Sampling interval: {sampling_interval_m}m (±{lat_step:.8f}° lat, ±{lon_step:.8f}° lon)")
                
                if total_samples > max_points * 2:  # Safety check
                    # Reduce sampling density
                    factor = (max_points * 2 / total_samples) ** 0.5
                    lat_step *= 1/factor
                    lon_step *= 1/factor
                    num_lat_samples = max(1, int(lat_range / lat_step)) + 1
                    num_lon_samples = max(1, int(lon_range / lon_step)) + 1
                    total_samples = num_lat_samples * num_lon_samples
                    logger.info(f"Reduced sampling density: {num_lat_samples} x {num_lon_samples} = {total_samples} sample points")
                
                dem_points = []
                point_count = 0
                nodata_count = 0
                polygon_rejected_count = 0
                sampling_error_count = 0
                
                # Sample points in a regular grid pattern using the same method as single points
                for lat_idx in range(num_lat_samples):
                    if point_count >= max_points:
                        logger.warning(f"Reached maximum point limit ({max_points}). Truncating results.")
                        break
                        
                    lat = min_lat + lat_idx * lat_step
                    
                    for lon_idx in range(num_lon_samples):
                        if point_count >= max_points:
                            break
                            
                        lon = min_lon + lon_idx * lon_step
                        
                        # Check if point is inside the polygon first (before expensive sampling)
                        point = Point(lon, lat)
                        if not (poly.contains(point) or poly.touches(point)):
                            polygon_rejected_count += 1
                            continue
                        
                        # Sample elevation using the same method as get_elevation_at_point
                        try:
                            # Transform to DEM CRS
                            x, y = transformer.transform(lon, lat)
                            
                            # Check if point is within dataset bounds
                            if not (dataset.bounds.left <= x <= dataset.bounds.right and 
                                   dataset.bounds.bottom <= y <= dataset.bounds.top):
                                sampling_error_count += 1
                                continue
                            
                            # Sample elevation using bilinear interpolation (same as single point method)
                            elevation_values = list(dataset.sample([(x, y)]))
                            elevation = float(elevation_values[0][0])
                            
                            # Check for nodata values
                            if dataset.nodata is not None and elevation == dataset.nodata:
                                nodata_count += 1
                                continue
                            if np.isnan(elevation):
                                nodata_count += 1
                                continue
                            
                            # Calculate approximate grid indices for reference
                            col, row = dataset.index(x, y)
                            
                            # Point is valid - add to results
                            dem_points.append({
                                "latitude": lat,
                                "longitude": lon,
                                "elevation_m": round(elevation, 4),
                                "x_grid_index": int(col),
                                "y_grid_index": int(row),
                                "grid_resolution_m": sampling_interval_m
                            })
                            point_count += 1
                            
                        except Exception as e:
                            logger.debug(f"Error sampling elevation at ({lat:.6f}, {lon:.6f}): {e}")
                            sampling_error_count += 1
                            continue
                    
                    if point_count >= max_points:
                        break
                
                logger.info(f"Processing summary: nodata_count={nodata_count}, polygon_rejected_count={polygon_rejected_count}, sampling_error_count={sampling_error_count}, accepted_points={point_count}")
                
                # Grid information
                grid_info = {
                    "total_width": dataset.width,
                    "total_height": dataset.height,
                    "sampled_area": {
                        "min_lat": min_lat,
                        "max_lat": max_lat,
                        "min_lon": min_lon,
                        "max_lon": max_lon,
                        "lat_samples": num_lat_samples,
                        "lon_samples": num_lon_samples,
                        "total_samples": total_samples
                    },
                    "grid_resolution_m": sampling_interval_m,
                    "dem_native_resolution_m": dem_resolution_m,
                    "pixel_size": {
                        "width": dem_pixel_size_x,
                        "height": dem_pixel_size_y
                    },
                    "crs": str(dataset.crs),
                    "bounds": {
                        "left": dataset.bounds.left,
                        "bottom": dataset.bounds.bottom,
                        "right": dataset.bounds.right,
                        "top": dataset.bounds.top
                    }
                }
                
                logger.info(f"Extracted {len(dem_points)} DEM points from polygon area")
                
                return dem_points, grid_info, dem_source_id, None
                
        except ImportError:
            error_msg = "Shapely library is required for polygon operations. Please install with: pip install shapely"
            logger.error(error_msg)
            return [], {}, dem_source_id, error_msg
        except Exception as e:
            logger.error(f"Error getting DEM points in polygon: {e}")
            return [], {}, dem_source_id, str(e)

    def generate_geojson_contours(self, polygon_coords: List[Tuple[float, float]], 
                                max_points: int = 50000,
                                sampling_interval_m: Optional[float] = None,
                                minor_contour_interval_m: float = 1.0,
                                major_contour_interval_m: float = 5.0,
                                dem_source_id: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any], str, Optional[str]]:
        """
        Generate GeoJSON contour lines from DEM data within a polygon area.
        
        Args:
            polygon_coords: List of (latitude, longitude) tuples defining the polygon boundary
            max_points: Maximum number of points to use for contour generation
            sampling_interval_m: Grid sampling interval in meters. If None, uses DEM pixel resolution
            minor_contour_interval_m: Interval for minor contour lines in meters
            major_contour_interval_m: Interval for major contour lines in meters
            dem_source_id: DEM source to use (defaults to default source)
        
        Returns:
            Tuple of (geojson_contours, statistics, dem_source_used, error_message)
        """
        if dem_source_id is None:
            dem_source_id = self.default_dem_id
        
        try:
            # First, get the DEM points using the existing method
            dem_points, grid_info, dem_source_used, error_message = self.get_dem_points_in_polygon(
                polygon_coords, max_points, sampling_interval_m, dem_source_id
            )
            
            if error_message or not dem_points:
                return {}, {}, dem_source_used, error_message or "No elevation data found in the specified area"
            
            logger.info(f"Generating contours from {len(dem_points)} elevation points")
            
            # Extract coordinates and elevations
            lats = [point["latitude"] for point in dem_points]
            lons = [point["longitude"] for point in dem_points]
            elevations = [point["elevation_m"] for point in dem_points]
            
            # Calculate statistics
            min_elevation = min(elevations)
            max_elevation = max(elevations)
            
            # Generate contour intervals based on minor and major intervals
            start_elevation = np.floor(min_elevation / minor_contour_interval_m) * minor_contour_interval_m
            end_elevation = np.ceil(max_elevation / minor_contour_interval_m) * minor_contour_interval_m
            
            minor_levels = np.arange(start_elevation, end_elevation + minor_contour_interval_m, minor_contour_interval_m)
            major_levels = np.arange(start_elevation, end_elevation + major_contour_interval_m, major_contour_interval_m)
            
            # Combine and sort levels, removing duplicates
            contour_levels = np.unique(np.concatenate((minor_levels, major_levels)))
            
            # Filter out levels that are outside our data range
            contour_levels = contour_levels[(contour_levels >= min_elevation) & (contour_levels <= max_elevation)]
            
            if len(contour_levels) == 0:
                return {}, {}, dem_source_used, "No valid contour levels found for the elevation range"
            
            logger.info(f"Generating {len(contour_levels)} contour levels: {contour_levels.tolist()}")
            
            # Create a regular grid for interpolation
            polygon = Polygon([(lon, lat) for lat, lon in polygon_coords])
            bounds = polygon.bounds
            min_lon, min_lat, max_lon, max_lat = bounds
            
            # Determine grid resolution based on data density
            lon_range = max_lon - min_lon
            lat_range = max_lat - min_lat
            num_points = len(dem_points)
            
            # Aim for roughly sqrt(num_points) * 2 grid points per dimension, with a higher cap
            target_grid_size = max(50, min(500, int(np.sqrt(num_points) * 2.0)))
            
            # Create interpolation grid
            grid_lon = np.linspace(min_lon, max_lon, target_grid_size)
            grid_lat = np.linspace(min_lat, max_lat, target_grid_size)
            grid_lon_mesh, grid_lat_mesh = np.meshgrid(grid_lon, grid_lat)
            
            # New strategy: Use NaN-based boundary handling to prevent contour artifacts
            logger.info("Using advanced NaN-based boundary handling to prevent contour connections")
            input_polygon_shapely = Polygon([(lon, lat) for lat, lon in polygon_coords])
            
            # Create an adaptive buffer inside the polygon to prevent boundary artifacts
            # Make buffer size adaptive based on polygon size and target grid resolution
            grid_cell_size = (max_lon - min_lon) / target_grid_size
            polygon_area = input_polygon_shapely.area
            
            # For fine contour intervals, use minimal boundary buffering to preserve contour generation
            min_contour_interval = min(minor_contour_interval_m, major_contour_interval_m)
            is_very_fine_interval = min_contour_interval <= 0.2
            
            if is_very_fine_interval:
                # For very fine intervals, use no internal buffer - rely on post-processing only
                logger.info(f"Very fine intervals detected ({min_contour_interval}m), using no internal buffer")
                inner_polygon = input_polygon_shapely
            elif polygon_area < (grid_cell_size * 10) ** 2:  # Very small polygon (< 10x10 grid cells)
                buffer_distance = -0.01 * grid_cell_size  # Minimal buffer
                logger.info(f"Very small polygon detected, using minimal buffer: {buffer_distance}")
                inner_polygon = input_polygon_shapely.buffer(buffer_distance)
                if inner_polygon.is_empty:
                    inner_polygon = input_polygon_shapely
            elif polygon_area < (grid_cell_size * 20) ** 2:  # Small polygon (< 20x20 grid cells)
                buffer_distance = -0.1 * grid_cell_size  # Small buffer
                logger.info(f"Small polygon detected, using small buffer: {buffer_distance}")
                inner_polygon = input_polygon_shapely.buffer(buffer_distance)
                if inner_polygon.is_empty or inner_polygon.area < input_polygon_shapely.area * 0.5:
                    inner_polygon = input_polygon_shapely
            else:  # Normal or large polygon
                buffer_distance = -0.5 * grid_cell_size  # Moderate buffer
                logger.info(f"Normal polygon detected, using moderate buffer: {buffer_distance}")
                inner_polygon = input_polygon_shapely.buffer(buffer_distance)
                if inner_polygon.is_empty or inner_polygon.area < input_polygon_shapely.area * 0.3:
                    inner_polygon = input_polygon_shapely
            
            # Use ALL elevation points for interpolation to avoid interpolation artifacts
            logger.info("Performing full interpolation with strategic NaN boundary placement")
            
            try:
                # Interpolate using all available points for best results
                grid_elevations = griddata(
                    points=np.column_stack((lons, lats)),
                    values=elevations,
                    xi=(grid_lon_mesh, grid_lat_mesh),
                    method='cubic',
                    fill_value=np.nan
                )
                
                # Fill remaining NaN values with nearest neighbor for robustness
                nan_count = np.sum(np.isnan(grid_elevations))
                if nan_count > 0:
                    logger.info(f"Filling {nan_count} NaN values with nearest neighbor interpolation")
                    grid_elevations_nearest = griddata(
                        points=np.column_stack((lons, lats)),
                        values=elevations,
                        xi=(grid_lon_mesh, grid_lat_mesh),
                        method='nearest'
                    )
                    # Fill all NaN values
                    nan_mask = np.isnan(grid_elevations)
                    grid_elevations[nan_mask] = grid_elevations_nearest[nan_mask]
                
                # NOW apply the boundary constraint: set areas outside inner polygon to NaN
                # This prevents matplotlib from creating contours that connect across boundaries
                logger.info("Applying NaN boundary constraints to prevent artifacts")
                for i in range(grid_lat_mesh.shape[0]):
                    for j in range(grid_lon_mesh.shape[1]):
                        point = Point(grid_lon_mesh[i, j], grid_lat_mesh[i, j])
                        if not (inner_polygon.contains(point) or inner_polygon.touches(point)):
                            grid_elevations[i, j] = np.nan
                
                # Validate that we have sufficient valid grid points for contour generation
                valid_points = np.sum(~np.isnan(grid_elevations))
                total_points = grid_elevations.size
                valid_percentage = 100 * valid_points / total_points
                
                nan_boundary_count = np.sum(np.isnan(grid_elevations))
                logger.info(f"Set {nan_boundary_count} grid points to NaN for boundary constraints")
                logger.info(f"Valid grid points for contour generation: {valid_points} ({valid_percentage:.1f}%)")
                
                # If we don't have enough valid points, relax the buffer constraints
                if valid_points < 20:  # Need at least 20 valid points for contour generation
                    logger.warning(f"Insufficient valid grid points ({valid_points}), relaxing buffer constraints")
                    
                    # Reset grid elevations and use original polygon with minimal constraints
                    grid_elevations = griddata(
                        points=np.column_stack((lons, lats)),
                        values=elevations,
                        xi=(grid_lon_mesh, grid_lat_mesh),
                        method='cubic',
                        fill_value=np.nan
                    )
                    
                    # Fill remaining NaN values with nearest neighbor for robustness
                    nan_count = np.sum(np.isnan(grid_elevations))
                    if nan_count > 0:
                        grid_elevations_nearest = griddata(
                            points=np.column_stack((lons, lats)),
                            values=elevations,
                            xi=(grid_lon_mesh, grid_lat_mesh),
                            method='nearest'
                        )
                        nan_mask = np.isnan(grid_elevations)
                        grid_elevations[nan_mask] = grid_elevations_nearest[nan_mask]
                    
                    # Only apply very minimal boundary filtering (just outside original polygon)
                    for i in range(grid_lat_mesh.shape[0]):
                        for j in range(grid_lon_mesh.shape[1]):
                            point = Point(grid_lon_mesh[i, j], grid_lat_mesh[i, j])
                            if not input_polygon_shapely.contains(point):
                                grid_elevations[i, j] = np.nan
                    
                    valid_points = np.sum(~np.isnan(grid_elevations))
                    logger.info(f"After relaxed filtering: {valid_points} valid grid points")
                
            except Exception as e:
                logger.error(f"Error during advanced interpolation: {e}")
                return {}, {}, dem_source_used, f"Failed to interpolate elevation data: {str(e)}"
            
            # Generate contours using scikit-image for more control
            logger.info("Generating contour lines using scikit-image for precise boundary handling")
            try:
                # Extract contour paths and convert to GeoJSON
                geojson_features = []

                # scikit-image works best with non-NaN values, so we fill with a value
                # outside the data range.
                min_valid_elevation = np.nanmin(grid_elevations)
                fill_value = min_valid_elevation - 100  # A value safely outside the range
                
                # The grid needs to be flipped because scikit-image indexing is (row, col)
                # which corresponds to (lat, lon), but our grid is (lon, lat).
                # We also replace NaNs with the fill value.
                processed_grid = np.nan_to_num(np.flipud(grid_elevations), nan=fill_value)

                # Iterate over each contour level and find contours
                for level in contour_levels:
                    # find_contours returns paths in pixel coordinates (indices)
                    paths = find_contours(processed_grid, level, fully_connected='low')
                    
                    for path in paths:
                        # Convert pixel/index coordinates back to geographic coordinates
                        # path[:, 1] gives the column indices (for longitude)
                        # path[:, 0] gives the row indices (for latitude)
                        
                        # Get longitudes from the original grid's columns
                        lon_indices = np.clip(path[:, 1].astype(int), 0, grid_lon_mesh.shape[1] - 1)
                        lons = grid_lon_mesh[0, lon_indices]
                        
                        # Get latitudes, accounting for the vertical flip
                        lat_indices = (processed_grid.shape[0] - 1) - path[:, 0].astype(int)
                        lat_indices = np.clip(lat_indices, 0, grid_lat_mesh.shape[0] - 1)
                        lats = grid_lat_mesh[lat_indices, 0]

                        # Combine into [lon, lat] pairs
                        vertices = np.vstack((lons, lats)).T
                        
                        if len(vertices) < 2:
                            continue
                        
                        # Create a LineString for filtering and clipping
                        contour_line = LineString(vertices)
                        
                        points_inside_count = 0
                        total_points = len(vertices)
                        max_segment_length = 0
                        
                        min_contour_interval = min(minor_contour_interval_m, major_contour_interval_m)
                        is_fine_interval = min_contour_interval <= 0.5
                        
                        # Set default thresholds first
                        inside_threshold = 0.8
                        max_allowed_segment = 0.001  # Relaxed from 0.0005
                        min_length_threshold = 0.000002  # Relaxed from 0.00001
                        min_points_threshold = 2  # Relaxed from 3
                        
                        # Adjust for fine intervals - even more permissive
                        if is_fine_interval:
                            inside_threshold = 0.6
                            max_allowed_segment = 0.002  # Relaxed from 0.001
                            min_length_threshold = 0.000001  # Relaxed from 0.000005
                            min_points_threshold = 2
                        
                        for i, vertex in enumerate(vertices):
                            if i > 0:
                                prev_vertex = vertices[i-1]
                                segment_length = np.sqrt((vertex[0] - prev_vertex[0])**2 + (vertex[1] - prev_vertex[1])**2)
                                max_segment_length = max(max_segment_length, segment_length)
                        
                        # Filter based on segment length first
                        if max_segment_length > max_allowed_segment:
                            continue

                        # Strict clipping: only keep parts that are inside the original polygon
                        clipped_geometry = input_polygon_shapely.intersection(contour_line)

                        if clipped_geometry.is_empty:
                            continue
                        
                        geoms_to_add = []
                        if clipped_geometry.geom_type == 'LineString':
                            geoms_to_add.append(clipped_geometry)
                        elif clipped_geometry.geom_type == 'MultiLineString':
                            geoms_to_add.extend(list(clipped_geometry.geoms))

                        for geom in geoms_to_add:
                            if geom.length < min_length_threshold or len(geom.coords) < min_points_threshold:
                                continue
                            
                            final_coords = [[float(coord[0]), float(coord[1])] for coord in geom.coords]
                            if len(final_coords) < 2:
                                continue
                                
                            geojson_features.append(self._create_geojson_feature(final_coords, float(level)))
                
                # Create GeoJSON FeatureCollection
                geojson_contours = {
                    "type": "FeatureCollection",
                    "features": geojson_features
                }
                
                # Create statistics
                statistics = {
                    "total_points": len(dem_points),
                    "min_elevation": float(min_elevation),
                    "max_elevation": float(max_elevation),
                    "contour_count": len(geojson_features),
                    "elevation_intervals": [float(level) for level in contour_levels]
                }
                
                logger.info(f"Generated {len(geojson_features)} contour lines")
                
                return geojson_contours, statistics, dem_source_used, None
                
            except Exception as e:
                logger.error(f"Error generating contours with scikit-image: {e}")
                return {}, {}, dem_source_used, f"Failed to generate contour lines: {str(e)}"
                
        except Exception as e:
            logger.error(f"Error generating GeoJSON contours: {e}")
            return {}, {}, dem_source_id, str(e)

    def _create_geojson_feature(self, coordinates: List[List[float]], elevation: float) -> Dict[str, Any]:
        """Helper to create a GeoJSON feature dictionary."""
        return {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates
            },
            "properties": {
                "elevation": elevation,
                "elevation_units": "meters"
            }
        }

    def select_best_source_for_point(self, latitude: float, longitude: float, 
                                   prefer_high_resolution: bool = True,
                                   max_resolution_m: Optional[float] = None) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Select the best DEM source for a specific location.
        
        Returns:
            Tuple of (best_source_id, all_scores_as_dicts)
        """
        if self.using_spatial_selector:
            # Use spatial selector
            try:
                selected_source = self.source_selector.select_best_source(latitude, longitude)
                best_source_id = selected_source['id']
                
                # Get detailed coverage summary for all options
                coverage_summary = self.source_selector.get_coverage_summary(latitude, longitude)
                
                # Convert to legacy format for backward compatibility
                scores_dict = []
                if coverage_summary['all_options']:
                    for i, option in enumerate(coverage_summary['all_options']):
                        scores_dict.append({
                            "source_id": option['id'],
                            "score": 1.0 - (i * 0.1),  # Higher score for better priority
                            "within_bounds": True,
                            "resolution_m": option['resolution_m'],
                            "priority": option['priority'],
                            "data_source": option['provider'],
                            "year": option.get('metadata', {}).get('capture_date', 'Unknown'),
                            "reason": coverage_summary['reason'] if i == 0 else f"Alternative option #{i+1}"
                        })
                else:
                    # No coverage available
                    scores_dict.append({
                        "source_id": "none",
                        "score": 0.0,
                        "within_bounds": False,
                        "resolution_m": 0,
                        "priority": 999,
                        "data_source": "No coverage",
                        "year": "N/A",
                        "reason": coverage_summary['reason']
                    })
                
                return best_source_id, scores_dict
                
            except Exception as e:
                logger.error(f"Spatial selector failed: {e}")
                # Fall back to default
                return self.default_dem_id, [{
                    "source_id": self.default_dem_id,
                    "score": 0.5,
                    "within_bounds": True,
                    "resolution_m": 0,
                    "priority": 1,
                    "data_source": "Fallback",
                    "year": "Unknown",
                    "reason": f"Spatial selector error: {e}"
                }]
        else:
            # Use legacy selector
            best_source_id, scores = self.source_selector.select_best_source(
                latitude, longitude, prefer_high_resolution, max_resolution_m
            )
            
            # Convert scores to dictionaries for JSON serialization
            scores_dict = []
            for score in scores:
                scores_dict.append({
                    "source_id": score.source_id,
                    "score": score.score,
                    "within_bounds": score.within_bounds,
                    "resolution_m": score.resolution_m,
                    "priority": score.priority,
                    "data_source": score.data_source,
                    "year": score.year,
                    "reason": score.reason
                })
            
            return best_source_id, scores_dict

    def get_coverage_summary(self) -> Dict[str, Any]:
        """Get coverage summary from the source selector."""
        if self.using_spatial_selector:
            # Return spatial selector statistics
            stats = self.source_selector.get_selector_stats()
            return {
                "total_sources": stats["total_configured_sources"],
                "enabled_sources": stats["enabled_sources"],
                "cache_performance": {
                    "total_selections": stats["total_selections"],
                    "cache_hits": stats["cache_hits"],
                    "hit_rate": stats["cache_hit_rate"]
                },
                "selector_type": "spatial_coverage"
            }
        else:
            # Use legacy coverage summary
            return self.source_selector.get_coverage_summary()

    async def close(self):
        """Close all cached datasets and elevation service resources."""
        # Close unified elevation service
        try:
            await self.elevation_service.close()
            logger.info("Closed unified elevation service resources.")
        except Exception as e:
            logger.warning(f"Error closing elevation service: {e}")
        
        # Close legacy source selector if it exists (for backward compatibility)
        if hasattr(self.source_selector, 'close'):
            try:
                await self.source_selector.close()
                logger.info("Closed legacy source selector resources.")
            except Exception as e:
                logger.warning(f"Error closing legacy source selector: {e}")
        
        # The custom ClosingLRUCache's clear() method handles closing datasets.
        if hasattr(self._dataset_cache, 'clear'):
            self._dataset_cache.clear()
        if hasattr(self._transformer_cache, 'clear'):
            self._transformer_cache.clear()
        logger.info("DEM Service closed and all caches cleared.") 