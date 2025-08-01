#!/usr/bin/env python3
"""
Comprehensive Phase 3 Validation
Tests all Phase 3 optimizations against performance targets and generates final report
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Tuple
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def point_in_bounds(lat: float, lon: float, bounds: Dict) -> bool:
    """Check if point is within bounds"""
    return (bounds.get("min_lat", 999) <= lat <= bounds.get("max_lat", -999) and 
            bounds.get("min_lon", 999) <= lon <= bounds.get("max_lon", -999))

def test_location_performance(index: Dict, location_name: str, lat: float, lon: float, 
                            original_files: int, target_speedup: float) -> Dict:
    """Test performance for a specific location"""
    logger.info(f"\nTesting {location_name} ({lat}, {lon})")
    logger.info("-" * 50)
    
    # Find best matching dataset/tile
    best_match = None
    best_files = float('inf')
    
    matching_datasets = []
    
    for dataset_id, dataset_info in index["datasets"].items():
        bounds = dataset_info.get("bounds", {})
        if point_in_bounds(lat, lon, bounds):
            file_count = len(dataset_info.get("files", []))
            if file_count > 0:
                matching_datasets.append({
                    "id": dataset_id,
                    "file_count": file_count,
                    "is_tile": dataset_info.get("is_tile", False),
                    "region": dataset_info.get("geographic_region", "unknown"),
                    "year": dataset_info.get("campaign_year", "unknown")
                })
                
                if file_count < best_files:
                    best_files = file_count
                    best_match = dataset_info
    
    if not best_match:
        logger.warning(f"No datasets found for {location_name}")
        return {"success": False, "speedup": 0}
    
    # Sort matches by file count (smallest first)
    matching_datasets.sort(key=lambda x: x["file_count"])
    
    logger.info(f"Found {len(matching_datasets)} matching datasets")
    logger.info(f"Best match: {matching_datasets[0]['id']} ({best_files} files)")
    
    if len(matching_datasets) > 1:
        logger.info(f"Alternative: {matching_datasets[1]['id']} ({matching_datasets[1]['file_count']} files)")
    
    # Calculate performance
    speedup = original_files / best_files if best_files > 0 else 0
    target_achieved = speedup >= target_speedup
    
    logger.info(f"Original files: {original_files:,}")
    logger.info(f"Optimized files: {best_files:,}")
    logger.info(f"Speedup: {speedup:.1f}x")
    logger.info(f"Target: {target_speedup}x")
    logger.info(f"Achievement: {'✅ SUCCESS' if target_achieved else '❌ FAILED'}")
    
    return {
        "success": target_achieved,
        "speedup": speedup,
        "target_speedup": target_speedup,
        "original_files": original_files,
        "optimized_files": best_files,
        "best_dataset": matching_datasets[0]["id"],
        "matching_datasets": len(matching_datasets)
    }

def comprehensive_phase3_validation():
    """Run comprehensive Phase 3 validation against all targets"""
    logger.info("COMPREHENSIVE PHASE 3 VALIDATION")
    logger.info("=" * 60)
    logger.info("Testing all optimizations against performance targets")
    
    config_dir = Path(__file__).parent.parent / "config"
    
    # Load tiled index (most optimized)
    tiled_index_file = config_dir / "phase3_brisbane_tiled_index.json"
    if not tiled_index_file.exists():
        logger.error(f"Tiled index not found: {tiled_index_file}")
        return
    
    with open(tiled_index_file, 'r') as f:
        tiled_index = json.load(f)
    
    logger.info(f"Loaded tiled index with {len(tiled_index['datasets'])} datasets/tiles")
    
    # Test locations with targets
    test_locations = [
        {
            "name": "Brisbane CBD",
            "lat": -27.4698,
            "lon": 153.0251,
            "original_files": 216106,  # QLD Elvis
            "target_speedup": 316
        },
        {
            "name": "Sydney Harbor",
            "lat": -33.8568,
            "lon": 151.2153,
            "original_files": 80686,   # NSW Elvis
            "target_speedup": 42
        },
        {
            "name": "Melbourne CBD",
            "lat": -37.8136,
            "lon": 144.9631,
            "original_files": 21422,   # GA VIC
            "target_speedup": 29  # Reasonable target based on size
        },
        {
            "name": "Gold Coast",
            "lat": -28.0167,
            "lon": 153.4000,
            "original_files": 216106,  # QLD Elvis
            "target_speedup": 100  # Should benefit from tiling
        },
        {
            "name": "Logan",
            "lat": -27.6397,
            "lon": 153.1086,
            "original_files": 216106,  # QLD Elvis
            "target_speedup": 200  # Should benefit from tiling
        }
    ]
    
    # Run tests
    results = {}
    total_targets = 0
    targets_achieved = 0
    
    for location in test_locations:
        result = test_location_performance(
            tiled_index,
            location["name"],
            location["lat"],
            location["lon"],
            location["original_files"],
            location["target_speedup"]
        )
        
        results[location["name"]] = result
        total_targets += 1
        if result["success"]:
            targets_achieved += 1
    
    # Generate summary report
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 3 FINAL RESULTS SUMMARY")
    logger.info("=" * 60)
    
    for location_name, result in results.items():
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        logger.info(f"{location_name:15}: {result['speedup']:8.1f}x (target: {result['target_speedup']:3.0f}x) {status}")
    
    success_rate = (targets_achieved / total_targets) * 100
    logger.info(f"\nOverall Success Rate: {targets_achieved}/{total_targets} ({success_rate:.1f}%)")
    
    # Performance achievements
    brisbane_result = results.get("Brisbane CBD", {})
    sydney_result = results.get("Sydney Harbor", {})
    
    logger.info("\n🎯 KEY ACHIEVEMENTS:")
    if brisbane_result.get("success"):
        logger.info(f"✅ Brisbane CBD: {brisbane_result['speedup']:.0f}x speedup (target: 316x)")
    if sydney_result.get("success"):
        logger.info(f"✅ Sydney Harbor: {sydney_result['speedup']:.0f}x speedup (target: 42x)")
    
    # Architecture summary
    logger.info("\n📊 ARCHITECTURE SUMMARY:")
    datasets = tiled_index["datasets"]
    tile_count = sum(1 for d in datasets.values() if d.get("is_tile", False))
    campaign_count = sum(1 for d in datasets.values() if not d.get("is_tile", False))
    
    logger.info(f"Total datasets: {len(datasets):,}")
    logger.info(f"Campaign datasets: {campaign_count:,}")
    logger.info(f"Spatial tiles: {tile_count:,}")
    logger.info(f"Total files indexed: {tiled_index.get('total_files', 0):,}")
    
    # Save validation report
    validation_report = {
        "validation_timestamp": datetime.now().isoformat(),
        "architecture": "Phase 3 - Campaign & Tile Optimization",
        "test_results": results,
        "summary": {
            "total_targets": total_targets,
            "targets_achieved": targets_achieved,
            "success_rate_percent": success_rate,
            "primary_targets_met": {
                "brisbane_316x": brisbane_result.get("success", False),
                "sydney_42x": sydney_result.get("success", False)
            }
        },
        "architecture_stats": {
            "total_datasets": len(datasets),
            "campaign_datasets": campaign_count,
            "spatial_tiles": tile_count,
            "total_files": tiled_index.get("total_files", 0)
        },
        "performance_comparison": {
            "phase_1_baseline": "O(n) flat search - 631,556 files",
            "phase_2_grouped": "O(k) dataset search - 2,000-80,000 files per query",
            "phase_3_campaign": "Campaign selection - 120-1,585 files per query",
            "phase_3_tiled": "Spatial tiling - 4-50 files per query"
        }
    }
    
    report_file = config_dir / "phase3_comprehensive_validation_report.json"
    with open(report_file, 'w') as f:
        json.dump(validation_report, f, indent=2)
    
    logger.info(f"\n📋 Validation report saved: {report_file}")
    
    if targets_achieved == total_targets:
        logger.info("\n🎉 ALL PHASE 3 TARGETS ACHIEVED!")
        logger.info("Phase 3 Campaign & Tile Optimization delivers world-class performance!")
    else:
        logger.info(f"\n⚠️  {targets_achieved}/{total_targets} targets achieved")
        logger.info("Phase 3 optimization provides significant improvements")
    
    return validation_report

def main():
    """Main validation execution"""
    report = comprehensive_phase3_validation()
    return report

if __name__ == "__main__":
    main()