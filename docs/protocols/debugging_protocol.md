# DEM Backend Service Diagnostic Protocol
## Critical Issues Resolution Plan

**Service Status**: Previously functional, now experiencing cascading endpoint failures  
**Primary Symptoms**: 
- Campaigns endpoint: `'NoneType' object is not iterable`
- Elevation endpoints: Return null values with extraction errors
- Health check: `collections_available=0` despite legacy conversion logic

---

## 📋 **PHASE 1: ROOT CAUSE IDENTIFICATION**

### 1.1 Data Pipeline Analysis
**Objective**: Trace data flow from S3 index loading to endpoint responses

#### **Step 1.A: Verify S3 Index Configuration**
```bash
# Check current Railway environment configuration
railway variables | grep UNIFIED_INDEX_PATH
```
**Expected**: Should point to valid index with actual data  
**Suspected Issue**: Currently points to `unified_spatial_index_v2_ideal.json` (empty/test file)  
**Resolution**: Change to `indexes/unified_spatial_index_v2.json` (production data)

#### **Step 1.B: Validate Index File Contents**
```bash
# Download and inspect the current index file
aws s3 cp s3://road-engineering-elevation-data/indexes/unified_spatial_index_v2_ideal.json ./debug_index.json
```
**Analysis Points**:
- File size (should be >100MB for full data)
- Contains `campaigns` field (legacy format) or `data_collections` field (new format)
- Campaign count matches expected ~1,582 collections

#### **Step 1.C: Legacy Conversion Process Validation**
**File**: `src/models/unified_wgs84_models.py:130-275`  
**Critical Path**: `model_post_init()` → `_convert_legacy_format()`

**Debug Points**:
1. Is conversion being triggered? (log line 145)
2. Are campaigns being found? (log line 147-150)  
3. Is conversion completing successfully? (log line 261)
4. Are data_collections being populated? (log line 262)

### 1.2 Service Initialization Chain Analysis
**Objective**: Verify each component initializes correctly

#### **Step 1.D: UnifiedWGS84S3Source Initialization**
**File**: `src/data_sources/unified_wgs84_s3_source.py:63-93`

**Critical Checkpoints**:
1. `_load_unified_index_from_s3()` success (line 67)
2. Index parsing without Pydantic errors (line 337)
3. Post-conversion collection count > 0 (line 73-77)

#### **Step 1.E: Endpoint Registration and Response Models**
**File**: `src/api/v1/endpoints.py`

**Critical Issues**:
- Campaigns endpoint iteration over None data_collections
- Elevation endpoints receiving None from unified source
- Response model mismatches causing Pydantic validation failures

---

## 📋 **PHASE 2: SYSTEMATIC ISSUE RESOLUTION**

### 2.1 Data Access Foundation (P0 - Critical)
**Objective**: Restore data pipeline from S3 to service

#### **Step 2.A: Fix S3 Index Configuration**
```bash
# Change Railway environment to point to correct index
railway variables --set "UNIFIED_INDEX_PATH=indexes/unified_spatial_index_v2.json"
```
**Verification**: Redeploy and check health endpoint for `collections_available > 0`

#### **Step 2.B: Enhanced Legacy Conversion Logging**
**File**: `src/models/unified_wgs84_models.py`  
**Action**: Add detailed debug logging to track conversion process:

```python
# Add after line 145
logger.info(f"Campaign sample data: {list(self.campaigns.items())[:2] if self.campaigns else 'None'}")

# Add after line 261
logger.info(f"Collections created: {[c.id for c in converted_collections[:5]]}")
```

#### **Step 2.C: Defensive Data Access Patterns**
**Files**: All data source files  
**Action**: Implement comprehensive None checking:

```python
# Pattern for all collection access
collections = self.unified_index.data_collections or []
for collection in collections:
    # Safe processing
```

### 2.2 Endpoint Stability Restoration (P0 - Critical)
**Objective**: Prevent crashes from None iteration

#### **Step 2.D: Campaigns Endpoint Protection**
**File**: `src/api/v1/endpoints.py` (campaigns endpoint)
**Issue**: Iterating over None data_collections
**Fix**: Add None checking before iteration

#### **Step 2.E: Elevation Endpoints Error Handling**
**Files**: All elevation endpoints  
**Issue**: Chain failures from None source data
**Fix**: Graceful degradation with structured error responses

### 2.3 Response Model Consistency (P1 - High)
**Objective**: Ensure all endpoints return valid structured responses

#### **Step 2.F: Pydantic Model Alignment**
**Action**: Verify response structure matches declared models:
- PathResponse requires `points` and `total_points`
- DEMPoint structure for batch endpoints
- Enhanced response models for metadata

---

## 📋 **PHASE 3: COMPREHENSIVE TESTING & VALIDATION**

### 3.1 Service Health Verification
```bash
# Health endpoint must show collections > 0
curl "https://re-dem-elevation-backend.up.railway.app/api/v1/health"

# Expected result:
{
  "status": "healthy",
  "collections_available": 1582,  # NOT 0
  "provider_type": "unified"
}
```

### 3.2 Critical Coordinate Testing
```bash
# Brisbane (AU) - Must return ~10.87m
curl "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation?lat=-27.4698&lon=153.0251"

# Auckland (NZ) - Must return ~25.0m  
curl "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation?lat=-36.8485&lon=174.7633"
```

### 3.3 All Endpoints Systematic Testing
**Protocol**: Test each endpoint type with known coordinates
- Single elevation: `/api/v1/elevation?lat=X&lon=Y`
- Batch points: `/api/v1/elevation/points`
- Line sampling: `/api/v1/elevation/line`
- Path sampling: `/api/v1/elevation/path`
- Campaigns list: `/api/v1/elevation/campaigns`
- Campaign details: `/api/v1/elevation/campaigns/{id}`

---

## 📋 **PHASE 4: PERFORMANCE & RELIABILITY HARDENING**

### 4.1 Ultimate Performance Index Integration
**Objective**: Implement the performance fix for spatial index bounds bug

**Files**: 
- `create_ultimate_performance_index.py` (ready)
- `create_ultimate_index.bat` (ready)

**Issue**: Current spatial index copies campaign bounds to all files, causing 36x more false matches
**Solution**: Use actual file bounds, reducing Sydney queries from 798 → 22 matches

### 4.2 Production Monitoring Enhancement
**Actions**:
- Implement structured logging for conversion process
- Add performance metrics for S3 index loading
- Create alerting for collections_available=0 condition

---

## 📋 **PHASE 5: REGRESSION PREVENTION**

### 5.1 Automated Testing Suite
**Critical Test Cases**:
1. S3 index loading and parsing
2. Legacy format conversion
3. All endpoint response structures
4. Known coordinate elevation values

### 5.2 Deployment Checklist
**Before ANY deployment**:
- [ ] Health endpoint returns collections > 0
- [ ] Brisbane coordinate returns ~10.87m
- [ ] Auckland coordinate returns ~25.0m
- [ ] All endpoints return structured JSON (not HTML errors)
- [ ] No Pydantic validation errors in responses

---

## 🎯 **EXPECTED OUTCOMES**

### Success Criteria
1. **Health Check**: `collections_available > 1500` (should be ~1582)
2. **Elevation Data**: Actual elevation values returned (not null)
3. **All Endpoints**: Structured JSON responses without internal errors
4. **Performance**: Response times <2s (current), <100ms (with performance fix)

### Failure Indicators
- Health check still shows `collections_available=0`
- Elevation endpoints continue returning null values
- Any endpoint returns `'NoneType' object is not iterable`
- Pydantic validation errors in API responses

---

## 🚨 **CRITICAL DEPENDENCIES**

### Railway Platform
- Environment variable updates require service restart
- S3 credentials must be properly configured
- Index file path must be accessible

### AWS S3 Infrastructure  
- `road-engineering-elevation-data` bucket accessibility
- Proper index file at specified path
- S3 credentials with read permissions

### Legacy Data Compatibility
- Conversion logic must handle both old and new schemas
- Backward compatibility during transition period
- Graceful fallback for missing data fields

---

**This protocol provides systematic approach to restore full service functionality while preventing regression of previously working features.**

**Priority Order**: Data Access (P0) → Endpoint Stability (P0) → Response Models (P1) → Performance (P2) → Testing (P2)