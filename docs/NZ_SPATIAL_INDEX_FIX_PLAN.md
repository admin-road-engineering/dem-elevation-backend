# NZ Spatial Index Loading Fix - Step-by-Step Plan

**Date**: 2025-01-31  
**Issue**: NZ spatial index not loading in Railway environment  
**Goal**: Enable NZ S3 sources for 1,700+ NZ elevation files

## 🎯 Problem Analysis

### Current State
- ✅ Geographic routing implemented (NZ coordinates detected)
- ✅ Redis connected to existing addon
- ❌ NZ spatial index not loading in Railway
- ❌ NZ coordinates falling back to GPXZ API instead of S3

### Root Cause Investigation Needed
1. **File deployment**: Is `config/nz_spatial_index.json` deployed to Railway?
2. **Loading logic**: Does spatial index loader include NZ index loading?
3. **Error handling**: Are there silent failures in NZ index loading?

## 📋 Step-by-Step Fix Plan

### Phase 1: Investigate Current State (5-10 minutes)

#### Step 1.1: Verify NZ Index File Deployment
```bash
# Check if NZ spatial index exists in Railway environment
curl "https://dem-elevation-backend-production-9c7a.up.railway.app/debug/settings-info" | jq
```
**Expected**: Should show file system info or config loading details

#### Step 1.2: Check SpatialIndexLoader Implementation
```bash
# Search for NZ index loading in spatial index loader
grep -n "nz_spatial_index\|load_nz_index" src/enhanced_source_selector.py
```
**Expected**: Find methods that load NZ spatial index

#### Step 1.3: Review S3IndexLoader for NZ Support
```bash
# Check if S3IndexLoader includes NZ indexes
grep -n "nz.*index\|NZ.*index" src/s3_index_loader.py
```
**Expected**: Determine if NZ indexes are loaded from S3 or local files

### Phase 2: Identify Loading Mechanism (10-15 minutes)

#### Step 2.1: Understand Index Loading Flow
**Action**: Read `src/enhanced_source_selector.py` SpatialIndexLoader class
**Focus**: How `load_nz_index()` method works
**Check**: 
- Does it load from local `config/nz_spatial_index.json`?
- Is there error handling for missing files?
- Are there any dependencies on S3 index loading?

#### Step 2.2: Check Railway File System
**Action**: Add debug endpoint to check file system
**Code**:
```python
@app.get("/debug/nz-index-status")
async def debug_nz_index_status():
    import os
    config_dir = Path("config")
    nz_index_file = config_dir / "nz_spatial_index.json"
    
    return {
        "config_dir_exists": config_dir.exists(),
        "nz_index_file_exists": nz_index_file.exists(),
        "config_files": list(os.listdir("config")) if config_dir.exists() else [],
        "nz_file_size": nz_index_file.stat().st_size if nz_index_file.exists() else 0
    }
```

#### Step 2.3: Check Index Loading Initialization
**Action**: Review where SpatialIndexLoader is initialized
**Files**: 
- `src/enhanced_source_selector.py` 
- `src/dependencies.py`
- `src/main.py`

### Phase 3: Implement Fix (15-30 minutes)

#### Step 3.1: Add NZ Index to S3IndexLoader (If Missing)
**If NZ index needs S3 loading:**
```python
# In src/s3_index_loader.py
self.required_indexes = [
    os.getenv('S3_CAMPAIGN_INDEX_KEY', 'indexes/campaign_index.json'),
    os.getenv('S3_TILED_INDEX_KEY', 'indexes/phase3_brisbane_tiled_index.json'),
    os.getenv('S3_SPATIAL_INDEX_KEY', 'indexes/spatial_index.json'),
    os.getenv('S3_NZ_INDEX_KEY', 'indexes/nz_spatial_index.json')  # ADD THIS
]
```

#### Step 3.2: Ensure NZ Index File is Committed
```bash
# Check if NZ index is in git
git status config/nz_spatial_index.json
git add config/nz_spatial_index.json  # If not tracked
```

#### Step 3.3: Add Error Logging to NZ Index Loading
```python
# In SpatialIndexLoader.load_nz_index()
def load_nz_index(self) -> Optional[Dict]:
    """Load NZ spatial index with enhanced error logging"""
    if self.nz_spatial_index is None:
        nz_index_file = self.config_dir / "nz_spatial_index.json"
        logger.info(f"Attempting to load NZ spatial index from: {nz_index_file}")
        
        if nz_index_file.exists():
            try:
                with open(nz_index_file, 'r') as f:
                    self.nz_spatial_index = json.load(f)
                    logger.info(f"Successfully loaded NZ spatial index with {len(self.nz_spatial_index.get('regions', {}))} regions")
            except Exception as e:
                logger.error(f"Failed to load NZ spatial index: {e}")
        else:
            logger.warning(f"NZ spatial index file not found: {nz_index_file}")
            logger.info(f"Config directory contents: {list(self.config_dir.glob('*')) if self.config_dir.exists() else 'Config dir does not exist'}")
    
    return self.nz_spatial_index
```

### Phase 4: Test and Deploy (10-15 minutes)

#### Step 4.1: Local Testing
```bash
# Test NZ coordinates locally
python scripts/switch_environment.py production
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -36.8485, "longitude": 174.7633}'
```
**Expected**: Should show NZ S3 source usage or better error messages

#### Step 4.2: Deploy to Railway
```bash
# Commit and push changes
git add src/enhanced_source_selector.py config/nz_spatial_index.json
git commit -m "fix: Add enhanced logging and ensure NZ spatial index deployment"
git push
```

#### Step 4.3: Verify Fix
```bash
# Wait for deployment, then test
sleep 60
curl -X POST "https://dem-elevation-backend-production-9c7a.up.railway.app/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -36.8485, "longitude": 174.7633}'
```
**Success Criteria**: `"dem_source_used": "nz_s3_source"` or S3 campaign name

### Phase 5: Alternative Solutions (If Needed)

#### Option A: Upload NZ Index to S3
If local file loading fails, upload to S3:
```bash
# Upload NZ index to S3 bucket
aws s3 cp config/nz_spatial_index.json s3://road-engineering-elevation-data/indexes/nz_spatial_index.json
```

#### Option B: Embed NZ Index in Code
If file system access is restricted:
```python
# Create src/nz_index_embedded.py with index data
# Import and use in SpatialIndexLoader
```

#### Option C: API-Based Index Loading
Load NZ index from external source:
```python
# Add method to load from URL or API endpoint
```

## 🎯 Success Metrics

### Immediate Success (Phase 4)
1. **NZ Index Loading**: Logs show "Successfully loaded NZ spatial index"
2. **S3 Source Usage**: Auckland coordinates return NZ S3 source
3. **Performance**: Response time improvement for NZ coordinates

### Long-term Success
1. **Coverage**: All NZ coordinates within coverage area use S3
2. **Fallback**: Uncovered NZ areas still use GPXZ API
3. **Cost**: Reduced API usage for covered NZ regions

## 🚨 Troubleshooting Guide

### If NZ Index Still Not Loading
1. **Check Railway logs**: `railway logs | grep -i nz`
2. **Verify file deployment**: Use debug endpoint
3. **Test alternative loading methods**: S3, embedded, API

### If S3 Access Fails
1. **Check AWS credentials**: Verify access to nz-elevation bucket
2. **Test S3 connectivity**: Use health endpoint
3. **Review permissions**: Ensure read access to NZ files

### If Performance Not Improved
1. **Verify coordinate coverage**: Check if test coordinates are in NZ index
2. **Test different coordinates**: Try multiple NZ locations
3. **Compare response times**: Before/after measurements

## 📝 Implementation Checklist

- [ ] **Phase 1**: Investigate current state
- [ ] **Phase 2**: Identify loading mechanism
- [ ] **Phase 3**: Implement fix
- [ ] **Phase 4**: Test and deploy
- [ ] **Phase 5**: Alternative solutions (if needed)

---

**Timeline**: 1-2 hours total  
**Priority**: High - enables performance boost for NZ market  
**Risk**: Low - fallback to GPXZ API already working