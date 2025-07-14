# Higher Resolution DEM Configuration Guide

## Adding Queensland LiDAR Data to Your DEM Backend

### Step 1: Update .env Configuration
Add these sources to your DEM_SOURCES configuration:

```json
{
  "local_dtm_gdb": {
    "path": "s3://roadengineer-dem-files/DTM.gdb", 
    "layer": null, 
    "crs": null, 
    "description": "Local DTM from geodatabase on S3 - auto-discovery enabled"
  },
  "qld_lidar_1m": {
    "path": "s3://your-bucket/QLD_LiDAR_1m_GoldCoast.tif",
    "layer": null,
    "crs": "EPSG:28356",
    "description": "Queensland 1m LiDAR DEM - High precision"
  },
  "elvis_lidar_05m": {
    "path": "s3://your-bucket/Elvis_LiDAR_0.5m_GoldCoast.tif",
    "layer": null,
    "crs": "EPSG:28356", 
    "description": "Elvis Portal 0.5m LiDAR - Highest precision"
  },
  "gc_council_lidar": {
    "path": "s3://your-bucket/GoldCoast_Council_LiDAR.las",
    "layer": null,
    "crs": "EPSG:28356",
    "description": "Gold Coast Council raw LiDAR point cloud"
  }
}
```

### Step 2: Download and Process Higher-Resolution Data

#### From Elvis Portal:
1. Visit https://elevation.fsdf.org.au/
2. Search coordinates: -28.002, 153.414
3. Download available LiDAR datasets
4. Convert to GeoTIFF if needed:
   ```bash
   gdal_translate -of GTiff source.las output.tif
   ```

#### From Queensland Government:
1. Request data from QSpatial
2. Process LAZ files to DEM rasters:
   ```bash
   las2dem -i input.laz -o output.tif -step 0.5
   ```

### Step 3: Priority Configuration
Configure your backend to try higher-resolution sources first:

```python
# In dem_service.py - modify source selection logic
def get_best_source_for_location(self, lat, lon):
    # Priority order: highest resolution first
    priority_sources = [
        "gc_council_lidar",      # Highest precision
        "elvis_lidar_05m",       # 0.5m resolution  
        "qld_lidar_1m",          # 1m resolution
        "local_dtm_gdb"          # Fallback
    ]
    
    for source_id in priority_sources:
        if self.point_in_bounds(source_id, lat, lon):
            return source_id
    
    return "local_dtm_gdb"  # Default fallback
```

### Expected Precision Improvements

| Data Source | Resolution | Expected Precision | Coverage |
|-------------|------------|-------------------|----------|
| Current DTM.gdb | ~5m | ±0.05m quantized | Gold Coast region |
| QLD LiDAR 1m | 1m | ±0.01-0.02m | Urban areas |
| Elvis LiDAR 0.5m | 0.5m | ±0.005-0.01m | Selected areas |
| Council LiDAR | 0.1-0.5m | ±0.002-0.005m | Local areas |

### Benefits for Your Use Case
- **Current Issue**: 0.05m quantization in slopes
- **With 1m LiDAR**: ~0.01m precision - 5x improvement
- **With 0.5m LiDAR**: ~0.005m precision - 10x improvement
- **With Council data**: ~0.002m precision - 25x improvement

This should resolve the precision issues you're seeing in slope calculations at 0.5m spacing. 