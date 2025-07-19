# Enhanced DEM Configuration for Higher Resolution Data

## Overview
This configuration enables automatic source selection based on priority, resolution, and coverage bounds for the new higher resolution data from the Elevation Team.

## Key Features
- **Automatic Source Selection**: The system automatically chooses the best available source for each location
- **Priority-Based Selection**: Sources are prioritized by resolution, data quality, and manual priority
- **Bounds-Based Coverage**: Sources include geographic bounds for precise coverage detection
- **Metadata-Rich Sources**: Each source includes resolution, data type, year, and region information

## Configuration Example

Create or update your `.env` file with the following configuration:

```env
# Enhanced DEM Elevation Service Configuration
# This configuration includes priority-based source selection and higher resolution data

# Configure DEM sources with priority, bounds, and metadata
# Note: JSON must be on a single line in .env files
DEM_SOURCES={
  "qld_50cm_lidar": {
    "path": "s3://your-high-res-bucket/queensland/50cm/QLD_50cm_LiDAR_Region1.tif",
    "resolution_m": 0.5,
    "priority": 1,
    "bounds": {"west": 153.0, "south": -28.2, "east": 153.8, "north": -27.8},
    "crs": "EPSG:28356",
    "data_source": "LiDAR",
    "year": 2024,
    "region": "Queensland Gold Coast",
    "description": "Queensland 50cm LiDAR - Highest resolution"
  },
  "tas_50cm_lidar": {
    "path": "s3://your-high-res-bucket/tasmania/50cm/TAS_50cm_LiDAR_Region1.tif",
    "resolution_m": 0.5,
    "priority": 1,
    "bounds": {"west": 147.0, "south": -43.5, "east": 148.5, "north": -42.0},
    "crs": "EPSG:28355",
    "data_source": "LiDAR",
    "year": 2024,
    "region": "Tasmania",
    "description": "Tasmania 50cm LiDAR - Highest resolution"
  },
  "qld_1m_lidar": {
    "path": "s3://your-high-res-bucket/queensland/1m/QLD_1m_LiDAR_Region1.tif",
    "resolution_m": 1.0,
    "priority": 2,
    "bounds": {"west": 138.0, "south": -29.0, "east": 154.0, "north": -10.0},
    "crs": "EPSG:28356",
    "data_source": "LiDAR",
    "year": 2024,
    "region": "Queensland",
    "description": "Queensland 1m LiDAR - High resolution"
  },
  "existing_dtm_gdb": {
    "path": "s3://roadengineer-dem-files/DTM.gdb",
    "resolution_m": 5.0,
    "priority": 3,
    "bounds": {"west": 138.0, "south": -44.0, "east": 154.0, "north": -10.0},
    "crs": null,
    "data_source": "Photogrammetry",
    "year": 2023,
    "region": "Australia East Coast",
    "description": "Existing DTM from geodatabase - fallback coverage"
  },
  "au_national_30m": {
    "path": "s3://roadengineer-dem-files/AU_National_30m_SRTM.tif",
    "resolution_m": 30.0,
    "priority": 4,
    "bounds": {"west": 110.0, "south": -44.0, "east": 160.0, "north": -9.0},
    "crs": "EPSG:4326",
    "data_source": "SRTM",
    "year": 2022,
    "region": "Australia National",
    "description": "National 30m SRTM - Continental coverage"
  }
}

# Set automatic source selection as default
DEFAULT_DEM_ID=qld_50cm_lidar
AUTO_SELECT_BEST_SOURCE=true

# Geodatabase settings
GDB_AUTO_DISCOVER=true
GDB_PREFERRED_DRIVERS=["OpenFileGDB", "FileGDB"]

# Performance settings
CACHE_SIZE_LIMIT=10
MAX_WORKER_THREADS=20
DATASET_CACHE_SIZE=10

# GDAL Error Handling
SUPPRESS_GDAL_ERRORS=true
GDAL_LOG_LEVEL=ERROR

# AWS S3 Configuration - Existing bucket
AWS_S3_BUCKET_NAME=roadengineer-dem-files
AWS_ACCESS_KEY_ID=YOUR_EXISTING_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY=YOUR_EXISTING_SECRET_ACCESS_KEY

# AWS S3 Configuration - New high-resolution bucket
AWS_S3_BUCKET_NAME_HIGH_RES=your-high-res-bucket-name
# Note: Uses same AWS credentials as above

# Google Elevation API Configuration (Fallback)
# GOOGLE_ELEVATION_API_KEY=YOUR_GOOGLE_API_KEY
```

## New Configuration Fields Explained

### Source-Level Fields
- **`resolution_m`**: Spatial resolution in meters (used for automatic quality scoring)
- **`priority`**: Manual priority ranking (1 = highest priority)
- **`bounds`**: Geographic bounds as `{"west": x, "south": y, "east": x, "north": y}`
- **`data_source`**: Data source type: "LiDAR", "Photogrammetry", "SAR", "SRTM"
- **`year`**: Year of data collection (newer data scores higher)
- **`region`**: Human-readable region identifier

### Global Settings
- **`AUTO_SELECT_BEST_SOURCE`**: Enable automatic source selection (true/false)
- **`AWS_S3_BUCKET_NAME_HIGH_RES`**: New bucket for high-resolution data

## How Source Selection Works

1. **Location Check**: Only sources with bounds that contain the query point are considered
2. **Priority Scoring**: Sources are scored based on:
   - Manual priority (highest weight)
   - Resolution (higher resolution = higher score)
   - Data source quality (LiDAR > Photogrammetry > SAR > SRTM)
   - Recency (newer data = higher score)
3. **Best Source Selection**: The source with the highest score is automatically selected

## New API Endpoints

### Source Selection
```bash
POST /v1/elevation/select-source
{
  "latitude": -28.002,
  "longitude": 153.414,
  "prefer_high_resolution": true,
  "max_resolution_m": 5.0
}
```

### Coverage Summary
```bash
GET /v1/elevation/coverage
```

### Point Elevation (with auto-selection)
```bash
POST /v1/elevation/point
{
  "latitude": -28.002,
  "longitude": 153.414
}
# System automatically selects best source
```

## Migration Steps

1. **Set up new S3 bucket** following the Elevation Team's instructions
2. **Update configuration** with the new sources and metadata
3. **Test source selection** using the new API endpoints
4. **Verify automatic selection** is working correctly
5. **Update client applications** to use the new capabilities

## Testing the Configuration

You can test the source selection with:

```bash
curl -X POST "http://localhost:8001/v1/elevation/select-source" \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": -28.002,
    "longitude": 153.414,
    "prefer_high_resolution": true
  }'
```

This will return which source would be selected for that location and why. 