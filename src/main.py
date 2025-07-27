import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os

from .config import get_settings, validate_environment_configuration
from .api.v1.endpoints import router as elevation_router
from .api.v1.dataset_endpoints import router as dataset_router
from .api.v1.campaigns_endpoints import router as campaign_router
from .dependencies import init_service_container, close_service_container, get_dem_service
from .logging_config import setup_logging

# Setup structured logging based on environment
setup_logging(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    service_name="dem-backend"
)
logger = logging.getLogger(__name__)

async def validate_index_driven_sources(settings):
    """Validate index-driven source configuration and connectivity"""
    logger.info("Validating index-driven DEM sources...")
    
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
        
        logger.info(
            "Index-driven source validation successful",
            extra={
                "event": "index_validation_success",
                "total_sources": source_count,
                "s3_sources": s3_sources,
                "api_sources": api_sources
            }
        )
        
        # If we have S3 sources, validate S3 connectivity using existing loader
        if s3_sources > 0 and os.getenv("SPATIAL_INDEX_SOURCE", "local").lower() == "s3":
            logger.info("Validating S3 connectivity for index-driven S3 sources...")
            try:
                from .s3_index_loader import s3_index_loader
                health_check = s3_index_loader.health_check()
                
                if health_check['status'] == 'healthy':
                    logger.info(f"S3 connectivity confirmed for {s3_sources} campaign sources")
                else:
                    logger.warning(f"S3 connectivity issue, but {s3_sources} sources available via index")
                    
            except Exception as e:
                logger.warning(
                    f"S3 connectivity test failed, but {s3_sources} index-driven sources still available",
                    extra={"error": str(e)}
                )
        
        return True
        
    except Exception as e:
        logger.error(
            "Index-driven source validation failed",
            extra={"event": "index_validation_failed", "error": str(e)},
            exc_info=True
        )
        return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events."""
    # Startup
    logger.info("Starting DEM Elevation Service...", extra={"event": "startup_begin"})
    try:
        settings = get_settings()
        
        # Validate configuration and log results
        validate_environment_configuration(settings)
        
        # CRITICAL: Force DEM_SOURCES property access to trigger S3 campaign loading
        # This ensures S3 campaigns are loaded before ServiceContainer initialization
        source_count = len(settings.DEM_SOURCES)
        logger.info(f"Forced DEM_SOURCES loading: {source_count} sources loaded during startup")
        
        # Validate index-driven sources (replaces legacy S3 validation)
        # This MUST happen before ServiceContainer initialization to load S3 campaigns
        validation_success = await validate_index_driven_sources(settings)
        if not validation_success:
            logger.warning("Source validation had issues, but continuing startup with available sources")
        
        # Initialize dependency injection container AFTER S3 campaigns are loaded
        service_container = init_service_container(settings)
        logger.info(
            "DEM Elevation Service started successfully",
            extra={
                "event": "startup_complete",
                "dem_sources_count": len(settings.DEM_SOURCES),
                "use_s3": getattr(settings, 'USE_S3_SOURCES', False),
                "use_apis": getattr(settings, 'USE_API_SOURCES', False)
            }
        )
        yield
    except Exception as e:
        logger.error(
            "Failed to start DEM service",
            extra={"event": "startup_failed", "error_type": type(e).__name__},
            exc_info=True
        )
        raise e
    
    # Shutdown
    logger.info("Shutting down DEM Elevation Service...", extra={"event": "shutdown_begin"})
    try:
        # Clean up service container and all managed services
        await close_service_container()
        logger.info("DEM Elevation Service shut down successfully", extra={"event": "shutdown_complete"})
    except Exception as e:
        logger.error("Error during shutdown", extra={"event": "shutdown_failed"}, exc_info=True)

# Create FastAPI application
app = FastAPI(
    title="DEM Elevation Service",
    description="A dedicated elevation data service using FastAPI that serves elevation data from Digital Elevation Model (DEM) files and geodatabases",
    version="1.0.0",
    lifespan=lifespan
)

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
