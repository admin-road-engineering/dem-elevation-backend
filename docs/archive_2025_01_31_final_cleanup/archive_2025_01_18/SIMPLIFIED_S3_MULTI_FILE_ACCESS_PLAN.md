# Simplified S3 Multi-File Access Plan
**Industry Best Practices for Manual Data Updates**

## Overview
Given that "new files being added isn't frequent and is manually added," this plan focuses on a **simplified, static approach** to multi-file S3 DEM access rather than complex dynamic real-time systems.

## Key Assumptions
- **Manual file additions**: New DEM files are added manually and infrequently
- **Static spatial index**: Can be updated periodically rather than real-time
- **Predictable workflow**: File additions follow consistent patterns
- **Cost optimization**: Minimize S3 API calls and processing overhead

## Current S3 Structure Analysis
```
s3://road-engineering-elevation-data/
├── csiro-elvis/elevation/1m-dem/z56/          # Queensland (74GB)
├── dawe-elvis/elevation/50cm-dem/z56/         # Queensland (30GB)  
├── ga-elvis/elevation/1m-dem/ausgeoid/z55/    # Victoria (287GB)
├── griffith-elvis/elevation/50cm-dem/z55/     # Queensland/Victoria (210GB)
├── act-elvis/                                 # ACT (148GB)
└── ga-elvis/elevation/1m-dem/ausgeoid/        # National (187GB)
```

## Simplified Architecture

### 1. Static Spatial Index Approach
Instead of real-time file discovery, create a **one-time spatial index** that maps coordinates to specific files:

```json
{
  "spatial_index": {
    "z56": {
      "files": [
        {
          "file": "s3://road-engineering-elevation-data/csiro-elvis/elevation/1m-dem/z56/E153_S28_1m_dem.tif",
          "bounds": {
            "min_lat": -28.0,
            "max_lat": -27.0,
            "min_lon": 153.0,
            "max_lon": 154.0
          }
        }
      ]
    }
  }
}
```

### 2. Coordinate-Based File Selection
Simple lookup algorithm:
```python
def select_file_for_coordinate(lat, lon, utm_zone):
    """Select specific .tif file based on coordinates"""
    zone_index = spatial_index[utm_zone]
    
    for file_info in zone_index["files"]:
        bounds = file_info["bounds"]
        if (bounds["min_lat"] <= lat <= bounds["max_lat"] and
            bounds["min_lon"] <= lon <= bounds["max_lon"]):
            return file_info["file"]
    
    return None
```

### 3. Manual Index Updates
When new files are added:
1. **Run index generator**: `python scripts/generate_spatial_index.py`
2. **Update configuration**: Automatically updates spatial index
3. **Restart service**: Single restart to load new index

## Implementation Plan

### Phase 1: Create Static Spatial Index Generator
Create `scripts/generate_spatial_index.py`:
```python
def generate_spatial_index():
    """Generate static spatial index from S3 bucket contents"""
    # 1. Scan S3 directories for .tif files
    # 2. Extract bounds from filename patterns (E153_S28_1m_dem.tif)
    # 3. Create spatial index JSON
    # 4. Save to config/spatial_index.json
```

### Phase 2: Implement File Selection Logic
Update `src/dem_service.py`:
```python
def _select_s3_file_from_index(self, lat, lon, s3_directory):
    """Use spatial index to select specific file"""
    # 1. Load spatial index
    # 2. Determine UTM zone from directory path
    # 3. Find matching file for coordinates
    # 4. Return full S3 path
```

### Phase 3: Create Update Workflow
Create `scripts/update_s3_index.py`:
```python
def update_index_workflow():
    """Complete workflow for updating spatial index"""
    # 1. Backup current index
    # 2. Generate new index
    # 3. Validate new index
    # 4. Update configuration
    # 5. Provide restart instructions
```

## Specific Implementation Details

### 1. Filename Pattern Analysis
Most files follow patterns like:
- `E153_S28_1m_dem.tif` (Easting 153, Southing 28, 1m resolution)
- `E144_S37_50cm_dem.tif` (Easting 144, Southing 37, 50cm resolution)

Extract bounds from filename:
```python
def extract_bounds_from_filename(filename):
    """Extract geographic bounds from standard filename"""
    # E153_S28_1m_dem.tif -> bounds for 153°E, 28°S tile
    match = re.match(r'E(\d+)_S(\d+)_.*\.tif', filename)
    if match:
        east = int(match.group(1))
        south = int(match.group(2))
        return {
            "min_lat": -south - 1,
            "max_lat": -south,
            "min_lon": east,
            "max_lon": east + 1
        }
```

### 2. Caching Strategy
Simple file-based caching:
```python
# Cache individual file datasets for 15 minutes
file_cache = {
    "s3://bucket/path/file.tif": {
        "dataset": rasterio_dataset,
        "cached_at": timestamp,
        "expire_after": 900  # 15 minutes
    }
}
```

### 3. Error Handling
Robust fallback chain:
```python
def get_elevation_with_fallback(lat, lon, source_path):
    """Try specific file, then directory scan, then fallback source"""
    try:
        # 1. Try spatial index lookup
        specific_file = self._select_s3_file_from_index(lat, lon, source_path)
        if specific_file:
            return self._get_elevation_from_file(specific_file, lat, lon)
        
        # 2. Try directory scan (existing logic)
        return self._get_elevation_from_directory(source_path, lat, lon)
        
    except Exception as e:
        # 3. Fallback to next source in priority order
        return self._try_next_source(lat, lon)
```

## Maintenance Workflow

### When New Files Are Added (Manual Process)
1. **Upload files to S3** (existing manual process)
2. **Run index generator**: `python scripts/generate_spatial_index.py`
3. **Review changes**: Check generated index for accuracy
4. **Update service**: Restart uvicorn server
5. **Validate**: Test affected coordinates

### Monthly Maintenance
1. **Run full validation**: `python scripts/validate_spatial_index.py`
2. **Check for orphaned files**: Files in S3 but not in index
3. **Performance review**: Check cache hit rates and response times

## Benefits of This Approach

### 1. Simplicity
- **No real-time scanning**: Index generated once, used many times
- **Predictable performance**: No variable S3 API call times
- **Easy debugging**: Clear mapping of coordinates to files

### 2. Cost Efficiency
- **Minimal S3 API calls**: Only during index generation
- **Cached file access**: Reuse open datasets
- **Optimized queries**: Direct file access, no directory scans

### 3. Reliability
- **Static configuration**: No dynamic failures
- **Graceful degradation**: Falls back to directory scanning if needed
- **Version control**: Spatial index can be versioned and tracked

### 4. Manual Process Alignment
- **Fits workflow**: Matches manual file addition process
- **Clear steps**: Simple workflow for updates
- **Validation built-in**: Easy to verify new files are indexed

## File Structure After Implementation

```
C:\Users\Admin\DEM Backend\
├── config/
│   ├── dem_sources.json                 # Current spatial selector config
│   ├── spatial_index.json               # NEW: Static file index
│   └── backups/                         # Backup configurations
├── scripts/
│   ├── generate_spatial_index.py        # NEW: Index generator
│   ├── update_s3_index.py              # NEW: Update workflow
│   └── validate_spatial_index.py       # NEW: Validation tool
└── src/
    └── dem_service.py                   # Updated with index lookup
```

## Next Steps

1. **Create spatial index generator** (`scripts/generate_spatial_index.py`)
2. **Update DEM service** with index-based file selection
3. **Generate initial index** from current S3 bucket
4. **Test Brisbane/Bendigo** coordinates with specific files
5. **Document update process** for future file additions

This approach provides **industry-standard multi-file access** while maintaining simplicity and aligning with your manual file addition workflow.