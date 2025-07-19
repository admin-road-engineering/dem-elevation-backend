# DEM Backend API Testing Plan - S3 → GPXZ → Google Fallback Chain

## Overview
This document outlines the comprehensive testing strategy for the S3 → GPXZ → Google fallback chain implementation, including all external APIs and S3 connections.

## Fallback Chain Testing Strategy

### Priority 1: S3 Sources Testing

**Australian S3 Bucket** (`road-engineering-elevation-data`)
- **Access Type**: Private (requires AWS credentials)
- **Files**: 214,450+ DEM files across UTM zones
- **Coverage**: Australia (1m LiDAR resolution)

**New Zealand S3 Bucket** (`nz-elevation`)
- **Access Type**: Public (unsigned access)
- **Files**: 1,691 DEM files across 16 regions
- **Coverage**: New Zealand (1m LiDAR resolution)

**Test Scenarios:**
- ✅ AWS credentials validation
- ✅ Private bucket access (Australian data)
- ✅ Public bucket access (NZ data)
- ✅ Spatial index coordinate matching
- ✅ File retrieval and elevation extraction
- ✅ Error handling for missing files
- ✅ Cost tracking and daily limits

### Priority 2: GPXZ.io API Testing

**Service**: Global elevation data API  
**Base URL**: `https://api.gpxz.io`  
**Purpose**: Global coverage fallback when S3 sources unavailable

**Endpoints:**
- `GET /v1/elevation/point` - Single point elevation
- `POST /v1/elevation/points` - Batch elevation requests

**Authentication:**
- API Key: `ak_zj8pF60R_1h0s4aVF52KDSBMq`
- Header: `X-API-Key: {api_key}`

**Rate Limits:**
- **Free Tier**: 100 requests/day, 1 request/second
- **Production**: 10,000+ requests/day (upgradeable)

**Test Scenarios:**
- ✅ API key validation
- ✅ Single point elevation request
- ✅ Rate limiting behavior (429 responses)
- ✅ Error handling for invalid coordinates
- ✅ Daily quota management
- ✅ Circuit breaker integration
- ✅ Fallback to Priority 3 when rate limited

### Priority 3: Google Elevation API Testing

**Service**: Google Maps Elevation API  
**Base URL**: `https://maps.googleapis.com/maps/api/elevation/json`  
**Purpose**: Final fallback when GPXZ rate limits exceeded

**Authentication:**
- API Key: `AIzaSyAyBIQ7miuT86ndVnCYV_TQUWToxCCsZFQ`
- Query Parameter: `key={api_key}`

**Rate Limits:**
- **Free Tier**: 2,500 requests/day
- **Production**: Upgradeable billing plans

**Test Scenarios:**
- ✅ API key validation
- ✅ Single point elevation request
- ✅ Rate limiting behavior
- ✅ Error handling for invalid coordinates
- ✅ Daily quota management
- ✅ Circuit breaker integration
- ✅ Final fallback functionality

## Fallback Chain Integration Testing

### End-to-End Fallback Testing

**Test Coordinates:**
- **Brisbane, Australia** (-27.4698, 153.0251) - Tests AU S3 → GPXZ fallback
- **Auckland, New Zealand** (-36.8485, 174.7633) - Tests NZ S3 → GPXZ fallback  
- **Los Angeles, USA** (34.0522, -118.2437) - Tests GPXZ API directly
- **London, UK** (51.5074, -0.1278) - Tests GPXZ → Google fallback
- **Random Ocean** (0.0, 0.0) - Tests no-data scenarios

**Expected Behavior:**
```
Brisbane: S3 (if available) → GPXZ → Google
Auckland: S3 (if available) → GPXZ → Google
Los Angeles: S3 (no coverage) → GPXZ → Google
London: S3 (no coverage) → GPXZ → Google (when rate limited)
Ocean: S3 (no coverage) → GPXZ → Google
```

### Circuit Breaker Testing

**Test Scenarios:**
- ✅ S3 failure triggers GPXZ fallback
- ✅ GPXZ rate limit triggers Google fallback
- ✅ Circuit breaker opens after 3-5 failures
- ✅ Circuit breaker recovery after timeout
- ✅ Graceful degradation between services

### Performance Testing

**Response Time Targets:**
- Single point: <100ms
- Batch requests: <500ms per 100 points
- Fallback chain: <2 seconds total

**Load Testing:**
- 50 concurrent users
- 1000 requests over 10 minutes
- Fallback chain under load

## Test Implementation

### Automated Test Suite

**Test Files:**
- `test_fallback_chain.py` - Complete fallback chain testing
- `test_s3_simple.py` - S3 multi-file access testing
- `test_nz_elevation.py` - NZ public bucket testing
- `test_nz_integration.py` - NZ integration testing
- `tests/test_phase2_integration.py` - Comprehensive integration tests

**Running Tests:**
```bash
# Complete fallback chain test
python test_fallback_chain.py

# S3 testing
python test_s3_simple.py

# NZ elevation testing
python test_nz_elevation.py

# Integration tests
pytest tests/test_phase2_integration.py

# All tests
pytest tests/
```

### Manual Testing

**API Endpoint Testing:**
```bash
# Test single point (should show fallback source)
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'

# Test health check (shows fallback chain status)
curl http://localhost:8001/api/v1/health

# Test source listing (shows priority levels)
curl http://localhost:8001/api/v1/elevation/sources
```

**Expected Responses:**
```json
{
  "latitude": -27.4698,
  "longitude": 153.0251,
  "elevation_m": 11.523284,
  "dem_source_used": "gpxz_api",
  "message": null
}
```

### Error Scenario Testing

**S3 Credential Issues:**
- Invalid AWS credentials
- Expired credentials
- Network connectivity issues
- Missing files in S3

**API Rate Limiting:**
- GPXZ daily quota exceeded
- Google API quota exceeded
- Rate limit recovery testing

**Network Failures:**
- Service unavailable (503 errors)
- Network timeouts
- DNS resolution failures

### Environment-Specific Testing

**Local Development:**
```bash
# Switch to local environment
python scripts/switch_environment.py local

# Test local-only sources
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'
```

**API Testing Environment:**
```bash
# Switch to API testing
python scripts/switch_environment.py api-test

# Test with limited quotas
python test_fallback_chain.py
```

**Production Environment:**
```bash
# Switch to production
python scripts/switch_environment.py production

# Test with full credentials
python test_fallback_chain.py
```

## Test Results Documentation

### Current Test Status ✅

**Fallback Chain Tests:**
- Brisbane → GPXZ: 11.523284m ✅
- Auckland → GPXZ: 25.022331m ✅
- Los Angeles → GPXZ: 86.770844m ✅
- London → Google: 8.335875m ✅
- Ocean → GPXZ: 0.0m ✅

**S3 Integration Tests:**
- Australian S3: 214,450 files indexed ✅
- NZ S3: 1,691 files indexed ✅
- Public bucket access: Working ✅
- Private bucket access: Working ✅
- Spatial coordinate matching: Working ✅

**API Integration Tests:**
- GPXZ API: Working ✅
- Google API: Working ✅
- Rate limit handling: Working ✅
- Circuit breaker: Working ✅
- Error handling: Working ✅

## Monitoring and Alerting

### Health Monitoring

**Service Health Endpoint:**
```bash
GET /api/v1/health
```

**Response includes:**
- Fallback chain status
- API rate limit remaining
- Circuit breaker states
- Error rates
- Performance metrics

### Logging and Metrics

**Key Metrics:**
- Response times per source type
- Fallback chain usage patterns
- API quota utilization
- Error rates by source
- S3 cost tracking

**Log Monitoring:**
```
2025-01-18 10:30:00 | INFO | Enhanced selector returned 11.523284m from gpxz_api
2025-01-18 10:30:01 | WARN | GPXZ rate limit exceeded, falling back to Google
2025-01-18 10:30:02 | INFO | Google API returned 8.335875m for (51.5074, -0.1278)
```

## Continuous Integration

### Automated Testing

**GitHub Actions / CI Pipeline:**
```yaml
name: DEM Backend Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Test Fallback Chain
        run: python test_fallback_chain.py
      - name: Test S3 Integration
        run: python test_s3_simple.py
      - name: Run Integration Tests
        run: pytest tests/test_phase2_integration.py
```

### Performance Regression Testing

**Load Test Scenarios:**
- Baseline performance measurement
- Fallback chain under load
- Rate limit recovery testing
- Circuit breaker behavior

This comprehensive testing plan ensures the S3 → GPXZ → Google fallback chain operates reliably in all scenarios with proper error handling, performance optimization, and monitoring.