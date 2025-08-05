#!/usr/bin/env python3
"""
Upload the fixed unified index to S3
"""
import os
import boto3
from pathlib import Path

def upload_fixed_index():
    """Upload corrected unified index to S3"""
    
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
    
    # Upload the fixed index
    local_file = project_root / "config" / "unified_spatial_index_v2_fixed.json"
    s3_key = "indexes/unified_spatial_index_v2.json"
    
    print(f"Uploading {local_file} to s3://{bucket_name}/{s3_key}")
    
    try:
        s3_client.upload_file(str(local_file), bucket_name, s3_key)
        print("SUCCESS: Fixed unified index uploaded to S3!")
        print(f"Railway will now load the corrected index with 661,314 files")
        print(f"Brisbane coordinates should now return elevation data")
        
    except Exception as e:
        print(f"ERROR uploading to S3: {e}")

if __name__ == "__main__":
    upload_fixed_index()