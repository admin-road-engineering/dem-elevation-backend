# Sydney Elevation Fix Plan

## Current Situation (August 20, 2025)

### What's Working
- Brisbane elevation: ✅ Working (~10.87m via S3)
- Auckland elevation: ✅ Working (~25m via S3) 
- Unified provider: ✅ Loading 1,582 collections
- API endpoints: ✅ All functioning

### What's Broken
- Sydney elevation: ❌ Returns null
- Melbourne elevation: ❌ Returns null
- Perth elevation: ❌ Returns null
- Canberra elevation: ❌ Returns null

### Root Cause
The S3 indexes have corrupted bounds for Sydney campaigns:
- **Index shows**: Sydney bounds at longitude 179 (Pacific Ocean)
- **Reality**: Sydney files exist in S3 at correct longitude ~151
- **Impact**: Spatial queries don't find Sydney files

## Why This Happened

1. Sydney WAS working with API fallback before
2. We switched to unified S3-only architecture 
3. The S3 indexes have always had wrong Sydney bounds
4. When we disabled API fallback, Sydney stopped working

## Fix Options

### Option 1: Re-enable API Fallback (Quick - 30 min)
1. Modify `unified_elevation_provider.py` to create API sources
2. Use FallbackDataSource to chain S3 → GPXZ API
3. Sydney will work via API while Brisbane uses S3

### Option 2: Fix S3 Index (Proper - 2 hours)
1. Download Sydney files from S3
2. Extract actual bounds using rasterio
3. Create corrected index with proper Sydney bounds
4. Upload as new index to S3
5. All cities work via S3

### Option 3: Hybrid Approach (Best - 1 hour)
1. Create a patch file with correct Sydney bounds
2. Apply patch when loading index
3. Upload patched index to S3
4. Minimal code changes, maximum compatibility

## Recommended Action

**Immediate**: Re-enable API fallback (Option 1)
- Restores service to working state
- Sydney works via API
- Brisbane continues via S3

**Long-term**: Fix S3 indexes (Option 2)
- Regenerate indexes with correct bounds
- All cities work via S3
- Better performance

## Technical Details

### Sydney Files in S3
```
Location: nsw-elvis/elevation/1m-dem/z56/Sydney201105/
Example: Sydney201105-LID1-AHD_3146266_56_0002_0002_1m.tif
Actual bounds: lat(-33.73 to -33.71), lon(150.99 to 151.01)
```

### Index Corruption
```json
// Current (WRONG)
"Sydney201105": {
  "coverage_bounds": {
    "min_lat": -37.50,
    "max_lat": -26.22,
    "min_lon": 140.90,  // ❌ Wrong!
    "max_lon": 179.91   // ❌ Wrong!
  }
}

// Should be
"Sydney201105": {
  "coverage_bounds": {
    "min_lat": -34.00,  // Sydney region
    "max_lat": -33.40,
    "min_lon": 150.50,  // ✅ Correct
    "max_lon": 151.70   // ✅ Correct
  }
}
```

## Next Steps

1. Decide on approach (recommend Option 1 for immediate fix)
2. Implement chosen solution
3. Test all major cities
4. Document fix for future reference