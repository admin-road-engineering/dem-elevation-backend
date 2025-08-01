#!/usr/bin/env python3
"""
NZ Elevation Incremental Spatial Index Generator
Detects NEW files added to NZ S3 bucket since last index generation
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

class NZIncrementalSpatialIndexGenerator:
    """
    Generates incremental updates to NZ elevation spatial index
    Only processes NEW files added since last index generation
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
    
    def load_existing_index(self) -> Optional[Dict]:
        """Load existing NZ spatial index"""
        if self.spatial_index_file.exists():
            try:
                with open(self.spatial_index_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading existing NZ spatial index: {e}")
        return None
    
    def get_processed_files(self, spatial_index: Dict) -> Set[str]:
        """Extract all file keys from existing spatial index"""
        processed_files = set()
        
        for region_data in spatial_index.get("regions", {}).values():
            for survey_data in region_data.get("surveys", {}).values():
                for file_info in survey_data.get("files", []):
                    s3_path = file_info.get("file", "")
                    if s3_path.startswith("s3://nz-elevation/"):
                        # Extract key from s3:// path
                        key = s3_path.replace("s3://nz-elevation/", "")
                        processed_files.add(key)
        
        return processed_files
    
    def get_last_update_timestamp(self, spatial_index: Dict) -> datetime:
        """Get timestamp of last index update"""
        timestamp_str = spatial_index.get("generated_at", "2024-01-01T00:00:00")
        try:
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except:
            return datetime(2024, 1, 1)
    
    def find_new_files(self, existing_index: Optional[Dict] = None) -> List[Dict]:
        """Find new .tiff files added since last index update"""
        
        if existing_index:
            processed_files = self.get_processed_files(existing_index)
            last_update = self.get_last_update_timestamp(existing_index)
            logger.info(f"Looking for files added after {last_update}")
            logger.info(f"Already processed {len(processed_files)} files")
        else:
            processed_files = set()
            last_update = datetime(2024, 1, 1)
            logger.info("No existing index found - will process all files")
        
        new_files = []
        
        try:
            # Use paginator to handle large buckets
            paginator = self.s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(Bucket="nz-elevation")
            
            logger.info("Scanning NZ elevation bucket for new .tiff files...")
            total_objects = 0
            new_files_found = 0
            
            for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        key = obj['Key']
                        total_objects += 1
                        
                        # Only process .tiff files
                        if key.lower().endswith('.tiff'):
                            # Check if this is a new file
                            if key not in processed_files:
                                # Check if modified after last update
                                last_modified = obj['LastModified']
                                if last_modified.replace(tzinfo=None) > last_update.replace(tzinfo=None):
                                    new_files.append({
                                        "key": key,
                                        "s3_path": f"s3://nz-elevation/{key}",
                                        "filename": key.split('/')[-1],
                                        "size": obj['Size'],
                                        "last_modified": last_modified.isoformat()
                                    })
                                    new_files_found += 1
                                    
                                    if new_files_found % 50 == 0:
                                        logger.info(f"   🔍 Found {new_files_found} new files so far...")
            
            logger.info(f"✅ Scan complete: {total_objects} total objects, {new_files_found} new .tiff files")
            
        except Exception as e:
            logger.error(f"❌ Error scanning for new files: {e}")
            raise
            
        return new_files
    
    def process_new_files(self, new_files: List[Dict], existing_index: Optional[Dict] = None) -> Dict:
        """Process new files and update spatial index"""
        
        if existing_index:
            spatial_index = existing_index.copy()
            logger.info(f"Updating existing index with {len(new_files)} new files")
        else:
            # Create new index structure
            spatial_index = {
                "generated_at": datetime.now().isoformat(),
                "bucket": "nz-elevation",
                "coordinate_system": "NZGD2000 / New Zealand Transverse Mercator 2000 (EPSG:2193)",
                "method": "incremental_dynamic_s3_scan_with_actual_bounds",
                "regions": {},
                "file_count": 0,
                "coverage_summary": {}
            }
            logger.info(f"Creating new index with {len(new_files)} files")
        
        # Process each new file
        processed_count = 0
        for file_info in new_files:
            # Extract region and survey from path
            path_parts = file_info["key"].split('/')
            if len(path_parts) >= 2:
                region_name = path_parts[0]
                survey_name = path_parts[1] if len(path_parts) > 1 else "default_survey"
            else:
                region_name = "unknown"
                survey_name = "default_survey"
            
            # Ensure region exists in index
            if region_name not in spatial_index["regions"]:
                spatial_index["regions"][region_name] = {
                    "surveys": {},
                    "file_count": 0,
                    "coverage_bounds": None
                }
            
            # Ensure survey exists in region
            if survey_name not in spatial_index["regions"][region_name]["surveys"]:
                spatial_index["regions"][region_name]["surveys"][survey_name] = {
                    "files": [],
                    "file_count": 0,
                    "coverage_bounds": None
                }
            
            # Extract actual bounds from GeoTIFF file
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
                    "method": "actual_geotiff_bounds_incremental"
                }
                
                spatial_index["regions"][region_name]["surveys"][survey_name]["files"].append(file_entry)
                spatial_index["file_count"] += 1
                processed_count += 1
                
                if processed_count % 50 == 0:
                    logger.info(f"   ✅ Processed {processed_count} new files with actual bounds...")
                    
            else:
                logger.warning(f"   ❌ Could not extract bounds from: {file_info['filename']}")
        
        # Update generated timestamp
        spatial_index["generated_at"] = datetime.now().isoformat()
        
        # Recalculate coverage bounds for affected regions/surveys
        self._recalculate_coverage_bounds(spatial_index)
        
        # Generate updated coverage summary
        spatial_index["coverage_summary"] = self._generate_coverage_summary(spatial_index)
        
        logger.info(f"✅ Processed {processed_count} new files successfully!")
        return spatial_index
    
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
                
                # Transform bounds to WGS84 for lat/lon storage
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
    
    def _recalculate_coverage_bounds(self, spatial_index: Dict):
        """Recalculate coverage bounds for regions and surveys"""
        for region_name, region_data in spatial_index["regions"].items():
            # Recalculate survey bounds
            for survey_name, survey_data in region_data["surveys"].items():
                if survey_data["files"]:
                    survey_data["coverage_bounds"] = self._calculate_coverage_bounds(survey_data["files"])
                    survey_data["file_count"] = len(survey_data["files"])
            
            # Recalculate region bounds
            all_region_files = []
            for survey_data in region_data["surveys"].values():
                all_region_files.extend(survey_data["files"])
            
            if all_region_files:
                region_data["coverage_bounds"] = self._calculate_coverage_bounds(all_region_files)
                region_data["file_count"] = len(all_region_files)
    
    def _calculate_coverage_bounds(self, files: List[Dict]) -> Optional[Dict]:
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
    
    def save_spatial_index(self, spatial_index: Dict):
        """Save spatial index to file"""
        with open(self.spatial_index_file, 'w') as f:
            json.dump(spatial_index, f, indent=2)
    
    def run_incremental_update(self):
        """Run incremental update process"""
        logger.info("🔄 Starting NZ elevation spatial index incremental update...")
        
        # Load existing index
        existing_index = self.load_existing_index()
        
        # Find new files
        new_files = self.find_new_files(existing_index)
        
        if not new_files:
            logger.info("✅ No new files found - index is up to date!")
            return existing_index
        
        # Process new files
        updated_index = self.process_new_files(new_files, existing_index)
        
        # Save updated index
        self.save_spatial_index(updated_index)
        
        logger.info(f"✅ NZ elevation spatial index updated successfully!")
        logger.info(f"   Total files: {updated_index['file_count']}")
        logger.info(f"   New files added: {len(new_files)}")
        logger.info(f"   Regions: {list(updated_index['regions'].keys())}")
        logger.info(f"   Saved to: {self.spatial_index_file}")
        
        return updated_index

def main():
    """Main function"""
    generator = NZIncrementalSpatialIndexGenerator()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "update":
            generator.run_incremental_update()
        elif command == "show":
            existing_index = generator.load_existing_index()
            if existing_index:
                print(json.dumps(existing_index.get("coverage_summary", {}), indent=2))
            else:
                print("No NZ spatial index found")
        else:
            print("Unknown command. Use: update or show")
    else:
        print("[INCREMENTAL NZ] NZ Elevation Incremental Spatial Index Generator")
        print("Detects and processes only NEW files added since last index update")
        print("Commands:")
        print("  update - Update index with new files")
        print("  show   - Show coverage summary")
        print()
        print("Example: python scripts/generate_nz_incremental_index.py update")

if __name__ == "__main__":
    main()