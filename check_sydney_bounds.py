#!/usr/bin/env python3
"""Check actual bounds of Sydney files in S3"""
import rasterio
import os

# Set up environment for S3 access using environment variables
if not os.environ.get('AWS_ACCESS_KEY_ID'):
    print("⚠️ ERROR: AWS_ACCESS_KEY_ID not set in environment")
    exit(1)
if not os.environ.get('AWS_SECRET_ACCESS_KEY'):
    print("⚠️ ERROR: AWS_SECRET_ACCESS_KEY not set in environment")
    exit(1)
os.environ.setdefault('AWS_DEFAULT_REGION', 'ap-southeast-2')

# Open a Sydney file to check its actual bounds
sydney_file = 's3://road-engineering-elevation-data/nsw-elvis/elevation/1m-dem/z56/Sydney201105/Sydney201105-LID1-AHD_3146266_56_0002_0002_1m.tif'

print(f'Checking bounds of Sydney file...')
try:
    with rasterio.open(sydney_file) as src:
        bounds = src.bounds
        print(f'File: Sydney201105-LID1-AHD_3146266_56_0002_0002_1m.tif')
        print(f'CRS: {src.crs}')
        print(f'Bounds: {bounds}')
        
        # If UTM, transform to WGS84
        if src.crs and src.crs.to_epsg() != 4326:
            from rasterio.warp import transform_bounds
            wgs84_bounds = transform_bounds(src.crs, 'EPSG:4326', *bounds)
            print(f'WGS84 bounds: {wgs84_bounds}')
            print(f'  Lat: {wgs84_bounds[1]:.4f} to {wgs84_bounds[3]:.4f}')
            print(f'  Lon: {wgs84_bounds[0]:.4f} to {wgs84_bounds[2]:.4f}')
            
            # Check if Sydney CBD would be in these bounds
            sydney_lat, sydney_lon = -33.8568, 151.2153
            in_bounds = (wgs84_bounds[1] <= sydney_lat <= wgs84_bounds[3] and 
                        wgs84_bounds[0] <= sydney_lon <= wgs84_bounds[2])
            print(f'Sydney CBD ({sydney_lat}, {sydney_lon}) in this file: {in_bounds}')
except Exception as e:
    print(f'Error: {e}')