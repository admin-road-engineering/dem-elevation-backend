#!/usr/bin/env python3
"""
Find the correct NZ file for Auckland CBD coordinates
"""
import boto3
import rasterio
from botocore import UNSIGNED
from botocore.config import Config
import os
from rasterio.warp import transform

def find_auckland_file():
    """Find NZ file containing Auckland CBD"""
    print("=== Finding Auckland File ===")
    
    # Setup
    s3_client = boto3.client('s3', region_name='ap-southeast-2', config=Config(signature_version=UNSIGNED))
    bucket_name = "nz-elevation"
    
    # Configure GDAL for unsigned access
    os.environ['AWS_NO_SIGN_REQUEST'] = 'YES'
    os.environ['GDAL_DISABLE_READDIR_ON_OPEN'] = 'EMPTY_DIR'
    
    # Auckland test coordinate
    test_lat, test_lon = -36.8485, 174.7633
    print(f"Looking for file containing: ({test_lat}, {test_lon})")
    
    # List Auckland files
    response = s3_client.list_objects_v2(
        Bucket=bucket_name,
        Prefix="auckland/",
        MaxKeys=50
    )
    
    tiff_files = [obj['Key'] for obj in response.get('Contents', []) if obj['Key'].endswith('.tiff')]
    print(f"Found {len(tiff_files)} TIFF files")
    
    for file_key in tiff_files[:10]:  # Test first 10 files
        print(f"\nTesting: {file_key}")
        vsi_path = f"/vsis3/{bucket_name}/{file_key}"
        
        try:
            with rasterio.open(vsi_path) as dataset:
                # Transform coordinate to dataset CRS
                xs, ys = transform('EPSG:4326', dataset.crs, [test_lon], [test_lat])
                x, y = xs[0], ys[0]
                
                # Check bounds
                left, bottom, right, top = dataset.bounds
                if left <= x <= right and bottom <= y <= top:
                    print(f"SUCCESS: File contains coordinate!")
                    print(f"  Bounds: ({left:.2f}, {bottom:.2f}) to ({right:.2f}, {top:.2f})")
                    print(f"  Coord: ({x:.2f}, {y:.2f})")
                    
                    # Test elevation extraction
                    row, col = dataset.index(x, y)
                    if 0 <= row < dataset.height and 0 <= col < dataset.width:
                        elevation = dataset.read(1)[row, col]
                        if dataset.nodata is None or elevation != dataset.nodata:
                            print(f"  Elevation: {elevation} meters")
                            return file_key
                        
        except Exception as e:
            print(f"  Error: {e}")
            continue
    
    print("No suitable file found")
    return None

if __name__ == "__main__":
    result = find_auckland_file()
    if result:
        print(f"\nUse this file for testing: {result}")
    else:
        print("\nNo file found containing the Auckland coordinate")