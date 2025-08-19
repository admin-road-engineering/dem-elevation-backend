"""
Unified WGS84 Spatial Models - Gemini Architectural Solution

Implements Option 1: Standardize on WGS84 bounds with native_crs metadata
This creates a truly country-agnostic architecture eliminating mixed bounds formats.

Schema Version 2.0 - WGS84 Unified Standard
"""

import uuid
from datetime import datetime
from typing import List, Optional, Union, Dict, Any, Literal
from pydantic import BaseModel, Field, validator, conint


class WGS84Bounds(BaseModel):
    """WGS84 coordinate bounds - universal format for all collections"""
    min_lat: float = Field(..., ge=-90, le=90, description="Minimum latitude (degrees)")
    max_lat: float = Field(..., ge=-90, le=90, description="Maximum latitude (degrees)")
    min_lon: float = Field(..., ge=-180, le=180, description="Minimum longitude (degrees)")
    max_lon: float = Field(..., ge=-180, le=180, description="Maximum longitude (degrees)")
    
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


class FileEntry(BaseModel):
    """Individual elevation data file with metadata"""
    file: str = Field(..., description="S3 path to the file")
    filename: str = Field(..., description="Base filename")
    bounds: WGS84Bounds = Field(..., description="File coverage bounds in WGS84")
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


class BaseUnifiedCollection(BaseModel):
    """Base class for all unified elevation data collections - WGS84 standardized"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique collection identifier")
    collection_type: str = Field(..., description="Collection type discriminator")
    country: str = Field(..., min_length=2, max_length=2, description="ISO 3166-1 alpha-2 country code")
    files: List[FileEntry] = Field(..., min_items=1, description="List of elevation files")
    coverage_bounds_wgs84: WGS84Bounds = Field(..., description="Collection coverage bounds in WGS84 - UNIVERSAL FORMAT")
    native_crs: str = Field(..., description="Native coordinate reference system (e.g., EPSG:28356)")
    file_count: int = Field(..., gt=0, description="Number of files in collection")
    resolution_m: float = Field(default=1.0, gt=0, description="Resolution in meters")
    data_type: Literal["DEM", "DSM"] = Field(default="DEM", description="Digital Elevation Model type")
    metadata: CollectionMetadata = Field(..., description="Collection metadata")
    
    @validator('file_count')
    def validate_file_count(cls, v, values):
        if 'files' in values and v != len(values['files']):
            raise ValueError('file_count must match length of files list')
        return v


class AustralianUnifiedCollection(BaseUnifiedCollection):
    """Australian elevation data - WGS84 unified format"""
    collection_type: Literal["australian_utm_zone"] = "australian_utm_zone"
    country: Literal["AU"] = "AU"
    utm_zone: conint(ge=1, le=60) = Field(..., description="UTM zone number")
    state: str = Field(..., description="Australian state/territory")
    region: Optional[str] = Field(None, description="Specific region within state")
    campaign_name: str = Field(..., description="Campaign name")
    survey_year: Optional[int] = Field(None, description="Survey campaign year")


class NewZealandUnifiedCollection(BaseUnifiedCollection):
    """New Zealand elevation data - WGS84 unified format"""
    collection_type: Literal["new_zealand_campaign"] = "new_zealand_campaign"
    country: Literal["NZ"] = "NZ"
    region: str = Field(..., description="Geographic region")
    survey_name: str = Field(..., description="Survey campaign name")
    survey_years: List[int] = Field(..., min_items=1, description="Years covered by survey")


# Discriminated union for all unified collection types
UnifiedDataCollection = Union[AustralianUnifiedCollection, NewZealandUnifiedCollection]


class UnifiedSchemaMetadata(BaseModel):
    """Metadata about the unified spatial index - Schema Version 2.0"""
    generated_at: Union[datetime, str] = Field(default_factory=datetime.now, description="Generation timestamp")
    generator: str = Field(default="unified_wgs84_standardization_v2", description="Generator name")
    total_collections: int = Field(..., ge=0, description="Total number of collections")
    total_files: int = Field(..., ge=0, description="Total number of files")
    countries: List[str] = Field(..., min_items=1, description="Countries represented")
    collection_types: List[str] = Field(..., min_items=1, description="Collection types present")
    bounds_format: Literal["wgs84_unified"] = "wgs84_unified"
    schema_version: Literal["2.0"] = "2.0"
    note: Optional[str] = Field(None, description="Additional notes about the index")


class UnifiedWGS84SpatialIndex(BaseModel):
    """Top-level unified spatial index with WGS84 standardization - Schema Version 2.0"""
    version: Optional[Literal["2.0"]] = "2.0"
    # Support both new and legacy schema formats
    schema_metadata: Optional[UnifiedSchemaMetadata] = Field(None, description="Index metadata with version 2.0 (new format)")
    data_collections: Optional[List[UnifiedDataCollection]] = Field(None, description="List of all unified collections (new format)")
    # Legacy format support (from coordinate correction deployment)
    schema_version: Optional[str] = Field(None, description="Schema version (legacy format)")
    campaigns: Optional[Dict[str, Any]] = Field(None, description="Campaign data (legacy format)")
    generated_at: Optional[str] = Field(None, description="Generation timestamp (legacy format)")
    statistics: Optional[Dict[str, Any]] = Field(None, description="Statistics (legacy format)")
    
    class Config:
        extra = "allow"  # Allow additional fields for future enhancements
    
    def model_post_init(self, __context):
        """Convert legacy format to new format if needed"""
        try:
            self._convert_legacy_format()
        except Exception as e:
            # Log error but don't crash the service
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Legacy conversion failed: {e}", exc_info=True)
    
    def _convert_legacy_format(self):
        """Convert legacy campaigns format to data_collections format"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"Legacy conversion starting: data_collections={self.data_collections is not None}, campaigns={self.campaigns is not None}")
        
        if self.data_collections is None and self.campaigns is not None and isinstance(self.campaigns, dict):
            # Convert legacy campaigns to data_collections
            converted_collections = []
            
            for campaign_id, campaign_data in self.campaigns.items():
                try:
                    # Skip if campaign_data is None or not a dict
                    if not isinstance(campaign_data, dict):
                        continue
                        
                    # Extract files from legacy format
                    files = campaign_data.get('files', [])
                    if not isinstance(files, list):
                        continue
                        
                    converted_files = []
                    
                    for file_data in files:
                        if not isinstance(file_data, dict):
                            continue
                            
                        # Safely extract bounds
                        bounds_data = file_data.get('bounds', {})
                        if not isinstance(bounds_data, dict):
                            continue
                            
                        # Convert file format with safe defaults
                        converted_file = FileEntry(
                            file=str(file_data.get('file', '')),
                            filename=str(file_data.get('filename', '')),
                            bounds=WGS84Bounds(
                                min_lat=float(bounds_data.get('min_lat', 0)),
                                max_lat=float(bounds_data.get('max_lat', 0)),
                                min_lon=float(bounds_data.get('min_lon', 0)),
                                max_lon=float(bounds_data.get('max_lon', 0))
                            ),
                            size_mb=float(file_data.get('size_mb', 0.0)),
                            last_modified=str(file_data.get('last_modified', '')),
                            resolution=str(file_data.get('resolution', '1m')),
                            coordinate_system=str(file_data.get('utm_zone', 'WGS84')),
                            method='legacy_conversion'
                        )
                        converted_files.append(converted_file)
                    
                    if converted_files:  # Only create collection if it has files
                        # Create collection bounds from file bounds with safe handling
                        try:
                            min_lat = min(f.bounds.min_lat for f in converted_files if f.bounds)
                            max_lat = max(f.bounds.max_lat for f in converted_files if f.bounds)
                            min_lon = min(f.bounds.min_lon for f in converted_files if f.bounds)
                            max_lon = max(f.bounds.max_lon for f in converted_files if f.bounds)
                        except (ValueError, AttributeError):
                            # Skip collection if bounds calculation fails
                            continue
                        
                        # Determine country from campaign ID
                        country = "AU" if "AU" in campaign_id.upper() else "NZ"
                        
                        # Create appropriate collection type based on country
                        if country == "AU":
                            collection = AustralianUnifiedCollection(
                                id=campaign_id,
                                files=converted_files,
                                coverage_bounds_wgs84=WGS84Bounds(
                                    min_lat=min_lat,
                                    max_lat=max_lat,
                                    min_lon=min_lon,
                                    max_lon=max_lon
                                ),
                                native_crs="EPSG:28356",  # Default Australian UTM
                                file_count=len(converted_files),
                                utm_zone=56,  # Default to Zone 56 for legacy
                                state="NSW",  # Default state
                                campaign_name=campaign_id.replace('_', ' ').title(),
                                survey_year=None,
                                metadata=CollectionMetadata(
                                    source_bucket="road-engineering-elevation-data",
                                    coordinate_system="EPSG:28356"
                                )
                            )
                        else:
                            collection = NewZealandUnifiedCollection(
                                id=campaign_id,
                                files=converted_files,
                                coverage_bounds_wgs84=WGS84Bounds(
                                    min_lat=min_lat,
                                    max_lat=max_lat,
                                    min_lon=min_lon,
                                    max_lon=max_lon
                                ),
                                native_crs="EPSG:2193",  # NZGD2000 
                                file_count=len(converted_files),
                                region="Unknown",
                                survey_name=campaign_id.replace('_', ' ').title(),
                                survey_years=[2020],  # Default year
                                metadata=CollectionMetadata(
                                    source_bucket="nz-elevation",
                                    coordinate_system="EPSG:2193"
                                )
                            )
                        converted_collections.append(collection)
                        
                except Exception as e:
                    # Skip problematic collections but continue processing
                    logger.warning(f"Failed to convert campaign {campaign_id}: {e}")
                    continue
            
            # Only set converted collections if we actually converted some
            if converted_collections:
                logger.info(f"Legacy conversion successful: {len(converted_collections)} collections converted")
                self.data_collections = converted_collections
                
                # Create schema metadata from legacy data
                if self.schema_metadata is None:
                    self.schema_metadata = UnifiedSchemaMetadata(
                        generated_at=self.generated_at or datetime.now().isoformat(),
                        total_collections=len(converted_collections),
                        total_files=sum(c.file_count for c in converted_collections if c.file_count),
                        countries=list(set(c.country for c in converted_collections if c.country)),
                        collection_types=list(set(c.collection_type for c in converted_collections if c.collection_type))
                    )
                    logger.info(f"Schema metadata created: {self.schema_metadata.total_collections} collections, {self.schema_metadata.total_files} files")
            else:
                logger.warning("Legacy conversion produced no collections")
        
    def get_collections_by_country(self, country: str) -> List[UnifiedDataCollection]:
        """Get all collections for a specific country"""
        collections = self.data_collections or []
        return [c for c in collections if c.country == country]
    
    def get_collections_by_type(self, collection_type: str) -> List[UnifiedDataCollection]:
        """Get all collections of a specific type"""
        collections = self.data_collections or []
        return [c for c in collections if c.collection_type == collection_type]
    
    def get_collection_by_id(self, collection_id: str) -> Optional[UnifiedDataCollection]:
        """Get a specific collection by ID"""
        collections = self.data_collections or []
        for collection in collections:
            if collection.id == collection_id:
                return collection
        return None

    def is_point_in_collection_bounds(self, collection: UnifiedDataCollection, lat: float, lon: float) -> bool:
        """
        Universal bounds checking - works for all countries and collection types
        This eliminates the need for country-specific bounds checking logic
        """
        bounds = collection.coverage_bounds_wgs84
        return (bounds.min_lat <= lat <= bounds.max_lat and
                bounds.min_lon <= lon <= bounds.max_lon)


# Type aliases for easier imports
UnifiedCollection = UnifiedDataCollection
UnifiedIndex = UnifiedWGS84SpatialIndex