import logging
import rasterio
from rasterio.env import Env
from pyproj import Transformer, Geod
from typing import Dict, List, Tuple, Optional, Any
from src.config import Settings
import os
from src.unified_elevation_service import UnifiedElevationService
from src.dataset_manager import DatasetManager
from src.contour_service import ContourService
from src.dem_exceptions import (
    DEMServiceError, DEMFileError, DEMCacheError, 
    DEMCoordinateError, DEMProcessingError
)

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

    def get_coverage_summary(self) -> Dict[str, Any]:
        """Get coverage summary for configured DEM sources."""
        return {
            "total_sources": len(self.settings.DEM_SOURCES),
            "default_source": self.default_dem_id,
            "configured_sources": list(self.settings.DEM_SOURCES.keys()),
            "selector_type": "unified_elevation_service"
        }

    async def close(self):
        """Close all service resources - lean coordinator cleanup."""
        services_to_close = [
            ("elevation_service", self.elevation_service),
            ("dataset_manager", self.dataset_manager)
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