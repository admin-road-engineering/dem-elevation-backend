#!/usr/bin/env python3
"""
Test and validate the ultimate performance index
Compare against current production index to show improvements
"""
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple
import statistics


def load_index(filepath: Path) -> Dict:
    """Load a spatial index file"""
    print(f"Loading {filepath.name}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def test_spatial_query(collections: List[Dict], lat: float, lon: float) -> Tuple[int, float]:
    """
    Test spatial query performance
    
    Returns:
        (match_count, query_time_ms)
    """
    start = time.perf_counter()
    matches = 0
    
    for collection in collections:
        bounds = collection.get('coverage_bounds', {})
        if bounds:
            if (bounds.get('min_lat', -90) <= lat <= bounds.get('max_lat', 90) and
                bounds.get('min_lon', -180) <= lon <= bounds.get('max_lon', 180)):
                matches += 1
    
    query_time_ms = (time.perf_counter() - start) * 1000
    return matches, query_time_ms


def analyze_bounds_quality(collections: List[Dict]) -> Dict:
    """Analyze the quality of bounds in the index"""
    stats = {
        'total_collections': len(collections),
        'collections_with_identical_file_bounds': 0,
        'collections_with_all_australia_bounds': 0,
        'collections_with_reasonable_bounds': 0,
        'average_coverage_area': 0,
        'max_coverage_area': 0,
        'min_coverage_area': float('inf')
    }
    
    areas = []
    
    for collection in collections:
        files = collection.get('files', [])
        bounds = collection.get('coverage_bounds', {})
        
        if not bounds or not files:
            continue
        
        # Check if all files have identical bounds (the bug!)
        if len(files) > 1:
            first_bounds = files[0].get('bounds', {})
            if all(f.get('bounds', {}) == first_bounds for f in files[:10]):
                stats['collections_with_identical_file_bounds'] += 1
        
        # Check for all-Australia bounds
        lat_span = bounds.get('max_lat', 0) - bounds.get('min_lat', 0)
        lon_span = bounds.get('max_lon', 0) - bounds.get('min_lon', 0)
        area = lat_span * lon_span
        
        if lat_span > 30 or lon_span > 30:  # Spanning most of Australia
            stats['collections_with_all_australia_bounds'] += 1
        elif 0 < lat_span < 5 and 0 < lon_span < 5:  # Reasonable local coverage
            stats['collections_with_reasonable_bounds'] += 1
        
        if area > 0:
            areas.append(area)
            stats['max_coverage_area'] = max(stats['max_coverage_area'], area)
            stats['min_coverage_area'] = min(stats['min_coverage_area'], area)
    
    if areas:
        stats['average_coverage_area'] = statistics.mean(areas)
    
    return stats


def main():
    """Run comprehensive index comparison tests"""
    print("=" * 70)
    print("ULTIMATE PERFORMANCE INDEX VALIDATION")
    print("=" * 70)
    print()
    
    # File paths
    production_index = Path('config/unified_spatial_index_v2_ideal.json')
    ultimate_index = Path('config/ultimate_performance_index.json')
    
    # Check which indexes exist
    if not production_index.exists():
        print(f"Production index not found: {production_index}")
        production_data = None
    else:
        production_data = load_index(production_index)
        print(f"✓ Production index loaded: {len(production_data.get('data_collections', []))} collections")
    
    if not ultimate_index.exists():
        print(f"Ultimate index not found: {ultimate_index}")
        print("Please run create_ultimate_index.bat first!")
        return
    
    ultimate_data = load_index(ultimate_index)
    print(f"✓ Ultimate index loaded: {len(ultimate_data.get('data_collections', []))} collections")
    print()
    
    # Test locations
    test_locations = [
        ('Sydney Harbor', -33.8688, 151.2093),
        ('Brisbane CBD', -27.4698, 153.0251),
        ('Melbourne CBD', -37.8136, 144.9631),
        ('Perth CBD', -31.9505, 115.8605),
        ('Canberra', -35.3, 149.1),
        ('Adelaide', -34.9285, 138.6007),
        ('Darwin', -12.4634, 130.8456),
        ('Hobart', -42.8821, 147.3272),
        ('Auckland NZ', -36.8485, 174.7633),
        ('Wellington NZ', -41.2865, 174.7762)
    ]
    
    # Performance comparison
    print("=" * 70)
    print("PERFORMANCE COMPARISON")
    print("=" * 70)
    print()
    
    if production_data:
        print("Location         | Production        | Ultimate          | Improvement")
        print("-" * 70)
        
        prod_collections = production_data.get('data_collections', [])
        ultimate_collections = ultimate_data.get('data_collections', [])
        
        total_prod_matches = 0
        total_ultimate_matches = 0
        improvements = []
        
        for location, lat, lon in test_locations:
            # Test production index
            prod_matches, prod_time = test_spatial_query(prod_collections, lat, lon)
            total_prod_matches += prod_matches
            
            # Test ultimate index
            ult_matches, ult_time = test_spatial_query(ultimate_collections, lat, lon)
            total_ultimate_matches += ult_matches
            
            # Calculate improvement
            if prod_matches > 0:
                improvement = prod_matches / max(1, ult_matches)
                improvements.append(improvement)
            else:
                improvement = 0
            
            # Display results
            prod_str = f"{prod_matches:3d} ({prod_time:5.1f}ms)"
            ult_str = f"{ult_matches:3d} ({ult_time:5.1f}ms)"
            imp_str = f"{improvement:5.1f}x" if improvement > 1 else "N/A"
            
            print(f"{location:15s} | {prod_str:17s} | {ult_str:17s} | {imp_str}")
        
        print("-" * 70)
        
        avg_prod = total_prod_matches / len(test_locations)
        avg_ultimate = total_ultimate_matches / len(test_locations)
        avg_improvement = statistics.mean(improvements) if improvements else 0
        
        print(f"{'AVERAGE':15s} | {avg_prod:7.1f} matches   | {avg_ultimate:7.1f} matches   | {avg_improvement:5.1f}x")
    
    else:
        print("Ultimate Index Performance:")
        print("-" * 40)
        
        ultimate_collections = ultimate_data.get('data_collections', [])
        
        for location, lat, lon in test_locations:
            matches, query_time = test_spatial_query(ultimate_collections, lat, lon)
            status = '✅' if matches < 50 else '⚠️' if matches < 100 else '❌'
            print(f"{location:15s}: {matches:3d} matches in {query_time:5.1f}ms {status}")
    
    print()
    
    # Analyze bounds quality
    print("=" * 70)
    print("BOUNDS QUALITY ANALYSIS")
    print("=" * 70)
    print()
    
    if production_data:
        print("Production Index Issues:")
        prod_stats = analyze_bounds_quality(production_data.get('data_collections', []))
        print(f"  - Collections with identical file bounds: {prod_stats['collections_with_identical_file_bounds']}")
        print(f"  - Collections with all-Australia bounds: {prod_stats['collections_with_all_australia_bounds']}")
        print(f"  - Collections with reasonable bounds: {prod_stats['collections_with_reasonable_bounds']}")
        print(f"  - Average coverage area: {prod_stats['average_coverage_area']:.2f} deg²")
        print()
    
    print("Ultimate Index Quality:")
    ult_stats = analyze_bounds_quality(ultimate_data.get('data_collections', []))
    print(f"  - Collections with identical file bounds: {ult_stats['collections_with_identical_file_bounds']}")
    print(f"  - Collections with all-Australia bounds: {ult_stats['collections_with_all_australia_bounds']}")
    print(f"  - Collections with reasonable bounds: {ult_stats['collections_with_reasonable_bounds']}")
    print(f"  - Average coverage area: {ult_stats['average_coverage_area']:.2f} deg²")
    
    # Show statistics from ultimate index
    if 'statistics' in ultimate_data:
        stats = ultimate_data['statistics']
        print()
        print("=" * 70)
        print("PROCESSING STATISTICS")
        print("=" * 70)
        print(f"  - Total files processed: {stats.get('total_files', 0):,}")
        print(f"  - WGS84 files (used directly): {stats.get('wgs84_files', 0):,}")
        print(f"  - UTM files (transformed): {stats.get('utm_files', 0):,}")
        print(f"  - Invalid/skipped files: {stats.get('invalid_files', 0) + stats.get('skipped_test_files', 0):,}")
        print(f"  - Campaigns created: {stats.get('campaigns_created', 0):,}")
    
    print()
    print("=" * 70)
    print("VALIDATION COMPLETE")
    print("=" * 70)
    
    # Final verdict
    if ult_stats['collections_with_identical_file_bounds'] == 0 and avg_ultimate < 50:
        print()
        print("🎉 SUCCESS! The ultimate index has fixed the performance issues:")
        print("  ✅ No more duplicate bounds across files")
        print("  ✅ Queries return <50 matches on average")
        print("  ✅ Ready for production deployment")
    else:
        print()
        print("⚠️ The ultimate index needs further optimization:")
        if ult_stats['collections_with_identical_file_bounds'] > 0:
            print("  ❌ Still has collections with identical file bounds")
        if avg_ultimate >= 50:
            print("  ❌ Average matches still too high")


if __name__ == '__main__':
    main()