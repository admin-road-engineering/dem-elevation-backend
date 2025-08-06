#!/usr/bin/env python3
"""Download and fix NZ index in one go"""

import json
import os
import boto3
from pathlib import Path

# Set AWS credentials
os.environ['AWS_ACCESS_KEY_ID'] = 'AKIA5SIDYET7N3U4JQ5H'
os.environ['AWS_SECRET_ACCESS_KEY'] = '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'
os.environ['AWS_DEFAULT_REGION'] = 'ap-southeast-2'

def fix_bounds_format(bounds):
    """Convert bounds to canonical WGS84 format"""
    # If already in correct format, return as-is
    if all(k in bounds for k in ['min_lat', 'max_lat', 'min_lon', 'max_lon']):
        return bounds
    
    # Handle x/y format (common in GIS where x=lon, y=lat)
    if all(k in bounds for k in ['min_x', 'max_x', 'min_y', 'max_y']):
        return {
            'min_lat': float(bounds['min_y']),
            'max_lat': float(bounds['max_y']),
            'min_lon': float(bounds['min_x']),
            'max_lon': float(bounds['max_x'])
        }
    
    # Handle rasterio BoundingBox format
    if all(k in bounds for k in ['left', 'right', 'bottom', 'top']):
        return {
            'min_lat': float(bounds['bottom']),
            'max_lat': float(bounds['top']),
            'min_lon': float(bounds['left']),
            'max_lon': float(bounds['right'])
        }
    
    return bounds

# Download from S3
print("Downloading NZ index from S3...")
s3 = boto3.client('s3')
response = s3.get_object(
    Bucket='road-engineering-elevation-data',
    Key='indexes/nz_spatial_index.json'
)
index_data = json.loads(response['Body'].read())

print(f"Loaded index with {len(index_data.get('collections', []))} collections")

# Check current format
sample_collection = None
for coll in index_data.get('collections', []):
    if coll.get('files'):
        sample_collection = coll
        break

if sample_collection:
    print(f"\nSample collection: {sample_collection.get('name')}")
    if sample_collection.get('files'):
        sample_file = sample_collection['files'][0]
        bounds = sample_file.get('bounds', {})
        print(f"Current bounds keys: {list(bounds.keys())}")
        print(f"Current bounds: {bounds}")

# Fix all bounds
total_files = 0
fixed_files = 0

for collection in index_data.get('collections', []):
    # Fix collection bounds
    if 'bounds' in collection:
        collection['bounds'] = fix_bounds_format(collection['bounds'])
    
    # Fix file bounds
    for file_entry in collection.get('files', []):
        total_files += 1
        if 'bounds' in file_entry:
            old_bounds = file_entry['bounds']
            new_bounds = fix_bounds_format(old_bounds)
            if old_bounds != new_bounds:
                file_entry['bounds'] = new_bounds
                fixed_files += 1

print(f"\nFixed {fixed_files}/{total_files} file bounds")

# Add metadata
if 'metadata' not in index_data:
    index_data['metadata'] = {}

index_data['metadata']['schema_version'] = '1.1'
index_data['metadata']['bounds_format'] = 'wgs84_canonical'
index_data['metadata']['bounds_crs'] = 'EPSG:4326'

# Save locally
output_path = Path('data/indexes/nz_spatial_index_fixed.json')
output_path.parent.mkdir(parents=True, exist_ok=True)

with open(output_path, 'w') as f:
    json.dump(index_data, f, indent=2)

print(f"\n✅ Fixed index saved to: {output_path}")

# Verify fix
if sample_collection:
    # Reload to verify
    with open(output_path, 'r') as f:
        fixed_data = json.load(f)
    
    for coll in fixed_data.get('collections', []):
        if coll.get('id') == sample_collection.get('id'):
            if coll.get('files'):
                fixed_file = coll['files'][0]
                fixed_bounds = fixed_file.get('bounds', {})
                print(f"\nFixed bounds keys: {list(fixed_bounds.keys())}")
                print(f"Fixed bounds: {fixed_bounds}")
                
                has_wgs84 = all(k in fixed_bounds for k in ['min_lat', 'max_lat', 'min_lon', 'max_lon'])
                print(f"Has WGS84 keys: {has_wgs84}")
                
                # Check Auckland
                auckland_lat, auckland_lon = -36.8485, 174.7633
                if has_wgs84:
                    in_bounds = (fixed_bounds['min_lat'] <= auckland_lat <= fixed_bounds['max_lat'] and
                               fixed_bounds['min_lon'] <= auckland_lon <= fixed_bounds['max_lon'])
                    print(f"Auckland in first file bounds: {in_bounds}")
            break