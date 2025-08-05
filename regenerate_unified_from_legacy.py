#!/usr/bin/env python3
"""
Emergency Fix: Regenerate Unified Index from Existing Legacy Data
Uses the working spatial_index.json (631,556 AU files) + nz_spatial_index.json
"""
import json
import sys
import logging
import uuid
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def regenerate_unified_index():
    """Regenerate unified index using existing legacy data"""
    
    project_root = Path(__file__).parent
    config_dir = project_root / "config"
    
    # Input files
    au_index_file = config_dir / "spatial_index.json"
    nz_index_file = config_dir / "nz_spatial_index.json"
    
    # Output file
    output_file = config_dir / "unified_spatial_index_v2_fixed.json"
    
    logger.info("🔄 Regenerating unified index from existing legacy data...")
    
    # Load Australian index
    logger.info("📂 Loading Australian spatial index...")
    with open(au_index_file, 'r') as f:
        au_index = json.load(f)
    
    au_file_count = au_index.get("file_count", 0)
    logger.info(f"   ✅ Loaded AU index: {au_file_count} files")
    
    # Load NZ index
    logger.info("📂 Loading NZ spatial index...")
    with open(nz_index_file, 'r') as f:
        nz_index = json.load(f)
    
    nz_campaigns = len(nz_index.get("campaigns", {}))
    nz_file_count = sum(len(c.get("files", [])) for c in nz_index.get("campaigns", {}).values())
    logger.info(f"   ✅ Loaded NZ index: {nz_campaigns} campaigns, {nz_file_count} files")
    
    # Convert Australian UTM zones to collections
    logger.info("🔄 Converting Australian UTM zones to collections...")
    au_collections = []
    
    for zone_name, zone_data in au_index.get("utm_zones", {}).items():
        # Convert files to unified format
        files = []
        for file_info in zone_data.get("files", []):
            file_entry = {
                "file": file_info["file"],
                "filename": file_info["filename"],
                "bounds": file_info["bounds"],
                "size_mb": file_info.get("size_mb", 0.0),
                "last_modified": file_info.get("last_modified", ""),
                "resolution": file_info.get("resolution", "1m"),
                "coordinate_system": file_info.get("coordinate_system", "GDA94"),
                "method": file_info.get("method", "utm_conversion")
            }
            files.append(file_entry)
        
        # Extract UTM zone number
        utm_zone = int(zone_name.replace('z', ''))
        
        # Create collection
        collection = {
            "id": str(uuid.uuid4()),
            "collection_type": "australian_utm_zone",
            "country": "AU",
            "utm_zone": utm_zone,
            "state": extract_state_from_zone(zone_data),
            "region": extract_region_from_zone(zone_data),
            "files": files,
            "coverage_bounds": zone_data.get("coverage_bounds", {}),
            "file_count": len(files),
            "metadata": {
                "source_bucket": "road-engineering-elevation-data",
                "coordinate_system": "GDA94",
                "utm_zone": utm_zone,
                "epsg_code": f"EPSG:283{utm_zone}",
                "discovery_method": "legacy_spatial_index"
            }
        }
        
        au_collections.append(collection)
        logger.info(f"   ✅ Converted UTM zone {utm_zone}: {len(files)} files")
    
    # Convert NZ campaigns to collections
    logger.info("🔄 Converting NZ campaigns to collections...")
    nz_collections = []
    
    for campaign_name, campaign_data in nz_index.get("campaigns", {}).items():
        # Convert files
        files = []
        for file_info in campaign_data.get("files", []):
            file_entry = {
                "file": file_info["file"],
                "filename": file_info["filename"],
                "bounds": file_info["bounds"],
                "size_mb": file_info.get("size_mb", 0.0),
                "last_modified": file_info.get("last_modified", ""),
                "resolution": file_info.get("resolution", "1m"),
                "coordinate_system": file_info.get("coordinate_system", "NZGD2000"),
                "method": file_info.get("method", "geotiff_extraction")
            }
            files.append(file_entry)
        
        # Extract years from campaign name
        import re
        years = re.findall(r'\b(19|20)\d{2}\b', campaign_name)
        survey_years = [int(year) for year in years] if years else [2020]
        
        collection = {
            "id": str(uuid.uuid4()),
            "collection_type": "new_zealand_campaign",
            "country": "NZ",
            "region": campaign_data.get("region", "unknown"),
            "survey_name": campaign_data.get("survey", campaign_name),
            "survey_years": survey_years,
            "data_type": campaign_data.get("data_type", "DEM").upper(),
            "files": files,
            "coverage_bounds": campaign_data.get("coverage_bounds", {}),
            "file_count": len(files),
            "metadata": {
                "source_bucket": "nz-elevation",
                "coordinate_system": "NZGD2000 / NZTM 2000",
                "original_campaign": campaign_name
            }
        }
        
        nz_collections.append(collection)
    
    logger.info(f"   ✅ Converted {len(nz_collections)} NZ collections")
    
    # Create unified index
    all_collections = au_collections + nz_collections
    total_files = sum(c["file_count"] for c in all_collections)
    
    unified_index = {
        "version": "2.0",
        "generated_at": datetime.now().isoformat(),
        "schema_metadata": {
            "total_collections": len(all_collections),
            "total_files": total_files,
            "countries": ["AU", "NZ"],
            "collection_types": ["australian_utm_zone", "new_zealand_campaign"],
            "generated_at": datetime.now().isoformat()
        },
        "data_collections": all_collections
    }
    
    # Save unified index
    with open(output_file, 'w') as f:
        json.dump(unified_index, f, indent=2)
    
    logger.info("✅ Regenerated unified index successfully!")
    logger.info(f"   Australian collections: {len(au_collections)}")
    logger.info(f"   NZ collections: {len(nz_collections)}")
    logger.info(f"   Total collections: {len(all_collections)}")
    logger.info(f"   Total files: {total_files}")
    logger.info(f"   Saved to: {output_file}")
    
    return output_file

def extract_state_from_zone(zone_data):
    """Extract state from zone data"""
    files = zone_data.get("files", [])
    if files:
        file_path = files[0].get("file", "").lower()
        if "qld" in file_path:
            return "QLD"
        elif "nsw" in file_path:
            return "NSW"
        elif "vic" in file_path:
            return "VIC"
        elif "act" in file_path:
            return "ACT"
    return "UNKNOWN"

def extract_region_from_zone(zone_data):
    """Extract region from zone data"""
    files = zone_data.get("files", [])
    if files:
        file_path = files[0].get("file", "").lower()
        if "brisbane" in file_path:
            return "brisbane"
        elif "sydney" in file_path:
            return "sydney"
    return None

if __name__ == "__main__":
    output_file = regenerate_unified_index()
    print(f"\n🎯 Next steps:")
    print(f"1. Upload {output_file} to S3 as 'indexes/unified_spatial_index_v2.json'")
    print(f"2. Test Brisbane coordinates: lat=-27.4698, lon=153.0251")
    print(f"3. Expected: Brisbane elevation found (54,000x speedup restored!)")