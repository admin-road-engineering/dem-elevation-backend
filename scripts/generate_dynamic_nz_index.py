#!/usr/bin/env python3
"""
Dynamic NZ Elevation Spatial Index Generator using STAC catalog and actual GeoTIFF metadata
Creates spatial index by reading actual bounds from each GeoTIFF file instead of hardcoded mappings
"""
import json
import sys
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import boto3
from botocore import UNSIGNED
from botocore.config import Config
import requests
import rasterio
from rasterio.errors import RasterioIOError
import os

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DynamicNZSpatialIndexGenerator:
    """
    Generates spatial index for NZ elevation data using STAC catalog and actual GeoTIFF metadata
    """
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.config_dir = self.project_root / "config"
        self.config_dir.mkdir(exist_ok=True)
        self.spatial_index_file = self.config_dir / "nz_spatial_index_dynamic.json"
        
        # STAC catalog URL from LINZ elevation repository
        self.stac_catalog_url = "https://nz-elevation.s3-ap-southeast-2.amazonaws.com/catalog.json"
        
        # S3 client for unsigned access to public bucket
        self.s3_client = boto3.client(
            's3',
            region_name='ap-southeast-2',
            config=Config(signature_version=UNSIGNED)
        )
    
    def generate_complete_index(self) -> Dict:
        """Generate complete spatial index using STAC catalog and actual GeoTIFF metadata"""
        
        logger.info("[DYNAMIC NZ] Generating NZ elevation spatial index from STAC catalog...")
        
        try:
            # Initialize spatial index structure
            spatial_index = {
                "generated_at": datetime.now().isoformat(),
                "bucket": "nz-elevation",
                "coordinate_system": "NZGD2000 / New Zealand Transverse Mercator 2000 (EPSG:2193)",
                "method": "dynamic_stac_metadata_extraction",
                "stac_catalog_url": self.stac_catalog_url,
                "regions": {},
                "file_count": 0,
                "coverage_summary": {}
            }
            
            # Step 1: Fetch STAC catalog
            logger.info("Fetching STAC catalog from LINZ...")
            stac_catalog = self._fetch_stac_catalog()
            
            # Step 2: Discover all collections from STAC catalog
            collections = self._discover_collections(stac_catalog)
            logger.info(f"Found {len(collections)} collections in STAC catalog")
            
            # Step 3: Process each collection
            for collection_info in collections:
                region_name = collection_info.get('region', 'unknown')
                logger.info(f"Processing region: {region_name}")
                
                region_data = {
                    "surveys": {},
                    "file_count": 0,
                    "coverage_bounds": None
                }
                
                # Get collection details
                collection_data = self._fetch_collection(collection_info['url'])
                if not collection_data:
                    continue
                
                # Extract items (individual GeoTIFF files) from collection
                items = self._extract_items_from_collection(collection_data)
                
                if items:
                    survey_name = collection_info.get('survey', 'default_survey')
                    survey_data = {
                        "files": [],
                        "file_count": len(items),
                        "coverage_bounds": None
                    }
                    
                    # Process each GeoTIFF file
                    for item in items:
                        file_info = self._process_geotiff_item(item)
                        if file_info:
                            survey_data["files"].append(file_info)
                            spatial_index["file_count"] += 1
                            logger.info(f"    Added: {file_info['filename']} -> bounds from actual metadata")
                    
                    # Calculate coverage bounds for survey
                    if survey_data["files"]:
                        survey_data["coverage_bounds"] = self._calculate_coverage_bounds(survey_data["files"])
                    
                    region_data["surveys"][survey_name] = survey_data
                    region_data["file_count"] += survey_data["file_count"]
                
                # Calculate coverage bounds for region
                all_region_files = []
                for survey_data in region_data["surveys"].values():
                    all_region_files.extend(survey_data["files"])
                
                if all_region_files:
                    region_data["coverage_bounds"] = self._calculate_coverage_bounds(all_region_files)
                
                spatial_index["regions"][region_name] = region_data
            
            # Generate coverage summary
            spatial_index["coverage_summary"] = self._generate_coverage_summary(spatial_index)
            
            # Save spatial index
            self._save_spatial_index(spatial_index)
            
            logger.info(f"✅ Dynamic NZ elevation spatial index generated successfully!")
            logger.info(f"   Total files: {spatial_index['file_count']}")
            logger.info(f"   Regions: {list(spatial_index['regions'].keys())}")
            logger.info(f"   Saved to: {self.spatial_index_file}")
            
            return spatial_index
            
        except Exception as e:
            logger.error(f"❌ Error generating dynamic NZ elevation spatial index: {e}")
            raise
    
    def _fetch_stac_catalog(self) -> Dict:
        """Fetch the root STAC catalog"""
        try:
            response = requests.get(self.stac_catalog_url, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch STAC catalog: {e}")
            raise
    
    def _discover_collections(self, catalog: Dict) -> List[Dict]:
        """Discover all collections from STAC catalog"""
        collections = []
        
        # Look for child links that point to collections
        for link in catalog.get("links", []):
            if link.get("rel") == "child":
                collection_url = link.get("href")
                if collection_url:
                    # Parse region/survey info from URL or title
                    region_info = {
                        "url": collection_url,
                        "title": link.get("title", "unknown"), 
                        "region": self._extract_region_from_url(collection_url),
                        "survey": self._extract_survey_from_url(collection_url)
                    }
                    collections.append(region_info)
        
        return collections
    
    def _extract_region_from_url(self, url: str) -> str:
        """Extract region name from collection URL"""
        # Parse region from URL path like 'auckland/collection.json'
        if '/' in url:
            parts = url.split('/')
            for part in parts:
                if part and part != 'collection.json':
                    return part
        return "unknown"
    
    def _extract_survey_from_url(self, url: str) -> str:
        """Extract survey name from collection URL"""
        # For now, use the region name as survey name
        # This can be enhanced to parse actual survey information
        return self._extract_region_from_url(url)
    
    def _fetch_collection(self, collection_url: str) -> Optional[Dict]:
        """Fetch individual collection data"""
        try:
            # Handle relative URLs by making them absolute
            if not collection_url.startswith('http'):
                base_url = "https://nz-elevation.s3-ap-southeast-2.amazonaws.com/"
                collection_url = base_url + collection_url.lstrip('/')
            
            response = requests.get(collection_url, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"Failed to fetch collection {collection_url}: {e}")
            return None
    
    def _extract_items_from_collection(self, collection: Dict) -> List[Dict]:
        """Extract individual items (GeoTIFF files) from collection"""
        items = []
        
        # Look for items in the collection
        for link in collection.get("links", []):
            if link.get("rel") == "item":
                item_url = link.get("href")
                if item_url:
                    # Fetch item metadata
                    item_data = self._fetch_item(item_url)
                    if item_data:
                        items.append(item_data)
        
        return items
    
    def _fetch_item(self, item_url: str) -> Optional[Dict]:
        """Fetch individual item (GeoTIFF) metadata"""
        try:
            # Handle relative URLs
            if not item_url.startswith('http'):
                base_url = "https://nz-elevation.s3-ap-southeast-2.amazonaws.com/"
                item_url = base_url + item_url.lstrip('/')
            
            response = requests.get(item_url, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"Failed to fetch item {item_url}: {e}")
            return None
    
    def _process_geotiff_item(self, item: Dict) -> Optional[Dict]:
        """Process individual GeoTIFF item and extract actual bounds from metadata"""
        try:
            # Extract S3 path from item assets
            dem_asset = None
            for asset_key, asset in item.get("assets", {}).items():
                if asset_key.endswith("dem") or "tiff" in asset.get("href", "").lower():
                    dem_asset = asset
                    break
            
            if not dem_asset:
                logger.warning(f"No DEM asset found in item {item.get('id', 'unknown')}")
                return None
            
            s3_path = dem_asset.get("href")
            if not s3_path:
                return None
            
            # Extract actual bounds from GeoTIFF metadata using rasterio
            bounds = self._extract_actual_bounds_from_geotiff(s3_path)
            if not bounds:
                return None
            
            # Extract file information
            filename = s3_path.split("/")[-1]
            
            file_entry = {
                "file": s3_path,
                "filename": filename,
                "bounds": bounds,
                "size_mb": round(dem_asset.get("file:size", 0) / 1024 / 1024, 2),
                "last_modified": item.get("datetime", "unknown"),
                "resolution": "1m",
                "region": item.get("properties", {}).get("region", "unknown"),
                "survey": item.get("properties", {}).get("survey", "unknown"),
                "coordinate_system": "EPSG:2193",
                "method": "actual_geotiff_metadata"
            }
            
            return file_entry
            
        except Exception as e:
            logger.warning(f"Failed to process GeoTIFF item: {e}")
            return None
    
    def _extract_actual_bounds_from_geotiff(self, s3_path: str) -> Optional[Dict]:
        """Extract actual bounds from GeoTIFF file using rasterio"""
        try:
            # Configure GDAL for unsigned S3 access
            os.environ['AWS_NO_SIGN_REQUEST'] = 'YES'
            os.environ['GDAL_DISABLE_READDIR_ON_OPEN'] = 'EMPTY_DIR'
            
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
                from rasterio.warp import transform_bounds
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
        
        min_lat = min(f["bounds"]["min_lat"] for f in files if f.get("bounds"))
        max_lat = max(f["bounds"]["max_lat"] for f in files if f.get("bounds"))
        min_lon = min(f["bounds"]["min_lon"] for f in files if f.get("bounds"))
        max_lon = max(f["bounds"]["max_lon"] for f in files if f.get("bounds"))
        
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
        print("Uses STAC catalog and actual GeoTIFF metadata instead of hardcoded mappings")
        print("Commands:")
        print("  generate - Generate spatial index from STAC catalog and actual file metadata")
        print("  show     - Show coverage summary")
        print()
        print("Example: python scripts/generate_dynamic_nz_index.py generate")

if __name__ == "__main__":
    main()