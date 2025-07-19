#!/usr/bin/env python3
"""
NZ Elevation Spatial Index Generator for S3 Multi-File DEM Access
Creates spatial index for New Zealand elevation data from public S3 bucket
"""
import json
import sys
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import boto3
from botocore import UNSIGNED
from botocore.config import Config

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NZSpatialIndexGenerator:
    """
    Generates spatial index for NZ elevation data from public S3 bucket
    Maps coordinates to specific DEM files for efficient access
    """
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.config_dir = self.project_root / "config"
        self.config_dir.mkdir(exist_ok=True)
        self.spatial_index_file = self.config_dir / "nz_spatial_index.json"
        
    def generate_complete_index(self) -> Dict:
        """Generate complete spatial index from NZ elevation S3 bucket"""
        
        logger.info("🗺️ Generating NZ elevation spatial index...")
        
        try:
            # Create S3 client for public bucket access
            s3_client = boto3.client(
                's3',
                region_name='ap-southeast-2',
                config=Config(signature_version=UNSIGNED)
            )
            
            # Initialize spatial index structure
            spatial_index = {
                "generated_at": datetime.now().isoformat(),
                "bucket": "nz-elevation",
                "coordinate_system": "NZGD2000 / New Zealand Transverse Mercator 2000 (EPSG:2193)",
                "regions": {},
                "file_count": 0,
                "coverage_summary": {}
            }
            
            # Get all regions from bucket
            regions = self._get_regions(s3_client)
            logger.info(f"Found {len(regions)} regions: {', '.join(regions)}")
            
            # Process each region
            for region in regions:
                logger.info(f"Processing region: {region}")
                
                region_data = {
                    "surveys": {},
                    "file_count": 0,
                    "coverage_bounds": None
                }
                
                # Get surveys for this region
                surveys = self._get_surveys_for_region(s3_client, region)
                
                for survey in surveys:
                    logger.info(f"  Processing survey: {survey}")
                    
                    # Get DEM files for this survey
                    dem_files = self._get_dem_files_for_survey(s3_client, region, survey)
                    
                    if dem_files:
                        survey_data = {
                            "files": [],
                            "file_count": len(dem_files),
                            "coverage_bounds": None
                        }
                        
                        for file_info in dem_files:
                            # Extract bounds from filename
                            bounds = self._extract_bounds_from_nz_filename(file_info["filename"])
                            
                            if bounds:
                                file_entry = {
                                    "file": f"s3://nz-elevation/{file_info['key']}",
                                    "filename": file_info["filename"],
                                    "bounds": bounds,
                                    "size_mb": round(file_info["size"] / 1024 / 1024, 2),
                                    "last_modified": file_info["last_modified"],
                                    "resolution": "1m",
                                    "region": region,
                                    "survey": survey,
                                    "coordinate_system": "EPSG:2193"
                                }
                                
                                survey_data["files"].append(file_entry)
                                spatial_index["file_count"] += 1
                                
                                logger.info(f"    Added: {file_info['filename']} -> {bounds}")
                            else:
                                logger.warning(f"    Could not extract bounds from: {file_info['filename']}")
                        
                        # Calculate coverage bounds for survey
                        if survey_data["files"]:
                            survey_data["coverage_bounds"] = self._calculate_coverage_bounds(survey_data["files"])
                        
                        region_data["surveys"][survey] = survey_data
                        region_data["file_count"] += survey_data["file_count"]
                
                # Calculate coverage bounds for region
                all_region_files = []
                for survey_data in region_data["surveys"].values():
                    all_region_files.extend(survey_data["files"])
                
                if all_region_files:
                    region_data["coverage_bounds"] = self._calculate_coverage_bounds(all_region_files)
                
                spatial_index["regions"][region] = region_data
            
            # Generate coverage summary
            spatial_index["coverage_summary"] = self._generate_coverage_summary(spatial_index)
            
            # Save spatial index
            self._save_spatial_index(spatial_index)
            
            logger.info(f"✅ NZ elevation spatial index generated successfully!")
            logger.info(f"   Total files: {spatial_index['file_count']}")
            logger.info(f"   Regions: {list(spatial_index['regions'].keys())}")
            logger.info(f"   Saved to: {self.spatial_index_file}")
            
            return spatial_index
            
        except Exception as e:
            logger.error(f"❌ Error generating NZ elevation spatial index: {e}")
            raise
    
    def _get_regions(self, s3_client) -> List[str]:
        """Get all regions from NZ elevation bucket"""
        regions = []
        
        try:
            response = s3_client.list_objects_v2(
                Bucket='nz-elevation',
                Delimiter='/'
            )
            
            if 'CommonPrefixes' in response:
                for prefix in response['CommonPrefixes']:
                    region = prefix['Prefix'].strip('/')
                    if region not in ['new-zealand']:  # Skip aggregated data
                        regions.append(region)
            
        except Exception as e:
            logger.warning(f"Error getting regions: {e}")
        
        return regions
    
    def _get_surveys_for_region(self, s3_client, region: str) -> List[str]:
        """Get all surveys for a region"""
        surveys = []
        
        try:
            response = s3_client.list_objects_v2(
                Bucket='nz-elevation',
                Prefix=f"{region}/",
                Delimiter='/'
            )
            
            if 'CommonPrefixes' in response:
                for prefix in response['CommonPrefixes']:
                    survey_path = prefix['Prefix'].strip('/')
                    survey = survey_path.split('/')[-1]
                    surveys.append(survey)
            
        except Exception as e:
            logger.warning(f"Error getting surveys for {region}: {e}")
        
        return surveys
    
    def _get_dem_files_for_survey(self, s3_client, region: str, survey: str) -> List[Dict]:
        """Get all DEM files for a survey"""
        dem_files = []
        
        try:
            # Look for DEM files in the survey directory
            dem_prefix = f"{region}/{survey}/dem_1m/2193/"
            
            paginator = s3_client.get_paginator('list_objects_v2')
            
            for page in paginator.paginate(Bucket='nz-elevation', Prefix=dem_prefix):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    
                    # Only process .tiff files
                    if key.endswith('.tiff'):
                        filename = key.split('/')[-1]
                        
                        dem_files.append({
                            "key": key,
                            "filename": filename,
                            "size": obj['Size'],
                            "last_modified": obj['LastModified'].isoformat()
                        })
                        
        except Exception as e:
            logger.warning(f"Error getting DEM files for {region}/{survey}: {e}")
        
        return dem_files
    
    def _extract_bounds_from_nz_filename(self, filename: str) -> Optional[Dict]:
        """Extract geographic bounds from NZ elevation filename patterns"""
        
        # NZ elevation files use NZGD2000 grid references
        # Pattern: AY30_10000_0405.tiff (Grid reference + tile numbers)
        
        # Extract grid reference (e.g., AY30, BP32, CF14)
        match = re.match(r'([A-Z]{2}\d{2})_\d+_\d+\.tiff', filename)
        if match:
            grid_ref = match.group(1)
            
            # Convert NZGD2000 grid reference to approximate lat/lon bounds
            # This is a simplified conversion - for precise work, use proper grid transformation
            bounds = self._nzgd2000_grid_to_latlon(grid_ref)
            if bounds:
                return bounds
        
        # Fallback: Use region-based bounds if grid reference fails
        region_bounds = self._get_region_bounds_from_filename(filename)
        if region_bounds:
            return region_bounds
        
        return None
    
    def _nzgd2000_grid_to_latlon(self, grid_ref: str) -> Optional[Dict]:
        """Convert NZGD2000 grid reference to approximate lat/lon bounds"""
        
        # NZGD2000 grid references mapping (approximate)
        # This is a simplified mapping for spatial indexing
        grid_mappings = {
            # Auckland region
            'AY30': {'min_lat': -36.9, 'max_lat': -36.8, 'min_lon': 174.7, 'max_lon': 174.8},
            'AY31': {'min_lat': -36.9, 'max_lat': -36.8, 'min_lon': 174.8, 'max_lon': 174.9},
            
            # Wellington region
            'BP32': {'min_lat': -41.3, 'max_lat': -41.2, 'min_lon': 174.9, 'max_lon': 175.0},
            'BP31': {'min_lat': -41.3, 'max_lat': -41.2, 'min_lon': 174.8, 'max_lon': 174.9},
            
            # Canterbury region
            'BV24': {'min_lat': -43.4, 'max_lat': -43.3, 'min_lon': 172.5, 'max_lon': 172.6},
            'BW24': {'min_lat': -43.4, 'max_lat': -43.3, 'min_lon': 172.6, 'max_lon': 172.7},
            
            # Otago region
            'CF14': {'min_lat': -46.2, 'max_lat': -46.1, 'min_lon': 169.7, 'max_lon': 169.8},
            'CE14': {'min_lat': -46.2, 'max_lat': -46.1, 'min_lon': 169.6, 'max_lon': 169.7},
        }
        
        if grid_ref in grid_mappings:
            return grid_mappings[grid_ref]
        
        # Fallback: Use first two letters to determine rough region
        region_code = grid_ref[:2]
        region_mappings = {
            'AY': {'min_lat': -37.0, 'max_lat': -36.5, 'min_lon': 174.5, 'max_lon': 175.0},  # Auckland
            'BP': {'min_lat': -41.5, 'max_lat': -41.0, 'min_lon': 174.5, 'max_lon': 175.5},  # Wellington
            'BV': {'min_lat': -43.5, 'max_lat': -43.0, 'min_lon': 172.0, 'max_lon': 173.0},  # Canterbury
            'BW': {'min_lat': -43.5, 'max_lat': -43.0, 'min_lon': 172.5, 'max_lon': 173.5},  # Canterbury
            'CF': {'min_lat': -46.5, 'max_lat': -46.0, 'min_lon': 169.5, 'max_lon': 170.0},  # Otago
            'CE': {'min_lat': -46.5, 'max_lat': -46.0, 'min_lon': 169.0, 'max_lon': 169.5},  # Otago
        }
        
        return region_mappings.get(region_code)
    
    def _get_region_bounds_from_filename(self, filename: str) -> Optional[Dict]:
        """Get approximate bounds based on region name in file path"""
        
        # Regional bounds for New Zealand
        region_bounds = {
            'auckland': {'min_lat': -37.0, 'max_lat': -36.5, 'min_lon': 174.5, 'max_lon': 175.0},
            'wellington': {'min_lat': -41.5, 'max_lat': -41.0, 'min_lon': 174.5, 'max_lon': 175.5},
            'canterbury': {'min_lat': -44.0, 'max_lat': -43.0, 'min_lon': 171.0, 'max_lon': 173.0},
            'otago': {'min_lat': -46.5, 'max_lat': -45.0, 'min_lon': 169.0, 'max_lon': 171.5},
            'southland': {'min_lat': -47.0, 'max_lat': -46.0, 'min_lon': 166.0, 'max_lon': 169.0},
            'west-coast': {'min_lat': -43.5, 'max_lat': -42.0, 'min_lon': 170.0, 'max_lon': 172.0},
            'northland': {'min_lat': -36.5, 'max_lat': -35.0, 'min_lon': 173.0, 'max_lon': 174.5},
            'waikato': {'min_lat': -38.5, 'max_lat': -37.0, 'min_lon': 174.5, 'max_lon': 176.0},
            'bay-of-plenty': {'min_lat': -38.5, 'max_lat': -37.0, 'min_lon': 176.0, 'max_lon': 178.0},
            'hawkes-bay': {'min_lat': -40.0, 'max_lat': -38.5, 'min_lon': 176.0, 'max_lon': 178.0},
            'taranaki': {'min_lat': -40.0, 'max_lat': -38.5, 'min_lon': 173.5, 'max_lon': 175.0},
            'manawatu-whanganui': {'min_lat': -40.5, 'max_lat': -39.0, 'min_lon': 174.5, 'max_lon': 176.5},
            'gisborne': {'min_lat': -38.5, 'max_lat': -37.0, 'min_lon': 177.0, 'max_lon': 179.0},
            'marlborough': {'min_lat': -42.0, 'max_lat': -40.5, 'min_lon': 173.0, 'max_lon': 175.0},
            'nelson': {'min_lat': -41.5, 'max_lat': -40.5, 'min_lon': 172.5, 'max_lon': 174.0},
            'tasman': {'min_lat': -41.5, 'max_lat': -40.5, 'min_lon': 172.0, 'max_lon': 173.5},
        }
        
        # Check if any region name appears in the filename
        for region, bounds in region_bounds.items():
            if region in filename.lower():
                return bounds
        
        return None
    
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
        
        # Test key locations
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
        """Find files that contain the given coordinate"""
        matching_files = []
        
        for region, region_data in spatial_index["regions"].items():
            for survey, survey_data in region_data["surveys"].items():
                for file_info in survey_data["files"]:
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
                logger.warning(f"Error loading NZ spatial index: {e}")
        return None

def main():
    """Main function"""
    generator = NZSpatialIndexGenerator()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "generate":
            generator.generate_complete_index()
        elif command == "show":
            index = generator.load_spatial_index()
            if index:
                print(json.dumps(index.get("coverage_summary", {}), indent=2))
            else:
                print("No NZ spatial index found")
        else:
            print("Unknown command. Use: generate or show")
    else:
        print("🗺️ NZ Elevation Spatial Index Generator")
        print("Commands:")
        print("  generate - Generate spatial index from NZ elevation S3 bucket")
        print("  show     - Show coverage summary")
        print()
        print("Example: python scripts/generate_nz_spatial_index.py generate")

if __name__ == "__main__":
    main()