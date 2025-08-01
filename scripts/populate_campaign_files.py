#!/usr/bin/env python3
"""
Campaign File Population - Phase 3 Implementation
Populates campaign-based spatial index with actual file lists from original grouped index
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def extract_campaign_from_s3_path(s3_path: str) -> str:
    """Extract campaign name from S3 file path using improved pattern matching"""
    if not s3_path.startswith('s3://'):
        return 'unknown'
    
    # Updated patterns based on actual file paths
    patterns = [
        # Pattern: after UTM zone folder (most common)
        r'/z\d{2}/([^/]+)/',
        # Pattern: after elevation type folder
        r'/(1m-dem|50cm-dem|2m-dem)/[^/]+/([^/]+)/',
        # Pattern: direct campaign folder
        r'/elevation/[^/]+/[^/]+/([^/]+)/',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, s3_path)
        if match:
            # Get the last capturing group (campaign name)
            campaign = match.groups()[-1]
            # Clean up campaign name - remove common artifacts
            campaign = campaign.replace('_', '').replace('-', '').strip()
            return campaign
    
    return 'unknown'

def populate_campaign_files(original_index_file: Path, campaign_index_file: Path, output_file: Path) -> Dict[str, Any]:
    """
    Populate campaign-based index with actual file lists from original grouped index
    """
    logger.info("Loading original grouped spatial index...")
    with open(original_index_file, 'r') as f:
        original_index = json.load(f)
    
    logger.info("Loading campaign-based index...")
    with open(campaign_index_file, 'r') as f:
        campaign_index = json.load(f)
    
    # Track file assignments
    file_assignments = {}
    unassigned_files = []
    
    # Process each original dataset
    for dataset_id, dataset_info in original_index["datasets"].items():
        if dataset_id not in ["qld_elvis", "nsw_elvis", "griffith_elvis"]:
            continue  # Only process the large datasets we're subdividing
        
        logger.info(f"Processing {dataset_info.get('file_count', 0)} files from {dataset_id}")
        files = dataset_info.get("files", [])
        
        for file_info in files:
            s3_path = file_info.get("key", "")
            campaign = extract_campaign_from_s3_path(s3_path)
            
            # Try to find matching campaign in our campaign index
            campaign_found = False
            
            # First try exact match
            if campaign in campaign_index["datasets"]:
                if campaign_index["datasets"][campaign]["parent_dataset"] == dataset_id:
                    if "files" not in campaign_index["datasets"][campaign]:
                        campaign_index["datasets"][campaign]["files"] = []
                    campaign_index["datasets"][campaign]["files"].append(file_info)
                    file_assignments[s3_path] = campaign
                    campaign_found = True
            
            # If no exact match, try fuzzy matching
            if not campaign_found:
                for campaign_name in campaign_index["datasets"]:
                    if campaign_index["datasets"][campaign_name]["parent_dataset"] == dataset_id:
                        # Try various matching strategies
                        if campaign.lower() in campaign_name.lower() or campaign_name.lower() in campaign.lower():
                            if "files" not in campaign_index["datasets"][campaign_name]:
                                campaign_index["datasets"][campaign_name]["files"] = []
                            campaign_index["datasets"][campaign_name]["files"].append(file_info)
                            file_assignments[s3_path] = campaign_name
                            campaign_found = True
                            break
            
            if not campaign_found:
                unassigned_files.append({
                    "s3_path": s3_path,
                    "extracted_campaign": campaign,
                    "dataset_id": dataset_id
                })
    
    # Update file counts and mark as populated
    total_assigned_files = 0
    for campaign_name, campaign_data in campaign_index["datasets"].items():
        actual_file_count = len(campaign_data.get("files", []))
        if actual_file_count > 0:
            campaign_data["file_count"] = actual_file_count
            campaign_data["files_populated"] = True
            campaign_data.pop("note", None)  # Remove placeholder note
            total_assigned_files += actual_file_count
        else:
            # Remove campaigns with no files
            campaign_data["files_populated"] = False
    
    # Clean up campaigns with no files
    campaigns_to_remove = [name for name, data in campaign_index["datasets"].items() 
                          if len(data.get("files", [])) == 0]
    
    for campaign_name in campaigns_to_remove:
        del campaign_index["datasets"][campaign_name]
        campaign_index["total_campaigns"] -= 1
    
    # Update totals
    campaign_index["total_files"] = total_assigned_files
    campaign_index["file_population_timestamp"] = datetime.now().isoformat()
    campaign_index["file_assignment_stats"] = {
        "total_assigned": total_assigned_files,
        "unassigned_files": len(unassigned_files),
        "campaigns_with_files": len([d for d in campaign_index["datasets"].values() if len(d.get("files", [])) > 0]),
        "campaigns_removed": len(campaigns_to_remove)
    }
    
    # Log some unassigned files for debugging
    if unassigned_files:
        logger.warning(f"{len(unassigned_files)} files could not be assigned to campaigns")
        logger.info("Sample unassigned files:")
        for i, file_info in enumerate(unassigned_files[:5]):
            logger.info(f"  {file_info['extracted_campaign']} <- {file_info['s3_path']}")
    
    # Save populated index
    logger.info(f"Saving populated campaign index to {output_file}")
    with open(output_file, 'w') as f:
        json.dump(campaign_index, f, indent=2)
    
    # Generate final statistics
    generate_final_statistics(campaign_index)
    
    logger.info("Campaign file population completed!")
    logger.info(f"Total campaigns with files: {campaign_index['file_assignment_stats']['campaigns_with_files']}")
    logger.info(f"Total files assigned: {total_assigned_files:,}")
    logger.info(f"Unassigned files: {len(unassigned_files):,}")
    
    return campaign_index

def generate_final_statistics(campaign_index: Dict) -> None:
    """Generate final performance statistics"""
    datasets = campaign_index["datasets"]
    
    # Calculate metro area statistics
    brisbane_campaigns = [d for d in datasets.values() if d["geographic_region"] == "brisbane_metro" and len(d.get("files", [])) > 0]
    sydney_campaigns = [d for d in datasets.values() if d["geographic_region"] == "sydney_metro" and len(d.get("files", [])) > 0]
    
    brisbane_files = sum(len(d.get("files", [])) for d in brisbane_campaigns)
    sydney_files = sum(len(d.get("files", [])) for d in sydney_campaigns)
    
    # Calculate performance improvements
    original_qld_files = 216106
    original_nsw_files = 80686
    
    brisbane_speedup = original_qld_files // max(1, brisbane_files) if brisbane_files > 0 else 0
    sydney_speedup = original_nsw_files // max(1, sydney_files) if sydney_files > 0 else 0
    
    campaign_index["performance_analysis"] = {
        "brisbane_metro": {
            "campaigns": len(brisbane_campaigns),
            "total_files": brisbane_files,
            "estimated_speedup": f"{brisbane_speedup}x",
            "original_files_searched": original_qld_files,
            "improvement": f"{(1 - brisbane_files/original_qld_files)*100:.1f}% reduction in files searched"
        },
        "sydney_metro": {
            "campaigns": len(sydney_campaigns),
            "total_files": sydney_files,
            "estimated_speedup": f"{sydney_speedup}x",
            "original_files_searched": original_nsw_files,
            "improvement": f"{(1 - sydney_files/original_nsw_files)*100:.1f}% reduction in files searched"
        },
        "phase_3_targets": {
            "brisbane_target_speedup": "316x",
            "brisbane_actual_speedup": f"{brisbane_speedup}x",
            "brisbane_target_achieved": brisbane_speedup >= 316,
            "sydney_target_speedup": "42x", 
            "sydney_actual_speedup": f"{sydney_speedup}x",
            "sydney_target_achieved": sydney_speedup >= 42
        }
    }

def main():
    """Main execution function"""
    config_dir = Path(__file__).parent.parent / "config"
    original_index_file = config_dir / "grouped_spatial_index.json"
    campaign_index_file = config_dir / "phase3_campaign_based_index.json"
    output_file = config_dir / "phase3_campaign_populated_index.json"
    
    if not original_index_file.exists():
        logger.error(f"Original grouped index not found: {original_index_file}")
        return
    
    if not campaign_index_file.exists():
        logger.error(f"Campaign index not found: {campaign_index_file}")
        return
    
    logger.info("Starting Phase 3 Campaign File Population")
    logger.info("=" * 60)
    
    populated_index = populate_campaign_files(original_index_file, campaign_index_file, output_file)
    
    # Print performance analysis
    if "performance_analysis" in populated_index:
        perf = populated_index["performance_analysis"]
        logger.info("PHASE 3 PERFORMANCE RESULTS:")
        logger.info(f"Brisbane Metro: {perf['brisbane_metro']['campaigns']} campaigns, {perf['brisbane_metro']['total_files']:,} files")
        logger.info(f"Brisbane Speedup: {perf['brisbane_metro']['estimated_speedup']} (Target: {perf['phase_3_targets']['brisbane_target_speedup']})")
        logger.info(f"Sydney Metro: {perf['sydney_metro']['campaigns']} campaigns, {perf['sydney_metro']['total_files']:,} files")
        logger.info(f"Sydney Speedup: {perf['sydney_metro']['estimated_speedup']} (Target: {perf['phase_3_targets']['sydney_target_speedup']})")
        
        if perf['phase_3_targets']['brisbane_target_achieved'] and perf['phase_3_targets']['sydney_target_achieved']:
            logger.info("🎉 ALL PHASE 3 PERFORMANCE TARGETS ACHIEVED!")
        else:
            logger.info("⚠️  Phase 3 targets not fully achieved - may need further optimization")
    
    return populated_index

if __name__ == "__main__":
    main()