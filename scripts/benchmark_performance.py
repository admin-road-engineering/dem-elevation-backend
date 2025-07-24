"""
Performance Benchmark Script for Phase 2 Grouped Dataset Architecture

Tests the performance improvements achieved by smart dataset selection:
- Brisbane CBD: Target 316x faster (2,000 vs 631,556 files searched)
- Sydney Harbor: Target 42x faster (15,000 vs 631,556 files)
- Regional queries: Target 3-5x faster through geographic partitioning
"""
import time
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple
import statistics

# Add project root to path
import sys
sys.path.append(str(Path(__file__).parent.parent))

from src.smart_dataset_selector import SmartDatasetSelector

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PerformanceBenchmark:
    """Benchmark smart dataset selection vs flat index performance"""
    
    def __init__(self):
        self.config_dir = Path(__file__).parent.parent / "config"
        self.smart_selector = SmartDatasetSelector(self.config_dir)
        self.flat_index = self._load_flat_index()
        
        # Test coordinates for different scenarios
        self.test_coordinates = {
            "brisbane_cbd": (-27.4698, 153.0251),
            "sydney_harbor": (-33.8568, 151.2153),
            "melbourne_cbd": (-37.8136, 144.9631),
            "perth_city": (-31.9505, 115.8605),
            "adelaide_hills": (-34.9285, 138.6007),
            "cairns_coast": (-16.9186, 145.7781),
            "hobart_waterfront": (-42.8821, 147.3272),
            "canberra_parliament": (-35.3081, 149.1245),
            "gold_coast": (-28.0167, 153.4000),
            "newcastle": (-32.9283, 151.7817)
        }
    
    def _load_flat_index(self) -> Dict:
        """Load the flat spatial index for comparison"""
        flat_index_file = self.config_dir / "precise_spatial_index.json"
        if not flat_index_file.exists():
            logger.error("Flat spatial index not found for comparison")
            return {}
        
        with open(flat_index_file, 'r') as f:
            return json.load(f)
    
    def benchmark_flat_search(self, latitude: float, longitude: float) -> Tuple[List[Dict], float, int]:
        """Simulate flat index search (searches all files)"""
        start_time = time.time()
        
        matching_files = []
        all_files = self.flat_index.get("utm_zones", {}).get("geographic", {}).get("files", [])
        files_searched = len(all_files)
        
        # Search through all files (this is what the old system did)
        for file_info in all_files:
            bounds = file_info.get("bounds", {})
            min_lat = bounds.get("min_lat", 999)
            max_lat = bounds.get("max_lat", -999)
            min_lon = bounds.get("min_lon", 999)
            max_lon = bounds.get("max_lon", -999)
            
            if min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon:
                matching_files.append(file_info)
        
        duration = time.time() - start_time
        return matching_files, duration, files_searched
    
    def benchmark_smart_search(self, latitude: float, longitude: float) -> Tuple[List[Dict], float, int]:
        """Benchmark smart dataset selection search"""
        start_time = time.time()
        
        matching_files, datasets_searched = self.smart_selector.find_files_for_coordinate(latitude, longitude)
        
        # Calculate actual files searched
        files_searched = 0
        for dataset_id in datasets_searched:
            dataset_files = self.smart_selector.get_files_for_dataset(dataset_id)
            files_searched += len(dataset_files)
        
        duration = time.time() - start_time
        return matching_files, duration, files_searched
    
    def run_single_benchmark(self, location_name: str, latitude: float, longitude: float) -> Dict[str, Any]:
        """Run benchmark for a single coordinate"""
        logger.info(f"Benchmarking {location_name} ({latitude}, {longitude})")
        
        # Run multiple iterations for statistical accuracy
        flat_durations = []
        smart_durations = []
        
        iterations = 5
        
        for i in range(iterations):
            # Benchmark flat search
            flat_matches, flat_duration, flat_files_searched = self.benchmark_flat_search(latitude, longitude)
            flat_durations.append(flat_duration)
            
            # Benchmark smart search
            smart_matches, smart_duration, smart_files_searched = self.benchmark_smart_search(latitude, longitude)
            smart_durations.append(smart_duration)
        
        # Calculate statistics
        flat_avg = statistics.mean(flat_durations)
        smart_avg = statistics.mean(smart_durations)
        speedup = flat_avg / smart_avg if smart_avg > 0 else 0
        search_reduction = flat_files_searched / smart_files_searched if smart_files_searched > 0 else 0
        
        result = {
            "location": location_name,
            "coordinates": (latitude, longitude),
            "flat_search": {
                "avg_duration_ms": flat_avg * 1000,
                "files_searched": flat_files_searched,
                "matches_found": len(flat_matches)
            },
            "smart_search": {
                "avg_duration_ms": smart_avg * 1000,
                "files_searched": smart_files_searched,
                "matches_found": len(smart_matches)
            },
            "performance_improvement": {
                "speedup_factor": round(speedup, 1),
                "search_reduction_factor": round(search_reduction, 1),
                "time_saved_ms": (flat_avg - smart_avg) * 1000
            }
        }
        
        logger.info(f"  {location_name}: {speedup:.1f}x speedup, {search_reduction:.1f}x fewer files searched")
        return result
    
    def run_full_benchmark(self) -> Dict[str, Any]:
        """Run full benchmark suite"""
        logger.info("="*60)
        logger.info("🚀 PHASE 2 PERFORMANCE BENCHMARK")
        logger.info("   Grouped Dataset Architecture vs Flat Index")
        logger.info("="*60)
        
        results = []
        
        for location_name, (lat, lon) in self.test_coordinates.items():
            result = self.run_single_benchmark(location_name, lat, lon)
            results.append(result)
        
        # Calculate overall statistics
        speedups = [r["performance_improvement"]["speedup_factor"] for r in results]
        search_reductions = [r["performance_improvement"]["search_reduction_factor"] for r in results]
        
        summary = {
            "benchmark_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_locations_tested": len(results),
            "individual_results": results,
            "overall_performance": {
                "average_speedup": round(statistics.mean(speedups), 1),
                "max_speedup": round(max(speedups), 1),
                "min_speedup": round(min(speedups), 1),
                "average_search_reduction": round(statistics.mean(search_reductions), 1),
                "max_search_reduction": round(max(search_reductions), 1),
                "target_achievements": {
                    "brisbane_cbd_target": "316x speedup",
                    "brisbane_cbd_actual": f"{next(r['performance_improvement']['speedup_factor'] for r in results if r['location'] == 'brisbane_cbd')}x speedup",
                    "sydney_harbor_target": "42x speedup", 
                    "sydney_harbor_actual": f"{next(r['performance_improvement']['speedup_factor'] for r in results if r['location'] == 'sydney_harbor')}x speedup"
                }
            }
        }
        
        return summary
    
    def save_benchmark_results(self, results: Dict[str, Any]) -> None:
        """Save benchmark results to file"""
        output_file = self.config_dir / "phase2_performance_benchmark.json"
        
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"📊 Benchmark results saved to: {output_file}")
    
    def print_summary(self, results: Dict[str, Any]) -> None:
        """Print benchmark summary"""
        overall = results["overall_performance"]
        
        logger.info("="*60)
        logger.info("📈 BENCHMARK RESULTS SUMMARY")
        logger.info("="*60)
        logger.info(f"Average speedup: {overall['average_speedup']}x")
        logger.info(f"Maximum speedup: {overall['max_speedup']}x")
        logger.info(f"Average search reduction: {overall['average_search_reduction']}x fewer files")
        logger.info(f"Maximum search reduction: {overall['max_search_reduction']}x fewer files")
        logger.info("")
        logger.info("🎯 TARGET ACHIEVEMENTS:")
        for target, actual in overall["target_achievements"].items():
            if "target" in target:
                continue
            target_name = target.replace("_actual", "").replace("_", " ").title()
            logger.info(f"  {target_name}: {actual}")
        logger.info("="*60)

def main():
    """Main benchmark execution"""
    benchmark = PerformanceBenchmark()
    
    # Run the full benchmark suite
    results = benchmark.run_full_benchmark()
    
    # Save and display results
    benchmark.save_benchmark_results(results)
    benchmark.print_summary(results)
    
    # Check if targets were met
    brisbane_speedup = next(r['performance_improvement']['speedup_factor'] 
                           for r in results['individual_results'] 
                           if r['location'] == 'brisbane_cbd')
    sydney_speedup = next(r['performance_improvement']['speedup_factor'] 
                         for r in results['individual_results'] 
                         if r['location'] == 'sydney_harbor')
    
    logger.info("🏆 TARGET ASSESSMENT:")
    logger.info(f"  Brisbane CBD: {'✅ TARGET MET' if brisbane_speedup >= 300 else '⚠️ BELOW TARGET'} ({brisbane_speedup}x vs 316x target)")
    logger.info(f"  Sydney Harbor: {'✅ TARGET MET' if sydney_speedup >= 40 else '⚠️ BELOW TARGET'} ({sydney_speedup}x vs 42x target)")

if __name__ == "__main__":
    main()