# High-Resolution DEM Integration Guide

## Executive Summary

This guide provides complete instructions for integrating the new 50cm resolution DEM data from the Elevation Team into your existing backend system. The integration includes:

- **New S3 bucket setup** with specific permissions for the Elevation Team
- **Enhanced source selection system** that automatically chooses the best available data
- **Priority-based data selection** with fallback coverage
- **Backward compatibility** with existing API endpoints

## Implementation Status

✅ **COMPLETED**: Core system enhancements
- Enhanced source selection service
- Priority-based scoring algorithm
- New API endpoints for source selection
- Backward-compatible configuration system

🔄 **NEXT STEPS**: Configuration and deployment (requires your action)

## Immediate Actions Required

### 1. S3 Bucket Setup (Critical - Do This First)

**Create new S3 bucket following Elevation Team requirements:**

1. **Create bucket** in AWS Console
   - **Region**: Sydney (`ap-southeast-2`) - **MANDATORY**
   - **Suggested name**: `dem-high-res-data-2024`

2. **Apply bucket policy** (replace `<your_bucket_name>` with your actual bucket name):
   ```json
   {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Sid": "DelegateS3Access",
               "Effect": "Allow",
               "Principal": {
                   "AWS": "arn:aws:iam::337340849400:user/ELEVATION_BULK_DATA_DISTRIBUTOR"
               },
               "Action": ["s3:ListBucket"],
               "Resource": [
                   "arn:aws:s3:::<your_bucket_name>",
                   "arn:aws:s3:::<your_bucket_name>/*"
               ]
           },
           {
               "Sid": "GrantOwnerFullControl",
               "Action": ["s3:PutObject", "s3:PutObjectAcl"],
               "Effect": "Allow",
               "Resource": "arn:aws:s3:::<your_bucket_name>/*",
               "Condition": {
                   "StringEquals": {
                       "s3:x-amz-acl": "bucket-owner-full-control"
                   }
               },
               "Principal": {
                   "AWS": ["arn:aws:iam::337340849400:user/ELEVATION_BULK_DATA_DISTRIBUTOR"]
               }
           }
       ]
   }
   ```

3. **Email the Elevation Team** your bucket name for their user policy setup

### 2. Configuration Update

**Update your `.env` file** with the enhanced configuration (see `docs/ENHANCED_CONFIGURATION.md` for complete example):

```env
# Enable automatic source selection
AUTO_SELECT_BEST_SOURCE=true

# Add new high-resolution bucket
AWS_S3_BUCKET_NAME_HIGH_RES=your-high-res-bucket-name

# Update DEM_SOURCES with metadata (example for Gold Coast)
DEM_SOURCES={
  "qld_50cm_lidar": {
    "path": "s3://your-high-res-bucket/queensland/50cm/QLD_50cm_LiDAR.tif",
    "resolution_m": 0.5,
    "priority": 1,
    "bounds": {"west": 153.0, "south": -28.2, "east": 153.8, "north": -27.8},
    "data_source": "LiDAR",
    "year": 2024,
    "description": "Queensland 50cm LiDAR - Highest resolution"
  },
  "existing_dtm_gdb": {
    "path": "s3://roadengineer-dem-files/DTM.gdb",
    "resolution_m": 5.0,
    "priority": 3,
    "data_source": "Photogrammetry",
    "year": 2023,
    "description": "Existing DTM - fallback coverage"
  }
}
```

### 3. System Restart

**Restart your DEM backend** to load the new configuration:

```bash
# Stop current service
# Then restart with:
python -m src.main
```

## New System Capabilities

### Automatic Source Selection
- **Smart Selection**: System automatically chooses best available source for each location
- **Priority-Based**: Higher resolution and newer data automatically preferred
- **Bounds-Aware**: Only considers sources that cover the query location
- **Fallback Coverage**: Seamlessly falls back to lower resolution data when needed

### New API Endpoints

#### 1. Source Selection API
```bash
POST /v1/elevation/select-source
{
  "latitude": -28.002,
  "longitude": 153.414,
  "prefer_high_resolution": true,
  "max_resolution_m": 5.0
}
```

**Response:**
```json
{
  "selected_source_id": "qld_50cm_lidar",
  "selected_source_info": {
    "resolution_m": 0.5,
    "data_source": "LiDAR",
    "bounds": {...}
  },
  "available_sources": ["qld_50cm_lidar", "existing_dtm_gdb"],
  "selection_reason": "Score: 285.1, Resolution: 0.5m, Priority: 1, Type: LiDAR"
}
```

#### 2. Coverage Summary API
```bash
GET /v1/elevation/coverage
```

**Response:**
```json
{
  "total_sources": 5,
  "sources_with_bounds": 4,
  "resolution_range": {"min": 0.5, "max": 30.0},
  "sources_by_type": {
    "LiDAR": 3,
    "Photogrammetry": 1,
    "SRTM": 1
  },
  "coverage_areas": [...]
}
```

#### 3. Enhanced Point Elevation
```bash
POST /v1/elevation/point
{
  "latitude": -28.002,
  "longitude": 153.414
}
# System automatically selects best source
```

## Data Quality Hierarchy

The system automatically prioritizes sources in this order:

1. **50cm LiDAR** (Queensland/Tasmania) - Priority 1
2. **1m LiDAR** (Regional coverage) - Priority 2  
3. **5m Photogrammetry** (Your existing data) - Priority 3
4. **30m SRTM** (National coverage) - Priority 4

## Testing Plan

### Phase 1: Basic Functionality
```bash
# Test source selection
curl -X POST "http://localhost:8001/v1/elevation/select-source" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -28.002, "longitude": 153.414}'

# Test coverage summary
curl "http://localhost:8001/v1/elevation/coverage"
```

### Phase 2: Data Quality Validation
```bash
# Test Gold Coast location (should select 50cm LiDAR)
curl -X POST "http://localhost:8001/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -28.002, "longitude": 153.414}'

# Test outside high-res area (should fallback to existing data)
curl -X POST "http://localhost:8001/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -25.000, "longitude": 150.000}'
```

## Migration Timeline

### Week 1: Infrastructure Setup
- [ ] Create new S3 bucket with proper permissions
- [ ] Notify Elevation Team of bucket name
- [ ] Wait for confirmation of data transfer setup

### Week 2: Configuration & Testing
- [ ] Update configuration with new sources
- [ ] Test source selection system
- [ ] Validate automatic selection logic

### Week 3: Data Integration
- [ ] Receive high-resolution data from Elevation Team
- [ ] Update configuration with actual file paths
- [ ] Test data access and quality

### Week 4: Production Deployment
- [ ] Deploy enhanced system to production
- [ ] Monitor performance and data quality
- [ ] Update client applications if needed

## Benefits of This Integration

### For Users
- **Higher Precision**: Up to 50cm resolution in key areas
- **Better Coverage**: More complete data coverage
- **Automatic Quality**: System always uses the best available data
- **Seamless Experience**: No changes required to existing API calls

### For System Operations
- **Intelligent Selection**: Reduces manual source management
- **Scalable Architecture**: Easy to add more data sources
- **Performance Optimized**: Efficient source selection and caching
- **Monitoring Ready**: Built-in coverage and quality reporting

## Support and Troubleshooting

### Common Issues
1. **Source Selection Not Working**: Check `AUTO_SELECT_BEST_SOURCE=true` in `.env`
2. **S3 Access Denied**: Verify bucket policy and AWS credentials
3. **No High-Res Data**: Confirm data transfer completed from Elevation Team

### Monitoring
- Check logs for source selection decisions
- Use `/v1/elevation/coverage` to monitor available sources
- Monitor response times for different source selections

## Next Steps

1. **Immediate**: Set up S3 bucket and email Elevation Team
2. **This Week**: Update configuration and test system
3. **Next Week**: Integrate actual high-resolution data
4. **Ongoing**: Monitor performance and add more sources as needed

This integration positions your system to automatically leverage the best available elevation data while maintaining full backward compatibility with existing applications. 