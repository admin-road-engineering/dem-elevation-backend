import logging
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

@app.get("/health", tags=["health"])
async def health_check():
    """Detailed health check endpoint."""
    try:
        settings = get_settings()
        
        # Count geodatabase sources (DEM_SOURCES values are dictionaries)
        geodatabase_sources = sum(1 for source in settings.DEM_SOURCES.values() 
                                 if source.get('path', '').lower().endswith('.gdb'))
        geotiff_sources = len(settings.DEM_SOURCES) - geodatabase_sources
        
        return {
            "status": "healthy",
            "dem_sources_configured": len(settings.DEM_SOURCES),
            "geodatabase_sources": geodatabase_sources,
            "geotiff_sources": geotiff_sources,
            "default_dem": settings.DEFAULT_DEM_ID or "first configured source",
            "geodatabase_auto_discovery": settings.GDB_AUTO_DISCOVER,
            "cache_size_limit": settings.CACHE_SIZE_LIMIT,
            "available_drivers": settings.GDB_PREFERRED_DRIVERS
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001) 