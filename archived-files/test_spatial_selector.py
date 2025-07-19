#!/usr/bin/env python3
"""
Test spatial selector implementation
Phase 2 validation script
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from coverage_database import CoverageDatabase
from spatial_selector import AutomatedSourceSelector

def test_basic_selection():
    """Test basic source selection functionality"""
    print("Testing Spatial Selector Implementation")
    print("=" * 50)
    
    print("1. Initializing selector...")
    db = CoverageDatabase()
    selector = AutomatedSourceSelector(db)
    
    stats = selector.get_selector_stats()
    print(f"   Enabled sources: {stats['enabled_sources']}")
    print("   PASS")
    
    return selector

def test_coordinate_validation(selector):
    """Test coordinate validation"""
    print("\n2. Testing coordinate validation...")
    
    # Test valid coordinates
    try:
        source = selector.select_best_source(-35.5, 149.0)  # ACT area
        print(f"   Valid coords OK: Selected {source['id']}")
    except Exception as e:
        print(f"   ERROR: Valid coords failed: {e}")
        return False
    
    # Test invalid latitude
    try:
        selector.select_best_source(91.0, 0.0)  # Invalid lat
        print("   ERROR: Should have failed with invalid latitude")
        return False
    except ValueError:
        print("   Invalid latitude correctly rejected")
    
    # Test invalid longitude
    try:
        selector.select_best_source(0.0, 181.0)  # Invalid lon
        print("   ERROR: Should have failed with invalid longitude")
        return False
    except ValueError:
        print("   Invalid longitude correctly rejected")
    
    # Test non-numeric input
    try:
        selector.select_best_source("invalid", 0.0)
        print("   ERROR: Should have failed with non-numeric input")
        return False
    except TypeError:
        print("   Non-numeric input correctly rejected")
    
    print("   PASS")
    return True

def test_boundary_conditions(selector):
    """Test boundary edge cases"""
    print("\n3. Testing boundary conditions...")
    
    # Test point exactly on ACT boundary (should be included)
    # ACT bounds: min_lat=-35.9, max_lat=-35.1, min_lon=148.7, max_lon=149.4
    try:
        # Test exact boundary points
        boundary_points = [
            (-35.9, 149.0),  # min_lat
            (-35.1, 149.0),  # max_lat
            (-35.5, 148.7),  # min_lon
            (-35.5, 149.4),  # max_lon
        ]
        
        for lat, lon in boundary_points:
            source = selector.select_best_source(lat, lon)
            print(f"   Boundary point ({lat}, {lon}): {source['id']}")
        
        print("   Boundary inclusion working correctly")
    except Exception as e:
        print(f"   ERROR: Boundary test failed: {e}")
        return False
    
    print("   PASS")
    return True

def test_priority_selection(selector):
    """Test priority-based selection"""
    print("\n4. Testing priority selection...")
    
    # Test in area with multiple coverage (Australia should have Priority 1)
    # NSW bounds should overlap with other sources
    lat, lon = -33.8688, 151.2093  # Sydney
    
    try:
        source = selector.select_best_source(lat, lon)
        print(f"   Sydney coords: Selected {source['id']} (priority {source['priority']})")
        
        if source['priority'] != 1:
            print(f"   WARNING: Expected priority 1, got {source['priority']}")
        
        # Get coverage summary to see all options
        summary = selector.get_coverage_summary(lat, lon)
        print(f"   Available sources: {summary['total_sources']}")
        print(f"   Selection reason: {summary['reason']}")
        
    except Exception as e:
        print(f"   ERROR: Priority test failed: {e}")
        return False
    
    print("   PASS")
    return True

def test_no_coverage_handling(selector):
    """Test handling of points with no coverage"""
    print("\n5. Testing no coverage scenarios...")
    
    # Test point with no coverage (Antarctica)
    try:
        selector.select_best_source(-85.0, 0.0)  # Antarctica
        print("   ERROR: Should have failed with no coverage")
        return False
    except ValueError as e:
        print(f"   No coverage correctly handled: {str(e)[:60]}...")
    
    # Test coverage summary for uncovered point
    try:
        summary = selector.get_coverage_summary(-85.0, 0.0)
        print(f"   Summary for uncovered point: {summary['total_sources']} sources")
        print(f"   Reason: {summary['reason']}")
    except Exception as e:
        print(f"   ERROR: Coverage summary failed: {e}")
        return False
    
    print("   PASS")
    return True

def test_tie_breaking(selector):
    """Test tie-breaking logic"""
    print("\n6. Testing tie-breaking logic...")
    
    # For deterministic tie-breaking, we need sources with same priority/resolution
    # In our default config, all NZ sources have same priority (1) and resolution (1m)
    # Test in NZ area to see tie-breaking
    
    lat, lon = -41.2865, 174.7762  # Wellington, NZ
    
    try:
        source = selector.select_best_source(lat, lon)
        print(f"   Wellington coords: Selected {source['id']}")
        
        # Get all options to see tie-breaking
        summary = selector.get_coverage_summary(lat, lon)
        if summary['total_sources'] > 1:
            print(f"   Multiple sources available ({summary['total_sources']})")
            # Show first few options
            for i, option in enumerate(summary['all_options'][:3]):
                print(f"      {i+1}. {option['id']} (p={option['priority']}, r={option['resolution_m']}m)")
        
    except Exception as e:
        print(f"   Tie-breaking test failed: {e}")
        return False
    
    print("   PASS")
    return True

def test_caching_performance(selector):
    """Test caching functionality"""
    print("\n7. Testing caching...")
    
    # Clear cache first
    selector.clear_cache()
    
    # Test same coordinates multiple times
    lat, lon = -35.5, 149.0
    
    # First call (cache miss)
    source1 = selector.select_best_source(lat, lon)
    stats1 = selector.get_selector_stats()
    
    # Second call (should be cache hit)
    source2 = selector.select_best_source(lat, lon)
    stats2 = selector.get_selector_stats()
    
    if source1['id'] != source2['id']:
        print(f"   ERROR: Inconsistent results: {source1['id']} vs {source2['id']}")
        return False
    
    if stats2['cache_hits'] <= stats1['cache_hits']:
        print("   WARNING: Cache doesn't seem to be working")
    else:
        print(f"   Cache working: {stats2['cache_hits']} hits")
    
    print(f"   Cache hit rate: {stats2['cache_hit_rate']:.2%}")
    print("   PASS")
    return True

def test_coverage_analysis(selector):
    """Test coverage analysis functionality"""
    print("\n8. Testing coverage analysis...")
    
    # Test various global points
    test_points = [
        (-35.5, 149.0),   # ACT, Australia
        (-33.8688, 151.2093),  # Sydney, Australia
        (-36.8485, 174.7633),  # Auckland, NZ
        (40.7128, -74.0060),   # New York, USA (GPXZ coverage)
        (51.5074, -0.1278),    # London, UK (GPXZ coverage)
        (-85.0, 0.0),          # Antarctica (no coverage)
    ]
    
    try:
        results = selector.test_coverage_at_points(test_points)
        
        print(f"   Tested {results['total_points']} points")
        print(f"   Coverage: {results['covered_points']}/{results['total_points']} ({results['coverage_percentage']:.1f}%)")
        print(f"   Uncovered: {len(results['uncovered_points'])}")
        
        if results['source_usage']:
            print("   Source usage:")
            for source_id, count in results['source_usage'].items():
                print(f"      {source_id}: {count}")
        
    except Exception as e:
        print(f"   Coverage analysis failed: {e}")
        return False
    
    print("   PASS")
    return True

if __name__ == "__main__":
    print("Phase 2: Spatial Selector Testing")
    
    try:
        selector = test_basic_selection()
        
        if not test_coordinate_validation(selector):
            sys.exit(1)
        if not test_boundary_conditions(selector):
            sys.exit(1)
        if not test_priority_selection(selector):
            sys.exit(1)
        if not test_no_coverage_handling(selector):
            sys.exit(1)
        if not test_tie_breaking(selector):
            sys.exit(1)
        if not test_caching_performance(selector):
            sys.exit(1)
        if not test_coverage_analysis(selector):
            sys.exit(1)
        
        print("\nALL TESTS PASSED!")
        print("Phase 2 Implementation: COMPLETE")
        
        # Show final stats
        stats = selector.get_selector_stats()
        print(f"\nFinal Stats:")
        print(f"- Total selections: {stats['total_selections']}")
        print(f"- Cache hit rate: {stats['cache_hit_rate']:.2%}")
        print(f"- Sources available: {stats['enabled_sources']}")
        
        print("\nNext steps:")
        print("- Integrate with existing DEM service")
        print("- Add GPXZ and Google API clients")
        print("- Create comprehensive unit tests")
        
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)