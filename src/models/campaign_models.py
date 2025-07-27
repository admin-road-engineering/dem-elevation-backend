"""Campaign data models for survey campaign visualization."""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Union
from datetime import datetime
from enum import Enum


class DataType(str, Enum):
    """Campaign data types."""
    LIDAR = "LiDAR"
    PHOTOGRAMMETRY = "Photogrammetry" 
    SRTM = "SRTM"


class Provider(str, Enum):
    """Data providers."""
    ELVIS = "Elvis"
    GEOSCIENCE_AUSTRALIA = "Geoscience Australia"


class Bounds(BaseModel):
    """Geographic bounds."""
    min_lat: float = Field(..., description="Minimum latitude")
    max_lat: float = Field(..., description="Maximum latitude")
    min_lon: float = Field(..., description="Minimum longitude")
    max_lon: float = Field(..., description="Maximum longitude")


class GeoJSONGeometry(BaseModel):
    """GeoJSON geometry representation."""
    type: str = Field(..., description="Geometry type")
    coordinates: List[Union[List[List[float]], List[List[List[float]]]]] = Field(..., description="Geometry coordinates")


class CampaignMetadata(BaseModel):
    """Campaign metadata."""
    capture_method: str = Field(..., description="Data capture method")
    vertical_datum: str = Field(..., description="Vertical datum reference")


class CampaignFile(BaseModel):
    """Individual campaign file information."""
    key: str = Field(..., description="S3 key or file path")
    filename: str = Field(..., description="File name")
    bounds: Bounds = Field(..., description="File geographic bounds")


class CampaignData(BaseModel):
    """Survey campaign data model."""
    id: str = Field(..., description="Campaign identifier")
    name: str = Field(..., description="Campaign display name")
    provider: Provider = Field(..., description="Data provider")
    data_type: DataType = Field(..., description="Data capture type")
    resolution_m: float = Field(..., description="Data resolution in meters")
    
    # Geographic representation
    bounds: Bounds = Field(..., description="Campaign bounding box")
    geometry: Optional[GeoJSONGeometry] = Field(None, description="Precise campaign boundaries")
    
    # Temporal data
    start_date: Optional[str] = Field(None, description="Campaign start date (ISO 8601)")
    end_date: Optional[str] = Field(None, description="Campaign end date (ISO 8601)")
    
    # Metadata
    geographic_region: str = Field(..., description="Geographic region identifier")
    file_count: int = Field(..., description="Number of files in campaign")
    accuracy: Optional[str] = Field(None, description="Data accuracy specification")
    campaign_year: Optional[str] = Field(None, description="Campaign collection year")
    
    metadata: CampaignMetadata = Field(..., description="Additional metadata")
    files: Optional[List[CampaignFile]] = Field(None, description="Campaign files list")


class CampaignFilters(BaseModel):
    """Campaign filtering parameters."""
    data_types: Optional[List[DataType]] = Field(None, description="Filter by data types")
    min_resolution: Optional[float] = Field(None, description="Minimum resolution in meters")
    max_resolution: Optional[float] = Field(None, description="Maximum resolution in meters")
    providers: Optional[List[Provider]] = Field(None, description="Filter by providers")
    regions: Optional[List[str]] = Field(None, description="Filter by geographic regions")
    date_range: Optional[Dict[str, str]] = Field(None, description="Date range filter")


class CampaignQuery(BaseModel):
    """Campaign query parameters."""
    bbox: Optional[Bounds] = Field(None, description="Bounding box filter")
    filters: Optional[CampaignFilters] = Field(None, description="Additional filters")
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(50, ge=1, le=500, description="Items per page")
    include_files: bool = Field(False, description="Include file details")
    include_geometry: bool = Field(False, description="Include GeoJSON geometry")


class CampaignResponse(BaseModel):
    """Campaign API response."""
    campaigns: List[CampaignData] = Field(..., description="Campaign data")
    total_count: int = Field(..., description="Total campaigns matching filters")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    has_next: bool = Field(..., description="More pages available")


class CampaignCluster(BaseModel):
    """Campaign cluster for performance optimization."""
    id: str = Field(..., description="Cluster identifier")
    center_lat: float = Field(..., description="Cluster center latitude")
    center_lon: float = Field(..., description="Cluster center longitude")
    campaign_count: int = Field(..., description="Number of campaigns in cluster")
    bounds: Bounds = Field(..., description="Cluster bounding box")
    zoom_level: int = Field(..., description="Optimal zoom level for cluster")


class CampaignClusterResponse(BaseModel):
    """Campaign cluster response."""
    clusters: List[CampaignCluster] = Field(..., description="Campaign clusters")
    zoom_level: int = Field(..., description="Current zoom level")
    total_campaigns: int = Field(..., description="Total campaigns in view")