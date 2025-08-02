# Spatial Index Management Guide

## 📊 Overview

The DEM Backend uses **dynamic spatial indexing** to efficiently map geographic coordinates to specific elevation data files in S3 buckets. This system automatically discovers new files and maintains accurate spatial coverage without hardcoded mappings.

## 🔧 Architecture

### Two-Bucket System
- **Australian Data**: `road-engineering-elevation-data` (Private bucket with 1,153 campaigns)
- **New Zealand Data**: `nz-elevation` (Public bucket with 188+ directories)
- **Indexes Storage**: Both indexes stored in private bucket at `/indexes/`

### Dynamic Discovery Approach
- **No Hardcoded Mappings**: Scans entire S3 buckets to discover all .tiff/.tif files
- **Actual Bounds Extraction**: Uses GeoTIFF metadata (rasterio) for precise coordinate bounds
- **Progressive Updates**: New files in buckets are automatically discoverable
- **Fallback Safety**: Incremental updates fall back to full regeneration if needed

## 🚀 Batch File Operations

### Australian S3 Bucket Management

#### Full Regeneration
**File**: `scripts/generate_australian_spatial_index.bat`
**Duration**: 15-30 minutes
**Purpose**: Complete scan of Australian S3 bucket, generates fresh spatial index

```bash
# What it does:
# 1. Discovers all directories with .tif files
# 2. Extracts UTM coordinates from filenames  
# 3. Converts to lat/lon bounds using UTM converter
# 4. Validates and saves to config/spatial_index.json
```

#### Incremental Update
**File**: `scripts/update_australian_spatial_index.bat`
**Duration**: 2-5 minutes  
**Purpose**: Processes only NEW files added since last update

```bash
# What it does:
# 1. Loads existing spatial_index.json
# 2. Compares S3 bucket contents vs processed files
# 3. Processes only files modified after last update timestamp
# 4. Merges new files into existing index structure
```

### New Zealand S3 Bucket Management

#### Full Regeneration
**File**: `generate_nz_dynamic_index.bat` (root directory)
**Duration**: 10-20 minutes
**Purpose**: Complete scan using dynamic S3 crawling with GeoTIFF metadata extraction

```bash
# What it does:
# 1. Discovers all 188+ directories with .tiff files
# 2. Opens each GeoTIFF with rasterio to extract actual bounds
# 3. Transforms NZTM coordinates to WGS84 lat/lon
# 4. Saves to config/nz_spatial_index_dynamic.json
```

#### Incremental Update  
**File**: `scripts/update_nz_spatial_index.bat`
**Duration**: 1-3 minutes
**Purpose**: Fast detection of only new files with actual bounds extraction

```bash
# What it does:
# 1. Loads existing nz_spatial_index_dynamic.json
# 2. Scans NZ bucket for files newer than last update
# 3. Extracts actual GeoTIFF bounds using rasterio
# 4. Updates index with new files and recalculates coverage
```

## 📁 Generated Index Files

### Australian Index Structure
**File**: `config/spatial_index.json`
```json
{
  "generated_at": "2025-01-31T12:00:00.000Z",
  "bucket": "road-engineering-elevation-data", 
  "utm_zones": {
    "z56": {
      "files": [...],
      "coverage_bounds": {...},
      "file_count": 800
    }
  },
  "file_count": 1153,
  "coverage_summary": {...}
}
```

### New Zealand Index Structure  
**File**: `config/nz_spatial_index.json`
```json
{
  "generated_at": "2025-08-02T02:23:48.000Z",
  "bucket": "nz-elevation",
  "method": "campaign_based_grouping_with_actual_bounds",
  "campaigns": {
    "auckland-north_2016-2018_dem": {
      "files": [...],
      "coverage_bounds": {...},
      "file_count": 379,
      "region": "auckland",
      "survey": "auckland-north_2016-2018",
      "data_type": "DEM",
      "resolution": "1m"
    },
    "canterbury_2020-2023_dem": {
      "files": [...],
      "coverage_bounds": {...},
      "file_count": 2546,
      "region": "canterbury",
      "survey": "canterbury_2020-2023", 
      "data_type": "DEM",
      "resolution": "1m"
    }
  },  
  "file_count": 29758,
  "coverage_summary": {...}
}
```

## 🔄 Production Deployment Workflow

### Initial Setup
```bash
# 1. Generate complete spatial indexes
generate_nz_dynamic_index.bat
scripts/generate_australian_spatial_index.bat

# 2. Upload NZ index to S3
python upload_nz_index.py

# 3. Deploy to Railway
railway up --detach

# 4. Enable NZ sources
railway variables --set "ENABLE_NZ_SOURCES=true"
```

### Regular Maintenance 
```bash
# Weekly: Check for new files (recommended)
scripts/update_nz_spatial_index.bat
scripts/update_australian_spatial_index.bat

# Upload updated NZ index if new files found
python upload_nz_index.py

# Monthly: Full regeneration (optional, for validation)
generate_nz_dynamic_index.bat
scripts/generate_australian_spatial_index.bat
```

## 🛠️ Technical Details

### Dynamic Discovery Process

#### Australian Bucket Scanning
1. **S3 Paginated Listing**: Scans entire bucket using boto3 paginator
2. **File Type Filtering**: Identifies .tif files in directory structure
3. **UTM Coordinate Extraction**: Parses filenames for UTM zone and coordinates
4. **Bounds Calculation**: Converts UTM to lat/lon using proper coordinate transformation
5. **Validation**: Ensures bounds are within reasonable Australian geographic limits

#### New Zealand Bucket Scanning  
1. **Public Bucket Access**: Uses unsigned S3 access to public NZ bucket
2. **Directory Discovery**: Finds all directories containing .tiff files (188+ found)
3. **GeoTIFF Metadata**: Opens each file with rasterio to extract actual spatial bounds
4. **Coordinate Transformation**: Converts NZTM (EPSG:2193) to WGS84 (EPSG:4326)
5. **Spatial Organization**: Groups files by region/survey with calculated coverage areas

### Incremental Update Algorithm
1. **Timestamp Comparison**: Compares S3 object LastModified vs index generated_at
2. **File Set Difference**: Identifies files in S3 but not in existing index
3. **Batch Processing**: Processes new files in batches with progress reporting
4. **Index Merging**: Adds new files to existing region/survey structure
5. **Coverage Recalculation**: Updates bounds for affected regions and surveys

### Error Handling & Fallbacks
- **Rasterio Failures**: Individual file failures don't stop entire process
- **S3 Access Issues**: Comprehensive error logging with continuation
- **Incremental Failures**: Automatic fallback to full regeneration
- **Invalid Bounds**: Files with invalid coordinates are logged but skipped

## 📊 Performance Metrics

### File Processing Rates
- **Australian Files**: ~50-100 files/minute (UTM parsing)  
- **New Zealand Files**: ~20-40 files/minute (GeoTIFF metadata extraction)
- **Incremental Updates**: ~100-200 files/minute (new files only)

### Expected Coverage
- **Australian**: 1,153 campaigns, ~54,000x Brisbane speedup maintained
- **New Zealand**: 91 survey campaigns, 29,758 files with actual bounds
- **Total Coverage**: Australia + New Zealand + Global API fallback

### Memory Usage
- **Index Loading**: ~50-100MB for complete spatial indexes
- **Generation Process**: ~200-400MB peak during GeoTIFF processing
- **Production Runtime**: ~600MB total including spatial indexes

## 🚨 Troubleshooting

### Common Issues

#### "No new files found" (but files were added)
- **Cause**: Files added to S3 but timestamps not updated properly
- **Solution**: Run full regeneration batch file instead of incremental

#### "Failed to extract bounds from GeoTIFF"
- **Cause**: Corrupted or non-standard GeoTIFF files
- **Solution**: Check rasterio logs, files are skipped automatically

#### "Incremental update failed, falling back to full"
- **Cause**: Index file corruption or major S3 structure changes
- **Solution**: This is expected behavior - full regeneration will proceed

#### Batch file times out or hangs
- **Cause**: Large number of new files or S3 connectivity issues
- **Solution**: Check internet connection, re-run batch file (resumes progress)

### Validation Commands
```bash
# Australian index validation
python scripts/generate_spatial_index.py validate

# Show coverage summaries  
python scripts/generate_spatial_index.py show
python scripts/generate_nz_spatial_index_dynamic.py show

# Check file counts
python scripts/generate_nz_incremental_index.py show
```

This spatial index management system ensures the DEM Backend can automatically adapt to new elevation data without requiring code changes or manual mapping updates.