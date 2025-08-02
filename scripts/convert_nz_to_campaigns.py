#!/usr/bin/env python3
"""
NZ Spatial Index Converter: Regions/Surveys → Campaigns
Converts existing nz_spatial_index_dynamic.json to campaign-based structure
"""
import json
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NZCampaignConverter:
    """
    Converts existing NZ dynamic spatial index from regions/surveys to campaign structure
    """
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.config_dir = self.project_root / "config"
        self.input_file = self.config_dir / "nz_spatial_index_dynamic.json"
        self.output_file = self.config_dir / "nz_spatial_index.json"
    
    def convert_to_campaigns(self) -> Dict:
        """Convert existing regional structure to campaign-based structure"""
        
        logger.info("🔄 Converting NZ spatial index from regions/surveys to campaigns...")
        
        # Load existing dynamic index
        if not self.input_file.exists():
            raise FileNotFoundError(f"Input file not found: {self.input_file}")
        
        with open(self.input_file, 'r') as f:
            dynamic_index = json.load(f)
        
        logger.info(f"📊 Loaded dynamic index with {dynamic_index['file_count']} files")
        
        # Initialize campaign-based structure (similar to Australian approach)
        campaign_index = {
            "generated_at": datetime.now().isoformat(),
            "bucket": dynamic_index["bucket"],
            "coordinate_system": dynamic_index["coordinate_system"],
            "method": "campaign_based_grouping_with_actual_bounds",
            "campaigns": {},  # Similar to Australian "utm_zones"
            "file_count": 0,
            "coverage_summary": {}
        }
        
        # Process each region and survey to create campaigns
        processed_files = 0
        for region_name, region_data in dynamic_index["regions"].items():
            logger.info(f"Processing region: {region_name}")
            
            for survey_name, survey_data in region_data["surveys"].items():
                # Extract data type from survey files
                data_type = self._extract_data_type_from_files(survey_data["files"])
                
                # Create campaign name: survey + data type
                campaign_name = f"{survey_name}_{data_type.lower()}"
                
                logger.info(f"  Creating campaign: {campaign_name} ({len(survey_data['files'])} files)")
                
                # Create campaign entry
                campaign_index["campaigns"][campaign_name] = {
                    "files": survey_data["files"],
                    "coverage_bounds": survey_data["coverage_bounds"],
                    "file_count": len(survey_data["files"]),
                    "region": region_name,
                    "survey": survey_name,
                    "data_type": data_type,
                    "resolution": "1m"
                }
                
                # Update file entries to include campaign info
                for file_entry in survey_data["files"]:
                    file_entry["campaign"] = campaign_name
                    if "data_type" not in file_entry:
                        file_entry["data_type"] = data_type
                
                campaign_index["file_count"] += len(survey_data["files"])
                processed_files += len(survey_data["files"])
        
        # Generate coverage summary
        campaign_index["coverage_summary"] = self._generate_coverage_summary(campaign_index)
        
        # Save campaign-based index
        self._save_campaign_index(campaign_index)
        
        logger.info(f"✅ Campaign-based NZ spatial index generated successfully!")
        logger.info(f"   Total files: {campaign_index['file_count']}")
        logger.info(f"   Campaigns: {len(campaign_index['campaigns'])}")
        logger.info(f"   Campaign list:")
        for campaign_name, campaign_data in campaign_index["campaigns"].items():
            logger.info(f"     📂 {campaign_name}: {campaign_data['file_count']} files ({campaign_data['region']}, {campaign_data['data_type']})")
        logger.info(f"   Saved to: {self.output_file}")
        
        return campaign_index
    
    def _extract_data_type_from_files(self, files: List[Dict]) -> str:
        """Extract data type (DEM/DSM) from file paths"""
        if not files:
            return "UNKNOWN"
        
        # Check file paths for dem_1m or dsm_1m
        sample_file = files[0]["file"]
        if "dem_1m" in sample_file:
            return "DEM"
        elif "dsm_1m" in sample_file:
            return "DSM"
        else:
            return "UNKNOWN"
    
    def _generate_coverage_summary(self, campaign_index: Dict) -> Dict:
        """Generate coverage summary for the campaign-based index"""
        summary = {
            "total_files": campaign_index["file_count"],
            "campaigns": {},
            "regions": {},
            "data_types": {"DEM": 0, "DSM": 0, "UNKNOWN": 0},
            "key_locations": {}
        }
        
        # Campaign summaries (similar to Australian zone summaries)
        for campaign, campaign_data in campaign_index["campaigns"].items():
            summary["campaigns"][campaign] = {
                "file_count": campaign_data["file_count"],
                "region": campaign_data["region"],
                "survey": campaign_data["survey"],
                "data_type": campaign_data["data_type"],
                "coverage_bounds": campaign_data["coverage_bounds"]
            }
            
            # Count data types
            data_type = campaign_data["data_type"]
            if data_type in summary["data_types"]:
                summary["data_types"][data_type] += campaign_data["file_count"]
        
        # Region rollup summaries
        region_files = {}
        for campaign, campaign_data in campaign_index["campaigns"].items():
            region = campaign_data["region"]
            if region not in region_files:
                region_files[region] = []
            region_files[region].extend(campaign_data["files"])
        
        for region, files in region_files.items():
            summary["regions"][region] = {
                "file_count": len(files),
                "campaign_count": len([c for c in campaign_index["campaigns"].values() if c["region"] == region]),
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
            matching_files = self._find_files_for_coordinate(campaign_index, lat, lon)
            summary["key_locations"][location] = {
                "coordinates": [lat, lon],
                "matching_files": len(matching_files),
                "files": [f["filename"] for f in matching_files[:3]],  # First 3 files
                "campaigns": list(set(f["campaign"] for f in matching_files[:3]))
            }
        
        return summary
    
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
    
    def _find_files_for_coordinate(self, campaign_index: Dict, lat: float, lon: float) -> List[Dict]:
        """Find files that contain the given coordinate using actual bounds"""
        matching_files = []
        
        for campaign, campaign_data in campaign_index["campaigns"].items():
            for file_info in campaign_data["files"]:
                if not file_info.get("bounds"):
                    continue
                    
                bounds = file_info["bounds"]
                if (bounds["min_lat"] <= lat <= bounds["max_lat"] and
                    bounds["min_lon"] <= lon <= bounds["max_lon"]):
                    matching_files.append(file_info)
        
        return matching_files
    
    def _save_campaign_index(self, campaign_index: Dict):
        """Save campaign-based spatial index to file"""
        with open(self.output_file, 'w') as f:
            json.dump(campaign_index, f, indent=2)
    
    def load_campaign_index(self) -> Optional[Dict]:
        """Load existing campaign-based spatial index"""
        if self.output_file.exists():
            try:
                with open(self.output_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading campaign spatial index: {e}")
        return None

def main():
    """Main function"""
    converter = NZCampaignConverter()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "convert":
            converter.convert_to_campaigns()
        elif command == "show":
            index = converter.load_campaign_index()
            if index:
                print(json.dumps(index.get("coverage_summary", {}), indent=2))
            else:
                print("No NZ campaign spatial index found")
        else:
            print("Unknown command. Use: convert or show")
    else:
        print("[NZ CONVERTER] NZ Spatial Index Converter: Regions/Surveys → Campaigns")
        print("Converts existing dynamic index to campaign-based structure")
        print("Commands:")
        print("  convert - Convert existing index to campaign structure")
        print("  show    - Show coverage summary")
        print()
        print("Example: python scripts/convert_nz_to_campaigns.py convert")

if __name__ == "__main__":
    main()