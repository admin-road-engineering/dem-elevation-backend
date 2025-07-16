# DEM Backend Scripts Directory

## Simplified Script Structure (Updated)

### 🚀 Essential Startup Scripts

**1. `start_with_geotiff.bat`** - **LOCAL DEVELOPMENT (Recommended)**
- Uses local GeoTIFF files (`./data/dems/dtm.tif`)
- Activates conda environment (dem-backend-fixed)
- Zero cost - no external API calls
- Best for: Daily development and testing

**2. `start_production.bat`** - **PRODUCTION MODE**
- Switches to production environment (S3 + APIs)
- Verifies AWS credentials before starting
- **WARNING**: Incurs AWS S3 and API costs
- Best for: Testing production configuration locally

### 🔧 Environment Management

**3. `switch_environment.py`** - **Core Environment Switcher**
- Usage: `python scripts/switch_environment.py [local|api-test|production]`
- Manages .env configuration switching
- Run this before starting if you need a different environment

**4. `switch_to_api_test.bat`** - Quick switch to API test mode
**5. `switch_to_production.bat`** - Quick switch to production mode

### 🛠️ Utility Scripts

**Data Processing:**
- `convert_gdb_to_tif.py` - Convert geodatabase to GeoTIFF
- `convert_gdb_direct.py` - Direct GDAL conversion
- `check_gdb.py` - Diagnose geodatabase access issues
- `inspect_gdb.py` - Inspect geodatabase contents
- `list_gdb_layers.py` - List all layers in geodatabase

**System Tools:**
- `find_locking_processes.py` - Find processes locking files
- `run_gdal_translate.bat` - Run GDAL translate command
- `switch_to_local_dtm.py` - Legacy local DTM switcher

**Testing:**
- `post_deploy_smoke_test.py` - Production deployment testing

## Quick Start Guide

### For Local Development:
```bash
# You're already using this successfully!
scripts\start_with_geotiff.bat
```

### For Production Testing:
```bash
# This will switch to production config and start server
scripts\start_production.bat
```

### To Change Environments:
```bash
# Switch to API test mode (free tier limits)
scripts\switch_to_api_test.bat

# Switch back to local mode
python scripts\switch_environment.py local

# Then start with your preferred script
scripts\start_with_geotiff.bat
```

## Archived Scripts

The following redundant scripts have been archived to `archived-files/redundant-scripts/`:
- `start_dem_backend.bat` - Replaced by start_with_geotiff.bat
- `start_dem_backend - S3.bat` - Replaced by start_production.bat
- `start_local_dev.bat` - Overlapped with start_with_geotiff.bat
- `start_local_dev_conda.bat` - Redundant with start_with_geotiff.bat

## Environment Modes

- **local**: Zero cost, uses local GeoTIFF files only
- **api-test**: Limited free tier (100 GPXZ requests/day)
- **production**: Full capabilities with S3 + paid APIs