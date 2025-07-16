# DEM Backend API Testing Plan

## Overview
This document outlines the comprehensive testing strategy for all external APIs and S3 connections used by the DEM Backend service.

## External Service Connections

### 1. GPXZ.io API (Third-Party Elevation Service)
**Service**: Global elevation data API  
**Base URL**: `https://api.gpxz.io`  
**Purpose**: Provides elevation data for areas not covered by local/S3 sources  

**Endpoints:**
- `GET /v1/elevation/point` - Single point elevation
- `POST /v1/elevation/points` - Batch elevation requests (up to 100 points)

**Authentication:**
- API Key: `ak_zj8pF60R_1h0s4aVF52KDSBMq` (visible in api-test config)
- Header: `X-API-Key: {api_key}`

**Rate Limits:**
- **Free Tier**: 100 requests/day, 1 request/second
- **Production**: 7,500 requests/day, 25 requests/second

**Test Scenarios:**
- ✅ API key validation
- ✅ Single point elevation request
- ✅ Rate limiting behavior
- ✅ Error handling for invalid coordinates
- ✅ Daily quota management

### 2. AWS S3 Storage Services

#### **Primary Bucket**: `road-engineering-elevation-data`
**Purpose**: Private S3 bucket for Australian DEM data  
**Region**: `ap-southeast-2` (Asia Pacific - Sydney)  
**Authentication**: AWS Access Key ID + Secret Access Key  

**DEM Files:**
- `AU_QLD_LiDAR_1m.tif` - Queensland 1m LiDAR (high resolution)
- `AU_National_5m_DEM.tif` - Australia National 5m DEM
- `AU_SRTM_1ArcSec.tif` - Global SRTM 30m fallback

**Cost Considerations:**
- Estimated 3.6TB total data
- S3CostManager limits: 1GB daily in development
- Production: Unlimited but monitored

**Test Scenarios:**
- ✅ AWS credentials validation
- ✅ Bucket access permissions
- ✅ File existence checks
- ✅ Download performance
- ✅ Cost tracking functionality

#### **Secondary Bucket**: `nz-elevation` (NZ Open Data)
**Purpose**: New Zealand elevation data (public AWS Open Data)  
**Region**: `ap-southeast-2`  
**Authentication**: No credentials required (public bucket)  

**DEM Files:**
- `canterbury/canterbury_2018-2019_DEM_1m.tif`
- `north-island/north-island_2021_DEM_1m.tif`  
- `wellington/wellington_2013-2014_DEM_1m.tif`

**Test Scenarios:**
- ✅ Public bucket access
- ✅ File availability
- ✅ Download without credentials

### 3. Main Platform Integration
**Production API**: `https://api.road.engineering`  
**Production Frontend**: `https://road.engineering`  
**Development API**: `http://localhost:3001`  
**Development Frontend**: `http://localhost:5173`  

**Integration Points:**
- JWT authentication via Supabase
- CORS configuration
- Microservice communication

**Test Scenarios:**
- ✅ Main platform health check
- ✅ CORS configuration
- ✅ JWT authentication flow
- ✅ Microservice communication

### 4. DEM Backend Internal APIs
**Base URL**: `http://localhost:8001` (development)  
**Production**: `https://dem-api.road.engineering`  

**Core Endpoints:**
- `GET /health` - Health check
- `GET /api/v1/elevation/sources` - List available sources
- `POST /api/v1/elevation/point` - Single point elevation
- `POST /api/v1/elevation/line` - Line elevation profile
- `POST /api/v1/elevation/path` - Path elevation (batch)

**Test Scenarios:**
- ✅ Health endpoint
- ✅ Source enumeration
- ✅ Point elevation requests
- ✅ Error handling
- ✅ Response time performance

## Testing Environments

### **Local Development** (`.env.local`)
**Sources**: Local files only  
**Cost**: Zero  
**External Connections**: None  

**Test Focus:**
- Local file access
- Geodatabase connectivity
- GeoTIFF processing

### **API Testing** (`.env.api-test`)
**Sources**: GPXZ API (free tier) + NZ Open Data + Local fallback  
**Cost**: Free tier limits  
**External Connections**: GPXZ.io, NZ Open Data S3  

**Test Focus:**
- GPXZ API integration
- Public S3 access
- Rate limiting
- Fallback mechanisms

### **Production** (`.env.production`)
**Sources**: Full multi-source (S3 + APIs + Local)  
**Cost**: S3 storage + transfer, GPXZ paid tier  
**External Connections**: All services  

**Test Focus:**
- AWS S3 private bucket access
- High-volume API usage
- Cost management
- Performance under load

## Test Execution Plan

### Phase 1: Environment Setup
1. **Verify credentials** for each environment
2. **Switch environments** using `scripts/switch_environment.py`
3. **Check service availability** for external APIs

### Phase 2: Individual Service Testing
1. **GPXZ API Tests**:
   ```bash
   python scripts/test_api_plan.py --service gpxz
   ```

2. **S3 Connection Tests**:
   ```bash
   python scripts/test_api_plan.py --service s3
   ```

3. **DEM Backend Tests**:
   ```bash
   python scripts/test_api_plan.py --service dem-backend
   ```

### Phase 3: Integration Testing
1. **End-to-end elevation requests**
2. **Source selection logic**
3. **Fallback mechanisms**
4. **Error handling**

### Phase 4: Performance Testing
1. **Response time benchmarks**
2. **Rate limiting validation**
3. **Cost monitoring**
4. **Concurrent request handling**

## Test Automation

### **Primary Test Script**: `scripts/test_api_plan.py`
**Usage:**
```bash
# Run all tests
python scripts/test_api_plan.py

# Test specific service
python scripts/test_api_plan.py --service gpxz

# Generate JSON report
python scripts/test_api_plan.py --json > test_report.json
```

**Features:**
- Comprehensive service testing
- Performance metrics
- Error reporting
- JSON output for CI/CD

### **Existing Test Scripts**
- `scripts/post_deploy_smoke_test.py` - Production deployment testing
- `tests/test_phase2_integration.py` - Integration testing
- `tests/test_s3_connection.py` - S3 specific tests

## Security Considerations

### **API Keys & Credentials**
- ⚠️ **GPXZ API key exposed** in `.env.api-test`
- ✅ **AWS credentials** via environment variables
- ✅ **JWT secrets** properly configured

### **Rate Limiting**
- ✅ **GPXZ API** - Client-side rate limiting implemented
- ✅ **S3 Access** - Cost-based limiting
- ✅ **DEM Backend** - FastAPI rate limiting

### **Cost Controls**
- ✅ **S3CostManager** - Daily usage limits
- ✅ **GPXZ quotas** - Daily request limits
- ✅ **Circuit breakers** - Prevent cascade failures

## Monitoring & Alerting

### **Metrics to Track**
- API response times
- Error rates by service
- S3 transfer volumes
- GPXZ API usage
- Source selection patterns

### **Alert Thresholds**
- API response time > 500ms
- Error rate > 5%
- Daily S3 usage > 1GB (development)
- GPXZ quota > 80% used

## Test Reporting

### **Test Results Location**
- `api_test_report.json` - Detailed test results
- `scripts/README_SCRIPTS.md` - Test documentation
- Railway logs - Production test results

### **Success Criteria**
- All API endpoints respond within 500ms
- S3 connectivity 99% uptime
- GPXZ API integration working
- Error handling covers all scenarios
- Cost controls functioning

## Troubleshooting Guide

### **Common Issues**
1. **GPXZ API 401 Unauthorized**
   - Check API key in environment
   - Verify key is not placeholder

2. **S3 403 Access Denied**
   - Validate AWS credentials
   - Check bucket permissions

3. **DEM Backend 404 Not Found**
   - Ensure service is running
   - Check port configuration

4. **Rate Limit Exceeded**
   - Wait for quota reset
   - Verify rate limiting logic

### **Debug Commands**
```bash
# Check environment configuration
python -c "from src.config import Settings; print(Settings().DEM_SOURCES)"

# Test GPXZ API directly
curl -H "X-API-Key: YOUR_KEY" "https://api.gpxz.io/v1/elevation/point?lat=-27.4698&lon=153.0251"

# Test S3 bucket access
aws s3 ls s3://road-engineering-elevation-data/

# Test DEM Backend health
curl http://localhost:8001/health
```

## Next Steps

1. **Run comprehensive tests** across all environments
2. **Set up monitoring** for production deployment
3. **Implement alerting** for service failures
4. **Create CI/CD pipeline** with automated testing
5. **Document performance baselines** for each service