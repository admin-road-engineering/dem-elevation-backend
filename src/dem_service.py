import logging
import numpy as np
import rasterio
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

# Configure GDAL logging to suppress non-critical errors
import rasterio.env
from rasterio.errors import RasterioIOError
import warnings

logger = logging.getLogger(__name__)

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
        self._dataset_cache: Dict[str, rasterio.DatasetReader] = {}
        self._transformer_cache: Dict[str, Transformer] = {}
        # Thread lock for thread-safe dataset access
        self._dataset_lock = threading.RLock()
        
        # Initialize source selector
        self.source_selector = DEMSourceSelector(settings)
        
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

    def _get_dataset(self, dem_source_id: str) -> rasterio.DatasetReader:
        """Get or create cached dataset for the given DEM source."""
        if dem_source_id not in self._dataset_cache:
            if dem_source_id not in self.settings.DEM_SOURCES:
                raise ValueError(f"DEM source '{dem_source_id}' not found in configuration")
            
            dem_source = self.settings.DEM_SOURCES[dem_source_id]
            
            # Detect geodatabase and get the actual path and layer name
            gdb_path, layer_name = self._detect_geodatabase_path(dem_source["path"])
            
            try:
                # Open the dataset using the detected path and layer
                dataset = self._open_dataset_with_fallbacks(gdb_path, layer_name)
                self._dataset_cache[dem_source_id] = dataset
                logger.info(f"Successfully opened and cached dataset for source: '{dem_source_id}'")
                
            except Exception as e:
                dem_path = dem_source["path"]
                logger.error(f"Failed to open DEM from source '{dem_source_id}' at path '{dem_path}': {e}")
                raise ValueError(f"Could not access or open DEM file: {dem_path}. Reason: {e}")
        
        return self._dataset_cache[dem_source_id]

    def _open_dataset_with_fallbacks(self, path: str, layer_name: Optional[str] = None) -> rasterio.DatasetReader:
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
            # Use a GDAL environment that doesn't suppress critical errors
            with Env(CPL_LOG_ERRORS='ON'):
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
        if auto_select and dem_source_id is None and self.settings.AUTO_SELECT_BEST_SOURCE:
            try:
                best_source_id, scores = self.source_selector.select_best_source(latitude, longitude)
                dem_source_id = best_source_id
                logger.debug(f"Auto-selected source '{best_source_id}' for point ({latitude}, {longitude})")
            except Exception as e:
                logger.warning(f"Failed to auto-select source, using default: {e}")
                dem_source_id = self.default_dem_id
        
        # Fallback to default if no source specified
        if dem_source_id is None:
            dem_source_id = self.default_dem_id
        
        try:
            # Use thread lock for thread-safe dataset access
            with self._dataset_lock:
                dataset = self._get_dataset(dem_source_id)
                transformer = self._get_transformer(dem_source_id)
                
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
        return self.source_selector.get_coverage_summary()

    def close(self):
        """Close all cached datasets."""
        for dataset in self._dataset_cache.values():
            dataset.close()
        self._dataset_cache.clear()
        self._transformer_cache.clear()
        logger.info("DEM Service closed and caches cleared") 