import boto3
import json
from typing import Dict, List, Optional
from pydantic import BaseModel
import logging
from pathlib import Path
from datetime import datetime
import re

logger = logging.getLogger(__name__)

class DEMMetadata(BaseModel):
    """Metadata for a DEM source"""
    id: str
    path: str
    bounds: Dict[str, float]  # {north, south, east, west}
    resolution_m: float
    crs: str
    size_mb: float
    description: str
    region: str
    accuracy_m: float
    last_updated: str

class S3SourceManager:
    """Manages S3-based DEM sources with catalog support"""
    
    def __init__(self, bucket_name: str, catalog_path: str = "dem_catalog.json", aws_credentials: Optional[Dict] = None):
        self.bucket_name = bucket_name
        self.catalog_path = catalog_path
        self.aws_credentials = aws_credentials
        self.s3_client = None
        self._catalog_cache = None
        
    def _get_client(self):
        """Lazy load S3 client with appropriate configuration"""
        if not self.s3_client:
            if self.bucket_name == "nz-elevation":
                # NZ Open Data bucket - public access, no signature required
                from botocore import UNSIGNED
                from botocore.config import Config
                self.s3_client = boto3.client(
                    's3',
                    region_name='ap-southeast-2',
                    config=Config(signature_version=UNSIGNED)
                )
            else:
                # Private bucket - requires AWS credentials
                if self.aws_credentials:
                    self.s3_client = boto3.client(
                        's3',
                        aws_access_key_id=self.aws_credentials.get('access_key_id'),
                        aws_secret_access_key=self.aws_credentials.get('secret_access_key'),
                        region_name=self.aws_credentials.get('region', 'ap-southeast-2')
                    )
                else:
                    # Fall back to default credentials
                    self.s3_client = boto3.client('s3')
        return self.s3_client
    
    def get_catalog(self, force_refresh: bool = False) -> Dict[str, DEMMetadata]:
        """Get DEM catalog from S3"""
        if self._catalog_cache and not force_refresh:
            return self._catalog_cache
            
        try:
            # For NZ Open Data, we'll build a catalog programmatically
            if self.bucket_name == "nz-elevation":
                return self._build_nz_catalog()
            
            # For our bucket, fetch the catalog
            response = self._get_client().get_object(
                Bucket=self.bucket_name,
                Key=self.catalog_path
            )
            catalog_data = json.loads(response['Body'].read())
            
            self._catalog_cache = {
                item['id']: DEMMetadata(**item) 
                for item in catalog_data['sources']
            }
            return self._catalog_cache
            
        except Exception as e:
            logger.error(f"Failed to fetch catalog: {e}")
            return {}
    
    def _build_nz_catalog(self) -> Dict[str, DEMMetadata]:
        """Build catalog for NZ Open Data elevation"""
        # Key NZ regions available
        nz_regions = {
            "canterbury_2018": {
                "id": "nz_canterbury_1m",
                "path": "s3://nz-elevation/canterbury/canterbury_2018-2019_DEM_1m.tif",
                "bounds": {"north": -42.7, "south": -44.9, "east": 173.1, "west": 170.1},
                "resolution_m": 1.0,
                "crs": "EPSG:2193",
                "size_mb": 8500,
                "description": "Canterbury region 1m DEM from LiDAR",
                "region": "canterbury",
                "accuracy_m": 0.1,
                "last_updated": "2019-12-01"
            },
            "wellington_2013": {
                "id": "nz_wellington_1m", 
                "path": "s3://nz-elevation/wellington/wellington_2013-2014_DEM_1m.tif",
                "bounds": {"north": -40.6, "south": -41.6, "east": 176.0, "west": 174.6},
                "resolution_m": 1.0,
                "crs": "EPSG:2193",
                "size_mb": 3200,
                "description": "Wellington region 1m DEM from LiDAR",
                "region": "wellington",
                "accuracy_m": 0.1,
                "last_updated": "2014-06-01"
            }
        }
        
        return {k: DEMMetadata(**v) for k, v in nz_regions.items()}
    
    def _build_australia_catalog(self) -> Dict[str, DEMMetadata]:
        """Build dynamic catalog for Australian elevation data"""
        # This will eventually be populated from S3 bucket scanning
        # Initial structure based on expected GA data transfer
        
        australia_regions = {
            # National Coverage
            "au_national_5m": {
                "id": "au_national_5m",
                "path": "s3://road-engineering-elevation-data/australia/national/AU_National_5m_DEM.tif",
                "bounds": {"north": -9.0, "south": -44.0, "east": 155.0, "west": 112.0},
                "resolution_m": 5.0,
                "crs": "EPSG:3577",
                "size_mb": 50000,
                "description": "Australia National 5m DEM - Geoscience Australia",
                "region": "australia",
                "accuracy_m": 2.0,
                "last_updated": "2024-01-01"
            },
            
            # Queensland High-Resolution
            "au_qld_lidar_1m": {
                "id": "au_qld_lidar_1m", 
                "path": "s3://road-engineering-elevation-data/australia/states/qld/AU_QLD_LiDAR_1m.tif",
                "bounds": {"north": -9.0, "south": -29.0, "east": 154.0, "west": 138.0},
                "resolution_m": 1.0,
                "crs": "EPSG:28356",
                "size_mb": 120000,
                "description": "Queensland 1m LiDAR DEM",
                "region": "queensland",
                "accuracy_m": 0.1,
                "last_updated": "2024-01-01"
            },
            
            # NSW Coverage
            "au_nsw_dem_2m": {
                "id": "au_nsw_dem_2m",
                "path": "s3://road-engineering-elevation-data/australia/states/nsw/AU_NSW_DEM_2m.tif", 
                "bounds": {"north": -28.0, "south": -38.0, "east": 154.0, "west": 141.0},
                "resolution_m": 2.0,
                "crs": "EPSG:28356",
                "size_mb": 80000,
                "description": "NSW 2m DEM",
                "region": "new_south_wales",
                "accuracy_m": 0.5,
                "last_updated": "2024-01-01"
            },
            
            # Tasmania High-Resolution (50cm from GA)
            "au_tas_lidar_50cm": {
                "id": "au_tas_lidar_50cm",
                "path": "s3://road-engineering-elevation-data/australia/states/tas/AU_TAS_LiDAR_0.5m.tif",
                "bounds": {"north": -39.0, "south": -44.0, "east": 149.0, "west": 144.0},
                "resolution_m": 0.5,
                "crs": "EPSG:28355",
                "size_mb": 25000,
                "description": "Tasmania 50cm LiDAR DEM - Ultra high resolution",
                "region": "tasmania", 
                "accuracy_m": 0.05,
                "last_updated": "2024-01-01"
            },
            
            # Urban High-Resolution Areas
            "au_sydney_metro_50cm": {
                "id": "au_sydney_metro_50cm",
                "path": "s3://road-engineering-elevation-data/australia/regions/urban/sydney_metro_0.5m.tif",
                "bounds": {"north": -33.5, "south": -34.1, "east": 151.5, "west": 150.5},
                "resolution_m": 0.5,
                "crs": "EPSG:28356",
                "size_mb": 8000,
                "description": "Sydney Metropolitan Area 50cm LiDAR",
                "region": "sydney_metro",
                "accuracy_m": 0.05,
                "last_updated": "2024-01-01"
            },
            
            # Transportation Corridors
            "au_pacific_highway": {
                "id": "au_pacific_highway",
                "path": "s3://road-engineering-elevation-data/australia/regions/corridors/pacific_highway_0.5m.tif",
                "bounds": {"north": -28.0, "south": -34.0, "east": 154.0, "west": 151.0},
                "resolution_m": 0.5,
                "crs": "EPSG:28356", 
                "size_mb": 15000,
                "description": "Pacific Highway Corridor 50cm LiDAR",
                "region": "pacific_highway",
                "accuracy_m": 0.05,
                "last_updated": "2024-01-01"
            }
        }
        
        return {k: DEMMetadata(**v) for k, v in australia_regions.items()}
    
    async def discover_new_datasets(self) -> Dict[str, DEMMetadata]:
        """Dynamically discover new datasets in S3 bucket"""
        try:
            s3_client = self._get_client()
            
            # List all .tif files in the bucket
            paginator = s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(
                Bucket=self.bucket_name,
                Prefix='australia/',
                Delimiter='/'
            )
            
            discovered_datasets = {}
            
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        key = obj['Key']
                        
                        # Skip if not a .tif file
                        if not key.lower().endswith('.tif'):
                            continue
                        
                        # Extract metadata from file path and name
                        dataset_info = self._extract_dataset_info(key, obj)
                        if dataset_info:
                            discovered_datasets[dataset_info['id']] = DEMMetadata(**dataset_info)
            
            logger.info(f"Discovered {len(discovered_datasets)} datasets in S3")
            return discovered_datasets
            
        except Exception as e:
            logger.error(f"Failed to discover new datasets: {e}")
            return {}
    
    def _extract_dataset_info(self, s3_key: str, s3_object: dict) -> Optional[Dict]:
        """Extract dataset information from S3 key and object metadata"""
        try:
            # Parse path: australia/states/qld/AU_QLD_LiDAR_1m.tif
            path_parts = s3_key.split('/')
            filename = path_parts[-1].replace('.tif', '')
            
            # Extract region and resolution from filename patterns
            region_mapping = {
                'QLD': 'queensland',
                'NSW': 'new_south_wales', 
                'TAS': 'tasmania',
                'VIC': 'victoria',
                'SA': 'south_australia',
                'WA': 'western_australia',
                'NT': 'northern_territory'
            }
            
            # Parse resolution from filename (e.g., _1m, _0.5m, _50cm)
            resolution_match = re.search(r'_(\d+(?:\.\d+)?)(m|cm)', filename.lower())
            
            if resolution_match:
                value, unit = resolution_match.groups()
                resolution_m = float(value) if unit == 'm' else float(value) / 100
            else:
                resolution_m = 5.0  # Default fallback
            
            # Determine region from path or filename
            region = 'australia'
            for state_code, region_name in region_mapping.items():
                if state_code in filename.upper():
                    region = region_name
                    break
            
            # Generate bounds based on region (rough estimates - could be improved with GDAL)
            bounds_mapping = {
                'queensland': {"north": -9.0, "south": -29.0, "east": 154.0, "west": 138.0},
                'new_south_wales': {"north": -28.0, "south": -38.0, "east": 154.0, "west": 141.0},
                'tasmania': {"north": -39.0, "south": -44.0, "east": 149.0, "west": 144.0},
                'australia': {"north": -9.0, "south": -44.0, "east": 155.0, "west": 112.0}
            }
            
            return {
                "id": filename.lower().replace('_', '_'),
                "path": f"s3://{self.bucket_name}/{s3_key}",
                "bounds": bounds_mapping.get(region, bounds_mapping['australia']),
                "resolution_m": resolution_m,
                "crs": self._infer_crs_from_region(region),
                "size_mb": round(s3_object['Size'] / (1024 * 1024), 2),
                "description": f"Auto-discovered {region} DEM ({resolution_m}m resolution)",
                "region": region,
                "accuracy_m": min(resolution_m * 0.1, 2.0),  # Rough accuracy estimate
                "last_updated": s3_object['LastModified'].isoformat()
            }
            
        except Exception as e:
            logger.warning(f"Failed to extract info from {s3_key}: {e}")
            return None
    
    def _infer_crs_from_region(self, region: str) -> str:
        """Infer CRS from Australian region"""
        crs_mapping = {
            'queensland': 'EPSG:28356',
            'new_south_wales': 'EPSG:28356',
            'tasmania': 'EPSG:28355',
            'victoria': 'EPSG:28355',
            'south_australia': 'EPSG:28354',
            'western_australia': 'EPSG:28350',
            'northern_territory': 'EPSG:28352',
            'australia': 'EPSG:3577'  # National GDA2020
        }
        return crs_mapping.get(region, 'EPSG:3577')
    
    async def update_catalog_with_discoveries(self) -> bool:
        """Update catalog with newly discovered datasets"""
        try:
            # Get existing catalog
            existing_catalog = self.get_catalog()
            
            # Discover new datasets
            new_datasets = await self.discover_new_datasets()
            
            # Merge catalogs (new datasets take precedence)
            updated_catalog = {**existing_catalog, **new_datasets}
            
            # Save updated catalog back to S3
            catalog_data = {
                "version": "1.0",
                "last_updated": datetime.now().isoformat(),
                "source_count": len(updated_catalog),
                "sources": [dataset.dict() for dataset in updated_catalog.values()]
            }
            
            # Upload updated catalog
            s3_client = self._get_client()
            s3_client.put_object(
                Bucket=self.bucket_name,
                Key='catalog/australia_dem_catalog.json',
                Body=json.dumps(catalog_data, indent=2),
                ContentType='application/json'
            )
            
            logger.info(f"Updated catalog with {len(updated_catalog)} datasets")
            self._catalog_cache = updated_catalog
            return True
            
        except Exception as e:
            logger.error(f"Failed to update catalog: {e}")
            return False
    
    def find_best_source(self, lat: float, lon: float) -> Optional[str]:
        """Find best DEM source for given coordinates"""
        catalog = self.get_catalog()
        
        candidates = []
        for source_id, metadata in catalog.items():
            bounds = metadata.bounds
            if (bounds['south'] <= lat <= bounds['north'] and 
                bounds['west'] <= lon <= bounds['east']):
                
                # Score based on resolution, accuracy, and region specificity
                resolution_score = 1.0 / metadata.resolution_m  # Higher is better
                accuracy_score = 1.0 / metadata.accuracy_m     # Higher is better
                
                # Prefer more specific regions over national coverage
                region_specificity = {
                    'sydney_metro': 10,
                    'pacific_highway': 9,
                    'queensland': 5,
                    'new_south_wales': 5,
                    'tasmania': 5,
                    'australia': 1
                }.get(metadata.region, 3)
                
                total_score = resolution_score * accuracy_score * region_specificity
                candidates.append((source_id, total_score, metadata.resolution_m))
        
        # Return highest scoring source
        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            return candidates[0][0]
        
        return None