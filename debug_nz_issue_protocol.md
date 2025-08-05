# NZ Coordinate Debugging Protocol Implementation

## Phase 1: Diagnosis & Hypothesis

### 1. Reproduce & Document

**Issue**: Auckland, NZ coordinates (-36.8485, 174.7633) returning "No elevation found in available files"

**Timeline of Changes**:
1. **WORKING STATE**: NZ coordinates were returning ~25m elevation successfully
2. **BREAKING CHANGE**: After implementing Phase 6 CRS-aware spatial architecture for AU
3. **AU FIX**: Brisbane now works (10.872m) but NZ broke
4. **CURRENT STATE**: 
   - Brisbane (AU): ✅ Working - 10.872m elevation
   - Auckland (NZ): ❌ Failing - "No elevation found in available files"

**Environmental Conditions**:
- Platform: Railway production
- S3 Buckets:
  - AU: `road-engineering-elevation-data` (private, requires signed requests)
  - NZ: `nz-elevation` (public, requires unsigned requests)
- Elevation extraction: GDAL primary, rasterio fallback

**Expected vs Actual**:
- Expected: Auckland should return ~25m elevation
- Actual: Returns null with "No elevation found in available files"

### 2. Gather & Analyze Evidence

**Key Evidence**:
1. Collections ARE being found (processing time shows work is happening)
2. Files ARE being identified within collections
3. Elevation extraction is FAILING at the GDAL/rasterio level
4. The breaking point was when we added bucket-aware configuration
5. **CRITICAL**: NZ worked BEFORE we added bucket detection logic

**Bucket Detection Test Results**:
- ✅ Bucket detection WORKS for S3 paths: `s3://nz-elevation/...`
- ✅ Bucket detection WORKS for GDAL VSI paths: `/vsis3/nz-elevation/...`
- ✅ Index contains correct paths with proper bucket detection

### 3. Isolate the Fault

The issue is in the elevation extraction layer:
- `_extract_elevation_sync()` for GDAL path
- `_extract_elevation_rasterio_fallback()` for rasterio path

### 4. Formulate Root Cause Hypothesis

**REVISED HYPOTHESIS**: 
Since bucket detection works correctly, the issue is in the environment configuration:
1. We removed `rasterio.env.Env` context manager to fix Brisbane
2. This broke NZ because rasterio needs explicit environment configuration
3. The `s3_environment_for_file` sets OS env vars, but rasterio might not pick them up

## Phase 2: Solution Design & Verification

### 5. Research & Design Solution

**Analysis of Current Code**:
```python
# Current (broken for NZ):
with s3_environment_for_file(file_path) as s3_env:
    with rasterio.open(file_path) as dataset:  # No Env context!
```

**Root Cause**: Rasterio needs its own `Env` context manager to properly handle S3 access

### 6. Assess Downstream Impact

**Proposed Solution**: Conditionally use rasterio.env.Env based on bucket type
- For NZ (public): Use Env with AWS_NO_SIGN_REQUEST
- For AU (private): Use current approach (works)

## Phase 3: Implementation & Validation

### 7. Proposed Fix

```python
def _extract_elevation_rasterio_fallback(self, file_path: str, lat: float, lon: float) -> Optional[float]:
    """Fallback elevation extraction using rasterio when GDAL is not available"""
    try:
        import rasterio
        from rasterio.warp import transform as warp_transform
        from rasterio.env import Env
        from ..utils.bucket_detector import BucketType
        
        # Use bucket-aware environment configuration
        with s3_environment_for_file(file_path) as s3_env:
            logger.debug(f"Rasterio fallback: Using {s3_env.bucket_type.value} configuration")
            
            # For NZ public bucket, need explicit Env context
            if s3_env.bucket_type == BucketType.PUBLIC_UNSIGNED:
                # Public bucket needs explicit unsigned configuration
                with Env(AWS_NO_SIGN_REQUEST='YES', AWS_REGION='ap-southeast-2'):
                    with rasterio.open(file_path) as dataset:
                        # ... rest of code
            else:
                # Private bucket works with environment variables
                with rasterio.open(file_path) as dataset:
                    # ... rest of code
```