#!/usr/bin/env python3
"""
Source Database Accuracy Monitoring System
Prevents future configuration drift and geographic coverage gaps
"""
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Set
from datetime import datetime
import logging

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def validate_geographic_coverage(dem_sources: Dict) -> Dict:
    """Test real coordinates against configured sources to find coverage gaps"""
    
    # Key test coordinates for Australia
    test_coordinates = {
        # Major cities
        "brisbane": (-27.4698, 153.0251),
        "sydney": (-33.8688, 151.2093),
        "melbourne": (-37.8136, 144.9631), 
        "perth": (-31.9505, 115.8605),
        "adelaide": (-34.9285, 138.6007),
        "darwin": (-12.4634, 130.8456),
        "hobart": (-42.8821, 147.3272),
        "canberra": (-35.2809, 149.1300),
        
        # Regional centers with known data
        "bendigo": (-36.7570, 144.2794),  # Victoria - should have GA coverage
        "toowoomba": (-27.5598, 151.9507),  # Queensland - should have data
        "ballarat": (-37.5622, 143.8503),  # Victoria
        "cairns": (-16.9186, 145.7781),   # Far North Queensland
        "townsville": (-19.2590, 146.8169),  # North Queensland
        
        # Road engineering project locations
        "gold_coast": (-28.0167, 153.4000),
        "sunshine_coast": (-26.6500, 153.0667),
        "newcastle": (-32.9267, 151.7767),
        "wollongong": (-34.4278, 150.8931)
    }
    
    coverage_results = {
        "covered_by_s3": [],
        "covered_by_api_only": [],
        "no_coverage": [],
        "source_usage": {}
    }
    
    # Import here to avoid circular imports during initial setup
    try:
        from dem_service import DEMService
        from config import Settings
        
        settings = Settings()
        dem_service = DEMService(settings)
        
        print("GEOGRAPHIC COVERAGE VALIDATION")
        print("=" * 40)
        
        for location, (lat, lon) in test_coordinates.items():
            try:
                # Test elevation retrieval
                elevation, source_used, error = dem_service.get_elevation_at_point(lat, lon, auto_select=True)
                
                if elevation is not None:
                    if source_used.startswith('s3://') or 'elvis' in source_used:
                        coverage_results["covered_by_s3"].append((location, lat, lon, source_used))
                        print(f"[S3] {location}: {elevation}m via {source_used}")
                    elif 'gpxz' in source_used or 'api' in source_used:
                        coverage_results["covered_by_api_only"].append((location, lat, lon, source_used))
                        print(f"[API] {location}: {elevation}m via {source_used}")
                    else:
                        coverage_results["covered_by_s3"].append((location, lat, lon, source_used))
                        print(f"[LOCAL] {location}: {elevation}m via {source_used}")
                    
                    # Track source usage
                    if source_used not in coverage_results["source_usage"]:
                        coverage_results["source_usage"][source_used] = 0
                    coverage_results["source_usage"][source_used] += 1
                    
                else:
                    coverage_results["no_coverage"].append((location, lat, lon, error))
                    print(f"[FAIL] {location}: No elevation data - {error}")
                    
            except Exception as e:
                coverage_results["no_coverage"].append((location, lat, lon, str(e)))
                print(f"[ERROR] {location}: Exception - {e}")
        
        # Cleanup
        if hasattr(dem_service, 'close'):
            dem_service.close()
            
    except ImportError as e:
        print(f"Cannot import DEM service for testing: {e}")
        coverage_results["error"] = str(e)
    
    return coverage_results

def generate_monitoring_report(dem_sources: Dict, coverage_results: Dict) -> Dict:
    """Generate comprehensive monitoring report"""
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "source_analysis": {
            "total_sources": len(dem_sources),
            "s3_sources": len([s for s in dem_sources.values() if 's3://' in s.get('path', '')]),
            "api_sources": len([s for s in dem_sources.values() if 'api://' in s.get('path', '')]),
            "local_sources": len([s for s in dem_sources.values() if not ('s3://' in s.get('path', '') or 'api://' in s.get('path', ''))]),
        },
        "geographic_coverage": {
            "s3_covered_locations": len(coverage_results.get("covered_by_s3", [])),
            "api_only_locations": len(coverage_results.get("covered_by_api_only", [])),
            "no_coverage_locations": len(coverage_results.get("no_coverage", [])),
            "coverage_percentage": (len(coverage_results.get("covered_by_s3", [])) + len(coverage_results.get("covered_by_api_only", []))) / max(1, len(coverage_results.get("covered_by_s3", [])) + len(coverage_results.get("covered_by_api_only", [])) + len(coverage_results.get("no_coverage", []))) * 100
        },
        "issues_detected": [],
        "recommendations": []
    }
    
    # Detect issues
    if coverage_results.get("api_only_locations"):
        report["issues_detected"].append({
            "type": "geographic_gap",
            "severity": "medium",
            "description": f"{len(coverage_results['api_only_locations'])} locations only covered by API sources",
            "locations": [loc[0] for loc in coverage_results["api_only_locations"]]
        })
        report["recommendations"].append("Add S3 DEM sources for API-only locations to improve accuracy and reduce costs")
    
    if coverage_results.get("no_coverage"):
        report["issues_detected"].append({
            "type": "no_coverage",
            "severity": "high", 
            "description": f"{len(coverage_results['no_coverage'])} locations have no elevation coverage",
            "locations": [loc[0] for loc in coverage_results["no_coverage"]]
        })
        report["recommendations"].append("Investigate missing coverage areas and add appropriate DEM sources")
    
    # Check for suspicious source usage patterns
    source_usage = coverage_results.get("source_usage", {})
    total_tests = sum(source_usage.values())
    
    for source, count in source_usage.items():
        usage_percentage = (count / total_tests) * 100 if total_tests > 0 else 0
        
        if 'gpxz' in source and usage_percentage > 50:
            report["issues_detected"].append({
                "type": "high_api_usage",
                "severity": "medium",
                "description": f"GPXZ API used for {usage_percentage:.1f}% of test locations",
                "details": f"May indicate missing S3 sources for major Australian locations"
            })
    
    return report

def create_monitoring_schedule():
    """Create automated monitoring schedule recommendations"""
    
    schedule = {
        "daily_checks": [
            "Validate critical coordinates (Brisbane, Melbourne, Sydney)",
            "Check S3 source availability",
            "Monitor API usage patterns"
        ],
        "weekly_checks": [
            "Run full geographic coverage validation",
            "Scan S3 bucket for new data sources", 
            "Validate configuration against actual S3 contents",
            "Check for orphaned/invalid source configurations"
        ],
        "monthly_checks": [
            "Full S3 bucket discovery scan",
            "Update source database with new findings",
            "Review and update geographic test coordinates",
            "Performance analysis of source selection"
        ],
        "automation_recommendations": [
            "Set up GitHub Actions workflow to run weekly checks",
            "Create alerts for geographic coverage gaps",
            "Implement automatic S3 source discovery",
            "Add source configuration validation to CI/CD pipeline"
        ]
    }
    
    return schedule

def main():
    """Main monitoring execution"""
    try:
        from config import Settings
        settings = Settings()
        
        print("SOURCE DATABASE ACCURACY MONITORING")
        print("=" * 50)
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Test geographic coverage
        coverage_results = validate_geographic_coverage(settings.DEM_SOURCES)
        
        print(f"\nCOVERAGE SUMMARY:")
        print(f"S3-covered locations: {len(coverage_results.get('covered_by_s3', []))}")
        print(f"API-only locations: {len(coverage_results.get('covered_by_api_only', []))}")
        print(f"No coverage: {len(coverage_results.get('no_coverage', []))}")
        
        # Generate report
        report = generate_monitoring_report(settings.DEM_SOURCES, coverage_results)
        
        print(f"\nISSUES DETECTED: {len(report['issues_detected'])}")
        for issue in report["issues_detected"]:
            print(f"  - {issue['severity'].upper()}: {issue['description']}")
        
        print(f"\nRECOMMENDATIONS: {len(report['recommendations'])}")
        for i, rec in enumerate(report["recommendations"], 1):
            print(f"  {i}. {rec}")
        
        # Save results
        output_dir = Path(__file__).parent.parent / "config"
        output_dir.mkdir(exist_ok=True)
        
        # Save detailed report
        with open(output_dir / "monitoring_report.json", 'w') as f:
            json.dump({
                "report": report,
                "coverage_details": coverage_results,
                "monitoring_schedule": create_monitoring_schedule()
            }, f, indent=2)
        
        print(f"\nMonitoring report saved: {output_dir / 'monitoring_report.json'}")
        
        # Create simple monitoring script for regular use
        monitoring_script = '''#!/bin/bash
# Daily Source Monitoring Script
# Run this daily to check source database accuracy

cd "$(dirname "$0")/.."
echo "=== Daily DEM Source Check ==="
date

# Test key coordinates
python -c "
from src.dem_service import DEMService
from src.config import Settings

settings = Settings()
service = DEMService(settings)

test_coords = [
    ('Brisbane', -27.4698, 153.0251),
    ('Melbourne', -37.8136, 144.9631),
    ('Sydney', -33.8688, 151.2093)
]

for name, lat, lon in test_coords:
    elevation, source, error = service.get_elevation_at_point(lat, lon)
    if elevation:
        print(f'{name}: {elevation:.1f}m via {source}')
    else:
        print(f'{name}: FAILED - {error}')
"

echo "=== Check complete ==="
'''
        
        with open(output_dir.parent / "scripts" / "daily_check.sh", 'w') as f:
            f.write(monitoring_script)
        
        print(f"Daily monitoring script created: scripts/daily_check.sh")
        
    except Exception as e:
        print(f"Monitoring failed: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())