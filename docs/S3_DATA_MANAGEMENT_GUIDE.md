# S3 Data Management Guide - Adding New DEM Files

## Overview

This guide provides step-by-step instructions for what to do when **additional DEM data is added to S3 buckets**. The DEM Backend uses **spatial indexing** to efficiently locate the correct DEM files for any given coordinates, so the index must be updated when new files are added.

## When to Use This Guide

Use this guide when:
- **New DEM files are added** to Australian S3 bucket (`road-engineering-elevation-data`)
- **New DEM files are added** to NZ S3 bucket (`nz-elevation`) 
- **Existing files are updated** or replaced
- **Coverage areas are expanded** with new data
- **Service is not finding DEM files** that you know exist in S3

## Understanding the Spatial Index System

### How It Works
The service uses **static spatial indexes** that map coordinates to specific DEM files:
- `config/spatial_index.json` - Australian DEM files (214,450+ files)
- `config/nz_spatial_index.json` - New Zealand DEM files (1,691+ files)

### Why It's Needed
Without spatial indexing, the service would need to:
1. List all files in S3 buckets (expensive and slow)
2. Parse each filename to determine coverage
3. Test each file for coordinate matches

With spatial indexing:
1. **Instant lookup** - Find the correct file in milliseconds
2. **Cost efficient** - No repeated S3 API calls
3. **Scalable** - Works with hundreds of thousands of files

## Step-by-Step Instructions

### For Australian S3 Bucket (`road-engineering-elevation-data`)

#### 1. Verify New Files Are in S3
```bash
# Check that new files are accessible
python -c "
import boto3
from src.config import get_settings
settings = get_settings()
s3 = boto3.client('s3', region_name=settings.AWS_DEFAULT_REGION)
response = s3.list_objects_v2(Bucket='road-engineering-elevation-data', Prefix='your-new-folder/', MaxKeys=10)
print(f'Found {len(response.get(\"Contents\", []))} new files')
for obj in response.get('Contents', []):
    print(f'  {obj[\"Key\"]}')
"
```

#### 2. Regenerate Australian Spatial Index
```bash
# Navigate to project root
cd "C:\Users\Admin\DEM Backend"

# Generate new spatial index (this will scan all files)
python scripts/generate_spatial_index.py generate
```

**Expected Output:**
```
🗺️ Generating spatial index from S3 bucket...
📊 Scanning S3 bucket: road-engineering-elevation-data
📁 Processing: csiro-elvis/elevation/1m-dem/z56/
📁 Processing: dawe-elvis/elevation/50cm-dem/z56/
📁 Processing: ga-elvis/elevation/1m-dem/ausgeoid/z55/
📁 Processing: your-new-folder/
...
✅ Spatial index generated successfully
📈 Coverage Summary:
   Total files: 215,000+ (increased from 214,450)
   UTM zones: 55, 56
   Resolution range: 0.5-1.0m
   Coverage area: Australia
```

#### 3. Validate the Updated Index
```bash
# Validate that the index is correct
python scripts/generate_spatial_index.py validate
```

#### 4. Test New Coverage
```bash
# Test a coordinate that should be covered by new data
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": YOUR_TEST_LAT, "longitude": YOUR_TEST_LON}'
```

### For New Zealand S3 Bucket (`nz-elevation`)

#### 1. Verify New Files Are in S3
```bash
# Check NZ bucket (public access)
python -c "
import boto3
from botocore import UNSIGNED
from botocore.config import Config
s3 = boto3.client('s3', region_name='ap-southeast-2', config=Config(signature_version=UNSIGNED))
response = s3.list_objects_v2(Bucket='nz-elevation', Prefix='your-new-region/', MaxKeys=10)
print(f'Found {len(response.get(\"Contents\", []))} new files')
for obj in response.get('Contents', []):
    print(f'  {obj[\"Key\"]}')
"
```

#### 2. Regenerate NZ Spatial Index
```bash
# Generate new NZ spatial index
python scripts/generate_nz_spatial_index.py generate
```

**Expected Output:**
```
🗺️ Generating NZ spatial index from S3 bucket...
📊 Scanning S3 bucket: nz-elevation
📁 Processing: auckland/
📁 Processing: wellington/
📁 Processing: your-new-region/
...
✅ NZ spatial index generated successfully
📈 Coverage Summary:
   Total files: 1,700+ (increased from 1,691)
   Regions: 17 (added your-new-region)
   Resolution: 1.0m
   Coverage area: New Zealand
```

#### 3. Validate the Updated Index
```bash
# Validate NZ index
python scripts/generate_nz_spatial_index.py validate
```

#### 4. Test New Coverage
```bash
# Test a coordinate in the new coverage area
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": YOUR_NZ_TEST_LAT, "longitude": YOUR_NZ_TEST_LON}'
```

## Advanced Operations

### Partial Index Updates (Future Enhancement)

Currently, the spatial index generators rebuild the entire index. For large datasets, you might want to implement **incremental updates**:

```python
# Future enhancement - partial index update
def update_spatial_index_incremental(new_folder_prefix: str):
    """Update spatial index with only new files"""
    # Load existing index
    existing_index = load_spatial_index()
    
    # Scan only new folder
    new_files = scan_s3_prefix(new_folder_prefix)
    
    # Merge with existing index
    updated_index = merge_spatial_indexes(existing_index, new_files)
    
    # Save updated index
    save_spatial_index(updated_index)
```

### Automated Index Updates

For production environments, consider automating index updates:

```bash
#!/bin/bash
# scripts/auto_update_spatial_index.sh

# Check for new files (compare with last update timestamp)
LAST_UPDATE=$(cat config/last_index_update.txt 2>/dev/null || echo "1970-01-01")

# Check S3 for files newer than last update
NEW_FILES=$(aws s3api list-objects-v2 \
  --bucket road-engineering-elevation-data \
  --query "Contents[?LastModified>'$LAST_UPDATE'].Key" \
  --output text)

if [ -n "$NEW_FILES" ]; then
    echo "New files detected, updating spatial index..."
    python scripts/generate_spatial_index.py generate
    echo "$(date -u +%Y-%m-%dT%H:%M:%S)" > config/last_index_update.txt
    echo "Spatial index updated successfully"
else
    echo "No new files, spatial index up to date"
fi
```

### Index Monitoring

Monitor spatial index health:

```bash
# Check index status
python scripts/generate_spatial_index.py show

# Expected output:
{
  "total_files": 214450,
  "utm_zones": ["55", "56"],
  "resolution_range": "0.5-1.0m",
  "coverage_area": "Australia",
  "last_updated": "2025-01-18T10:30:00Z"
}
```

## Troubleshooting

### Common Issues

**1. Spatial Index Not Found**
```bash
# Error: FileNotFoundError: config/spatial_index.json
# Solution: Generate the index
python scripts/generate_spatial_index.py generate
```

**2. AWS Credentials Error**
```bash
# Error: Unable to locate credentials
# Solution: Check AWS credentials are set
python -c "from src.config import get_settings; print(get_settings().AWS_ACCESS_KEY_ID)"
```

**3. New Files Not Found**
```bash
# Error: Service returns elevation_m: null for new coverage area
# Solution: Regenerate spatial index
python scripts/generate_spatial_index.py generate
```

**4. Index Validation Fails**
```bash
# Error: Spatial index validation failed
# Solution: Check S3 connectivity and regenerate
python scripts/generate_spatial_index.py validate
python scripts/generate_spatial_index.py generate
```

### Performance Considerations

**Index Generation Time:**
- Australian index (214,450 files): ~5-10 minutes
- NZ index (1,691 files): ~30 seconds
- Depends on network speed and S3 response times

**Index Size:**
- Australian spatial index: ~25MB
- NZ spatial index: ~200KB
- Loaded into memory at service startup

**Memory Usage:**
- Spatial indexes are cached in memory
- Australian index: ~100MB RAM
- NZ index: ~5MB RAM

## Integration with Service

### Service Restart Not Required

The spatial index is loaded at **service startup**. After updating the index:

**Option 1: Restart Service (Recommended)**
```bash
# Stop service (Ctrl+C)
# Start service
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
```

**Option 2: Hot Reload (If Implemented)**
```bash
# Future enhancement - hot reload spatial index
curl -X POST "http://localhost:8001/api/v1/admin/reload-spatial-index"
```

### Verification After Update

```bash
# 1. Check service health
curl http://localhost:8001/api/v1/health

# 2. Test known coordinates
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'

# 3. Test new coverage area
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": YOUR_NEW_LAT, "longitude": YOUR_NEW_LON}'

# 4. Check fallback chain is working
python test_fallback_chain.py
```

## Best Practices

### 1. Test Before Production
```bash
# Always test in development environment first
python scripts/switch_environment.py local
python scripts/generate_spatial_index.py generate
# Test thoroughly
python scripts/switch_environment.py production
```

### 2. Backup Old Index
```bash
# Backup current index before updating
cp config/spatial_index.json config/spatial_index_backup_$(date +%Y%m%d).json
cp config/nz_spatial_index.json config/nz_spatial_index_backup_$(date +%Y%m%d).json
```

### 3. Monitor After Updates
```bash
# Check service logs after index update
tail -f service.log

# Monitor error rates
curl http://localhost:8001/api/v1/health
```

### 4. Document Changes
```bash
# Add entry to changelog
echo "$(date): Updated spatial index - added new DEM files to region XYZ" >> CHANGELOG.md
```

## Summary

When new DEM data is added to S3 buckets:

1. **Verify files are in S3** - Check upload was successful
2. **Regenerate spatial index** - Run the appropriate script
3. **Validate the index** - Ensure no errors
4. **Test coverage** - Verify new areas work
5. **Restart service** - Load the updated index
6. **Monitor** - Check for any issues

This process ensures the DEM Backend service can efficiently locate and access all available DEM files, including newly added data.