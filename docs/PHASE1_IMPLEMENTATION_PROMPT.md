# Phase 1 Implementation Prompt - UnifiedIndexLoader Creation

**Session Context**: Implementing Gemini-reviewed architectural fix for NZ spatial index loading

## 🎯 Current Status

### ✅ Completed
- **Baseline Validation**: Australian S3 sources working perfectly
  - Brisbane: `"dem_source_used": "Brisbane2009LGA"`, elevation: 11.523m 
  - Sydney: `"dem_source_used": "Sydney201304"`, elevation: 21.710m
  - Total sources: 1,153 (1,151 AU campaigns + 2 API)
- **URL Updated**: All docs use `https://re-dem-elevation-backend.up.railway.app`
- **Geographic Routing**: NZ coordinates detected correctly, fallback to GPXZ working
- **Redis Connected**: Using existing Railway Redis addon

### 🔄 Current Issue
- **NZ Spatial Index Loading**: `config/nz_spatial_index.json` not loading in Railway
- **Architectural Inconsistency**: SpatialIndexLoader (filesystem) vs S3IndexLoader (S3)
- **Result**: Auckland coordinates use GPXZ API instead of NZ S3 sources

## 📋 Phase 1 Task: Create UnifiedIndexLoader (Safe Implementation)

### **CRITICAL REQUIREMENT: Do NOT break Australian S3 sources**
- Australian campaigns provide 54,000x speedup (Brisbane) and 672x speedup (Sydney)
- Must maintain all 1,153 source count throughout implementation

### **Implementation Strategy: Additive Only**
1. **Create NEW file** `src/unified_index_loader.py` without touching existing code
2. **Add OPTIONAL property** to ServiceContainer (backward compatible)
3. **Validate Australian sources** continue working at each step

## 🔧 Technical Requirements

### UnifiedIndexLoader Specification
```python
# Create: src/unified_index_loader.py
class UnifiedIndexLoader:
    """
    Unified index loader supporting both S3 (production) and filesystem (development)
    
    Features:
    - Data-driven configuration via S3_INDEX_KEYS environment variable
    - Environment detection (APP_ENV=development uses local files)
    - Proper error handling and logging
    - Compatible with existing ServiceContainer pattern
    """
    
    def __init__(self, bucket_name: str = None, environment: str = None):
        # Parse S3_INDEX_KEYS for dynamic configuration
        # Support both S3 and filesystem loading
        
    async def load_index(self, index_name: str) -> Dict[str, Any]:
        # Load from S3 (production) or filesystem (development)
        
    def _get_local_path(self, s3_key: str) -> Path:
        # Map S3 key to local config/filename.json
```

### ServiceContainer Integration
```python
# In src/dependencies.py - ADD new property (don't modify existing)
@property
def unified_index_loader(self) -> Optional[UnifiedIndexLoader]:
    """Get UnifiedIndexLoader (NEW - for testing only)"""
    if not hasattr(self, '_unified_index_loader'):
        self._unified_index_loader = UnifiedIndexLoader()
        logger.info("UnifiedIndexLoader created with data-driven configuration")
    return self._unified_index_loader
```

## 🧪 Validation Requirements

### Checkpoint 1B: After UnifiedIndexLoader Creation
```bash
# MUST PASS: Australian sources still working
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}' | jq '.dem_source_used'
# Expected: "Brisbane2009LGA"

curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -33.8688, "longitude": 151.2093}' | jq '.dem_source_used'
# Expected: "Sydney201304"

# Source count maintained
curl "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/sources" | jq '.total_sources'
# Expected: 1153
```

### Checkpoint 1C: After ServiceContainer Update
```bash
# Same validation tests - Australian sources MUST continue working
# If ANY test fails, immediately rollback changes
```

## 🚨 Safety Protocols

### Stop Conditions
**STOP IMPLEMENTATION IF**:
- Australian coordinates return `"gpxz_api"` instead of campaign names
- Total sources drops below 1,153
- Response times exceed 200ms for Australian coordinates
- Any errors in health endpoint

### Rollback Strategy
```bash
# Immediate rollback if Australian sources break
git status
git diff  # Review changes
git checkout -- src/dependencies.py  # Revert ServiceContainer changes
git rm src/unified_index_loader.py   # Remove new file
git push  # Deploy rollback
```

## 📁 File Structure Context

### Current Architecture
```
src/
├── enhanced_source_selector.py      # Contains SpatialIndexLoader (filesystem)
├── s3_index_loader.py              # Loads from S3, hardcoded index list
├── dependencies.py                 # ServiceContainer for DI
└── main.py                        # FastAPI app initialization
```

### After Phase 1 (Additive)
```
src/
├── enhanced_source_selector.py      # UNCHANGED
├── s3_index_loader.py              # UNCHANGED
├── unified_index_loader.py         # NEW - data-driven loader
├── dependencies.py                 # ADD optional unified_index_loader property
└── main.py                        # UNCHANGED
```

## 🎯 Success Criteria

### Phase 1 Complete When:
1. ✅ **UnifiedIndexLoader created** with data-driven S3_INDEX_KEYS support
2. ✅ **ServiceContainer integration** as optional property
3. ✅ **Australian sources validation** - all tests pass
4. ✅ **No breaking changes** - existing code unchanged
5. ✅ **Ready for Phase 2** - NZ index upload to S3

### Next Phase Preview
**Phase 2**: Upload `config/nz_spatial_index.json` to S3 bucket (zero impact on Australian sources)

## 🔍 Key Files to Examine

### Review Before Implementation
```bash
# Understand current S3IndexLoader
cat src/s3_index_loader.py | head -50

# Understand ServiceContainer pattern  
cat src/dependencies.py | grep -A 10 "@property"

# Understand current Australian campaign loading
curl "https://re-dem-elevation-backend.up.railway.app/api/v1/health" | jq '.s3_indexes'
```

## 🚀 Implementation Checklist

- [ ] Create `src/unified_index_loader.py` with data-driven configuration
- [ ] Add environment detection (S3 for production, filesystem for development)
- [ ] Implement error handling with proper logging
- [ ] Add optional `unified_index_loader` property to ServiceContainer
- [ ] Test Australian sources after each change
- [ ] Commit changes incrementally with validation
- [ ] Document any issues or unexpected behavior

---

**CRITICAL**: Australian S3 sources (Brisbane2009LGA, Sydney201304) must continue working throughout Phase 1. If they break at any point, immediately rollback and reassess the approach.

**Validation URL**: `https://re-dem-elevation-backend.up.railway.app`  
**Expected Brisbane**: `"dem_source_used": "Brisbane2009LGA"`  
**Expected Sydney**: `"dem_source_used": "Sydney201304"`  
**Expected Count**: 1,153 total sources