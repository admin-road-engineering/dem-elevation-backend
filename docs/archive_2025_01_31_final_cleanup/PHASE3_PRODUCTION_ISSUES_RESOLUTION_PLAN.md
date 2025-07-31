# Phase 3 Production Issues - Detailed Resolution Plan
**Date**: 2025-07-24  
**Status**: Ready for Implementation  
**Railway URL**: https://road-engineering-dem-backend-production.up.railway.app

## 📊 Executive Summary

Phase 3 campaign-based selection is working perfectly (Brisbane2019Prj selected with 398x speedup), but four production issues prevent full functionality. This document provides a systematic resolution plan with detailed diagnostic steps.

## 🎯 Current Status

### ✅ Working Components
- **Campaign Intelligence**: Brisbane2019Prj selection with multi-factor scoring
- **Performance Optimization**: 398x Brisbane speedup (1,585 vs 631,556 files)
- **S3 Index Loading**: Campaign index successfully loaded from S3
- **Railway Hobby Deployment**: 8GB RAM environment operational

### ⚠️ Production Issues

## 🚨 Issue #1: S3 File Extraction Failure (P0 - BLOCKING)

### Symptoms
- Campaign selection succeeds: `Brisbane2019Prj` (1,585 files, score: 0.860)
- File matching works: 1 matching file found for coordinate
- Extraction fails: `_extract_elevation_from_s3_file()` returns None
- Result: `elevation_m: null` despite successful campaign selection

### Root Cause Analysis
From logs: "All campaigns failed for coordinate (-27.4698, 153.0251)"

**Possible Causes:**
1. AWS credentials or S3 permissions issue
2. DEM file format incompatibility
3. File bounds don't actually cover the coordinate
4. GDAL/Rasterio S3 access issues
5. Memory constraints or timeouts

### Detailed Resolution Steps

#### Step 1: Enhanced S3 Extraction Logging
```python
# IMPORTANT CORRECTION: dem_file is an S3 key, not a full s3:// URL
# In enhanced_source_selector.py - _extract_elevation_from_s3_file method

async def _extract_elevation_from_s3_file(self, dem_file: str, lat: float, lon: float, 
                                         use_credentials: bool = True) -> Optional[float]:
    """Extract elevation with comprehensive error logging"""
    logger.info(f"Starting S3 extraction: key={dem_file} for ({lat}, {lon})")
    
    try:
        # S3 bucket is configured, not part of dem_file
        bucket_name = "road-engineering-elevation-data"  # Or from config
        logger.info(f"S3 bucket: {bucket_name}, key: {dem_file}")
        
        # Test S3 accessibility
        if use_credentials:
            s3_client = boto3.client('s3', 
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                region_name=os.getenv('AWS_DEFAULT_REGION', 'ap-southeast-2')
            )
            
            # Check if file exists
            try:
                response = s3_client.head_object(Bucket=bucket_name, Key=dem_file)
                logger.info(f"S3 file exists: size={response['ContentLength']} bytes, "
                           f"type={response.get('ContentType', 'unknown')}, "
                           f"modified={response['LastModified']}")
            except ClientError as e:
                error_code = e.response['Error']['Code']
                logger.error(f"S3 access error: {error_code} - {e}")
                if error_code == '404':
                    logger.error(f"File not found in S3: {bucket_name}/{dem_file}")
                elif error_code == '403':
                    logger.error(f"Access denied to S3 file (check IAM permissions)")
                return None
        
        # Construct VSI path for GDAL
        vsi_path = f"/vsis3/{bucket_name}/{dem_file}"
        logger.info(f"Opening rasterio dataset from VSI path: {vsi_path}")
        
        # Monitor memory before opening large file
        import psutil
        process = psutil.Process()
        memory_before = process.memory_info().rss / 1024 / 1024
        logger.info(f"Memory before S3 open: {memory_before:.2f} MB")
        
        with rasterio.open(vsi_path) as dataset:
            # Log dataset properties
            logger.info(f"Dataset opened successfully")
            logger.info(f"  Driver: {dataset.driver}")
            logger.info(f"  CRS: {dataset.crs}")
            logger.info(f"  Bounds: {dataset.bounds}")
            logger.info(f"  Shape: {dataset.shape}")
            logger.info(f"  Transform: {dataset.transform}")
            logger.info(f"  Bands: {dataset.count}")
            logger.info(f"  Data types: {dataset.dtypes}")
            logger.info(f"  Nodata value: {dataset.nodata}")
            
            # Check if coordinate is within bounds
            if not (dataset.bounds.left <= lon <= dataset.bounds.right and 
                    dataset.bounds.bottom <= lat <= dataset.bounds.top):
                logger.warning(f"Coordinate ({lat}, {lon}) outside dataset bounds")
                logger.warning(f"  Bounds: left={dataset.bounds.left}, right={dataset.bounds.right}, "
                              f"bottom={dataset.bounds.bottom}, top={dataset.bounds.top}")
                return None
            
            # Transform coordinate to pixel indices
            try:
                row, col = dataset.index(lon, lat)
                logger.info(f"Pixel coordinates: row={row}, col={col}")
                
                # Validate pixel indices
                if row < 0 or col < 0 or row >= dataset.shape[0] or col >= dataset.shape[1]:
                    logger.error(f"Pixel indices out of bounds: row={row}, col={col}, "
                                f"shape={dataset.shape}")
                    return None
                    
            except Exception as e:
                logger.error(f"Coordinate transformation failed: {e}")
                return None
            
            # Read elevation value
            try:
                elevation = dataset.read(1)[row, col]
                logger.info(f"Raw elevation value: {elevation}, type: {type(elevation)}")
                
                # Check for nodata
                if dataset.nodata is not None and elevation == dataset.nodata:
                    logger.warning(f"Elevation is nodata value: {dataset.nodata}")
                    return None
                
                # Check for invalid values
                if np.isnan(elevation) or np.isinf(elevation):
                    logger.warning(f"Invalid elevation value: {elevation}")
                    return None
                    
                return float(elevation)
                
            except IndexError as e:
                logger.error(f"Index error reading elevation: {e}")
                logger.error(f"Attempted to read row={row}, col={col} from shape={dataset.shape}")
                return None
                
    except ImportError as e:
        logger.error(f"Rasterio import error: {e}")
        logger.error("Check if rasterio is installed in requirements.txt")
        return None
    except MemoryError as e:
        memory_current = process.memory_info().rss / 1024 / 1024
        logger.error(f"Memory error: current usage {memory_current:.2f} MB")
        logger.error(f"Memory increase: {memory_current - memory_before:.2f} MB")
        return None
    except Exception as e:
        logger.error(f"S3 extraction failed: {type(e).__name__}: {e}")
        logger.error(f"Full traceback:", exc_info=True)
        return None
    finally:
        # Log memory after operation
        if 'process' in locals():
            memory_after = process.memory_info().rss / 1024 / 1024
            logger.info(f"Memory after S3 operation: {memory_after:.2f} MB")
```

#### Step 2: AWS Credential Verification
```bash
# Verify AWS credentials in Railway
railway variables --service cda12ccf-822d-4bb9-b804-44099401b462 --kv | grep -E "AWS_|S3_"

# Should show:
# AWS_ACCESS_KEY_ID=AKIA***************
# AWS_SECRET_ACCESS_KEY=************************
# AWS_DEFAULT_REGION=ap-southeast-2
# S3_INDEX_BUCKET=road-engineering-elevation-data

# Test AWS credentials locally
aws s3 ls s3://road-engineering-elevation-data/ --profile railway-dem
```

#### Step 3: GDAL/Rasterio Configuration
```python
# Add GDAL configuration debugging
import os
logger.info("GDAL environment variables:")
for key, value in os.environ.items():
    if key.startswith(('GDAL_', 'CPL_', 'AWS_')):
        # Mask sensitive values
        if 'KEY' in key or 'SECRET' in key:
            value = '***masked***'
        logger.info(f"  {key}={value}")

# Check rasterio/GDAL version compatibility
import rasterio
logger.info(f"Rasterio version: {rasterio.__version__}")
logger.info(f"GDAL version: {rasterio.__gdal_version__}")
```

## 🚨 Issue #2: GPXZ/Google Fallback Not Working (P1)

### Symptoms
- Empty attempted sources: `"attempted_sources": []`
- No elevation for any coordinates (even NYC)
- Suggests initialization or configuration failure

### Detailed Resolution Steps

#### Step 1: Source Selector Initialization Debugging
```python
# In enhanced_source_selector.py __init__
def __init__(self, config: Dict[str, Any], use_s3: bool = True, use_apis: bool = True,
             gpxz_config: Optional[GPXZConfig] = None, google_api_key: Optional[str] = None):
    logger.info("=== EnhancedSourceSelector Initialization ===")
    logger.info(f"Parameters:")
    logger.info(f"  use_s3: {use_s3}")
    logger.info(f"  use_apis: {use_apis}")
    logger.info(f"  config sources: {list(config.keys())}")
    logger.info(f"  gpxz_config: {gpxz_config is not None}")
    logger.info(f"  google_api_key: {'set' if google_api_key else 'missing'}")
    
    # Initialize components
    self.use_s3 = use_s3
    self.use_apis = use_apis
    
    # Check campaign selector
    if use_s3:
        logger.info("Initializing CampaignDatasetSelector...")
        self.campaign_selector = CampaignDatasetSelector(use_s3_indexes=True)
        logger.info(f"Campaign selector initialized: {self.campaign_selector is not None}")
    
    # Check GPXZ client
    if use_apis and gpxz_config:
        logger.info("Initializing GPXZ client...")
        self.gpxz_client = GPXZClient(gpxz_config)
        logger.info(f"GPXZ client initialized: {self.gpxz_client is not None}")
    else:
        logger.warning(f"GPXZ client NOT initialized (use_apis={use_apis}, "
                      f"gpxz_config={gpxz_config is not None})")
    
    # Check Google client
    if use_apis and google_api_key:
        logger.info("Initializing Google client...")
        self.google_client = GoogleElevationClient(google_api_key)
        logger.info(f"Google client initialized: {self.google_client is not None}")
    else:
        logger.warning(f"Google client NOT initialized (use_apis={use_apis}, "
                      f"google_api_key={'set' if google_api_key else 'missing'})")
```

#### Step 2: Add Missing API Keys
```bash
# Check current API keys
railway variables --service cda12ccf-822d-4bb9-b804-44099401b462 --kv | grep -E "GPXZ|GOOGLE"

# Add GPXZ API key if missing
railway variables --service cda12ccf-822d-4bb9-b804-44099401b462 --set "GPXZ_API_KEY=your_gpxz_api_key"

# Add Google API key if needed
railway variables --service cda12ccf-822d-4bb9-b804-44099401b462 --set "GOOGLE_MAPS_API_KEY=your_google_api_key"
```

#### Step 3: Fix Source Attempt Logic
```python
# In get_elevation_with_resilience method
async def get_elevation_with_resilience(self, lat: float, lon: float) -> Dict[str, Any]:
    """Get elevation with comprehensive error handling"""
    logger.info(f"=== Starting elevation query for ({lat}, {lon}) ===")
    self.attempted_sources = []
    last_error = None
    
    # Debug source configuration
    source_attempts = [
        ("s3_sources", self._try_s3_sources_with_campaigns),
        ("gpxz_api", self._try_gpxz_source),
        ("google_api", self._try_google_source)
    ]
    
    logger.info(f"Configured source attempts: {[name for name, func in source_attempts]}")
    logger.info(f"Source functions available:")
    for name, func in source_attempts:
        logger.info(f"  {name}: {func is not None} ({func.__name__ if func else 'None'})")
    
    # Check what's enabled
    logger.info(f"Source availability:")
    logger.info(f"  S3 enabled: {self.use_s3}, campaign_selector: {self.campaign_selector is not None}")
    logger.info(f"  GPXZ enabled: {self.use_apis}, client: {self.gpxz_client is not None}")
    logger.info(f"  Google enabled: {self.use_apis}, client: {self.google_client is not None}")
```

#### Step 4: Circuit Breaker Diagnostics
```python
# Add circuit breaker state monitoring
def _log_circuit_breaker_status(self):
    """Log status of all circuit breakers"""
    logger.info("Circuit breaker status:")
    for name, cb in self.circuit_breakers.items():
        state = "OPEN" if not cb.is_available() else "CLOSED"
        logger.info(f"  {name}: {state} (failures: {cb.failure_count}/{cb.failure_threshold})")
        if not cb.is_available():
            recovery_time = cb.last_failure_time + cb.recovery_timeout - time.time()
            logger.info(f"    Recovery in: {recovery_time:.1f} seconds")

# Add manual circuit breaker reset for debugging
def reset_all_circuit_breakers(self):
    """Reset all circuit breakers for debugging"""
    logger.warning("Manually resetting all circuit breakers")
    for name, cb in self.circuit_breakers.items():
        cb.reset()
        logger.info(f"  Reset {name}")
```

## 🚨 Issue #3: Contour Endpoint Error (P2)

### Symptoms
- Error: "too many values to unpack (expected 3)"
- Occurs during grid elevation sampling
- Breaks frontend contour visualization

### Detailed Resolution Steps

#### Step 1: Error Location with Stack Trace
```python
# In contour endpoint or service
import traceback

try:
    # The failing line (example)
    lat, lon, elevation = point_data
except ValueError as e:
    logger.error(f"=== Contour Unpacking Error ===")
    logger.error(f"Error message: {e}")
    logger.error(f"Point data type: {type(point_data)}")
    logger.error(f"Point data value: {repr(point_data)}")
    if hasattr(point_data, '__len__'):
        logger.error(f"Point data length: {len(point_data)}")
        if len(point_data) > 0:
            logger.error(f"First element: {repr(point_data[0])}")
    
    # Full stack trace
    logger.error("Stack trace:")
    logger.error(traceback.format_exc())
    
    # Re-raise with more context
    raise ValueError(f"Expected (lat, lon, elevation) tuple, got {type(point_data)}: {repr(point_data)}")
```

#### Step 2: Data Flow Tracing
```python
# Add logging throughout the contour generation pipeline
def generate_contour_data(self, polygon_bounds, grid_resolution):
    logger.info(f"=== Starting contour generation ===")
    logger.info(f"Polygon bounds: {polygon_bounds}")
    logger.info(f"Grid resolution: {grid_resolution}m")
    
    # Log grid generation
    grid_points = self._generate_grid_points(polygon_bounds, grid_resolution)
    logger.info(f"Generated {len(grid_points)} grid points")
    logger.debug(f"Sample grid points: {grid_points[:3]}")
    
    # Log elevation extraction
    elevation_points = []
    for i, point in enumerate(grid_points):
        logger.debug(f"Processing grid point {i}: {point}")
        
        # Check point structure
        if isinstance(point, (list, tuple)):
            logger.debug(f"  Point is {type(point)} with {len(point)} elements")
        elif isinstance(point, dict):
            logger.debug(f"  Point is dict with keys: {list(point.keys())}")
        
        # Extract elevation (this might be where it fails)
        try:
            if len(point) == 2:
                lat, lon = point
                elevation = self._get_elevation(lat, lon)
                elevation_points.append((lat, lon, elevation))
            elif len(point) == 3:
                lat, lon, elevation = point
                elevation_points.append((lat, lon, elevation))
            else:
                logger.error(f"Unexpected point format: {point}")
        except Exception as e:
            logger.error(f"Failed to process point {i}: {e}")
```

#### Step 3: Flexible Data Structure Handling
```python
# Robust point data handling
def _process_elevation_point(self, point_data):
    """Extract lat, lon, elevation from various data structures"""
    
    # Handle tuple/list
    if isinstance(point_data, (tuple, list)):
        if len(point_data) == 2:
            lat, lon = point_data
            return lat, lon, None  # Elevation to be fetched
        elif len(point_data) == 3:
            return point_data  # lat, lon, elevation
        else:
            raise ValueError(f"Expected 2 or 3 elements, got {len(point_data)}")
    
    # Handle dict/object
    elif isinstance(point_data, dict):
        lat = point_data.get('lat') or point_data.get('latitude')
        lon = point_data.get('lon') or point_data.get('longitude')
        elevation = point_data.get('elevation') or point_data.get('elevation_m')
        
        if lat is None or lon is None:
            raise ValueError(f"Missing lat/lon in dict: {list(point_data.keys())}")
        
        return lat, lon, elevation
    
    # Handle custom objects
    elif hasattr(point_data, 'lat') and hasattr(point_data, 'lon'):
        return point_data.lat, point_data.lon, getattr(point_data, 'elevation', None)
    
    else:
        raise ValueError(f"Unsupported point data type: {type(point_data)}")
```

## 🚨 Issue #4: Dataset Management Endpoints Missing (P3)

### Symptoms
- `/api/v1/datasets/campaigns` returns 404
- Campaign analytics not accessible
- Routes not registered

### Detailed Resolution Steps

#### Step 1: Check Current Route Registration
```python
# In main.py, add route debugging
@app.on_event("startup")
async def log_routes():
    """Log all registered routes for debugging"""
    logger.info("=== Registered API Routes ===")
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            logger.info(f"  {route.path} [{', '.join(route.methods)}]")
    
    # Check for dataset routes
    dataset_routes = [r for r in app.routes if '/datasets' in getattr(r, 'path', '')]
    if not dataset_routes:
        logger.warning("No dataset routes found!")
```

#### Step 2: Register Dataset Routes
```python
# In main.py, after other route registrations
from .api.v1 import endpoints  # Existing elevation endpoints
from .api.v1 import dataset_endpoints  # Dataset management endpoints

# Register elevation routes
app.include_router(
    endpoints.router,
    prefix="/api/v1/elevation",
    tags=["elevation"]
)

# Register dataset management routes
app.include_router(
    dataset_endpoints.router,
    prefix="/api/v1/datasets",
    tags=["datasets"]
)

logger.info("Dataset management routes registered at /api/v1/datasets")
```

#### Step 3: Verify Dataset Endpoints Implementation
```python
# Check src/api/v1/dataset_endpoints.py
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, List, Any
from ...campaign_dataset_selector import CampaignDatasetSelector

router = APIRouter()

@router.get("/campaigns")
async def get_campaigns() -> Dict[str, Any]:
    """Get all available campaigns with metadata"""
    try:
        selector = CampaignDatasetSelector(use_s3_indexes=True)
        
        # Get campaign statistics
        stats = selector.get_performance_stats()
        
        # Get campaign list
        campaigns = []
        if selector.campaign_index and "datasets" in selector.campaign_index:
            for campaign_id, campaign_info in selector.campaign_index["datasets"].items():
                campaigns.append({
                    "campaign_id": campaign_id,
                    "provider": campaign_info.get("provider", "unknown"),
                    "resolution_m": campaign_info.get("resolution_m", "unknown"),
                    "campaign_year": campaign_info.get("campaign_year", "unknown"),
                    "file_count": len(campaign_info.get("files", [])),
                    "bounds": campaign_info.get("bounds", {}),
                    "priority": campaign_info.get("priority", 99)
                })
        
        return {
            "total_campaigns": len(campaigns),
            "campaigns": campaigns,
            "statistics": stats
        }
        
    except Exception as e:
        logger.error(f"Failed to get campaigns: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/campaigns/{campaign_id}")
async def get_campaign_details(campaign_id: str) -> Dict[str, Any]:
    """Get detailed information about a specific campaign"""
    # Implementation details...
```

## 📋 Implementation Checklist

### Phase 1: Critical S3 Fix (2-3 hours)
- [ ] Deploy enhanced S3 extraction logging
- [ ] Verify AWS credentials and permissions
- [ ] Check GDAL/Rasterio configuration
- [ ] Identify specific S3 extraction failure
- [ ] Implement targeted fix
- [ ] Test Brisbane elevation with campaign attribution

### Phase 2: API Fallback Fix (1 hour)
- [ ] Add comprehensive initialization logging
- [ ] Set GPXZ_API_KEY in Railway
- [ ] Set GOOGLE_MAPS_API_KEY if needed
- [ ] Debug source attempt logic
- [ ] Check circuit breaker states
- [ ] Test NYC coordinate with GPXZ fallback

### Phase 3: Feature Fixes (1.5 hours)
- [ ] Add contour endpoint error logging
- [ ] Trace data flow in contour generation
- [ ] Fix unpacking error with flexible handling
- [ ] Register dataset management routes
- [ ] Verify dataset endpoints work
- [ ] Test full feature set

## 🎯 Success Validation

### Test Suite
```bash
# 1. Brisbane Campaign Test (S3)
curl -X POST "https://road-engineering-dem-backend-production.up.railway.app/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'
# Expected: elevation_m with "dem_source_used": "Brisbane2019Prj"

# 2. Sydney Campaign Test (S3)
curl -X POST "https://road-engineering-dem-backend-production.up.railway.app/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -33.8688, "longitude": 151.2093}'
# Expected: elevation_m with campaign-specific source

# 3. NYC GPXZ Fallback Test
curl -X POST "https://road-engineering-dem-backend-production.up.railway.app/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": 40.7589, "longitude": -73.9851}'
# Expected: elevation_m with "dem_source_used": "gpxz_api"

# 4. Contour Generation Test
curl -X POST "https://road-engineering-dem-backend-production.up.railway.app/api/v1/elevation/contour-data" \
  -H "Content-Type: application/json" \
  -d '{
    "area_bounds": {
      "polygon_coordinates": [
        {"latitude": -27.468, "longitude": 153.024},
        {"latitude": -27.470, "longitude": 153.024},
        {"latitude": -27.470, "longitude": 153.026},
        {"latitude": -27.468, "longitude": 153.026},
        {"latitude": -27.468, "longitude": 153.024}
      ]
    },
    "grid_resolution_m": 20.0
  }'
# Expected: Grid elevation data

# 5. Campaign Management Test
curl "https://road-engineering-dem-backend-production.up.railway.app/api/v1/datasets/campaigns"
# Expected: List of campaigns with metadata
```

## 📈 Success Metrics

### Minimum Viable Production
- ✅ Brisbane returns elevation with campaign ID (e.g., "Brisbane2019Prj")
- ✅ NYC returns elevation via GPXZ fallback
- ✅ Campaign metadata included in responses

### Full Production
- ✅ All S3 campaign elevations working
- ✅ Complete fallback chain operational (S3 → GPXZ → Google)
- ✅ Contour generation functional
- ✅ Dataset management API accessible
- ✅ 398x Brisbane performance demonstrated

## 🚀 Next Steps

1. Begin with Phase 1 enhanced S3 logging deployment
2. Identify root cause from detailed logs
3. Implement targeted fixes based on findings
4. Progress through phases systematically
5. Validate each fix before moving to next phase

This plan incorporates all feedback corrections and provides a clear path to full production functionality with Phase 3 campaign-based attribution.