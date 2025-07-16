#!/usr/bin/env python3
"""
Minimal DEM Backend server for testing without geospatial dependencies.
Use this for basic FastAPI testing while setting up proper environment.
"""
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional

# Minimal configuration
CORS_ORIGINS = [
    "http://localhost:3001",
    "http://localhost:5173", 
    "https://road.engineering",
    "https://api.road.engineering"
]

app = FastAPI(
    title="DEM Elevation Service (Minimal)",
    description="Basic DEM Backend for testing - geospatial functionality disabled",
    version="1.0.0-minimal"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request models
class ElevationRequest(BaseModel):
    latitude: float
    longitude: float

class ElevationResponse(BaseModel):
    elevation_m: Optional[float]
    latitude: float
    longitude: float
    source: str
    message: str

# Basic endpoints
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "DEM Elevation Service",
        "status": "running",
        "mode": "minimal",
        "message": "Geospatial packages not available - see SETUP_INSTRUCTIONS.md"
    }

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "mode": "minimal",
        "dem_sources_configured": 0,
        "geospatial_packages": "unavailable",
        "setup_required": "See SETUP_INSTRUCTIONS.md for conda setup"
    }

@app.get("/api/v1/elevation/sources")
async def get_sources():
    """Get available elevation sources"""
    return {
        "sources": {},
        "total_sources": 0,
        "message": "No sources available - geospatial packages not installed",
        "setup_instructions": "Run setup_conda_env.bat or follow SETUP_INSTRUCTIONS.md"
    }

@app.post("/api/v1/elevation/point")
async def get_elevation(request: ElevationRequest) -> ElevationResponse:
    """Get elevation for a single point (minimal mode)"""
    return ElevationResponse(
        elevation_m=None,
        latitude=request.latitude,
        longitude=request.longitude,
        source="unavailable",
        message="Geospatial packages not installed - elevation data unavailable"
    )

@app.get("/setup-status")
async def setup_status():
    """Check setup status"""
    issues = []
    
    # Test package imports
    try:
        import rasterio
        rasterio_ok = True
    except ImportError as e:
        rasterio_ok = False
        issues.append(f"rasterio: {str(e)[:50]}")
    
    try:
        import fiona
        fiona_ok = True
    except ImportError as e:
        fiona_ok = False
        issues.append(f"fiona: {str(e)[:50]}")
    
    # Check data files
    data_files = [
        "./data/DTM.gdb",
        "./data/DTM.tif"
    ]
    
    available_files = []
    for file_path in data_files:
        if os.path.exists(file_path):
            available_files.append(file_path)
    
    return {
        "geospatial_packages": {
            "rasterio": rasterio_ok,
            "fiona": fiona_ok,
            "ready": rasterio_ok and fiona_ok
        },
        "data_files": {
            "available": available_files,
            "total_checked": len(data_files)
        },
        "issues": issues,
        "next_steps": [
            "Install Miniconda",
            "Run: conda env create -f environment.yml",
            "Run: conda activate dem-backend", 
            "Run: uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload"
        ] if issues else ["Ready to use full DEM Backend!"]
    }

if __name__ == "__main__":
    import uvicorn
    print("Starting DEM Backend in minimal mode...")
    print("Install conda environment for full functionality")
    uvicorn.run(app, host="0.0.0.0", port=8001)