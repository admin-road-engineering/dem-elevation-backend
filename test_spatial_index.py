#!/usr/bin/env python3
"""
Test script for spatial index generation and S3 tiled access
"""
import sys
import asyncio
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_spatial_index_generation():
    """Test generating spatial index from S3 bucket"""
    print("[INFO] Testing spatial index generation...")
    
    try:
        from scripts.generate_spatial_index import SpatialIndexGenerator
        
        generator = SpatialIndexGenerator()
        spatial_index = generator.generate_complete_index()
        
        print("[OK] Spatial index generated successfully!")
        print(f"   Files indexed: {spatial_index['file_count']}")
        print(f"   UTM zones: {list(spatial_index['utm_zones'].keys())}")
        
        # Test key locations
        for location, details in spatial_index['coverage_summary']['key_locations'].items():
            print(f"   {location}: {details['matching_files']} files")
            
        return True
        
    except Exception as e:
        print(f"[ERROR] Error generating spatial index: {e}")
        return False

def test_s3_tiled_access():
    """Test complete S3 tiled data access"""
    print("\n[INFO] Testing S3 tiled data access...")
    
    test_coordinates = [
        ("Brisbane", -27.4698, 153.0251),
        ("Bendigo", -36.7570, 144.2794),
        ("Melbourne", -37.8136, 144.9631),
        ("Canberra", -35.2809, 149.1300)
    ]
    
    try:
        from config import Settings
        from dem_service import DEMService
        
        settings = Settings()
        dem_service = DEMService(settings)
        
        print("DEM Service initialized successfully!")
        
        results = []
        for location, lat, lon in test_coordinates:
            try:
                print(f"\n[TEST] Testing {location} ({lat}, {lon})...")
                
                elevation, source_used, error = dem_service.get_elevation_at_point(
                    lat, lon, auto_select=True
                )
                
                if elevation is not None:
                    print(f"   [OK] {location}: {elevation:.2f}m from {source_used}")
                    results.append({
                        "location": location,
                        "elevation": elevation,
                        "source": source_used,
                        "success": True
                    })
                else:
                    print(f"   [FAIL] {location}: Failed - {error}")
                    results.append({
                        "location": location,
                        "error": error,
                        "success": False
                    })
                    
            except Exception as e:
                print(f"   [ERROR] {location}: Error - {e}")
                results.append({
                    "location": location,
                    "error": str(e),
                    "success": False
                })
        
        # Summary
        successful = sum(1 for r in results if r["success"])
        print(f"\n[SUMMARY] Results: {successful}/{len(results)} locations successful")
        
        # Check for S3 usage
        s3_used = sum(1 for r in results if r["success"] and not r["source"].startswith("gpxz"))
        print(f"   S3 sources used: {s3_used}/{successful}")
        
        return successful > 0
        
    except Exception as e:
        print(f"[ERROR] Error testing S3 access: {e}")
        return False

def test_spatial_index_usage():
    """Test spatial index file selection"""
    print("\n[INFO] Testing spatial index usage...")
    
    try:
        from scripts.generate_spatial_index import SpatialIndexGenerator
        
        generator = SpatialIndexGenerator()
        spatial_index = generator.load_spatial_index()
        
        if not spatial_index:
            print("[ERROR] No spatial index found - generate one first")
            return False
        
        print(f"[OK] Loaded spatial index with {spatial_index['file_count']} files")
        
        # Test coordinate lookup
        test_coords = [
            ("Brisbane", -27.4698, 153.0251),
            ("Bendigo", -36.7570, 144.2794)
        ]
        
        for location, lat, lon in test_coords:
            matching_files = []
            for zone, zone_data in spatial_index.get("utm_zones", {}).items():
                for file_info in zone_data.get("files", []):
                    bounds = file_info.get("bounds", {})
                    if (bounds.get("min_lat", 0) <= lat <= bounds.get("max_lat", 0) and
                        bounds.get("min_lon", 0) <= lon <= bounds.get("max_lon", 0)):
                        matching_files.append(file_info)
            
            print(f"   {location}: {len(matching_files)} matching files")
            if matching_files:
                best_file = min(matching_files, key=lambda f: f.get("resolution", "1m"))
                print(f"      Best: {best_file['filename']}")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Error testing spatial index: {e}")
        return False

def main():
    """Run all tests"""
    print("[INFO] Testing S3 Multi-File Access Implementation")
    print("=" * 60)
    
    # Test 1: Generate spatial index
    index_success = test_spatial_index_generation()
    
    # Test 2: Test spatial index usage
    if index_success:
        index_usage_success = test_spatial_index_usage()
    else:
        index_usage_success = False
    
    # Test 3: Test complete S3 access
    access_success = test_s3_tiled_access()
    
    print("\n" + "=" * 60)
    print("[RESULTS] Final Results:")
    print(f"   Spatial Index Generation: {'[PASS]' if index_success else '[FAIL]'}")
    print(f"   Spatial Index Usage: {'[PASS]' if index_usage_success else '[FAIL]'}")
    print(f"   S3 Tiled Access: {'[PASS]' if access_success else '[FAIL]'}")
    
    if all([index_success, index_usage_success, access_success]):
        print("\n[SUCCESS] All tests passed! S3 multi-file access is working correctly.")
    else:
        print("\n[WARNING] Some tests failed. Check the output above for details.")

if __name__ == "__main__":
    main()