"""
Configurable Coverage Database for DEM Sources
Implements Phase 1 of SPATIAL_COVERAGE_IMPLEMENTATION_PLAN_V2.md
"""
import json
import os
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class CoverageDatabase:
    """
    Manages elevation source database with configurable loading
    Supports JSON config files and environment variables
    """
    
    SUPPORTED_SCHEMA_VERSION = "1.0"
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize coverage database from JSON config or environment variable
        
        Args:
            config_path: Path to JSON config file (overrides environment)
        """
        self.sources = []
        self.schema_version = None
        self.last_updated = None
        
        # Load sources from config
        if config_path:
            self._load_from_file(config_path)
        elif os.getenv('DEM_SOURCES_CONFIG_PATH'):
            self._load_from_file(os.getenv('DEM_SOURCES_CONFIG_PATH'))
        else:
            logger.info("No config file specified, using default hardcoded sources")
            self._load_default_sources()
            
        # Validate all sources
        self._validate_sources()
        self._validate_schema_version()
        
        logger.info(
            f"Coverage database initialized: {len(self.sources)} sources, "
            f"schema v{self.schema_version}"
        )
    
    def _load_from_file(self, path: str) -> None:
        """Load sources from JSON configuration file"""
        try:
            config_path = Path(path)
            if not config_path.exists():
                raise FileNotFoundError(f"Config file not found: {path}")
                
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Extract metadata
            self.schema_version = config.get('schema_version', '1.0')
            self.last_updated = config.get('last_updated')
            self.sources = config.get('elevation_sources', [])
            
            logger.info(f"Loaded {len(self.sources)} sources from {path}")
            
        except Exception as e:
            logger.error(f"Failed to load config from {path}: {e}")
            raise ValueError(f"Invalid configuration file: {e}")
    
    def _load_default_sources(self) -> None:
        """Load default hardcoded sources with complete attributes"""
        self.schema_version = self.SUPPORTED_SCHEMA_VERSION
        self.last_updated = "2024-01-17"
        
        self.sources = [
            # Australia S3 Sources (Priority 1 - 1m LiDAR)
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
                "enabled": True,
                "visible_in_coverage": True,
                "metadata": {
                    "capture_date": "2019-2021",
                    "point_density": "8 points/m²",
                    "vertical_datum": "AHD"
                }
            },
            {
                "id": "nsw_elvis",
                "name": "New South Wales LiDAR",
                "source_type": "s3",
                "path": "s3://road-engineering-elevation-data/nsw-elvis/",
                "crs": "EPSG:3577",
                "resolution_m": 1,
                "data_type": "LiDAR",
                "provider": "NSW Elvis",
                "priority": 1,
                "bounds": {
                    "type": "bbox",
                    "min_lat": -37.5,
                    "max_lat": -28.2,
                    "min_lon": 140.9,
                    "max_lon": 153.6
                },
                "cost_per_query": 0.001,
                "accuracy": "±0.1m",
                "enabled": True,
                "visible_in_coverage": True,
                "metadata": {
                    "capture_date": "2017-2021",
                    "point_density": "4-8 points/m²",
                    "vertical_datum": "AHD"
                }
            },
            {
                "id": "vic_elvis",
                "name": "Victoria LiDAR",
                "source_type": "s3",
                "path": "s3://road-engineering-elevation-data/vic-elvis/",
                "crs": "EPSG:3577",
                "resolution_m": 1,
                "data_type": "LiDAR",
                "provider": "VIC Elvis",
                "priority": 1,
                "bounds": {
                    "type": "bbox",
                    "min_lat": -39.2,
                    "max_lat": -34.0,
                    "min_lon": 140.9,
                    "max_lon": 150.2
                },
                "cost_per_query": 0.001,
                "accuracy": "±0.1m",
                "enabled": True,
                "visible_in_coverage": True,
                "metadata": {
                    "capture_date": "2018-2021",
                    "point_density": "4 points/m²",
                    "vertical_datum": "AHD"
                }
            },
            
            # New Zealand S3 Sources (Priority 1 - 1m LiDAR)
            {
                "id": "nz_auckland",
                "name": "Auckland Region LiDAR",
                "source_type": "s3",
                "path": "s3://nz-elevation/auckland/",
                "crs": "EPSG:2193",
                "resolution_m": 1,
                "data_type": "LiDAR",
                "provider": "LINZ Open Data",
                "priority": 1,
                "bounds": {
                    "type": "bbox",
                    "min_lat": -37.5,
                    "max_lat": -36.0,
                    "min_lon": 174.0,
                    "max_lon": 176.0
                },
                "cost_per_query": 0.0,
                "accuracy": "±0.1m",
                "enabled": True,
                "visible_in_coverage": True,
                "metadata": {
                    "capture_date": "2013-2019",
                    "point_density": "4 points/m²",
                    "vertical_datum": "NZVD2016"
                }
            },
            {
                "id": "nz_wellington",
                "name": "Wellington Region LiDAR",
                "source_type": "s3",
                "path": "s3://nz-elevation/wellington/",
                "crs": "EPSG:2193",
                "resolution_m": 1,
                "data_type": "LiDAR",
                "provider": "LINZ Open Data",
                "priority": 1,
                "bounds": {
                    "type": "bbox",
                    "min_lat": -41.6,
                    "max_lat": -40.6,
                    "min_lon": 174.6,
                    "max_lon": 176.2
                },
                "cost_per_query": 0.0,
                "accuracy": "±0.1m",
                "enabled": True,
                "visible_in_coverage": True,
                "metadata": {
                    "capture_date": "2013-2018",
                    "point_density": "4 points/m²",
                    "vertical_datum": "NZVD2016"
                }
            },
            {
                "id": "nz_canterbury",
                "name": "Canterbury Region LiDAR",
                "source_type": "s3",
                "path": "s3://nz-elevation/canterbury/",
                "crs": "EPSG:2193",
                "resolution_m": 1,
                "data_type": "LiDAR",
                "provider": "LINZ Open Data",
                "priority": 1,
                "bounds": {
                    "type": "bbox",
                    "min_lat": -44.5,
                    "max_lat": -42.5,
                    "min_lon": 170.0,
                    "max_lon": 173.5
                },
                "cost_per_query": 0.0,
                "accuracy": "±0.1m",
                "enabled": True,
                "visible_in_coverage": True,
                "metadata": {
                    "capture_date": "2015-2020",
                    "point_density": "4 points/m²",
                    "vertical_datum": "NZVD2016"
                }
            },
            {
                "id": "nz_otago",
                "name": "Otago Region LiDAR",
                "source_type": "s3",
                "path": "s3://nz-elevation/otago/",
                "crs": "EPSG:2193",
                "resolution_m": 1,
                "data_type": "LiDAR",
                "provider": "LINZ Open Data",
                "priority": 1,
                "bounds": {
                    "type": "bbox",
                    "min_lat": -46.7,
                    "max_lat": -44.0,
                    "min_lon": 167.5,
                    "max_lon": 171.5
                },
                "cost_per_query": 0.0,
                "accuracy": "±0.1m",
                "enabled": True,
                "visible_in_coverage": True,
                "metadata": {
                    "capture_date": "2016-2020",
                    "point_density": "4 points/m²",
                    "vertical_datum": "NZVD2016"
                }
            },
            {
                "id": "nz_national",
                "name": "New Zealand National LiDAR",
                "source_type": "s3",
                "path": "s3://nz-elevation/",
                "crs": "EPSG:2193",
                "resolution_m": 1,
                "data_type": "LiDAR",
                "provider": "LINZ Open Data",
                "priority": 1,
                "bounds": {
                    "type": "bbox",
                    "min_lat": -47.3,
                    "max_lat": -34.4,
                    "min_lon": 166.4,
                    "max_lon": 178.6
                },
                "cost_per_query": 0.0,
                "accuracy": "±0.1m",
                "enabled": True,
                "visible_in_coverage": True,
                "metadata": {
                    "capture_date": "2013-2021",
                    "point_density": "1-8 points/m²",
                    "vertical_datum": "NZVD2016"
                }
            },
            
            # GPXZ Enhanced Coverage (Priority 2)
            {
                "id": "gpxz_usa_ned",
                "name": "USA NED 10m",
                "source_type": "api",
                "path": "api://gpxz",
                "crs": "EPSG:4326",
                "resolution_m": 10,
                "data_type": "NED",
                "provider": "GPXZ",
                "priority": 2,
                "bounds": {
                    "type": "bbox",
                    "min_lat": 24.0,
                    "max_lat": 49.0,
                    "min_lon": -125.0,
                    "max_lon": -66.0
                },
                "cost_per_query": 0.01,
                "accuracy": "±5m",
                "enabled": True,
                "visible_in_coverage": True,
                "metadata": {
                    "dataset": "USGS National Elevation Dataset",
                    "vertical_datum": "NAVD88"
                }
            },
            {
                "id": "gpxz_europe_eudem",
                "name": "Europe EU-DEM 25m",
                "source_type": "api",
                "path": "api://gpxz",
                "crs": "EPSG:4326",
                "resolution_m": 25,
                "data_type": "EU-DEM",
                "provider": "GPXZ",
                "priority": 2,
                "bounds": {
                    "type": "bbox",
                    "min_lat": 34.0,
                    "max_lat": 71.0,
                    "min_lon": -32.0,
                    "max_lon": 45.0
                },
                "cost_per_query": 0.01,
                "accuracy": "±7m",
                "enabled": True,
                "visible_in_coverage": True,
                "metadata": {
                    "dataset": "EU Digital Elevation Model",
                    "vertical_datum": "EVS2000"
                }
            },
            
            # GPXZ Global Coverage (Priority 3)
            {
                "id": "gpxz_global_srtm",
                "name": "Global SRTM 30m",
                "source_type": "api",
                "path": "api://gpxz",
                "crs": "EPSG:4326",
                "resolution_m": 30,
                "data_type": "SRTM",
                "provider": "GPXZ",
                "priority": 3,
                "bounds": {
                    "type": "bbox",
                    "min_lat": -60.0,
                    "max_lat": 60.0,
                    "min_lon": -180.0,
                    "max_lon": 180.0
                },
                "cost_per_query": 0.01,
                "accuracy": "±16m",
                "enabled": True,
                "visible_in_coverage": True,
                "metadata": {
                    "dataset": "Shuttle Radar Topography Mission",
                    "vertical_datum": "WGS84"
                }
            }
        ]
    
    def _validate_sources(self) -> None:
        """Validate all sources have required attributes"""
        required_fields = [
            'id', 'name', 'source_type', 'path', 'crs', 
            'resolution_m', 'data_type', 'provider', 'priority', 
            'bounds', 'cost_per_query', 'accuracy', 'enabled'
        ]
        
        for i, source in enumerate(self.sources):
            # Check required fields
            missing = [f for f in required_fields if f not in source]
            if missing:
                raise ValueError(
                    f"Source {source.get('id', f'index_{i}')} missing required fields: {missing}"
                )
            
            # Validate source types
            if source['source_type'] not in ['s3', 'api']:
                raise ValueError(
                    f"Source {source['id']} has invalid source_type: {source['source_type']}"
                )
            
            # Validate bounds structure
            bounds = source['bounds']
            if bounds['type'] == 'bbox':
                required_bbox = ['min_lat', 'max_lat', 'min_lon', 'max_lon']
                missing_bbox = [f for f in required_bbox if f not in bounds]
                if missing_bbox:
                    raise ValueError(
                        f"Source {source['id']} bbox missing fields: {missing_bbox}"
                    )
                
                # Validate coordinate ranges
                if not (-90 <= bounds['min_lat'] <= bounds['max_lat'] <= 90):
                    raise ValueError(f"Source {source['id']} has invalid latitude bounds")
                if not (-180 <= bounds['min_lon'] <= bounds['max_lon'] <= 180):
                    raise ValueError(f"Source {source['id']} has invalid longitude bounds")
            
            # Validate priority
            if not isinstance(source['priority'], int) or source['priority'] < 1:
                raise ValueError(f"Source {source['id']} has invalid priority: {source['priority']}")
                
            # Validate resolution
            if not isinstance(source['resolution_m'], (int, float)) or source['resolution_m'] <= 0:
                raise ValueError(f"Source {source['id']} has invalid resolution: {source['resolution_m']}")
    
    def _validate_schema_version(self) -> None:
        """Validate schema version compatibility"""
        if not self.schema_version:
            logger.warning("No schema version specified, assuming current version")
            self.schema_version = self.SUPPORTED_SCHEMA_VERSION
            return
            
        if self.schema_version != self.SUPPORTED_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported schema version {self.schema_version}. "
                f"Supported version: {self.SUPPORTED_SCHEMA_VERSION}"
            )
    
    def get_enabled_sources(self) -> List[Dict[str, Any]]:
        """Get all enabled sources"""
        return [s for s in self.sources if s['enabled']]
    
    def get_sources_by_priority(self, priority: int) -> List[Dict[str, Any]]:
        """Get all enabled sources with specified priority"""
        return [
            s for s in self.sources 
            if s['enabled'] and s['priority'] == priority
        ]
    
    def get_source_by_id(self, source_id: str) -> Optional[Dict[str, Any]]:
        """Get source by ID"""
        for source in self.sources:
            if source['id'] == source_id:
                return source
        return None
    
    def get_visible_sources(self) -> List[Dict[str, Any]]:
        """Get sources that should be visible in coverage maps"""
        return [
            s for s in self.sources 
            if s['enabled'] and s.get('visible_in_coverage', True)
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        enabled = self.get_enabled_sources()
        
        by_priority = {}
        by_type = {}
        
        for source in enabled:
            priority = source['priority']
            source_type = source['source_type']
            
            by_priority[priority] = by_priority.get(priority, 0) + 1
            by_type[source_type] = by_type.get(source_type, 0) + 1
        
        return {
            "total_sources": len(self.sources),
            "enabled_sources": len(enabled),
            "visible_sources": len(self.get_visible_sources()),
            "schema_version": self.schema_version,
            "last_updated": self.last_updated,
            "by_priority": by_priority,
            "by_type": by_type,
            "resolution_range": {
                "min": min(s['resolution_m'] for s in enabled) if enabled else None,
                "max": max(s['resolution_m'] for s in enabled) if enabled else None
            }
        }