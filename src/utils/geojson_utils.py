"""GeoJSON utility functions for campaign boundary generation."""

import logging
from typing import List, Dict, Any, Optional, Tuple
from shapely.geometry import Polygon, MultiPolygon, Point
from shapely.ops import unary_union
from shapely.validation import make_valid
from shapely.simplify import preserve_topology
import geojson

logger = logging.getLogger(__name__)


def bounds_to_polygon(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> Polygon:
    """Convert bounding box to Shapely Polygon."""
    return Polygon([
        (min_lon, min_lat),
        (max_lon, min_lat),
        (max_lon, max_lat),
        (min_lon, max_lat),
        (min_lon, min_lat)
    ])


def polygons_to_geojson(geometry) -> Dict[str, Any]:
    """Convert Shapely geometry to GeoJSON format."""
    if isinstance(geometry, Polygon):
        # Single polygon
        coordinates = [list(geometry.exterior.coords)]
        # Add interior rings (holes) if present
        for interior in geometry.interiors:
            coordinates.append(list(interior.coords))
        
        return {
            "type": "Polygon",
            "coordinates": coordinates
        }
    
    elif isinstance(geometry, MultiPolygon):
        # Multiple polygons
        coordinates = []
        for poly in geometry.geoms:
            poly_coords = [list(poly.exterior.coords)]
            # Add interior rings (holes) if present
            for interior in poly.interiors:
                poly_coords.append(list(interior.coords))
            coordinates.append(poly_coords)
        
        return {
            "type": "MultiPolygon",
            "coordinates": coordinates
        }
    
    else:
        raise ValueError(f"Unsupported geometry type: {type(geometry)}")


def simplify_geometry(geometry, tolerance: float = 0.001) -> Any:
    """Simplify geometry while preserving topology."""
    try:
        if isinstance(geometry, (Polygon, MultiPolygon)):
            return preserve_topology(geometry, tolerance)
        return geometry
    except Exception as e:
        logger.warning(f"Failed to simplify geometry: {e}")
        return geometry


def validate_and_fix_geometry(geometry) -> Any:
    """Validate and fix invalid geometries."""
    try:
        if not geometry.is_valid:
            logger.info("Invalid geometry detected, attempting to fix")
            geometry = make_valid(geometry)
        return geometry
    except Exception as e:
        logger.warning(f"Failed to validate/fix geometry: {e}")
        return geometry


def generate_convex_hull(file_bounds: List[Dict[str, float]]) -> Polygon:
    """Generate convex hull from file bounds."""
    points = []
    
    for bounds in file_bounds:
        # Add all four corners of each file's bounding box
        min_lon = bounds.get("min_lon", 0)
        max_lon = bounds.get("max_lon", 0)
        min_lat = bounds.get("min_lat", 0)
        max_lat = bounds.get("max_lat", 0)
        
        points.extend([
            Point(min_lon, min_lat),
            Point(max_lon, min_lat),
            Point(max_lon, max_lat),
            Point(min_lon, max_lat)
        ])
    
    if len(points) < 3:
        raise ValueError("Insufficient points to generate convex hull")
    
    # Create MultiPoint and get convex hull
    from shapely.geometry import MultiPoint
    multi_point = MultiPoint(points)
    return multi_point.convex_hull


def generate_union_geometry(file_bounds: List[Dict[str, float]]) -> Any:
    """Generate union geometry from file bounds (more precise than convex hull)."""
    polygons = []
    
    for bounds in file_bounds:
        min_lon = bounds.get("min_lon", 0)
        max_lon = bounds.get("max_lon", 0)
        min_lat = bounds.get("min_lat", 0)
        max_lat = bounds.get("max_lat", 0)
        
        polygon = bounds_to_polygon(min_lon, min_lat, max_lon, max_lat)
        polygons.append(polygon)
    
    if not polygons:
        raise ValueError("No valid polygons to union")
    
    # Union all polygons
    union_geom = unary_union(polygons)
    return validate_and_fix_geometry(union_geom)


def calculate_geometry_bounds(geometry) -> Tuple[float, float, float, float]:
    """Calculate bounding box from geometry."""
    bounds = geometry.bounds
    return bounds[0], bounds[1], bounds[2], bounds[3]  # min_lon, min_lat, max_lon, max_lat


def get_zoom_level_tolerance(zoom_level: int) -> float:
    """Get appropriate simplification tolerance based on zoom level."""
    # More aggressive simplification for lower zoom levels
    if zoom_level <= 6:
        return 0.01  # ~1km at equator
    elif zoom_level <= 8:
        return 0.005  # ~500m at equator
    elif zoom_level <= 10:
        return 0.002  # ~200m at equator
    else:
        return 0.0005  # ~50m at equator


def generate_campaign_boundary(
    file_bounds: List[Dict[str, float]], 
    method: str = "union",
    zoom_level: Optional[int] = None,
    simplify: bool = True
) -> Dict[str, Any]:
    """
    Generate campaign boundary using specified method.
    
    Args:
        file_bounds: List of file bounding boxes
        method: "union" (precise) or "convex_hull" (simplified)
        zoom_level: Optional zoom level for simplification
        simplify: Whether to apply simplification
    
    Returns:
        GeoJSON geometry dict
    """
    try:
        if not file_bounds:
            raise ValueError("No file bounds provided")
        
        # Generate geometry based on method
        if method == "convex_hull":
            geometry = generate_convex_hull(file_bounds)
        else:  # default to union
            geometry = generate_union_geometry(file_bounds)
        
        # Apply simplification if requested
        if simplify and zoom_level is not None:
            tolerance = get_zoom_level_tolerance(zoom_level)
            geometry = simplify_geometry(geometry, tolerance)
        
        # Convert to GeoJSON
        return polygons_to_geojson(geometry)
        
    except Exception as e:
        logger.error(f"Failed to generate campaign boundary: {e}")
        
        # Fallback: create simple bounding box from all file bounds
        if file_bounds:
            min_lon = min(bounds.get("min_lon", 0) for bounds in file_bounds)
            max_lon = max(bounds.get("max_lon", 0) for bounds in file_bounds)
            min_lat = min(bounds.get("min_lat", 0) for bounds in file_bounds)
            max_lat = max(bounds.get("max_lat", 0) for bounds in file_bounds)
            
            fallback_polygon = bounds_to_polygon(min_lon, min_lat, max_lon, max_lat)
            return polygons_to_geojson(fallback_polygon)
        
        raise


def validate_geojson_geometry(geojson_dict: Dict[str, Any]) -> bool:
    """Validate GeoJSON geometry structure."""
    try:
        # Use geojson library for validation
        geometry = geojson.loads(geojson.dumps(geojson_dict))
        return geometry.is_valid
    except Exception as e:
        logger.warning(f"GeoJSON validation failed: {e}")
        return False


def calculate_geometry_area(geometry) -> float:
    """Calculate geometry area in square degrees."""
    try:
        if hasattr(geometry, 'area'):
            return geometry.area
        return 0.0
    except Exception as e:
        logger.warning(f"Failed to calculate geometry area: {e}")
        return 0.0


def geometry_contains_point(geometry, lon: float, lat: float) -> bool:
    """Check if geometry contains a point."""
    try:
        point = Point(lon, lat)
        return geometry.contains(point)
    except Exception as e:
        logger.warning(f"Failed to check point containment: {e}")
        return False


def geometries_intersect(geom1, geom2) -> bool:
    """Check if two geometries intersect."""
    try:
        return geom1.intersects(geom2)
    except Exception as e:
        logger.warning(f"Failed to check geometry intersection: {e}")
        return False