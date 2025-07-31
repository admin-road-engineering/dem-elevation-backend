# DEM Source Management Protocol
**Complete Process for Adding New Data Sources - Start to Finish**

## Overview
This protocol ensures that new DEM data sources are discovered, validated, configured, and integrated seamlessly into the elevation service without geographic coverage gaps or configuration drift.

## The Problem We Solved
- **Brisbane used GPXZ instead of available S3 Queensland data**
- **Bendigo had no coverage despite existing Victoria data in S3**
- **Invalid sources (`nsw_elvis`, `vic_elvis`) configured but non-existent**
- **Manual configuration led to 649GB+ of data being unused**

## Root Causes Identified
1. **Dual Configuration System**: Both `.env` file and `config/dem_sources.json` must be updated
2. **No S3 Discovery**: Never scanned actual bucket contents
3. **Manual Process**: No validation that configured sources exist
4. **Geographic Gaps**: No testing of real coordinates against sources

## Complete Protocol

### Phase 1: Discovery and Validation

#### 1.1 Automated S3 Bucket Scanning
```bash
# Run comprehensive bucket scan
python scripts/s3_bucket_scanner.py

# Quick validation of current issues
python scripts/quick_source_discovery.py
```

**What this does:**
- Discovers all available DEM sources in S3 bucket
- Extracts geographic coverage and resolutions
- Validates current configuration against S3 reality
- Identifies missing and invalid sources

#### 1.2 Geographic Coverage Testing
```bash
# Test current coverage gaps
python scripts/source_monitoring.py
```

**What this does:**
- Tests major Australian cities against current sources
- Identifies locations using API instead of S3
- Detects no-coverage areas
- Reports source usage patterns

### Phase 2: Configuration Updates

#### 2.1 Update Environment Configuration (.env)
**Template for adding new sources:**
```env
DEM_SOURCES={"existing_sources": {...}, "new_source_id": {"path": "s3://road-engineering-elevation-data/path/", "layer": null, "crs": "EPSG:XXXX", "description": "Description"}}
```

**Critical Requirements:**
- Single-line JSON format
- No trailing commas
- Proper escape characters
- Valid CRS codes

#### 2.2 Update Spatial Selector Configuration (config/dem_sources.json)
**Template for spatial selector entries:**
```json
{
  "id": "new_source_id",
  "name": "Human Readable Name",
  "source_type": "s3",
  "path": "s3://road-engineering-elevation-data/path/",
  "crs": "EPSG:XXXX",
  "resolution_m": 1,
  "data_type": "LiDAR",
  "provider": "Provider Name",
  "priority": 1,
  "bounds": {
    "type": "bbox",
    "min_lat": -XX.X,
    "max_lat": -XX.X,
    "min_lon": XXX.X,
    "max_lon": XXX.X
  },
  "cost_per_query": 0.001,
  "accuracy": "±0.1m",
  "enabled": true,
  "visible_in_coverage": true,
  "metadata": {
    "capture_date": "YYYY",
    "point_density": "X points/m²",
    "vertical_datum": "AHD",
    "color": "#00AA00",
    "opacity": 0.4
  }
}
```

**Critical Requirements:**
- Geographic bounds must accurately cover the data
- Priority: 1 (highest) for high-resolution S3, 2-3 for APIs
- CRS must match the actual data projection

### Phase 3: Service Integration

#### 3.1 Server Restart (Required)
```bash
# Stop current server (Ctrl+C)
# Restart with updated configuration
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
```

**Why restart is required:**
- Spatial selector loads configuration once at startup
- Changes to `config/dem_sources.json` require restart
- `.env` changes are picked up on reload

#### 3.2 Validation Testing
```bash
# Test key coordinates
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'  # Brisbane

curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -36.7570, "longitude": 144.2794}'  # Bendigo
```

**Success Indicators:**
- Brisbane uses Queensland S3 sources (not GPXZ)
- Bendigo uses Victoria S3 sources (not GPXZ/invalid sources)
- Higher resolution data returned
- No error messages

### Phase 4: Monitoring and Maintenance

#### 4.1 Automated Monitoring Setup
```bash
# Set up daily monitoring
chmod +x scripts/daily_check.sh

# Add to cron or task scheduler
# Daily: scripts/daily_check.sh
# Weekly: python scripts/source_monitoring.py
# Monthly: python scripts/s3_bucket_scanner.py
```

#### 4.2 Continuous Validation
```bash
# Quick status check
python -c "
from src.config import Settings
from src.dem_service import DEMService
import asyncio

async def test():
    settings = Settings()
    service = DEMService(settings)
    
    # Test Brisbane
    elevation, source, error = service.get_elevation_at_point(-27.4698, 153.0251)
    print(f'Brisbane: {elevation}m via {source}')
    
    # Test Bendigo  
    elevation, source, error = service.get_elevation_at_point(-36.7570, 144.2794)
    print(f'Bendigo: {elevation}m via {source}')

asyncio.run(test())
"
```

## Automated Tools Created

### 1. S3 Bucket Scanner (`scripts/s3_bucket_scanner.py`)
- **Purpose**: Comprehensive S3 bucket analysis
- **Output**: Complete source inventory with metadata
- **Schedule**: Monthly or when new data added

### 2. Quick Source Discovery (`scripts/quick_source_discovery.py`)
- **Purpose**: Rapid validation of current vs. available sources
- **Output**: Missing sources and invalid configurations
- **Schedule**: Before any configuration changes

### 3. Source Monitoring (`scripts/source_monitoring.py`)
- **Purpose**: Geographic coverage validation with real coordinates
- **Output**: Coverage gaps and source usage analysis
- **Schedule**: Weekly

### 4. Daily Check (`scripts/daily_check.sh`)
- **Purpose**: Rapid health check of key locations
- **Output**: Service status for Brisbane, Melbourne, Sydney
- **Schedule**: Daily

## Configuration Templates

### Template: New Queensland Region
```json
{
  "id": "new_qld_region",
  "name": "Queensland [Region] LiDAR",
  "source_type": "s3",
  "path": "s3://road-engineering-elevation-data/provider-elvis/elevation/resolution/z56/",
  "crs": "EPSG:32756",
  "resolution_m": 1,
  "priority": 1,
  "bounds": {
    "type": "bbox",
    "min_lat": -29.0,
    "max_lat": -25.0,
    "min_lon": 150.0,
    "max_lon": 154.0
  }
}
```

### Template: New Victoria Region
```json
{
  "id": "new_vic_region", 
  "name": "Victoria [Region] LiDAR",
  "source_type": "s3",
  "path": "s3://road-engineering-elevation-data/provider-elvis/elevation/resolution/z55/",
  "crs": "EPSG:32755",
  "resolution_m": 1,
  "priority": 1,
  "bounds": {
    "type": "bbox",
    "min_lat": -39.0,
    "max_lat": -34.0,
    "min_lon": 140.0,
    "max_lon": 150.0
  }
}
```

## Quality Assurance Checklist

### Before Adding New Sources
- [ ] Run S3 bucket scanner to identify available data
- [ ] Validate that source paths actually exist in S3
- [ ] Determine accurate geographic bounds
- [ ] Choose appropriate priority and resolution

### During Configuration
- [ ] Update `.env` DEM_SOURCES with proper JSON formatting
- [ ] Update `config/dem_sources.json` with geographic bounds
- [ ] Verify CRS codes match actual data
- [ ] Remove any invalid/non-existent sources

### After Configuration Changes  
- [ ] Restart uvicorn server completely
- [ ] Test key coordinates in affected regions
- [ ] Verify S3 sources used instead of APIs
- [ ] Run source monitoring validation
- [ ] Check server logs for any errors

### Ongoing Monitoring
- [ ] Daily: Run daily_check.sh
- [ ] Weekly: Run source_monitoring.py
- [ ] Monthly: Run s3_bucket_scanner.py
- [ ] When new data added: Full protocol

## Troubleshooting Guide

### Issue: Still Using GPXZ Instead of S3
**Cause**: Configuration not loaded or invalid bounds
**Solution**: 
1. Check `config/dem_sources.json` has correct bounds
2. Restart server completely
3. Verify geographic bounds cover test coordinates

### Issue: "AWS Access Key Id does not exist"
**Cause**: S3 authentication issue (separate from source selection)
**Solution**: Check AWS credentials in `.env` file

### Issue: Source Selection Not Working
**Cause**: Spatial selector initialization failed
**Solution**:
1. Check server logs for spatial selector errors
2. Validate `config/dem_sources.json` syntax
3. Ensure bounds format is correct

### Issue: New Sources Not Appearing
**Cause**: Server hasn't reloaded configuration
**Solution**: Full server restart (not just reload)

## Success Metrics

### Configuration Accuracy
- All configured sources exist in S3 ✅
- No invalid sources in configuration ✅
- Geographic bounds accurately cover data ✅

### Geographic Coverage
- Major cities use S3 instead of APIs ✅
- No coverage gaps for Australian locations ✅
- Appropriate resolution sources selected ✅

### System Reliability  
- Daily monitoring passes ✅
- Source selection working correctly ✅
- Performance within acceptable limits ✅

## Implementation History

### 2025-07-17: Initial Fix
- **Problem**: Brisbane used GPXZ (30m) instead of available Queensland S3 data (50cm-1m)
- **Solution**: Added 5 missing Queensland/Victoria sources
- **Result**: Brisbane now uses `csiro_qld_z56`, Bendigo uses `ga_vic_z55`
- **Data Activated**: 649GB+ of previously unused Australian DEM data

### Future Updates
Document each source addition with:
- Date added
- Source details
- Geographic coverage
- Validation results
- Any issues encountered

---

**This protocol prevents the Brisbane/Bendigo coverage issue from recurring and ensures our 936GB S3 bucket is fully utilized for Australian elevation queries.**