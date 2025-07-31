# Overlapping DEM Implementation Plan

**Project**: DEM Elevation Service - Serverless Architecture (Vercel + S3)  
**Date**: December 6, 2024  
**Scope**: Australia and New Zealand DEM Coverage  

## 📊 Project Requirements Summary

- **Data Volume**: 20-30 DEM files
- **Update Frequency**: Infrequent updates
- **Geographic Scope**: Australia and New Zealand
- **Current Architecture**: Vercel Serverless + Amazon S3
- **Budget**: Open to PostGIS database integration

## 🎯 Architecture Overview

### Current State
- Single `DTM.gdb` file (4GB) on S3
- Cloud-native rasterio access with HTTP range requests
- Vercel serverless functions with AWS S3 integration

### Target State
- Multiple overlapping DEM files with priority-based selection
- Spatial indexing for efficient overlap detection
- Support for different resolutions and data sources
- Australia/New Zealand coverage

## 🏗️ Implementation Strategy

### Phase 1: Enhanced Config-Based System (Immediate - 1-2 weeks)

#### Enhanced Configuration Structure
```python
# Enhanced config.py
DEM_SOURCES = {
    "lidar_gold_coast_2024": {
        "path": "s3://roadengineer-dem-files/au/qld/lidar_gc_2024.tif",
        "resolution": 0.5,
        "priority": 1,
        "bounds": {"west": 153.0, "south": -28.5, "east": 153.8, "north": -27.8},
        "crs": "EPSG:28356",
        "data_source": "LiDAR",
        "year": 2024,
        "region": "Gold Coast"
    },
    "regional_qld_5m": {
        "path": "s3://roadengineer-dem-files/au/qld/regional_5m.tif",
        "resolution": 5.0,
        "priority": 2,
        "bounds": {"west": 138.0, "south": -29.0, "east": 154.0, "north": -10.0},
        "crs": "EPSG:28356",
        "data_source": "Photogrammetry",
        "year": 2023,
        "region": "Queensland"
    },
    "nz_north_island": {
        "path": "s3://roadengineer-dem-files/nz/north/nztm_8m.tif",
        "resolution": 8.0,
        "priority": 3,
        "bounds": {"west": 166.0, "south": -41.5, "east": 179.0, "north": -34.0},
        "crs": "EPSG:2193",  # NZTM
        "data_source": "SRTM",
        "year": 2022,
        "region": "North Island"
    }
}
```

#### DEM Selection Logic
```python
# New dem_selector.py
from typing import List, Optional
from config import Settings

class DEMSelector:
    def __init__(self, settings: Settings):
        self.sources = settings.DEM_SOURCES
    
    def find_overlapping_sources(self, lat: float, lon: float) -> List[str]:
        """Find all DEM sources that contain the coordinate"""
        matching_sources = []
        
        for source_id, source_config in self.sources.items():
            bounds = source_config.bounds
            if (bounds["west"] <= lon <= bounds["east"] and 
                bounds["south"] <= lat <= bounds["north"]):
                matching_sources.append(source_id)
        
        return matching_sources
    
    def select_best_source(self, lat: float, lon: float) -> Optional[str]:
        """Select the best DEM source based on priority rules"""
        overlapping = self.find_overlapping_sources(lat, lon)
        
        if not overlapping:
            return None
        
        if len(overlapping) == 1:
            return overlapping[0]
        
        # Priority rules: 1. Manual priority, 2. Resolution, 3. Recency
        best_source = min(overlapping, key=lambda sid: (
            self.sources[sid].priority,
            self.sources[sid].resolution,
            -self.sources[sid].year  # Negative for descending (newer first)
        ))
        
        return best_source
    
    def get_overlap_info(self, lat: float, lon: float) -> dict:
        """Return detailed information about overlapping sources"""
        overlapping = self.find_overlapping_sources(lat, lon)
        selected = self.select_best_source(lat, lon)
        
        return {
            "coordinate": {"lat": lat, "lon": lon},
            "overlapping_sources": len(overlapping),
            "available_sources": overlapping,
            "selected_source": selected,
            "selection_details": {
                source_id: {
                    "resolution": self.sources[source_id].resolution,
                    "priority": self.sources[source_id].priority,
                    "year": self.sources[source_id].year,
                    "data_source": self.sources[source_id].data_source
                }
                for source_id in overlapping
            } if overlapping else {}
        }
```

#### Integration with Existing DEM Service
```python
# Updated dem_service.py
from dem_selector import DEMSelector

class DEMService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.dem_selector = DEMSelector(settings)
        # ... existing initialization code ...
    
    def get_elevation_at_point(self, latitude: float, longitude: float, 
                              dem_source_id: Optional[str] = None) -> Tuple[Optional[float], str, Optional[str]]:
        """
        Get elevation at a single point with automatic DEM selection.
        """
        # If no specific DEM source requested, auto-select the best one
        if dem_source_id is None:
            dem_source_id = self.dem_selector.select_best_source(latitude, longitude)
            if dem_source_id is None:
                return None, "none", "No DEM coverage available for this location"
        
        # ... rest of existing elevation logic ...
        return elevation, dem_source_id, message
```

### Phase 2: Spatial Indexing (3-6 months)

#### Pre-computed Spatial Index
```json
// spatial_index.json stored on S3
{
    "index_version": "1.0",
    "last_updated": "2024-12-06T10:30:00Z",
    "grid_size": 0.1,
    "coordinate_system": "WGS84",
    "cells": {
        "153.0_-28.0": [
            {"source_id": "lidar_gold_coast_2024", "priority": 1, "resolution": 0.5},
            {"source_id": "regional_qld_5m", "priority": 2, "resolution": 5.0}
        ],
        "167.0_-36.0": [
            {"source_id": "nz_north_island", "priority": 3, "resolution": 8.0}
        ]
    },
    "statistics": {
        "total_cells": 2847,
        "cells_with_multiple_sources": 156,
        "max_overlaps_per_cell": 4
    }
}
```

## 📁 File Organization Strategy

### S3 Bucket Structure
```
s3://roadengineer-dem-files/
├── au/                           # Australia
│   ├── qld/                      # Queensland
│   │   ├── lidar_gc_2024.tif    # Gold Coast LiDAR (0.5m)
│   │   ├── regional_5m.tif      # Regional coverage (5m)
│   │   └── srtm_30m.tif         # SRTM fallback (30m)
│   ├── nsw/                      # New South Wales
│   │   ├── sydney_lidar_2024.tif
│   │   ├── regional_10m.tif
│   │   └── srtm_30m.tif
│   ├── vic/                      # Victoria
│   ├── wa/                       # Western Australia
│   ├── sa/                       # South Australia
│   ├── tas/                      # Tasmania
│   ├── nt/                       # Northern Territory
│   └── national/
│       └── srtm_australia_30m.tif
├── nz/                           # New Zealand
│   ├── north/
│   │   ├── lidar_auckland_2024.tif
│   │   └── nztm_8m.tif
│   ├── south/
│   │   └── nztm_8m.tif
│   └── national/
│       └── srtm_newzealand_30m.tif
├── metadata/                     # Index and metadata files
│   ├── spatial_index.json
│   ├── source_catalog.json
│   └── coverage_map.geojson
└── archive/                      # Archived/historical data
    └── old_versions/
```

### Naming Convention
```
{data_source}_{region}_{resolution}_{year}.{ext}

Examples:
- lidar_goldcoast_0.5m_2024.tif
- photogrammetry_qld_5m_2023.tif
- srtm_australia_30m_2022.tif
- nztm_northisland_8m_2023.tif
```

## 🔧 Priority Rules Implementation

### Priority Calculation Logic
```python
PRIORITY_RULES = {
    "manual_priority": {
        "weight": 1.0,
        "description": "Manually assigned priority (1=highest)"
    },
    "resolution": {
        "weight": 2.0, 
        "description": "Spatial resolution (smaller=better)"
    },
    "data_source": {
        "weight": 3.0,
        "hierarchy": {
            "LiDAR": 1,
            "Photogrammetry": 2, 
            "SAR": 3,
            "SRTM": 4
        }
    },
    "recency": {
        "weight": 4.0,
        "description": "Year of data collection (newer=better)"
    }
}

def calculate_source_score(source_config: dict) -> float:
    """Calculate composite score for DEM source selection"""
    score = 0
    
    # Manual priority (lower is better)
    score += source_config.priority * PRIORITY_RULES["manual_priority"]["weight"]
    
    # Resolution (lower is better)
    score += source_config.resolution * PRIORITY_RULES["resolution"]["weight"]
    
    # Data source type
    data_source_rank = PRIORITY_RULES["data_source"]["hierarchy"].get(
        source_config.data_source, 5
    )
    score += data_source_rank * PRIORITY_RULES["data_source"]["weight"]
    
    # Recency (older is worse)
    age_penalty = (2024 - source_config.year) * 0.1
    score += age_penalty * PRIORITY_RULES["recency"]["weight"]
    
    return score
```

## 🛠️ Admin Tools (Phase 3)

### DEM Management Tools
```python
# admin_tools.py
class DEMAdminTools:
    def rebuild_spatial_index(self):
        """Rebuild spatial index when new DEM files are added"""
        pass
    
    def validate_dem_coverage(self):
        """Check for gaps or excessive overlaps in coverage"""
        pass
    
    def update_dem_priorities(self):
        """Tool to adjust priorities when new data arrives"""
        pass
    
    def generate_coverage_report(self):
        """Generate coverage statistics and overlap analysis"""
        pass
    
    def upload_new_dem(self, file_path: str, metadata: dict):
        """Upload new DEM file with metadata"""
        pass
```

### Coverage Analysis
```python
def analyze_coverage():
    """Analyze current DEM coverage and identify gaps"""
    return {
        "total_area_covered": "2.1M km²",
        "coverage_by_resolution": {
            "0.5m": "15,000 km²",
            "5m": "500,000 km²", 
            "30m": "1.6M km²"
        },
        "overlap_statistics": {
            "areas_with_multiple_sources": "45,000 km²",
            "max_overlaps": 4,
            "avg_overlaps": 1.8
        },
        "gaps": [
            {"region": "Central Australia", "area": "50,000 km²"},
            {"region": "Remote WA", "area": "25,000 km²"}
        ]
    }
```

## 🚀 Implementation Timeline

### Week 1-2: Basic Overlap Detection
- [x] Current single-file S3 system working
- [ ] Extend config.py with bounds and metadata
- [ ] Implement DEMSelector class
- [ ] Add overlap detection to DEM service
- [ ] Test with 2-3 sample files

### Month 1: Production Deployment
- [ ] Deploy enhanced system to Vercel
- [ ] Add 5-10 DEM files covering key regions
- [ ] Implement priority-based selection
- [ ] Add API endpoints for overlap information

### Month 2-3: Spatial Indexing
- [ ] Build spatial index generation tools
- [ ] Implement grid-based indexing
- [ ] Add index caching and optimization
- [ ] Performance testing and optimization

### Month 4-6: Full Coverage
- [ ] Add all 20-30 DEM files
- [ ] Implement admin tools
- [ ] Add coverage analysis and reporting
- [ ] Documentation and monitoring

## 📈 Performance Considerations

### Serverless Constraints
- **Memory Limit**: 1GB RAM on Vercel
- **Cold Start**: Keep index loading under 1-2 seconds
- **File Size**: Individual DEM files should be reasonable for HTTP range requests

### Optimization Strategies
- **Index Caching**: Cache spatial index in memory between requests
- **Grid Size**: 0.1° grid cells balance accuracy vs. performance
- **Lazy Loading**: Only load DEM metadata when needed
- **Regional Deployment**: Consider edge functions for global coverage

## 🔍 Testing Strategy

### Test Cases
1. **Single Coverage**: Points with only one DEM source
2. **Multiple Overlaps**: Points with 2-4 overlapping sources  
3. **No Coverage**: Points outside all DEM bounds
4. **Edge Cases**: Points exactly on boundaries
5. **Performance**: Response times with full dataset

### Sample Test Coordinates
```python
TEST_COORDINATES = {
    "gold_coast": {"lat": -28.0, "lon": 153.3},  # Multiple overlaps expected
    "sydney": {"lat": -33.8, "lon": 151.2},     # High-res LiDAR available
    "auckland": {"lat": -36.8, "lon": 174.7},   # New Zealand coverage
    "outback": {"lat": -25.0, "lon": 135.0},    # SRTM only
    "no_coverage": {"lat": 0.0, "lon": 0.0}     # No coverage expected
}
```

## 📋 Next Steps

### Immediate Actions (This Week)
1. **Implement basic DEMSelector class**
2. **Test overlap detection with current single file**
3. **Add 1-2 additional DEM files to S3**
4. **Update API to return overlap information**

### Decision Points
- **Start with Option A (minimal)** or **Option B (full implementation)**?
- **Deploy current system to Vercel first** or **add overlap handling locally**?
- **Add PostGIS integration** now or later?

---

**Recommendation**: Start with **Phase 1 implementation** immediately, test with 2-3 files, then deploy to Vercel. The scale (20-30 files) and update frequency (infrequent) makes the config-based approach ideal for quick implementation and reliable operation. 