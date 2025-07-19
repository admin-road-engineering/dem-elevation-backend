#!/usr/bin/env python3
"""
Comprehensive Spatial Index Generator for S3 Multi-File DEM Access
Dynamically discovers and scans ALL directories in S3 bucket for .tif files
"""
import json
import sys
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ComprehensiveSpatialIndexGenerator:
    """
    Generates spatial index by dynamically discovering ALL directories in S3 bucket
    """
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.config_dir = self.project_root / "config"
        self.config_dir.mkdir(exist_ok=True)
        self.spatial_index_file = self.config_dir / "spatial_index.json"
        
    def generate_complete_index(self) -> Dict:
        """Generate complete spatial index by scanning entire S3 bucket"""
        
        logger.info("🗺️ Starting comprehensive spatial index generation...")
        logger.info("📡 This will scan the ENTIRE S3 bucket for all .tif files")
        
        try:
            from config import Settings
            
            settings = Settings()
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_DEFAULT_REGION
            )
            
            # Initialize spatial index structure
            spatial_index = {
                "generated_at": datetime.now().isoformat(),
                "bucket": settings.AWS_S3_BUCKET_NAME,
                "utm_zones": {},
                "file_count": 0,
                "coverage_summary": {},
                "directories_scanned": []
            }
            
            # Step 1: Discover ALL directories containing .tif files
            logger.info("🔍 Discovering all directories with .tif files...")
            directories_with_tifs = self._discover_all_tif_directories(s3_client, settings.AWS_S3_BUCKET_NAME)
            
            logger.info(f"📁 Found {len(directories_with_tifs)} directories with .tif files:")
            for directory in sorted(directories_with_tifs):
                logger.info(f"   📂 {directory}")
            
            spatial_index["directories_scanned"] = sorted(directories_with_tifs)
            
            # Step 2: Process each directory
            for directory in sorted(directories_with_tifs):
                logger.info(f"🗂️ Processing directory: {directory}")
                
                # Extract UTM zone from directory path
                utm_zone = self._extract_utm_zone(directory)
                if utm_zone not in spatial_index["utm_zones"]:
                    spatial_index["utm_zones"][utm_zone] = {
                        "files": [],
                        "coverage_bounds": None,
                        "file_count": 0,
                        "directories": []
                    }
                
                if directory not in spatial_index["utm_zones"][utm_zone]["directories"]:
                    spatial_index["utm_zones"][utm_zone]["directories"].append(directory)
                
                # Scan directory for .tif files
                files_found = self._scan_s3_directory_comprehensive(s3_client, settings.AWS_S3_BUCKET_NAME, directory)
                
                files_added_this_dir = 0
                for file_info in files_found:
                    # Extract bounds from filename
                    bounds = self._extract_bounds_from_filename(file_info["filename"])
                    
                    if bounds:
                        file_entry = {
                            "file": f"s3://{settings.AWS_S3_BUCKET_NAME}/{file_info['key']}",
                            "filename": file_info["filename"],
                            "bounds": bounds,
                            "size_mb": round(file_info["size"] / 1024 / 1024, 2),
                            "last_modified": file_info["last_modified"],
                            "resolution": self._extract_resolution(file_info["filename"]),
                            "utm_zone": utm_zone,
                            "directory": directory
                        }
                        
                        spatial_index["utm_zones"][utm_zone]["files"].append(file_entry)
                        spatial_index["file_count"] += 1
                        files_added_this_dir += 1
                        
                        # Log every 1000 files to show progress
                        if spatial_index["file_count"] % 1000 == 0:
                            logger.info(f"   ✅ Processed {spatial_index['file_count']} files so far...")
                    else:
                        logger.warning(f"   ⚠️ Could not extract bounds from: {file_info['filename']}")
                
                logger.info(f"   📊 Added {files_added_this_dir} files from {directory}")
                
                # Update zone summary
                zone_files = spatial_index["utm_zones"][utm_zone]["files"]
                spatial_index["utm_zones"][utm_zone]["file_count"] = len(zone_files)
                
                # Calculate coverage bounds for zone
                if zone_files:
                    spatial_index["utm_zones"][utm_zone]["coverage_bounds"] = self._calculate_coverage_bounds(zone_files)
            
            # Generate coverage summary
            spatial_index["coverage_summary"] = self._generate_coverage_summary(spatial_index)
            
            # Save spatial index
            self._save_spatial_index(spatial_index)
            
            logger.info("✅ Comprehensive spatial index generated successfully!")
            logger.info(f"   📊 Total files: {spatial_index['file_count']:,}")
            logger.info(f"   📁 Directories scanned: {len(spatial_index['directories_scanned'])}")
            logger.info(f"   🗺️ UTM zones: {list(spatial_index['utm_zones'].keys())}")
            logger.info(f"   💾 Saved to: {self.spatial_index_file}")
            
            return spatial_index
            
        except Exception as e:
            logger.error(f"❌ Error generating comprehensive spatial index: {e}")
            raise
    
    def _discover_all_tif_directories(self, s3_client, bucket_name: str) -> Set[str]:
        """Discover all directories in the bucket that contain .tif files"""
        directories_with_tifs = set()
        
        try:
            # Use paginator to handle large buckets
            paginator = s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(Bucket=bucket_name)
            
            for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        key = obj['Key']
                        
                        # Check if this is a .tif file
                        if key.lower().endswith('.tif') or key.lower().endswith('.tiff'):
                            # Extract directory path
                            directory = '/'.join(key.split('/')[:-1]) + '/'
                            directories_with_tifs.add(directory)
                            
                            # Log progress every 10000 objects
                            if len(directories_with_tifs) % 10 == 0:
                                logger.info(f"   🔍 Found {len(directories_with_tifs)} directories so far...")
            
        except ClientError as e:
            logger.error(f"❌ Error accessing S3 bucket: {e}")
            raise
            
        return directories_with_tifs
    
    def _scan_s3_directory_comprehensive(self, s3_client, bucket_name: str, directory: str) -> List[Dict]:
        """Scan specific S3 directory for .tif files"""
        files_found = []
        
        try:
            # Use paginator for directories with many files
            paginator = s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(
                Bucket=bucket_name,
                Prefix=directory
            )
            
            for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        key = obj['Key']
                        filename = key.split('/')[-1]
                        
                        # Only include .tif files
                        if filename.lower().endswith('.tif') or filename.lower().endswith('.tiff'):
                            files_found.append({
                                "key": key,
                                "filename": filename,
                                "size": obj['Size'],
                                "last_modified": obj['LastModified'].isoformat()
                            })
            
        except ClientError as e:
            logger.warning(f"⚠️ Error scanning directory {directory}: {e}")
            
        return files_found
    
    def _extract_utm_zone(self, directory_path: str) -> str:
        """Extract UTM zone from directory path"""
        # Look for patterns like z56, z55, etc.
        utm_match = re.search(r'/z(\d+)/', directory_path)
        if utm_match:
            return f"z{utm_match.group(1)}"
        
        # State-based zone assignment
        if "act-elvis" in directory_path:
            return "z55"  # ACT is in zone 55
        elif "nsw-elvis" in directory_path:
            return "z56"  # Most NSW is in zone 56
        elif "qld-elvis" in directory_path:
            return "z56"  # Most QLD is in zone 56  
        elif "tas-elvis" in directory_path:
            return "z55"  # Tasmania is in zone 55
        elif "ga-elvis/elevation/1m-dem/ausgeoid/" in directory_path:
            return "national"  # National coverage
        else:
            # Try to determine from path structure
            if "/z54/" in directory_path:
                return "z54"
            elif "/z55/" in directory_path:
                return "z55"
            elif "/z56/" in directory_path:
                return "z56"
            else:
                return "unknown"
    
    def _extract_bounds_from_filename(self, filename: str) -> Optional[Dict]:
        """Extract coordinate bounds from DEM filename"""
        # Pattern for standard DEM files with grid coordinates
        # Example: SomeName_3726677_56_0001_0001.tif
        pattern = r'_(\d{7})_(\d{2})_\d{4}_\d{4}\.tiff?$'
        match = re.search(pattern, filename)
        
        if match:
            easting = int(match.group(1))
            zone = int(match.group(2))
            
            # Convert grid coordinates to approximate lat/lon bounds
            # This is a simplified conversion - actual bounds would need proper UTM conversion
            # For now, use broad regional bounds based on zone
            if zone == 54:
                return {"min_lat": -26.0, "max_lat": -10.0, "min_lon": 138.0, "max_lon": 144.0}
            elif zone == 55:
                return {"min_lat": -43.0, "max_lat": -10.0, "min_lon": 144.0, "max_lon": 150.0}
            elif zone == 56:
                return {"min_lat": -35.0, "max_lat": -10.0, "min_lon": 150.0, "max_lon": 156.0}
            else:
                return {"min_lat": -44.0, "max_lat": -9.0, "min_lon": 112.0, "max_lon": 154.0}
        
        # Fallback patterns for other naming conventions
        if any(pattern in filename.lower() for pattern in ['clarence', 'richmond']):
            return {"min_lat": -29.0, "max_lat": -25.0, "min_lon": 151.0, "max_lon": 154.0}
        
        # Default broad Australia bounds
        return {"min_lat": -44.0, "max_lat": -9.0, "min_lon": 112.0, "max_lon": 154.0}
    
    def _extract_resolution(self, filename: str) -> str:
        """Extract resolution from filename"""
        if "50cm" in filename.lower():
            return "50cm"
        elif "1m" in filename.lower():
            return "1m"
        elif "2m" in filename.lower():
            return "2m"
        elif "5m" in filename.lower():
            return "5m"
        else:
            return "unknown"
    
    def _calculate_coverage_bounds(self, files: List[Dict]) -> Dict:
        """Calculate overall coverage bounds for a set of files"""
        if not files:
            return None
            
        min_lat = min(f["bounds"]["min_lat"] for f in files)
        max_lat = max(f["bounds"]["max_lat"] for f in files)
        min_lon = min(f["bounds"]["min_lon"] for f in files)
        max_lon = max(f["bounds"]["max_lon"] for f in files)
        
        return {
            "min_lat": min_lat,
            "max_lat": max_lat,
            "min_lon": min_lon,
            "max_lon": max_lon
        }
    
    def _generate_coverage_summary(self, spatial_index: Dict) -> Dict:
        """Generate summary of coverage by region"""
        summary = {}
        
        for zone_name, zone_data in spatial_index["utm_zones"].items():
            summary[zone_name] = {
                "file_count": zone_data["file_count"],
                "directories": len(zone_data.get("directories", [])),
                "coverage_bounds": zone_data.get("coverage_bounds"),
                "resolutions": list(set(f.get("resolution", "unknown") for f in zone_data["files"]))
            }
        
        return summary
    
    def _save_spatial_index(self, spatial_index: Dict):
        """Save spatial index to JSON file"""
        try:
            with open(self.spatial_index_file, 'w') as f:
                json.dump(spatial_index, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"❌ Error saving spatial index: {e}")
            raise

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate comprehensive spatial index')
    parser.add_argument('action', choices=['generate', 'validate', 'show'], 
                       help='Action to perform')
    
    args = parser.parse_args()
    
    generator = ComprehensiveSpatialIndexGenerator()
    
    if args.action == 'generate':
        result = generator.generate_complete_index()
        print(f"✅ Generated spatial index with {result['file_count']:,} files")
        print(f"📁 Scanned {len(result['directories_scanned'])} directories")
        
    elif args.action == 'validate':
        if generator.spatial_index_file.exists():
            with open(generator.spatial_index_file) as f:
                index = json.load(f)
            print(f"✅ Spatial index is valid ({index['file_count']:,} files)")
        else:
            print("❌ No spatial index file found")
            
    elif args.action == 'show':
        if generator.spatial_index_file.exists():
            with open(generator.spatial_index_file) as f:
                index = json.load(f)
            print(json.dumps(index, indent=2, default=str))
        else:
            print("❌ No spatial index file found")

if __name__ == "__main__":
    main()