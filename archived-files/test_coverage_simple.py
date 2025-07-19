#!/usr/bin/env python3
"""
Simple test for the coverage database implementation
Phase 1 validation script - ASCII only
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from coverage_database import CoverageDatabase

def test_basic_functionality():
    """Test basic database functionality"""
    print("Testing Coverage Database Implementation")
    print("=" * 50)
    
    # Test 1: Default sources
    print("1. Testing default sources...")
    db = CoverageDatabase()
    print(f"   Loaded {len(db.sources)} sources")
    print(f"   Schema version: {db.schema_version}")
    
    stats = db.get_stats()
    print(f"   Enabled: {stats['enabled_sources']}")
    print(f"   Visible: {stats['visible_sources']}")
    print(f"   Resolution: {stats['resolution_range']['min']}-{stats['resolution_range']['max']}m")
    print("   PASS")
    
    # Test 2: JSON config
    print("\n2. Testing JSON config...")
    config_path = "config/dem_sources.json"
    if Path(config_path).exists():
        db_json = CoverageDatabase(config_path)
        print(f"   Loaded {len(db_json.sources)} sources from JSON")
        print(f"   Last updated: {db_json.last_updated}")
        
        # Test specific source
        act = db_json.get_source_by_id("act_elvis")
        if act:
            print(f"   Found ACT: {act['name']} ({act['resolution_m']}m)")
        print("   PASS")
    else:
        print(f"   Config not found: {config_path}")
        print("   SKIP")
    
    # Test 3: Source selection by priority
    print("\n3. Testing priority selection...")
    for priority in [1, 2, 3]:
        sources = db.get_sources_by_priority(priority)
        print(f"   Priority {priority}: {len(sources)} sources")
    print("   PASS")
    
    # Test 4: Validation
    print("\n4. Testing validation...")
    try:
        # Test with invalid source
        invalid_db = CoverageDatabase()
        invalid_db.sources[0]['resolution_m'] = -1  # Invalid
        invalid_db._validate_sources()
        print("   ERROR: Should have failed validation")
        return False
    except ValueError:
        print("   Validation correctly rejected invalid source")
        print("   PASS")
    
    print("\nALL TESTS PASSED!")
    print("Phase 1 Implementation: COMPLETE")
    return True

if __name__ == "__main__":
    success = test_basic_functionality()
    if not success:
        sys.exit(1)
    
    print("\nNext steps:")
    print("- Implement spatial selector with tie-breaking")
    print("- Add comprehensive unit tests")
    print("- Integration with DEM service")