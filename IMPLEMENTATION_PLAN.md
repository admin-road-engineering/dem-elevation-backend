# DEM Backend Recovery Implementation Plan

## Executive Summary
Both Brisbane (AU) and Auckland (NZ) coordinates worked individually at different points but are now broken due to over-engineering during optimization attempts. This plan implements Gemini's validated recovery strategy focusing on minimal changes to restore basic functionality.

## Core Principle
**"Make it work, then make it better"** - NOT the other way around

## Critical Context
- **Brisbane**: Previously worked (10.872m elevation) → Now broken after complex session management changes
- **Auckland**: Previously worked (~25m elevation) → Now broken after bounds/CRS logic changes
- **Service Status**: Healthy with 1,582 collections loaded, but both primary use cases broken
- **Over-Engineering Crisis**: Multiple "optimization" attempts created more problems than solutions

## Implementation Steps (Gemini-Validated)

### Phase 1: Test-Driven Recovery Foundation

#### Step 2.5: Build Core Integration Test (FIRST PRIORITY)
**Rationale**: Gemini's critical addition - test-driven recovery prevents further regression

**Implementation**:
```python
# tests/integration/test_elevation_recovery.py
import pytest
import httpx

class TestElevationRecovery:
    BASE_URL = "https://re-dem-elevation-backend.up.railway.app"
    
    def test_brisbane_elevation_recovery(self):
        """Test Brisbane AU coordinate returns expected elevation"""
        response = httpx.get(f"{self.BASE_URL}/api/v1/elevation", 
                           params={"lat": -27.4698, "lon": 153.0251})
        assert response.status_code == 200
        data = response.json()
        assert data["elevation_m"] is not None
        assert 10.0 <= data["elevation_m"] <= 12.0  # Expected ~10.872m
        assert data["processing_time_ms"] < 2000   # <2s target
    
    def test_auckland_elevation_recovery(self):
        """Test Auckland NZ coordinate returns expected elevation"""  
        response = httpx.get(f"{self.BASE_URL}/api/v1/elevation",
                           params={"lat": -36.8485, "lon": 174.7633})
        assert response.status_code == 200
        data = response.json()
        assert data["elevation_m"] is not None
        assert 20.0 <= data["elevation_m"] <= 30.0  # Expected ~25m
        assert data["processing_time_ms"] < 2000   # <2s target
```

**Success Criteria**: These tests will initially FAIL. Recovery is complete when they PASS.

### Phase 2: Minimal Fixes Only

#### Step 1: Fix Brisbane GDAL/Rasterio Access
**Current Issue**: GDAL opens files successfully but `_gdal_array` import fails → rasterio fallback fails with boto3 session error

**Minimal Fix Strategy**:
1. **Option A**: Fix GDAL `_gdal_array` import issue directly
2. **Option B**: Simplify rasterio to use basic environment variables (revert complex session management)

**Implementation**: 
- Remove complex boto3 session logic
- Use simple environment variable approach that worked before
- Focus on AU private bucket credentials only initially

#### Step 2: Fix Auckland NZ File Discovery  
**Current Issue**: Collections found (73 eligible) but 0 files discovered in each collection

**Root Cause Investigation**:
- Verify `nz_spatial_index.json` bounds CRS (likely WGS84 vs UTM mismatch like AU had)
- Check file discovery logic hasn't been broken by bounds checking changes

**Minimal Fix Strategy**:
- Verify NZ collection bounds are in correct coordinate system
- Ensure intersection logic works correctly for WGS84 input coordinates

### Phase 3: Validation & Stop

#### Step 3: Test and Stop
**Definition of Success**: Integration test suite passes consistently
- Brisbane returns ~10.872m elevation
- Auckland returns ~25m elevation  
- Both respond in <2s
- No additional "optimizations" until this baseline works

## What NOT to Do (Anti-Patterns to Avoid)

### Avoid During Recovery
- ❌ Complex bucket detection strategies
- ❌ Singleton session patterns (until basic functionality works)
- ❌ Multiple context managers
- ❌ Sophisticated error handling that masks root issues
- ❌ "Architectural improvements" before basic functionality

### Focus on Basics Only
- ✅ Simple environment variable approach
- ✅ Basic rasterio/GDAL file access  
- ✅ Minimal bounds checking
- ✅ Clear error messages
- ✅ Working integration tests

## Post-Recovery Phase (Only After Both Coordinates Work)

### P0 Critical (After Recovery)
1. **Security**: Move from static AWS keys to IAM roles  
2. **Performance**: Switch from 382.7MB JSON to MessagePack for index format
3. **Testing**: Expand integration test suite to prevent future regression

### P1 Architecture (After P0)
1. **Two-Tier R-Tree**: WGS84 coarse filter → UTM precise check
2. **Nested Configuration**: Pydantic structured settings
3. **Documentation Cleanup**: Break up monolithic CLAUDE.md

### P2 Refinement (After P1)
1. **Unified CLI**: Replace .bat scripts with `python -m dem_backend.cli`
2. **Index Optimization**: Consider FlatBuffers for advanced performance
3. **Advanced Error Handling**: Once basic functionality is rock solid

## Success Metrics

### Recovery Complete When:
1. **Integration Tests Pass**: Both Brisbane and Auckland assertions pass
2. **Consistent Performance**: Multiple test runs succeed without flakiness
3. **Clean Logs**: No critical errors during normal operation
4. **Response Times**: Both coordinates respond in <2s

### Long-Term Success (Post-Recovery):
1. **Sub-100ms Performance**: Original performance targets restored
2. **Zero Downtime**: Service reliability with proper error handling
3. **Security Hardened**: No static credentials in production
4. **Developer Experience**: Clear documentation and onboarding

## Key Lessons Integrated

1. **Architecture Excellence**: Resilience and working functionality, not just sophisticated patterns
2. **Test-Driven Development**: Integration tests prevent regression and validate success
3. **Minimal Viable Recovery**: Simplest approach that works, then improve incrementally
4. **Documentation Discipline**: Technical success measured by working code, not AI approval

---

*This plan prioritizes working functionality over architectural sophistication, following the critical lesson that exceptional software works reliably first, then optimizes second.*