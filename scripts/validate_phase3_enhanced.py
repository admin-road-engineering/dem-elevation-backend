#!/usr/bin/env python3
"""
Enhanced Phase 3 Validation with Performance Metrics
Tests all Phase 3 enhancements with S3 latency simulation and detailed metrics
"""

import sys
import time
import logging
import statistics
from pathlib import Path
from typing import Dict, List, Any, Tuple
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from campaign_dataset_selector import CampaignDatasetSelector

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def simulate_s3_latency() -> float:
    """Simulate realistic S3 latency (10-50ms)"""
    import random
    return random.uniform(0.01, 0.05)  # 10-50ms

def test_resolution_prioritization():
    """Test that resolution scoring works correctly"""
    logger.info("\n🔬 Testing Resolution Prioritization")
    logger.info("-" * 50)
    
    selector = CampaignDatasetSelector()
    
    # Test scenarios: 50cm LiDAR vs 30m DEM
    test_campaigns = [
        {"resolution_m": 0.5, "campaign_year": "2010", "provider": "elvis"},  # 50cm old
        {"resolution_m": 30.0, "campaign_year": "2023", "provider": "ga"},   # 30m new
        {"resolution_m": 1.0, "campaign_year": "2020", "provider": "csiro"}, # 1m recent
    ]
    
    scores = []
    for i, campaign in enumerate(test_campaigns):
        res_score = selector._calculate_resolution_score(campaign)
        temp_score = selector._calculate_temporal_score(campaign)
        prov_score = selector._calculate_provider_score(campaign)
        
        total_score = (res_score * selector.resolution_weight +
                      temp_score * selector.temporal_weight +
                      prov_score * selector.provider_weight)
        
        scores.append((i, total_score, campaign))
        logger.info(f"Campaign {i+1}: {campaign['resolution_m']}m {campaign['campaign_year']} -> Score: {total_score:.3f}")
    
    # Sort by score
    scores.sort(key=lambda x: x[1], reverse=True)
    best_campaign = scores[0][2]
    
    # Should prioritize high resolution despite older date
    success = best_campaign["resolution_m"] <= 1.0  # High-res should win
    logger.info(f"✅ Resolution priority test: {'PASS' if success else 'FAIL'}")
    logger.info(f"Best campaign: {best_campaign['resolution_m']}m from {best_campaign['campaign_year']}")
    
    return success

def test_coordinate_validation():
    """Test input coordinate validation"""
    logger.info("\n🔍 Testing Coordinate Validation")
    logger.info("-" * 50)
    
    selector = CampaignDatasetSelector()
    
    # Valid coordinates
    try:
        selector.select_campaigns_for_coordinate(-27.4698, 153.0251)
        logger.info("✅ Valid coordinates accepted")
        valid_test = True
    except ValueError:
        logger.error("❌ Valid coordinates rejected")
        valid_test = False
    
    # Invalid coordinates
    try:
        selector.select_campaigns_for_coordinate(91.0, 153.0251)  # Invalid lat
        logger.error("❌ Invalid coordinates accepted")
        invalid_test = False
    except ValueError:
        logger.info("✅ Invalid coordinates properly rejected")
        invalid_test = True
    
    return valid_test and invalid_test

def benchmark_performance_with_latency(num_queries: int = 100) -> Dict[str, Any]:
    """Benchmark performance with simulated S3 latency"""
    logger.info(f"\n⚡ Performance Benchmark ({num_queries} queries)")
    logger.info("-" * 50)
    
    selector = CampaignDatasetSelector()
    
    # Test coordinates across different regions
    test_coords = [
        (-27.4698, 153.0251, "Brisbane CBD"),      # Tiled
        (-33.8568, 151.2153, "Sydney Harbor"),    # Campaign  
        (-28.0167, 153.4000, "Gold Coast"),       # Tiled
        (-27.6397, 153.1086, "Logan"),            # Tiled
        (-37.8136, 144.9631, "Melbourne CBD"),    # Campaign
    ]
    
    results = {}
    
    for lat, lon, location in test_coords:
        logger.info(f"\nTesting {location} ({lat}, {lon})")
        
        query_times = []
        files_searched = []
        datasets_used = []
        
        for i in range(num_queries // len(test_coords)):
            start_time = time.time()
            
            # Add simulated S3 latency
            time.sleep(simulate_s3_latency())
            
            try:
                files, campaigns = selector.find_files_for_coordinate(lat, lon)
                
                end_time = time.time()
                query_time = end_time - start_time
                query_times.append(query_time)
                files_searched.append(len(files))
                datasets_used.extend(campaigns)
                
            except Exception as e:
                logger.error(f"Query failed: {e}")
                continue
        
        if query_times:
            results[location] = {
                "avg_query_time": statistics.mean(query_times),
                "p95_query_time": statistics.quantiles(query_times, n=20)[18] if len(query_times) > 1 else query_times[0],
                "min_query_time": min(query_times),
                "max_query_time": max(query_times),
                "avg_files_found": statistics.mean(files_searched) if files_searched else 0,
                "unique_datasets": len(set(datasets_used)),
                "queries_completed": len(query_times)
            }
            
            logger.info(f"  Avg time: {results[location]['avg_query_time']*1000:.1f}ms")
            logger.info(f"  P95 time: {results[location]['p95_query_time']*1000:.1f}ms")
            logger.info(f"  Avg files: {results[location]['avg_files_found']:.1f}")
    
    return results

def validate_all_success_criteria() -> Dict[str, bool]:
    """Validate all Phase 3 success criteria"""
    logger.info("\n🎯 Validating All Success Criteria")
    logger.info("=" * 60)
    
    selector = CampaignDatasetSelector()
    criteria_results = {}
    
    # 1. Performance targets
    logger.info("\n1. Performance Targets")
    
    # Brisbane CBD test
    files, campaigns = selector.find_files_for_coordinate(-27.4698, 153.0251)
    brisbane_files = len(files) if files else 0
    brisbane_speedup = 216106 / max(1, brisbane_files)
    criteria_results["brisbane_100x"] = brisbane_speedup >= 100
    logger.info(f"  Brisbane speedup: {brisbane_speedup:.0f}x (target: >100x) {'✅' if criteria_results['brisbane_100x'] else '❌'}")
    
    # Sydney Harbor test  
    files, campaigns = selector.find_files_for_coordinate(-33.8568, 151.2153)
    sydney_files = len(files) if files else 0
    sydney_speedup = 80686 / max(1, sydney_files) if sydney_files > 0 else 0
    criteria_results["sydney_42x"] = sydney_speedup >= 42
    logger.info(f"  Sydney speedup: {sydney_speedup:.0f}x (target: >42x) {'✅' if criteria_results['sydney_42x'] else '❌'}")
    
    # 2. Data quality (resolution prioritization)
    logger.info("\n2. Data Quality")
    criteria_results["resolution_priority"] = test_resolution_prioritization()
    
    # 3. Error handling
    logger.info("\n3. Error Handling")
    criteria_results["coordinate_validation"] = test_coordinate_validation()
    
    # 4. Fallback reliability (check fallback rates)
    logger.info("\n4. Fallback Reliability")
    # Test multiple coordinates to check fallback usage
    fallback_count = 0
    total_tests = 20
    
    test_coordinates = [
        (-27.4698, 153.0251), (-33.8568, 151.2153), (-28.0167, 153.4000),
        (-27.6397, 153.1086), (-37.8136, 144.9631), (-19.2590, 146.8169),
        (-34.9285, 138.6007), (-42.8821, 147.3272), (-12.4634, 130.8456),
        (-31.9505, 115.8605), (-35.2809, 149.1300), (-26.2041, 28.0473),
        (-29.7497, 151.1081), (-23.6980, 133.8807), (-16.2861, 145.7781),
        (-20.2319, 118.5084), (-25.2744, 133.7751), (-32.0569, 115.7470),
        (-41.4332, 147.1441), (-14.4932, 132.5501)
    ]
    
    for lat, lon in test_coordinates[:total_tests]:
        try:
            files, campaigns = selector.find_files_for_coordinate(lat, lon)
            if not files:  # No files found = fallback needed
                fallback_count += 1
        except Exception:
            fallback_count += 1
    
    fallback_rate = fallback_count / total_tests
    criteria_results["fallback_low"] = fallback_rate <= 0.1  # <10% fallback rate
    logger.info(f"  Fallback rate: {fallback_rate*100:.1f}% (target: <10%) {'✅' if criteria_results['fallback_low'] else '❌'}")
    
    # 5. Performance benchmarks
    logger.info("\n5. Performance Benchmarks")
    perf_results = benchmark_performance_with_latency(20)  # Smaller sample for testing
    
    # Check if P95 < 100ms for any location
    p95_acceptable = any(r["p95_query_time"] < 0.1 for r in perf_results.values())
    criteria_results["p95_performance"] = p95_acceptable
    logger.info(f"  P95 < 100ms: {'✅' if p95_acceptable else '❌'}")
    
    return criteria_results

def generate_final_report(criteria_results: Dict[str, bool], perf_results: Dict[str, Any]):
    """Generate comprehensive final report"""
    logger.info("\n" + "=" * 60)
    logger.info("FINAL PHASE 3 AUDIT RESPONSE REPORT")
    logger.info("=" * 60)
    
    total_criteria = len(criteria_results)
    passed_criteria = sum(criteria_results.values())
    success_rate = (passed_criteria / total_criteria) * 100
    
    logger.info(f"\nSUCCESS CRITERIA: {passed_criteria}/{total_criteria} ({success_rate:.1f}%)")
    
    for criterion, passed in criteria_results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"  {criterion}: {status}")
    
    logger.info(f"\nPERFORMANCE SUMMARY:")
    for location, metrics in perf_results.items():
        logger.info(f"  {location}:")
        logger.info(f"    Avg: {metrics['avg_query_time']*1000:.1f}ms")
        logger.info(f"    P95: {metrics['p95_query_time']*1000:.1f}ms")
        logger.info(f"    Files: {metrics['avg_files_found']:.1f}")
    
    logger.info(f"\n🏆 AUDIT RESPONSE STATUS:")
    if success_rate >= 90:
        logger.info("✅ EXCELLENT - Ready for production deployment")
    elif success_rate >= 80:
        logger.info("⚠️  GOOD - Minor refinements needed")
    else:
        logger.info("❌ NEEDS WORK - Significant issues to address")
    
    # Save detailed report
    report = {
        "validation_timestamp": datetime.now().isoformat(),
        "audit_response_version": "Phase 3 Enhanced",
        "success_criteria": criteria_results,
        "performance_metrics": perf_results,
        "overall_success_rate": success_rate,
        "ready_for_production": success_rate >= 90
    }
    
    config_dir = Path(__file__).parent.parent / "config"
    report_file = config_dir / "audit_response_validation_report.json"
    
    import json
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"\n📋 Detailed report saved: {report_file}")
    
    return success_rate >= 90

def main():
    """Main validation execution"""
    logger.info("Phase 3 Enhanced Validation - Audit Response Testing")
    logger.info("=" * 60)
    
    # Run all validation tests
    criteria_results = validate_all_success_criteria()
    perf_results = benchmark_performance_with_latency(50)  # Comprehensive test
    
    # Generate final report
    production_ready = generate_final_report(criteria_results, perf_results)
    
    return production_ready

if __name__ == "__main__":
    main()