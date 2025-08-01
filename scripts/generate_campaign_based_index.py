#!/usr/bin/env python3
"""
Campaign-Based Spatial Index Generator - Phase 3 Implementation
Creates optimized spatial index organized by survey campaigns instead of regional datasets
"""

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_campaign_based_index(campaign_analysis_file: Path, output_file: Path) -> Dict[str, Any]:
    """
    Create campaign-based spatial index from campaign analysis.
    
    This transforms the current regional grouping (qld_elvis: 216k files) into 
    campaign-specific datasets (Brisbane2009LGA: 1.6k files, Logan2017LGA: 4.4k files, etc.)
    """
    logger.info("Loading campaign analysis...")
    with open(campaign_analysis_file, 'r') as f:
        campaign_data = json.load(f)
    
    # Create new campaign-based index structure
    campaign_index = {
        "index_timestamp": datetime.now().isoformat(),
        "extraction_method": "campaign_based_subdivision",
        "architecture": "Phase 3 - Campaign-Based Optimization",
        "total_campaigns": 0,
        "total_files": 0,
        "datasets": {}
    }
    
    # Define campaign priorities and classifications
    campaign_priorities = {
        # Brisbane Metro Area - Highest Priority
        "Brisbane2009LGA": 1, "Brisbane2014LGA": 1, "Brisbane2019Prj": 1,
        "Logan2009LGA": 1, "Logan2013LGA": 1, "Logan2017LGA": 1, "Logan2021GDA2020LGA": 1, "Logan2023LGA": 1,
        "MoretonBay2009LGA": 1, "MoretonBay2014LGA": 1, "MoretonBay2018LGA": 1,
        "Ipswich2009LGA": 1, "Ipswich2014LGA": 1, "Ipswich2019LGA": 1, "Ipswich2023LGA": 1,
        "Redland2009LGA": 1, "Redland2014LGA": 1,
        "GoldCoast2009LGA": 1, "GoldCoast2014LGA": 1,
        
        # Sydney Metro Area - Highest Priority  
        "Sydney201105": 1, "Sydney201304": 1, "Sydney201705": 1, "Sydney201906": 1, "Sydney202004": 1, "Sydney202005": 1, "Sydney202006": 1, "Sydney202008": 1,
        "Penrith201102": 1, "Penrith201105": 1, "Penrith201304": 1, "Penrith201407": 1, "Penrith201610": 1, "Penrith201705": 1, "Penrith201804": 1, "Penrith201904": 1, "Penrith201906": 1, "Penrith201907": 1, "Penrith202004": 1, "Penrith202006": 1,
        "Gosford201105": 1, "Gosford201409": 1, "Gosford201611": 1, "Gosford201705": 1, "Gosford202008": 1,
        "Wollongong201102": 1, "Wollongong201304": 1, "Wollongong201605": 1, "Wollongong201906": 1, "Wollongong202004": 1,
        
        # Large Regional Campaigns - Medium Priority
        "SuratCMA2012OGIA": 2, "SuratCMA2014OGIA": 2, "SuratCMA2020OGIA": 2, "SuratCMA2021OGIA": 2, "SuratCMA2022OGIA": 2,
        "FraserCoast2009Ctl": 2, "Bundaberg2016Rgn": 2, "ScenicRim2011LGA": 2,
        "BurdekinRiverSouth2024Prj": 2, "Rockhampton2015Prj": 2, "BorderRivers2023Prj": 2,
        
        # Other Regional Areas - Standard Priority
        "Toowoomba2010Rgn": 3, "Toowoomba2015Prj": 3, "ToowoombaCooby2020Prj": 3,
        "SunshineCoast2008LGA": 3, "SunshineCoast2014LGA": 3, "Noosa2015LGA": 3,
        "Cairns2010Prj": 3, "Townsville2009Ctl": 3, "Townsville2018Prj": 3,
        "Mackay2009Rgn": 3, "Mackay2015Rgn": 3, "Mackay2021Prj": 3,
    }
    
    # Process each regional dataset's campaigns
    for dataset_id, campaigns in campaign_data["campaign_breakdown"].items():
        logger.info(f"Processing {len(campaigns)} campaigns from {dataset_id}")
        
        for campaign_name, campaign_info in campaigns.items():
            if campaign_info["file_count"] == 0:
                continue  # Skip empty campaigns
                
            # Determine campaign classification
            geographic_region = classify_geographic_region(campaign_name, campaign_info["bounds"])
            priority = campaign_priorities.get(campaign_name, 4)  # Default priority 4
            
            # Create campaign dataset entry
            campaign_dataset = {
                "name": f"{campaign_name} Survey Campaign",
                "source_type": "s3", 
                "path": f"s3://road-engineering-elevation-data/{dataset_id.replace('_', '-')}/",
                "crs": "EPSG:3577",  # Australian Albers
                "bounds": {
                    "type": "bbox",
                    "min_lat": campaign_info["bounds"]["min_lat"],
                    "max_lat": campaign_info["bounds"]["max_lat"], 
                    "min_lon": campaign_info["bounds"]["min_lon"],
                    "max_lon": campaign_info["bounds"]["max_lon"]
                },
                "priority": priority,
                "resolution_m": 1,  # Most campaigns are 1m resolution
                "data_type": "LiDAR",
                "provider": get_provider_from_dataset(dataset_id),
                "accuracy": "±0.1m",
                "file_count": campaign_info["file_count"],
                "geographic_region": geographic_region,
                "parent_dataset": dataset_id,
                "campaign_year": extract_year_from_campaign(campaign_name),
                "metadata": {
                    "capture_method": "Airborne LiDAR",
                    "vertical_datum": "AHD",
                    "color": get_region_color(geographic_region),
                    "opacity": 0.6
                },
                "files": []  # Will be populated from original grouped index
            }
            
            campaign_index["datasets"][campaign_name] = campaign_dataset
            campaign_index["total_campaigns"] += 1
            campaign_index["total_files"] += campaign_info["file_count"]
    
    # Now populate file lists from the original grouped index
    logger.info("Populating file lists from original grouped index...")
    populate_campaign_files(campaign_index, campaign_data)
    
    # Generate summary statistics
    generate_campaign_statistics(campaign_index)
    
    # Save the campaign-based index
    logger.info(f"Saving campaign-based index to {output_file}")
    with open(output_file, 'w') as f:
        json.dump(campaign_index, f, indent=2)
    
    logger.info(f"Campaign-based index created successfully!")
    logger.info(f"Total campaigns: {campaign_index['total_campaigns']}")
    logger.info(f"Total files: {campaign_index['total_files']:,}")
    
    return campaign_index

def classify_geographic_region(campaign_name: str, bounds: Dict) -> str:
    """Classify campaign into geographic regions for better organization"""
    if not bounds or not bounds.get("min_lat"):
        return "unknown"
    
    lat = (bounds["min_lat"] + bounds["max_lat"]) / 2
    lon = (bounds["min_lon"] + bounds["max_lon"]) / 2
    
    # Brisbane Metro Area
    if -28.0 <= lat <= -26.5 and 152.0 <= lon <= 154.0:
        if any(name in campaign_name.lower() for name in ["brisbane", "logan", "ipswich", "moreton", "redland", "goldcoast"]):
            return "brisbane_metro"
        else:
            return "southeast_qld"
    
    # Sydney Metro Area  
    if -34.5 <= lat <= -32.5 and 150.0 <= lon <= 152.0:
        if any(name in campaign_name.lower() for name in ["sydney", "penrith", "gosford", "wollongong"]):
            return "sydney_metro"
        else:
            return "nsw_central"
    
    # Melbourne Metro Area
    if -38.5 <= lat <= -37.0 and 144.0 <= lon <= 146.0:
        return "melbourne_metro"
    
    # Other classifications
    if lat >= -17.0:
        return "far_north_qld"
    elif lat >= -21.0:
        return "north_qld" 
    elif lat >= -26.0:
        return "central_qld"
    elif lat >= -29.0:
        return "southeast_qld"
    else:
        return "nsw_central"

def get_provider_from_dataset(dataset_id: str) -> str:
    """Get provider name from dataset ID"""
    if "elvis" in dataset_id:
        return "Elvis"
    elif "ga_" in dataset_id:
        return "Geoscience Australia"
    elif "csiro" in dataset_id:
        return "CSIRO"
    else:
        return "Unknown"

def extract_year_from_campaign(campaign_name: str) -> str:
    """Extract year from campaign name"""
    import re
    year_match = re.search(r'(20\d{2})', campaign_name)
    if year_match:
        return year_match.group(1)
    return "unknown"

def get_region_color(region: str) -> str:
    """Get color code for geographic region"""
    color_map = {
        "brisbane_metro": "#FF6B6B",     # Red
        "sydney_metro": "#4ECDC4",       # Teal  
        "melbourne_metro": "#45B7D1",    # Blue
        "southeast_qld": "#FFA726",      # Orange
        "central_qld": "#66BB6A",        # Green
        "north_qld": "#AB47BC",          # Purple
        "far_north_qld": "#EC407A",      # Pink
        "nsw_central": "#78909C",        # Blue Gray
        "unknown": "#9E9E9E"             # Gray
    }
    return color_map.get(region, "#9E9E9E")

def populate_campaign_files(campaign_index: Dict, campaign_data: Dict) -> None:
    """Populate file lists for each campaign from original analysis"""
    # This would need access to the original grouped_spatial_index.json
    # For now, we'll create placeholder file structures
    logger.info("Note: File population requires original grouped index - creating structure only")
    
    # Mark that files need to be populated from original index
    for campaign_name in campaign_index["datasets"]:
        campaign_index["datasets"][campaign_name]["files_populated"] = False
        campaign_index["datasets"][campaign_name]["note"] = "Files to be populated from original grouped spatial index"

def generate_campaign_statistics(campaign_index: Dict) -> None:
    """Generate summary statistics for the campaign index"""
    datasets = campaign_index["datasets"]
    
    # Region statistics
    region_stats = defaultdict(lambda: {"campaigns": 0, "files": 0})
    priority_stats = defaultdict(lambda: {"campaigns": 0, "files": 0})
    year_stats = defaultdict(lambda: {"campaigns": 0, "files": 0})
    
    for campaign_name, dataset in datasets.items():
        region = dataset["geographic_region"]
        priority = dataset["priority"]
        year = dataset["campaign_year"]
        file_count = dataset["file_count"]
        
        region_stats[region]["campaigns"] += 1
        region_stats[region]["files"] += file_count
        
        priority_stats[priority]["campaigns"] += 1
        priority_stats[priority]["files"] += file_count
        
        year_stats[year]["campaigns"] += 1
        year_stats[year]["files"] += file_count
    
    campaign_index["statistics"] = {
        "by_region": dict(region_stats),
        "by_priority": dict(priority_stats),
        "by_year": dict(year_stats),
        "performance_estimates": {
            "brisbane_metro_campaigns": len([d for d in datasets.values() if d["geographic_region"] == "brisbane_metro"]),
            "brisbane_metro_files": sum(d["file_count"] for d in datasets.values() if d["geographic_region"] == "brisbane_metro"),
            "sydney_metro_campaigns": len([d for d in datasets.values() if d["geographic_region"] == "sydney_metro"]),
            "sydney_metro_files": sum(d["file_count"] for d in datasets.values() if d["geographic_region"] == "sydney_metro"),
            "estimated_brisbane_speedup": f"{216106 // max(1, sum(d['file_count'] for d in datasets.values() if d['geographic_region'] == 'brisbane_metro'))}x",
            "estimated_sydney_speedup": f"{80686 // max(1, sum(d['file_count'] for d in datasets.values() if d['geographic_region'] == 'sydney_metro'))}x"
        }
    }

def main():
    """Main execution function"""
    config_dir = Path(__file__).parent.parent / "config"
    campaign_analysis_file = config_dir / "campaign_structure_analysis.json"
    output_file = config_dir / "phase3_campaign_based_index.json"
    
    if not campaign_analysis_file.exists():
        logger.error(f"Campaign analysis file not found: {campaign_analysis_file}")
        return
    
    logger.info("Starting Phase 3 Campaign-Based Index Generation")
    logger.info("=" * 60)
    
    campaign_index = create_campaign_based_index(campaign_analysis_file, output_file)
    
    # Print summary
    stats = campaign_index["statistics"]["performance_estimates"]
    logger.info("PERFORMANCE IMPROVEMENTS:")
    logger.info(f"Brisbane Metro: {stats['brisbane_metro_campaigns']} campaigns, {stats['brisbane_metro_files']:,} files")
    logger.info(f"Estimated Brisbane speedup: {stats['estimated_brisbane_speedup']}")
    logger.info(f"Sydney Metro: {stats['sydney_metro_campaigns']} campaigns, {stats['sydney_metro_files']:,} files") 
    logger.info(f"Estimated Sydney speedup: {stats['estimated_sydney_speedup']}")
    logger.info(f"Total campaigns: {campaign_index['total_campaigns']}")
    
    return campaign_index

if __name__ == "__main__":
    main()