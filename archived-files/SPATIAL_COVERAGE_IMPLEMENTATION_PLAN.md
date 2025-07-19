# Spatial Coverage-Based DEM Source Selection Implementation Plan

## Executive Summary

This plan outlines the implementation of an automated, spatial coverage-based source selection system for the DEM Backend service. The system will automatically select the highest resolution elevation data source based on geographic location while maintaining full backward compatibility with existing API endpoints.

## Project Goals

1. **Automated Source Selection**: Select the best elevation source based on coordinates and resolution
2. **Coverage Visualization**: Provide coverage area data for frontend map visualization
3. **Backward Compatibility**: Maintain existing API endpoints without breaking changes
4. **Cost Optimization**: Prioritize S3 sources over API sources when available
5. **Transparency**: Provide clear information about data sources and selection reasoning

## Architecture Overview

### Current Architecture (Problems)
- Configuration-based source selection via `.env` file
- GPXZ API integration not working (treats `api://gpxz` as file path)
- Poor source selection logic (always defaults to one source)
- No geographic awareness for source selection

### New Architecture (Solutions)
- Spatial database of elevation sources with coverage bounds
- Automated selection based on resolution and priority
- Proper API/S3 source handling
- Coverage visualization endpoints for frontend
- Maintained backward compatibility

## Implementation Phases

### Phase 1: Core Spatial Database (Week 1)

#### 1.1 Create Coverage Database
**File**: `src/coverage_database.py`
```python
ELEVATION_SOURCES = [
    {
        "id": "act_elvis",
        "name": "Australian Capital Territory LiDAR",
        "source_type": "s3",
        "path": "s3://road-engineering-elevation-data/act-elvis/",
        "crs": "EPSG:3577",
        "resolution_m": 1,
        "priority": 1,
        "bounds": {"min_lat": -35.9, "max_lat": -35.1, "min_lon": 148.7, "max_lon": 149.4},
        "enabled": True
    },
    # ... additional sources
]
```

#### 1.2 Define Coverage Areas
- **Australia S3 Sources** (3 regions): ACT, NSW, VIC
- **New Zealand S3 Sources** (5 regions): Auckland, Wellington, Canterbury, Otago, National
- **GPXZ Enhanced Coverage**: USA (10m), Europe (25m)
- **GPXZ Global Coverage**: Worldwide (30m)

#### 1.3 Source Attributes
- `id`: Unique identifier
- `source_type`: "s3" or "api"
- `resolution_m`: Resolution in meters
- `priority`: 1 (highest) to 3 (lowest)
- `bounds`: Geographic coverage area
- `crs`: Coordinate reference system
- `cost_per_query`: Estimated cost
- `accuracy`: Expected accuracy
- `enabled`: Active/inactive flag

### Phase 2: Spatial Selection Logic (Week 1-2)

#### 2.1 Create Spatial Selector
**File**: `src/spatial_selector.py`
```python
class AutomatedSourceSelector:
    def __init__(self, sources_db):
        self.sources = sources_db
        
    def select_best_source(self, lat: float, lon: float):
        # Filter covering sources
        # Sort by priority and resolution
        # Return best match
        
    def point_in_bounds(self, lat: float, lon: float, bounds: dict):
        # Check if point is within bounds
        
    def get_coverage_summary(self, lat: float, lon: float):
        # Return all available sources for a point
```

#### 2.2 Integration Points
- Replace `EnhancedSourceSelector` with `AutomatedSourceSelector`
- Update `DEMService` to use new selector
- Maintain existing API signatures

### Phase 3: Backend API Updates (Week 2)

#### 3.1 Update Existing Endpoints
**Maintain compatibility while enhancing responses**

```python
@router.post("/elevation/point")
async def get_elevation_point(request: PointRequest):
    # Use spatial selector
    # Maintain response format
    # Add optional enhanced fields
```

#### 3.2 New Management Endpoints
```python
GET  /api/v1/elevation/sources/database    # Complete sources table
POST /api/v1/elevation/sources/select      # Source selection details
GET  /api/v1/elevation/coverage-areas      # Coverage visualization data
```

#### 3.3 Enhanced Response Format
```json
{
  "elevation_m": 45.2,
  "source": "nsw_elvis",
  "resolution_m": 1,              // New optional field
  "data_type": "LiDAR",           // New optional field
  "accuracy": "±0.1m",            // New optional field
  "coordinates": {...},           // Existing field
  "metadata": {...}               // Existing field
}
```

### Phase 4: GPXZ API Integration Fix (Week 2-3)

#### 4.1 Implement GPXZ Client
**File**: `src/gpxz_client.py` (update existing)
```python
class GPXZClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.gpxz.io/v1"
        
    async def get_elevation(self, lat: float, lon: float):
        # Proper API call implementation
        # Handle rate limiting
        # Return elevation value
```

#### 4.2 Source Handler Factory
```python
class SourceHandlerFactory:
    @staticmethod
    def get_handler(source_type: str):
        if source_type == "s3":
            return S3SourceHandler()
        elif source_type == "api":
            return GPXZAPIHandler()
        else:
            raise ValueError(f"Unknown source type: {source_type}")
```

### Phase 5: Frontend Integration Support (Week 3)

#### 5.1 Coverage Areas Endpoint
```python
@router.get("/coverage-areas")
async def get_coverage_areas():
    return {
        "high_resolution_zones": [...],    # 1m LiDAR
        "medium_resolution_zones": [...],  # 10-25m
        "global_fallback": {...}           # 30m SRTM
    }
```

#### 5.2 Frontend Integration Guide
- Map overlay implementation examples
- Coverage visualization code snippets
- Real-time resolution indicators
- Source selection tooltips

### Phase 6: Testing & Validation (Week 3-4)

#### 6.1 Unit Tests
- `test_spatial_selector.py`: Boundary conditions, priority selection
- `test_coverage_database.py`: Data integrity, bounds validation
- `test_gpxz_integration.py`: API client functionality

#### 6.2 Integration Tests
- End-to-end elevation queries
- Source selection verification
- Performance benchmarks
- Cost tracking validation

#### 6.3 Load Testing
- Concurrent request handling
- Cache effectiveness
- S3 vs API performance comparison

## Technical Specifications

### Source Priority Rules
1. **Priority 1**: High-resolution local S3 sources (1m)
2. **Priority 2**: Enhanced GPXZ coverage (10-25m)
3. **Priority 3**: Global GPXZ fallback (30m)

### Selection Algorithm
```
1. Find all sources covering the requested point
2. Filter by enabled status
3. Sort by (priority ASC, resolution_m ASC)
4. Select first result
5. Fall back to error if no coverage
```

### Performance Considerations
- Cache source boundaries in memory
- Use spatial indexing for large datasets
- Implement connection pooling for API calls
- Batch requests when possible

## Migration Strategy

### Step 1: Deploy with Feature Flag
```python
USE_SPATIAL_SELECTION = os.getenv("USE_SPATIAL_SELECTION", "false") == "true"
```

### Step 2: Gradual Rollout
1. Deploy code with feature disabled
2. Test with subset of requests
3. Monitor performance and accuracy
4. Enable for all requests
5. Remove old configuration system

### Step 3: Deprecation Timeline
- Week 1-2: Deploy new system (disabled)
- Week 3: Enable for 10% of requests
- Week 4: Enable for 50% of requests
- Week 5: Enable for 100% of requests
- Week 8: Remove old configuration code

## Success Metrics

### Technical Metrics
- **Source selection accuracy**: >99.9%
- **Response time**: <500ms for 95% of requests
- **Cache hit rate**: >80%
- **API fallback rate**: <20%

### Business Metrics
- **Cost reduction**: 30% less API usage
- **Data quality**: 80% queries use 1m resolution
- **User satisfaction**: Coverage visualization adoption
- **System reliability**: 99.9% uptime

## Risk Mitigation

### Technical Risks
- **S3 Access Issues**: Implement circuit breakers and fallbacks
- **API Rate Limiting**: Queue management and caching
- **CRS Transformation Errors**: Validation and error handling
- **Performance Degradation**: Load testing and optimization

### Operational Risks
- **Configuration Errors**: Automated validation
- **Coverage Gaps**: Global fallback ensures full coverage
- **Cost Overruns**: Usage monitoring and alerts

## Documentation Updates

### Developer Documentation
- Architecture diagrams
- API endpoint specifications
- Integration examples
- Troubleshooting guide

### User Documentation
- Coverage map explanation
- Data source information
- Resolution comparison guide
- Cost implications

## Timeline Summary

**Week 1**: Core spatial database and selection logic
**Week 2**: Backend API updates and GPXZ integration
**Week 3**: Frontend support and testing
**Week 4**: Final validation and deployment

## Next Steps

1. Review and approve implementation plan
2. Set up development branch
3. Begin Phase 1 implementation
4. Schedule weekly progress reviews
5. Prepare staging environment for testing

---

## Appendix A: Coverage Bounds Reference

### Australia (EPSG:3577)
- **ACT**: -35.9°S to -35.1°S, 148.7°E to 149.4°E
- **NSW**: -37.5°S to -28.2°S, 140.9°E to 153.6°E
- **VIC**: -39.2°S to -34.0°S, 140.9°E to 150.2°E

### New Zealand (EPSG:2193)
- **Auckland**: -37.5°S to -36.0°S, 174.0°E to 176.0°E
- **Wellington**: -41.6°S to -40.6°S, 174.6°E to 176.2°E
- **Canterbury**: -44.5°S to -42.5°S, 170.0°E to 173.5°E
- **Otago**: -46.7°S to -44.0°S, 167.5°E to 171.5°E

### GPXZ Coverage (EPSG:4326)
- **USA NED**: 24°N to 49°N, 125°W to 66°W (10m)
- **Europe EU-DEM**: 34°N to 71°N, 32°W to 45°E (25m)
- **Global SRTM**: 60°S to 60°N, 180°W to 180°E (30m)

## Appendix B: API Examples

### Current API (Maintained)
```bash
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'
```

### New Coverage API
```bash
curl "http://localhost:8001/api/v1/elevation/coverage-areas"

curl -X POST "http://localhost:8001/api/v1/elevation/sources/select" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'
```