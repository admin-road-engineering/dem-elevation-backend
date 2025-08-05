#!/usr/bin/env python3
"""
List Brisbane files in S3 bucket to find correct paths
"""
import boto3
import os
from pathlib import Path

def list_brisbane_files():
    """List Brisbane files in S3 bucket"""
    
    # Load credentials from .env
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
    
    # Create S3 client
    s3_client = boto3.client(
        's3',
        aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
        region_name=os.environ['AWS_DEFAULT_REGION']
    )
    
    bucket = 'road-engineering-elevation-data'
    print(f"Listing Brisbane files in bucket: {bucket}")
    
    # First, let's see what's in the root of the bucket
    print("\n=== Root level folders ===")
    paginator = s3_client.get_paginator('list_objects_v2')
    page_iterator = paginator.paginate(Bucket=bucket, Delimiter='/')
    
    for page in page_iterator:
        if 'CommonPrefixes' in page:
            for prefix in page['CommonPrefixes']:
                print(f"Folder: {prefix['Prefix']}")
    
    # List all objects with Brisbane in the key (case insensitive)
    print("\n=== Searching for Brisbane files ===")
    page_iterator = paginator.paginate(Bucket=bucket)
    
    brisbane_files = []
    all_keys = []
    for page in page_iterator:
        if 'Contents' in page:
            for obj in page['Contents']:
                key = obj['Key']
                all_keys.append(key)
                if 'brisbane' in key.lower():
                    brisbane_files.append((key, obj.get('Size', 0)))
    
    print(f"Total objects in bucket: {len(all_keys)}")
    print(f"Brisbane-related objects: {len(brisbane_files)}")
    
    # Show Brisbane objects (not just .tif)
    for key, size in brisbane_files[:20]:
        size_mb = size / (1024*1024) if size > 0 else 0
        print(f"  {key} ({size_mb:.1f} MB)")
    
    print(f"\nFound {len(brisbane_files)} Brisbane .tif files:")
    for i, file_key in enumerate(brisbane_files[:10]):  # Show first 10
        print(f"{i+1:2d}. s3://{bucket}/{file_key}")
        size_mb = obj.get('Size', 0) / (1024*1024)
        print(f"    Size: {size_mb:.1f} MB")
    
    if len(brisbane_files) > 10:
        print(f"... and {len(brisbane_files) - 10} more files")
    
    # Test one of the files
    if brisbane_files:
        test_file = f"s3://{bucket}/{brisbane_files[0]}"
        print(f"\n=== Testing file: {test_file} ===")
        
        try:
            import rasterio
            from rasterio.env import Env
            
            with Env(AWS_REGION='ap-southeast-2'):
                with rasterio.open(test_file) as src:
                    print(f"SUCCESS: Opened file")
                    print(f"Size: {src.width} x {src.height}")
                    print(f"CRS: {src.crs}")
                    print(f"Bounds: {src.bounds}")
                    
                    # Test Brisbane coordinates
                    brisbane_lat, brisbane_lon = -27.4698, 153.0251
                    from rasterio.warp import transform
                    xs, ys = transform('EPSG:4326', src.crs, [brisbane_lon], [brisbane_lat])
                    x, y = xs[0], ys[0]
                    print(f"Transformed coordinates: ({x}, {y})")
                    
                    # Check if within bounds
                    if src.bounds.left <= x <= src.bounds.right and src.bounds.bottom <= y <= src.bounds.top:
                        print("✅ Coordinates are within file bounds!")
                        
                        # Try to extract elevation
                        row, col = src.index(x, y)
                        if 0 <= row < src.height and 0 <= col < src.width:
                            elevation = src.read(1, window=rasterio.windows.Window(col, row, 1, 1))
                            print(f"ELEVATION: {elevation[0, 0]}m")
                        else:
                            print("❌ Pixel coordinates outside raster")
                    else:
                        print("❌ Coordinates are outside file bounds")
                        print(f"File bounds: {src.bounds}")
                        
        except Exception as e:
            print(f"Failed to test file: {e}")

if __name__ == "__main__":
    list_brisbane_files()