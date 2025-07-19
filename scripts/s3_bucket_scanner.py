#!/usr/bin/env python3
"""
S3 Bucket Scanner for DEM Source Discovery
Automatically discovers and validates DEM sources in S3 buckets
"""
import boto3
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
import logging

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config import Settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class DemSource:
    """DEM source metadata"""
    path: str
    crs: str
    description: str
    file_count: int
    total_size_gb: float
    sample_files: List[str]
    geographic_areas: Set[str]
    utm_zones: Set[str]
    resolutions: Set[str]

class S3BucketScanner:
    """
    Automated S3 bucket scanner for DEM source discovery
    
    Features:
    - Discovers all available DEM datasets in S3 bucket
    - Extracts geographic coverage from filenames
    - Validates source paths and estimates coverage
    - Generates source configurations automatically
    - Detects missing/orphaned configurations
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.s3 = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_DEFAULT_REGION
        )
        self.bucket = settings.AWS_S3_BUCKET_NAME
        
    def scan_bucket(self) -> Dict[str, DemSource]:
        """Scan entire bucket and discover all DEM sources"""
        logger.info(f"Scanning S3 bucket: {self.bucket}")
        
        discovered_sources = {}
        
        # Get top-level folders
        try:
            response = self.s3.list_objects_v2(Bucket=self.bucket, Delimiter='/')
            
            if 'CommonPrefixes' in response:
                for prefix in response['CommonPrefixes']:
                    folder = prefix['Prefix'].rstrip('/')
                    logger.info(f"Analyzing folder: {folder}")
                    
                    # Scan each folder for DEM data
                    sources = self._scan_folder(folder)
                    discovered_sources.update(sources)
                    
        except Exception as e:
            logger.error(f"Error scanning bucket: {e}")
            
        return discovered_sources
    
    def _scan_folder(self, folder: str) -> Dict[str, DemSource]:
        """Scan a specific folder for DEM sources"""
        sources = {}
        
        try:
            paginator = self.s3.get_paginator('list_objects_v2')
            
            # Find all elevation data paths
            dem_paths = set()
            for page in paginator.paginate(Bucket=self.bucket, Prefix=f"{folder}/"):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        key = obj['Key']
                        if key.endswith(('.tif', '.tiff')) and 'elevation' in key:
                            # Extract the logical DEM source path
                            path_parts = key.split('/')
                            if len(path_parts) >= 3:
                                # Find the deepest folder containing DEM files
                                for i in range(len(path_parts) - 1, 0, -1):
                                    dem_path = '/'.join(path_parts[:i]) + '/'
                                    if self._is_logical_dem_source(dem_path):
                                        dem_paths.add(dem_path)
                                        break
            
            # Analyze each discovered DEM path
            for dem_path in dem_paths:
                source = self._analyze_dem_source(dem_path)
                if source:
                    source_id = self._generate_source_id(dem_path)
                    sources[source_id] = source
                    
        except Exception as e:
            logger.error(f"Error scanning folder {folder}: {e}")
            
        return sources
    
    def _is_logical_dem_source(self, path: str) -> bool:
        """Determine if a path represents a logical DEM source"""
        # Look for patterns that indicate DEM source boundaries
        path_lower = path.lower()
        
        # Resolution indicators
        if any(res in path_lower for res in ['1m-dem', '50cm-dem', '2m-dem', '5m-dem']):
            return True
            
        # UTM zone indicators
        if any(zone in path_lower for zone in ['/z50/', '/z51/', '/z52/', '/z53/', '/z54/', '/z55/', '/z56/']):
            return True
            
        # Projection indicators
        if any(proj in path_lower for proj in ['ausgeoid', 'quasigeoid', 'ahd']):
            return True
            
        return False
    
    def _analyze_dem_source(self, dem_path: str) -> Optional[DemSource]:
        """Analyze a specific DEM source path"""
        try:
            logger.info(f"Analyzing DEM source: {dem_path}")
            
            file_count = 0
            total_size = 0
            sample_files = []
            geographic_areas = set()
            utm_zones = set()
            resolutions = set()
            
            paginator = self.s3.get_paginator('list_objects_v2')
            
            for page in paginator.paginate(Bucket=self.bucket, Prefix=dem_path):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        if obj['Key'].endswith(('.tif', '.tiff')):
                            file_count += 1
                            total_size += obj['Size']
                            
                            # Collect sample files
                            if len(sample_files) < 5:
                                sample_files.append(obj['Key'].split('/')[-1])
                            
                            # Extract metadata from filename
                            filename = obj['Key'].split('/')[-1]
                            areas, zones, reso = self._extract_metadata_from_filename(filename)
                            geographic_areas.update(areas)
                            utm_zones.update(zones)
                            resolutions.update(reso)
            
            if file_count == 0:
                return None
                
            # Determine CRS based on UTM zones
            crs = self._determine_crs(utm_zones, dem_path)
            
            # Generate description
            description = self._generate_description(dem_path, geographic_areas, resolutions)
            
            return DemSource(
                path=f"s3://{self.bucket}/{dem_path}",
                crs=crs,
                description=description,
                file_count=file_count,
                total_size_gb=total_size / (1024**3),
                sample_files=sample_files,
                geographic_areas=geographic_areas,
                utm_zones=utm_zones,
                resolutions=resolutions
            )
            
        except Exception as e:
            logger.error(f"Error analyzing {dem_path}: {e}")
            return None
    
    def _extract_metadata_from_filename(self, filename: str) -> Tuple[Set[str], Set[str], Set[str]]:
        """Extract geographic and technical metadata from filename"""
        areas = set()
        zones = set()
        resolutions = set()
        
        filename_lower = filename.lower()
        
        # Geographic areas
        area_patterns = [
            'adelaide', 'melbourne', 'sydney', 'brisbane', 'perth', 'darwin',
            'bendigo', 'ballarat', 'geelong', 'toowoomba', 'cairns', 'townsville',
            'act', 'nsw', 'vic', 'qld', 'sa', 'wa', 'nt', 'tas',
            'clarence', 'richmond', 'burnett', 'fitzroy', 'mary',
            'hunter', 'manning', 'richmond', 'cooper', 'murray', 'goulburn'
        ]
        
        for pattern in area_patterns:
            if pattern in filename_lower:
                areas.add(pattern.title())
        
        # UTM zones
        for zone in ['50', '51', '52', '53', '54', '55', '56']:
            if f'_{zone}_' in filename or f'z{zone}' in filename_lower:
                zones.add(f'z{zone}')
        
        # Resolutions
        if '50cm' in filename_lower or '0_5' in filename:
            resolutions.add('50cm')
        elif '1m' in filename_lower:
            resolutions.add('1m')
        elif '2m' in filename_lower:
            resolutions.add('2m')
        elif '5m' in filename_lower:
            resolutions.add('5m')
        
        return areas, zones, resolutions
    
    def _determine_crs(self, utm_zones: Set[str], path: str) -> str:
        """Determine appropriate CRS based on UTM zones and path"""
        if len(utm_zones) == 1:
            zone = list(utm_zones)[0].replace('z', '')
            return f"EPSG:327{zone}"  # UTM WGS84 southern hemisphere
        elif 'ausgeoid' in path.lower() or 'quasigeoid' in path.lower():
            return "EPSG:3577"  # Australian Albers
        else:
            return "EPSG:4326"  # WGS84 as fallback
    
    def _generate_description(self, path: str, areas: Set[str], resolutions: Set[str]) -> str:
        """Generate human-readable description"""
        path_parts = path.split('/')
        
        # Extract organization
        org = path_parts[0].replace('-elvis', '').upper() if path_parts else 'Unknown'
        
        # Extract resolution
        res = list(resolutions)[0] if resolutions else 'Unknown'
        
        # Extract coverage
        if areas:
            area_str = ', '.join(sorted(areas)[:3])
            if len(areas) > 3:
                area_str += f" (+{len(areas)-3} more)"
        else:
            area_str = "Australia"
        
        return f"{area_str} {res} LiDAR/DEM ({org})"
    
    def _generate_source_id(self, path: str) -> str:
        """Generate unique source ID from path"""
        parts = path.rstrip('/').split('/')
        
        # Extract meaningful parts
        org = parts[0].replace('-elvis', '') if parts else 'unknown'
        
        if len(parts) >= 4:
            resolution = parts[2] if 'dem' in parts[2] else parts[3]
            zone = parts[-1] if parts[-1].startswith('z') or parts[-1] in ['ausgeoid', 'quasigeoid'] else ''
            
            base_id = f"{org}_{resolution.replace('-', '_')}"
            if zone:
                base_id += f"_{zone}"
        else:
            base_id = f"{org}_elevation"
        
        return base_id.lower()

def validate_current_sources(scanner: S3BucketScanner, current_sources: Dict) -> Dict:
    """Validate current source configuration against S3 reality"""
    logger.info("Validating current source configuration...")
    
    validation_results = {
        'valid': {},
        'invalid': {},
        'missing_in_config': {},
        'recommendations': []
    }
    
    # Discover all available sources
    discovered = scanner.scan_bucket()
    
    # Check current config
    for source_id, source_config in current_sources.items():
        if 'road-engineering-elevation-data' in source_config.get('path', ''):
            # Extract S3 path
            s3_path = source_config['path'].replace('s3://road-engineering-elevation-data/', '')
            
            # Check if it exists
            try:
                response = scanner.s3.list_objects_v2(
                    Bucket=scanner.bucket,
                    Prefix=s3_path,
                    MaxKeys=1
                )
                exists = 'Contents' in response or 'CommonPrefixes' in response
                
                if exists:
                    validation_results['valid'][source_id] = source_config
                else:
                    validation_results['invalid'][source_id] = source_config
                    validation_results['recommendations'].append(
                        f"Remove invalid source: {source_id} (path not found)"
                    )
                    
            except Exception as e:
                validation_results['invalid'][source_id] = source_config
                validation_results['recommendations'].append(
                    f"Remove errored source: {source_id} ({e})"
                )
    
    # Find missing sources
    for source_id, discovered_source in discovered.items():
        if source_id not in current_sources:
            validation_results['missing_in_config'][source_id] = discovered_source
            validation_results['recommendations'].append(
                f"Add missing source: {source_id} - {discovered_source.description}"
            )
    
    return validation_results

def generate_updated_config(discovered_sources: Dict[str, DemSource]) -> Dict:
    """Generate complete source configuration from discovered sources"""
    config = {}
    
    for source_id, source in discovered_sources.items():
        config[source_id] = {
            "path": source.path,
            "layer": None,
            "crs": source.crs,
            "description": source.description
        }
    
    return config

def main():
    """Main scanner execution"""
    try:
        settings = Settings()
        scanner = S3BucketScanner(settings)
        
        print("S3 DEM Source Discovery Scanner")
        print("=" * 50)
        
        # Scan bucket
        discovered = scanner.scan_bucket()
        
        print(f"\nDiscovery Results:")
        print(f"Found {len(discovered)} DEM sources")
        print(f"Total data: {sum(s.total_size_gb for s in discovered.values()):.1f} GB")
        print(f"Total files: {sum(s.file_count for s in discovered.values()):,}")
        
        print(f"\nDiscovered Sources:")
        for source_id, source in discovered.items():
            print(f"  {source_id}: {source.description}")
            print(f"    Files: {source.file_count:,} ({source.total_size_gb:.1f} GB)")
            print(f"    Areas: {', '.join(sorted(source.geographic_areas))}")
            print(f"    UTM: {', '.join(sorted(source.utm_zones))}")
            print()
        
        # Validate current config
        print(f"\nConfiguration Validation:")
        current_sources = settings.DEM_SOURCES
        validation = validate_current_sources(scanner, current_sources)
        
        print(f"Valid sources: {len(validation['valid'])}")
        print(f"Invalid sources: {len(validation['invalid'])}")
        print(f"Missing sources: {len(validation['missing_in_config'])}")
        
        if validation['recommendations']:
            print(f"\nRecommendations:")
            for rec in validation['recommendations']:
                print(f"  - {rec}")
        
        # Generate complete config
        complete_config = generate_updated_config(discovered)
        
        # Save results
        output_dir = Path(__file__).parent.parent / "config"
        output_dir.mkdir(exist_ok=True)
        
        with open(output_dir / "discovered_sources.json", 'w') as f:
            json.dump({
                "discovered_sources": {k: {
                    "path": v.path,
                    "crs": v.crs,
                    "description": v.description,
                    "file_count": v.file_count,
                    "total_size_gb": round(v.total_size_gb, 2),
                    "geographic_areas": list(v.geographic_areas),
                    "utm_zones": list(v.utm_zones),
                    "resolutions": list(v.resolutions)
                } for k, v in discovered.items()},
                "validation_results": validation,
                "recommended_config": complete_config
            }, f, indent=2)
        
        print(f"\nResults saved to: {output_dir / 'discovered_sources.json'}")
        print("Use this data to update your .env DEM_SOURCES configuration")
        
    except Exception as e:
        logger.error(f"Scanner failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()