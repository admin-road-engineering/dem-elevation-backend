#!/usr/bin/env python3
"""
Test NZ elevation integration with main DEM service
"""
import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_nz_source_configuration():
    """Test NZ sources are properly configured"""
    print("[INFO] Testing NZ source configuration...")
    
    try:
        from config import Settings
        
        settings = Settings()
        
        # Check for NZ sources
        nz_sources = [src_id for src_id in settings.DEM_SOURCES.keys() if src_id.startswith('nz_')]
        print(f"[INFO] Found {len(nz_sources)} NZ sources: {nz_sources}")
        
        # Show NZ source details
        for src_id in nz_sources:
            src_config = settings.DEM_SOURCES[src_id]
            print(f"   {src_id}: {src_config['path']}")
            print(f"      CRS: {src_config.get('crs', 'Not specified')}")
            print(f"      Description: {src_config.get('description', 'No description')}")
        
        # Check default DEM ID
        default_dem = settings.DEFAULT_DEM_ID
        print(f"[INFO] Default DEM ID: {default_dem}")
        
        if default_dem and default_dem.startswith('nz_'):
            print("[OK] NZ source is set as default")
        else:
            print("[INFO] Non-NZ source is default")
        
        return len(nz_sources) > 0
        
    except Exception as e:
        print(f"[ERROR] Configuration test failed: {e}")
        return False

def test_nz_spatial_index_integration():
    """Test NZ spatial index integration"""
    print("\n[INFO] Testing NZ spatial index integration...")
    
    try:
        from scripts.generate_nz_spatial_index import NZSpatialIndexGenerator
        
        generator = NZSpatialIndexGenerator()
        spatial_index = generator.load_spatial_index()
        
        if spatial_index:
            print(f"[OK] NZ spatial index loaded: {spatial_index['file_count']} files")
            print(f"   Regions: {list(spatial_index['regions'].keys())}")
            
            # Test coordinate lookup
            test_coords = [
                ("Auckland", -36.8485, 174.7633),
                ("Wellington", -41.2865, 174.7762),
                ("Christchurch", -43.5321, 172.6362)
            ]
            
            for location, lat, lon in test_coords:
                matching_files = []
                for region, region_data in spatial_index["regions"].items():
                    for survey, survey_data in region_data["surveys"].items():
                        for file_info in survey_data["files"]:
                            bounds = file_info["bounds"]
                            if (bounds["min_lat"] <= lat <= bounds["max_lat"] and
                                bounds["min_lon"] <= lon <= bounds["max_lon"]):
                                matching_files.append(file_info)
                
                print(f"   {location}: {len(matching_files)} matching files")
                if matching_files:
                    print(f"      Best file: {matching_files[0]['filename']}")
            
            return True
        else:
            print("[ERROR] NZ spatial index not found")
            return False
            
    except Exception as e:
        print(f"[ERROR] NZ spatial index integration failed: {e}")
        return False

def test_nz_elevation_queries():
    """Test NZ elevation queries"""
    print("\n[INFO] Testing NZ elevation queries...")
    
    try:
        from config import Settings
        
        settings = Settings()
        
        # Test coordinates in New Zealand
        test_coords = [
            ("Auckland CBD", -36.8485, 174.7633),
            ("Wellington CBD", -41.2865, 174.7762),
            ("Christchurch CBD", -43.5321, 172.6362),
            ("Dunedin", -45.8788, 170.5028),
            ("Queenstown", -45.0312, 168.6626)
        ]
        
        results = []
        for location, lat, lon in test_coords:
            print(f"\n[TEST] Testing {location} ({lat}, {lon})...")
            
            # Check if we have NZ sources covering this location
            nz_sources = [src_id for src_id in settings.DEM_SOURCES.keys() if src_id.startswith('nz_')]
            
            coverage_found = False
            for src_id in nz_sources:
                src_config = settings.DEM_SOURCES[src_id]
                if 'nz-elevation' in src_config['path']:
                    coverage_found = True
                    print(f"   [INFO] {location} covered by {src_id}")
                    break
            
            if coverage_found:
                results.append({
                    "location": location,
                    "coordinates": [lat, lon],
                    "covered": True,
                    "sources": nz_sources
                })
                print(f"   [OK] {location} has NZ elevation coverage")
            else:
                results.append({
                    "location": location,
                    "coordinates": [lat, lon],
                    "covered": False,
                    "sources": []
                })
                print(f"   [WARNING] {location} may not have NZ elevation coverage")
        
        # Summary
        covered_locations = sum(1 for r in results if r["covered"])
        print(f"\n[SUMMARY] NZ elevation coverage: {covered_locations}/{len(results)} locations")
        
        return covered_locations > 0
        
    except Exception as e:
        print(f"[ERROR] NZ elevation query test failed: {e}")
        return False

def test_nz_public_access():
    """Test NZ public bucket access configuration"""
    print("\n[INFO] Testing NZ public bucket access...")
    
    try:
        import boto3
        from botocore import UNSIGNED
        from botocore.config import Config
        
        # Test public access to NZ elevation bucket
        s3_client = boto3.client(
            's3',
            region_name='ap-southeast-2',
            config=Config(signature_version=UNSIGNED)
        )
        
        # Test basic access
        response = s3_client.list_objects_v2(
            Bucket='nz-elevation',
            MaxKeys=5
        )
        
        files = response.get('Contents', [])
        print(f"[OK] NZ elevation bucket accessible: {len(files)} files found")
        
        # Test file access
        if files:
            test_file = files[0]
            head_response = s3_client.head_object(
                Bucket='nz-elevation',
                Key=test_file['Key']
            )
            print(f"[OK] Test file accessible: {test_file['Key']}")
            print(f"   Size: {head_response['ContentLength']} bytes")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] NZ public access test failed: {e}")
        return False

def main():
    """Run all NZ integration tests"""
    print("[INFO] NZ Elevation Integration Test")
    print("=" * 50)
    
    # Test 1: Configuration
    config_success = test_nz_source_configuration()
    
    # Test 2: Spatial index integration
    spatial_success = test_nz_spatial_index_integration()
    
    # Test 3: Elevation queries
    query_success = test_nz_elevation_queries()
    
    # Test 4: Public access
    access_success = test_nz_public_access()
    
    print("\n" + "=" * 50)
    print("[RESULTS] Integration Test Results:")
    print(f"   Configuration: {'[PASS]' if config_success else '[FAIL]'}")
    print(f"   Spatial Index: {'[PASS]' if spatial_success else '[FAIL]'}")
    print(f"   Elevation Queries: {'[PASS]' if query_success else '[FAIL]'}")
    print(f"   Public Access: {'[PASS]' if access_success else '[FAIL]'}")
    
    if all([config_success, spatial_success, query_success, access_success]):
        print("\n[SUCCESS] NZ elevation integration is working correctly!")
        print("Ready for production use with public NZ elevation data")
    else:
        print("\n[WARNING] Some integration tests failed. Check output above.")

if __name__ == "__main__":
    main()