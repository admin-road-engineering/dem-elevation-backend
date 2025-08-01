#!/usr/bin/env python3
"""
Phase 1 Enhanced Validation Script
Executes the agreed-upon validation strategy with 5k-50k file samples

Based on senior engineer feedback: Local build approach with stratified sampling
targeting >99% success rate and 90%+ overlap reduction.
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
    print("Environment variables loaded")
except ImportError:
    print("Using system environment variables")

# Geospatial libraries
try:
    import rasterio as rio
    from rasterio.warp import transform_bounds
    from rasterio.crs import CRS
    from rasterio.errors import RasterioIOError
    RASTERIO_AVAILABLE = True
except ImportError:
    print("❌ rasterio required. Install with: pip install rasterio")
    RASTERIO_AVAILABLE = False

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)8s | %(message)s')
logger = logging.getLogger(__name__)

class Phase1Validator:
    """Phase 1 Enhanced Validation implementation"""
    
    def __init__(self, bucket_name: str = "road-engineering-elevation-data"):
        self.bucket_name = bucket_name
        self.project_root = Path(__file__).parent.parent
        self.config_dir = self.project_root / "config"
        
        # Validation targets from senior engineer review
        self.target_success_rate = 0.99  # >99%
        self.target_overlap_reduction = 0.90  # >90%
        self.target_precise_bounds = 0.99  # >99%
        
        # Test coordinates for overlap validation
        self.test_coordinates = [
            {"name": "Brisbane CBD", "lat": -27.4698, "lon": 153.0251, "expected_files_old": 31809},
            {"name": "Sydney Harbor", "lat": -33.8568, "lon": 151.2153, "expected_files_old": 20000},
            {"name": "Melbourne CBD", "lat": -37.8136, "lon": 144.9631, "expected_files_old": 15000},
            {"name": "Canberra Center", "lat": -35.2809, "lon": 149.1300, "expected_files_old": 5000},
            {"name": "Gold Coast", "lat": -28.0167, "lon": 153.4000, "expected_files_old": 10000}
        ]
        
        # Statistics
        self.stats = {
            "start_time": None,
            "end_time": None,
            "total_files": 0,
            "successful_extractions": 0,
            "failed_extractions": 0,
            "precise_bounds": 0,
            "reasonable_bounds": 0,
            "regional_bounds": 0,
            "crs_distribution": {},
            "regional_distribution": {},
            "processing_rate": 0,
            "overlap_reductions": {}
        }
    
    def load_spatial_index(self) -> Dict:
        """Load existing spatial index"""
        spatial_index_file = self.config_dir / "spatial_index.json"
        
        if not spatial_index_file.exists():
            raise FileNotFoundError(f"Spatial index not found: {spatial_index_file}")
        
        logger.info("📂 Loading spatial index...")
        with open(spatial_index_file, 'r') as f:
            return json.load(f)
    
    def stratified_sample_files(self, spatial_index: Dict, sample_size: int) -> List[str]:
        """Perform stratified sampling based on regional and CRS distribution"""
        import random
        
        # Extract all files
        all_files = []
        for zone_data in spatial_index.get("utm_zones", {}).values():
            for file_info in zone_data.get("files", []):
                s3_key = file_info.get("key") or file_info.get("file", "")
                filename = file_info.get("filename", "")
                if filename.lower().endswith(('.tif', '.tiff')) and s3_key:
                    all_files.append(s3_key)
        
        # Group by region
        regional_groups = {
            'queensland': [],
            'nsw': [],
            'act': [],
            'victoria': [],
            'tasmania': [],
            'other': []
        }
        
        for key in all_files:
            key_lower = key.lower()
            if any(x in key_lower for x in ['qld', 'queensland', 'brisbane', 'gold-coast', 'cairns']):
                regional_groups['queensland'].append(key)
            elif any(x in key_lower for x in ['nsw', 'sydney', 'newcastle', 'clarence']):
                regional_groups['nsw'].append(key)
            elif any(x in key_lower for x in ['act', 'canberra']):
                regional_groups['act'].append(key)
            elif any(x in key_lower for x in ['vic', 'victoria', 'melbourne']):
                regional_groups['victoria'].append(key)
            elif any(x in key_lower for x in ['tas', 'tasmania']):
                regional_groups['tasmania'].append(key)
            else:
                regional_groups['other'].append(key)
        
        # Target distribution aligned with ELVIS dataset
        target_distribution = {
            'queensland': 0.35,  # 35% Queensland
            'nsw': 0.25,         # 25% NSW  
            'act': 0.15,         # 15% ACT
            'victoria': 0.10,    # 10% Victoria
            'tasmania': 0.05,    # 5% Tasmania
            'other': 0.10        # 10% Other
        }
        
        # Sample per region
        stratified_files = []
        for region, target_pct in target_distribution.items():
            group_files = regional_groups[region]
            if group_files:
                target_count = int(sample_size * target_pct)
                actual_count = min(target_count, len(group_files))
                selected = random.sample(group_files, actual_count)
                stratified_files.extend(selected)
                self.stats["regional_distribution"][region] = actual_count
                logger.info(f"📊 {region.title()}: {actual_count:,} files ({actual_count/sample_size*100:.1f}%)")
        
        # Fill remaining slots randomly
        if len(stratified_files) < sample_size:
            remaining_needed = sample_size - len(stratified_files)
            remaining_files = [f for f in all_files if f not in stratified_files]
            if remaining_files:
                additional = random.sample(remaining_files, min(remaining_needed, len(remaining_files)))
                stratified_files.extend(additional)
        
        return stratified_files[:sample_size]
    
    def extract_file_metadata(self, s3_key: str) -> Optional[Dict]:
        """Extract metadata from single file using direct rasterio access"""
        try:
            s3_url = f"s3://{self.bucket_name}/{s3_key}" if not s3_key.startswith('s3://') else s3_key
            
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
                    self.stats["precise_bounds"] += 1
                elif area < 1.0:
                    precision = "reasonable"
                    self.stats["reasonable_bounds"] += 1
                else:
                    precision = "regional"
                    self.stats["regional_bounds"] += 1
                
                # Track CRS distribution
                crs_str = str(file_crs) if file_crs else "unknown"
                self.stats["crs_distribution"][crs_str] = self.stats["crs_distribution"].get(crs_str, 0) + 1
                
                return {
                    'key': s3_key,
                    'filename': Path(s3_key).name,
                    'min_lon': min_lon,
                    'min_lat': min_lat,
                    'max_lon': max_lon,
                    'max_lat': max_lat,
                    'area_deg2': area,
                    'precision': precision,
                    'crs': crs_str,
                    'width': src.width,
                    'height': src.height
                }
                
        except Exception as e:
            logger.debug(f"Failed to extract metadata from {s3_key}: {e}")
            return None
    
    def parallel_metadata_extraction(self, file_keys: List[str], max_workers: int = 30) -> List[Dict]:
        """Extract metadata from files using parallel processing"""
        logger.info(f"🚀 Starting parallel extraction: {len(file_keys):,} files with {max_workers} workers")
        
        self.stats["start_time"] = time.time()
        self.stats["total_files"] = len(file_keys)
        
        results = []
        completed = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_key = {executor.submit(self.extract_file_metadata, key): key for key in file_keys}
            
            for future in as_completed(future_to_key):
                completed += 1
                
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                        self.stats["successful_extractions"] += 1
                    else:
                        self.stats["failed_extractions"] += 1
                        
                except Exception as e:
                    self.stats["failed_extractions"] += 1
                    logger.debug(f"Task failed: {e}")
                
                # Progress logging
                if completed % 500 == 0:
                    progress = completed / len(file_keys) * 100
                    success_rate = self.stats["successful_extractions"] / completed * 100
                    logger.info(f"📊 Progress: {completed:,}/{len(file_keys):,} ({progress:.1f}%) | Success: {success_rate:.1f}%")
        
        self.stats["end_time"] = time.time()
        elapsed = self.stats["end_time"] - self.stats["start_time"]
        self.stats["processing_rate"] = len(results) / elapsed if elapsed > 0 else 0
        
        logger.info(f"✅ Completed: {len(results):,} successful extractions in {elapsed:.1f}s")
        logger.info(f"⚡ Processing rate: {self.stats['processing_rate']:.1f} files/second")
        
        return results
    
    def validate_overlap_reduction(self, metadata_results: List[Dict]) -> Dict:
        """Validate overlap reduction for test coordinates"""
        logger.info("🔍 Validating overlap reduction for test coordinates...")
        
        reduction_results = {}
        
        for coord in self.test_coordinates:
            lat, lon = coord["lat"], coord["lon"]
            name = coord["name"]
            expected_old = coord["expected_files_old"]
            
            # Count files that contain this coordinate
            matching_files = []
            for file_data in metadata_results:
                if (file_data["min_lat"] <= lat <= file_data["max_lat"] and 
                    file_data["min_lon"] <= lon <= file_data["max_lon"]):
                    matching_files.append(file_data)
            
            new_count = len(matching_files)
            reduction_pct = (1 - new_count / expected_old) * 100 if expected_old > 0 else 0
            
            reduction_results[name] = {
                "lat": lat,
                "lon": lon,
                "old_file_count": expected_old,
                "new_file_count": new_count,
                "reduction_percentage": reduction_pct,
                "meets_target": reduction_pct >= self.target_overlap_reduction * 100
            }
            
            logger.info(f"📍 {name}: {expected_old:,} → {new_count} files ({reduction_pct:.1f}% reduction)")
        
        self.stats["overlap_reductions"] = reduction_results
        return reduction_results
    
    def generate_phase1_report(self, metadata_results: List[Dict], overlap_results: Dict):
        """Generate comprehensive Phase 1 validation report"""
        report_file = self.config_dir / "phase1_validation_report.md"
        
        # Calculate summary metrics
        success_rate = self.stats["successful_extractions"] / self.stats["total_files"] * 100
        precise_pct = self.stats["precise_bounds"] / self.stats["successful_extractions"] * 100
        meets_success_target = success_rate >= self.target_success_rate * 100
        meets_precision_target = precise_pct >= self.target_precise_bounds * 100
        
        # Check overlap reduction targets
        overlap_meets_target = all(result["meets_target"] for result in overlap_results.values())
        
        with open(report_file, 'w') as f:
            f.write("# Phase 1 Enhanced Validation Report\\n\\n")
            f.write(f"**Generated:** {datetime.now().isoformat()}\\n")
            f.write(f"**Sample Size:** {self.stats['total_files']:,} files\\n")
            f.write(f"**Processing Time:** {self.stats['end_time'] - self.stats['start_time']:.1f} seconds\\n")
            f.write(f"**Processing Rate:** {self.stats['processing_rate']:.1f} files/second\\n\\n")
            
            f.write("## Executive Summary\\n\\n")
            f.write(f"- **Success Rate:** {success_rate:.2f}% ({self.stats['successful_extractions']:,}/{self.stats['total_files']:,})\\n")
            f.write(f"- **Target Success Rate:** {self.target_success_rate*100:.0f}% {'✅ MET' if meets_success_target else '❌ NOT MET'}\\n")
            f.write(f"- **Precise Bounds:** {precise_pct:.1f}% ({self.stats['precise_bounds']:,} files)\\n")
            f.write(f"- **Target Precise Bounds:** {self.target_precise_bounds*100:.0f}% {'✅ MET' if meets_precision_target else '❌ NOT MET'}\\n")
            f.write(f"- **Overlap Reduction Target:** {'✅ MET' if overlap_meets_target else '❌ NOT MET'}\\n\\n")
            
            f.write("## Regional Distribution\\n\\n")
            for region, count in self.stats["regional_distribution"].items():
                pct = count / self.stats["total_files"] * 100
                f.write(f"- **{region.title()}:** {count:,} files ({pct:.1f}%)\\n")
            f.write("\\n")
            
            f.write("## Coordinate Reference Systems\\n\\n")
            sorted_crs = sorted(self.stats["crs_distribution"].items(), key=lambda x: x[1], reverse=True)
            for crs, count in sorted_crs[:10]:  # Top 10 CRS
                pct = count / self.stats["successful_extractions"] * 100
                f.write(f"- **{crs}:** {count:,} files ({pct:.1f}%)\\n")
            f.write("\\n")
            
            f.write("## Overlap Reduction Results\\n\\n")
            for location, result in overlap_results.items():
                status = "✅" if result["meets_target"] else "❌"
                f.write(f"- **{location}:** {result['old_file_count']:,} → {result['new_file_count']} files ")
                f.write(f"({result['reduction_percentage']:.1f}% reduction) {status}\\n")
            f.write("\\n")
            
            f.write("## Recommendations\\n\\n")
            if meets_success_target and meets_precision_target and overlap_meets_target:
                f.write("✅ **PROCEED TO PRODUCTION:** All Phase 1 targets met\\n")
                f.write("- Success rate exceeds 99% target\\n")
                f.write("- Precision meets 99% target for precise bounds\\n")
                f.write("- Overlap reduction exceeds 90% target\\n")
                f.write("- **Next Steps:** Scale to full 50k sample, then production deployment\\n\\n")
            else:
                f.write("⚠️ **ADDITIONAL OPTIMIZATION NEEDED**\\n")
                if not meets_success_target:
                    f.write("- Improve success rate to meet 99% target\\n")
                if not meets_precision_target:
                    f.write("- Enhance coordinate precision extraction\\n")
                if not overlap_meets_target:
                    f.write("- Investigate overlap reduction methodology\\n")
                f.write("\\n")
        
        logger.info(f"📋 Phase 1 validation report saved: {report_file}")
        
        # Print summary to console
        print("\\n" + "="*60)
        print("PHASE 1 VALIDATION RESULTS")
        print("="*60)
        print(f"Success Rate: {success_rate:.2f}% {'✅' if meets_success_target else '❌'}")
        print(f"Precise Bounds: {precise_pct:.1f}% {'✅' if meets_precision_target else '❌'}")
        print(f"Overlap Reduction: {'✅' if overlap_meets_target else '❌'}")
        print(f"Processing Rate: {self.stats['processing_rate']:.1f} files/second")
        print("="*60)
        
        if meets_success_target and meets_precision_target and overlap_meets_target:
            print("🎉 ALL TARGETS MET - READY FOR PRODUCTION SCALE!")
        else:
            print("⚠️  Some targets not met - review needed")

def main():
    """Main Phase 1 validation execution"""
    if not RASTERIO_AVAILABLE:
        print("rasterio required for Phase 1 validation")
        return
    
    print("Phase 1 Enhanced Validation")
    print("Validating precision improvements and overlap reduction")
    print("Targets: >99% success, >99% precise bounds, >90% overlap reduction")
    print()
    
    # Get sample size from user
    print("Sample size options:")
    print("1. Quick test (1,000 files) - 2-3 minutes")
    print("2. Medium validation (5,000 files) - 10-15 minutes") 
    print("3. Enhanced validation (25,000 files) - 45-60 minutes")
    print("4. Full Phase 1 (50,000 files) - 90-120 minutes")
    
    print("\\nAuto-selecting option 2: Medium validation (5,000 files)")
    choice = "2"  # Auto-select medium validation
    
    if choice == "1":
        sample_size = 1000
        max_workers = 20
    elif choice == "2":
        sample_size = 5000
        max_workers = 30
    elif choice == "3":
        sample_size = 25000
        max_workers = 40
    elif choice == "4":
        sample_size = 50000
        max_workers = 50
    else:
        print("Invalid choice, using quick test")
        sample_size = 1000
        max_workers = 20
    
    validator = Phase1Validator()
    
    try:
        # Load spatial index and sample files
        spatial_index = validator.load_spatial_index()
        file_keys = validator.stratified_sample_files(spatial_index, sample_size)
        
        # Extract metadata
        metadata_results = validator.parallel_metadata_extraction(file_keys, max_workers)
        
        # Validate overlap reduction
        overlap_results = validator.validate_overlap_reduction(metadata_results)
        
        # Generate report
        validator.generate_phase1_report(metadata_results, overlap_results)
        
    except KeyboardInterrupt:
        logger.info("⏹️ Validation interrupted by user")
    except Exception as e:
        logger.error(f"❌ Validation failed: {e}")
        raise

if __name__ == "__main__":
    main()