#!/usr/bin/env python3
"""
Upload NZ spatial index to S3
"""
import os
import json
import boto3
from pathlib import Path
from botocore.exceptions import NoCredentialsError, ProfileNotFound
from dotenv import load_dotenv

def upload_nz_index():
    """Upload NZ spatial index to S3 bucket"""
    print("Uploading NZ spatial index to S3...")
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Try multiple credential sources
    s3_client = None
    
    # Try environment variables first (now loaded from .env)
    if os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY'):
        print("[INFO] Using environment variables for AWS credentials")
        s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_DEFAULT_REGION', 'ap-southeast-2')
        )
    else:
        # Try default AWS credentials (from ~/.aws/credentials or IAM role)
        print("[INFO] Trying default AWS credentials...")
        try:
            s3_client = boto3.client('s3', region_name='ap-southeast-2')
            # Test the credentials by listing buckets
            s3_client.list_buckets()
            print("[INFO] Using default AWS credentials")
        except (NoCredentialsError, ProfileNotFound):
            print("[ERROR] No AWS credentials found")
            return False
        except Exception as e:
            print(f"[ERROR] AWS credentials test failed: {e}")
            return False
        
    try:
        # Create S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_DEFAULT_REGION', 'ap-southeast-2')
        )
        
        # Upload NZ spatial index
        bucket_name = "road-engineering-elevation-data"
        local_path = Path("config/nz_spatial_index.json")
        s3_key = "indexes/nz_spatial_index.json"
        
        if not local_path.exists():
            print(f"[ERROR] Local file not found: {local_path}")
            return False
        
        print(f"[UPLOAD] Uploading {local_path} to s3://{bucket_name}/{s3_key}")
        
        # Upload file
        s3_client.upload_file(
            str(local_path),
            bucket_name,
            s3_key,
            ExtraArgs={'ContentType': 'application/json'}
        )
        
        print(f"[SUCCESS] NZ spatial index uploaded successfully")
        
        # Verify upload
        response = s3_client.head_object(Bucket=bucket_name, Key=s3_key)
        size_mb = response['ContentLength'] / (1024 * 1024)
        print(f"[VERIFY] File size: {size_mb:.2f} MB")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Upload failed: {e}")
        return False

if __name__ == "__main__":
    success = upload_nz_index()
    if success:
        print("\n[COMPLETE] NZ spatial index upload completed successfully")
    else:
        print("\n[FAILED] NZ spatial index upload failed")