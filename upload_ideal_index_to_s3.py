#!/usr/bin/env python3
"""
DEBUGGING PROTOCOL PHASE 2: Upload correct unified index to S3

This script uploads the working unified_spatial_index_v2_ideal.json to S3
so that production Railway can load the correct 1,582 collection index.
"""

import boto3
import json
import os
from pathlib import Path

def upload_ideal_index():
    """Upload the ideal unified index to S3 for production use"""
    
    print("=== UPLOADING IDEAL UNIFIED INDEX TO S3 ===")
    
    # Local index file (392MB backward-compatible WGS84 format for production)  
    local_index = Path("config/unified_spatial_index_v2_compatible.json")
    
    if not local_index.exists():
        print(f"ERROR: Local index file not found: {local_index}")
        return False
    
    # Load and validate the index
    print(f"Loading index from: {local_index}")
    with open(local_index, 'r') as f:
        index_data = json.load(f)
    
    total_collections = len(index_data.get('data_collections', []))
    print(f"Index contains {total_collections} collections")
    
    if total_collections != 1582:
        print(f"WARNING: Expected 1582 collections, found {total_collections}")
    
    # AWS credentials from .env file or environment
    aws_access_key = os.getenv('AWS_ACCESS_KEY_ID', 'AKIA5SIDYET7N3U4JQ5H')
    aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY', '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')
    aws_region = os.getenv('AWS_DEFAULT_REGION', 'ap-southeast-2')
    
    if not aws_access_key or not aws_secret_key:
        print("ERROR: AWS credentials not found")
        return False
    
    print(f"Using AWS region: {aws_region}")
    
    # Create S3 client
    s3_client = boto3.client(
        's3',
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region
    )
    
    # Upload to S3 - using production-expected filename  
    bucket = "road-engineering-elevation-data"
    s3_key = "indexes/unified_spatial_index_v2_ideal.json"
    
    print(f"Uploading to s3://{bucket}/{s3_key}")
    
    try:
        # Upload with progress
        file_size = local_index.stat().st_size
        print(f"File size: {file_size / (1024*1024):.1f} MB")
        
        s3_client.upload_file(
            str(local_index),
            bucket,
            s3_key,
            ExtraArgs={
                'ContentType': 'application/json',
                'Metadata': {
                    'total_collections': str(total_collections),
                    'upload_timestamp': str(index_data.get('schema_metadata', {}).get('generated_at', '')),
                    'purpose': 'nz_debugging_protocol_phase2'
                }
            }
        )
        
        print("SUCCESS: Upload completed successfully!")
        
        # Verify upload
        print("Verifying upload...")
        response = s3_client.head_object(Bucket=bucket, Key=s3_key)
        uploaded_size = response['ContentLength']
        print(f"Verified: {uploaded_size / (1024*1024):.1f} MB uploaded")
        
        if abs(uploaded_size - file_size) < 1024:  # Allow 1KB difference
            print("SUCCESS: Upload verification successful!")
            return True
        else:
            print(f"ERROR: Size mismatch - local: {file_size}, uploaded: {uploaded_size}")
            return False
            
    except Exception as e:
        print(f"ERROR: Upload failed: {e}")
        return False

if __name__ == "__main__":
    success = upload_ideal_index()
    if success:
        print("\nPHASE 2 COMPLETE: Index uploaded successfully")
        print("Railway should now load the correct 1,582 collection index")
        print("Both AU and NZ coordinates should work after restart")
    else:
        print("\nPHASE 2 FAILED: Index upload unsuccessful")
        exit(1)