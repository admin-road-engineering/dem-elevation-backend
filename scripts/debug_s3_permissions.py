#!/usr/bin/env python3
"""
Debug S3 permissions and access
"""

import boto3
from pathlib import Path

def load_env_manually():
    """Load .env file manually"""
    env_file = Path(__file__).parent.parent / ".env"
    credentials = {}
    
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('AWS_ACCESS_KEY_ID='):
                credentials['access_key'] = line.split('=', 1)[1]
            elif line.startswith('AWS_SECRET_ACCESS_KEY='):
                credentials['secret_key'] = line.split('=', 1)[1]
    
    return credentials.get('access_key'), credentials.get('secret_key')

def debug_permissions():
    """Debug what permissions we actually have"""
    access_key, secret_key = load_env_manually()
    
    print("S3 Permissions Debug")
    print("=" * 30)
    print(f"Access Key: {access_key[:4]}...{access_key[-4:]}")
    
    s3_client = boto3.client(
        's3',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name='ap-southeast-2'
    )
    
    # Test 1: List all buckets (basic S3 access)
    print("\n1. Testing ListBuckets permission...")
    try:
        response = s3_client.list_buckets()
        buckets = [bucket['Name'] for bucket in response['Buckets']]
        print(f"SUCCESS: Can list {len(buckets)} buckets")
        if 'road-engineering-elevation-data' in buckets:
            print("  ✓ Target bucket 'road-engineering-elevation-data' found")
        else:
            print("  ✗ Target bucket 'road-engineering-elevation-data' NOT found")
            print(f"  Available buckets: {buckets}")
    except Exception as e:
        print(f"FAILED: {str(e)}")
    
    # Test 2: Get bucket location
    print("\n2. Testing GetBucketLocation permission...")
    try:
        response = s3_client.get_bucket_location(Bucket='road-engineering-elevation-data')
        print(f"SUCCESS: Bucket region: {response.get('LocationConstraint', 'us-east-1')}")
    except Exception as e:
        print(f"FAILED: {str(e)}")
    
    # Test 3: List objects in bucket
    print("\n3. Testing ListObjects permission...")
    try:
        response = s3_client.list_objects_v2(
            Bucket='road-engineering-elevation-data',
            MaxKeys=5
        )
        if 'Contents' in response:
            print(f"SUCCESS: Can list objects, found {len(response['Contents'])} items")
            for obj in response['Contents'][:3]:
                print(f"  - {obj['Key']}")
        else:
            print("SUCCESS: Can list objects, but bucket is empty")
    except Exception as e:
        print(f"FAILED: {str(e)}")
    
    # Test 4: List top-level "folders"
    print("\n4. Testing folder listing...")
    try:
        response = s3_client.list_objects_v2(
            Bucket='road-engineering-elevation-data',
            Delimiter='/',
            MaxKeys=20
        )
        if 'CommonPrefixes' in response:
            folders = [prefix['Prefix'].rstrip('/') for prefix in response['CommonPrefixes']]
            print(f"SUCCESS: Found {len(folders)} top-level folders:")
            for folder in folders:
                print(f"  - {folder}")
        else:
            print("No folders found (but no error)")
    except Exception as e:
        print(f"FAILED: {str(e)}")
    
    # Test 5: Check if we can get a specific object
    print("\n5. Testing object access...")
    try:
        # Try to get metadata for any object
        response = s3_client.list_objects_v2(
            Bucket='road-engineering-elevation-data',
            MaxKeys=1
        )
        if 'Contents' in response and response['Contents']:
            first_object = response['Contents'][0]['Key']
            print(f"Trying to get metadata for: {first_object}")
            
            response = s3_client.head_object(
                Bucket='road-engineering-elevation-data',
                Key=first_object
            )
            print(f"SUCCESS: Can access object metadata")
            print(f"  Size: {response['ContentLength']} bytes")
            print(f"  Last Modified: {response['LastModified']}")
        else:
            print("No objects found to test")
    except Exception as e:
        print(f"FAILED: {str(e)}")

if __name__ == "__main__":
    debug_permissions()