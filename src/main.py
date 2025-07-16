import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os

from src.config import get_settings, validate_environment_configuration
from src.api.v1.endpoints import router as elevation_router, init_dem_service
from src.logging_config import setup_logging

# Setup structured logging based on environment
setup_logging(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    service_name="dem-backend"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events."""
    # Startup
    logger.info("Starting DEM Elevation Service...", extra={"event": "startup_begin"})
    try:
        settings = get_settings()
        
        # Validate configuration and log results
        validate_environment_configuration(settings)
        
        init_dem_service(settings)
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
        # Clean up DEM service resources
        from src.api.v1.endpoints import dem_service
        if dem_service:
            if hasattr(dem_service, 'close') and callable(dem_service.close):
                await dem_service.close()
            else:
                dem_service.close()
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

# Import models for legacy endpoint
from src.models import PointsRequest, StandardResponse
from src.api.v1.endpoints import get_dem_service

# Legacy compatibility endpoint
@app.post("/api/get_elevations", tags=["legacy"])
async def get_elevations_legacy(request: dict):
    """Legacy batch elevation endpoint for backward compatibility."""
    from src.api.v1.endpoints import get_elevation_points
    
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

@app.get("/api/v1/health", tags=["health"])
async def health_check():
    """Standardized health check endpoint."""
    try:
        import time
        settings = get_settings()
        
        return {
            "status": "healthy",
            "service": "DEM Backend API",
            "version": "v1.0.0",
            "uptime_seconds": int(time.time() - getattr(health_check, '_start_time', time.time())),
            "sources_available": len(settings.DEM_SOURCES),
            "last_check": f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")

# Set start time for uptime calculation
setattr(health_check, '_start_time', time.time())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001) 