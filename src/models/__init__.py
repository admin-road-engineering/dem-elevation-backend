"""Models package for DEM Backend."""

from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict

# Essential models needed by endpoints (copied to avoid circular imports)

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

class ContourDataRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    width_km: float = Field(1.0, gt=0, le=50)
    height_km: float = Field(1.0, gt=0, le=50)
    contour_interval: float = Field(10.0, gt=0)
    dem_source_id: Optional[str] = None

# Response models
class PointResponse(BaseModel):
    elevation: Optional[float]
    latitude: float
    longitude: float
    dem_source_used: Optional[str]
    message: Optional[str] = None

class LineResponse(BaseModel):
    points: List[PointResponse]
    total_points: int
    message: Optional[str] = None

class PathResponse(BaseModel):
    points: List[PointResponse]
    total_points: int
    message: Optional[str] = None

# Enhanced response models with structured resolution fields (Phase 2C)
class EnhancedPointResponse(BaseModel):
    elevation: Optional[float]
    latitude: float
    longitude: float
    dem_source_used: Optional[str]
    message: Optional[str] = None
    # Enhanced structured fields
    resolution: Optional[float] = None
    grid_resolution_m: Optional[float] = None
    data_type: Optional[str] = None
    accuracy: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class EnhancedLineResponse(BaseModel):
    points: List[EnhancedPointResponse]
    total_points: int
    message: Optional[str] = None

class EnhancedPathResponse(BaseModel):
    points: List[EnhancedPointResponse]
    total_points: int
    message: Optional[str] = None

class ContourDataResponse(BaseModel):
    contours: List[List[List[float]]]
    bounds: Dict[str, float]
    contour_interval: float
    message: Optional[str] = None

class LegacyContourDataResponse(BaseModel):
    success: bool
    contour_data: Optional[Any] = None
    error_message: Optional[str] = None

class GeoJSONFeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: List[Dict[str, Any]]

class ContourStatistics(BaseModel):
    total_lines: int
    total_points: int
    elevation_range: Dict[str, float]

class DEMPoint(BaseModel):
    lat: float
    lon: float
    elevation: Optional[float] = None
    data_source: Optional[str] = None

class ErrorResponse(BaseModel):
    error: str
    details: Optional[str] = None

class SourceSelectionRequest(BaseModel):
    latitude: float
    longitude: float

class SourceSelectionResponse(BaseModel):
    selected_source: Optional[str]
    source_type: Optional[str]
    message: Optional[str] = None

# Additional models for compatibility
class PointsRequest(BaseModel):
    points: List[Dict[str, float]]

class StandardResponse(BaseModel):
    results: List[DEMPoint]
    metadata: Dict[str, Any]

class ElevationRequest(BaseModel):
    latitude: float
    longitude: float

class ElevationResponse(BaseModel):
    elevation_m: Optional[float]
    dem_source_used: str
    message: Optional[str] = None

class ElevationResult(BaseModel):
    elevation_m: Optional[float]
    dem_source_used: str
    message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class BatchElevationRequest(BaseModel):
    points: List[ElevationRequest]

class BatchElevationResponse(BaseModel):
    results: List[ElevationResult]

class ContourRequest(BaseModel):
    latitude: float
    longitude: float
    radius_km: float = 1.0

class ContourResponse(BaseModel):
    contours: List[Any]

class DEMSourceMetadata(BaseModel):
    path: str
    crs: Optional[str] = None
    layer: Optional[str] = None
    description: Optional[str] = None

# Standardized models for GPXZ-style API
class StandardCoordinate(BaseModel):
    """Standardized coordinate model for new API endpoints."""
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)

class PointsRequest(BaseModel):
    """Request model for batch points endpoint."""
    points: List[StandardCoordinate]
    source: Optional[str] = None

class LineRequest_Standard(BaseModel):
    """Request model for line sampling endpoint."""
    start: StandardCoordinate
    end: StandardCoordinate
    num_points: int = Field(..., ge=2, le=1000)
    source: Optional[str] = None

class PathRequest_Standard(BaseModel):
    """Request model for complex path sampling endpoint."""
    path: List[StandardCoordinate] = Field(..., min_items=2)
    num_points: int = Field(..., ge=2, le=1000)
    interpolation: str = Field(default="geodesic", pattern="^(geodesic|linear)$")
    source: Optional[str] = None

class StandardElevationResult(BaseModel):
    """Standardized elevation result for new API endpoints."""
    lat: float
    lon: float
    elevation: Optional[float]
    data_source: str

class StandardMetadata(BaseModel):
    """Standardized metadata for new API responses."""
    total_points: int
    successful_points: int
    crs: str = "EPSG:4326"
    units: str = "meters"

class StandardErrorDetail(BaseModel):
    """Standardized error detail structure."""
    code: int = Field(description="HTTP status code")
    message: str = Field(description="Human-readable error message")
    details: Optional[str] = Field(None, description="Additional error details")
    timestamp: str = Field(description="ISO 8601 timestamp of the error")

class StandardErrorResponse(BaseModel):
    """Standardized error response format."""
    status: str = "ERROR"
    error: StandardErrorDetail

# Additional frontend models
class PolygonBounds(BaseModel):
    """Represents a polygon area for contour data generation."""
    polygon_coordinates: List[Coordinate] = Field(..., min_items=3, description="List of coordinates defining the polygon boundary")

class FrontendContourDataRequest(BaseModel):
    """Request model matching frontend requirements for contour data."""
    area_bounds: PolygonBounds
    grid_resolution_m: float = Field(10.0, ge=1.0, le=50.0, description="Grid resolution in meters")
    source: Optional[str] = None

class FrontendContourDataResponse(BaseModel):
    """Response model matching frontend requirements for contour data."""
    status: str = "OK"
    dem_points: List[DEMPoint] = Field(description="Grid elevation points for contour generation")
    total_points: int = Field(description="Total number of points returned")
    dem_source_used: str = Field(description="DEM source that was used")
    grid_info: Dict[str, Any] = Field(description="Grid metadata including dimensions and bounds")
    crs: str = "EPSG:4326"
    message: str = Field(description="Success message")