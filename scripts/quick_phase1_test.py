#!/usr/bin/env python3
"""
Quick Phase 1 Test - 100 files
Validates the core functionality and generates immediate results
"""
import json
import sys
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Geospatial libraries
try:
    import rasterio as rio
    from rasterio.warp import transform_bounds
    from rasterio.crs import CRS
    from rasterio.errors import RasterioIOError
    RASTERIO_AVAILABLE = True
except ImportError:
    print("rasterio required for validation")
    RASTERIO_AVAILABLE = False

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)8s | %(message)s')
logger = logging.getLogger(__name__)

def load_spatial_index() -> Dict:
    """Load existing spatial index"""
    config_dir = Path(__file__).parent.parent / "config"
    spatial_index_file = config_dir / "spatial_index.json"
    
    logger.info("Loading spatial index...")
    with open(spatial_index_file, 'r') as f:
        return json.load(f)

def extract_file_metadata(s3_key: str, bucket_name: str = "road-engineering-elevation-data") -> Optional[Dict]:
    """Extract metadata from single file"""
    try:
        s3_url = f"s3://{bucket_name}/{s3_key}" if not s3_key.startswith('s3://') else s3_key
        
        with rio.open(s3_url) as src:
            bounds = src.bounds
            file_crs = src.crs
            
            # Transform to WGS84 if needed
            if file_crs and file_crs != CRS.from_epsg(4326):
                try:
                    min_lon, min_lat, max_lon, max_lat = transform_bounds(
                        file_crs, CRS.from_epsg(4326),
                        bounds.left, bounds.bottom, bounds.right, bounds.top
                    )
                except Exception:
                    min_lon, min_lat = bounds.left, bounds.bottom
                    max_lon, max_lat = bounds.right, bounds.top
            else:
                min_lon, min_lat = bounds.left, bounds.bottom
                max_lon, max_lat = bounds.right, bounds.top
            
            # Calculate precision
            lat_range = max_lat - min_lat
            lon_range = max_lon - min_lon
            area = lat_range * lon_range
            
            if area < 0.001:
                precision = "precise"
            elif area < 1.0:
                precision = "reasonable"
            else:
                precision = "regional"
            
            return {
                'key': s3_key,
                'filename': Path(s3_key).name,
                'min_lon': min_lon,
                'min_lat': min_lat,
                'max_lon': max_lon,
                'max_lat': max_lat,
                'area_deg2': area,
                'precision': precision,
                'crs': str(file_crs) if file_crs else "unknown",
                'width': src.width,
                'height': src.height
            }
            
    except Exception as e:
        logger.debug(f"Failed to extract metadata from {s3_key}: {e}")
        return None

def test_overlap_reduction(metadata_results: List[Dict]) -> Dict:
    """Test overlap reduction for Brisbane CBD"""
    # Brisbane CBD coordinate (from previous testing)
    brisbane_lat, brisbane_lon = -27.4698, 153.0251
    
    # Count files that contain this coordinate
    matching_files = []
    for file_data in metadata_results:
        if (file_data["min_lat"] <= brisbane_lat <= file_data["max_lat"] and 
            file_data["min_lon"] <= brisbane_lon <= file_data["max_lon"]):
            matching_files.append(file_data)
    
    return {
        "coordinate": f"{brisbane_lat}, {brisbane_lon}",
        "matching_files": len(matching_files),
        "sample_size": len(metadata_results),
        "files_with_precise_bounds": len([f for f in metadata_results if f["precision"] == "precise"]),
        "files_with_reasonable_bounds": len([f for f in metadata_results if f["precision"] == "reasonable"])
    }

def main():
    """Quick test execution"""
    if not RASTERIO_AVAILABLE:
        return
    
    print("Quick Phase 1 Test - 100 files")
    print("="*50)
    
    start_time = time.time()
    
    # Load spatial index and get sample
    spatial_index = load_spatial_index()
    
    # Extract first 100 GeoTIFF files
    all_files = []
    for zone_data in spatial_index.get("utm_zones", {}).values():
        for file_info in zone_data.get("files", []):
            s3_key = file_info.get("key") or file_info.get("file", "")
            filename = file_info.get("filename", "")
            if filename.lower().endswith(('.tif', '.tiff')) and s3_key:
                all_files.append(s3_key)
                if len(all_files) >= 100:  # Quick sample
                    break
        if len(all_files) >= 100:
            break
    
    print(f"Testing {len(all_files)} files...")
    
    # Extract metadata with parallel processing
    results = []
    successful = 0
    failed = 0
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_key = {executor.submit(extract_file_metadata, key): key for key in all_files}
        
        for future in as_completed(future_to_key):
            try:
                result = future.result()
                if result:
                    results.append(result)
                    successful += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
    
    end_time = time.time()
    elapsed = end_time - start_time
    
    # Calculate metrics
    success_rate = (successful / len(all_files)) * 100
    precise_count = len([r for r in results if r["precision"] == "precise"])
    reasonable_count = len([r for r in results if r["precision"] == "reasonable"])
    regional_count = len([r for r in results if r["precision"] == "regional"])
    
    # Test overlap reduction
    overlap_test = test_overlap_reduction(results)
    
    # Print results
    print("\nQUICK TEST RESULTS:")
    print(f"Files processed: {len(all_files)}")
    print(f"Success rate: {success_rate:.1f}% ({successful}/{len(all_files)})")
    print(f"Processing time: {elapsed:.1f} seconds")
    print(f"Processing rate: {successful/elapsed:.1f} files/second")
    print()
    print("PRECISION DISTRIBUTION:")
    print(f"  Precise bounds (<0.001 deg²): {precise_count} files ({precise_count/successful*100:.1f}%)")
    print(f"  Reasonable bounds (<1.0 deg²): {reasonable_count} files ({reasonable_count/successful*100:.1f}%)")  
    print(f"  Regional bounds (>1.0 deg²): {regional_count} files ({regional_count/successful*100:.1f}%)")
    print()
    print("OVERLAP TEST (Brisbane CBD):")
    print(f"  Files covering coordinate: {overlap_test['matching_files']}")
    print(f"  Sample size: {overlap_test['sample_size']}")
    print(f"  Precise bounds in sample: {overlap_test['files_with_precise_bounds']}")
    print()
    
    # Assessment
    meets_success_target = success_rate >= 99.0
    meets_precision_target = (precise_count + reasonable_count) / successful >= 0.99 if successful > 0 else False
    
    print("TARGET ASSESSMENT:")
    print(f"  Success rate >99%: {'PASS' if meets_success_target else 'FAIL'}")
    print(f"  Precision >99%: {'PASS' if meets_precision_target else 'FAIL'}")
    print()
    
    if meets_success_target and meets_precision_target:
        print("SUCCESS: Quick test validates Phase 1 approach!")
        print("Ready to scale to full 50,000-file validation")
    else:
        print("WARNING: Some targets not met in quick test")
        print("Review needed before scaling")
    
    # Save quick results
    config_dir = Path(__file__).parent.parent / "config"
    quick_results = {
        "timestamp": datetime.now().isoformat(),
        "sample_size": len(all_files),
        "successful_extractions": successful,
        "failed_extractions": failed,
        "success_rate": success_rate,
        "processing_time": elapsed,
        "processing_rate": successful/elapsed,
        "precision_distribution": {
            "precise": precise_count,
            "reasonable": reasonable_count,
            "regional": regional_count
        },
        "overlap_test": overlap_test,
        "meets_targets": {
            "success_rate": meets_success_target,
            "precision": meets_precision_target
        }
    }
    
    with open(config_dir / "quick_phase1_test_results.json", 'w') as f:
        json.dump(quick_results, f, indent=2)
    
    print(f"\nResults saved to: {config_dir / 'quick_phase1_test_results.json'}")

if __name__ == "__main__":
    main()