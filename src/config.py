from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, Any, Optional, List
import os
import json
from pathlib import Path

class DEMSource(BaseModel):
    path: str
    crs: Optional[str] = None  # Optional explicit CRS, prefer reading from file metadata
    layer: Optional[str] = None  # For geodatabases: specific layer name to use
    description: Optional[str] = None  # Optional description of the data source

    class Config:
        extra = "allow"  # Allow additional fields for future extensibility

def load_dem_sources_from_file(base_dir: str = ".") -> Dict[str, Dict[str, Any]]:
    """
    Load DEM sources from external configuration file as single source of truth.
    
    This function now uses dem_sources.json as the definitive source configuration,
    eliminating programmatic hardcoding of API sources for better maintainability.
    """
    config_file = Path(base_dir) / "config" / "dem_sources.json"
    
    if not config_file.exists():
        # Fallback to minimal API sources if config file doesn't exist (Railway compatible)
        return {
            "gpxz_api": {
                "path": "api://gpxz",
                "layer": None,
                "crs": None,
                "description": "GPXZ API global coverage",
                "priority": 2,
                "source_type": "api"
            },
            "google_elevation": {
                "path": "api://google",
                "layer": None,
                "crs": None,
                "description": "Google Elevation API fallback",
                "priority": 3,
                "source_type": "api"
            }
        }
    
    try:
        with open(config_file, 'r') as f:
            data = json.load(f)
        
        # Convert the comprehensive JSON structure to the format expected by current system
        sources = {}
        
        for source_config in data.get("elevation_sources", []):
            # Skip disabled sources
            if not source_config.get("enabled", True):
                continue
                
            source_id = source_config["id"]
            sources[source_id] = {
                "path": source_config["path"],
                "layer": source_config.get("layer"),
                "crs": source_config.get("crs"),
                "description": source_config.get("name", source_config.get("description", "")),
                "priority": source_config.get("priority", 3),
                "source_type": source_config.get("source_type", "file"),
                "bounds": source_config.get("bounds"),
                "resolution_m": source_config.get("resolution_m"),
                "data_type": source_config.get("data_type"),
                "provider": source_config.get("provider"),
                "cost_per_query": source_config.get("cost_per_query", 0.0),
                "accuracy": source_config.get("accuracy")
            }
        
        # dem_sources.json is now the single source of truth - no programmatic additions needed
        
        return sources
        
    except Exception as e:
        # Return minimal config on error - only API sources for Railway
        return {
            "gpxz_api": {"path": "api://gpxz", "priority": 2, "description": "GPXZ API fallback"},
            "google_elevation": {"path": "api://google", "priority": 3, "description": "Google Elevation API fallback"}
        }

class Settings(BaseSettings):
    # Load DEM sources from external file instead of environment
    _dem_sources_cache: Optional[Dict[str, Dict[str, Any]]] = None
    DEFAULT_DEM_ID: Optional[str] = None  # Optional default DEM source ID
    BASE_DIR: str = Field(default=".", description="Base directory for the application")
    
    # Multi-source environment settings
    USE_S3_SOURCES: bool = Field(default=False, description="Enable S3-based DEM sources")
    USE_API_SOURCES: bool = Field(default=False, description="Enable external API sources")
    
    # Geodatabase-specific settings
    GDB_AUTO_DISCOVER: bool = Field(default=True, description="Automatically discover raster layers in geodatabases")
    GDB_PREFERRED_DRIVERS: list = Field(default=["OpenFileGDB", "FileGDB"], description="Preferred drivers for geodatabase access")
    
    # Performance settings
    CACHE_SIZE_LIMIT: int = Field(default=10, description="Maximum number of datasets to keep in cache")
    DATASET_CACHE_SIZE: int = Field(default=10, description="Maximum number of datasets to keep in memory cache")
    MAX_WORKER_THREADS: int = Field(default=10, description="Maximum number of worker threads for async operations")
    
    # GDAL Error Handling
    SUPPRESS_GDAL_ERRORS: bool = Field(default=True, description="Suppress non-critical GDAL errors from log output")
    GDAL_LOG_LEVEL: str = Field(default="ERROR", description="GDAL logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL")
    
    # AWS S3 Configuration
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_S3_BUCKET_NAME: Optional[str] = None
    AWS_DEFAULT_REGION: str = Field(default="ap-southeast-2", description="Default AWS region")
    
    # New S3 bucket for high-resolution data
    AWS_S3_BUCKET_NAME_HIGH_RES: Optional[str] = None
    
    # GPXZ.io API Configuration
    GPXZ_API_KEY: Optional[str] = None
    GPXZ_DAILY_LIMIT: int = Field(default=100, description="Daily request limit for GPXZ API")
    GPXZ_RATE_LIMIT: int = Field(default=1, description="Requests per second limit for GPXZ API")
    
    # Google Elevation API Configuration
    GOOGLE_ELEVATION_API_KEY: Optional[str] = None
    
    # Source selection settings
    AUTO_SELECT_BEST_SOURCE: bool = Field(default=True, description="Automatically select the best available source for each location")
    
    # Server settings
    HOST: str = Field(default="0.0.0.0", description="Server host")
    PORT: int = Field(default=8001, description="Server port")
    
    # Authentication settings
    SUPABASE_JWT_SECRET: Optional[str] = None
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT algorithm for token verification")
    JWT_AUDIENCE: str = Field(default="authenticated", description="JWT audience for token verification")
    REQUIRE_AUTH: bool = Field(default=False, description="Whether to require authentication for protected endpoints")
    
    # CORS and main platform integration
    CORS_ORIGINS: str = Field(default="http://localhost:3001,http://localhost:5173,http://localhost:5174", description="Comma-separated list of allowed CORS origins")
    MAIN_BACKEND_URL: str = Field(default="http://localhost:3001", description="Main platform backend URL")
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    @property
    def DEM_SOURCES(self) -> Dict[str, Dict[str, Any]]:
        """Load DEM sources from external configuration file"""
        if self._dem_sources_cache is None:
            self._dem_sources_cache = load_dem_sources_from_file(self.BASE_DIR)
        return self._dem_sources_cache

def runtime_config_check(settings: Settings) -> Dict[str, Any]:
    """Runtime configuration check with fallback capabilities"""
    import logging
    logger = logging.getLogger(__name__)
    
    status = {
        "overall_health": "healthy",
        "warnings": [],
        "fallbacks_active": [],
        "sources_available": {
            "local": 0,
            "s3": 0, 
            "api": 0
        }
    }
    
    # Check API availability at runtime
    if settings.USE_API_SOURCES:
        if not settings.GPXZ_API_KEY:
            status["warnings"].append("GPXZ_API_KEY missing - API sources disabled")
            status["fallbacks_active"].append("api_to_local")
        else:
            status["sources_available"]["api"] = 1
    
    # Check S3 availability at runtime  
    if settings.USE_S3_SOURCES:
        s3_sources = [src for src in settings.DEM_SOURCES.values() 
                     if src.get('path', '').startswith('s3://')]
        if s3_sources:
            # Check credentials for private buckets
            private_sources = [src for src in s3_sources 
                             if 'road-engineering-elevation-data' in src.get('path', '')]
            if private_sources and (not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY):
                status["warnings"].append("AWS credentials missing - private S3 sources unavailable")
                status["fallbacks_active"].append("private_s3_to_public")
            
            status["sources_available"]["s3"] = len(s3_sources)
    
    # Check local sources
    local_sources = [src for src in settings.DEM_SOURCES.values() 
                    if not src.get('path', '').startswith(('s3://', 'api://'))]
    status["sources_available"]["local"] = len(local_sources)
    
    # Determine overall health
    total_sources = sum(status["sources_available"].values())
    if total_sources == 0:
        status["overall_health"] = "critical"
        status["warnings"].append("No elevation sources available")
    elif len(status["warnings"]) > 0:
        status["overall_health"] = "degraded"
    
    # Log runtime status
    logger.info(
        "Runtime configuration check completed",
        extra={
            "config_health": status["overall_health"],
            "sources_local": status["sources_available"]["local"],
            "sources_s3": status["sources_available"]["s3"],
            "sources_api": status["sources_available"]["api"],
            "warnings_count": len(status["warnings"]),
            "fallbacks_count": len(status["fallbacks_active"])
        }
    )
    
    return status

def validate_environment_configuration(settings: Settings) -> None:
    """
    Validate configuration for the current environment mode.
    
    Performs comprehensive validation of environment variables and configuration.
    Critical errors prevent startup, warnings are logged but allow continuation.
    
    Raises:
        ValueError: For critical configuration errors that prevent startup
    """
    import logging
    import os
    from pathlib import Path
    logger = logging.getLogger(__name__)
    
    critical_errors = []
    warnings = []
    
    # Basic validation - DEM_SOURCES must exist
    if not settings.DEM_SOURCES:
        critical_errors.append("DEM_SOURCES configuration is required but not provided")
    
    # Validate DEM_SOURCES structure
    if settings.DEM_SOURCES:
        for source_id, source_config in settings.DEM_SOURCES.items():
            if not isinstance(source_config, dict):
                critical_errors.append(f"DEM source '{source_id}' must be a dictionary")
                continue
            
            if 'path' not in source_config:
                critical_errors.append(f"DEM source '{source_id}' missing required 'path' field")
            
            # Validate local file paths exist
            path = source_config.get('path', '')
            if not path.startswith(('s3://', 'api://', 'http://', 'https://')):
                if not Path(path).exists():
                    warnings.append(f"Local DEM file not found: {path} (source: {source_id})")
    
    # JWT Authentication validation
    if hasattr(settings, 'REQUIRE_AUTH') and settings.REQUIRE_AUTH:
        if not getattr(settings, 'SUPABASE_JWT_SECRET', None):
            critical_errors.append(
                "REQUIRE_AUTH=true but SUPABASE_JWT_SECRET not provided. "
                "Set SUPABASE_JWT_SECRET or disable authentication with REQUIRE_AUTH=false"
            )
    
    # Validate CORS configuration
    if hasattr(settings, 'CORS_ORIGINS'):
        cors_origins = settings.CORS_ORIGINS.strip() if settings.CORS_ORIGINS else ""
        if cors_origins and cors_origins != "*":
            # Check if origins are valid URLs
            for origin in cors_origins.split(','):
                origin = origin.strip()
                if origin and not (origin.startswith('http://') or origin.startswith('https://')):
                    warnings.append(f"CORS origin should include protocol: {origin}")
    
    # Check for critical errors first
    if critical_errors:
        error_msg = "Critical configuration errors found:\n" + "\n".join(f"- {error}" for error in critical_errors)
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # Validate S3-specific requirements
    if settings.USE_S3_SOURCES:
        s3_sources = [src for src in settings.DEM_SOURCES.values() 
                     if src.get('path', '').startswith('s3://')]
        
        if s3_sources and not settings.AWS_DEFAULT_REGION:
            logger.warning("S3 sources configured but AWS_DEFAULT_REGION not set")
        
        # Check for our own S3 bucket access
        our_bucket_sources = [src for src in settings.DEM_SOURCES.values() 
                             if 'road-engineering-elevation-data' in src.get('path', '')]
        
        if our_bucket_sources:
            if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
                warnings.append(
                    "Private S3 bucket sources configured but AWS credentials not provided. "
                    "Some sources may be inaccessible."
                )
    
    # Validate API-specific requirements
    if settings.USE_API_SOURCES:
        api_sources = [src for src in settings.DEM_SOURCES.values() 
                      if src.get('path', '').startswith('api://')]
        
        if api_sources and not settings.GPXZ_API_KEY:
            warnings.append(
                "API sources configured but GPXZ_API_KEY not provided. "
                "External API sources will be unavailable. "
                "Set GPXZ_API_KEY in environment or switch to local mode."
            )
        elif not api_sources and settings.GPXZ_API_KEY:
            logger.info(
                "GPXZ_API_KEY provided but no API sources configured. "
                "Add API sources to DEM_SOURCES to enable external elevation data."
            )
        
        # Validate GPXZ rate limits
        if settings.GPXZ_API_KEY:
            if settings.GPXZ_DAILY_LIMIT <= 0:
                logger.warning("GPXZ_DAILY_LIMIT should be > 0 for API usage")
            if settings.GPXZ_RATE_LIMIT <= 0:
                logger.warning("GPXZ_RATE_LIMIT should be > 0 for API usage")
            else:
                logger.info(
                    "GPXZ API configured successfully",
                    extra={
                        "gpxz_daily_limit": settings.GPXZ_DAILY_LIMIT,
                        "gpxz_rate_limit": settings.GPXZ_RATE_LIMIT,
                        "config_status": "complete"
                    }
                )
    
    # Validate local sources exist
    local_sources = [src for src in settings.DEM_SOURCES.values() 
                    if not src.get('path', '').startswith(('s3://', 'api://'))]
    
    if local_sources:
        for src in local_sources:
            path = src.get('path', '')
            if path and not path.startswith('./'):
                # Check if file exists for absolute paths
                from pathlib import Path
                if not Path(path).exists():
                    warnings.append(f"Local DEM source file not found: {path}")
    
    # Log all collected warnings (with ASCII fallback for cross-platform compatibility)
    if warnings:
        for warning in warnings:
            try:
                logger.warning(f"{warning}")
            except UnicodeEncodeError:
                logger.warning(f"WARNING: {warning}")
        logger.info(f"Environment validation completed with {len(warnings)} warnings")
    else:
        try:
            logger.info("Environment validation completed successfully - no issues found")
        except UnicodeEncodeError:
            logger.info("Environment validation completed successfully - no issues found")
    
    # Log configuration summary
    source_count = len(settings.DEM_SOURCES) if settings.DEM_SOURCES else 0
    logger.info(
        "Configuration summary",
        extra={
            "dem_sources_count": source_count,
            "use_s3": getattr(settings, 'USE_S3_SOURCES', False),
            "use_apis": getattr(settings, 'USE_API_SOURCES', False),
            "auth_enabled": getattr(settings, 'REQUIRE_AUTH', False),
            "validation_status": "complete"
        }
    )

def get_settings():
    """Dependency for getting settings with validation."""
    settings = Settings()
    
    # Validate configuration
    try:
        validate_environment_configuration(settings)
    except ValueError as e:
        raise ValueError(f"Configuration validation failed: {e}")
    
    # Set AWS environment variables if provided in settings
    if settings.AWS_ACCESS_KEY_ID:
        os.environ['AWS_ACCESS_KEY_ID'] = settings.AWS_ACCESS_KEY_ID
    if settings.AWS_SECRET_ACCESS_KEY:
        os.environ['AWS_SECRET_ACCESS_KEY'] = settings.AWS_SECRET_ACCESS_KEY
    if settings.AWS_S3_BUCKET_NAME:
        os.environ['AWS_S3_BUCKET_NAME'] = settings.AWS_S3_BUCKET_NAME
    if settings.AWS_DEFAULT_REGION:
        os.environ['AWS_DEFAULT_REGION'] = settings.AWS_DEFAULT_REGION
    
    return settings 