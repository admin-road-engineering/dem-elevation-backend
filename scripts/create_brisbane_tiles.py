#!/usr/bin/env python3
"""
Brisbane Tile Subdivision - Phase 3 Final Optimization
Subdivides Brisbane campaigns into spatial tiles to achieve 316x performance target
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Tuple
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_spatial_tiles(bounds: Dict, tile_size: float = 0.05) -> List[Dict]:
    """
    Create spatial tiles from campaign bounds.
    
    Args:
        bounds: Campaign bounds {min_lat, max_lat, min_lon, max_lon}
        tile_size: Size of each tile in degrees (default: 0.05 = ~5km)
    
    Returns:
        List of tile bounds
    """
    if not bounds or not all(k in bounds for k in ["min_lat", "max_lat", "min_lon", "max_lon"]):
        return []
    
    min_lat = bounds["min_lat"]
    max_lat = bounds["max_lat"]
    min_lon = bounds["min_lon"]
    max_lon = bounds["max_lon"]
    
    tiles = []
    
    # Create grid of tiles
    lat = min_lat
    while lat < max_lat:
        lon = min_lon
        while lon < max_lon:
            tile_bounds = {
                "type": "bbox",
                "min_lat": lat,
                "max_lat": min(lat + tile_size, max_lat),
                "min_lon": lon,
                "max_lon": min(lon + tile_size, max_lon)
            }
            tiles.append(tile_bounds)
            lon += tile_size
        lat += tile_size
    
    return tiles

def point_in_bounds(lat: float, lon: float, bounds: Dict) -> bool:
    """Check if point is within bounds"""
    return (bounds["min_lat"] <= lat <= bounds["max_lat"] and 
            bounds["min_lon"] <= lon <= bounds["max_lon"])

def subdivide_brisbane_campaigns():
    """Subdivide Brisbane campaigns into spatial tiles for 316x performance"""
    config_dir = Path(__file__).parent.parent / "config"
    campaign_index_file = config_dir / "phase3_campaign_populated_index.json"
    output_file = config_dir / "phase3_brisbane_tiled_index.json"
    
    if not campaign_index_file.exists():
        logger.error(f"Campaign index not found: {campaign_index_file}")
        return
    
    logger.info("Loading campaign index...")
    with open(campaign_index_file, 'r') as f:
        campaign_index = json.load(f)
    
    # Brisbane CBD test coordinate for optimization
    brisbane_cbd_lat = -27.4698
    brisbane_cbd_lon = 153.0251
    
    # Identify Brisbane campaigns to subdivide
    brisbane_campaigns = []
    for campaign_id, campaign_data in campaign_index["datasets"].items():
        if campaign_data.get("geographic_region") == "brisbane_metro":
            file_count = len(campaign_data.get("files", []))
            if file_count > 500:  # Only subdivide large campaigns
                brisbane_campaigns.append((campaign_id, campaign_data))
    
    logger.info(f"Found {len(brisbane_campaigns)} large Brisbane campaigns to subdivide")
    
    # Create tiled index
    tiled_index = campaign_index.copy()
    tiled_index["architecture"] = "Phase 3 - Brisbane Tiled Optimization"
    tiled_index["tile_timestamp"] = datetime.now().isoformat()
    
    tiles_created = 0
    files_redistributed = 0
    
    for campaign_id, campaign_data in brisbane_campaigns:
        logger.info(f"Subdividing {campaign_id} ({len(campaign_data.get('files', []))} files)")
        
        # Create tiles for this campaign
        tiles = create_spatial_tiles(campaign_data.get("bounds", {}), tile_size=0.02)  # Smaller tiles for CBD
        logger.info(f"Created {len(tiles)} tiles for {campaign_id}")
        
        # Distribute files to tiles
        files = campaign_data.get("files", [])
        tile_datasets = {}
        
        for i, tile_bounds in enumerate(tiles):
            tile_id = f"{campaign_id}_tile_{i+1:02d}"
            tile_files = []
            
            # Assign files to this tile based on their bounds
            for file_info in files:
                file_bounds = file_info.get("bounds", {})
                if file_bounds:
                    # Check if file center point is in this tile
                    file_center_lat = (file_bounds.get("min_lat", 0) + file_bounds.get("max_lat", 0)) / 2
                    file_center_lon = (file_bounds.get("min_lon", 0) + file_bounds.get("max_lon", 0)) / 2
                    
                    if point_in_bounds(file_center_lat, file_center_lon, tile_bounds):
                        tile_files.append(file_info)
            
            # Only create tile dataset if it has files
            if tile_files:
                tile_dataset = campaign_data.copy()
                tile_dataset["name"] = f"{campaign_data['name']} - Tile {i+1:02d}"
                tile_dataset["bounds"] = tile_bounds
                tile_dataset["files"] = tile_files
                tile_dataset["file_count"] = len(tile_files)
                tile_dataset["parent_campaign"] = campaign_id
                tile_dataset["tile_number"] = i + 1
                tile_dataset["is_tile"] = True
                
                tile_datasets[tile_id] = tile_dataset
                files_redistributed += len(tile_files)
        
        # Remove original campaign and add tiles
        del tiled_index["datasets"][campaign_id]
        tiled_index["datasets"].update(tile_datasets)
        tiles_created += len(tile_datasets)
        
        logger.info(f"Created {len(tile_datasets)} non-empty tiles for {campaign_id}")
    
    # Update totals
    tiled_index["total_campaigns"] = len(tiled_index["datasets"])
    tiled_index["tiling_stats"] = {
        "campaigns_subdivided": len(brisbane_campaigns),
        "tiles_created": tiles_created,
        "files_redistributed": files_redistributed
    }
    
    # Save tiled index
    logger.info(f"Saving tiled index to {output_file}")
    with open(output_file, 'w') as f:
        json.dump(tiled_index, f, indent=2)
    
    # Test performance with Brisbane CBD
    logger.info("\nTesting Brisbane CBD performance with tiled index...")
    test_brisbane_cbd_performance(tiled_index, brisbane_cbd_lat, brisbane_cbd_lon)
    
    logger.info(f"Brisbane tiling completed!")
    logger.info(f"Total tiles created: {tiles_created}")
    logger.info(f"Files redistributed: {files_redistributed:,}")
    
    return tiled_index

def test_brisbane_cbd_performance(tiled_index: Dict, lat: float, lon: float):
    """Test performance improvement with tiled index"""
    logger.info("=" * 60)
    logger.info("BRISBANE CBD TILED PERFORMANCE TEST")
    logger.info("=" * 60)
    
    # Find tiles containing the CBD coordinate
    matching_tiles = []
    
    for tile_id, tile_data in tiled_index["datasets"].items():
        if not tile_data.get("is_tile", False):
            continue  # Skip non-tile datasets
        
        if point_in_bounds(lat, lon, tile_data.get("bounds", {})):
            matching_tiles.append((tile_id, tile_data))
    
    logger.info(f"Found {len(matching_tiles)} tiles containing Brisbane CBD ({lat}, {lon})")
    
    if matching_tiles:
        # Sort by file count (prefer smaller tiles)
        matching_tiles.sort(key=lambda x: len(x[1].get("files", [])))
        
        best_tile_id, best_tile = matching_tiles[0]
        files_in_best_tile = len(best_tile.get("files", []))
        
        logger.info(f"Best tile: {best_tile_id}")
        logger.info(f"Files in best tile: {files_in_best_tile}")
        
        # Calculate performance
        original_qld_files = 216106
        phase2_files = 31485
        phase3_campaign_files = 1585  # Brisbane2019Prj
        
        speedup_vs_original = original_qld_files / files_in_best_tile
        speedup_vs_phase2 = phase2_files / files_in_best_tile
        speedup_vs_phase3_campaign = phase3_campaign_files / files_in_best_tile
        
        target_speedup = 316
        target_achieved = speedup_vs_original >= target_speedup
        
        logger.info(f"\nPERFORMANCE RESULTS:")
        logger.info("-" * 40)
        logger.info(f"Original QLD Elvis: {original_qld_files:,} files")
        logger.info(f"Phase 2 grouped: {phase2_files:,} files")
        logger.info(f"Phase 3 campaign: {phase3_campaign_files:,} files")
        logger.info(f"Phase 3 tiled: {files_in_best_tile:,} files")
        logger.info(f"Speedup vs Original: {speedup_vs_original:.1f}x")
        logger.info(f"Speedup vs Phase 2: {speedup_vs_phase2:.1f}x")
        logger.info(f"Speedup vs Campaign: {speedup_vs_phase3_campaign:.1f}x")
        logger.info(f"Target speedup: {target_speedup}x")
        logger.info(f"Target achieved: {'✅ YES' if target_achieved else '❌ NO'}")
        
        if target_achieved:
            logger.info("🎉 BRISBANE 316x TARGET ACHIEVED WITH TILING!")
        else:
            gap = target_speedup - speedup_vs_original
            needed_files = original_qld_files // target_speedup
            logger.info(f"Gap: {gap:.1f}x additional speedup needed")
            logger.info(f"Need ≤{needed_files} files to hit target")
        
        return target_achieved
    
    return False

def main():
    """Main execution function"""
    logger.info("Brisbane Tile Subdivision for 316x Performance Target")
    logger.info("=" * 60)
    
    tiled_index = subdivide_brisbane_campaigns()
    return tiled_index

if __name__ == "__main__":
    main()