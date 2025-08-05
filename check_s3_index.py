#!/usr/bin/env python3
"""
Check S3 index status
"""
import os
import boto3
import json
from pathlib import Path

def check_s3_index():
    """Check S3 index status"""
    
    # Load environment
    project_root = Path(__file__).parent
    env_file = project_root / '.env'
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
    
    # Initialize S3 client
    s3_client = boto3.client(
        's3',
        aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
        region_name=os.environ.get('AWS_DEFAULT_REGION', 'ap-southeast-2')
    )
    
    bucket_name = os.environ.get('AWS_S3_BUCKET_NAME', 'road-engineering-elevation-data')
    
    # List indexes
    print(f"Checking S3 bucket: {bucket_name}/indexes/")
    
    try:
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix='indexes/'
        )
        
        if 'Contents' in response:
            for obj in response['Contents']:
                key = obj['Key']
                size_mb = obj['Size'] / (1024 * 1024)
                modified = obj['LastModified']
                print(f"  OK {key} ({size_mb:.1f} MB) - {modified}")
        else:
            print("  ERROR No indexes found!")
            
        # Check specific file
        key = "indexes/unified_spatial_index_v2.json"
        try:
            head_response = s3_client.head_object(Bucket=bucket_name, Key=key)
            size_mb = head_response['ContentLength'] / (1024 * 1024)
            modified = head_response['LastModified']
            print(f"\nTarget index: {key}")
            print(f"   Size: {size_mb:.1f} MB")
            print(f"   Modified: {modified}")
            
            # Download and check content
            obj_response = s3_client.get_object(Bucket=bucket_name, Key=key)
            content = json.loads(obj_response['Body'].read())
            
            total_collections = len(content.get('data_collections', []))
            total_files = sum(c.get('file_count', 0) for c in content.get('data_collections', []))
            
            print(f"   Collections: {total_collections}")
            print(f"   Total files: {total_files}")
            
            if total_collections == 1339:
                print("   SUCCESS: 1,339 collections found!")
            else:
                print(f"   ERROR: Expected 1,339 collections, found {total_collections}")
                
        except Exception as e:
            print(f"   ERROR checking {key}: {e}")
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    check_s3_index()