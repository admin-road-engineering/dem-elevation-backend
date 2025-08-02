#!/usr/bin/env python3
"""
Upload unified spatial index to S3 for Phase 2 deployment
"""
import os
import json
import boto3
from pathlib import Path
from botocore.exceptions import NoCredentialsError, ProfileNotFound
from dotenv import load_dotenv

def upload_unified_index():
    """Upload unified spatial index to S3 bucket"""
    print("Uploading unified spatial index v2.0 to S3...")
    
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
        
        # Upload unified spatial index
        bucket_name = "road-engineering-elevation-data"
        local_path = Path("config/unified_spatial_index_v2.json")
        s3_key = "indexes/unified_spatial_index_v2.json"
        
        if not local_path.exists():
            print(f"[ERROR] Local file not found: {local_path}")
            print("[INFO] Run: python scripts/migrate_to_unified_index.py generate")
            return False
        
        # Check file size
        file_size_mb = local_path.stat().st_size / (1024 * 1024)
        print(f"[INFO] Uploading {local_path} ({file_size_mb:.1f} MB)")
        print(f"[INFO] Destination: s3://{bucket_name}/{s3_key}")
        
        # Upload file with progress (for large files)
        def upload_callback(bytes_transferred):
            percentage = (bytes_transferred / local_path.stat().st_size) * 100
            print(f"\r[UPLOAD] Progress: {percentage:.1f}%", end='', flush=True)
        
        s3_client.upload_file(
            str(local_path),
            bucket_name,
            s3_key,
            Callback=upload_callback,
            ExtraArgs={'ContentType': 'application/json'}
        )
        
        print(f"\n[SUCCESS] Unified spatial index uploaded successfully")
        
        # Verify upload
        response = s3_client.head_object(Bucket=bucket_name, Key=s3_key)
        size_mb = response['ContentLength'] / (1024 * 1024)
        print(f"[VERIFY] File size: {size_mb:.2f} MB")
        print(f"[VERIFY] Last modified: {response['LastModified']}")
        
        # Show next steps
        print("\n" + "="*60)
        print("PHASE 2 DEPLOYMENT NEXT STEPS:")
        print("="*60)
        print("1. Enable unified architecture:")
        print("   railway variables --set \"USE_UNIFIED_SPATIAL_INDEX=true\"")
        print("")
        print("2. Deploy to Railway:")
        print("   git push  # Triggers automatic deployment")
        print("")
        print("3. Test coordinates:")
        print("   Brisbane: https://re-dem-elevation-backend.up.railway.app/api/v1/elevation?lat=-27.4698&lon=153.0251")
        print("   Auckland: https://re-dem-elevation-backend.up.railway.app/api/v1/elevation?lat=-36.8485&lon=174.7633")
        print("")
        print("4. Monitor health:")
        print("   https://re-dem-elevation-backend.up.railway.app/api/v1/health")
        print("="*60)
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Upload failed: {e}")
        return False

if __name__ == "__main__":
    success = upload_unified_index()
    if success:
        print("\n[COMPLETE] Ready for Phase 2 deployment!")
    else:
        print("\n[FAILED] Upload failed - check credentials and file")