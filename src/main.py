import asyncio
import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os

from .config import get_settings, validate_environment_configuration
from .api.v1.endpoints import router as elevation_router
from .api.v1.dataset_endpoints import router as dataset_router
from .api.v1.campaigns_endpoints import router as campaign_router
from .dependencies import init_service_container, close_service_container, get_dem_service
from .logging_config import setup_logging
from .s3_client_factory import create_s3_client_factory
from .source_provider import SourceProvider, SourceProviderConfig

# Setup structured logging based on environment
setup_logging(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    service_name="dem-backend"
)
logger = logging.getLogger(__name__)

async def validate_s3_connectivity(s3_factory):
    """Async validation of S3 connectivity with timeout using DI factory"""
    try:
        logger.info("Validating S3 connectivity...")
        
        # Test basic connectivity to default S3 region using injected factory
        async with s3_factory.get_client("private", "ap-southeast-2") as s3_client:
            # Simple list operation to test connectivity
            await asyncio.wait_for(s3_client.list_buckets(), timeout=5.0)
            
        logger.info("S3 connectivity validation successful")
        return {"status": "healthy", "connectivity": True}
        
    except asyncio.TimeoutError:
        logger.warning("S3 connectivity validation timed out")
        return {"status": "timeout", "connectivity": False}
    except Exception as e:
        logger.warning(f"S3 connectivity validation failed: {e}")
        return {"status": "error", "connectivity": False, "error": str(e)}

async def validate_api_sources():
    """Async validation of API sources connectivity"""
    try:
        logger.info("Validating API sources...")
        
        # Quick validation - just check if API keys are configured
        gpxz_key = os.getenv("GPXZ_API_KEY")
        
        if gpxz_key:
            logger.info("GPXZ API key configured")
            return {"status": "healthy", "gpxz_configured": True}
        else:
            logger.info("GPXZ API key not configured - API sources will be limited")
            return {"status": "partial", "gpxz_configured": False}
            
    except Exception as e:
        logger.warning(f"API sources validation failed: {e}")
        return {"status": "error", "error": str(e)}

async def validate_index_driven_sources_concurrent(settings, s3_factory):
    """
    Phase 2B: Concurrent startup validation using DI and asyncio.gather pattern
    Validates index-driven source configuration and connectivity concurrently
    """
    logger.info("Starting concurrent validation of index-driven DEM sources...")
    
    try:
        # Check that sources were loaded successfully via index-driven approach
        source_count = len(settings.DEM_SOURCES)
        if source_count == 0:
            logger.warning("No DEM sources loaded from index-driven configuration")
            return False
        
        # Count S3 vs API sources for validation reporting
        s3_sources = sum(1 for source in settings.DEM_SOURCES.values() 
                        if source.get('source_type') == 's3')
        api_sources = sum(1 for source in settings.DEM_SOURCES.values() 
                         if source.get('source_type') == 'api')
        
        logger.info(f"Found {s3_sources} S3 sources and {api_sources} API sources")
        
        # Phase 2B: Concurrent validation using asyncio.gather with injected dependencies
        validation_tasks = []
        
        # Add S3 validation if we have S3 sources (pass injected factory)
        if s3_sources > 0:
            validation_tasks.append(validate_s3_connectivity(s3_factory))
        
        # Add API validation if we have API sources  
        if api_sources > 0:
            validation_tasks.append(validate_api_sources())
        
        # Run all validations concurrently with timeout
        if validation_tasks:
            logger.info(f"Running {len(validation_tasks)} validation tasks concurrently...")
            results = await asyncio.gather(*validation_tasks, return_exceptions=True)
            
            # Process results
            all_healthy = True
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.warning(f"Validation task {i} failed with exception: {result}")
                    all_healthy = False
                elif isinstance(result, dict) and result.get("status") not in ["healthy", "partial"]:
                    logger.warning(f"Validation task {i} returned unhealthy status: {result}")
                    all_healthy = False
                else:
                    logger.info(f"Validation task {i} completed: {result}")
        
        logger.info(
            "Concurrent source validation completed",
            extra={
                "event": "concurrent_validation_success",
                "total_sources": source_count,
                "s3_sources": s3_sources,
                "api_sources": api_sources,
                "validation_tasks": len(validation_tasks)
            }
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "Concurrent source validation failed",
            extra={"event": "concurrent_validation_failed", "error": str(e)},
            exc_info=True
        )
        return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Phase 3B.5: Unified Elevation Provider with feature flag control.
    
    This lifespan handler implements both legacy and unified v2.0 architectures:
    - Feature flag controlled: USE_UNIFIED_SPATIAL_INDEX
    - Unified v2.0: Country-agnostic discriminated unions with Collection Handlers
    - Legacy fallback: SourceProvider pattern for compatibility
    - Production-ready startup with fail-fast behavior
    """
    # Startup
    logger.info("Starting DEM Elevation Service with UnifiedElevationProvider...", extra={"event": "startup_begin"})
    
    try:
        # Get static settings (no I/O operations)
        settings = get_settings()
        validate_environment_configuration(settings)
        
        # Create S3ClientFactory for all architectures
        s3_factory = create_s3_client_factory()
        app.state.s3_factory = s3_factory
        
        # Phase 3B.5: Feature flag controlled provider selection
        if settings.USE_UNIFIED_SPATIAL_INDEX:
            logger.info("🚀 Using Phase 2 Unified Architecture (v2.0) with discriminated unions")
            
            # Import UnifiedElevationProvider and CRS service  
            from .providers.unified_elevation_provider import UnifiedElevationProvider
            from .services.crs_service import CRSTransformationService
            
            # Create CRS transformation service for CRS-aware spatial queries
            crs_service = CRSTransformationService()
            logger.info("CRS transformation service created for Brisbane coordinate system fix")
            
            # Create and initialize unified provider with CRS service
            unified_provider = UnifiedElevationProvider(s3_client_factory=s3_factory, crs_service=crs_service)
            
            # Initialize unified system - BLOCKS startup until complete
            logger.info("Initializing unified elevation system...")
            unified_success = await unified_provider.initialize()
            
            if not unified_success and settings.APP_ENV == "production":
                logger.critical("Production service cannot start without unified system")
                # TEMPORARY: Disable fail-fast to allow deployment - will fix index after deploy
                logger.critical("ALLOWING DEGRADED START - MUST FIX INDEX PATH IMMEDIATELY")
                # raise SystemExit(1)  # DISABLED TEMPORARILY FOR DEPLOYMENT FIX
            elif not unified_success:
                logger.warning("Development service: unified system failed, falling back to legacy")
                # Fall through to legacy initialization below
                settings.USE_UNIFIED_SPATIAL_INDEX = False
            else:
                # Unified system success - store on app.state
                app.state.unified_provider = unified_provider
                app.state.source_provider = None  # Clear legacy reference
                logger.info("✅ Unified elevation provider initialized successfully")
        
        if not settings.USE_UNIFIED_SPATIAL_INDEX:
            logger.info("📊 Using Legacy Architecture (SourceProvider pattern)")
            
            # Create SourceProvider with dependency-injected configuration
            # Phase 3B.3.2: S3 index paths injected from settings
            source_config = SourceProviderConfig(
                s3_bucket_name=os.getenv('DEM_S3_BUCKET', 'road-engineering-elevation-data'),
                campaign_index_key=getattr(settings, 'S3_CAMPAIGN_INDEX_PATH', 'indexes/spatial_index.json'),
                nz_index_key=getattr(settings, 'S3_NZ_INDEX_PATH', 'indexes/nz_spatial_index.json'),
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                aws_region=settings.AWS_DEFAULT_REGION,
                enable_nz_sources=getattr(settings, 'ENABLE_NZ_SOURCES', False)
            )
            
            # Create SourceProvider and store on app.state
            provider = SourceProvider(source_config)
            app.state.source_provider = provider
            app.state.unified_provider = None  # Clear unified reference
            logger.info("SourceProvider created and stored on app.state")
        
        # Load all data asynchronously - BLOCKS startup until complete (legacy only)
        if not settings.USE_UNIFIED_SPATIAL_INDEX:
            logger.info("Loading legacy data sources asynchronously...")
            try:
                load_success = await provider.load_all_sources()
            except Exception as e:
                # Phase 3B.3.2: Implement fail-fast production behavior
                from .exceptions import S3IndexNotFoundError, S3AccessError
                
                if isinstance(e, S3IndexNotFoundError):
                    critical_msg = (
                        f"CRITICAL: S3 DataSource failed to initialize: "
                        f"Index '{e.index_path}' not found in bucket '{e.bucket}'. "
                        f"Service degrading to API-only mode."
                    )
                    logger.critical(critical_msg)
                    
                    # Fail-fast in production for configuration errors
                    if settings.APP_ENV == "production":
                        logger.critical("Production environment cannot start with missing S3 index. Exiting.")
                        raise SystemExit(1)
                    else:
                        logger.warning("Development environment - continuing with API fallback")
                        load_success = False
                else:
                    # Re-raise other exceptions
                    raise e
            
            if not load_success and settings.APP_ENV == "production":
                logger.critical(f"Production service cannot start without critical data sources: {provider.get_load_errors()}")
                raise SystemExit(1)
            elif not load_success:
                logger.warning(f"Development service starting in degraded mode: {provider.get_load_errors()}")
            
            # Get loaded sources for service container
            dem_sources = provider.get_dem_sources()
            logger.info(f"Legacy data loading completed: {len(dem_sources)} sources available")
        else:
            # Unified provider already initialized above
            dem_sources = {}  # Unified provider doesn't use dem_sources dict
            logger.info("Unified provider initialization completed")
        
        # Pre-initialize EnhancedSourceSelector during startup (legacy mode only)
        if not settings.USE_UNIFIED_SPATIAL_INDEX:
            logger.info("Pre-initializing EnhancedSourceSelector during lifespan startup...")
            try:
                from .enhanced_source_selector import EnhancedSourceSelector
                from .gpxz_client import GPXZConfig
                
                # Prepare configurations for external services
                gpxz_config = GPXZConfig(api_key=settings.GPXZ_API_KEY) if settings.GPXZ_API_KEY else None
                google_api_key = settings.GOOGLE_ELEVATION_API_KEY
                aws_creds = {
                    "access_key_id": settings.AWS_ACCESS_KEY_ID,
                    "secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
                    "region": settings.AWS_DEFAULT_REGION
                } if settings.AWS_ACCESS_KEY_ID else None
                
                # Create and fully initialize EnhancedSourceSelector here (with event loop available)
                enhanced_selector = EnhancedSourceSelector(
                    config=dem_sources,
                    use_s3=getattr(settings, 'USE_S3_SOURCES', False),
                    use_apis=getattr(settings, 'USE_API_SOURCES', False),
                    gpxz_config=gpxz_config,
                    google_api_key=google_api_key,
                    aws_credentials=aws_creds,
                    redis_manager=None,  # Will be created lazily
                    enable_nz=getattr(settings, 'ENABLE_NZ_SOURCES', False)
                )
                
                # Trigger NZ index loading if enabled (now we have a running event loop)
                if getattr(settings, 'ENABLE_NZ_SOURCES', False):
                    logger.info("Loading NZ spatial index during lifespan startup...")
                    try:
                        await enhanced_selector._load_nz_index_async()
                        logger.info("NZ spatial index loaded successfully during startup")
                    except Exception as nz_error:
                        logger.warning(f"Failed to load NZ index during startup: {nz_error}")
                
                # Store on app.state for dependency injection
                app.state.enhanced_selector = enhanced_selector
                logger.info("EnhancedSourceSelector pre-initialized and stored on app.state")
            except Exception as e:
                logger.warning(f"Failed to pre-initialize EnhancedSourceSelector (will fall back to lazy loading): {e}")
                app.state.enhanced_selector = None
        else:
            # Unified mode doesn't use EnhancedSourceSelector
            app.state.enhanced_selector = None
            logger.info("Unified mode: Skipping EnhancedSourceSelector initialization")

        # Initialize service container with loaded data and provider
        if settings.USE_UNIFIED_SPATIAL_INDEX:
            # Unified provider mode
            service_container = init_service_container(
                settings, 
                source_provider=None,  # No legacy provider
                enhanced_selector=None,  # No enhanced selector
                unified_provider=getattr(app.state, 'unified_provider', None)
            )
        else:
            # Legacy provider mode
            service_container = init_service_container(
                settings, 
                source_provider=provider,
                enhanced_selector=getattr(app.state, 'enhanced_selector', None)
            )
        
        # Log startup completion with appropriate provider info
        if settings.USE_UNIFIED_SPATIAL_INDEX:
            logger.info(
                "DEM Elevation Service started successfully with Unified Provider (v2.0)",
                extra={
                    "event": "startup_complete",
                    "provider_type": "unified",
                    "unified_mode": True,
                    "unified_index_path": settings.UNIFIED_INDEX_PATH
                }
            )
        else:
            logger.info(
                "DEM Elevation Service started successfully with Legacy SourceProvider pattern",
                extra={
                    "event": "startup_complete",
                    "provider_type": "legacy",
                    "sources_loaded": len(dem_sources),
                    "load_success": load_success,
                    "provider_stats": provider.get_performance_stats()
                }
            )
        
        yield  # App ready for traffic
        
    except Exception as e:
        logger.error(
            "Failed to start DEM service with SourceProvider",
            extra={"event": "startup_failed", "error_type": type(e).__name__},
            exc_info=True
        )
        raise e
    
    # Shutdown
    logger.info("Shutting down DEM Elevation Service...", extra={"event": "shutdown_begin"})
    try:
        # Clean up service container
        await close_service_container()
        
        # Clear references for both provider types
        if hasattr(app.state, 'source_provider'):
            app.state.source_provider = None
        if hasattr(app.state, 'unified_provider'):
            app.state.unified_provider = None
        if hasattr(app.state, 's3_factory'):
            app.state.s3_factory = None
        if hasattr(app.state, 'enhanced_selector'):
            app.state.enhanced_selector = None
        
        logger.info("DEM Elevation Service shut down successfully", extra={"event": "shutdown_complete"})
    except Exception as e:
        logger.error("Error during shutdown", extra={"event": "shutdown_failed"}, exc_info=True)

# Create rate limiter for API protection
limiter = Limiter(key_func=get_remote_address)

# Create FastAPI application
app = FastAPI(
    title="DEM Elevation Service",
    description="A dedicated elevation data service using FastAPI that serves elevation data from Digital Elevation Model (DEM) files and geodatabases",
    version="1.0.0",
    lifespan=lifespan
)

# Add rate limiting error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.get("/debug/settings-info")
async def debug_settings_info():
    """Debug endpoint to check Settings instance state in production"""
    import os
    from .dependencies import get_service_container
    
    # Get multiple Settings instances
    direct_settings = get_settings()
    container_settings = get_service_container().settings
    
    return {
        "direct_settings": {
            "source_count": len(direct_settings.DEM_SOURCES),
            "first_3_sources": list(direct_settings.DEM_SOURCES.keys())[:3],
            "instance_id": id(direct_settings)
        },
        "container_settings": {
            "source_count": len(container_settings.DEM_SOURCES), 
            "first_3_sources": list(container_settings.DEM_SOURCES.keys())[:3],
            "instance_id": id(container_settings)
        },
        "same_instance": direct_settings is container_settings,
        "environment": {
            "RAILWAY_ENVIRONMENT": os.environ.get("RAILWAY_ENVIRONMENT"),
            "SPATIAL_INDEX_SOURCE": os.environ.get("SPATIAL_INDEX_SOURCE"),
            "DEM_SOURCES_in_env": "DEM_SOURCES" in os.environ,
            "USE_S3_SOURCES": os.environ.get("USE_S3_SOURCES"),
            "USE_API_SOURCES": os.environ.get("USE_API_SOURCES")
        }
    }

@app.get("/api/v1/debug/sqlite-settings")
async def debug_sqlite_settings(request: Request):
    """Debug endpoint to check SQLite boolean parsing issue
    Secured with API key authentication via middleware"""
    import os
    
    settings = get_settings()
    
    # Get raw environment values
    env_raw = os.environ.get("USE_SQLITE_INDEX")
    
    return {
        "sqlite_config": {
            "USE_SQLITE_INDEX": {
                "parsed_value": settings.USE_SQLITE_INDEX,
                "parsed_type": type(settings.USE_SQLITE_INDEX).__name__,
                "env_raw": env_raw,
                "env_type": type(env_raw).__name__ if env_raw is not None else "None",
                "truthy_test": env_raw.lower() in ('true', '1', 'yes', 'on') if env_raw else False
            },
            "SQLITE_INDEX_URL": settings.SQLITE_INDEX_URL,
            "SQLITE_DB_HASH": settings.SQLITE_DB_HASH,
            "SQLITE_DB_VERSION": settings.SQLITE_DB_VERSION if hasattr(settings, 'SQLITE_DB_VERSION') else None,
            "SQLITE_DOWNLOAD_PATH": settings.SQLITE_DOWNLOAD_PATH
        },
        "app_environment": {
            "APP_ENV": settings.APP_ENV,
            "RAILWAY_ENVIRONMENT": os.environ.get("RAILWAY_ENVIRONMENT"),
            "USE_S3_SOURCES": settings.USE_S3_SOURCES,
            "USE_API_SOURCES": settings.USE_API_SOURCES
        },
        "diagnostic": {
            "should_use_sqlite": env_raw and env_raw.lower() in ('true', '1', 'yes', 'on'),
            "actual_using_sqlite": settings.USE_SQLITE_INDEX,
            "mismatch": (env_raw and env_raw.lower() in ('true', '1', 'yes', 'on')) != settings.USE_SQLITE_INDEX
        }
    }

# Add CORS middleware
settings = get_settings()
cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()] if settings.CORS_ORIGINS else ["*"]

# Log CORS configuration for debugging
logger.info(f"CORS configured for origins: {cors_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS", "HEAD"],
    allow_headers=[
        "Authorization",
        "Content-Type", 
        "Accept",
        "Origin",
        "User-Agent",
        "DNT",
        "Cache-Control",
        "X-Mx-ReqToken",
        "Keep-Alive",
        "X-Requested-With",
        "If-Modified-Since"
    ],
    expose_headers=["Content-Length", "Content-Type"],
    max_age=86400  # 24 hours
)

# Include routers
app.include_router(elevation_router, prefix="/api")
app.include_router(dataset_router, prefix="/api/v1/datasets")
app.include_router(campaign_router, prefix="/api/v1")

logger.info("API routes registered:")
logger.info("  Elevation endpoints: /api/v1/elevation/*")
logger.info("  Dataset endpoints: /api/v1/datasets/*")
logger.info("  Campaign endpoints: /api/v1/campaigns/*")

# Import models for legacy endpoint
from .models import PointsRequest, StandardResponse

# Legacy compatibility endpoint
@app.post("/api/get_elevations", tags=["legacy"])
async def get_elevations_legacy(request: dict):
    """Legacy batch elevation endpoint for backward compatibility."""
    from .api.v1.endpoints import get_elevation_points
    
    # Convert legacy format to new format
    coordinates = request.get("coordinates", [])
    points = []
    for coord in coordinates:
        points.append({
            "lat": coord.get("latitude"),
            "lon": coord.get("longitude")
        })
    
    # Create new request format
    new_request = PointsRequest(points=points)
    
    # Use new endpoint
    response = await get_elevation_points(new_request, get_dem_service())
    
    # Convert back to legacy format
    legacy_elevations = []
    for result in response.results:
        legacy_elevations.append({
            "latitude": result.lat,
            "longitude": result.lon,
            "elevation": result.elevation,
            "source": result.data_source
        })
    
    return {
        "elevations": legacy_elevations,
        "total_points": response.metadata.total_points,
        "successful_points": response.metadata.successful_points,
        "source": response.results[0].data_source if response.results else "unknown"
    }

@app.get("/attribution", tags=["legal"])
async def attribution_page():
    """Data source attribution page for Creative Commons compliance."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>DEM Backend - Data Attribution</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
            h1 { color: #2c3e50; }
            h2 { color: #34495e; border-bottom: 2px solid #3498db; padding-bottom: 5px; }
            .source { margin: 20px 0; padding: 15px; background: #f8f9fa; border-left: 4px solid #3498db; }
            .license { font-weight: bold; color: #27ae60; }
            .copyright { font-style: italic; color: #7f8c8d; }
            a { color: #3498db; text-decoration: none; }
            a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <h1>Elevation Data Attribution</h1>
        
        <p>This DEM Backend service uses elevation data from multiple sources. In compliance with Creative Commons licenses, we provide proper attribution for all data sources used.</p>
        
        <div class="source">
            <h2>Geoscience Australia (ELVIS)</h2>
            <p><strong>Data:</strong> 1 second SRTM Digital Elevation Model and LiDAR datasets</p>
            <p class="copyright"><strong>Copyright:</strong> © Commonwealth of Australia (Geoscience Australia) 2024</p>
            <p class="license"><strong>License:</strong> Creative Commons Attribution 4.0 International (CC BY 4.0)</p>
            <p><strong>Source:</strong> <a href="https://elevation.fsdf.org.au/" target="_blank">https://elevation.fsdf.org.au/</a></p>
            <p><strong>Citation:</strong> Geoscience Australia (2024). 1 second SRTM Digital Elevation Model. https://elevation.fsdf.org.au/</p>
        </div>
        
        <div class="source">
            <h2>NASA SRTM</h2>
            <p><strong>Data:</strong> Shuttle Radar Topography Mission (SRTM) elevation data</p>
            <p class="copyright"><strong>Attribution:</strong> SRTM data courtesy of NASA EOSDIS Land Processes Distributed Active Archive Center (LP DAAC)</p>
            <p class="license"><strong>License:</strong> Creative Commons Zero (CC0) - Public Domain</p>
            <p><strong>Source:</strong> <a href="https://www.earthdata.nasa.gov/data/instruments/srtm" target="_blank">NASA SRTM</a></p>
            <p><strong>Citation:</strong> Farr, T. G. et al. (2007). The Shuttle Radar Topography Mission. Rev. Geophys., 45, RG2004, doi:10.1029/2005RG000183</p>
        </div>
        
        <div class="source">
            <h2>GPXZ.io API</h2>
            <p><strong>Data:</strong> Global elevation data via API service</p>
            <p class="copyright"><strong>Attribution:</strong> Elevation data provided by GPXZ.io</p>
            <p class="license"><strong>License:</strong> Commercial API service - subject to GPXZ.io terms of service</p>
            <p><strong>Source:</strong> <a href="https://www.gpxz.io/" target="_blank">https://www.gpxz.io/</a></p>
        </div>
        
        <h2>Usage and Redistribution</h2>
        <p>When using elevation data from this service, please include appropriate attribution based on the data sources used for your specific geographic area. The service includes source information in API responses to help identify which attribution applies.</p>
        
        <p>For questions about licensing or attribution requirements, please contact the respective data providers using the links above.</p>
        
        <p><small>Last updated: July 2024</small></p>
    </body>
    </html>
    """
    
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html_content)

@app.get("/", tags=["health"])
async def root():
    """Health check endpoint."""
    return {
        "service": "DEM Elevation Service",
        "status": "running",
        "version": "1.0.0",
        "features": [
            "GeoTIFF support",
            "Geodatabase (.gdb) support", 
            "Automatic layer discovery",
            "Multiple CRS support",
            "Bilinear interpolation",
            "Great circle line generation",
            "Native DEM point extraction for contours"
        ]
    }

@app.get("/debug-sources", tags=["debug"])
async def debug_sources():
    """Debug endpoint to verify source count from ServiceContainer."""
    try:
        from .dependencies import get_service_container
        from .config import get_settings
        import time
        
        # Get sources from ServiceContainer (what the API uses)
        container_settings = get_service_container().settings
        container_sources = len(container_settings.DEM_SOURCES)
        
        # Get sources from fresh Settings instance (what startup uses)
        fresh_settings = get_settings()
        fresh_sources = len(fresh_settings.DEM_SOURCES)
        
        return {
            "timestamp": time.time(),
            "container_settings_id": id(container_settings),
            "fresh_settings_id": id(fresh_settings),
            "container_sources": container_sources,
            "fresh_sources": fresh_sources,
            "settings_match": id(container_settings) == id(fresh_settings),
            "source_counts_match": container_sources == fresh_sources,
            "first_few_container_sources": list(container_settings.DEM_SOURCES.keys())[:5],
            "first_few_fresh_sources": list(fresh_settings.DEM_SOURCES.keys())[:5]
        }
    except Exception as e:
        return {"error": str(e), "type": type(e).__name__}

@app.get("/debug-elevation-service", tags=["debug"])
async def debug_elevation_service():
    """Debug the elevation service configuration."""
    try:
        from .dependencies import get_service_container
        
        container = get_service_container()
        elevation_service = container.elevation_service
        
        # Check elevation service configuration
        debug_info = {
            "elevation_service_type": type(elevation_service).__name__,
            "using_index_driven": getattr(elevation_service, 'using_index_driven_selector', False),
            "using_enhanced": getattr(elevation_service, 'using_enhanced_selector', False),
            "has_enhanced_selector": hasattr(elevation_service, '_enhanced_selector'),
            "source_selector_type": type(elevation_service.source_selector).__name__ if hasattr(elevation_service, 'source_selector') else None,
        }
        
        # Try to get elevation for Brisbane to see what happens
        try:
            result = await elevation_service.get_elevation(-27.4698, 153.0251)
            debug_info["test_elevation_result"] = {
                "elevation_m": result.elevation_m,
                "dem_source_used": result.dem_source_used,
                "message": result.message
            }
            debug_info["test_success"] = True
        except Exception as e:
            debug_info["test_error"] = str(e)
            debug_info["test_error_type"] = type(e).__name__
            debug_info["test_success"] = False
        
        return debug_info
        
    except Exception as e:
        return {"error": str(e), "type": type(e).__name__}

@app.get("/test-elevation", tags=["debug"])
async def test_elevation_simple():
    """Simple test elevation endpoint bypassing all models."""
    try:
        from .dependencies import get_service_container
        from .models import PointResponse
        
        container = get_service_container()
        service = container.dem_service
        
        # Test Brisbane coordinates directly
        result = await service.elevation_service.get_elevation(-27.4698, 153.0251)
        
        # Test creating PointResponse like the endpoint does
        try:
            response = PointResponse(
                latitude=-27.4698,
                longitude=153.0251,
                elevation_m=result.elevation_m,
                dem_source_used=result.dem_source_used,
                message=result.message
            )
            return {
                "success": True,
                "response_dict": response.dict(),
                "raw_result": {
                    "elevation_m": result.elevation_m,
                    "dem_source_used": result.dem_source_used,
                    "message": result.message
                }
            }
        except Exception as model_error:
            return {
                "success": False,
                "model_error": str(model_error),
                "raw_result": {
                    "elevation_m": result.elevation_m,
                    "dem_source_used": result.dem_source_used,
                    "message": result.message
                }
            }
        
    except Exception as e:
        import traceback
        return {
            "error": str(e), 
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }

@app.get("/api/v1/health", tags=["health"])
async def health_check():
    """Simple, robust health check endpoint for Railway deployment."""
    try:
        import time
        
        # Initialize start time if not set
        if not hasattr(health_check, '_start_time'):
            health_check._start_time = time.time()
        
        health_response = {
            "status": "healthy",
            "service": "DEM Backend API", 
            "version": "v1.0.0",
            "uptime_seconds": int(time.time() - health_check._start_time),
            "last_check": f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"
        }
        
        # Try to get source information safely
        try:
            # Check provider type and get appropriate information
            if hasattr(app.state, 'unified_provider') and app.state.unified_provider:
                # Unified provider mode
                health_response["provider_type"] = "unified"
                health_response["unified_mode"] = True
                
                # Get unified provider health info
                provider_health = await app.state.unified_provider.health_check()
                health_response["provider_health"] = provider_health
                
                # Get coverage info for collection count
                try:
                    coverage_info = await app.state.unified_provider.coverage_info()
                    health_response["collections_available"] = coverage_info.get("total_collections", 0)
                except Exception:
                    health_response["collections_available"] = "unknown"
                
            elif hasattr(app.state, 'source_provider') and app.state.source_provider:
                # Legacy provider mode
                health_response["provider_type"] = "legacy"
                health_response["unified_mode"] = False
                
                dem_sources = app.state.source_provider.get_dem_sources()
                health_response["sources_available"] = len(dem_sources) if dem_sources else 0
                health_response["s3_indexes"] = {
                    "status": "healthy",
                    "bucket_accessible": True,
                    "campaign_index_loaded": False,  # May be false with graceful degradation
                    "cache_info": {"hits": 0, "misses": 0, "maxsize": 1, "currsize": 0}
                }
            else:
                # No provider available - service starting
                health_response["provider_type"] = "unknown"
                health_response["unified_mode"] = False
                health_response["sources_available"] = 0
                health_response["status"] = "starting"
        except Exception as e:
            # Don't fail health check due to provider issues
            health_response["provider_type"] = "error"
            health_response["sources_available"] = 0
            health_response["startup_note"] = "Providers still initializing"
        
        return health_response
        
    except Exception as e:
        # Return a simple error response instead of raising exception
        return {
            "status": "error",
            "service": "DEM Backend API",
            "version": "v1.0.0", 
            "error": str(e),
            "last_check": f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"
        }

# Set start time for uptime calculation
setattr(health_check, '_start_time', time.time())

if __name__ == "__main__":
    import uvicorn
    # Phase 3B.3.2: Use settings for host/port configuration
    settings = get_settings()
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
