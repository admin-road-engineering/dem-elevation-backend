#!/usr/bin/env python3
"""
NZ Elevation Campaign-Based Spatial Index Generator
Groups NZ files by survey campaigns (similar to Australian approach) rather than regions
"""
import json
import sys
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Set
from datetime import datetime
import boto3
from botocore import UNSIGNED
from botocore.config import Config
import rasterio
from rasterio.warp import transform_bounds

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NZCampaignSpatialIndexGenerator:
    """
    Generates NZ elevation spatial index grouped by survey campaigns (similar to Australian approach)
    """
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.config_dir = self.project_root / "config"
        self.config_dir.mkdir(exist_ok=True)
        self.spatial_index_file = self.config_dir / "nz_spatial_index.json"
        
        # S3 client for unsigned access to public NZ bucket
        self.s3_client = boto3.client(
            's3',
            region_name='ap-southeast-2',
            config=Config(signature_version=UNSIGNED)
        )
        
        # Configure GDAL for S3 access
        os.environ['AWS_NO_SIGN_REQUEST'] = 'YES'
        os.environ['GDAL_DISABLE_READDIR_ON_OPEN'] = 'EMPTY_DIR'
    
    def generate_complete_index(self) -> Dict:
        """Generate complete spatial index using campaign-based grouping like Australian approach"""
        
        logger.info("🗺️ [NZ CAMPAIGNS] Generating NZ elevation spatial index grouped by campaigns...")
        
        try:
            bucket_name = "nz-elevation"
            
            # Initialize spatial index structure (similar to Australian approach)
            spatial_index = {
                "generated_at": datetime.now().isoformat(),
                "bucket": bucket_name,
                "coordinate_system": "NZGD2000 / New Zealand Transverse Mercator 2000 (EPSG:2193)",
                "method": "campaign_based_grouping_with_actual_bounds",
                "campaigns": {},  # Similar to Australian "utm_zones"
                "file_count": 0,
                "coverage_summary": {}
            }
            
            # Step 1: Auto-discover ALL directories containing .tiff files
            logger.info("🔍 Auto-discovering all directories with .tiff files...")
            directories_to_scan = self._discover_all_tiff_directories(bucket_name)
            
            logger.info(f"📁 Found {len(directories_to_scan)} directories with .tiff files")
            
            # Step 2: Process each directory and group by campaign
            processed_files = 0
            for directory in sorted(directories_to_scan):
                logger.info(f"Scanning directory: {directory}")
                
                # Extract campaign name from directory path
                campaign_name = self._extract_campaign_from_path(directory)
                if campaign_name not in spatial_index["campaigns"]:
                    spatial_index["campaigns"][campaign_name] = {
                        "files": [],
                        "coverage_bounds": None,
                        "file_count": 0,
                        "region": self._extract_region_from_path(directory),
                        "data_type": self._extract_data_type_from_path(directory)  # DEM vs DSM
                    }
                
                # Step 3: Scan directory for .tiff files
                files_found = self._scan_s3_directory(bucket_name, directory)
                logger.info(f"   Found {len(files_found)} .tiff files in {directory}")
                
                # Step 4: Extract actual bounds from each GeoTIFF file
                for file_info in files_found:
                    bounds = self._extract_actual_bounds_from_geotiff(file_info['s3_path'])
                    
                    if bounds:
                        file_entry = {
                            "file": file_info['s3_path'],
                            "filename": file_info["filename"],
                            "bounds": bounds,
                            "size_mb": round(file_info["size"] / 1024 / 1024, 2),
                            "last_modified": file_info["last_modified"],
                            "resolution": "1m",  # NZ elevation data is 1m resolution
                            "campaign": campaign_name,
                            "region": spatial_index["campaigns"][campaign_name]["region"],
                            "data_type": spatial_index["campaigns"][campaign_name]["data_type"],
                            "coordinate_system": "EPSG:2193",
                            "method": "actual_geotiff_bounds"
                        }
                        
                        spatial_index["campaigns"][campaign_name]["files"].append(file_entry)
                        spatial_index["file_count"] += 1
                        processed_files += 1
                        
                        if processed_files % 100 == 0:
                            logger.info(f"   ✅ Processed {processed_files} files with actual bounds...")
                        
                    else:
                        logger.warning(f"   ❌ Could not extract bounds from: {file_info['filename']}")
            
            # Calculate coverage bounds for each campaign
            for campaign_name, campaign_data in spatial_index["campaigns"].items():
                if campaign_data["files"]:
                    campaign_data["coverage_bounds"] = self._calculate_coverage_bounds(campaign_data["files"])
                    campaign_data["file_count"] = len(campaign_data["files"])
            
            # Generate coverage summary
            spatial_index["coverage_summary"] = self._generate_coverage_summary(spatial_index)
            
            # Save spatial index
            self._save_spatial_index(spatial_index)
            
            logger.info(f"✅ NZ elevation campaign-based spatial index generated successfully!")
            logger.info(f"   Total files processed: {spatial_index['file_count']}")
            logger.info(f"   Campaigns: {list(spatial_index['campaigns'].keys())}")
            logger.info(f"   Saved to: {self.spatial_index_file}")
            
            return spatial_index
            
        except Exception as e:
            logger.error(f"❌ Error generating NZ campaign-based spatial index: {e}")
            raise
    
    def _discover_all_tiff_directories(self, bucket_name: str) -> List[str]:
        """Discover all directories in the NZ bucket that contain .tiff files"""
        directories_with_tiffs = set()
        
        try:
            # Use paginator to handle large buckets
            paginator = self.s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(Bucket=bucket_name)
            
            logger.info("   Scanning entire NZ bucket for .tiff files...")
            total_objects = 0
            
            for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        key = obj['Key']
                        total_objects += 1
                        
                        # Check if this is a .tiff file
                        if key.lower().endswith('.tiff'):
                            # Extract directory path
                            directory = '/'.join(key.split('/')[:-1]) + '/'
                            directories_with_tiffs.add(directory)
                            
                            # Log progress every 100 discoveries
                            if len(directories_with_tiffs) % 50 == 0:
                                logger.info(f"   🔍 Found {len(directories_with_tiffs)} directories with .tiff files (scanned {total_objects} objects)...")
            
            logger.info(f"   ✅ Scan complete: {total_objects} total objects, {len(directories_with_tiffs)} directories with .tiff files")
            
        except Exception as e:
            logger.error(f"❌ Error discovering directories: {e}")
            raise
            
        return sorted(list(directories_with_tiffs))
    
    def _extract_campaign_from_path(self, directory_path: str) -> str:
        """
        Extract campaign name from directory path - this is the key grouping similar to Australian approach
        
        Examples:
        - auckland/auckland-north_2016-2018/dem_1m/2193/ → auckland-north_2016-2018_dem
        - wellington/wellington-city_2021/dsm_1m/2193/ → wellington-city_2021_dsm
        """
        parts = directory_path.strip('/').split('/')
        
        if len(parts) >= 3:
            region = parts[0]
            survey = parts[1]
            data_type = parts[2]  # dem_1m or dsm_1m
            
            # Create campaign name: survey + data type
            campaign_name = f"{survey}_{data_type}"
            return campaign_name
        elif len(parts) >= 2:
            # Fallback for simpler structures
            return f"{parts[0]}_{parts[1]}"
        else:
            return "unknown_campaign"
    
    def _extract_region_from_path(self, directory_path: str) -> str:
        """Extract region name from directory path"""
        parts = directory_path.strip('/').split('/')
        if len(parts) > 0:
            return parts[0]
        return "unknown"
    
    def _extract_data_type_from_path(self, directory_path: str) -> str:
        """Extract data type (DEM vs DSM) from directory path"""
        if "dem_1m" in directory_path:
            return "DEM"
        elif "dsm_1m" in directory_path:
            return "DSM" 
        else:
            return "unknown"
    
    def _scan_s3_directory(self, bucket_name: str, directory: str) -> List[Dict]:
        """Scan a specific S3 directory for .tiff files"""
        files_found = []
        
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(
                Bucket=bucket_name,
                Prefix=directory
            )
            
            for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        key = obj['Key']
                        
                        # Only process .tiff files
                        if key.lower().endswith('.tiff'):
                            filename = key.split('/')[-1]
                            
                            files_found.append({
                                "s3_path": f"s3://{bucket_name}/{key}",
                                "key": key,
                                "filename": filename,
                                "size": obj['Size'],
                                "last_modified": obj['LastModified'].isoformat()
                            })
                            
        except Exception as e:
            logger.warning(f"Error scanning directory {directory}: {e}")
        
        return files_found
    
    def _extract_actual_bounds_from_geotiff(self, s3_path: str) -> Optional[Dict]:
        """Extract actual bounds from GeoTIFF file using rasterio"""
        try:
            # Create VSI path for direct S3 access
            if s3_path.startswith("s3://"):
                vsi_path = f"/vsis3/{s3_path[5:]}"
            else:
                vsi_path = f"/vsis3/nz-elevation/{s3_path}"
            
            # Open with rasterio and extract bounds
            with rasterio.open(vsi_path) as dataset:
                # Get bounds in the dataset's CRS (should be EPSG:2193 for NZ)
                bounds_2193 = dataset.bounds
                
                # Transform bounds to WGS84 for lat/lon storage (consistent with Australian method)
                bounds_4326 = transform_bounds(
                    dataset.crs, 
                    'EPSG:4326', 
                    bounds_2193.left, 
                    bounds_2193.bottom, 
                    bounds_2193.right, 
                    bounds_2193.top
                )
                
                return {
                    "min_lat": bounds_4326[1],  # bottom
                    "max_lat": bounds_4326[3],  # top
                    "min_lon": bounds_4326[0],  # left
                    "max_lon": bounds_4326[2],  # right
                    "nztm_bounds": {
                        "left": bounds_2193.left,
                        "bottom": bounds_2193.bottom,
                        "right": bounds_2193.right,
                        "top": bounds_2193.top
                    }
                }
                
        except Exception as e:
            logger.warning(f"Failed to extract bounds from {s3_path}: {e}")
            return None
    
    def _calculate_coverage_bounds(self, files: List[Dict]) -> Dict:
        """Calculate overall coverage bounds for a set of files"""
        if not files:
            return None
        
        valid_files = [f for f in files if f.get("bounds")]
        if not valid_files:
            return None
        
        min_lat = min(f["bounds"]["min_lat"] for f in valid_files)
        max_lat = max(f["bounds"]["max_lat"] for f in valid_files)
        min_lon = min(f["bounds"]["min_lon"] for f in valid_files)
        max_lon = max(f["bounds"]["max_lon"] for f in valid_files)
        
        return {
            "min_lat": min_lat,
            "max_lat": max_lat,
            "min_lon": min_lon,
            "max_lon": max_lon
        }
    
    def _generate_coverage_summary(self, spatial_index: Dict) -> Dict:
        """Generate coverage summary for the index"""
        summary = {
            "total_files": spatial_index["file_count"],
            "campaigns": {},
            "regions": {},
            "data_types": {"DEM": 0, "DSM": 0},
            "key_locations": {}
        }
        
        # Campaign summaries (similar to Australian zone summaries)
        for campaign, campaign_data in spatial_index["campaigns"].items():
            summary["campaigns"][campaign] = {
                "file_count": campaign_data["file_count"],
                "region": campaign_data["region"],
                "data_type": campaign_data["data_type"],
                "coverage_bounds": campaign_data["coverage_bounds"]
            }
            
            # Count data types
            data_type = campaign_data["data_type"]
            if data_type in summary["data_types"]:
                summary["data_types"][data_type] += campaign_data["file_count"]
        
        # Region rollup summaries
        region_files = {}
        for campaign, campaign_data in spatial_index["campaigns"].items():
            region = campaign_data["region"]
            if region not in region_files:
                region_files[region] = []
            region_files[region].extend(campaign_data["files"])
        
        for region, files in region_files.items():
            summary["regions"][region] = {
                "file_count": len(files),
                "campaign_count": len([c for c in spatial_index["campaigns"].values() if c["region"] == region]),
                "coverage_bounds": self._calculate_coverage_bounds(files)
            }
        
        # Test key locations with actual bounds
        test_locations = {
            "auckland": (-36.8485, 174.7633),
            "wellington": (-41.2865, 174.7762),
            "christchurch": (-43.5321, 172.6362),
            "dunedin": (-45.8788, 170.5028),
            "queenstown": (-45.0312, 168.6626)
        }
        
        for location, (lat, lon) in test_locations.items():
            matching_files = self._find_files_for_coordinate(spatial_index, lat, lon)
            summary["key_locations"][location] = {
                "coordinates": [lat, lon],
                "matching_files": len(matching_files),
                "files": [f["filename"] for f in matching_files[:3]],  # First 3 files
                "campaigns": list(set(f["campaign"] for f in matching_files[:3]))
            }
        
        return summary
    
    def _find_files_for_coordinate(self, spatial_index: Dict, lat: float, lon: float) -> List[Dict]:
        """Find files that contain the given coordinate using actual bounds"""
        matching_files = []
        
        for campaign, campaign_data in spatial_index["campaigns"].items():
            for file_info in campaign_data["files"]:
                if not file_info.get("bounds"):
                    continue
                    
                bounds = file_info["bounds"]
                if (bounds["min_lat"] <= lat <= bounds["max_lat"] and
                    bounds["min_lon"] <= lon <= bounds["max_lon"]):
                    matching_files.append(file_info)
        
        return matching_files
    
    def _save_spatial_index(self, spatial_index: Dict):
        """Save spatial index to file"""
        with open(self.spatial_index_file, 'w') as f:
            json.dump(spatial_index, f, indent=2)
    
    def load_spatial_index(self) -> Optional[Dict]:
        """Load existing spatial index"""
        if self.spatial_index_file.exists():
            try:
                with open(self.spatial_index_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading NZ campaign spatial index: {e}")
        return None

def main():
    """Main function"""
    generator = NZCampaignSpatialIndexGenerator()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "generate":
            generator.generate_complete_index()
        elif command == "show":
            index = generator.load_spatial_index()
            if index:
                print(json.dumps(index.get("coverage_summary", {}), indent=2))
            else:
                print("No NZ campaign spatial index found")
        else:
            print("Unknown command. Use: generate or show")
    else:
        print("[NZ CAMPAIGNS] NZ Elevation Campaign-Based Spatial Index Generator")
        print("Groups files by survey campaigns (similar to Australian approach)")
        print("Commands:")
        print("  generate - Generate spatial index grouped by campaigns")
        print("  show     - Show coverage summary")
        print()
        print("Example: python scripts/generate_nz_campaign_index.py generate")

if __name__ == "__main__":
    main()