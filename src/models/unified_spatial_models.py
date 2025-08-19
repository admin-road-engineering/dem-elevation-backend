"""
Unified Spatial Index Models with Discriminated Unions
Implements Gemini's recommended schema for type-safe, extensible data collections
"""
from pydantic import BaseModel, Field, conint, validator
from typing import Dict, List, Optional, Literal, Union, Any
from datetime import datetime
import uuid

class WGS84Bounds(BaseModel):
    """Geographic bounding box in WGS84 coordinates"""
    min_lat: float = Field(..., ge=-90, le=90, description="Minimum latitude")
    max_lat: float = Field(..., ge=-90, le=90, description="Maximum latitude") 
    min_lon: float = Field(..., ge=-180, le=180, description="Minimum longitude")
    max_lon: float = Field(..., ge=-180, le=180, description="Maximum longitude")
    
    @validator('max_lat')
    def validate_lat_order(cls, v, values):
        if 'min_lat' in values and v < values['min_lat']:
            raise ValueError('max_lat must be >= min_lat')
        return v
    
    @validator('max_lon')
    def validate_lon_order(cls, v, values):
        if 'min_lon' in values and v < values['min_lon']:
            raise ValueError('max_lon must be >= min_lon')
        return v

class UTMBounds(BaseModel):
    """Projected bounding box in UTM coordinates (meters)"""
    min_x: float = Field(..., description="Minimum easting (meters)")
    max_x: float = Field(..., description="Maximum easting (meters)")
    min_y: float = Field(..., description="Minimum northing (meters)")
    max_y: float = Field(..., description="Maximum northing (meters)")
    
    @validator('max_x')
    def validate_x_order(cls, v, values):
        if 'min_x' in values and v < values['min_x']:
            raise ValueError('max_x must be >= min_x')
        return v
    
    @validator('max_y')
    def validate_y_order(cls, v, values):
        if 'min_y' in values and v < values['min_y']:
            raise ValueError('max_y must be >= min_y')
        return v

# Union type for flexible bounds handling
CoverageBounds = Union[WGS84Bounds, UTMBounds]

class FileEntry(BaseModel):
    """Individual elevation data file with metadata"""
    file: str = Field(..., description="S3 path to the file")
    filename: str = Field(..., description="Base filename")
    bounds: Union[WGS84Bounds, UTMBounds] = Field(..., description="File coverage bounds")
    size_mb: float = Field(..., ge=0, description="File size in megabytes")
    last_modified: str = Field(..., description="ISO format timestamp")
    resolution: str = Field(..., description="Spatial resolution (e.g., '1m')")
    coordinate_system: str = Field(..., description="Coordinate reference system")
    method: str = Field(..., description="Bounds extraction method")

class CollectionMetadata(BaseModel):
    """Additional metadata for collections"""
    source_bucket: str = Field(..., description="S3 bucket containing the data")
    coordinate_system: str = Field(..., description="Native coordinate system")
    original_path: Optional[str] = Field(None, description="Original data path")
    original_campaign: Optional[str] = Field(None, description="Original campaign name")
    performance_note: Optional[str] = Field(None, description="Performance characteristics")
    note: Optional[str] = Field(None, description="Additional notes")

class BaseCollection(BaseModel):
    """Base class for all elevation data collections"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique collection identifier")
    country: str = Field(..., min_length=2, max_length=2, description="ISO 3166-1 alpha-2 country code")
    files: List[FileEntry] = Field(..., min_items=1, description="List of elevation files")
    coverage_bounds: CoverageBounds = Field(..., description="Overall collection coverage")
    file_count: int = Field(..., gt=0, description="Number of files in collection")
    metadata: CollectionMetadata = Field(..., description="Collection metadata")
    
    @validator('file_count')
    def validate_file_count(cls, v, values):
        if 'files' in values and v != len(values['files']):
            raise ValueError('file_count must match length of files list')
        return v

class AustralianUTMCollection(BaseCollection):
    """Australian elevation data organized by UTM zones"""
    collection_type: Literal["australian_utm_zone"] = "australian_utm_zone"
    country: Literal["AU"] = "AU"
    utm_zone: conint(ge=1, le=60) = Field(..., description="UTM zone number")
    state: str = Field(..., description="Australian state/territory")
    region: Optional[str] = Field(None, description="Specific region within state")
    campaign_name: str = Field(..., description="Campaign name")
    survey_year: Optional[int] = Field(None, description="Survey campaign year")
    campaign_year: Optional[int] = Field(None, description="Survey campaign year (legacy)")
    data_type: Literal["DEM", "DSM"] = Field(default="DEM", description="Digital Elevation Model type")
    resolution_m: float = Field(default=1.0, gt=0, description="Resolution in meters")
    epsg: str = Field(..., description="EPSG code for CRS-aware spatial queries")
    bounds_transformation: Optional[Dict[str, Any]] = Field(None, description="Bounds transformation metadata")

class NewZealandCampaignCollection(BaseCollection):
    """New Zealand elevation data organized by survey campaigns"""
    collection_type: Literal["new_zealand_campaign"] = "new_zealand_campaign"
    country: Literal["NZ"] = "NZ"
    region: str = Field(..., description="Geographic region")
    survey_name: str = Field(..., description="Survey campaign name")
    survey_years: List[int] = Field(..., min_items=1, description="Years covered by survey")
    data_type: Literal["DEM", "DSM", "UNKNOWN"] = Field(default="DEM", description="Data type")
    resolution_m: float = Field(default=1.0, gt=0, description="Resolution in meters")

# Discriminated union for all collection types
DataCollection = Union[AustralianUTMCollection, NewZealandCampaignCollection]

class SchemaMetadata(BaseModel):
    """Metadata about the unified spatial index"""
    generated_at: Union[datetime, str] = Field(default_factory=datetime.now, description="Generation timestamp")
    generator: str = Field(default="unified_spatial_index_v2", description="Generator name")
    total_collections: int = Field(..., ge=0, description="Total number of collections")
    total_files: int = Field(..., ge=0, description="Total number of files")
    countries: List[str] = Field(..., min_items=1, description="Countries represented")
    collection_types: List[str] = Field(..., min_items=1, description="Collection types present")
    note: Optional[str] = Field(None, description="Additional notes about the index")

class UnifiedSpatialIndex(BaseModel):
    """Top-level unified spatial index with discriminated unions"""
    version: Optional[Literal["2.0"]] = "2.0"
    # Support both new and legacy schema formats
    schema_metadata: Optional[SchemaMetadata] = Field(None, description="Index metadata (new format)")
    data_collections: Optional[List[DataCollection]] = Field(None, description="List of all data collections (new format)")
    # Legacy format support (from coordinate correction deployment)
    schema_version: Optional[str] = Field(None, description="Schema version (legacy format)")
    campaigns: Optional[Dict[str, Any]] = Field(None, description="Campaign data (legacy format)")
    transformation_metadata: Optional[Dict[str, Any]] = Field(None, description="Bounds transformation metadata")
    
    class Config:
        extra = "allow"  # Allow additional fields for transformation metadata
        
    def get_collections_by_country(self, country: str) -> List[DataCollection]:
        """Get all collections for a specific country"""
        collections = self.data_collections or []
        return [c for c in collections if c.country == country]
    
    def get_collections_by_type(self, collection_type: str) -> List[DataCollection]:
        """Get all collections of a specific type"""
        collections = self.data_collections or []
        return [c for c in collections if c.collection_type == collection_type]
    
    def get_collection_by_id(self, collection_id: str) -> Optional[DataCollection]:
        """Get a specific collection by ID"""
        collections = self.data_collections or []
        for collection in collections:
            if collection.id == collection_id:
                return collection
        return None

# Type aliases for easier imports
AustralianCollection = AustralianUTMCollection
NewZealandCollection = NewZealandCampaignCollection