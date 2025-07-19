#!/usr/bin/env python3
"""
Test script for NZ elevation S3 bucket access
"""
import sys
import boto3
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_nz_elevation_access():
    """Test accessing NZ elevation bucket"""
    print("[INFO] Testing NZ elevation bucket access...")
    
    try:
        # Create S3 client for public bucket access (no credentials needed)
        from botocore import UNSIGNED
        from botocore.config import Config
        
        s3_client = boto3.client(
            's3',
            region_name='ap-southeast-2',
            config=Config(signature_version=UNSIGNED)
        )
        
        # List top-level contents
        print("[INFO] Listing bucket contents...")
        response = s3_client.list_objects_v2(
            Bucket='nz-elevation',
            MaxKeys=20,
            Delimiter='/'
        )
        
        # Show directories
        if 'CommonPrefixes' in response:
            print("[INFO] Found directories:")
            for prefix in response['CommonPrefixes']:
                print(f"   {prefix['Prefix']}")
        
        # Show files
        if 'Contents' in response:
            print("[INFO] Found files:")
            for obj in response['Contents']:
                print(f"   {obj['Key']} ({obj['Size']} bytes)")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to access NZ elevation bucket: {e}")
        return False

def test_nz_elevation_structure():
    """Test NZ elevation bucket structure"""
    print("\n[INFO] Testing NZ elevation bucket structure...")
    
    try:
        from botocore import UNSIGNED
        from botocore.config import Config
        
        s3_client = boto3.client(
            's3',
            region_name='ap-southeast-2',
            config=Config(signature_version=UNSIGNED)
        )
        
        # Look for elevation data patterns
        test_prefixes = [
            "dem_01m/",
            "elevation/",
            "lidar/",
            "auckland/",
            "wellington/",
            "christchurch/",
            "otago/",
            "canterbury/"
        ]
        
        found_data = []
        for prefix in test_prefixes:
            try:
                response = s3_client.list_objects_v2(
                    Bucket='nz-elevation',
                    Prefix=prefix,
                    MaxKeys=5
                )
                
                if 'Contents' in response:
                    files = response['Contents']
                    if files:
                        print(f"   Found data in {prefix}: {len(files)} files")
                        # Show sample files
                        for file_info in files[:2]:
                            print(f"      {file_info['Key']}")
                        found_data.append(prefix)
                        
            except Exception as e:
                print(f"   No data found in {prefix}")
        
        if found_data:
            print(f"\n[OK] Found elevation data in: {', '.join(found_data)}")
            return True
        else:
            print("[WARNING] No elevation data found in expected locations")
            return False
            
    except Exception as e:
        print(f"[ERROR] Failed to explore NZ elevation structure: {e}")
        return False

def test_nz_elevation_files():
    """Test NZ elevation file access"""
    print("\n[INFO] Testing NZ elevation file access...")
    
    try:
        from botocore import UNSIGNED
        from botocore.config import Config
        
        s3_client = boto3.client(
            's3',
            region_name='ap-southeast-2',
            config=Config(signature_version=UNSIGNED)
        )
        
        # Find .tiff files (NZ uses .tiff not .tif)
        response = s3_client.list_objects_v2(
            Bucket='nz-elevation',
            MaxKeys=100
        )
        
        tiff_files = []
        if 'Contents' in response:
            for obj in response['Contents']:
                if obj['Key'].endswith('.tiff'):
                    tiff_files.append(obj)
        
        print(f"[INFO] Found {len(tiff_files)} .tiff files")
        
        # Show sample files
        for i, file_info in enumerate(tiff_files[:5]):
            print(f"   {i+1}. {file_info['Key']} ({file_info['Size']} bytes)")
            
        # Test file access
        if tiff_files:
            test_file = tiff_files[0]
            print(f"\n[INFO] Testing file access: {test_file['Key']}")
            
            try:
                # Try to get file metadata
                head_response = s3_client.head_object(
                    Bucket='nz-elevation',
                    Key=test_file['Key']
                )
                print(f"   [OK] File accessible: {head_response['ContentLength']} bytes")
                print(f"   Last modified: {head_response['LastModified']}")
                return True
                
            except Exception as e:
                print(f"   [ERROR] File not accessible: {e}")
                return False
        else:
            print("[WARNING] No .tiff files found for testing")
            return False
            
    except Exception as e:
        print(f"[ERROR] Failed to test NZ elevation files: {e}")
        return False

def main():
    """Run all NZ elevation tests"""
    print("[INFO] NZ Elevation S3 Bucket Test")
    print("=" * 50)
    
    # Test 1: Basic access
    access_success = test_nz_elevation_access()
    
    # Test 2: Structure exploration
    structure_success = test_nz_elevation_structure()
    
    # Test 3: File access
    file_success = test_nz_elevation_files()
    
    print("\n" + "=" * 50)
    print("[RESULTS] Test Results:")
    print(f"   Bucket Access: {'[PASS]' if access_success else '[FAIL]'}")
    print(f"   Structure Exploration: {'[PASS]' if structure_success else '[FAIL]'}")
    print(f"   File Access: {'[PASS]' if file_success else '[FAIL]'}")
    
    if all([access_success, structure_success, file_success]):
        print("\n[SUCCESS] NZ elevation bucket is accessible!")
        print("Next step: Add NZ elevation sources to DEM configuration")
    else:
        print("\n[WARNING] Some tests failed. Check output above for details.")

if __name__ == "__main__":
    main()