"""
ContourService: Handles complex contour generation and terrain analysis.

This class extracts the sophisticated contour generation logic from DEMService,
following the Single Responsibility Principle and improving testability.
"""

import logging
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from shapely.geometry import Polygon, Point, LineString
from shapely.ops import unary_union
from skimage.measure import find_contours
from scipy.interpolate import griddata

from src.dataset_manager import DatasetManager
from src.dem_exceptions import DEMProcessingError, DEMCoordinateError

logger = logging.getLogger(__name__)


class ContourService:
    """
    Handles complex contour generation and DEM terrain analysis.
    
    This service encapsulates all contour-related operations, providing a clean
    interface for terrain visualization while maintaining separation of concerns.
    """
    
    def __init__(self, dataset_manager: DatasetManager):
        self.dataset_manager = dataset_manager
        logger.info("ContourService initialized")

    def get_dem_points_in_polygon(self, polygon_coords: List[Tuple[float, float]], 
                                 dem_source_id: str, max_points: int = 1000) -> Tuple[List[Dict[str, Any]], str, Optional[str]]:
        """
        Extract elevation points within a polygon area for contour analysis.
        
        Args:
            polygon_coords: List of (latitude, longitude) tuples defining the polygon
            dem_source_id: ID of the DEM source to use
            max_points: Maximum number of points to extract
            
        Returns:
            Tuple of (elevation_points, dem_source_used, error_message)
            
        Raises:
            DEMCoordinateError: If polygon coordinates are invalid
            DEMProcessingError: If elevation extraction fails
        """
        try:
            if len(polygon_coords) < 3:
                raise DEMCoordinateError("Polygon must have at least 3 coordinates")
            
            # Get dataset and transformer
            dataset = self.dataset_manager.get_dataset(dem_source_id)
            transformer = self.dataset_manager.get_transformer(dem_source_id)
            
            logger.info(f"Extracting DEM points from polygon with {len(polygon_coords)} vertices")
            
            # Transform polygon coordinates to dataset CRS
            transformed_coords = []
            for lat, lon in polygon_coords:
                try:
                    x, y = transformer.transform(lon, lat)  # Note: lon, lat order for transform
                    transformed_coords.append((x, y))
                except Exception as e:
                    logger.error(f"Failed to transform coordinate ({lat}, {lon}): {e}")
                    raise DEMCoordinateError(f"Invalid coordinate ({lat}, {lon}): {str(e)}")
            
            # Create shapely polygon for spatial operations
            try:
                polygon_shapely = Polygon(transformed_coords)
                if not polygon_shapely.is_valid:
                    polygon_shapely = polygon_shapely.buffer(0)  # Fix self-intersections
                    
                bounds = polygon_shapely.bounds
                logger.info(f"Polygon bounds in dataset CRS: {bounds}")
                
            except Exception as e:
                raise DEMProcessingError(f"Failed to create valid polygon: {str(e)}")
            
            # Calculate sampling grid based on max_points
            bbox_width = bounds[2] - bounds[0]
            bbox_height = bounds[3] - bounds[1]
            bbox_area = bbox_width * bbox_height
            
            # Estimate grid size to achieve roughly max_points within the polygon
            if bbox_area <= 0:
                raise DEMProcessingError("Polygon has zero area")
            
            points_per_unit_area = max_points / bbox_area
            grid_spacing = 1.0 / np.sqrt(points_per_unit_area)
            
            # Ensure minimum reasonable spacing based on dataset resolution
            if hasattr(dataset, 'res') and dataset.res[0] > 0:
                min_spacing = dataset.res[0] * 2  # At least 2x dataset resolution
                grid_spacing = max(grid_spacing, min_spacing)
            
            logger.info(f"Using grid spacing: {grid_spacing:.2f} units")
            
            # Generate sampling grid
            x_coords = np.arange(bounds[0], bounds[2], grid_spacing)
            y_coords = np.arange(bounds[1], bounds[3], grid_spacing)
            
            dem_points = []
            points_processed = 0
            points_inside = 0
            
            for x in x_coords:
                for y in y_coords:
                    points_processed += 1
                    
                    # Check if point is inside polygon
                    point = Point(x, y)
                    if polygon_shapely.contains(point):
                        points_inside += 1
                        
                        try:
                            # Sample elevation at this point
                            row, col = dataset.index(x, y)
                            
                            # Check bounds
                            if (0 <= row < dataset.height and 0 <= col < dataset.width):
                                elevation = dataset.read(1, window=((row, row+1), (col, col+1)))[0, 0]
                                
                                # Skip nodata values
                                if dataset.nodata is not None and elevation == dataset.nodata:
                                    continue
                                if np.isnan(elevation) or np.isinf(elevation):
                                    continue
                                
                                # Transform back to WGS84 for output
                                lon_wgs84, lat_wgs84 = transformer.transform(x, y, direction='INVERSE')
                                
                                dem_points.append({
                                    "latitude": lat_wgs84,
                                    "longitude": lon_wgs84,
                                    "elevation_m": float(elevation),
                                    "x_crs": x,
                                    "y_crs": y
                                })
                                
                                # Limit total points
                                if len(dem_points) >= max_points:
                                    logger.info(f"Reached max_points limit ({max_points})")
                                    break
                                    
                        except Exception as e:
                            # Skip points that can't be sampled
                            continue
                
                if len(dem_points) >= max_points:
                    break
            
            logger.info(f"Processed {points_processed} grid points, {points_inside} inside polygon, extracted {len(dem_points)} elevation points")
            
            if len(dem_points) == 0:
                return [], dem_source_id, "No valid elevation points found within polygon"
            
            return dem_points, dem_source_id, None
            
        except (DEMCoordinateError, DEMProcessingError):
            raise
        except Exception as e:
            logger.error(f"Unexpected error extracting DEM points: {e}")
            raise DEMProcessingError(f"Failed to extract elevation points: {str(e)}")

    def generate_geojson_contours(self, polygon_coords: List[Tuple[float, float]], 
                                dem_source_id: str, max_points: int = 1000,
                                minor_contour_interval_m: float = 1.0,
                                major_contour_interval_m: float = 5.0,
                                simplify_tolerance: float = 0.0001) -> Tuple[Dict[str, Any], Dict[str, Any], str, Optional[str]]:
        """
        Generate GeoJSON contour lines from DEM data within a polygon area.
        
        Args:
            polygon_coords: List of (latitude, longitude) tuples defining the polygon
            dem_source_id: ID of the DEM source to use
            max_points: Maximum number of points to use for contour generation
            minor_contour_interval_m: Interval for minor contour lines in meters
            major_contour_interval_m: Interval for major contour lines in meters
            simplify_tolerance: Tolerance for line simplification
            
        Returns:
            Tuple of (geojson_contours, statistics, dem_source_used, error_message)
        """
        try:
            # Extract elevation points within polygon
            dem_points, dem_source_used, error_msg = self.get_dem_points_in_polygon(
                polygon_coords, dem_source_id, max_points
            )
            
            if error_msg or not dem_points:
                return {}, {}, dem_source_used, error_msg or "No elevation points available"
            
            logger.info(f"Generating contours from {len(dem_points)} elevation points")
            
            # Extract coordinates and elevations
            elevations = np.array([point["elevation_m"] for point in dem_points])
            x_coords = np.array([point["x_crs"] for point in dem_points])  # Use CRS coordinates
            y_coords = np.array([point["y_crs"] for point in dem_points])
            
            # Calculate elevation statistics
            min_elevation = float(np.min(elevations))
            max_elevation = float(np.max(elevations))
            mean_elevation = float(np.mean(elevations))
            
            logger.info(f"Elevation range: {min_elevation:.2f}m to {max_elevation:.2f}m (mean: {mean_elevation:.2f}m)")
            
            # Generate contour intervals based on minor and major intervals
            start_elevation = np.floor(min_elevation / minor_contour_interval_m) * minor_contour_interval_m
            end_elevation = np.ceil(max_elevation / minor_contour_interval_m) * minor_contour_interval_m
            
            minor_levels = np.arange(start_elevation, end_elevation + minor_contour_interval_m, minor_contour_interval_m)
            major_levels = np.arange(start_elevation, end_elevation + major_contour_interval_m, major_contour_interval_m)
            
            # Combine and sort contour levels
            contour_levels = np.unique(np.concatenate((minor_levels, major_levels)))
            
            # Filter to actual elevation range
            contour_levels = contour_levels[(contour_levels >= min_elevation) & (contour_levels <= max_elevation)]
            
            if len(contour_levels) == 0:
                return {}, {}, dem_source_used, "No valid contour levels found for the elevation range"
            
            logger.info(f"Generating {len(contour_levels)} contour levels: {contour_levels.tolist()}")
            
            # Create regular grid for interpolation
            bbox_x = [np.min(x_coords), np.max(x_coords)]
            bbox_y = [np.min(y_coords), np.max(y_coords)]
            
            # Calculate grid resolution based on point density
            grid_points = min(200, int(np.sqrt(len(dem_points)) * 4))  # Adaptive resolution
            grid_x = np.linspace(bbox_x[0], bbox_x[1], grid_points)
            grid_y = np.linspace(bbox_y[0], bbox_y[1], grid_points)
            
            # Create meshgrid
            mesh_x, mesh_y = np.meshgrid(grid_x, grid_y)
            
            logger.info(f"Creating {grid_points}x{grid_points} interpolation grid")
            
            # Interpolate elevations to grid using linear interpolation
            try:
                grid_z = griddata(
                    (x_coords, y_coords), elevations,
                    (mesh_x, mesh_y), method='linear', fill_value=np.nan
                )
                
                # Apply NaN-based boundary handling to prevent contour artifacts
                input_polygon_shapely = Polygon([(dem_points[i]["x_crs"], dem_points[i]["y_crs"]) for i in range(0, len(dem_points), max(1, len(dem_points)//10))])
                
                # Mask grid points outside the input polygon
                for i in range(grid_points):
                    for j in range(grid_points):
                        point = Point(mesh_x[i, j], mesh_y[i, j])
                        if not input_polygon_shapely.contains(point):
                            grid_z[i, j] = np.nan
                
                # Validate grid
                valid_points = np.sum(~np.isnan(grid_z))
                valid_percentage = (valid_points / (grid_points * grid_points)) * 100
                
                logger.info(f"Valid grid points for contour generation: {valid_points} ({valid_percentage:.1f}%)")
                
                if valid_points < 20:  # Need at least 20 valid points for contour generation
                    return {}, {}, dem_source_used, f"Insufficient valid grid points ({valid_points}) for contour generation"
                
            except Exception as e:
                logger.error(f"Grid interpolation failed: {e}")
                return {}, {}, dem_source_used, f"Failed to create interpolation grid: {str(e)}"
            
            # Generate contours using scikit-image
            logger.info("Generating contour lines using scikit-image for precise boundary handling")
            
            try:
                # Get transformer for coordinate conversion
                transformer = self.dataset_manager.get_transformer(dem_source_id)
                
                geojson_features = []
                
                # Iterate over each contour level and find contours
                for level in contour_levels:
                    # find_contours returns paths in pixel coordinates (indices)
                    paths = find_contours(grid_z, level, fully_connected='low')
                    
                    for path in paths:
                        if len(path) < 3:  # Skip very short contours
                            continue
                        
                        # Convert pixel coordinates to CRS coordinates
                        vertices = []
                        for point in path:
                            # Convert from grid indices to actual coordinates
                            y_idx, x_idx = point  # Note: find_contours returns (row, col)
                            
                            # Interpolate to get actual coordinates
                            if 0 <= y_idx < grid_points and 0 <= x_idx < grid_points:
                                x_crs = grid_x[int(x_idx)]
                                y_crs = grid_y[int(y_idx)]
                                
                                # Transform back to WGS84
                                try:
                                    lon, lat = transformer.transform(x_crs, y_crs, direction='INVERSE')
                                    vertices.append([lon, lat])
                                except Exception:
                                    continue  # Skip invalid transformations
                        
                        if len(vertices) >= 3:  # Valid contour line
                            # Create LineString and apply simplification if requested
                            contour_line = LineString(vertices)
                            
                            if simplify_tolerance > 0:
                                contour_line = contour_line.simplify(simplify_tolerance, preserve_topology=True)
                            
                            # Determine contour type
                            is_major = level in major_levels
                            contour_type = "major" if is_major else "minor"
                            
                            # Create GeoJSON feature
                            feature = {
                                "type": "Feature",
                                "geometry": {
                                    "type": "LineString",
                                    "coordinates": list(contour_line.coords)
                                },
                                "properties": {
                                    "elevation": float(level),
                                    "type": contour_type,
                                    "interval": major_contour_interval_m if is_major else minor_contour_interval_m
                                }
                            }
                            geojson_features.append(feature)
                
                # Create final GeoJSON structure
                geojson_contours = {
                    "type": "FeatureCollection",
                    "features": geojson_features
                }
                
                # Create statistics
                statistics = {
                    "min_elevation": min_elevation,
                    "max_elevation": max_elevation,
                    "mean_elevation": mean_elevation,
                    "contour_count": len(geojson_features),
                    "elevation_intervals": [float(level) for level in contour_levels]
                }
                
                logger.info(f"Generated {len(geojson_features)} contour lines")
                
                return geojson_contours, statistics, dem_source_used, None
                
            except Exception as e:
                logger.error(f"Error generating contours with scikit-image: {e}")
                return {}, {}, dem_source_used, f"Failed to generate contour lines: {str(e)}"
            
        except (DEMCoordinateError, DEMProcessingError):
            raise
        except Exception as e:
            logger.error(f"Error generating GeoJSON contours: {e}")
            return {}, {}, dem_source_id, f"Contour generation failed: {str(e)}"