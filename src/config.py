from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, Any, Optional, List, Literal
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Explicitly load .env file to ensure environment variables are available
load_dotenv()

class DEMSource(BaseModel):
    path: str
    crs: Optional[str] = None  # Optional explicit CRS, prefer reading from file metadata
    layer: Optional[str] = None  # For geodatabases: specific layer name to use
    description: Optional[str] = None  # Optional description of the data source

    class Config:
        extra = "allow"  # Allow additional fields for future extensibility

# Global cache for index-driven sources with TTL
_sources_cache = None
_cache_timestamp = None
_CACHE_TTL_SECONDS = 600  # 10 minutes TTL

def load_dem_sources_from_spatial_index() -> Dict[str, Dict[str, Any]]:
    """
    Load DEM sources dynamically from S3 spatial indices - index-driven approach.
    
    This eliminates the need for separate dem_sources.json configuration by using
    the spatial indices as the single source of truth for available DEM sources.
    
    Benefits:
    - Automatic discovery of new S3 DEM files
    - Always in sync with actual S3 contents  
    - Single source of truth (spatial index)
    - No manual configuration maintenance needed
    - TTL caching for performance (10min cache)
    """
    import logging
    import time
    logger = logging.getLogger(__name__)
    
    global _sources_cache, _cache_timestamp
    
    # Check cache validity
    current_time = time.time()
    if (_sources_cache is not None and 
        _cache_timestamp is not None and 
        (current_time - _cache_timestamp) < _CACHE_TTL_SECONDS):
        logger.debug(f"Returning cached DEM sources (age: {current_time - _cache_timestamp:.1f}s)")
        return _sources_cache
    
    logger.info("Loading DEM sources from spatial indices (index-driven approach)")
    
    sources = {}
    
    # Try to load from spatial indices - S3 or local
    try:
        campaign_index = None
        
        # Check if we're configured for S3 indices
        if os.getenv("SPATIAL_INDEX_SOURCE", "local").lower() == "s3":
            logger.info("Attempting to load sources from S3 spatial indices...")
            
            # Import S3 index loader with detailed error tracking and fallback
            s3_index_loader = None
            try:
                from .s3_index_loader import s3_index_loader
                logger.info("Successfully imported s3_index_loader via relative import")
            except ImportError as relative_error:
                logger.warning(f"Relative import failed: {relative_error}. Trying absolute import...")
                try:
                    from src.s3_index_loader import s3_index_loader
                    logger.info("Successfully imported s3_index_loader via absolute import")
                except ImportError as absolute_error:
                    import traceback
                    logger.error(f"Both relative and absolute imports failed.")
                    logger.error(f"Relative error: {relative_error}")
                    logger.error(f"Absolute error: {absolute_error}")
                    logger.error(f"Full traceback:\n{traceback.format_exc()}")
                    logger.error(f"Python path: {os.environ.get('PYTHONPATH', 'Not set')}")
                    logger.error(f"Current working directory: {os.getcwd()}")
                    logger.error(f"Available modules: {[m for m in os.listdir('/app/src') if m.endswith('.py')]}")
                    raise ImportError(f"S3 index loader import failed: {absolute_error}") from absolute_error
            
            if s3_index_loader is None:
                raise ImportError("s3_index_loader is None after import attempts")
            
            # Test S3 connectivity first
            health_check = s3_index_loader.health_check()
            if health_check.get('status') == 'healthy':
                logger.info("S3 indices accessible - loading campaign sources")
                
                # Load campaign index for source discovery
                try:
                    campaign_index = s3_index_loader.load_index('campaign')
                except Exception as campaign_error:
                    logger.error(f"Failed to load campaign index from S3: {campaign_error}", exc_info=True)
                    campaign_index = None
                    
            else:
                logger.warning(f"S3 indices not accessible: {health_check.get('reason', 'Unknown error')}. "
                             f"Status: {health_check.get('status', 'unknown')}. Falling back to local indices.")
        
        # Fall back to local campaign index if S3 failed or not configured
        if campaign_index is None:
            logger.info("Loading campaign sources from local indices...")
            local_campaign_file = Path(__file__).parent.parent / "config" / "phase3_campaign_populated_index.json"
            
            if local_campaign_file.exists():
                try:
                    with open(local_campaign_file, 'r') as f:
                        campaign_index = json.load(f)
                    logger.info(f"Local campaign index loaded: {local_campaign_file}")
                except Exception as local_error:
                    logger.error(f"Failed to load local campaign index: {local_error}")
                    campaign_index = None
            else:
                logger.warning(f"Local campaign index file not found: {local_campaign_file}")
        
        # Process campaign index data if we have it
        if campaign_index:
            # Extract sources from campaign data (handle both 'campaigns' and 'datasets' keys)
            campaigns = campaign_index.get('campaigns', campaign_index.get('datasets', {}))
            total_campaigns = campaign_index.get('total_campaigns', len(campaigns))
            logger.info(f"Found {len(campaigns)} campaigns in index (total: {total_campaigns})")
            
            for campaign_id, campaign_data in campaigns.items():
                # Create source entry from campaign metadata
                campaign_files = campaign_data.get('files', [])
                if campaign_files:
                    # Handle different file formats - objects with 'key' field or direct paths
                    if isinstance(campaign_files[0], dict) and 'key' in campaign_files[0]:
                        # Files are objects with key field - use the key directly
                        if len(campaign_files) == 1:
                            # Single file - use specific file key
                            campaign_path = campaign_files[0]['key']
                        else:
                            # Multi-file campaign - use the common S3 path structure
                            first_key = campaign_files[0]['key']
                            # Extract path from s3://bucket/path format
                            if first_key.startswith('s3://'):
                                s3_path = first_key.split('/', 3)[3] if len(first_key.split('/', 3)) > 3 else first_key
                                # Use campaign path from the data if available, otherwise derive prefix
                                campaign_path = campaign_data.get('path', f"s3://{os.getenv('DEM_S3_BUCKET', 'road-engineering-elevation-data')}/")
                            else:
                                campaign_path = f"s3://{os.getenv('DEM_S3_BUCKET', 'road-engineering-elevation-data')}/{first_key}"
                    else:
                        # Files are direct paths (legacy format)
                        if len(campaign_files) == 1:
                            campaign_path = f"s3://{os.getenv('DEM_S3_BUCKET', 'road-engineering-elevation-data')}/{campaign_files[0]}"
                        else:
                            first_file = campaign_files[0]
                            campaign_prefix = "/".join(first_file.split("/")[:-1]) + "/"
                            campaign_path = f"s3://{os.getenv('DEM_S3_BUCKET', 'road-engineering-elevation-data')}/{campaign_prefix}"
                    
                    sources[campaign_id] = {
                        "path": campaign_path,
                        "layer": None,
                        "crs": campaign_data.get('crs', 'EPSG:4326'),
                        "description": campaign_data.get('description', f"Campaign {campaign_id}"),
                        "priority": 1,  # S3 sources get highest priority
                        "source_type": "s3",
                        "bounds": campaign_data.get('bounds', {}),
                        "resolution_m": campaign_data.get('resolution_m', 1.0),
                        "data_type": campaign_data.get('data_type', 'LiDAR'),
                        "provider": campaign_data.get('provider', 'Unknown'),
                        "campaign_id": campaign_id,
                        "file_count": len(campaign_files),
                        "cost_per_query": 0.001,  # S3 cost estimate
                        "accuracy": campaign_data.get('accuracy', '±1m')
                    }
            
            if sources:
                logger.info(f"Successfully loaded {len(sources)} S3 campaign sources from index")
            else:
                logger.warning("No campaign sources found in index")
                
    except ImportError:
        logger.warning("S3 index loader not available - using API fallback sources")
    except Exception as s3_error:
        logger.error(f"Failed to load S3 sources: {s3_error}. Falling back to API sources only.", exc_info=True)
    
    # Add API sources as fallback (always available)
    api_sources = {
        "gpxz_api": {
            "path": "api://gpxz",
            "layer": None,
            "crs": None,
            "description": "GPXZ API global coverage",
            "priority": 2,
            "source_type": "api",
            "bounds": {"global": True},
            "resolution_m": 30.0,  # SRTM resolution
            "data_type": "SRTM",
            "provider": "GPXZ.io",
            "cost_per_query": 0.01,
            "accuracy": "±10m"
        },
        "google_elevation": {
            "path": "api://google",
            "layer": None,
            "crs": None,
            "description": "Google Elevation API fallback",
            "priority": 3,
            "source_type": "api",
            "bounds": {"global": True},
            "resolution_m": 30.0,  # Google uses SRTM
            "data_type": "SRTM",
            "provider": "Google",
            "cost_per_query": 0.005,
            "accuracy": "±10m"
        }
    }
    
    # Merge API sources
    sources.update(api_sources)
    
    # Log final source summary
    s3_count = sum(1 for s in sources.values() if s.get('source_type') == 's3')
    api_count = sum(1 for s in sources.values() if s.get('source_type') == 'api')
    
    logger.info(f"Index-driven source loading complete:")
    logger.info(f"  - S3 campaigns: {s3_count}")
    logger.info(f"  - API sources: {api_count}")
    logger.info(f"  - Total sources: {len(sources)}")
    
    if len(sources) == 0:
        logger.error("No DEM sources available - this should not happen")
        # Emergency fallback
        sources = {
            "emergency_fallback": {
                "path": "api://gpxz",
                "description": "Emergency GPXZ fallback",
                "priority": 9,
                "source_type": "api"
            }
        }
    
    # Update cache
    _sources_cache = sources
    _cache_timestamp = current_time
    logger.debug(f"Updated DEM sources cache with {len(sources)} sources")
    
    return sources

# Legacy function name for compatibility during transition
def load_dem_sources_from_file(base_dir: str = ".") -> Dict[str, Dict[str, Any]]:
    """
    Legacy compatibility wrapper - now uses index-driven approach.
    
    This maintains API compatibility while switching to the superior
    index-driven source discovery approach.
    """
    return load_dem_sources_from_spatial_index()

class Settings(BaseSettings):
    # Load DEM sources from external file instead of environment
    _dem_sources_cache: Optional[Dict[str, Dict[str, Any]]] = None
    DEFAULT_DEM_ID: Optional[str] = None  # Optional default DEM source ID
    BASE_DIR: str = Field(default=".", description="Base directory for the application")
    
    # Environment detection (Phase 3B.1: Critical Production Safety + Phase 3B.2: Development Support)
    APP_ENV: Literal["production", "development"] = Field(
        default="production", 
        description="Application environment: production (Railway), development (Docker Compose)"
    )
    
    # Phase 2: Unified Architecture Feature Flags
    USE_UNIFIED_SPATIAL_INDEX: bool = Field(
        default=False,
        description="Enable unified v2.0 spatial index (AU+NZ combined with discriminated unions)"
    )
    UNIFIED_INDEX_PATH: str = Field(
        default="indexes/unified_spatial_index_v2.json",
        description="S3 path for unified spatial index"
    )
    
    # Phase 2: SQLite R*Tree Spatial Index
    USE_SQLITE_INDEX: bool = Field(
        default=False,
        description="Enable SQLite R*Tree spatial indexing for <10ms query performance"
    )
    SQLITE_INDEX_URL: str = Field(
        default="s3://road-engineering-elevation-data/indexes/spatial_index.db.gz",
        description="URL to compressed SQLite spatial database"
    )
    SQLITE_DB_HASH: Optional[str] = Field(
        default=None,
        description="SHA256 hash for SQLite database integrity verification"
    )
    SQLITE_DOWNLOAD_PATH: str = Field(
        default="./spatial_index.db",
        description="Local path for downloaded SQLite database"
    )
    SQLITE_DB_VERSION: Optional[str] = Field(
        default=None,
        description="SQLite database version identifier"
    )
    
    # Multi-source environment settings (Phase 3B.2: Enhanced with better field types)
    USE_S3_SOURCES: bool = Field(default=False, description="Enable S3-based DEM sources")
    USE_API_SOURCES: bool = Field(default=False, description="Enable external API sources")
    ENABLE_NZ_SOURCES: bool = Field(default=False, description="Enable New Zealand elevation sources (S3 nz-elevation bucket)")
    
    # Data source configuration (Phase 3B.2: Added with Literal types)
    SPATIAL_INDEX_SOURCE: Literal["local", "s3"] = Field(
        default="local",
        description="Source for spatial indexes: local (filesystem), s3 (S3 bucket)"
    )
    
    # S3 Index Configuration (Phase 3B.3.2: Dependency Injection Support)
    S3_CAMPAIGN_INDEX_PATH: str = Field(
        default="indexes/campaign_index.json",
        description="S3 path to campaign spatial index file"
    )
    S3_NZ_INDEX_PATH: str = Field(
        default="indexes/nz_spatial_index.json", 
        description="S3 path to New Zealand spatial index file"
    )
    
    # Geodatabase-specific settings
    GDB_AUTO_DISCOVER: bool = Field(default=True, description="Automatically discover raster layers in geodatabases")
    GDB_PREFERRED_DRIVERS: list = Field(default=["OpenFileGDB", "FileGDB"], description="Preferred drivers for geodatabase access")
    
    # Performance settings
    CACHE_SIZE_LIMIT: int = Field(default=10, description="Maximum number of datasets to keep in cache")
    DATASET_CACHE_SIZE: int = Field(default=10, description="Maximum number of datasets to keep in memory cache")
    MAX_WORKER_THREADS: int = Field(default=10, description="Maximum number of worker threads for async operations")
    
    # GDAL Error Handling (Phase 3B.2: Enhanced with Literal types)
    SUPPRESS_GDAL_ERRORS: bool = Field(default=True, description="Suppress non-critical GDAL errors from log output")
    GDAL_LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="ERROR", 
        description="GDAL logging level"
    )
    
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
    
    # ========================================
    # ENHANCED MULTI-BUCKET S3 CONFIGURATION 
    # ========================================
    # Implements Gemini's approved architecture for mixed public/private bucket support
    
    # LEGACY CONFIGURATION (Backward Compatible)
    S3_INDEX_BUCKET: str = Field(default="road-engineering-elevation-data", description="Legacy S3 bucket for Australian indexes")
    
    # FEATURE FLAG - NZ Sources Integration
    ENABLE_NZ_SOURCES: bool = Field(default=False, description="Enable New Zealand S3 sources integration")
    
    # SIMPLE MODE - NZ Configuration via Environment Variables (Phase 3B.2: Enhanced types)
    S3_NZ_BUCKET: str = Field(default="nz-elevation", description="New Zealand S3 bucket name")
    S3_NZ_REGION: str = Field(default="ap-southeast-2", description="New Zealand S3 bucket region")
    S3_NZ_INDEX_KEY: str = Field(default="indexes/nz_spatial_index.json", description="New Zealand spatial index file key")
    S3_NZ_ACCESS_TYPE: Literal["public", "private"] = Field(
        default="public", 
        description="New Zealand bucket access type"
    )
    S3_NZ_REQUIRED: bool = Field(default=False, description="Whether NZ sources are required for startup")
    
    # EXPERT MODE - JSON Configuration (overrides all other S3 settings)
    S3_SOURCES_CONFIG: str = Field(default="", description="JSON configuration for advanced multi-bucket setup")
    
    # Server settings (Phase 3B.3.2: Enhanced with Railway PORT support)
    HOST: str = Field(default="0.0.0.0", description="Server host")
    PORT: int = Field(
        default=8001, 
        description="Port for the Uvicorn server. Injected by Railway's $PORT in production."
    )
    
    # Authentication settings
    SUPABASE_JWT_SECRET: Optional[str] = None
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT algorithm for token verification")
    JWT_AUDIENCE: str = Field(default="authenticated", description="JWT audience for token verification")
    REQUIRE_AUTH: bool = Field(default=False, description="Whether to require authentication for protected endpoints")
    
    # CORS and main platform integration
    CORS_ORIGINS: str = Field(default="http://localhost:3001,http://localhost:5173,http://localhost:5174", description="Comma-separated list of allowed CORS origins")
    MAIN_BACKEND_URL: str = Field(default="http://localhost:3001", description="Main platform backend URL")
    
    # Phase 3B.1: Simplified production-focused configuration  
    # Railway deployment uses .env file with APP_ENV for safety checks
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding='utf-8', 
        extra="ignore"
    )
    
    @field_validator('USE_SQLITE_INDEX', 'USE_S3_SOURCES', 'USE_API_SOURCES', 
                     'ENABLE_NZ_SOURCES', 'USE_UNIFIED_SPATIAL_INDEX', mode='before')
    @classmethod
    def parse_boolean(cls, v):
        """Handle string boolean values from environment variables.
        Railway and other platforms pass environment variables as strings.
        This validator ensures proper boolean coercion for common representations."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on', 't', 'y')
        return bool(v)
    
    @property
    def DEM_SOURCES(self) -> Dict[str, Dict[str, Any]]:
        """
        Static DEM sources configuration - NO I/O OPERATIONS.
        
        Phase 3A-Fix: This property now only returns static configuration from environment.
        All dynamic data loading has been moved to SourceProvider for async startup.
        """
        import os
        import json
        
        # Only return sources from environment variable (static config)
        env_dem_sources = os.getenv('DEM_SOURCES', '').strip()
        if env_dem_sources and env_dem_sources != '{}':
            try:
                parsed_sources = json.loads(env_dem_sources)
                if isinstance(parsed_sources, dict) and len(parsed_sources) > 0:
                    return parsed_sources
            except (json.JSONDecodeError, TypeError):
                pass
        
        # Return minimal static API sources as fallback
        # NOTE: SourceProvider will provide the full dynamic source list
        return {
            'gpxz_api': {
                'source_type': 'api',
                'name': 'GPXZ.io Global Elevation API',
                'resolution_m': 30.0,
                'accuracy': '±1m',
                'coverage': 'global'
            },
            'google_api': {
                'source_type': 'api', 
                'name': 'Google Elevation API',
                'resolution_m': 30.0,
                'accuracy': '±1m',
                'coverage': 'global'
            }
        }
    
    def refresh_dem_sources(self) -> None:
        """Refresh DEM sources cache - useful when S3 indices are updated"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info("Refreshing DEM sources cache")
        
        # Clear both instance cache and global TTL cache
        self._dem_sources_cache = None
        global _sources_cache, _cache_timestamp
        _sources_cache = None
        _cache_timestamp = None
    
    def build_s3_sources_config(self) -> List['S3SourceConfig']:
        """
        Build S3 sources configuration using Gemini's approved precedence hierarchy:
        1. Expert Mode: S3_SOURCES_CONFIG JSON (overrides everything)
        2. Simple Mode: Individual environment variables
        3. Legacy Fallback: Existing behavior preserved
        """
        from .s3_config import S3SourceConfig, S3ConfigurationManager
        return S3ConfigurationManager.build_sources_from_settings(self)
    
    def validate_app_environment(self) -> None:
        """
        Phase 3B.2: Validate APP_ENV configuration consistency.
        
        Ensures environment-specific settings are consistent with APP_ENV value.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if self.APP_ENV == "production":
            # Production validation
            if not os.getenv('REDIS_URL') and not os.getenv('REDIS_PRIVATE_URL'):
                logger.warning("Production environment without Redis configuration - service will fail-fast on startup")
            
            if self.SPATIAL_INDEX_SOURCE == "s3" and not self.AWS_ACCESS_KEY_ID:
                logger.warning("Production using S3 spatial indexes without AWS credentials")
                
        elif self.APP_ENV == "development":
            # Development validation
            if not os.getenv('REDIS_URL'):
                logger.info("Development environment - Redis fallback will be used if Redis unavailable")
            
            if self.SPATIAL_INDEX_SOURCE == "s3":
                logger.info("Development using S3 spatial indexes - ensure AWS credentials are configured")
        
        logger.info(f"APP_ENV validation complete: {self.APP_ENV} environment configured correctly")

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
        DEMConfigurationError: For DEM-specific configuration errors
    """
    import logging
    import os
    from pathlib import Path
    from .dem_exceptions import DEMConfigurationError
    logger = logging.getLogger(__name__)
    
    critical_errors = []
    warnings = []
    
    # Configuration dependency validation (Phase 3A.3)
    if getattr(settings, 'ENABLE_NZ_SOURCES', False) and not getattr(settings, 'USE_S3_SOURCES', False):
        critical_errors.append(
            "Configuration dependency error: ENABLE_NZ_SOURCES=true requires USE_S3_SOURCES=true. "
            "NZ sources are hosted on S3 and cannot be used without S3 support enabled."
        )
    
    # Basic validation - DEM_SOURCES must exist
    if not settings.DEM_SOURCES:
        critical_errors.append("DEM_SOURCES configuration is required but not provided")
    
    # Validate DEM_SOURCES structure
    if settings.DEM_SOURCES:
        for source_id, source_config in settings.DEM_SOURCES.items():
            if not isinstance(source_config, dict):
                critical_errors.append(f"DEM source '{source_id}' must be a dictionary")
                continue
            
            # Only require 'path' field for non-API sources
            source_type = source_config.get('source_type', 'file')
            if source_type != 'api' and 'path' not in source_config:
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
        raise DEMConfigurationError(error_msg)
    
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
    from .dem_exceptions import DEMConfigurationError
    settings = Settings()
    
    # Validate configuration
    try:
        validate_environment_configuration(settings)
    except (ValueError, DEMConfigurationError) as e:
        raise DEMConfigurationError(f"Configuration validation failed: {e}")
    
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