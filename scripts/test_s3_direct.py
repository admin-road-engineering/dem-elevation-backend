#!/usr/bin/env python3
"""
Direct S3 test with manual credential loading
"""

import boto3
import os
from pathlib import Path

def load_env_manually():
    """Load .env file manually"""
    env_file = Path(__file__).parent.parent / ".env"
    
    if not env_file.exists():
        print(f"ERROR: .env file not found at {env_file}")
        return None, None
    
    credentials = {}
    
    with open(env_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if line.startswith('AWS_ACCESS_KEY_ID='):
                credentials['access_key'] = line.split('=', 1)[1]
                print(f"Found AWS_ACCESS_KEY_ID on line {line_num}")
            elif line.startswith('AWS_SECRET_ACCESS_KEY='):
                credentials['secret_key'] = line.split('=', 1)[1]
                print(f"Found AWS_SECRET_ACCESS_KEY on line {line_num}")
    
    return credentials.get('access_key'), credentials.get('secret_key')

def test_s3_connection():
    """Test S3 connection with manual credential loading"""
    print("Loading credentials from .env file...")
    
    access_key, secret_key = load_env_manually()
    
    if not access_key or not secret_key:
        print("ERROR: Could not find AWS credentials in .env file")
        return False
    
    print(f"Access Key: {access_key[:4]}...{access_key[-4:]}")
    print(f"Secret Key: {secret_key[:4]}...{secret_key[-4:]}")
    
    try:
        # Create S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name='ap-southeast-2'
        )
        
        print("Testing S3 connection...")
        
        # Test bucket access
        bucket_name = 'road-engineering-elevation-data'
        response = s3_client.head_bucket(Bucket=bucket_name)
        print(f"SUCCESS: Connected to bucket '{bucket_name}'")
        
        # List top-level folders
        print("Listing top-level folders...")
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Delimiter='/',
            MaxKeys=20
        )
        
        if 'CommonPrefixes' in response:
            folders = [prefix['Prefix'].rstrip('/') for prefix in response['CommonPrefixes']]
            print(f"Found {len(folders)} top-level folders:")
            for folder in folders:
                print(f"  - {folder}")
        else:
            print("No folders found in bucket")
        
        return True
        
    except Exception as e:
        print(f"ERROR: S3 connection failed: {str(e)}")
        return False

if __name__ == "__main__":
    print("S3 Direct Connection Test")
    print("=" * 30)
    
    success = test_s3_connection()
    
    if success:
        print("\nSUCCESS: S3 connection working!")
        print("You can now run the full structure explorer")
    else:
        print("\nFAILED: Check your credentials and try again")