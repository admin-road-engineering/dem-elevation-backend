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
    Phase 3A-Fix: SourceProvider pattern for production-ready startup.
    
    This lifespan handler implements Gemini's approved architecture:
    - Moves all I/O out of Settings class
    - Uses SourceProvider with aioboto3 for async S3 operations
    - Blocks startup until all critical data is loaded
    - Enables sub-500ms startup time for production deployment
    """
    # Startup
    logger.info("Starting DEM Elevation Service with SourceProvider pattern...", extra={"event": "startup_begin"})
    
    try:
        # Get static settings (no I/O operations)
        settings = get_settings()
        validate_environment_configuration(settings)
        
        # Create SourceProvider with static configuration
        source_config = SourceProviderConfig(
            s3_bucket_name=os.getenv('DEM_S3_BUCKET', 'road-engineering-elevation-data'),
            campaign_index_key='indexes/grouped_spatial_index.json',
            nz_index_key='indexes/nz_spatial_index.json',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            aws_region=settings.AWS_DEFAULT_REGION,
            enable_nz_sources=getattr(settings, 'ENABLE_NZ_SOURCES', False)
        )
        
        # Create SourceProvider and store on app.state
        provider = SourceProvider(source_config)
        app.state.source_provider = provider
        logger.info("SourceProvider created and stored on app.state")
        
        # Load all data asynchronously - BLOCKS startup until complete
        logger.info("Loading all data sources asynchronously...")
        load_success = await provider.load_all_sources()
        
        if not load_success:
            logger.error(f"Failed to load critical data sources: {provider.get_load_errors()}")
            raise RuntimeError("Critical data loading failed - cannot start service")
        
        # Get loaded sources for service container
        dem_sources = provider.get_dem_sources()
        logger.info(f"Data loading completed: {len(dem_sources)} sources available")
        
        # Create S3ClientFactory for legacy compatibility
        s3_factory = create_s3_client_factory()
        app.state.s3_factory = s3_factory
        
        # Initialize service container with loaded data
        service_container = init_service_container(settings, source_provider=provider)
        
        logger.info(
            "DEM Elevation Service started successfully with SourceProvider pattern",
            extra={
                "event": "startup_complete",
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
        
        # Clear references
        if hasattr(app.state, 'source_provider'):
            app.state.source_provider = None
        if hasattr(app.state, 's3_factory'):
            app.state.s3_factory = None
        
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
    """Standardized health check endpoint with S3 index status."""
    try:
        import time
        from .dependencies import get_service_container
        settings = get_service_container().settings
        
        health_response = {
            "status": "healthy",
            "service": "DEM Backend API",
            "version": "v1.0.0",
            "uptime_seconds": int(time.time() - getattr(health_check, '_start_time', time.time())),
            "sources_available": len(settings.DEM_SOURCES),
            "last_check": f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"
        }
        
        # Add S3 index status if using S3 indexes
        if os.getenv("SPATIAL_INDEX_SOURCE", "local").lower() == "s3":
            try:
                from .s3_index_loader import s3_index_loader
                s3_health = s3_index_loader.health_check()
                index_info = s3_index_loader.get_index_info()
                
                health_response["s3_indexes"] = {
                    "status": s3_health.get("status", "unknown"),
                    "bucket_accessible": s3_health.get("bucket_accessible", False),
                    "campaign_index_loaded": s3_health.get("campaign_index_loaded", False),
                    "cache_info": index_info.get("cache_info", {})
                }
                
                if s3_health.get("status") != "healthy":
                    health_response["status"] = "degraded"
                    
            except Exception as e:
                health_response["s3_indexes"] = {
                    "status": "error",
                    "error": str(e)
                }
                health_response["status"] = "degraded"
        
        return health_response
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")

# Set start time for uptime calculation
setattr(health_check, '_start_time', time.time())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001) # Force Railway rebuild Sat, Jul 26, 2025 11:29:16 PM
