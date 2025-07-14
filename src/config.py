from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, Any, Optional
import os

class DEMSource(BaseModel):
    path: str
    crs: Optional[str] = None  # Optional explicit CRS, prefer reading from file metadata
    layer: Optional[str] = None  # For geodatabases: specific layer name to use
    description: Optional[str] = None  # Optional description of the data source

    class Config:
        extra = "allow"  # Allow additional fields for future extensibility

class Settings(BaseSettings):
    DEM_SOURCES: Dict[str, Dict[str, Any]]  # Changed to use raw dict for backward compatibility
    DEFAULT_DEM_ID: Optional[str] = None  # Optional default DEM source ID
    
    # Geodatabase-specific settings
    GDB_AUTO_DISCOVER: bool = Field(default=True, description="Automatically discover raster layers in geodatabases")
    GDB_PREFERRED_DRIVERS: list = Field(default=["OpenFileGDB", "FileGDB"], description="Preferred drivers for geodatabase access")
    
    # Performance settings
    CACHE_SIZE_LIMIT: int = Field(default=10, description="Maximum number of datasets to keep in cache")
    
    # GDAL Error Handling
    SUPPRESS_GDAL_ERRORS: bool = Field(default=True, description="Suppress non-critical GDAL errors from log output")
    GDAL_LOG_LEVEL: str = Field(default="ERROR", description="GDAL logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL")
    
    # AWS S3 Configuration
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_S3_BUCKET_NAME: Optional[str] = None
    
    # New S3 bucket for high-resolution data
    AWS_S3_BUCKET_NAME_HIGH_RES: Optional[str] = None
    
    # Source selection settings
    AUTO_SELECT_BEST_SOURCE: bool = Field(default=True, description="Automatically select the best available source for each location")
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

def get_settings():
    """Dependency for getting settings."""
    settings = Settings()
    
    # Set AWS environment variables if provided in settings
    if settings.AWS_ACCESS_KEY_ID:
        os.environ['AWS_ACCESS_KEY_ID'] = settings.AWS_ACCESS_KEY_ID
    if settings.AWS_SECRET_ACCESS_KEY:
        os.environ['AWS_SECRET_ACCESS_KEY'] = settings.AWS_SECRET_ACCESS_KEY
    if settings.AWS_S3_BUCKET_NAME:
        os.environ['AWS_S3_BUCKET_NAME'] = settings.AWS_S3_BUCKET_NAME
    
    return settings 