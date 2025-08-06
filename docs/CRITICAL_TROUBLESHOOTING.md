# Critical Troubleshooting Guide

**Purpose**: Prevent regressions and provide systematic debugging for elevation service failures.

## 🚨 Critical Failure Patterns

### Pattern 1: NZ Coordinates Returning Null Elevation

**Symptoms**:
- Auckland (-36.8485, 174.7633) returns `elevation_m: null`
- Brisbane works fine (returns ~10.87m)
- Processing time < 100ms (fails fast)

**Root Causes & Solutions**:

#### 1. AttributeError: FileEntry object has no attribute 'path'
**Cause**: NZ `FileEntry` objects use `file` attribute, AU collections might use `path`  
**Location**: `src/handlers/collection_handlers.py` debug logging  
**Fix**: Always use `getattr(file_entry, 'filename', file_entry.file.split('/')[-1])`  
**Never**: Access `file_entry.path` directly

#### 2. Collection Priority Issues
**Cause**: AU collections getting higher priority than NZ for NZ coordinates  
**Location**: `src/handlers/collection_handlers.py:get_collection_priority()`  
**Debug**: Check if AU collections have absurdly wide bounds (348° longitude)  
**Fix**: Ensure NZ collections get 10,000x priority boost for NZ coordinates

#### 3. Collection Handler Registration
**Cause**: NewZealandCampaignHandler not registered or not matching collections  
**Location**: `src/handlers/collection_handlers.py:CollectionHandlerRegistry.__init__()`  
**Fix**: Verify handler order and `can_handle()` logic

### Pattern 2: Both AU/NZ Coordinates Failing

**Symptoms**:
- Both Brisbane and Auckland return null
- Longer processing times (>1s)
- "No collections found" or "No files found" messages

**Root Causes & Solutions**:

#### 1. Unified Index Loading Failure
**Cause**: S3 index not loaded or corrupted  
**Location**: `src/data_sources/unified_s3_source.py:initialize()`  
**Debug**: Check health endpoint `/api/v1/health` for `collections_available`  
**Fix**: Verify S3 credentials and `UNIFIED_INDEX_PATH` setting

#### 2. Pydantic Model Parsing Issues
**Cause**: Index JSON structure doesn't match Pydantic models  
**Location**: `src/models/unified_spatial_models.py`  
**Debug**: Test with `python test_pydantic_parsing.py`  
**Fix**: Ensure index schema matches model structure

## 🔧 Systematic Debugging Workflow

### Step 1: Health Check
```bash
curl -s "https://re-dem-elevation-backend.up.railway.app/api/v1/health" | python -m json.tool
```
**Look for**:
- `collections_available: 1582` (should be >1500)
- `provider_type: "unified"`
- `unified_mode: true`

### Step 2: Test Known Coordinates
```bash
# Auckland (should return ~25.0m)
curl -s "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation?lat=-36.8485&lon=174.7633" | python -m json.tool

# Brisbane (should return ~10.87m) 
curl -s "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation?lat=-27.4698&lon=153.0251" | python -m json.tool
```

### Step 3: Collection Discovery Test
Create local test script:
```python
#!/usr/bin/env python3
import json
import boto3
from src.models.unified_spatial_models import UnifiedSpatialIndex
from src.handlers.collection_handlers import CollectionHandlerRegistry

# Load index and test collection finding
# [Use test_backend_workflow.py as template]
```

### Step 4: File Discovery Test  
```python
# Test if files are found in top NZ collection
# Check bounds access: file_entry.bounds.min_lat vs file_entry.bounds['min_lat']
# Verify file path access: file_entry.file vs file_entry.path
```

## ⚠️ Critical Code Locations

### File Path Access Patterns
**CORRECT** (works for both AU/NZ):
```python
# Safe filename access
filename = getattr(file_entry, 'filename', file_entry.file.split('/')[-1])

# Safe file path access  
file_path = getattr(file_entry, 'file', getattr(file_entry, 'path', ''))
```

**INCORRECT** (causes AttributeError):
```python
# NEVER do this - breaks NZ files
filename = file_entry.path.split('/')[-1]
file_path = file_entry.path
```

### Bounds Access Patterns
**CORRECT** (handles both Pydantic models and dicts):
```python
if hasattr(bounds, 'min_lat'):
    # Pydantic model
    lat_in_bounds = bounds.min_lat <= lat <= bounds.max_lat
elif isinstance(bounds, dict) and 'min_lat' in bounds:
    # Dict format
    lat_in_bounds = bounds['min_lat'] <= lat <= bounds['max_lat']
```

### Collection Priority Logic
**CRITICAL**: NZ collections must get massive priority boost:
```python
if hasattr(collection, 'country') and getattr(collection, 'country', None) == 'NZ':
    base_priority *= 10000.0  # HUGE boost to ensure NZ always wins
```

## 🎯 Regression Prevention Checklist

### Before Any Code Changes:
1. ✅ Test Auckland endpoint returns 25.0m elevation
2. ✅ Test Brisbane endpoint returns 10.87m elevation  
3. ✅ Verify health endpoint shows 1582 collections
4. ✅ Check processing times < 10s for both coordinates

### File Path Access Rules:
1. ✅ Never access `file_entry.path` directly
2. ✅ Always use `file_entry.file` or safe getattr patterns
3. ✅ Test with both AU and NZ collections in debug scripts

### Collection Handler Rules:
1. ✅ NZ collections must get 10,000x priority boost
2. ✅ NewZealandCampaignHandler must be registered
3. ✅ Handler `can_handle()` logic must check country attribute

### Bounds Access Rules:
1. ✅ Support both Pydantic models (`bounds.min_lat`) and dicts (`bounds['min_lat']`)
2. ✅ Always check `hasattr()` before attribute access
3. ✅ Test bounds intersection logic with known coordinates

## 🚀 Quick Recovery Commands

### Test Local Backend Workflow:
```bash
python test_backend_workflow.py
```

### Test Pydantic Parsing:
```bash  
python test_pydantic_parsing.py
```

### Test Simple NZ Access:
```bash
python simple_nz_test.py
```

### Deploy Emergency Fix:
```bash
git add -A && git commit -m "fix: emergency elevation service repair" && git push
```

This guide ensures the elevation service remains operational and provides systematic debugging when issues arise.