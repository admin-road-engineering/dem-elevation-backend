from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict

# Request Models
class PointRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    dem_source_id: Optional[str] = None

class Coordinate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)

class LineRequest(BaseModel):
    start_point: Coordinate
    end_point: Coordinate
    num_points: int = Field(2, ge=2)
    dem_source_id: Optional[str] = None

class PathPoint(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    id: Optional[Any] = None

class PathRequest(BaseModel):
    points: List[PathPoint]
    dem_source_id: Optional[str] = None

class PolygonBounds(BaseModel):
    """Represents a polygon area for contour data generation."""
    polygon_coordinates: List[Coordinate] = Field(..., min_items=3, description="List of coordinates defining the polygon boundary")

class ContourDataRequest(BaseModel):
    """Request model for generating contour data from native DEM points."""
    area_bounds: PolygonBounds
    max_points: int = Field(50000, ge=100, le=200000, description="Maximum number of DEM points to return (safety limit)")
    sampling_interval_m: Optional[float] = Field(None, ge=0.1, le=50.0, description="Grid sampling interval in meters. If None, uses DEM resolution (recommended)")
    minor_contour_interval_m: float = Field(1.0, ge=0.1, description="Interval for minor contour lines in meters")
    major_contour_interval_m: float = Field(5.0, ge=0.1, description="Interval for major contour lines in meters")
    dem_source_id: Optional[str] = None

# Response Models
class PointResponse(BaseModel):
    latitude: float
    longitude: float
    elevation_m: Optional[float]
    crs: str = "EPSG:4326"
    dem_source_used: str
    message: Optional[str] = None

class LinePointResponse(BaseModel):
    latitude: float
    longitude: float
    elevation_m: Optional[float]
    sequence: int
    message: Optional[str] = None

class LineResponse(BaseModel):
    points: List[LinePointResponse]
    crs: str = "EPSG:4326"
    dem_source_used: str
    message: Optional[str] = None

class PathElevationResponse(BaseModel):
    input_latitude: float
    input_longitude: float
    input_id: Optional[Any]
    elevation_m: Optional[float]
    sequence: int
    message: Optional[str] = None

class PathResponse(BaseModel):
    path_elevations: List[PathElevationResponse]
    crs: str = "EPSG:4326"
    dem_source_used: str
    message: Optional[str] = None

class DEMPoint(BaseModel):
    """Represents a native DEM point with grid coordinates."""
    latitude: float
    longitude: float
    elevation_m: Optional[float]
    x_grid_index: int = Field(description="X index in the DEM grid")
    y_grid_index: int = Field(description="Y index in the DEM grid")
    grid_resolution_m: Optional[float] = Field(None, description="Grid resolution in meters")

# New GeoJSON models for contour response
class GeoJSONGeometry(BaseModel):
    """GeoJSON geometry model."""
    type: str = Field(description="Geometry type (e.g., 'LineString')")
    coordinates: List[List[float]] = Field(description="Array of coordinate pairs [longitude, latitude]")

class GeoJSONProperties(BaseModel):
    """GeoJSON feature properties."""
    elevation: float = Field(description="Contour elevation value")
    elevation_units: str = Field(default="meters", description="Units of elevation measurement")

class GeoJSONFeature(BaseModel):
    """GeoJSON feature model."""
    type: str = Field(default="Feature", description="GeoJSON object type")
    geometry: GeoJSONGeometry = Field(description="The geometry of the feature")
    properties: GeoJSONProperties = Field(description="Properties of the feature")

class GeoJSONFeatureCollection(BaseModel):
    """GeoJSON FeatureCollection model."""
    type: str = Field(default="FeatureCollection", description="GeoJSON object type")
    features: List[GeoJSONFeature] = Field(description="Array of GeoJSON features")

class ContourStatistics(BaseModel):
    """Statistics about the generated contours."""
    total_points: int = Field(description="Total number of elevation points used")
    min_elevation: float = Field(description="Minimum elevation in the area")
    max_elevation: float = Field(description="Maximum elevation in the area")
    contour_count: int = Field(description="Number of contour lines generated")
    elevation_intervals: List[float] = Field(description="Elevation intervals used for contour generation")

class ContourDataResponse(BaseModel):
    """Response model for contour data containing GeoJSON contours."""
    success: bool = Field(default=True, description="Indicates if the request was successful")
    contours: GeoJSONFeatureCollection = Field(description="GeoJSON FeatureCollection of contour lines")
    statistics: ContourStatistics = Field(description="Statistics about the generated contours")
    area_bounds: PolygonBounds = Field(description="The polygon area that was queried")
    dem_source_used: str = Field(description="DEM source that was used")
    crs: str = "EPSG:4326"
    message: Optional[str] = None

# Keep old response model for backward compatibility if needed
class LegacyContourDataResponse(BaseModel):
    """Legacy response model for contour data containing native DEM points."""
    dem_points: List[DEMPoint] = Field(description="Native DEM points within the requested area")
    total_points: int = Field(description="Total number of points returned")
    area_bounds: PolygonBounds = Field(description="The polygon area that was queried")
    dem_source_used: str = Field(description="DEM source that was used")
    grid_info: Dict[str, Any] = Field(description="Information about the DEM grid (resolution, extent, etc.)")
    crs: str = "EPSG:4326"
    message: Optional[str] = None

# Error Models
class ErrorResponse(BaseModel):
    detail: str
    error_type: Optional[str] = None 

class DEMSourceMetadata(BaseModel):
    """Extended metadata for DEM sources with spatial bounds and priority."""
    path: str
    crs: Optional[str] = None
    layer: Optional[str] = None
    description: Optional[str] = None
    
    # New fields for priority-based selection
    resolution_m: Optional[float] = None  # Spatial resolution in meters
    priority: Optional[int] = None        # Manual priority (1=highest)
    bounds: Optional[Dict[str, float]] = None  # {"west": x, "south": y, "east": x, "north": y}
    data_source: Optional[str] = None     # "LiDAR", "Photogrammetry", "SRTM", etc.
    year: Optional[int] = None            # Year of data collection
    region: Optional[str] = None          # Region identifier
    
    class Config:
        extra = "allow"

class SourceSelectionRequest(BaseModel):
    """Request for automatic DEM source selection."""
    latitude: float
    longitude: float
    prefer_high_resolution: bool = True
    max_resolution_m: Optional[float] = None  # Maximum acceptable resolution
    
class SourceSelectionResponse(BaseModel):
    """Response with selected DEM source information."""
    selected_source_id: str
    selected_source_info: Dict[str, Any]
    available_sources: List[str]
    selection_reason: str 