# Phase 2: Unified Data Collections Architecture Implementation Plan

## 🎯 **Mission Statement**

Implement Gemini's unified `data_collections` schema to achieve true architectural unification between Australian and New Zealand elevation data systems, creating a single, country-agnostic spatial index that eliminates conditional logic and enables future scalability.

## 📊 **Current State Assessment**

### ✅ **Phase 1 Achievements**
- **NZ Campaign Structure**: 91 survey campaigns successfully implemented
- **Structural Consistency**: Both AU and NZ now use flat campaign/zone → files pattern
- **29,758 NZ Files**: All indexed with actual GeoTIFF bounds extraction
- **Production Deployment**: Campaign-based index uploaded to S3 (26.52MB)

### 🎯 **Phase 2 Objectives**
- **Unified Schema**: Single `data_collections` structure for both countries
- **Country-Agnostic Logic**: Eliminate AU/NZ conditional code paths
- **Schema Validation**: Pydantic models with fail-fast startup behavior
- **Feature Flag Safety**: Safe deployment with `USE_UNIFIED_SPATIAL_INDEX`
- **Performance Preservation**: Maintain 54,000x Brisbane speedup

## 🏗️ **Target Architecture**

### **Unified Spatial Index Schema v2.0**

```json
{
  "version": "2.0",
  "schema_metadata": {
    "generated_at": "2025-08-02T12:00:00.000Z",
    "generator": "unified_spatial_index_v2",
    "total_collections": 1244,
    "total_files": 32000+,
    "countries": ["AU", "NZ"],
    "collection_types": ["australian_utm_zone", "new_zealand_campaign"]
  },
  "data_collections": {
    // Australian UTM Zones (existing 1,153 converted)
    "au_z55_act2015": {
      "collection_id": "au_z55_act2015",
      "collection_type": "australian_utm_zone",
      "country": "AU",
      "utm_zone": 55,
      "state": "ACT",
      "campaign_year": 2015,
      "data_type": "DEM",
      "resolution_m": 1,
      "files": [...],
      "coverage_bounds": {...},
      "file_count": 150,
      "metadata": {
        "source_bucket": "road-engineering-elevation-data",
        "original_path": "act-elvis/elevation/1m-dem/z55/ACT2015/",
        "coordinate_system": "GDA94 / MGA Zone 55"
      }
    },
    "au_z56_qld_brisbane": {
      "collection_id": "au_z56_qld_brisbane",
      "collection_type": "australian_utm_zone",
      "country": "AU", 
      "utm_zone": 56,
      "state": "QLD",
      "region": "brisbane",
      "data_type": "DEM",
      "resolution_m": 1,
      "files": [...],
      "coverage_bounds": {...},
      "file_count": 200,
      "metadata": {
        "source_bucket": "road-engineering-elevation-data",
        "performance_note": "54000x speedup maintained",
        "coordinate_system": "GDA94 / MGA Zone 56"
      }
    },
    
    // New Zealand Campaigns (existing 91 converted)
    "nz_auckland_north_2016_dem": {
      "collection_id": "nz_auckland_north_2016_dem", 
      "collection_type": "new_zealand_campaign",
      "country": "NZ",
      "region": "auckland",
      "survey_name": "auckland-north",
      "survey_years": [2016, 2017, 2018],
      "data_type": "DEM",
      "resolution_m": 1,
      "files": [...],
      "coverage_bounds": {...},
      "file_count": 379,
      "metadata": {
        "source_bucket": "nz-elevation", 
        "original_campaign": "auckland-north_2016-2018_dem",
        "coordinate_system": "NZGD2000 / NZTM 2000 (EPSG:2193)"
      }
    },
    "nz_canterbury_2020_dem": {
      "collection_id": "nz_canterbury_2020_dem",
      "collection_type": "new_zealand_campaign", 
      "country": "NZ",
      "region": "canterbury",
      "survey_name": "canterbury",
      "survey_years": [2020, 2021, 2022, 2023],
      "data_type": "DEM", 
      "resolution_m": 1,
      "files": [...],
      "coverage_bounds": {...},
      "file_count": 2546,
      "metadata": {
        "source_bucket": "nz-elevation",
        "original_campaign": "canterbury_2020-2023_dem", 
        "coordinate_system": "NZGD2000 / NZTM 2000 (EPSG:2193)",
        "note": "Largest NZ campaign"
      }
    }
  }
}
```

## 🔧 **Implementation Strategy**

### **Step 1: Pydantic Schema Definition**

Create comprehensive data models for validation and type safety:

```python
# src/models/spatial_index_models.py
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Literal, Union
from datetime import datetime

class CoverageBounds(BaseModel):
    min_lat: float = Field(..., ge=-90, le=90)
    max_lat: float = Field(..., ge=-90, le=90) 
    min_lon: float = Field(..., ge=-180, le=180)
    max_lon: float = Field(..., ge=-180, le=180)

class FileEntry(BaseModel):
    file: str  # S3 path
    filename: str
    bounds: CoverageBounds
    size_mb: float
    last_modified: str
    resolution: str
    coordinate_system: str
    method: str

class CollectionMetadata(BaseModel):
    source_bucket: str
    coordinate_system: str
    original_path: Optional[str] = None
    original_campaign: Optional[str] = None
    performance_note: Optional[str] = None
    note: Optional[str] = None

class AustralianCollection(BaseModel):
    collection_id: str
    collection_type: Literal["australian_utm_zone"] = "australian_utm_zone"
    country: Literal["AU"] = "AU"
    utm_zone: int = Field(..., ge=1, le=60)
    state: str
    region: Optional[str] = None
    campaign_year: Optional[int] = None
    data_type: Literal["DEM", "DSM"] = "DEM"
    resolution_m: int = 1
    files: List[FileEntry]
    coverage_bounds: CoverageBounds
    file_count: int
    metadata: CollectionMetadata

class NewZealandCollection(BaseModel):
    collection_id: str
    collection_type: Literal["new_zealand_campaign"] = "new_zealand_campaign"
    country: Literal["NZ"] = "NZ"
    region: str
    survey_name: str
    survey_years: List[int]
    data_type: Literal["DEM", "DSM", "UNKNOWN"] = "DEM"
    resolution_m: int = 1
    files: List[FileEntry]
    coverage_bounds: CoverageBounds
    file_count: int
    metadata: CollectionMetadata

DataCollection = Union[AustralianCollection, NewZealandCollection]

class SchemaMetadata(BaseModel):
    generated_at: datetime
    generator: str = "unified_spatial_index_v2"
    total_collections: int
    total_files: int
    countries: List[str]
    collection_types: List[str]

class UnifiedSpatialIndex(BaseModel):
    version: Literal["2.0"] = "2.0"
    schema_metadata: SchemaMetadata
    data_collections: Dict[str, DataCollection]
    
    class Config:
        extra = "forbid"  # Strict validation
```

### **Step 2: Migration Scripts**

Create converters for existing indexes:

```python
# scripts/migrate_to_unified_index.py
class UnifiedIndexMigrator:
    """Migrates Australian and NZ indexes to unified v2.0 schema"""
    
    def migrate_australian_index(self, au_index: Dict) -> Dict[str, AustralianCollection]:
        """Convert AU utm_zones to data_collections"""
        
    def migrate_nz_index(self, nz_index: Dict) -> Dict[str, NewZealandCollection]:  
        """Convert NZ campaigns to data_collections"""
        
    def generate_unified_index(self) -> UnifiedSpatialIndex:
        """Combine both indexes into unified schema"""
```

### **Step 3: S3Source Refactoring**

Update S3Source to use unified schema:

```python
# src/data_sources/s3_source.py
class UnifiedS3Source:
    """Country-agnostic S3 source using unified data_collections"""
    
    def __init__(self, use_unified_index: bool = False):
        self.use_unified_index = use_unified_index
        
    def _load_spatial_index(self) -> UnifiedSpatialIndex:
        """Load and validate unified spatial index"""
        if self.use_unified_index:
            # Load unified v2.0 index
            return self._load_unified_index()
        else:
            # Load legacy indexes (AU + NZ separate)
            return self._load_legacy_indexes()
    
    def _find_collections_for_coordinate(self, lat: float, lon: float) -> List[DataCollection]:
        """Country-agnostic collection lookup"""
        # Single algorithm for both AU and NZ collections
        
    def _get_elevation_from_collection(self, collection: DataCollection, lat: float, lon: float) -> ElevationResult:
        """Extract elevation from any collection type"""
        # Polymorphic handling based on collection_type
```

### **Step 4: Feature Flag Implementation**

Safe deployment with configuration control:

```python
# src/config.py
class Settings(BaseSettings):
    USE_UNIFIED_SPATIAL_INDEX: bool = Field(
        default=False,
        description="Enable unified v2.0 spatial index (AU+NZ combined)"
    )
    UNIFIED_INDEX_PATH: str = Field(
        default="indexes/spatial_index_v2.json",
        description="S3 path for unified spatial index"
    )

# src/main.py - FastAPI lifespan
async def load_elevation_sources(app: FastAPI):
    settings = get_settings()
    
    if settings.USE_UNIFIED_SPATIAL_INDEX:
        logger.info("🔄 Loading unified spatial index v2.0...")
        s3_source = UnifiedS3Source(use_unified_index=True)
    else:
        logger.info("📊 Loading legacy spatial indexes...")
        s3_source = LegacyS3Source()
```

## 📋 **Implementation Tasks**

### **Phase 2.1: Schema Design & Validation**
1. **Create Pydantic Models**: Define comprehensive schema validation
2. **Schema Testing**: Validate with sample AU and NZ data
3. **Migration Logic**: Build converters for existing indexes
4. **Validation Suite**: Comprehensive testing framework

### **Phase 2.2: Index Generation**
1. **Unified Generator**: Single script for AU+NZ combined index
2. **Data Preservation**: Ensure no data loss during migration
3. **Performance Testing**: Validate index loading performance
4. **Size Optimization**: Optimize unified index file size

### **Phase 2.3: Application Integration**
1. **S3Source Refactoring**: Country-agnostic query logic
2. **Feature Flag Integration**: Safe deployment mechanism
3. **Fallback Logic**: Graceful degradation to legacy indexes
4. **Performance Validation**: Maintain Brisbane speedup

### **Phase 2.4: Production Deployment**
1. **Staging Testing**: Comprehensive validation in staging environment
2. **Gradual Rollout**: Feature flag controlled deployment
3. **Performance Monitoring**: Ensure no regression
4. **Documentation Update**: Complete operational guides

## 🎯 **Success Criteria**

### **Functional Requirements**
- ✅ **Single Index File**: Both AU and NZ data in unified schema
- ✅ **Country-Agnostic Logic**: No conditional AU/NZ code paths
- ✅ **Schema Validation**: Pydantic validation with fail-fast startup
- ✅ **Feature Flag Control**: Safe deployment and rollback capability
- ✅ **Data Integrity**: No loss of spatial or metadata information

### **Performance Requirements**
- ✅ **Brisbane Speedup Preserved**: Maintain 54,000x performance
- ✅ **Index Loading Time**: <5 seconds for complete unified index
- ✅ **Memory Usage**: <100MB for unified index in memory
- ✅ **Query Performance**: <50ms for coordinate → collection lookup

### **Operational Requirements** 
- ✅ **Production Safety**: Feature flag controlled deployment
- ✅ **Monitoring**: Comprehensive logging and error tracking
- ✅ **Documentation**: Complete operational and architectural docs
- ✅ **Rollback Plan**: Immediate fallback to legacy indexes

## 🔍 **Risk Assessment & Mitigation**

### **High Risk: Performance Regression**
- **Risk**: Unified index could slow down Brisbane queries
- **Mitigation**: Extensive performance testing, feature flag rollback

### **Medium Risk: Schema Complexity**
- **Risk**: Complex schema could introduce validation errors
- **Mitigation**: Comprehensive Pydantic validation, extensive testing

### **Low Risk: Data Loss During Migration**
- **Risk**: Information could be lost converting to unified schema
- **Mitigation**: Data preservation validation, backup procedures

## 📊 **Timeline & Dependencies**

### **Phase 2 Implementation: 3-4 Development Sessions**
- **Session 1**: Pydantic schema design and validation
- **Session 2**: Migration scripts and unified index generation
- **Session 3**: S3Source refactoring and feature flag integration
- **Session 4**: Production deployment and performance validation

### **Dependencies**
- **Phase 1 Complete**: NZ campaign structure must be deployed
- **Existing Performance**: Brisbane speedup benchmarks established
- **Production Access**: Railway deployment and S3 upload capabilities

This Phase 2 implementation will achieve Gemini's vision of true architectural unification, creating a foundation for the advanced patterns in Phase 3 (R-tree optimization, composite patterns) while maintaining the project's safety-first engineering principles.