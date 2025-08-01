# Australian S3 Sources - Validation Checkpoints

**Critical**: Ensure 1,151 Australian S3 campaigns continue working during NZ index implementation

## 🚨 Impact Analysis

### Current Australian S3 Architecture
- **Campaign Selector**: Uses `CampaignDatasetSelector` for 1,151 Australian campaigns
- **Index Source**: Loads from S3 via `S3IndexLoader` 
- **Performance**: 54,000x speedup for Brisbane, 672x for Sydney
- **Status**: ✅ Currently working (confirmed in logs)

### Potential Impact Areas
1. **S3IndexLoader Changes**: Modifying required_indexes array
2. **ServiceContainer Integration**: New dependency injection patterns
3. **EnhancedSourceSelector**: Changes to initialization and usage
4. **Environment Variables**: New S3_INDEX_KEYS configuration

## 🧪 Validation Test Suite

### Brisbane Test (Primary Australian Validation)
```bash
# Expected: Brisbane2009LGA S3 campaign, ~11.5m elevation
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}' | jq '.dem_source_used'
```
**Success Criteria**: `"dem_source_used": "Brisbane2009LGA"` (not gpxz_api)

### Sydney Test (Secondary Australian Validation)
```bash
# Expected: Sydney201304 S3 campaign, ~21.7m elevation
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -33.8688, "longitude": 151.2093}' | jq '.dem_source_used'
```
**Success Criteria**: `"dem_source_used": "Sydney201304"` (not gpxz_api)

### Sources Count Validation
```bash
# Expected: 1,153 total sources (1,151 AU + 2 API)
curl "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/sources" | jq '.total_sources'
```
**Success Criteria**: `1153` total sources maintained

## 📋 Modified Implementation Plan with Checkpoints

### Phase 1: Create UnifiedIndexLoader (with AU validation)

#### Checkpoint 1A: Before Changes
```bash
# Validate current Australian functionality
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}' | jq '.'
# Document current response for comparison
```

#### Step 1.1: Create UnifiedIndexLoader (Non-Breaking)
**Safe Approach**: Create new file without modifying existing S3IndexLoader yet
```python
# Create src/unified_index_loader.py as NEW file
# Keep existing src/s3_index_loader.py unchanged initially
```

#### Checkpoint 1B: Add to ServiceContainer (Optional Property)
```python
# In src/dependencies.py - ADD new property without breaking existing
class ServiceContainer:
    # ... existing code unchanged ...
    
    @property
    def unified_index_loader(self) -> Optional[UnifiedIndexLoader]:
        """Get UnifiedIndexLoader (NEW - for testing only)"""
        if not hasattr(self, '_unified_index_loader'):
            self._unified_index_loader = UnifiedIndexLoader()
        return self._unified_index_loader
```

#### Checkpoint 1C: Test Australian Sources Still Work
```bash
# Validate Australian sources unaffected by new ServiceContainer property
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}' | jq '.dem_source_used'
```
**STOP IF**: Australian sources stop working

### Phase 2: Upload NZ Index (Zero Impact on Australian)

#### Step 2.1: Upload NZ Index to S3
```bash
# This has ZERO impact on Australian sources - just adds new file
aws s3 cp config/nz_spatial_index.json s3://road-engineering-elevation-data/indexes/nz_spatial_index.json
```

#### Checkpoint 2A: Australian Sources Unaffected
```bash
# Validate S3 upload doesn't impact existing Australian functionality
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}' | jq '.dem_source_used'
```

### Phase 3: Gradual Migration (High Risk - Multiple Checkpoints)

#### Checkpoint 3A: Before EnhancedSourceSelector Changes
```bash
# Final validation before touching EnhancedSourceSelector
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}' | jq '.'
```

#### Step 3.1: Minimal EnhancedSourceSelector Changes
**Strategy**: Add NZ functionality without breaking Australian logic
```python
# In src/enhanced_source_selector.py
class EnhancedSourceSelector:
    def __init__(self, ..., unified_index_loader: Optional[UnifiedIndexLoader] = None):
        # Keep existing initialization unchanged
        self.spatial_index_loader = SpatialIndexLoader() if use_s3 else None  # KEEP
        
        # Add new unified loader as OPTIONAL
        self.unified_index_loader = unified_index_loader  # NEW, optional
        
    async def _try_nz_source(self, lat: float, lon: float) -> Optional[float]:
        # Use unified loader IF available, otherwise keep existing logic
        if self.unified_index_loader:
            return await self._try_nz_source_unified(lat, lon)  # NEW path
        else:
            return await self._try_nz_source_legacy(lat, lon)   # EXISTING path
```

#### Checkpoint 3B: Test Both Australian and NZ After Minimal Changes
```bash
# Test Australian (should still work with existing path)
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}' | jq '.dem_source_used'

# Test NZ (should now work with new path)
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -d '{"latitude": -36.8485, "longitude": 174.7633}' | jq '.dem_source_used'
```

#### Checkpoint 3C: Enable Unified Loader Injection
```python
# In src/dependencies.py - ONLY after validation above passes
@property
def elevation_service(self) -> UnifiedElevationService:
    if self._elevation_service is None:
        self._elevation_service = UnifiedElevationService(
            self.settings, 
            redis_manager=self.redis_manager,
            unified_index_loader=self.unified_index_loader  # ADD this injection
        )
```

#### Checkpoint 3D: Final Validation After Full Integration
```bash
# Test Australian sources (critical - must still work)
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}' | jq '.dem_source_used'

# Test NZ sources (should now work via unified loader)
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -d '{"latitude": -36.8485, "longitude": 174.7633}' | jq '.dem_source_used'

# Test sources count (should be 1,153)
curl "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/sources" | jq '.total_sources'
```

## 🚨 Rollback Strategy

### If Australian Sources Break at Any Checkpoint:

#### Immediate Rollback Commands
```bash
# Revert to previous git commit immediately
git log --oneline -5  # Find last working commit
git revert <commit-hash>  # Revert breaking change
git push  # Deploy rollback
```

#### Validation After Rollback
```bash
# Confirm Australian sources restored
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}' | jq '.dem_source_used'
```

## 🎯 Success Criteria Summary

### Must Continue Working (Non-Negotiable)
1. **Brisbane**: `"dem_source_used": "Brisbane2009LGA"`
2. **Sydney**: `"dem_source_used": "Sydney201304"`  
3. **Sources Count**: `1153` total sources
4. **Performance**: <200ms response times for Australian coordinates

### Should Start Working (New Functionality)
1. **Auckland**: `"dem_source_used"` should be NZ S3 source (not gpxz_api)
2. **Wellington**: `"dem_source_used"` should be NZ S3 source (not gpxz_api)

## 📊 Risk Assessment

### Low Risk Changes
- ✅ Creating new UnifiedIndexLoader file
- ✅ Uploading NZ index to S3
- ✅ Adding optional ServiceContainer properties

### Medium Risk Changes  
- ⚠️ Modifying EnhancedSourceSelector initialization
- ⚠️ Adding dependency injection to UnifiedElevationService

### High Risk Changes
- 🚨 Removing SpatialIndexLoader code
- 🚨 Changing S3IndexLoader required_indexes array
- 🚨 Modifying core elevation service dependencies

### Risk Mitigation
- **Incremental deployment** with validation checkpoints
- **Backward compatibility** during transition
- **Immediate rollback** capability at each checkpoint
- **Australian sources** tested before and after each change

---

**Strategy**: Additive changes first, then gradual migration with Australian validation at every step