#!/usr/bin/env python3
"""
Comprehensive Benchmarking Script
Phase 2 implementation for performance validation with fallback mechanism testing

Benchmarks S3 vs local vs API sources with comprehensive fallback chain validation
Addresses Gemini's recommendation for formalized benchmarking capabilities
"""

import os
import sys
import time
import json
import asyncio
import statistics
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from unittest.mock import patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from enhanced_source_selector import EnhancedSourceSelector
from config import Settings
import logging

@dataclass
class BenchmarkResult:
    """Result of a single benchmark test"""
    scenario: str
    coordinate: Tuple[float, float]
    source_used: Optional[str]
    elevation_value: Optional[float]
    response_time_ms: float
    success: bool
    error_details: Optional[str] = None
    files_searched: Optional[int] = None
    speedup_factor: Optional[str] = None

class ComprehensiveBenchmarker:
    """Comprehensive benchmarking of DEM service performance and fallback behavior"""
    
    def __init__(self):
        # Test coordinates representing different scenarios
        self.test_coordinates = {
            "brisbane_cbd": (-27.4698, 153.0251),      # Phase 3 optimized
            "sydney_harbor": (-33.8688, 151.2093),    # Major metro
            "melbourne_cbd": (-37.8136, 144.9631),    # Major metro
            "perth_city": (-31.9505, 115.8605),       # Regional metro
            "adelaide_city": (-34.9285, 138.6007),    # Regional metro
            "canberra_parliament": (-35.3081, 149.1244), # Specific dataset
            "rural_nsw": (-32.2, 148.6),              # Rural area
            "remote_outback": (-26.0, 134.0),         # Remote area (API only)
            "nz_auckland": (-36.8485, 174.7633),      # New Zealand
            "international": (40.7128, -74.0060)      # International (NYC)
        }
        
        self.benchmark_results: List[BenchmarkResult] = []
        self.iterations_per_test = 5
        
        # Configure logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
    async def _benchmark_single_request(self, coordinate: Tuple[float, float], 
                                       scenario: str, force_s3_failure: bool = False,
                                       force_gpxz_failure: bool = False,
                                       force_google_failure: bool = False) -> BenchmarkResult:
        """Benchmark a single elevation request"""
        
        start_time = time.time()
        
        try:
            # Create settings and selector
            settings = Settings()
            selector = EnhancedSourceSelector(
                dem_sources=settings.DEM_SOURCES,
                use_s3_sources=settings.USE_S3_SOURCES and not force_s3_failure,
                use_api_sources=settings.USE_API_SOURCES
            )
            
            # Apply failure scenarios
            if force_s3_failure:
                with patch.object(selector, 's3_source_manager') as mock_s3:
                    mock_s3.get_elevation_from_s3.return_value = None
                    
                    if force_gpxz_failure:
                        with patch.object(selector, 'gpxz_client') as mock_gpxz:
                            mock_gpxz.get_elevation.return_value = None
                            
                            if force_google_failure:
                                with patch.object(selector, 'google_elevation_client') as mock_google:
                                    mock_google.get_elevation.return_value = None
                                    elevation = await selector.get_elevation_with_resilience(
                                        coordinate[0], coordinate[1]
                                    )
                            else:
                                elevation = await selector.get_elevation_with_resilience(
                                    coordinate[0], coordinate[1]
                                )
                    else:
                        elevation = await selector.get_elevation_with_resilience(
                            coordinate[0], coordinate[1]
                        )
            else:
                # Normal operation
                elevation = await selector.get_elevation_with_resilience(
                    coordinate[0], coordinate[1]
                )
                
            response_time = (time.time() - start_time) * 1000
            
            # Determine source used and performance metrics
            source_used = "unknown"
            files_searched = None
            speedup_factor = None
            
            # Try to extract performance info if available
            if hasattr(selector, 'last_performance_info'):
                perf_info = selector.last_performance_info
                source_used = perf_info.get('source', 'unknown')
                files_searched = perf_info.get('files_searched')
                speedup_factor = perf_info.get('speedup_factor')
            elif elevation and isinstance(elevation, dict):
                source_used = elevation.get('source', 'api_fallback')
            elif elevation is not None:
                source_used = "s3_or_api"
                
            return BenchmarkResult(
                scenario=scenario,
                coordinate=coordinate,
                source_used=source_used,
                elevation_value=elevation if isinstance(elevation, (int, float)) else None,
                response_time_ms=response_time,
                success=elevation is not None,
                files_searched=files_searched,
                speedup_factor=speedup_factor
            )
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return BenchmarkResult(
                scenario=scenario,
                coordinate=coordinate,
                source_used=None,
                elevation_value=None,
                response_time_ms=response_time,
                success=False,
                error_details=str(e)
            )
            
    async def benchmark_normal_operations(self) -> List[BenchmarkResult]:
        """Benchmark normal operations across all test coordinates"""
        print("\n=== Benchmarking Normal Operations ===")
        
        results = []
        
        for location_name, coordinate in self.test_coordinates.items():
            print(f"\nTesting {location_name} ({coordinate[0]}, {coordinate[1]})")
            
            # Run multiple iterations for statistical accuracy
            iteration_results = []
            for i in range(self.iterations_per_test):
                result = await self._benchmark_single_request(
                    coordinate, f"normal_{location_name}"
                )
                iteration_results.append(result)
                
                print(f"  Iteration {i+1}: {result.response_time_ms:.2f}ms, "
                      f"source={result.source_used}, success={result.success}")
                      
            # Calculate statistics
            successful_results = [r for r in iteration_results if r.success]
            if successful_results:
                response_times = [r.response_time_ms for r in successful_results]
                avg_time = statistics.mean(response_times)
                median_time = statistics.median(response_times)
                
                # Create summary result
                summary_result = BenchmarkResult(
                    scenario=f"normal_{location_name}_summary",
                    coordinate=coordinate,
                    source_used=successful_results[0].source_used,
                    elevation_value=successful_results[0].elevation_value,
                    response_time_ms=avg_time,
                    success=True,
                    files_searched=successful_results[0].files_searched,
                    speedup_factor=successful_results[0].speedup_factor
                )
                
                print(f"  Summary: {avg_time:.2f}ms avg, {median_time:.2f}ms median")
                results.append(summary_result)
            else:
                # All iterations failed
                failed_result = iteration_results[0]  # Use first failure as representative
                failed_result.scenario = f"normal_{location_name}_summary"
                results.append(failed_result)
                print(f"  Summary: All iterations failed")
                
            results.extend(iteration_results)
            
        return results
        
    async def benchmark_fallback_scenarios(self) -> List[BenchmarkResult]:
        """Benchmark fallback scenarios with forced failures"""
        print("\n=== Benchmarking Fallback Scenarios ===")
        
        results = []
        test_coordinate = self.test_coordinates["brisbane_cbd"]  # Use optimized coordinate
        
        # Scenario 1: S3 failure -> GPXZ fallback
        print("\nTesting S3 failure -> GPXZ fallback")
        for i in range(self.iterations_per_test):
            result = await self._benchmark_single_request(
                test_coordinate, "s3_failure_gpxz_fallback", 
                force_s3_failure=True
            )
            results.append(result)
            print(f"  Iteration {i+1}: {result.response_time_ms:.2f}ms, "
                  f"source={result.source_used}, success={result.success}")
                  
        # Scenario 2: S3 + GPXZ failure -> Google fallback
        print("\nTesting S3 + GPXZ failure -> Google fallback")
        for i in range(self.iterations_per_test):
            result = await self._benchmark_single_request(
                test_coordinate, "s3_gpxz_failure_google_fallback",
                force_s3_failure=True, force_gpxz_failure=True
            )
            results.append(result)
            print(f"  Iteration {i+1}: {result.response_time_ms:.2f}ms, "
                  f"source={result.source_used}, success={result.success}")
                  
        # Scenario 3: Complete failure
        print("\nTesting complete failure (all sources)")
        for i in range(self.iterations_per_test):
            result = await self._benchmark_single_request(
                test_coordinate, "complete_failure",
                force_s3_failure=True, force_gpxz_failure=True, force_google_failure=True
            )
            results.append(result)
            print(f"  Iteration {i+1}: {result.response_time_ms:.2f}ms, "
                  f"source={result.source_used}, success={result.success}")
                  
        return results
        
    async def benchmark_performance_optimization(self) -> List[BenchmarkResult]:
        """Benchmark performance optimization scenarios"""
        print("\n=== Benchmarking Performance Optimization ===")
        
        results = []
        
        # Focus on Phase 3 optimized coordinates
        optimized_coordinates = {
            "brisbane_metro": (-27.4698, 153.0251),
            "sydney_metro": (-33.8688, 151.2093),
        }
        
        for location_name, coordinate in optimized_coordinates.items():
            print(f"\nTesting performance optimization for {location_name}")
            
            # Test with S3 indexes enabled (should be fast)
            s3_results = []
            for i in range(self.iterations_per_test):
                result = await self._benchmark_single_request(
                    coordinate, f"s3_optimized_{location_name}"
                )
                s3_results.append(result)
                
            # Test with S3 disabled (fallback to API)
            api_results = []
            for i in range(self.iterations_per_test):
                result = await self._benchmark_single_request(
                    coordinate, f"api_fallback_{location_name}",
                    force_s3_failure=True
                )
                api_results.append(result)
                
            # Calculate performance comparison
            successful_s3 = [r for r in s3_results if r.success]
            successful_api = [r for r in api_results if r.success]
            
            if successful_s3 and successful_api:
                s3_avg = statistics.mean([r.response_time_ms for r in successful_s3])
                api_avg = statistics.mean([r.response_time_ms for r in successful_api])
                improvement_factor = api_avg / s3_avg if s3_avg > 0 else 1
                
                print(f"  S3 optimized: {s3_avg:.2f}ms avg")
                print(f"  API fallback: {api_avg:.2f}ms avg")
                print(f"  Improvement factor: {improvement_factor:.1f}x")
                
            results.extend(s3_results)
            results.extend(api_results)
            
        return results
        
    def analyze_benchmark_results(self, results: List[BenchmarkResult]) -> Dict[str, Any]:
        """Analyze benchmark results and generate performance report"""
        
        analysis = {
            "summary": {
                "total_tests": len(results),
                "successful_tests": sum(1 for r in results if r.success),
                "success_rate": 0,
                "benchmark_timestamp": datetime.utcnow().isoformat()
            },
            "performance_metrics": {
                "response_times": {},
                "source_usage": {},
                "speedup_analysis": {}
            },
            "fallback_reliability": {
                "s3_to_gpxz": {"tests": 0, "successes": 0, "avg_time_ms": 0},
                "gpxz_to_google": {"tests": 0, "successes": 0, "avg_time_ms": 0},
                "complete_failure": {"tests": 0, "successes": 0}
            },
            "geographic_coverage": {},
            "recommendations": []
        }
        
        if results:
            successful_results = [r for r in results if r.success]
            analysis["summary"]["success_rate"] = len(successful_results) / len(results) * 100
            
            # Response time analysis
            if successful_results:
                response_times = [r.response_time_ms for r in successful_results]
                analysis["performance_metrics"]["response_times"] = {
                    "avg_ms": statistics.mean(response_times),
                    "median_ms": statistics.median(response_times),
                    "min_ms": min(response_times),
                    "max_ms": max(response_times),
                    "p95_ms": sorted(response_times)[int(len(response_times) * 0.95)]
                }
                
            # Source usage analysis
            for result in successful_results:
                source = result.source_used or "unknown"
                if source not in analysis["performance_metrics"]["source_usage"]:
                    analysis["performance_metrics"]["source_usage"][source] = 0
                analysis["performance_metrics"]["source_usage"][source] += 1
                
            # Fallback reliability analysis
            for result in results:
                if "s3_failure_gpxz_fallback" in result.scenario:
                    analysis["fallback_reliability"]["s3_to_gpxz"]["tests"] += 1
                    if result.success:
                        analysis["fallback_reliability"]["s3_to_gpxz"]["successes"] += 1
                        
                elif "s3_gpxz_failure_google_fallback" in result.scenario:
                    analysis["fallback_reliability"]["gpxz_to_google"]["tests"] += 1
                    if result.success:
                        analysis["fallback_reliability"]["gpxz_to_google"]["successes"] += 1
                        
                elif "complete_failure" in result.scenario:
                    analysis["fallback_reliability"]["complete_failure"]["tests"] += 1
                    if result.success:
                        analysis["fallback_reliability"]["complete_failure"]["successes"] += 1
                        
            # Geographic coverage analysis
            for location, coordinate in self.test_coordinates.items():
                location_results = [r for r in results if r.coordinate == coordinate and r.success]
                if location_results:
                    avg_time = statistics.mean([r.response_time_ms for r in location_results])
                    analysis["geographic_coverage"][location] = {
                        "tests": len([r for r in results if r.coordinate == coordinate]),
                        "successes": len(location_results),
                        "avg_response_time_ms": avg_time,
                        "primary_source": location_results[0].source_used
                    }
                    
        # Generate recommendations
        perf_metrics = analysis["performance_metrics"]["response_times"]
        if perf_metrics and perf_metrics["avg_ms"] > 1000:
            analysis["recommendations"].append({
                "priority": "MEDIUM",
                "issue": f"High average response time ({perf_metrics['avg_ms']:.0f}ms)",
                "action": "Consider CloudFront optimization or S3 Transfer Acceleration"
            })
            
        fallback_success_rate = 0
        fallback_tests = analysis["fallback_reliability"]["s3_to_gpxz"]["tests"]
        fallback_successes = analysis["fallback_reliability"]["s3_to_gpxz"]["successes"]
        
        if fallback_tests > 0:
            fallback_success_rate = fallback_successes / fallback_tests * 100
            
        if fallback_success_rate < 80:
            analysis["recommendations"].append({
                "priority": "HIGH",
                "issue": f"Low fallback success rate ({fallback_success_rate:.1f}%)",
                "action": "Check GPXZ and Google API credentials and rate limits"
            })
            
        if analysis["summary"]["success_rate"] < 95:
            analysis["recommendations"].append({
                "priority": "HIGH",
                "issue": f"Low overall success rate ({analysis['summary']['success_rate']:.1f}%)",
                "action": "Review service configuration and external dependencies"
            })
            
        return analysis
        
    async def run_comprehensive_benchmark(self) -> Dict[str, Any]:
        """Run comprehensive benchmark suite"""
        print("Starting Comprehensive DEM Service Benchmark...")
        print(f"Test coordinates: {len(self.test_coordinates)} locations")
        print(f"Iterations per test: {self.iterations_per_test}")
        print(f"Benchmark timestamp: {datetime.utcnow().isoformat()}")
        
        all_results = []
        
        try:
            # Phase 1: Normal operations
            normal_results = await self.benchmark_normal_operations()
            all_results.extend(normal_results)
            self.benchmark_results.extend(normal_results)
            
            # Phase 2: Fallback scenarios
            fallback_results = await self.benchmark_fallback_scenarios()
            all_results.extend(fallback_results)
            self.benchmark_results.extend(fallback_results)
            
            # Phase 3: Performance optimization
            optimization_results = await self.benchmark_performance_optimization()
            all_results.extend(optimization_results)
            self.benchmark_results.extend(optimization_results)
            
            # Analyze results
            analysis = self.analyze_benchmark_results(all_results)
            
            # Display summary
            print(f"\n=== Benchmark Summary ===")
            print(f"Total tests: {analysis['summary']['total_tests']}")
            print(f"Success rate: {analysis['summary']['success_rate']:.1f}%")
            
            if analysis["performance_metrics"]["response_times"]:
                rt = analysis["performance_metrics"]["response_times"]
                print(f"Response times: {rt['avg_ms']:.2f}ms avg, {rt['p95_ms']:.2f}ms P95")
                
            print(f"\nFallback Reliability:")
            fb = analysis["fallback_reliability"]
            if fb["s3_to_gpxz"]["tests"] > 0:
                success_rate = fb["s3_to_gpxz"]["successes"] / fb["s3_to_gpxz"]["tests"] * 100
                print(f"  S3 -> GPXZ: {success_rate:.1f}% ({fb['s3_to_gpxz']['successes']}/{fb['s3_to_gpxz']['tests']})")
                
            if fb["gpxz_to_google"]["tests"] > 0:
                success_rate = fb["gpxz_to_google"]["successes"] / fb["gpxz_to_google"]["tests"] * 100
                print(f"  GPXZ -> Google: {success_rate:.1f}% ({fb['gpxz_to_google']['successes']}/{fb['gpxz_to_google']['tests']})")
                
            if analysis["recommendations"]:
                print(f"\nRecommendations:")
                for rec in analysis["recommendations"]:
                    print(f"  [{rec['priority']}] {rec['issue']}: {rec['action']}")
                    
            return analysis
            
        except Exception as e:
            print(f"\nBenchmark suite failed: {e}")
            return {"error": str(e), "timestamp": datetime.utcnow().isoformat()}

def main():
    """Main entry point for comprehensive benchmarking"""
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("""
Comprehensive DEM Service Benchmarking Script

Usage:
    python scripts/comprehensive_benchmark.py [--json] [--iterations N]

Options:
    --json          Output results in JSON format
    --iterations N  Number of iterations per test (default: 5)
    --help         Show this help message

This script benchmarks:
1. Normal operations across 10 global test coordinates
2. Fallback scenarios (S3 -> GPXZ -> Google)
3. Performance optimization (S3 vs API sources)
4. Geographic coverage and source reliability

Addresses Gemini's recommendation for formalized benchmarking capabilities.
        """)
        return
        
    async def run_benchmark():
        benchmarker = ComprehensiveBenchmarker()
        
        # Check for custom iterations
        if "--iterations" in sys.argv:
            iter_pos = sys.argv.index("--iterations")
            if iter_pos + 1 < len(sys.argv):
                try:
                    benchmarker.iterations_per_test = int(sys.argv[iter_pos + 1])
                except ValueError:
                    print("Invalid iterations value")
                    sys.exit(3)
                    
        try:
            results = await benchmarker.run_comprehensive_benchmark()
            
            # JSON output option
            if "--json" in sys.argv:
                print(json.dumps(results, indent=2, default=str))
                
            # Exit with appropriate code based on success rate
            success_rate = results.get("summary", {}).get("success_rate", 0)
            if success_rate >= 95:
                sys.exit(0)  # Excellent
            elif success_rate >= 80:
                sys.exit(1)  # Good but improvable
            else:
                sys.exit(2)  # Concerning issues
                
        except KeyboardInterrupt:
            print("\nBenchmark interrupted by user")
            sys.exit(3)
        except Exception as e:
            print(f"\nUnexpected error: {e}")
            sys.exit(4)
            
    # Run async benchmark
    asyncio.run(run_benchmark())

if __name__ == "__main__":
    main()