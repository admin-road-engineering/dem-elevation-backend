# NZ Spatial Index - Strategic Architectural Fix Plan

**Date**: 2025-01-31  
**Gemini Review**: ✅ **Approved - Strategic data-driven approach**  
**Goal**: Implement unified, scalable index loading architecture

## 🎯 Strategic Approach (Gemini-Recommended)

### Problems Identified by Gemini Review
1. **Security Risk**: Debug endpoints need authentication/environment flags
2. **Architectural Inconsistency**: SpatialIndexLoader (filesystem) vs S3IndexLoader (S3)
3. **Scalability Issue**: Hardcoded index lists prevent easy expansion
4. **Code Duplication**: Two separate loaders for same conceptual purpose

### Strategic Solution
**Unified Data-Driven IndexLoader** that:
- Uses `S3_INDEX_KEYS` environment variable for dynamic configuration
- Supports both production (S3) and development (filesystem) modes
- Eliminates hardcoded index lists
- Managed by ServiceContainer for proper dependency injection

## 📋 Revised Implementation Plan

### Phase 1: Create Unified IndexLoader (30-45 minutes)

#### Step 1.1: Refactor S3IndexLoader to UnifiedIndexLoader
```python
# In src/unified_index_loader.py (new file)
class UnifiedIndexLoader:
    """Unified index loader supporting both S3 (production) and filesystem (development)"""
    
    def __init__(self, bucket_name: str = None, environment: str = None):
        self.bucket_name = bucket_name or os.getenv("S3_INDEX_BUCKET", "road-engineering-elevation-data")
        self.environment = environment or os.getenv("APP_ENV", "production")
        
        # Parse index keys from environment variable (data-driven configuration)
        index_keys_str = os.getenv("S3_INDEX_KEYS", 
            "indexes/campaign_index.json,indexes/phase3_brisbane_tiled_index.json,indexes/spatial_index.json,indexes/nz_spatial_index.json")
        self.index_keys = [key.strip() for key in index_keys_str.split(",")]
        
        # Local config directory for development mode
        self.config_dir = Path(__file__).parent.parent / "config"
        
    def _get_local_path(self, s3_key: str) -> Path:
        """Map S3 key to local filesystem path"""
        # Use basename of S3 key (e.g., nz_spatial_index.json from indexes/nz_spatial_index.json)
        filename = Path(s3_key).name
        return self.config_dir / filename
    
    async def load_index(self, index_name: str) -> Dict[str, Any]:
        """Load index from S3 (production) or filesystem (development)"""
        if self.environment == "development":
            return await self._load_from_filesystem(index_name)
        else:
            return await self._load_from_s3(index_name)
```

#### Step 1.2: Add to ServiceContainer
```python
# In src/dependencies.py
class ServiceContainer:
    def __init__(self, settings: Settings):
        # ... existing code ...
        self._index_loader: Optional[UnifiedIndexLoader] = None
    
    @property
    def index_loader(self) -> UnifiedIndexLoader:
        """Get or create the UnifiedIndexLoader instance."""
        if self._index_loader is None:
            self._index_loader = UnifiedIndexLoader()
            logger.info("UnifiedIndexLoader created with data-driven configuration")
        return self._index_loader
```

#### Step 1.3: Add Secure Debug Endpoint
```python
# In src/main.py
@app.get("/debug/index-status")
async def debug_index_status(request: Request):
    """Secure debug endpoint for index status"""
    # Security: Only enable in non-production or with auth
    if os.getenv("APP_ENV") == "production" and not os.getenv("ENABLE_DEBUG_ENDPOINTS"):
        raise HTTPException(status_code=404, detail="Not found")
    
    container = get_service_container()
    return await container.index_loader.get_index_status()
```

### Phase 2: Upload NZ Index to S3 (15-20 minutes)

#### Step 2.1: Upload Missing Index to S3
```bash
# Upload NZ spatial index to S3 bucket
aws s3 cp config/nz_spatial_index.json s3://road-engineering-elevation-data/indexes/nz_spatial_index.json

# Verify upload
aws s3 ls s3://road-engineering-elevation-data/indexes/ | grep nz
```

#### Step 2.2: Set Environment Variables
```bash
# Set data-driven index configuration in Railway
railway variables --set "S3_INDEX_KEYS=indexes/campaign_index.json,indexes/phase3_brisbane_tiled_index.json,indexes/spatial_index.json,indexes/nz_spatial_index.json"

# Enable development mode for local testing
railway variables --set "APP_ENV=production"  # Keep as production for Railway
```

### Phase 3: Replace SpatialIndexLoader Usage (20-30 minutes)

#### Step 3.1: Update EnhancedSourceSelector
```python
# In src/enhanced_source_selector.py
class EnhancedSourceSelector:
    def __init__(self, config: Dict, index_loader: UnifiedIndexLoader, ...):
        # Replace spatial_index_loader with unified index_loader
        self.index_loader = index_loader  # Injected via ServiceContainer
        
    async def _try_nz_source(self, lat: float, lon: float) -> Optional[float]:
        """Try NZ source using unified index loader"""
        try:
            # Load NZ index via unified loader
            nz_index = await self.index_loader.load_index('nz_spatial')
            
            # Find matching file using existing logic
            nz_file = self._find_nz_file_in_index(nz_index, lat, lon)
            if nz_file:
                logger.info(f"Found NZ DEM file via unified loader: {nz_file}")
                elevation = await self._extract_elevation_from_s3_file(nz_file, lat, lon, use_credentials=False)
                return elevation
        except Exception as e:
            logger.error(f"NZ source error via unified loader: {e}", exc_info=True)
            return None
```

#### Step 3.2: Update Dependency Injection
```python
# In src/unified_elevation_service.py
class UnifiedElevationService:
    def __init__(self, settings: Settings, redis_manager: RedisStateManager, index_loader: UnifiedIndexLoader):
        # Inject unified index loader
        self.enhanced_source_selector = EnhancedSourceSelector(
            config=settings.DEM_SOURCES,
            index_loader=index_loader,  # Use injected unified loader
            use_s3=settings.USE_S3_SOURCES,
            # ... other parameters
        )
```

### Phase 4: Remove Legacy Code (10-15 minutes)

#### Step 4.1: Delete SpatialIndexLoader
```bash
# Remove old SpatialIndexLoader class from enhanced_source_selector.py
# Lines 22-160 can be deleted after usage is replaced
```

#### Step 4.2: Clean Up Imports
```python
# Remove unused imports related to old spatial index loading
# Update imports to use UnifiedIndexLoader
```

### Phase 5: Test and Deploy (15-20 minutes)

#### Step 5.1: Local Testing with Development Mode
```bash
# Test with development mode (uses local files)
export APP_ENV=development
export S3_INDEX_KEYS="indexes/campaign_index.json,indexes/spatial_index.json,indexes/nz_spatial_index.json"

python scripts/switch_environment.py production
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -36.8485, "longitude": 174.7633}'
```

#### Step 5.2: Deploy to Railway
```bash
# Commit unified architecture changes
git add src/unified_index_loader.py src/dependencies.py src/enhanced_source_selector.py
git commit -m "feat: Implement unified data-driven index loading architecture

- Create UnifiedIndexLoader supporting S3 (production) and filesystem (development)
- Add S3_INDEX_KEYS environment variable for dynamic configuration
- Integrate with ServiceContainer for proper dependency injection
- Add secure debug endpoints with environment-based access control
- Replace SpatialIndexLoader with unified approach
- Enable NZ spatial index loading via data-driven configuration

🤖 Generated with Claude Code

Co-Authored-By: Claude <noreply@anthropic.com>"

git push
```

#### Step 5.3: Verify Production Deployment
```bash
# Wait for Railway deployment
sleep 60

# Test Auckland coordinates
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -36.8485, "longitude": 174.7633}'

# Expected: dem_source_used should be NZ S3 source
```

## 🎯 Success Metrics

### Immediate Success
1. **Data-Driven Configuration**: Adding new indexes only requires environment variable update
2. **NZ S3 Usage**: Auckland coordinates use NZ S3 source instead of GPXZ API
3. **Unified Architecture**: Single IndexLoader for both development and production
4. **Secure Debug**: Debug endpoints protected by environment flags

### Long-Term Benefits
1. **Scalability**: New countries/indexes can be added operationally
2. **Maintainability**: No hardcoded index lists in code
3. **Testability**: Proper dependency injection via ServiceContainer
4. **Consistency**: Same loading mechanism for all environments

## 🚨 Security Implementation

### Debug Endpoint Protection
```python
# Only enable debug endpoints in development or with explicit flag
if os.getenv("APP_ENV") == "production" and not os.getenv("ENABLE_DEBUG_ENDPOINTS"):
    raise HTTPException(status_code=404, detail="Not found")
```

### Environment Variables
```bash
# Production (Railway)
APP_ENV=production
ENABLE_DEBUG_ENDPOINTS=false  # Never set to true in production

# Development (Local)
APP_ENV=development
ENABLE_DEBUG_ENDPOINTS=true
```

## 📊 Architecture Comparison

### Before (Problematic)
- **SpatialIndexLoader**: Hardcoded local file loading
- **S3IndexLoader**: Hardcoded S3 key list
- **Inconsistent**: Different loaders for same purpose
- **Inflexible**: New indexes require code changes

### After (Strategic)
- **UnifiedIndexLoader**: Environment-driven configuration
- **Data-Driven**: `S3_INDEX_KEYS` environment variable
- **Consistent**: Single loader for all environments
- **Scalable**: New indexes are operational changes

## 🛠️ Implementation Checklist

- [ ] **Phase 1**: Create UnifiedIndexLoader with data-driven configuration
- [ ] **Phase 2**: Upload NZ index to S3 and set environment variables
- [ ] **Phase 3**: Replace SpatialIndexLoader usage throughout codebase
- [ ] **Phase 4**: Remove legacy SpatialIndexLoader code
- [ ] **Phase 5**: Test, deploy, and verify production functionality

---

**Timeline**: 2-3 hours total  
**Approach**: Strategic architectural improvement (not tactical patch)  
**Gemini Review**: ✅ **Approved for architectural consistency and scalability**  
**Security**: ✅ **Debug endpoints protected, no security vulnerabilities**