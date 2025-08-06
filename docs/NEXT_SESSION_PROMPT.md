# Next Session: Complete Auckland Recovery

## Current Status
**Brisbane**: ✅ WORKING - Returns 10.872m elevation in <2s
**Auckland**: ❌ BROKEN - Returns null despite 17 files existing with correct bounds

## What We Know
1. **Index is correct**: File BA32_10000_0401.tiff contains Auckland (-36.8485, 174.7633)
   - Bounds: lat [-36.8783, -36.8126], lon [174.7489, 174.8043]
   - Path: s3://nz-elevation/auckland/auckland-north_2016-2018/dem_1m/2193/BA32_10000_0401.tiff

2. **Pydantic models work**: Bounds parse correctly as WGS84Bounds objects with proper attributes

3. **Debug logging added**: Will show if NZ collections are being found in bounds check

## Next Steps

### Step 1: Check Debug Logs
Wait for Railway deployment and test Auckland to see debug output:
```bash
curl -s "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation?lat=-36.8485&lon=174.7633"
```

Look for these log messages in Railway:
- "✅ NZ collection {id} passed bounds check for Auckland"
- "🔍 Auckland search: Found {n} NZ collections"

### Step 2: Diagnose Based on Logs

**If NO NZ collections found**:
- Issue is in collection bounds checking (line 365-375 in collection_handlers.py)
- Check if NZ collections have 'country' attribute set correctly
- Check if bounds are being parsed as dicts vs objects

**If NZ collections found but no files**:
- Issue is in file bounds checking (line 41-68 in collection_handlers.py)
- Already added dict fallback, but may need more investigation

**If timeout or hang**:
- Issue is in GDAL/rasterio extraction for NZ files
- Check if NZ public bucket access is working

### Step 3: Apply Minimal Fix
Based on diagnosis, apply the simplest fix that makes Auckland work:
- No architectural changes
- No optimization attempts
- Just make it return ~25m elevation

### Step 4: Validate Success
Run integration test to confirm both coordinates work:
```bash
python tests/integration/test_elevation_recovery.py
```

Success criteria:
- Brisbane: 10.872m in <2s ✅
- Auckland: 20-30m in <2s ✅

## Important Files
- `src/handlers/collection_handlers.py` - Collection and file bounds checking
- `src/data_sources/unified_s3_source.py` - Main elevation extraction
- `tests/integration/test_elevation_recovery.py` - Integration tests

## Key Principle
**"Make it work, then make it better"** - Focus only on getting Auckland to return elevation. No optimizations until both coordinates work reliably.

## Test Commands
```bash
# Test Brisbane (should work)
curl -s "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation?lat=-27.4698&lon=153.0251" | python -m json.tool

# Test Auckland (currently broken)
curl -s "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation?lat=-36.8485&lon=174.7633" | python -m json.tool

# Run integration tests
python tests/integration/test_elevation_recovery.py
```

## Recovery Complete When
Both integration tests pass consistently, showing Brisbane and Auckland returning expected elevations in under 2 seconds.