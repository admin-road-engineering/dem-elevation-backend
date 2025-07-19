#!/usr/bin/env python3
"""
Simple test for S3 access without DEM service dependencies
"""
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_s3_credentials():
    """Test basic S3 access"""
    print("[INFO] Testing S3 credentials and bucket access...")
    
    try:
        from config import Settings
        import boto3
        
        settings = Settings()
        
        # Test S3 connection
        s3 = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_DEFAULT_REGION
        )
        
        # Test bucket access
        response = s3.list_objects_v2(
            Bucket=settings.AWS_S3_BUCKET_NAME,
            MaxKeys=5
        )
        
        files = response.get('Contents', [])
        print(f"[OK] S3 connection successful! Found {len(files)} files")
        
        for file_info in files:
            print(f"   {file_info['Key']} ({file_info['Size']} bytes)")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] S3 connection failed: {e}")
        return False

def test_spatial_index():
    """Test spatial index loading"""
    print("\n[INFO] Testing spatial index loading...")
    
    try:
        from scripts.generate_spatial_index import SpatialIndexGenerator
        
        generator = SpatialIndexGenerator()
        spatial_index = generator.load_spatial_index()
        
        if spatial_index:
            print(f"[OK] Spatial index loaded: {spatial_index['file_count']} files")
            
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
                
                # Show sample files
                for i, file_info in enumerate(matching_files[:3]):
                    print(f"      {i+1}. {file_info['filename']}")
            
            return True
        else:
            print("[ERROR] No spatial index found")
            return False
            
    except Exception as e:
        print(f"[ERROR] Spatial index test failed: {e}")
        return False

def test_basic_import():
    """Test basic import without problematic libraries"""
    print("\n[INFO] Testing basic imports...")
    
    try:
        # Test configuration loading
        from config import Settings
        settings = Settings()
        print(f"[OK] Config loaded: {len(settings.DEM_SOURCES)} sources")
        
        # Test spatial index generator
        from scripts.generate_spatial_index import SpatialIndexGenerator
        print("[OK] Spatial index generator imported")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Basic import failed: {e}")
        return False

def regenerate_spatial_index():
    """Regenerate spatial index with corrected coordinates"""
    print("\n[INFO] Regenerating spatial index...")
    
    try:
        from scripts.generate_spatial_index import SpatialIndexGenerator
        
        generator = SpatialIndexGenerator()
        spatial_index = generator.generate_complete_index()
        
        print(f"[OK] Spatial index regenerated: {spatial_index['file_count']} files")
        
        # Check coverage summary
        coverage = spatial_index.get('coverage_summary', {})
        for location, details in coverage.get('key_locations', {}).items():
            print(f"   {location}: {details['matching_files']} matching files")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Spatial index regeneration failed: {e}")
        return False

def main():
    """Run all tests"""
    print("[INFO] Simple S3 Access Test")
    print("=" * 50)
    
    # Test 1: Basic imports
    import_success = test_basic_import()
    
    # Test 2: S3 credentials
    s3_success = test_s3_credentials()
    
    # Test 3: Regenerate spatial index
    if s3_success:
        index_success = regenerate_spatial_index()
    else:
        index_success = False
    
    # Test 4: Spatial index loading
    if index_success:
        spatial_success = test_spatial_index()
    else:
        spatial_success = False
    
    print("\n" + "=" * 50)
    print("[RESULTS] Test Results:")
    print(f"   Basic Imports: {'[PASS]' if import_success else '[FAIL]'}")
    print(f"   S3 Connection: {'[PASS]' if s3_success else '[FAIL]'}")
    print(f"   Index Generation: {'[PASS]' if index_success else '[FAIL]'}")
    print(f"   Spatial Index: {'[PASS]' if spatial_success else '[FAIL]'}")
    
    if all([import_success, s3_success, index_success, spatial_success]):
        print("\n[SUCCESS] All tests passed! S3 multi-file access is working.")
        print("Next step: Resolve DLL import issues for full DEM service integration.")
    else:
        print("\n[WARNING] Some tests failed. Check output above for details.")

if __name__ == "__main__":
    main()