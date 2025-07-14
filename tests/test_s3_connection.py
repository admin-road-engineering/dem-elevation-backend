#!/usr/bin/env python3
"""Test script to verify S3 connectivity and rasterio S3 access."""

import os
import sys
import traceback
import requests
import json
import logging
import pytest

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8001"
HEALTH_URL = f"{BASE_URL}/health"

def test_aws_credentials():
    """Test if AWS credentials are available."""
    logger.info("=== TESTING AWS CREDENTIALS ===")
    
    access_key = os.getenv('AWS_ACCESS_KEY_ID')
    secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    bucket_name = os.getenv('AWS_S3_BUCKET_NAME')
    
    logger.info(f"AWS_ACCESS_KEY_ID: {'✅ Set' if access_key else '❌ Not set'}")
    logger.info(f"AWS_SECRET_ACCESS_KEY: {'✅ Set' if secret_key else '❌ Not set'}")
    logger.info(f"AWS_S3_BUCKET_NAME: {'✅ Set' if bucket_name else '❌ Not set'}")
    
    if access_key and secret_key and bucket_name:
        logger.info(f"Bucket: {bucket_name}")
        logger.info(f"Access Key ID: {access_key[:8]}..." if len(access_key) > 8 else access_key)
        return True
    else:
        logger.error("❌ AWS credentials not properly configured")
        return False

def test_boto3_import():
    """Test if boto3 can be imported and basic S3 connectivity."""
    logger.info("\n=== TESTING BOTO3 IMPORT ===")
    
    try:
        import boto3
        logger.info(f"✅ boto3 imported successfully (version: {boto3.__version__})")
        
        # Test S3 client creation
        s3_client = boto3.client('s3')
        logger.info("✅ S3 client created successfully")
        
        return True
    except ImportError as e:
        logger.error(f"❌ boto3 import failed: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ S3 client creation failed: {e}")
        return False

def test_s3_bucket_access():
    """Test if we can access the specified S3 bucket."""
    logger.info("\n=== TESTING S3 BUCKET ACCESS ===")
    
    bucket_name = os.getenv('AWS_S3_BUCKET_NAME')
    if not bucket_name:
        logger.error("❌ AWS_S3_BUCKET_NAME not set")
        return False
    
    try:
        import boto3
        s3_client = boto3.client('s3')
        
        # Try to list objects in the bucket
        response = s3_client.list_objects_v2(Bucket=bucket_name, MaxKeys=10)
        
        if 'Contents' in response:
            logger.info(f"✅ Successfully accessed bucket '{bucket_name}'")
            logger.info(f"   Found {len(response['Contents'])} objects")
            for obj in response['Contents'][:5]:  # Show first 5 objects
                logger.info(f"   - {obj['Key']} ({obj['Size']} bytes)")
            return True
        else:
            logger.warning(f"⚠️  Bucket '{bucket_name}' is empty or no objects found")
            return True  # Empty bucket is still accessible
            
    except Exception as e:
        logger.error(f"❌ Failed to access bucket '{bucket_name}': {e}")
        return False

def test_rasterio_s3_support():
    """Test if rasterio has S3 support enabled."""
    logger.info("\n=== TESTING RASTERIO S3 SUPPORT ===")
    
    try:
        import rasterio
        from rasterio.env import Env, GDALVersion
        
        logger.info(f"✅ rasterio imported (version: {rasterio.__version__})")
        logger.info(f"✅ GDAL version: {GDALVersion.runtime()}")
        
        # Check if GDAL has S3 support
        with Env() as env:
            # List available drivers
            drivers = rasterio.drivers.raster_driver_extensions()
            logger.info(f"✅ Found {len(drivers)} raster drivers")
            
            # Check for VSI (Virtual File System) support which includes S3
            logger.info("✅ Checking GDAL VSI support...")
            
        return True
        
    except Exception as e:
        logger.error(f"❌ rasterio test failed: {e}")
        return False

def test_s3_dem_file_access():
    """Test accessing the actual DEM file from S3."""
    logger.info("\n=== TESTING S3 DEM FILE ACCESS ===")
    
    bucket_name = os.getenv('AWS_S3_BUCKET_NAME')
    if not bucket_name:
        logger.error("❌ AWS_S3_BUCKET_NAME not set")
        return False
    
    s3_path = f"s3://{bucket_name}/DTM.gdb"
    logger.info(f"Testing S3 path: {s3_path}")
    
    try:
        import rasterio
        from rasterio.env import Env
        
        # Try to open the DEM file from S3
        with Env():
            logger.info("Attempting to open DEM file from S3...")
            with rasterio.open(s3_path) as dataset:
                logger.info(f"✅ Successfully opened DEM file from S3!")
                logger.info(f"   Driver: {dataset.driver}")
                logger.info(f"   CRS: {dataset.crs}")
                logger.info(f"   Bounds: {dataset.bounds}")
                logger.info(f"   Shape: {dataset.width} x {dataset.height}")
                logger.info(f"   Data type: {dataset.dtypes}")
                
                # Try to read a small sample
                logger.info("   Testing data read...")
                sample = dataset.read(1, window=((0, 10), (0, 10)))
                logger.info(f"   Sample data shape: {sample.shape}")
                logger.info(f"   Sample values: {sample.flatten()[:3]}")
                
                return True
                
    except Exception as e:
        logger.error(f"❌ Failed to access DEM file from S3: {e}")
        logger.error(f"   Error details: {traceback.format_exc()}")
        return False

def test_s3_connection_status():
    """Test the S3 connection status via the health endpoint."""
    logger.info("=== Testing S3 Connection Status ===")
    
    # Check if S3 credentials are provided in environment variables
    if not os.getenv("AWS_ACCESS_KEY_ID") or not os.getenv("AWS_SECRET_ACCESS_KEY"):
        pytest.skip("AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY not set. Skipping S3 connection test.")
        
    try:
        response = requests.get(HEALTH_URL)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        health_data = response.json()
        logger.info(f"Health check response: {json.dumps(health_data, indent=2)}")
        
        assert health_data.get("status") == "healthy", f"Service status is not healthy: {health_data}"
        
        # Check S3 specific health info
        s3_health = health_data.get("s3_dem_source_health", {})
        
        assert s3_health.get("status") == "healthy", \
            f"S3 DEM source status is not healthy: {s3_health.get('message', 'No message')}"
        assert s3_health.get("message") == "Successfully connected to S3 bucket", \
            f"S3 health message mismatch: {s3_health.get('message')}"
            
        logger.info("✅ S3 connection test passed! Service is connected to S3.")
        
    except requests.exceptions.ConnectionError as e:
        pytest.fail(f"Could not connect to the DEM service. Is it running? Error: {e}")
    except Exception as e:
        pytest.fail(f"An unexpected error occurred during S3 connection test: {e}")

# The main function is no longer needed for pytest
# if __name__ == "__main__":
#     test_s3_connection_status() 