import logging
import rasterio
from rasterio.env import Env
from pyproj import Transformer, Geod
from typing import Dict, List, Tuple, Optional, Any
from src.config import Settings
import os
from src.source_selector import DEMSourceSelector
from src.enhanced_source_selector import EnhancedSourceSelector
from src.unified_elevation_service import UnifiedElevationService
from src.dataset_manager import DatasetManager
from src.contour_service import ContourService
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
        
        # Initialize dataset manager for all rasterio I/O and caching
        self.dataset_manager = DatasetManager(settings)
        
        # Initialize contour service for complex terrain analysis
        self.contour_service = ContourService(self.dataset_manager)
        
        # Set AWS environment variables globally for GDAL/rasterio
        import os
        os.environ['AWS_ACCESS_KEY_ID'] = settings.AWS_ACCESS_KEY_ID
        os.environ['AWS_SECRET_ACCESS_KEY'] = settings.AWS_SECRET_ACCESS_KEY
        os.environ['AWS_DEFAULT_REGION'] = settings.AWS_DEFAULT_REGION
        
        # Initialize unified elevation service that handles all source selection logic
        self.elevation_service = UnifiedElevationService(settings)
        
        # Provide dataset manager to elevation service for dependency injection
        if hasattr(self.elevation_service, 'set_dataset_manager'):
            self.elevation_service.set_dataset_manager(self.dataset_manager)
        
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
                self.dataset_manager.get_dataset(self.default_dem_id)
                self.dataset_manager.get_transformer(self.default_dem_id)
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
                
                # Handle GPXZ API sources - delegate to enhanced source selector
                if source_path == "api://gpxz":
                    logger.warning(f"GPXZ API source {dem_source_id} should be handled by enhanced source selector")
                    return None, dem_source_id, "API sources should use enhanced source selector"
            
            # Convert spatial source ID to actual dataset if needed
            actual_source_id = self._resolve_source_id(dem_source_id)
            dataset = self.dataset_manager.get_dataset(actual_source_id, latitude, longitude)
            transformer = self.dataset_manager.get_transformer(actual_source_id)
            
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
            
            dataset = self.dataset_manager.get_dataset(dem_source_id)
            transformer = self.dataset_manager.get_transformer(dem_source_id)
            
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
            dataset = self.dataset_manager.get_dataset(dem_source_id)
            dem_source = self.settings.DEM_SOURCES[dem_source_id]
            
            # Check if it's a geodatabase - simplified detection without detailed path analysis
            is_geodatabase = dem_source["path"].lower().endswith('.gdb')
            layer_name = dem_source.get("layer")
            
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
        Delegate to ContourService for DEM point extraction within a polygon.
        
        This method delegates to the ContourService while maintaining the existing API.
        """
        if dem_source_id is None:
            dem_source_id = self.default_dem_id
        
        try:
            # Call ContourService method with compatible signature
            dem_points, dem_source_used, error_message = self.contour_service.get_dem_points_in_polygon(
                polygon_coords, dem_source_id, max_points
            )
            
            # Create legacy grid_info structure for backward compatibility
            grid_info = {
                "total_points": len(dem_points),
                "max_points_limit": max_points,
                "sampling_method": "contour_service_delegation"
            }
            
            return dem_points, grid_info, dem_source_used, error_message
            
        except Exception as e:
            logger.error(f"Error in get_dem_points_in_polygon delegation: {e}")
            return [], {}, dem_source_id or self.default_dem_id, str(e)

    def generate_geojson_contours(self, polygon_coords: List[Tuple[float, float]], 
                                max_points: int = 50000,
                                sampling_interval_m: Optional[float] = None,
                                minor_contour_interval_m: float = 1.0,
                                major_contour_interval_m: float = 5.0,
                                dem_source_id: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any], str, Optional[str]]:
        """
        Delegate to ContourService for GeoJSON contour generation.
        
        This method delegates to the ContourService while maintaining the existing API.
        """
        if dem_source_id is None:
            dem_source_id = self.default_dem_id
        
        try:
            # Call ContourService method with compatible signature
            geojson_contours, statistics, dem_source_used, error_message = self.contour_service.generate_geojson_contours(
                polygon_coords=polygon_coords,
                dem_source_id=dem_source_id,
                max_points=max_points,
                minor_contour_interval_m=minor_contour_interval_m,
                major_contour_interval_m=major_contour_interval_m
            )
            
            return geojson_contours, statistics, dem_source_used, error_message
            
        except Exception as e:
            logger.error(f"Error in generate_geojson_contours delegation: {e}")
            return {}, {}, dem_source_id or self.default_dem_id, str(e)


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
        """Close all service resources - lean coordinator cleanup."""
        services_to_close = [
            ("elevation_service", self.elevation_service),
            ("dataset_manager", self.dataset_manager),
            ("source_selector", getattr(self, 'source_selector', None))
        ]
        
        for service_name, service in services_to_close:
            if service and hasattr(service, 'close'):
                try:
                    if service_name == "elevation_service":
                        await service.close()
                    else:
                        await service.close() if hasattr(service.close, '__await__') else service.close()
                    logger.info(f"Closed {service_name} resources.")
                except Exception as e:
                    logger.warning(f"Error closing {service_name}: {e}")
        
        logger.info("DEM Service coordinator closed successfully.") 