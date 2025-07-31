#!/usr/bin/env python3
import boto3
from botocore.config import Config

s3_client = boto3.client('s3', region_name='ap-southeast-2', config=Config(connect_timeout=5, read_timeout=30))
bucket = 'road-engineering-elevation-data'

import os

required_files = [
    os.getenv('S3_CAMPAIGN_INDEX_KEY', 'indexes/campaign_index.json'),
    os.getenv('S3_TILED_INDEX_KEY', 'indexes/phase3_brisbane_tiled_index.json'), 
    os.getenv('S3_SPATIAL_INDEX_KEY', 'indexes/spatial_index.json')
]

print("Checking required index files:")
for file_key in required_files:
    try:
        response = s3_client.head_object(Bucket=bucket, Key=file_key)
        size_mb = response['ContentLength'] / (1024 * 1024)
        print(f"OK {file_key}: {size_mb:.2f} MB")
    except Exception as e:
        print(f"MISSING {file_key}: {str(e)}")

print("\nListing all files in indexes/ directory:")
try:
    objects = s3_client.list_objects_v2(Bucket=bucket, Prefix='indexes/')
    if 'Contents' in objects:
        for obj in objects['Contents']:
            size_mb = obj['Size'] / (1024 * 1024)
            print(f"FOUND {obj['Key']}: {size_mb:.2f} MB")
    else:
        print("No files found in indexes/ directory")
except Exception as e:
    print(f"Failed to list indexes: {e}")