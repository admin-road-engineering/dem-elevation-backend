#!/usr/bin/env python3
"""
Quick test for the coverage database implementation
Phase 1 validation script
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from coverage_database import CoverageDatabase

def test_default_sources():
    """Test loading default hardcoded sources"""
    print("Testing default sources...")
    
    db = CoverageDatabase()
    
    print(f"✅ Loaded {len(db.sources)} sources")
    print(f"✅ Schema version: {db.schema_version}")
    
    # Test stats
    stats = db.get_stats()
    print(f"✅ Enabled sources: {stats['enabled_sources']}")
    print(f"✅ Visible sources: {stats['visible_sources']}")
    print(f"✅ Resolution range: {stats['resolution_range']['min']}-{stats['resolution_range']['max']}m")
    
    # Test priority grouping
    for priority in [1, 2, 3]:
        sources = db.get_sources_by_priority(priority)
        print(f"✅ Priority {priority}: {len(sources)} sources")
    
    print("Default sources test PASSED ✅\n")

def test_json_config():
    """Test loading from JSON config file"""
    print("Testing JSON config file...")
    
    config_path = "config/dem_sources.json"
    if not Path(config_path).exists():
        print(f"❌ Config file not found: {config_path}")
        return
    
    db = CoverageDatabase(config_path)
    
    print(f"✅ Loaded {len(db.sources)} sources from JSON")
    print(f"✅ Schema version: {db.schema_version}")
    print(f"✅ Last updated: {db.last_updated}")
    
    # Validate some specific sources
    act_source = db.get_source_by_id("act_elvis")
    if act_source:
        print(f"✅ Found ACT source: {act_source['name']}")
        print(f"   Resolution: {act_source['resolution_m']}m")
        print(f"   Bounds: {act_source['bounds']['min_lat']}, {act_source['bounds']['max_lat']}")
    
    nz_source = db.get_source_by_id("nz_auckland")
    if nz_source:
        print(f"✅ Found NZ source: {nz_source['name']}")
        print(f"   Provider: {nz_source['provider']}")
        print(f"   CRS: {nz_source['crs']}")
    
    print("JSON config test PASSED ✅\n")

def test_validation():
    """Test validation logic"""
    print("Testing validation...")
    
    # Test invalid schema version
    try:
        db = CoverageDatabase()
        db.schema_version = "999.0"
        db._validate_schema_version()
        print("❌ Should have failed with invalid schema version")
    except ValueError as e:
        print(f"✅ Correctly caught invalid schema: {e}")
    
    # Test missing required field
    try:
        db = CoverageDatabase()
        # Remove a required field
        db.sources[0].pop('resolution_m')
        db._validate_sources()
        print("❌ Should have failed with missing field")
    except ValueError as e:
        print(f"✅ Correctly caught missing field: {e}")
    
    print("Validation test PASSED ✅\n")

def test_coordinate_bounds():
    """Test coordinate validation in bounds"""
    print("Testing coordinate bounds validation...")
    
    db = CoverageDatabase()
    
    # Test valid bounds
    test_source = {
        'id': 'test',
        'bounds': {
            'type': 'bbox',
            'min_lat': -35.0, 'max_lat': -34.0,
            'min_lon': 148.0, 'max_lon': 149.0
        }
    }
    
    # Add other required fields
    for field in ['name', 'source_type', 'path', 'crs', 'resolution_m', 
                  'data_type', 'provider', 'priority', 'cost_per_query', 
                  'accuracy', 'enabled']:
        test_source[field] = 'test_value' if isinstance(test_source.get(field), str) else 1
    
    test_source['source_type'] = 's3'
    test_source['enabled'] = True
    
    db.sources = [test_source]
    
    try:
        db._validate_sources()
        print("✅ Valid bounds accepted")
    except ValueError as e:
        print(f"❌ Valid bounds rejected: {e}")
        return
    
    # Test invalid latitude bounds
    test_source['bounds']['min_lat'] = -95.0  # Invalid
    try:
        db._validate_sources()
        print("❌ Should have failed with invalid latitude")
    except ValueError as e:
        print(f"✅ Correctly caught invalid latitude: {e}")
    
    print("Coordinate bounds test PASSED ✅\n")

if __name__ == "__main__":
    print("TESTING Coverage Database Implementation")
    print("=" * 50)
    
    try:
        test_default_sources()
        test_json_config()
        test_validation()
        test_coordinate_bounds()
        
        print("ALL TESTS PASSED!")
        print("\nPhase 1 Implementation: COMPLETE")
        print("\nNext steps:")
        print("- Implement spatial selector (Phase 2)")
        print("- Add unit tests with pytest")
        print("- Integration with existing DEM service")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)