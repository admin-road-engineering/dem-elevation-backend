# DEM Backend Recovery Plan

## Problem Statement
Both Brisbane (AU) and Auckland (NZ) coordinates worked individually at different points, but now both are broken after multiple "optimization" attempts. We've over-engineered the solution.

## Root Cause Analysis

### Brisbane (AU) Issue
- **Symptom**: GDAL opens files successfully but `_gdal_array` import fails, forcing rasterio fallback
- **Current Error**: `"GDAL's AWS config options can not be directly set. AWS credentials are handled exclusively by boto3"`
- **Root Cause**: Over-complicated session management when simple env vars likely worked

### Auckland (NZ) Issue  
- **Symptom**: Collections found (73 eligible) but 0 files discovered in each collection
- **Root Cause**: Bounds/CRS logic changes broke file discovery

## Recovery Strategy

### Principle: MINIMAL CHANGES ONLY
**Goal**: Get both coordinates working with the simplest possible approach, then stop.

### Step 1: Fix GDAL Array Import (Brisbane)
- **Approach**: Ensure GDAL can import `_gdal_array` properly
- **Alternative**: If GDAL broken, make rasterio work with SIMPLE environment variables
- **Avoid**: Complex boto3 session management, bucket detection logic

### Step 2: Fix File Discovery (Auckland)  
- **Approach**: Revert to simple file discovery logic that worked before
- **Focus**: Ensure bounds checking works correctly for NZ collections
- **Avoid**: Complex CRS transformation chains

### Step 3: Test and Stop
- **Verify**: Both Brisbane and Auckland return correct elevations
- **Document**: What the minimal working approach is
- **Stop**: No additional "optimizations" until both work consistently

## What NOT to Do

### Avoid Over-Engineering
- ❌ Complex bucket detection strategies
- ❌ Singleton session patterns (until basic functionality works)
- ❌ Multiple context managers
- ❌ Sophisticated error handling that masks root issues

### Focus on Basics
- ✅ Simple environment variable approach
- ✅ Basic rasterio/GDAL file access
- ✅ Minimal bounds checking
- ✅ Clear error messages

## Success Criteria

1. **Brisbane (-27.4698, 153.0251)**: Returns ~10.872m elevation
2. **Auckland (-36.8485, 174.7633)**: Returns ~25m elevation  
3. **Response Time**: <2s for both (performance optimization comes later)
4. **Reliability**: Works consistently across multiple requests

## Post-Recovery Phase

**Only after both coordinates work reliably:**
- Then consider Gemini's architectural improvements
- Then implement performance optimizations
- Then add sophisticated error handling

## Key Lesson

**"Make it work, then make it better"** - not the other way around.