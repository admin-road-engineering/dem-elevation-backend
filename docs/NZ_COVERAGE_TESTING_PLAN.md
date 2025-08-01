# New Zealand Coverage Testing & Frontend Integration Plan

**Date**: 2025-01-31  
**Status**: Planning Phase  
**Objective**: Verify NZ S3 bucket usage, test frontend integration, and document comprehensive coverage

## 🎯 Testing Objectives

### 1. New Zealand S3 Bucket Verification
**Issue**: NZ coordinates may not be using the `nz-elevation` S3 bucket as expected
**Expected**: NZ coordinates should use S3 campaigns when available, fallback to GPXZ API when not

### 2. Frontend Integration Testing  
**Issue**: Verify frontend can connect to Railway deployment and display survey campaigns
**Expected**: Frontend displays campaign coverage data from backend `/api/v1/elevation/sources`

### 3. Survey Campaign Coverage Analysis
**Issue**: Document actual coverage areas for NZ S3 bucket vs GPXZ API coverage
**Expected**: Clear coverage maps and source selection logic documentation

## 🧪 Test Plan

### Phase 1: Backend NZ Coverage Analysis

#### 1.1 Test NZ Coordinates Against Different Sources
```bash
# Auckland CBD (should potentially use NZ S3)
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -36.8485, "longitude": 174.7633}'

# Wellington CBD (should potentially use NZ S3)
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -41.2865, "longitude": 174.7762}'

# Christchurch CBD (should potentially use NZ S3)
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -43.5321, "longitude": 172.6362}'

# Remote NZ location (likely GPXZ fallback)
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -45.0312, "longitude": 169.6891}'
```

#### 1.2 Analyze Available NZ Sources
```bash
# Check all NZ sources loaded
curl "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/sources" | \
  jq '.sources[] | select(.source_id | contains("nz") or contains("NZ"))'

# Check total source count
curl "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/sources" | \
  jq '.total_sources'
```

#### 1.3 Review NZ Spatial Index Configuration
```bash
# Check if NZ spatial index exists and is loaded
ls -la config/
cat config/phase3_campaign_populated_index.json | jq 'keys[] | select(. | contains("NZ"))'
```

### Phase 2: Frontend Integration Testing

#### 2.1 Test Frontend Connection to Railway
**Endpoint**: Frontend should connect to `https://dem-elevation-backend-production-9c7a.up.railway.app`
**CORS**: Verify CORS allows frontend origin (localhost:5173/5174/3001)

#### 2.2 Survey Campaign Display Testing
**Frontend Component**: Survey campaigns display tool
**Backend Data**: `/api/v1/elevation/sources` endpoint
**Requirements**:
- Display campaign names and coverage areas
- Show resolution information
- Indicate S3 vs API sources

#### 2.3 Integration Test Scenarios
```bash
# Test health endpoint (should work from frontend)
curl "https://dem-elevation-backend-production-9c7a.up.railway.app/api/v1/health"

# Test sources endpoint (frontend survey display)
curl "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/sources"

# Test elevation endpoint (core functionality)
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -36.8485, "longitude": 174.7633}'
```

### Phase 3: Coverage Documentation & Analysis

#### 3.1 NZ S3 Bucket Analysis
**Bucket**: `nz-elevation` (1,700+ files as per CLAUDE.md)
**Questions to Answer**:
- Which NZ regions have S3 coverage?
- What resolutions are available?
- How does spatial indexing work for NZ?
- Why might NZ coordinates fallback to GPXZ?

#### 3.2 GPXZ API Coverage Analysis  
**Service**: GPXZ.io global elevation API
**Coverage**: Global (100 requests/day free tier)
**Usage Pattern**: Fallback for areas without S3 coverage

#### 3.3 Coverage Comparison Matrix
Create comprehensive comparison of:
- S3 Australian campaigns (1,151 campaigns)
- S3 NZ campaigns (from nz-elevation bucket)
- GPXZ global coverage
- Google Elevation fallback

## 🔍 Investigation Areas

### 1. NZ Spatial Index Configuration
**File**: `config/phase3_campaign_populated_index.json`
**Question**: Does this include NZ campaigns or only Australian?
**Alternative**: Check for separate NZ spatial index file

### 2. Source Selection Logic
**File**: `src/enhanced_source_selector.py`
**Question**: How does IndexDrivenSourceSelector handle NZ coordinates?
**Check**: Geographic bounds and campaign selection logic

### 3. NZ Campaign Loading
**Files**: 
- `src/s3_index_loader.py`
- `config/` directory
**Question**: Are NZ campaigns loaded into spatial index?
**Check**: S3 bucket scanning and campaign metadata

### 4. Frontend API Integration
**Frontend Location**: `C:\Users\Admin\road-engineering-branch\road-engineering`
**Check**: 
- API base URL configuration
- Survey campaign display component
- CORS handling

## 📊 Expected Outcomes

### Success Criteria
1. **NZ S3 Usage**: NZ coordinates use S3 campaigns when available
2. **Frontend Integration**: Frontend successfully displays survey campaigns
3. **Coverage Documentation**: Complete coverage map with clear boundaries
4. **Fallback Logic**: Proper API fallback for uncovered areas

### Failure Scenarios & Solutions
1. **NZ always uses GPXZ**: Check NZ spatial index loading
2. **Frontend connection fails**: Verify CORS and endpoint URLs
3. **Missing campaign data**: Review S3 bucket scanning logic
4. **Internal server errors**: Ensure Redis addon connected

## 🛠️ Diagnostic Commands

### Backend Health Check
```bash
# Verify service status
curl "https://dem-elevation-backend-production-9c7a.up.railway.app/api/v1/health"

# Check Redis connection
railway logs --service dem-elevation-backend | grep -i redis

# Verify environment variables
railway variables --service dem-elevation-backend
```

### Local Development Testing
```bash
# Switch to production environment locally
python scripts/switch_environment.py production

# Test NZ coordinates locally
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -36.8485, "longitude": 174.7633}'

# Check local source loading
curl "http://localhost:8001/api/v1/elevation/sources" | jq '.total_sources'
```

## 📝 Documentation Deliverables

### 1. NZ Coverage Analysis Report
- Actual NZ S3 campaign coverage areas
- Resolution and quality comparison
- Geographic boundaries and gaps

### 2. Frontend Integration Guide
- API endpoint configuration
- Survey campaign display implementation
- Error handling and fallback UI

### 3. Source Selection Logic Documentation
- Decision tree for S3 vs API usage
- Geographic boundary definitions
- Performance characteristics by region

### 4. Troubleshooting Guide Update
- NZ-specific issues and solutions
- Frontend integration common problems
- Performance optimization recommendations

## 🚀 Next Steps

1. **Execute Phase 1**: Test NZ coordinates and analyze backend responses
2. **Execute Phase 2**: Test frontend integration with Railway deployment
3. **Execute Phase 3**: Document comprehensive coverage analysis
4. **Update Documentation**: Integrate findings into existing docs
5. **Performance Testing**: Measure NZ vs Australian coordinate response times

---

**Status**: ✅ Plan Complete - Ready for execution  
**Priority**: High - Critical for NZ market expansion  
**Timeline**: 1-2 hours for complete testing and documentation