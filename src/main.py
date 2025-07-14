import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.config import get_settings
from src.api.v1.endpoints import router as elevation_router, init_dem_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events."""
    # Startup
    logger.info("Starting DEM Elevation Service...")
    try:
        settings = get_settings()
        init_dem_service(settings)
        logger.info("DEM Elevation Service started successfully")
        yield
    except Exception as e:
        logger.error(f"Failed to start DEM service: {e}")
        raise e
    
    # Shutdown
    logger.info("Shutting down DEM Elevation Service...")
    try:
        # Clean up DEM service resources
        from src.api.v1.endpoints import dem_service
        if dem_service:
            dem_service.close()
        logger.info("DEM Elevation Service shut down successfully")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

# Create FastAPI application
app = FastAPI(
    title="DEM Elevation Service",
    description="A dedicated elevation data service using FastAPI that serves elevation data from Digital Elevation Model (DEM) files and geodatabases",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
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
        
        # Count geodatabase sources
        geodatabase_sources = sum(1 for source in settings.DEM_SOURCES.values() 
                                 if source.path.lower().endswith('.gdb'))
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