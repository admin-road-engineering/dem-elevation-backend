# Multi-Location S3 Data Management

## Overview

The DEM Backend uses a sophisticated catalog-driven system to manage multi-location S3 data across various Australian regions (Queensland, NSW, Victoria, Tasmania, etc.) and specialized datasets (urban corridors, highways, LiDAR coverage). This system is designed for scalability and automatic discovery of new datasets without code changes.

## Architecture

### Catalog-Based Management

The system treats S3 as a **multi-source repository** with dynamic discovery and selection, using these key components:

**S3SourceManager** (`src/s3_source_manager.py`):
- Maintains JSON catalog (`dem_catalog.json`) in each bucket
- Stores metadata for each DEM file (ID, path, bounds, resolution, CRS, size, description)
- Dynamically builds catalogs for new buckets
- Handles catalog updates and discoveries

**EnhancedSourceSelector** (`src/enhanced_source_selector.py`):
- Selects best source for lat/lon queries
- Prioritizes: Local → Free S3 (NZ) → Paid S3 (AU) → API fallback
- Integrates cost tracking and circuit breakers
- Handles source failures gracefully

**Base DEMSourceSelector** (`src/source_selector.py`):
- Scores sources by bounds overlap, resolution, priority, data type
- Ranks LiDAR > National DEM > SRTM for accuracy
- Supports coverage queries for geographic bounds

## Multi-Location Data Structure

### Primary S3 Bucket: `road-engineering-elevation-data`

**Regional Structure:**
```
australia/
├── states/
│   ├── qld/
│   │   ├── AU_QLD_LiDAR_1m.tif          # Queensland 1m LiDAR
│   │   ├── brisbane_metro_0.5m.tif       # Brisbane high-resolution
│   │   └── gold_coast_lidar_0.5m.tif     # Gold Coast LiDAR
│   ├── nsw/
│   │   ├── AU_NSW_DEM_2m.tif             # NSW 2m DEM
│   │   ├── sydney_metro_0.5m.tif         # Sydney high-resolution
│   │   └── pacific_highway_0.5m.tif      # Pacific Highway corridor
│   ├── vic/
│   │   ├── AU_VIC_DEM_5m.tif             # Victoria 5m DEM
│   │   └── melbourne_metro_1m.tif        # Melbourne metro area
│   ├── tas/
│   │   └── AU_TAS_LiDAR_50cm.tif         # Tasmania 50cm LiDAR
│   ├── sa/
│   │   └── AU_SA_DEM_5m.tif              # South Australia 5m DEM
│   └── wa/
│       └── AU_WA_DEM_5m.tif              # Western Australia 5m DEM
├── national/
│   ├── AU_National_5m_DEM.tif            # Australia-wide 5m DEM
│   └── AU_SRTM_1ArcSec.tif               # Global SRTM 30m fallback
└── corridors/
    ├── bruce_highway_1m.tif              # Bruce Highway (QLD)
    ├── princes_highway_1m.tif            # Princes Highway (NSW/VIC)
    └── great_ocean_road_1m.tif           # Great Ocean Road (VIC)
```

### Catalog Entry Structure

Each dataset is cataloged with comprehensive metadata:

```json
{
  "au_qld_lidar_1m": {
    "id": "au_qld_lidar_1m",
    "path": "s3://road-engineering-elevation-data/australia/states/qld/AU_QLD_LiDAR_1m.tif",
    "bounds": [138.0, -29.0, 154.0, -9.0],
    "resolution_m": 1.0,
    "crs": "EPSG:28356",
    "region": "queensland",
    "size_bytes": 2147483648,
    "description": "Queensland 1m LiDAR - High accuracy elevation data",
    "accuracy": "±0.1m vertical accuracy",
    "last_updated": "2024-01-15T00:00:00Z",
    "data_type": "lidar",
    "priority": 1
  }
}
```

### Secondary Buckets

**High-Resolution Bucket**: `AWS_S3_BUCKET_NAME_HIGH_RES`
- Ultra-high resolution datasets (< 1m)
- Urban corridor specific data
- Specialized engineering projects

**NZ Open Data**: `nz-elevation` (Public)
- Canterbury, North Island, Wellington DEMs
- No authentication required
- Free access for testing

## Data Discovery and Updates

### Automatic Discovery

The `discover_new_datasets()` method automatically:

1. **Scans bucket** for new `.tif` files
2. **Extracts metadata** from filename patterns:
   - `AU_QLD_LiDAR_1m.tif` → Region: Queensland, Resolution: 1m, Type: LiDAR
   - `sydney_metro_0.5m.tif` → Region: NSW, Resolution: 0.5m, Type: Metro
3. **Infers bounds** from regional knowledge or file headers
4. **Determines CRS** based on region (e.g., EPSG:3577 for national Australia)
5. **Assigns priority** based on data type and resolution

### Catalog Updates

Adding new data follows this workflow:

1. **Upload DEM file** to appropriate S3 location
2. **Run discovery**:
   ```bash
   python scripts/manage_s3_catalog.py --action discover --bucket road-engineering-elevation-data
   ```
3. **Update catalog**:
   ```bash
   python scripts/manage_s3_catalog.py --action update --bucket road-engineering-elevation-data
   ```
4. **Validate integrity**:
   ```bash
   python scripts/manage_s3_catalog.py --action validate --bucket road-engineering-elevation-data
   ```

### Future-Proofing

The system handles new data additions without code changes:
- New regional files are auto-discovered
- Metadata is inferred from naming conventions
- Priority and selection logic adapts automatically
- No service restarts required

## Source Selection Logic

### Priority Hierarchy

1. **Local Sources** (highest priority)
   - Zero cost
   - Fastest access
   - Limited coverage

2. **Free S3 Sources** (NZ Open Data)
   - Public bucket access
   - No authentication required
   - Regional coverage (NZ only)

3. **Paid S3 Sources** (Primary bucket)
   - Private bucket (requires AWS credentials)
   - Comprehensive Australian coverage
   - Cost-managed access

4. **API Sources** (GPXZ.io)
   - Global coverage
   - Rate-limited access
   - Fallback for uncovered areas

### Selection Criteria

For each query location, the system:

1. **Filters by bounds** - Only sources covering the query point
2. **Ranks by resolution** - Higher resolution preferred
3. **Considers data type** - LiDAR > National DEM > SRTM
4. **Checks cost limits** - Respects daily usage limits
5. **Validates availability** - Skips failed/unavailable sources

### Cost Management

**S3CostManager** tracks and limits usage:
- Daily transfer limits (1GB development, unlimited production)
- Per-request cost estimation
- Circuit breaker for over-limit scenarios
- Automatic fallback to free sources

## Testing Multi-Location Data

### Comprehensive Testing Tools

**1. S3 Catalog Testing**:
```bash
python scripts/test_s3_catalog.py
```
- Tests catalog integrity
- Validates metadata structure
- Checks regional coverage
- Tests source selection logic

**2. Multi-Location API Testing**:
```bash
python scripts/test_api_plan.py
```
- Tests elevation queries across all Australian states
- Validates source selection for each region
- Checks response times and accuracy

**3. Catalog Management**:
```bash
# View catalog statistics
python scripts/manage_s3_catalog.py --action stats

# Discover new datasets
python scripts/manage_s3_catalog.py --action discover

# Update catalog (dry run)
python scripts/manage_s3_catalog.py --action update --dry-run

# Validate catalog integrity
python scripts/manage_s3_catalog.py --action validate

# Export catalog for analysis
python scripts/manage_s3_catalog.py --action export --output catalog_backup.json
```

### Test Coverage by Region

The testing suite covers these specific locations:

| Region | Test Location | Expected Sources | Resolution |
|--------|---------------|------------------|------------|
| Queensland | Brisbane (-27.47, 153.03) | `au_qld_lidar_1m`, `au_national` | 1m, 5m |
| NSW | Sydney (-33.87, 151.21) | `au_nsw_dem_2m`, `au_national` | 2m, 5m |
| Victoria | Melbourne (-37.81, 144.96) | `au_vic_dem_5m`, `au_national` | 5m |
| Tasmania | Hobart (-42.88, 147.33) | `au_tas_lidar_50cm`, `au_national` | 0.5m, 5m |
| SA | Adelaide (-34.93, 138.60) | `au_sa_dem_5m`, `au_national` | 5m |
| WA | Perth (-31.95, 115.86) | `au_wa_dem_5m`, `au_national` | 5m |

### Performance Testing

**Response Time Benchmarks**:
- Local queries: < 100ms
- S3 queries: < 500ms
- API fallback: < 1000ms

**Source Selection Validation**:
- Highest resolution source selected
- Cost-effective source preferred
- Fallback mechanisms tested

## Configuration

### Environment Variables

```bash
# Primary S3 bucket
AWS_S3_BUCKET_NAME=road-engineering-elevation-data

# High-resolution bucket (optional)
AWS_S3_BUCKET_NAME_HIGH_RES=high-res-elevation-data

# AWS credentials
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=ap-southeast-2

# Source selection options
USE_S3_SOURCES=true
AUTO_SELECT_BEST_SOURCE=true
CACHE_SIZE_LIMIT=50
```

### DEM Sources Configuration

Multi-location sources are configured in environment files:

```json
{
  "au_qld_lidar": {
    "path": "s3://road-engineering-elevation-data/australia/states/qld/AU_QLD_LiDAR_1m.tif",
    "layer": null,
    "crs": "EPSG:28356",
    "description": "Queensland 1m LiDAR"
  },
  "au_nsw_dem": {
    "path": "s3://road-engineering-elevation-data/australia/states/nsw/AU_NSW_DEM_2m.tif",
    "layer": null,
    "crs": "EPSG:28356",
    "description": "NSW 2m DEM"
  },
  "au_national": {
    "path": "s3://road-engineering-elevation-data/australia/national/AU_National_5m_DEM.tif",
    "layer": null,
    "crs": "EPSG:3577",
    "description": "Australia National 5m DEM"
  }
}
```

## Monitoring and Maintenance

### Automated Monitoring

**Health Checks**:
- Catalog integrity validation
- Source availability monitoring
- Cost usage tracking
- Performance metrics

**Alerts**:
- New dataset discovery
- Cost threshold exceeded
- Source failures
- Performance degradation

### Maintenance Tasks

**Daily**:
- Cost usage reports
- Source availability checks
- Performance monitoring

**Weekly**:
- Catalog integrity validation
- New dataset discovery
- Usage pattern analysis

**Monthly**:
- Full catalog export/backup
- Performance baseline updates
- Cost optimization review

## Best Practices

### Adding New Data

1. **Follow naming conventions**:
   - `AU_{STATE}_{TYPE}_{RESOLUTION}.tif`
   - `{city}_metro_{resolution}.tif`
   - `{highway}_corridor_{resolution}.tif`

2. **Organize by hierarchy**:
   - State-level in `/states/`
   - National in `/national/`
   - Specialized in `/corridors/`

3. **Test integration**:
   - Run discovery after upload
   - Validate catalog integrity
   - Test source selection

### Cost Optimization

1. **Use appropriate resolution**:
   - 1m for urban areas
   - 5m for regional coverage
   - 30m for fallback only

2. **Implement caching**:
   - Dataset caching for frequent queries
   - Response caching for repeated requests
   - Regional query optimization

3. **Monitor usage**:
   - Track daily transfer volumes
   - Analyze query patterns
   - Optimize source selection

## Future Enhancements

### Planned Features

1. **Automated Data Ingestion**:
   - CI/CD pipeline for new data
   - Automated quality validation
   - Metadata extraction

2. **Advanced Analytics**:
   - Usage pattern analysis
   - Cost optimization recommendations
   - Performance benchmarking

3. **Multi-Region Support**:
   - International data sources
   - Regional failover
   - Global coverage expansion

### Integration Opportunities

1. **Geoscience Australia Integration**:
   - Automated data feeds
   - Official dataset validation
   - Metadata synchronization

2. **State Government APIs**:
   - Real-time data updates
   - Specialized dataset access
   - Authoritative source validation

This multi-location S3 management system provides a robust, scalable foundation for managing diverse elevation datasets across Australia while maintaining cost-effectiveness and performance optimization.