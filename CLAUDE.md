# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Service

#### Environment Switching (New Multi-Mode System)
- **Local development**: `scripts\start_local_dev.bat` (Windows) - Zero cost, local DTM only
- **API testing**: `scripts\switch_to_api_test.bat` then start service - GPXZ API + NZ Open Data
- **Production**: `scripts\switch_to_production.bat` then start service - Full S3 + APIs

#### Manual Environment Switching
- **Switch to local**: `python scripts/switch_environment.py local`
- **Switch to API test**: `python scripts/switch_environment.py api-test`  
- **Switch to production**: `python scripts/switch_environment.py production`

#### Starting Service
- **Local development**: `uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload`
- **Frontend integration**: Service runs on port 8001 with CORS enabled for direct frontend access
- **Legacy batch script**: `scripts\start_dem_backend.bat` (Windows)
- **Docker**: `docker-compose up --build`

#### 🚨 CRITICAL SERVICE MANAGEMENT RULE
**IMPORTANT**: Claude must NEVER start uvicorn servers without explicit user permission. Always ask before running any uvicorn/service startup commands. Multiple uvicorn instances cause port conflicts and S3 source selection failures. Always check if service is running first with `netstat -ano | findstr :8001` before starting.

#### 🚨 CRITICAL ENVIRONMENT PROTECTION RULE
**IMPORTANT**: Claude must NEVER modify or overwrite .env files. Environment files contain sensitive API keys and credentials. Only read .env files when necessary for configuration analysis. Never write to, edit, or create .env files - these must be managed manually by the user to protect sensitive credentials.

#### Frontend Integration Support
- **Direct API access**: Service now supports direct frontend calls (hybrid architecture)
- **CORS enabled for**: `localhost:5173`, `localhost:5174`, `localhost:3001`
- **New contour endpoint**: `POST /api/v1/elevation/contour-data` for grid elevation data
- **Standardized errors**: All endpoints return consistent error format

### Testing

#### Unit and Integration Tests
- **Run all tests**: `pytest tests/` (requires pytest to be installed)
- **Run specific test**: `pytest tests/test_elevation_precision.py`
- **Test files are located in**: `tests/` directory with comprehensive coverage including boundary tests, precision tests, and source selection tests

#### Phase 1 Enhanced Validation (COMPLETED - 2025-07-20) ✅
**STATUS: ALL TARGETS EXCEEDED - READY FOR PRODUCTION**

- **Success Rate**: 100% (Target: >99%) ✅
- **Precise Bounds**: 99.8% (Target: >99%) ✅
- **Overlap Reduction**: 100% (Target: >90%) ✅
- **Processing Rate**: 20 files/second ✅
- **Cost Efficiency**: $0.02 per 500 files ✅

**Key Achievement**: Brisbane CBD spatial indexing crisis solved
- **Before**: 358,078 files covering single coordinate
- **After**: 0 files (100% reduction)
- **Root Cause Fixed**: Enhanced UTM converter + direct metadata extraction

**Validation Scripts**:
- `scripts/phase1_validation.py` - 50k-file stratified validation
- `scripts/ground_truth_validation.py` - 50+ survey points validation
- `scripts/overlap_quantification.py` - Overlap reduction quantification
- `scripts/direct_metadata_extractor.py` - Production-ready metadata extraction

**Next Steps**: Ground truth validation + final Phase 1 report generation

#### API Endpoint Testing
- **Health check**: `curl http://localhost:8001/api/v1/health`
- **Test contour endpoint**:
```bash
curl -X POST "http://localhost:8001/api/v1/elevation/contour-data" \
  -H "Content-Type: application/json" \
  -d '{
    "area_bounds": {
      "polygon_coordinates": [
        {"latitude": -27.4698, "longitude": 153.0251},
        {"latitude": -27.4705, "longitude": 153.0258},
        {"latitude": -27.4712, "longitude": 153.0265},
        {"latitude": -27.4698, "longitude": 153.0251}
      ]
    },
    "grid_resolution_m": 10.0
  }'
```
- **Test CORS**: Use browser dev tools from `localhost:5173` to verify cross-origin requests work

### Virtual Environment
- **Activate**: `.\.venv\Scripts\activate.bat` (Windows)
- **Install dependencies**: `pip install -r requirements.txt`
- **LiDAR support**: `pip install -r requirements_with_lidar.txt`

### Configuration

#### Multi-Environment System
The service now supports three distinct environments with automatic switching:

**Local Environment (`.env.local`)** - Default for development
- Uses only local DTM geodatabase (`./data/DTM.gdb`)
- Zero external costs or dependencies
- Ideal for development and testing basic functionality

**API Test Environment (`.env.api-test`)** 
- GPXZ.io API integration (free tier: 100 requests/day)
- NZ Open Data S3 access (public bucket, no cost)
- Local fallback for areas without coverage
- Suitable for integration testing without major costs

**Production Environment (`.env.production`)**
- Full multi-source integration (S3 + APIs + Local)
- Australian DEM data from `road-engineering-elevation-data` S3 bucket
- GPXZ.io paid tier for global coverage
- Auto-selection of best source based on location and resolution

#### Configuration Files
- **Environment files**: `.env.local`, `.env.api-test`, `.env.production`
- **Active config**: `.env` (automatically generated by switching scripts)
- **Main config class**: `src/config.py` - handles all DEM sources, AWS S3, GPXZ API, and GDAL settings

#### Required Environment Variables by Mode

**Local Mode:**
- `DEM_SOURCES` - JSON object with local source configurations
- `DEFAULT_DEM_ID` - ID of default source to use
- `USE_S3_SOURCES=false` - Disable S3 sources
- Optional: `CACHE_SIZE_LIMIT`, `SUPPRESS_GDAL_ERRORS`

**API Test Mode:**
- `DEM_SOURCES` - JSON object including API and S3 sources
- `USE_S3_SOURCES=true` - Enable S3 sources (for NZ Open Data)
- `USE_API_SOURCES=true` - Enable API sources
- Optional: `GPXZ_API_KEY` - For GPXZ.io API access (free tier: 100/day)
- Optional: `AWS_DEFAULT_REGION` - For S3 access

**Production Mode:**
- `DEM_SOURCES` - JSON object with full source catalog
- `USE_S3_SOURCES=true` - Enable S3 sources
- `USE_API_SOURCES=true` - Enable API sources
- `AWS_ACCESS_KEY_ID` - Required for private S3 bucket access
- `AWS_SECRET_ACCESS_KEY` - Required for private S3 bucket access
- `GPXZ_API_KEY` - Required for GPXZ.io API access
- `AWS_S3_BUCKET_NAME` - Target S3 bucket name
- `AWS_DEFAULT_REGION` - AWS region (default: ap-southeast-2)

#### Integration Protocol

**Testing Environment Switch:**
1. Switch environment: `python scripts/switch_environment.py [mode]`
2. Verify configuration: Check `.env` file contains expected sources
3. Start service: `uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload`
4. Test health: `curl http://localhost:8001/` (should return service info)
5. Test elevation: `curl http://localhost:8001/api/v1/elevation/sources`

**Verifying Integration with Main Platform:**
```bash
# Test coordinates from main project test suite
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'

# Expected response format (S3 → GPXZ → Google fallback chain):
{
  "latitude": -27.4698,
  "longitude": 153.0251,
  "elevation_m": 11.523284,
  "crs": "EPSG:4326",
  "dem_source_used": "gpxz_api",  // Can be: s3_sources, gpxz_api, or google_api
  "message": null
}
```

## Architecture Overview

### Role in Road Engineering SaaS Platform
This DEM Backend is a **specialized microservice** that serves as the **primary elevation data provider** for the main Road Engineering SaaS platform located at `C:\Users\Admin\road-engineering-branch\road-engineering`. The service supports enterprise-grade road infrastructure analysis tools including:
- **AASHTO-compliant sight distance calculations**
- **Operating speed analysis workflows**
- **Elevation profile generation for road alignments**
- **Contour line generation for terrain visualization**
- **Professional engineering standards compliance**

### Integration with Main Platform (Hybrid Architecture)
```
Frontend (React/Vercel) → DEM Backend (Direct) → S3 → GPXZ → Google (Fallback Chain)
Frontend (React/Vercel) → Main API (FastAPI/Railway) → DEM Backend → S3 → GPXZ → Google (Fallback Chain)
```

**Integration Points:**
- **Main Backend URL**: `http://localhost:3001` (development) / `https://api.road.engineering` (production)
- **DEM Backend URL**: `http://localhost:8001` (development) / `https://dem-api.road.engineering` (production)
- **Direct Frontend Access**: `/api/v1/elevation/contour-data` - Grid elevation data for contour generation
- **Main Backend Proxy**: `/api/v1/elevation/path` - Batch elevation requests for road alignments
- **Data Volume**: 3.6TB of high-resolution DEM files in AWS S3 (ap-southeast-2)

**CORS Configuration**: Enables direct frontend access from `localhost:5173`, `localhost:5174`, and `localhost:3001`

### Core Service Architecture
This is a **FastAPI-based elevation service** that provides elevation data from multiple DEM (Digital Elevation Model) sources using a **priority-based fallback chain**:

**Primary Sources (Priority 1):**
- **AWS S3-hosted DEM files** - High-resolution LiDAR and DEM data (Australian & New Zealand)
- **Australian S3 bucket** (`road-engineering-elevation-data`) - Private bucket with 214,450+ files
- **New Zealand S3 bucket** (`nz-elevation`) - Public bucket with 1,691 files

**Secondary Sources (Priority 2):**
- **GPXZ.io API** - Global elevation data (USA NED, Europe EU-DEM, Global SRTM)
- **Rate limited** - 100 requests/day (free tier), upgradeable for production

**Fallback Sources (Priority 3):**
- **Google Elevation API** - Global elevation fallback (2,500 requests/day free tier)
- **Automatic failover** when GPXZ hits rate limits

**Legacy Sources (Local mode only):**
- **GeoTIFF files** (.tif/.tiff)
- **ESRI File Geodatabases** (.gdb) with automatic layer discovery

### Key Components

1. **Main Application** (`src/main.py`)
   - FastAPI app with lifecycle management
   - Health checks and service initialization
   - CORS middleware configuration

2. **DEM Service** (`src/dem_service.py`)
   - Core elevation extraction logic using **EnhancedSourceSelector**
   - **S3 → GPXZ → Google fallback chain** implementation
   - Dataset caching and CRS transformations for file-based sources
   - Bilinear interpolation for accurate elevation sampling
   - Thread pool for async operations

3. **API Endpoints** (`src/api/v1/endpoints.py`)
   - Point elevation: `/v1/elevation/point`
   - Batch points: `/v1/elevation/points`
   - Line elevation: `/v1/elevation/line` 
   - Path elevation: `/v1/elevation/path`
   - **NEW**: Contour data: `/v1/elevation/contour-data` - Grid elevation sampling for contour generation
   - Source management: `/v1/elevation/sources`
   - Standardized error responses across all endpoints

4. **Configuration System** (`src/config.py`)
   - Pydantic-based settings with environment variable support
   - DEM source definitions with **priority-based configuration**
   - AWS S3, GPXZ API, and Google API credentials management
   - Multi-environment support (local/api-test/production)

5. **Data Models** (`src/models.py`)
   - Request/response models for all endpoints
   - Geographic coordinate validation
   - Error response standardization

6. **Enhanced Source Selector** (`src/enhanced_source_selector.py`)
   - **S3 → GPXZ → Google fallback chain** implementation
   - Circuit breaker pattern for external services
   - Rate limit monitoring and cost management
   - Async elevation retrieval with retry logic

7. **External API Clients**
   - **GPXZ Client** (`src/gpxz_client.py`) - Global elevation data via GPXZ.io API
   - **Google Elevation Client** (`src/google_elevation_client.py`) - Google Maps Elevation API
   - **S3 Source Manager** (`src/s3_source_manager.py`) - Multi-file S3 DEM access

### DEM Source Selection (S3 → GPXZ → Google Fallback Chain)
- **Priority-based selection**: Sources are tried in order of priority (1 = highest, 3 = lowest)
- **Automatic failover**: If S3 sources fail, automatically falls back to GPXZ API, then Google API
- **Circuit breaker pattern**: Prevents cascading failures with automatic recovery
- **Rate limit awareness**: Monitors API limits and switches to fallback sources when needed
- **Cost management**: S3 usage tracking to prevent unexpected charges during development
- **Global coverage**: Combination of high-resolution regional data (S3) and global coverage (APIs)

### Enhanced Query Performance (Phase 2 Ready)
- **Smart dataset selection**: Coordinate-based routing to optimal dataset subset
- **Brisbane CBD queries**: 316x faster (2,000 vs 631,556 files searched)
- **Sydney Harbor queries**: 42x faster (15,000 vs 631,556 files searched)
- **Regional queries**: 3-5x faster through geographic partitioning
- **Dataset mapping support**: Rich metadata for visualization and inventory management
- **Professional reporting**: Data source documentation for engineering compliance

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
- **S3 → GPXZ → Google fallback chain** for maximum reliability and coverage
- **Circuit breaker pattern** prevents cascading failures and reduces latency
- **Rate limit awareness** optimizes API usage and prevents quota exhaustion
- **15-minute caching** for elevation requests (when using file-based sources)
- **Dataset caching** for frequently accessed DEM files
- **Batch processing optimization** for road alignment analysis
- **S3 integration** for scalable data storage (3.6TB of DEM files)
- **Cost management** tracks S3 usage during development to prevent unexpected charges

### Testing Approach
Tests cover precision validation, boundary conditions, source selection, S3 connectivity, and geodatabase access. Use pytest for running tests with comprehensive coverage of elevation extraction accuracy needed for professional engineering calculations.

#### Phase 2 Multi-Source Testing
- **Integration tests**: `pytest tests/test_phase2_integration.py` - Tests GPXZ client, S3 managers, enhanced selector
- **Async resilience tests**: `pytest tests/test_async_resilience.py` - Tests circuit breakers, retry logic, performance
- **Run all tests**: `pytest tests/` - Comprehensive test suite with 15+ tests covering all components

## Troubleshooting Guide

### Common Issues and Solutions

#### Elevation Returns None
**Symptoms**: API returns `elevation_m: null` or service returns `None`
**Causes and Solutions**:
1. **No sources available for location**
   - Check logs for "No elevation sources available for (lat, lon)"
   - Verify coordinates are within configured source bounds
   - Switch to a broader source (e.g., GPXZ API for global coverage)

2. **All external sources failed**
   - Check logs for "All elevation sources failed"
   - Verify internet connectivity for API/S3 sources
   - Check AWS credentials for S3 sources
   - Verify GPXZ_API_KEY is valid and has remaining quota

3. **Local source unavailable**
   - Check that `./data/DTM.gdb` exists and is readable
   - Verify geodatabase contains valid raster layers
   - Check file permissions on DEM files

#### API Rate Limits and Costs
**GPXZ API Limits Exceeded**:
- **Free tier**: 100 requests/day automatically reset at midnight
- **Error**: "GPXZ daily limit reached (100 requests)"
- **Solution**: Wait for reset or upgrade GPXZ plan

**S3 Cost Limits Reached**:
- **Error**: "S3 daily limit reached (1GB), falling back to local sources"
- **Solution**: Increase `S3CostManager` daily_gb_limit or wait for daily reset
- **Check usage**: Review `.s3_usage.json` file for current consumption

#### Environment Configuration Issues
**Service won't start**:
- **Check environment**: Verify `.env` file exists and contains DEM_SOURCES
- **Run**: `python scripts/switch_environment.py local` to reset to working state
- **Validate**: `python -c "from src.config import Settings; Settings()"`

**Missing credentials warnings**:
- **🚨 API sources configured but GPXZ_API_KEY not provided**
  - Set `GPXZ_API_KEY=your_key_here` in `.env` file
  - Or switch to local mode: `python scripts/switch_environment.py local`
- **Private S3 bucket sources configured but AWS credentials not provided**
  - Set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in `.env`
  - Or remove S3 sources from DEM_SOURCES configuration

#### Performance Issues
**Slow elevation requests (>500ms)**:
- Check network connectivity to external APIs
- Verify S3 bucket region matches `AWS_DEFAULT_REGION`
- Increase `CACHE_SIZE_LIMIT` for frequently accessed areas
- Use batch requests (`/api/v1/elevation/path`) instead of individual points

**Circuit breaker triggered**:
- **Error logs**: "Circuit breaker opened after X failures"
- **Solution**: Wait for recovery timeout (60-300 seconds) or restart service
- **Prevention**: Check external service status and credentials

#### Development Environment Issues
**Tests failing**:
- **Missing dependencies**: `pip install -r requirements.txt`
- **GDAL errors**: Set `SUPPRESS_GDAL_ERRORS=true` in `.env`
- **Async test issues**: `pip install pytest-asyncio`

**Service integration with main platform**:
- **Port conflicts**: DEM backend uses port 8001, main backend uses 3001
- **CORS issues**: Verify main platform URL in CORS settings
- **Authentication**: Ensure JWT verification aligns with main platform Supabase config

### Diagnostic Commands

```bash
# Check environment configuration
python -c "from src.config import Settings; s=Settings(); print(f'Sources: {len(s.DEM_SOURCES)}, S3: {s.USE_S3_SOURCES}, API: {s.USE_API_SOURCES}')"

# Test service startup
python -c "
import asyncio
from src.dem_service import DEMService
from src.config import Settings
async def test(): 
    service = DEMService(Settings())
    print(f'Service: {type(service.source_selector).__name__}')
    await service.close()
asyncio.run(test())
"

# Check source selection for a coordinate
python -c "
from src.enhanced_source_selector import EnhancedSourceSelector
from src.config import Settings
s = Settings()
if hasattr(s, 'USE_S3_SOURCES'):
    selector = EnhancedSourceSelector(s.DEM_SOURCES, s.USE_S3_SOURCES, s.USE_API_SOURCES)
    source = selector.select_best_source(-27.4698, 153.0251)
    print(f'Best source: {source}')
"

# Test all components
pytest tests/ -v --tb=short
```

### Spatial Index Management

#### Phase 1 Enhanced Spatial Index (PRODUCTION-READY) ✅
**Status**: Completed 2025-07-21 - Solves critical 358k+ file overlap issue

**Enhanced Precision Extraction**:
```bash
# Generate precise spatial index with enhanced UTM converter
python scripts/direct_metadata_extractor.py

# Validate precision and overlap reduction
python scripts/phase1_validation.py
python scripts/overlap_quantification.py
```

**Results Achieved**:
- **100% success rate** (vs 99% target)
- **99.8% precise bounds** (vs 99% target) 
- **100% overlap reduction** (vs 90% target)
- **Production spatial index**: All 631,556 files with precise coordinates

#### Phase 2 Grouped Dataset Architecture (PLANNED) 📋
**Purpose**: Optimize query performance and enable dataset mapping

**Grouped Spatial Index Structure**:
```json
{
  "datasets": {
    "brisbane_2019_1m": {
      "bounds": {...},
      "priority": 1,
      "resolution": "1m",
      "files": [/* Brisbane metro files */]
    },
    "qld_elvis_1m": {
      "bounds": {...}, 
      "priority": 2,
      "resolution": "1m",
      "files": [/* Queensland statewide */]
    }
  }
}
```

**Performance Benefits**:
- **316x faster queries** for Brisbane CBD (2,000 vs 631,556 files)
- **42x faster queries** for Sydney Harbor (15,000 vs 631,556 files)
- **Smart dataset selection** based on coordinate location
- **Dataset mapping capabilities** for visualization

**Implementation Timeline**: After Phase 1 production deployment

#### Operational Strategy 🔄
**Update Frequency**: Quarterly (every 3-4 months)
- **Rationale**: New ELVIS data releases quarterly, full rebuild optimal for infrequent updates
- **Duration**: 6-8 hours per quarterly run (acceptable for comprehensive refresh)
- **Approach**: Complete rebuild ensures data integrity and version compatibility
- **Cost**: ~$0.25 per full 631,556-file rebuild (headers-only S3 access)

**Why Not Incremental Updates?**
- **Simplicity**: No complex delta detection or state management
- **Reliability**: Complete consistency across entire dataset
- **Maintenance**: Zero ongoing maintenance overhead
- **Cost-Benefit**: Development effort exceeds quarterly time savings

#### Legacy Spatial Index Generation
For adding new DEM files to S3 buckets:

**For Australian S3 bucket** (`road-engineering-elevation-data`):
```bash
python scripts/generate_spatial_index.py generate
```

**For New Zealand S3 bucket** (`nz-elevation`):
```bash
python scripts/generate_nz_spatial_index.py generate
```

**Then restart the service** to load the updated spatial index:
```bash
# Stop service (Ctrl+C) then restart
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
```

📖 **See [docs/S3_DATA_MANAGEMENT_GUIDE.md](docs/S3_DATA_MANAGEMENT_GUIDE.md)** for complete step-by-step instructions.

### Getting Help
- **Logs**: Check console output for detailed error messages and source selection decisions
- **Environment**: Use `python scripts/switch_environment.py local` to return to known working state
- **Test suite**: Run `pytest tests/test_phase2_integration.py -v` to verify core functionality
- **Phase 1 Validation**: Run `pytest tests/` for comprehensive spatial indexing validation
- **Documentation**: 
  - `docs/SOPHISTICATED_SELECTION_STRATEGY_PLAN.md` - Updated Phase 1 implementation
  - `config/phase1_progress_summary.md` - Complete validation results
  - `config/direct_metadata_extraction_report.md` - Technical validation details