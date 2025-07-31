# Quick Start: DEM Source Management
**Seamless Process for Managing Elevation Data Sources**

## Problem Solved ✅
- **Brisbane was using GPXZ (30m) instead of available Queensland S3 data (50cm-1m)**
- **Bendigo had no coverage despite existing Victoria data in S3**  
- **649GB+ of DEM data was unused due to configuration gaps**

## Solution Implemented ✅
- **Brisbane now uses `csiro_qld_z56` (Queensland S3 data)**
- **Bendigo now uses `ga_vic_z55` (Victoria S3 data)**
- **Complete automated protocol for future source additions**

## Quick Commands

### Daily Operations
```bash
# Check service status
python scripts/dem_source_cli.py status

# Quick daily health check  
scripts/daily_check.sh
```

### Adding New Data Sources
```bash
# 1. Discover what's available in S3
python scripts/dem_source_cli.py discover

# 2. Validate current configuration
python scripts/dem_source_cli.py validate

# 3. Add new sources interactively
python scripts/dem_source_cli.py add

# 4. Test geographic coverage
python scripts/dem_source_cli.py monitor
```

### Weekly Maintenance
```bash
# Full monitoring report
python scripts/source_monitoring.py

# Quick validation
python scripts/quick_source_discovery.py
```

### Monthly Deep Scan
```bash
# Comprehensive S3 bucket analysis
python scripts/s3_bucket_scanner.py
```

## Current Status After Fix

### Working Sources ✅
- **Brisbane (-27.4698, 153.0251)**: Uses `csiro_qld_z56` (Queensland 1m LiDAR)
- **Bendigo (-36.7570, 144.2794)**: Uses `ga_vic_z55` (Victoria 1m LiDAR)
- **14 total sources** configured (up from 11)
- **936GB S3 bucket** fully utilized

### Geographic Coverage ✅
- **Queensland**: CSIRO + DAWE sources (74GB + 30GB)
- **Victoria**: GA sources with Bendigo coverage
- **ACT**: High-resolution LiDAR
- **New Zealand**: Complete coverage
- **Global**: GPXZ API fallback

## When New Data Arrives

### Automated Approach (Recommended)
```bash
# Run the CLI tool
python scripts/dem_source_cli.py add

# Follow the prompts for:
# - Source ID and name
# - S3 path
# - Geographic bounds  
# - Resolution and metadata

# The tool will:
# - Validate the source exists in S3
# - Update both configuration files
# - Test geographic coverage
# - Provide next steps
```

### Manual Approach (Advanced)
Follow the complete protocol in `docs/DEM_SOURCE_MANAGEMENT_PROTOCOL.md`

## Key Files

### Configuration Files
- **`.env`**: Main source configuration (single-line JSON)
- **`config/dem_sources.json`**: Spatial selector configuration with geographic bounds

### Automation Scripts
- **`scripts/dem_source_cli.py`**: Main CLI tool
- **`scripts/s3_bucket_scanner.py`**: Full S3 discovery
- **`scripts/quick_source_discovery.py`**: Quick validation
- **`scripts/source_monitoring.py`**: Geographic coverage testing

### Documentation
- **`docs/DEM_SOURCE_MANAGEMENT_PROTOCOL.md`**: Complete technical protocol
- **`docs/QUICK_START_SOURCE_MANAGEMENT.md`**: This quick start guide

## Troubleshooting

### Sources Still Using GPXZ Instead of S3
```bash
# 1. Check if sources are properly configured
python scripts/dem_source_cli.py status

# 2. Restart the server completely
# Stop: Ctrl+C
# Start: uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload

# 3. Test specific coordinates
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'
```

### Geographic Coverage Gaps
```bash
# Test coverage comprehensively
python scripts/source_monitoring.py

# Check what's missing
python scripts/quick_source_discovery.py
```

### Configuration Errors
```bash
# Validate configuration syntax
python -c "from src.config import Settings; Settings()"

# Check spatial selector config
python -c "import json; json.load(open('config/dem_sources.json'))"
```

## Success Metrics ✅

After implementing this system:
- **Brisbane elevation requests** use high-resolution S3 data instead of GPXZ
- **Victoria/Bendigo coordinates** have proper coverage
- **No more invalid source configurations** (removed nsw_elvis, vic_elvis)
- **Automated discovery** prevents future coverage gaps
- **936GB S3 bucket** is fully utilized for Australian queries

## Next Steps for New Data

1. **Run discovery**: `python scripts/dem_source_cli.py discover`
2. **Add sources**: `python scripts/dem_source_cli.py add`  
3. **Restart server**: `uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload`
4. **Test coverage**: `python scripts/dem_source_cli.py monitor`
5. **Set up monitoring**: Add to daily/weekly schedule

This system ensures **no more Brisbane/Bendigo coverage issues** and provides a **seamless process** for future DEM data integration.