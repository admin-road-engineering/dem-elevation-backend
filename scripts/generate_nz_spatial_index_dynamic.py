#!/usr/bin/env python3
"""
Dynamic NZ Elevation Spatial Index Generator - No Hardcoded Mappings
Uses the same approach as Australian bucket: discover all files dynamically and extract actual bounds
"""
import json
import sys
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional
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

class DynamicNZSpatialIndexGenerator:
    """
    Generates spatial index for NZ elevation data using the same dynamic approach as Australian bucket
    No hardcoded mappings - discovers all files and extracts actual bounds from GeoTIFF metadata
    """
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.config_dir = self.project_root / "config"
        self.config_dir.mkdir(exist_ok=True)
        self.spatial_index_file = self.config_dir / "nz_spatial_index_dynamic.json"
        
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
        """Generate complete spatial index using dynamic discovery like Australian bucket"""
        
        logger.info("🗺️ [DYNAMIC NZ] Generating NZ elevation spatial index from S3 bucket scan...")
        
        try:
            bucket_name = "nz-elevation"
            
            # Initialize spatial index structure
            spatial_index = {
                "generated_at": datetime.now().isoformat(),
                "bucket": bucket_name,
                "coordinate_system": "NZGD2000 / New Zealand Transverse Mercator 2000 (EPSG:2193)",
                "method": "dynamic_s3_scan_with_actual_bounds",
                "regions": {},
                "file_count": 0,
                "coverage_summary": {}
            }
            
            # Step 1: Auto-discover ALL directories containing .tiff files (like Australian bucket)
            logger.info("🔍 Auto-discovering all directories with .tiff files...")
            directories_to_scan = self._discover_all_tiff_directories(bucket_name)
            
            logger.info(f"📁 Found {len(directories_to_scan)} directories with .tiff files:")
            for directory in sorted(directories_to_scan)[:10]:  # Show first 10
                logger.info(f"   📂 {directory}")
            if len(directories_to_scan) > 10:
                logger.info(f"   ... and {len(directories_to_scan) - 10} more")
            
            # Step 2: Process each directory
            processed_files = 0
            for directory in sorted(directories_to_scan):
                logger.info(f"Scanning directory: {directory}")
                
                # Extract region from directory path
                region_name = self._extract_region_from_path(directory)
                if region_name not in spatial_index["regions"]:
                    spatial_index["regions"][region_name] = {
                        "surveys": {},
                        "file_count": 0,
                        "coverage_bounds": None
                    }
                
                # Extract survey from directory path
                survey_name = self._extract_survey_from_path(directory)
                if survey_name not in spatial_index["regions"][region_name]["surveys"]:
                    spatial_index["regions"][region_name]["surveys"][survey_name] = {
                        "files": [],
                        "file_count": 0,
                        "coverage_bounds": None
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
                            "region": region_name,
                            "survey": survey_name,
                            "coordinate_system": "EPSG:2193",
                            "method": "actual_geotiff_bounds"
                        }
                        
                        spatial_index["regions"][region_name]["surveys"][survey_name]["files"].append(file_entry)
                        spatial_index["file_count"] += 1
                        processed_files += 1
                        
                        if processed_files % 100 == 0:
                            logger.info(f"   ✅ Processed {processed_files} files with actual bounds...")
                        
                    else:
                        logger.warning(f"   ❌ Could not extract bounds from: {file_info['filename']}")
                
                # Calculate coverage bounds for survey
                survey_data = spatial_index["regions"][region_name]["surveys"][survey_name]
                if survey_data["files"]:
                    survey_data["coverage_bounds"] = self._calculate_coverage_bounds(survey_data["files"])
                    survey_data["file_count"] = len(survey_data["files"])
            
            # Calculate coverage bounds for each region
            for region_name, region_data in spatial_index["regions"].items():
                all_region_files = []
                for survey_data in region_data["surveys"].values():
                    all_region_files.extend(survey_data["files"])
                
                if all_region_files:
                    region_data["coverage_bounds"] = self._calculate_coverage_bounds(all_region_files)
                    region_data["file_count"] = len(all_region_files)
            
            # Generate coverage summary
            spatial_index["coverage_summary"] = self._generate_coverage_summary(spatial_index)
            
            # Save spatial index
            self._save_spatial_index(spatial_index)
            
            logger.info(f"✅ Dynamic NZ elevation spatial index generated successfully!")
            logger.info(f"   Total files processed: {spatial_index['file_count']}")
            logger.info(f"   Regions: {list(spatial_index['regions'].keys())}")
            logger.info(f"   Saved to: {self.spatial_index_file}")
            
            return spatial_index
            
        except Exception as e:
            logger.error(f"❌ Error generating dynamic NZ elevation spatial index: {e}")
            raise
    
    def _discover_all_tiff_directories(self, bucket_name: str) -> List[str]:
        """Discover all directories in the NZ bucket that contain .tiff files (like Australian method)"""
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
                            
                            # Log progress every 500 discoveries
                            if len(directories_with_tiffs) % 100 == 0:
                                logger.info(f"   🔍 Found {len(directories_with_tiffs)} directories with .tiff files (scanned {total_objects} objects)...")
            
            logger.info(f"   ✅ Scan complete: {total_objects} total objects, {len(directories_with_tiffs)} directories with .tiff files")
            
        except Exception as e:
            logger.error(f"❌ Error discovering directories: {e}")
            raise
            
        return sorted(list(directories_with_tiffs))
    
    def _extract_region_from_path(self, directory_path: str) -> str:
        """Extract region name from directory path"""
        parts = directory_path.strip('/').split('/')
        if len(parts) > 0:
            return parts[0]
        return "unknown"
    
    def _extract_survey_from_path(self, directory_path: str) -> str:
        """Extract survey name from directory path"""
        parts = directory_path.strip('/').split('/')
        if len(parts) > 1:
            return parts[1]
        return "default_survey"
    
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
        """Extract actual bounds from GeoTIFF file using rasterio (like Australian method but with S3)"""
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
            "regions": {},
            "key_locations": {}
        }
        
        # Region summaries
        for region, region_data in spatial_index["regions"].items():
            summary["regions"][region] = {
                "file_count": region_data["file_count"],
                "survey_count": len(region_data["surveys"]),
                "coverage_bounds": region_data["coverage_bounds"]
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
                "files": [f["filename"] for f in matching_files[:3]]  # First 3 files
            }
        
        return summary
    
    def _find_files_for_coordinate(self, spatial_index: Dict, lat: float, lon: float) -> List[Dict]:
        """Find files that contain the given coordinate using actual bounds"""
        matching_files = []
        
        for region, region_data in spatial_index["regions"].items():
            for survey, survey_data in region_data["surveys"].items():
                for file_info in survey_data["files"]:
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
                logger.warning(f"Error loading dynamic NZ spatial index: {e}")
        return None

def main():
    """Main function"""
    generator = DynamicNZSpatialIndexGenerator()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "generate":
            generator.generate_complete_index()
        elif command == "show":
            index = generator.load_spatial_index()
            if index:
                print(json.dumps(index.get("coverage_summary", {}), indent=2))
            else:
                print("No dynamic NZ spatial index found")
        else:
            print("Unknown command. Use: generate or show")
    else:
        print("[DYNAMIC NZ] Dynamic NZ Elevation Spatial Index Generator")
        print("Uses same approach as Australian bucket: scan entire bucket and extract actual GeoTIFF bounds")
        print("Commands:")
        print("  generate - Generate spatial index by scanning entire NZ S3 bucket")
        print("  show     - Show coverage summary")
        print()
        print("Example: python scripts/generate_nz_spatial_index_dynamic.py generate")

if __name__ == "__main__":
    main()