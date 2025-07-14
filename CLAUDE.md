# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Service
- **Local development**: `uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload`
- **Using batch script**: `scripts\start_dem_backend.bat` (Windows)
- **With S3 storage**: `scripts\start_dem_backend - S3.bat`
- **Docker**: `docker-compose up --build`

### Testing
- **Run all tests**: `pytest tests/` (requires pytest to be installed)
- **Run specific test**: `pytest tests/test_elevation_precision.py`
- **Test files are located in**: `tests/` directory with comprehensive coverage including boundary tests, precision tests, and source selection tests

### Virtual Environment
- **Activate**: `.\.venv\Scripts\activate.bat` (Windows)
- **Install dependencies**: `pip install -r requirements.txt`
- **LiDAR support**: `pip install -r requirements_with_lidar.txt`

### Configuration
- **Environment setup**: Copy `env.example` to `.env` and configure DEM sources
- **Main config file**: `src/config.py` - handles DEM sources, AWS S3, and GDAL settings

## Architecture Overview

### Role in Road Engineering SaaS Platform
This DEM Backend is a **specialized microservice** that serves as the **primary elevation data provider** for the main Road Engineering SaaS platform located at `C:\Users\Admin\road-engineering-branch\road-engineering`. The service supports enterprise-grade road infrastructure analysis tools including:
- **AASHTO-compliant sight distance calculations**
- **Operating speed analysis workflows**
- **Elevation profile generation for road alignments**
- **Contour line generation for terrain visualization**
- **Professional engineering standards compliance**

### Integration with Main Platform
```
Frontend (React/Vercel) → Main API (FastAPI/Railway) → DEM Backend (This Service) → S3 DEM Files
```

**Primary Integration Points:**
- **Main Backend URL**: `http://localhost:3001` (development) / `https://api.road.engineering` (production)
- **DEM Backend URL**: `http://localhost:8001` (development) / `https://dem-api.road.engineering` (production)
- **Key Endpoint**: `/api/v1/elevation/path` - Batch elevation requests for road alignments
- **Data Volume**: 3.6TB of high-resolution DEM files in AWS S3 (ap-southeast-2)

### Core Service Architecture
This is a **FastAPI-based elevation service** that provides elevation data from multiple DEM (Digital Elevation Model) sources including:
- **GeoTIFF files** (.tif/.tiff)
- **ESRI File Geodatabases** (.gdb) with automatic layer discovery
- **AWS S3-hosted DEM files** with transparent access (primary production data source)

### Key Components

1. **Main Application** (`src/main.py`)
   - FastAPI app with lifecycle management
   - Health checks and service initialization
   - CORS middleware configuration

2. **DEM Service** (`src/dem_service.py`)
   - Core elevation extraction logic
   - Dataset caching and CRS transformations
   - Bilinear interpolation for accurate elevation sampling
   - Thread pool for async operations

3. **API Endpoints** (`src/api/v1/endpoints.py`)
   - Point elevation: `/v1/elevation/point`
   - Line elevation: `/v1/elevation/line` 
   - Path elevation: `/v1/elevation/path`
   - Source management: `/v1/elevation/sources`
   - Contour data extraction for native DEM points

4. **Configuration System** (`src/config.py`)
   - Pydantic-based settings with environment variable support
   - DEM source definitions with automatic validation
   - AWS S3 and GDAL error handling configuration

5. **Data Models** (`src/models.py`)
   - Request/response models for all endpoints
   - Geographic coordinate validation
   - Error response standardization

### DEM Source Selection
- **Multi-source support**: Configure multiple DEM sources with priority-based selection
- **Automatic source selection**: Service can automatically choose the best source based on location and resolution
- **Source metadata**: Each source includes path, CRS, layer info, and descriptions
- **Fallback mechanisms**: Graceful degradation when primary sources are unavailable

### Geodatabase Handling
- **Auto-discovery**: Automatically finds raster layers in .gdb files using common naming patterns
- **Layer specification**: Option to specify exact layer names for complex geodatabases
- **Driver fallback**: Uses OpenFileGDB and FileGDB drivers with automatic fallback
- **Error suppression**: Configured to suppress non-critical GDAL errors from geodatabase access

### Performance Features
- **Dataset caching**: Keeps recently used DEM datasets in memory (configurable cache size)
- **CRS transformation caching**: Caches coordinate transformations for performance
- **Thread pooling**: Non-blocking I/O operations using FastAPI's thread pool
- **Resource cleanup**: Proper dataset cleanup on service shutdown

### AWS S3 Integration
- **Transparent S3 access**: DEM files can be hosted on S3 with `s3://` paths
- **Credential management**: AWS credentials configured via environment variables
- **Bucket configuration**: Supports multiple S3 buckets for different data tiers

### Data Utilities
- **Scripts directory** contains utilities for:
  - Converting geodatabases to GeoTIFF (`convert_gdb_to_tif.py`)
  - Inspecting geodatabase contents (`inspect_gdb.py`, `list_gdb_layers.py`)
  - Checking DEM availability (`src/check_available_dems.py`)
  - Switching between local/S3 storage (`switch_to_local_dtm.py`)

### Key Dependencies
- **rasterio**: DEM file reading and elevation sampling
- **fiona**: Geodatabase layer discovery and access  
- **pyproj**: CRS transformations and great circle calculations
- **boto3**: AWS S3 access for cloud-hosted DEMs
- **GDAL/OGR**: Underlying geospatial data access (via rasterio/fiona)

## Important Notes

### Environment Configuration
The service requires a `.env` file with DEM_SOURCES configuration. The DEM_SOURCES must be a single-line JSON object mapping source IDs to source configurations with path, crs, layer, and description fields.

**Production DEM Sources Configuration:**
- **Primary**: `s3://roadengineer-dem-files/AU_QLD_LiDAR_1m.tif` (1m resolution LiDAR for Queensland)
- **National**: `s3://roadengineer-dem-files/AU_National_5m_DEM.tif` (5m resolution Australia-wide)
- **SRTM Fallback**: `s3://roadengineer-dem-files/AU_SRTM_1ArcSec.tif` (30m resolution global)
- **Local DTM**: `./data/DTM.gdb` (Local high-resolution geodatabase)

### Integration with Main Platform
**Business Context**: This microservice supports a professional road engineering SaaS platform with tiered pricing:
- **Free Tier**: Basic crash data visualization, limited elevation profiles (10/month)
- **Professional ($49/month)**: Unlimited engineering tools, sight distance analysis
- **Enterprise (Custom)**: API access, batch processing, priority support

**Rate Limiting**: The main platform implements 50-100 requests/hour for engineering endpoints to protect valuable IP and infrastructure costs.

### GDAL Error Handling
The service is configured to suppress non-critical GDAL errors by default (especially from geodatabase access). This can be controlled via `SUPPRESS_GDAL_ERRORS` and `GDAL_LOG_LEVEL` settings.

### Port Configuration
- Default development port: **8001** (chosen to avoid conflicts with main backend on 3001)
- Docker deployment uses port 8000 internally, mapped to host port 8000
- Production deployment: Railway hosting with custom domain `dem-api.road.engineering`

### Performance Considerations
**Critical for Production**: This service handles batch requests of up to 500 elevation points per request from the main platform. Performance optimizations include:
- **15-minute caching** for elevation requests
- **Dataset caching** for frequently accessed DEM files
- **Batch processing optimization** for road alignment analysis
- **S3 integration** for scalable data storage (3.6TB of DEM files)

### Testing Approach
Tests cover precision validation, boundary conditions, source selection, S3 connectivity, and geodatabase access. Use pytest for running tests with comprehensive coverage of elevation extraction accuracy needed for professional engineering calculations.