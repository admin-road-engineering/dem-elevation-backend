"""
Performance Outlier Analysis - Phase 2 Diagnostic Tool
Investigates why certain locations have different performance patterns
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Tuple
import sys

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.smart_dataset_selector import SmartDatasetSelector
from src.policy_based_selector import PolicyBasedSelector, SelectionPolicy

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PerformanceOutlierAnalyzer:
    """Analyzes performance outliers and explains dataset selection patterns"""
    
    def __init__(self):
        self.config_dir = Path(__file__).parent.parent / "config"
        self.smart_selector = SmartDatasetSelector(self.config_dir)
        self.policy_selector = PolicyBasedSelector(self.config_dir, SelectionPolicy.FASTEST)
        
        # Load benchmark results for analysis
        self.benchmark_data = self._load_benchmark_results()
    
    def _load_benchmark_results(self) -> Dict:
        """Load the latest benchmark results"""
        benchmark_file = self.config_dir / "phase2_performance_benchmark.json"
        if not benchmark_file.exists():
            logger.warning("No benchmark results found")
            return {}
        
        with open(benchmark_file, 'r') as f:
            return json.load(f)
    
    def analyze_location_performance(self, location_name: str, latitude: float, longitude: float) -> Dict[str, Any]:
        """Comprehensive analysis of why a location has specific performance characteristics"""
        
        logger.info(f"Analyzing performance patterns for {location_name}")
        
        # Get dataset selection details
        dataset_matches = self.smart_selector.select_datasets_for_coordinate(latitude, longitude)
        enhanced_matches = self.policy_selector.select_datasets_with_policy(latitude, longitude)
        
        # Find matching files
        matching_files, datasets_searched = self.smart_selector.find_files_for_coordinate(latitude, longitude)
        
        # Get benchmark data for this location
        benchmark_result = None
        if self.benchmark_data:
            for result in self.benchmark_data.get("individual_results", []):
                if result.get("location") == location_name:
                    benchmark_result = result
                    break
        
        # Analyze why this location has its specific performance pattern
        analysis = {
            "location": location_name,
            "coordinates": {"latitude": latitude, "longitude": longitude},
            "performance_analysis": self._analyze_performance_pattern(benchmark_result, dataset_matches, datasets_searched),
            "dataset_selection": {
                "datasets_considered": len(dataset_matches),
                "datasets_searched": datasets_searched,
                "files_found": len(matching_files),
                "selection_confidence": dataset_matches[0].confidence_score if dataset_matches else 0.0
            },
            "geographic_factors": self._analyze_geographic_factors(latitude, longitude, dataset_matches),
            "dataset_characteristics": self._analyze_dataset_characteristics(dataset_matches),
            "optimization_opportunities": self._identify_optimization_opportunities(benchmark_result, dataset_matches),
            "detailed_dataset_analysis": enhanced_matches[:3]  # Top 3 with detailed scoring
        }
        
        return analysis
    
    def _analyze_performance_pattern(self, benchmark_result: Dict, dataset_matches: List, datasets_searched: List[str]) -> Dict[str, Any]:
        """Analyze the performance pattern and explain the factors"""
        if not benchmark_result:
            return {"status": "No benchmark data available"}
        
        speedup = benchmark_result.get("performance_improvement", {}).get("speedup_factor", 0)
        files_searched = benchmark_result.get("smart_search", {}).get("files_searched", 0)
        
        # Categorize performance
        if speedup >= 50:
            performance_category = "excellent"
            explanation = "Very high speedup due to small, specific dataset selection"
        elif speedup >= 20:
            performance_category = "very_good"
            explanation = "Good speedup with targeted dataset selection"
        elif speedup >= 10:
            performance_category = "good"
            explanation = "Moderate speedup, some efficiency gained"
        elif speedup >= 5:
            performance_category = "fair"
            explanation = "Limited speedup, large datasets still being searched"
        else:
            performance_category = "poor"
            explanation = "Minimal speedup, optimization needed"
        
        # Identify specific factors
        factors = []
        if files_searched > 100000:
            factors.append(f"Large dataset search ({files_searched:,} files)")
        if len(datasets_searched) > 1:
            factors.append(f"Multiple datasets searched ({len(datasets_searched)})")
        if len(dataset_matches) > 5:
            factors.append(f"Many candidate datasets ({len(dataset_matches)})")
        
        return {
            "performance_category": performance_category,
            "speedup_factor": speedup,
            "files_searched": files_searched,
            "explanation": explanation,
            "contributing_factors": factors
        }
    
    def _analyze_geographic_factors(self, latitude: float, longitude: float, dataset_matches: List) -> Dict[str, Any]:
        """Analyze geographic factors affecting performance"""
        
        # Determine general region
        if -29 <= latitude <= -25 and 150 <= longitude <= 155:
            region = "Southeast Queensland (Brisbane area)"
            coverage_notes = "High-density LiDAR coverage, multiple overlapping datasets"
        elif -34 <= latitude <= -30 and 150 <= longitude <= 155:
            region = "New South Wales Coast (Sydney area)"
            coverage_notes = "Good LiDAR coverage along coast, some inland gaps"
        elif -39 <= latitude <= -35 and 144 <= longitude <= 150:
            region = "Victoria (Melbourne area)"
            coverage_notes = "Victoria-specific datasets with GA national fallback"
        elif -32 <= latitude <= -28 and 115 <= longitude <= 120:
            region = "Western Australia (Perth area)"
            coverage_notes = "Limited specific coverage, relies on national datasets"
        elif -36 <= latitude <= -34 and 138 <= longitude <= 140:
            region = "South Australia (Adelaide area)"
            coverage_notes = "National GA coverage, fewer specific datasets"
        elif -44 <= latitude <= -40 and 144 <= longitude <= 149:
            region = "Tasmania"
            coverage_notes = "Tasmania-specific ELVIS dataset available"
        elif -37 <= latitude <= -34 and 148 <= longitude <= 150:
            region = "Australian Capital Territory"
            coverage_notes = "Small, highly specific ACT dataset - excellent performance"
        else:
            region = "Other/Remote area"
            coverage_notes = "Limited coverage, may rely on lower-resolution national data"
        
        # Count datasets by bounds overlap
        datasets_in_bounds = 0
        for match in dataset_matches:
            bounds = match.dataset_info.get("bounds", {})
            if bounds:
                min_lat = bounds.get("min_lat", 999)
                max_lat = bounds.get("max_lat", -999)
                min_lon = bounds.get("min_lon", 999)
                max_lon = bounds.get("max_lon", -999)
                
                if min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon:
                    datasets_in_bounds += 1
        
        return {
            "region": region,
            "coverage_characteristics": coverage_notes,
            "datasets_with_bounds_match": datasets_in_bounds,
            "total_candidate_datasets": len(dataset_matches),
            "geographic_specificity": "high" if datasets_in_bounds <= 2 else "moderate" if datasets_in_bounds <= 4 else "low"
        }
    
    def _analyze_dataset_characteristics(self, dataset_matches: List) -> Dict[str, Any]:
        """Analyze characteristics of selected datasets"""
        if not dataset_matches:
            return {"status": "No datasets selected"}
        
        # Analyze top dataset
        top_dataset = dataset_matches[0]
        
        characteristics = {
            "primary_dataset": {
                "id": top_dataset.dataset_id,
                "name": top_dataset.dataset_info.get("name"),
                "file_count": top_dataset.file_count,
                "confidence": top_dataset.confidence_score,
                "resolution_m": top_dataset.dataset_info.get("resolution_m"),
                "data_type": top_dataset.dataset_info.get("data_type"),
                "provider": top_dataset.dataset_info.get("provider")
            },
            "dataset_size_analysis": self._categorize_dataset_size(top_dataset.file_count),
            "resolution_analysis": self._categorize_resolution(top_dataset.dataset_info.get("resolution_m", 30)),
            "alternatives_available": len(dataset_matches) - 1
        }
        
        return characteristics
    
    def _categorize_dataset_size(self, file_count: int) -> str:
        """Categorize dataset size impact on performance"""
        if file_count < 5000:
            return "very_small - excellent query performance"
        elif file_count < 20000:
            return "small - good query performance"
        elif file_count < 50000:
            return "medium - moderate query performance"
        elif file_count < 100000:
            return "large - slower query performance"
        else:
            return "very_large - significant performance impact"
    
    def _categorize_resolution(self, resolution_m: float) -> str:
        """Categorize resolution quality"""
        if resolution_m <= 0.5:
            return "ultra_high - 50cm or better"
        elif resolution_m <= 1.0:
            return "high - 1m resolution"
        elif resolution_m <= 5.0:
            return "medium - up to 5m resolution"
        elif resolution_m <= 30.0:
            return "standard - up to 30m resolution"
        else:
            return "low - greater than 30m resolution"
    
    def _identify_optimization_opportunities(self, benchmark_result: Dict, dataset_matches: List) -> List[str]:
        """Identify specific optimization opportunities"""
        opportunities = []
        
        if not benchmark_result:
            return ["No benchmark data available for optimization analysis"]
        
        speedup = benchmark_result.get("performance_improvement", {}).get("speedup_factor", 0)
        files_searched = benchmark_result.get("smart_search", {}).get("files_searched", 0)
        
        # Performance-based recommendations
        if speedup < 10:
            opportunities.append("Consider tighter geographic bounds for primary dataset")
        
        if files_searched > 50000:
            opportunities.append("Dataset could benefit from geographic subdivision")
        
        if len(dataset_matches) > 5:
            opportunities.append("Too many candidate datasets - refine selection criteria")
        
        # Dataset-specific recommendations
        if dataset_matches:
            top_dataset = dataset_matches[0]
            if top_dataset.confidence_score < 0.7:
                opportunities.append("Low confidence in primary dataset - verify geographic bounds")
            
            if top_dataset.file_count > 100000:
                opportunities.append("Primary dataset is very large - consider splitting by sub-region")
        
        # Geographic-specific recommendations
        if "qld_elvis" in [m.dataset_id for m in dataset_matches[:2]]:
            opportunities.append("Queensland coordinates could benefit from Brisbane/Gold Coast subdatasets")
        
        if "nsw_elvis" in [m.dataset_id for m in dataset_matches[:2]]:
            opportunities.append("NSW coordinates could benefit from Sydney/Newcastle subdatasets")
        
        return opportunities if opportunities else ["Performance is well-optimized for this location"]

def main():
    """Run performance outlier analysis on key locations"""
    analyzer = PerformanceOutlierAnalyzer()
    
    # Analyze key locations from benchmark
    locations_to_analyze = [
        ("brisbane_cbd", -27.4698, 153.0251),
        ("sydney_harbor", -33.8568, 151.2153),
        ("melbourne_cbd", -37.8136, 144.9631),
        ("canberra_parliament", -35.3081, 149.1245),  # Best performer
        ("cairns_coast", -16.9186, 145.7781),        # Poorest performer
    ]
    
    logger.info("="*80)
    logger.info("🔍 PHASE 2 PERFORMANCE OUTLIER ANALYSIS")
    logger.info("="*80)
    
    results = {}
    
    for location_name, lat, lon in locations_to_analyze:
        logger.info(f"\n📍 Analyzing {location_name.replace('_', ' ').title()}")
        logger.info("-" * 50)
        
        analysis = analyzer.analyze_location_performance(location_name, lat, lon)
        results[location_name] = analysis
        
        # Print key findings
        perf = analysis["performance_analysis"]
        geo = analysis["geographic_factors"]
        dataset = analysis["dataset_characteristics"]
        
        logger.info(f"Performance: {perf.get('performance_category', 'unknown').upper()} "
                   f"({perf.get('speedup_factor', 0)}x speedup)")
        logger.info(f"Region: {geo.get('region', 'unknown')}")
        logger.info(f"Primary Dataset: {dataset.get('primary_dataset', {}).get('name', 'unknown')} "
                   f"({dataset.get('primary_dataset', {}).get('file_count', 0):,} files)")
        logger.info(f"Explanation: {perf.get('explanation', 'No explanation available')}")
        
        # Show top optimization opportunity
        opportunities = analysis.get("optimization_opportunities", [])
        if opportunities:
            logger.info(f"Top Opportunity: {opportunities[0]}")
    
    # Save detailed analysis
    output_file = analyzer.config_dir / "performance_outlier_analysis.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    logger.info(f"\n📊 Detailed analysis saved to: {output_file}")
    
    # Summary insights
    logger.info("\n" + "="*80)
    logger.info("🎯 KEY INSIGHTS")
    logger.info("="*80)
    
    # Identify patterns
    excellent_performers = [name for name, data in results.items() 
                          if data["performance_analysis"].get("speedup_factor", 0) >= 50]
    poor_performers = [name for name, data in results.items() 
                      if data["performance_analysis"].get("speedup_factor", 0) < 10]
    
    if excellent_performers:
        logger.info(f"🏆 Excellent Performers: {', '.join(excellent_performers)}")
        logger.info("    Pattern: Small, geographically specific datasets (< 5k files)")
    
    if poor_performers:
        logger.info(f"⚠️  Needs Optimization: {', '.join(poor_performers)}")
        logger.info("    Pattern: Large datasets or multiple dataset searches")
    
    logger.info("\n💡 PHASE 3 RECOMMENDATIONS:")
    logger.info("   1. Subdivide large datasets (QLD, NSW) by metro regions")
    logger.info("   2. Implement Brisbane/Sydney/Melbourne specific subdatasets")
    logger.info("   3. Add geographic proximity weighting to confidence scoring")
    logger.info("   4. Consider population density as a dataset subdivision factor")

if __name__ == "__main__":
    main()