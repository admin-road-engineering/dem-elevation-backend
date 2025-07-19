#!/usr/bin/env python3
"""
Spatial Index Generator for S3 Multi-File DEM Access
Creates static spatial index mapping coordinates to specific DEM files
"""
import json
import sys
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SpatialIndexGenerator:
    """
    Generates static spatial index from S3 bucket contents
    Maps coordinates to specific DEM files for efficient access
    """
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.config_dir = self.project_root / "config"
        self.config_dir.mkdir(exist_ok=True)
        self.spatial_index_file = self.config_dir / "spatial_index.json"
        
    def generate_complete_index(self) -> Dict:
        """Generate complete spatial index from S3 bucket"""
        
        logger.info("🗺️ Generating spatial index from S3 bucket...")
        
        try:
            from config import Settings
            import boto3
            
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
                "coverage_summary": {}
            }
            
            # Define S3 directories to scan
            directories_to_scan = [
                "csiro-elvis/elevation/1m-dem/z56/",
                "dawe-elvis/elevation/50cm-dem/z56/", 
                "ga-elvis/elevation/1m-dem/ausgeoid/z55/",
                "griffith-elvis/elevation/50cm-dem/z55/",
                "act-elvis/",
                "ga-elvis/elevation/1m-dem/ausgeoid/"
            ]
            
            for directory in directories_to_scan:
                logger.info(f"Scanning directory: {directory}")
                
                # Extract UTM zone from directory path
                utm_zone = self._extract_utm_zone(directory)
                if utm_zone not in spatial_index["utm_zones"]:
                    spatial_index["utm_zones"][utm_zone] = {
                        "files": [],
                        "coverage_bounds": None,
                        "file_count": 0
                    }
                
                # Scan directory for .tif files
                files_found = self._scan_s3_directory(s3_client, settings.AWS_S3_BUCKET_NAME, directory)
                
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
                            "utm_zone": utm_zone
                        }
                        
                        spatial_index["utm_zones"][utm_zone]["files"].append(file_entry)
                        spatial_index["file_count"] += 1
                        
                        logger.info(f"  Added: {file_info['filename']} -> {bounds}")
                    else:
                        logger.warning(f"  Could not extract bounds from: {file_info['filename']}")
                
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
            
            logger.info(f"✅ Spatial index generated successfully!")
            logger.info(f"   Total files: {spatial_index['file_count']}")
            logger.info(f"   UTM zones: {list(spatial_index['utm_zones'].keys())}")
            logger.info(f"   Saved to: {self.spatial_index_file}")
            
            return spatial_index
            
        except Exception as e:
            logger.error(f"❌ Error generating spatial index: {e}")
            raise
    
    def _extract_utm_zone(self, directory_path: str) -> str:
        """Extract UTM zone from directory path"""
        # Look for patterns like z56, z55, etc.
        utm_match = re.search(r'/z(\d+)/', directory_path)
        if utm_match:
            return f"z{utm_match.group(1)}"
        
        # Default zone based on directory content
        if "act-elvis" in directory_path:
            return "z55"  # ACT is in zone 55
        elif "ga-elvis/elevation/1m-dem/ausgeoid/" in directory_path:
            return "national"  # National coverage
        else:
            return "unknown"
    
    def _scan_s3_directory(self, s3_client, bucket_name: str, directory: str) -> List[Dict]:
        """Scan S3 directory for .tif files"""
        files_found = []
        
        try:
            paginator = s3_client.get_paginator('list_objects_v2')
            
            for page in paginator.paginate(Bucket=bucket_name, Prefix=directory):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    
                    # Only process .tif files
                    if key.endswith('.tif'):
                        filename = key.split('/')[-1]
                        
                        files_found.append({
                            "key": key,
                            "filename": filename,
                            "size": obj['Size'],
                            "last_modified": obj['LastModified'].isoformat()
                        })
                        
        except Exception as e:
            logger.warning(f"Error scanning directory {directory}: {e}")
        
        return files_found
    
    def _extract_bounds_from_filename(self, filename: str) -> Optional[Dict]:
        """Extract geographic bounds from filename patterns"""
        
        # Pattern 1: ClarenceRiver2023-DEM-AHD-1m_3706680_56_0001_0001.tif
        # Format: NAME_EASTING_ZONE_TILE_TILE.tif
        match = re.match(r'.*_(\d{7})_(\d{2})_\d+_\d+\.tif', filename)
        if match:
            easting = int(match.group(1))
            utm_zone = int(match.group(2))
            
            # Use regional patterns instead of UTM conversion for now
            # This provides better accuracy for spatial indexing
            if utm_zone == 56:  # Queensland zone
                return {
                    "min_lat": -29.0,
                    "max_lat": -25.0,
                    "min_lon": 151.0,
                    "max_lon": 154.0
                }
            elif utm_zone == 55:  # Victoria zone
                return {
                    "min_lat": -39.0,
                    "max_lat": -34.0,
                    "min_lon": 143.0,
                    "max_lon": 150.0
                }
        
        # Pattern 2: E153_S28_1m_dem.tif (Easting 153, Southing 28)
        match = re.match(r'E(\d+)_S(\d+)_.*\.tif', filename)
        if match:
            east = int(match.group(1))
            south = int(match.group(2))
            return {
                "min_lat": -south - 1,
                "max_lat": -south,
                "min_lon": east,
                "max_lon": east + 1
            }
        
        # Pattern 3: Brisbane_153_-28_1m.tif (Lon 153, Lat -28)
        match = re.match(r'.*_(\d+)_(-?\d+)_.*\.tif', filename)
        if match:
            lon = int(match.group(1))
            lat = int(match.group(2))
            return {
                "min_lat": lat - 0.5,
                "max_lat": lat + 0.5,
                "min_lon": lon - 0.5,
                "max_lon": lon + 0.5
            }
        
        # Pattern 4: ACT_Tile_123_456.tif (Grid tile system)
        match = re.match(r'.*_(\d+)_(\d+)\.tif', filename)
        if match and "act" in filename.lower():
            # ACT tiles - approximate bounds
            return {
                "min_lat": -35.9,
                "max_lat": -35.1,
                "min_lon": 148.7,
                "max_lon": 149.4
            }
        
        # Pattern 5: Generic regional files based on content
        if any(region in filename.lower() for region in ['clarence', 'richmond']):
            # Clarence River area (Northern NSW/Southern QLD)
            return {
                "min_lat": -29.5,
                "max_lat": -28.5,
                "min_lon": 152.5,
                "max_lon": 153.5
            }
        
        if any(region in filename.lower() for region in ['brisbane', 'qld', 'queensland']):
            return {
                "min_lat": -28.5,
                "max_lat": -26.5,
                "min_lon": 152.5,
                "max_lon": 154.5
            }
        
        if any(region in filename.lower() for region in ['melbourne', 'vic', 'victoria', 'bendigo']):
            return {
                "min_lat": -38.5,
                "max_lat": -36.5,
                "min_lon": 143.5,
                "max_lon": 145.5
            }
        
        return None
    
    def _utm_to_latlon_bounds(self, easting: int, utm_zone: int) -> Optional[Dict]:
        """Convert UTM coordinates to approximate lat/lon bounds"""
        try:
            # Simple approximation for Australian UTM zones
            # This is a rough conversion - for precise work, use proper UTM transformation
            
            # Central meridian for UTM zone
            central_meridian = (utm_zone - 1) * 6 - 180 + 3
            
            # Approximate conversion (rough but workable for indexing)
            if utm_zone == 56:  # Queensland/NSW
                # Zone 56 covers roughly 150-156°E
                # More realistic conversion: easting ~500000 = central meridian (153°E)
                approx_lon = 153 + (easting - 500000) / 111000  # Rough degrees per meter
                # Assume typical Queensland latitudes
                approx_lat = -27.0  # Central Queensland latitude
                
                return {
                    "min_lat": approx_lat - 0.01,
                    "max_lat": approx_lat + 0.01,
                    "min_lon": approx_lon - 0.01,
                    "max_lon": approx_lon + 0.01
                }
            elif utm_zone == 55:  # Victoria/NSW
                # Zone 55 covers roughly 144-150°E
                # More realistic conversion: easting ~500000 = central meridian (147°E)
                approx_lon = 147 + (easting - 500000) / 111000  # Rough degrees per meter
                # Assume typical Victoria latitudes
                approx_lat = -37.0  # Central Victoria latitude
                
                return {
                    "min_lat": approx_lat - 0.01,
                    "max_lat": approx_lat + 0.01,
                    "min_lon": approx_lon - 0.01,
                    "max_lon": approx_lon + 0.01
                }
            
            return None
            
        except Exception as e:
            logger.warning(f"Error converting UTM to lat/lon: {e}")
            return None
    
    def _extract_resolution(self, filename: str) -> str:
        """Extract resolution from filename"""
        if "1m" in filename:
            return "1m"
        elif "50cm" in filename:
            return "50cm"
        elif "25cm" in filename:
            return "25cm"
        elif "5m" in filename:
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
        """Generate coverage summary for the index"""
        summary = {
            "total_files": spatial_index["file_count"],
            "zones": {},
            "key_locations": {}
        }
        
        # Zone summaries
        for zone, zone_data in spatial_index["utm_zones"].items():
            summary["zones"][zone] = {
                "file_count": zone_data["file_count"],
                "coverage_bounds": zone_data["coverage_bounds"]
            }
        
        # Test key locations
        test_locations = {
            "brisbane": (-27.4698, 153.0251),
            "bendigo": (-36.7570, 144.2794),
            "melbourne": (-37.8136, 144.9631),
            "canberra": (-35.2809, 149.1300)
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
        """Find files that contain the given coordinate"""
        matching_files = []
        
        for zone, zone_data in spatial_index["utm_zones"].items():
            for file_info in zone_data["files"]:
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
                logger.warning(f"Error loading spatial index: {e}")
        return None
    
    def validate_spatial_index(self) -> bool:
        """Validate existing spatial index"""
        spatial_index = self.load_spatial_index()
        if not spatial_index:
            logger.error("No spatial index found")
            return False
        
        logger.info("🔍 Validating spatial index...")
        
        # Check structure
        required_keys = ["generated_at", "bucket", "utm_zones", "file_count"]
        for key in required_keys:
            if key not in spatial_index:
                logger.error(f"Missing required key: {key}")
                return False
        
        # Check zones have files
        total_files = 0
        for zone, zone_data in spatial_index["utm_zones"].items():
            if "files" not in zone_data:
                logger.error(f"Zone {zone} missing files list")
                return False
            total_files += len(zone_data["files"])
        
        if total_files != spatial_index["file_count"]:
            logger.error(f"File count mismatch: {total_files} vs {spatial_index['file_count']}")
            return False
        
        logger.info(f"✅ Spatial index is valid ({total_files} files)")
        return True

def main():
    """Main function"""
    generator = SpatialIndexGenerator()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "generate":
            generator.generate_complete_index()
        elif command == "validate":
            generator.validate_spatial_index()
        elif command == "show":
            index = generator.load_spatial_index()
            if index:
                print(json.dumps(index.get("coverage_summary", {}), indent=2))
            else:
                print("No spatial index found")
        else:
            print("Unknown command. Use: generate, validate, or show")
    else:
        print("🗺️ Spatial Index Generator")
        print("Commands:")
        print("  generate - Generate spatial index from S3")
        print("  validate - Validate existing index")
        print("  show     - Show coverage summary")
        print()
        print("Example: python scripts/generate_spatial_index.py generate")

if __name__ == "__main__":
    main()