#!/usr/bin/env python3
"""
Upload UTM Bounds Index: Phase 6 P0 Critical Fix

This script uploads the corrected unified index with UTM bounds to S3,
replacing the WGS84 bounds version to fix the data-code contract violation.
"""

import boto3
import logging
from pathlib import Path
import json
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def upload_utm_bounds_index():
    """Upload the corrected unified index with UTM bounds to S3"""
    
    # Configuration
    bucket_name = "road-engineering-elevation-data"
    source_file = Path("config/unified_spatial_index_v2_utm_bounds.json")
    s3_key = "indexes/unified_spatial_index_v2_ideal.json"  # Replace the existing ideal index
    
    if not source_file.exists():
        logger.error(f"Source file not found: {source_file}")
        return False
    
    try:
        # Create S3 client with correct credentials from .env
        s3_client = boto3.client(
            's3',
            aws_access_key_id='AKIA5SIDYET7N3U4JQ5H',
            aws_secret_access_key='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',
            region_name='ap-southeast-2'
        )
        
        # Get file size for progress tracking
        file_size = source_file.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        
        logger.info(f"=== Uploading UTM Bounds Index to S3 ===")
        logger.info(f"Source: {source_file}")
        logger.info(f"Target: s3://{bucket_name}/{s3_key}")
        logger.info(f"Size: {file_size_mb:.1f} MB")
        
        # Upload file
        logger.info("Starting upload...")
        start_time = datetime.now()
        
        s3_client.upload_file(
            str(source_file),
            bucket_name,
            s3_key,
            ExtraArgs={
                'ContentType': 'application/json',
                'Metadata': {
                    'transformation': 'wgs84_to_utm_bounds',
                    'upload_date': datetime.utcnow().isoformat(),
                    'original_file': 'unified_spatial_index_v2_ideal.json',
                    'phase': 'phase_6_p0_critical_fix'
                }
            }
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info(f"✅ Upload completed successfully!")
        logger.info(f"Duration: {duration:.1f} seconds")
        logger.info(f"Speed: {file_size_mb/duration:.1f} MB/s")
        
        # Verify upload by checking S3 object
        logger.info("Verifying upload...")
        response = s3_client.head_object(Bucket=bucket_name, Key=s3_key)
        s3_size = response['ContentLength']
        
        if s3_size == file_size:
            logger.info(f"✅ Verification successful: S3 size ({s3_size}) matches local size ({file_size})")
            return True
        else:
            logger.error(f"❌ Verification failed: S3 size ({s3_size}) != local size ({file_size})")
            return False
            
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main function"""
    logger.info("=== Phase 6 P0: Upload UTM Bounds Index ===")
    
    # Load and verify the corrected index first
    source_file = Path("config/unified_spatial_index_v2_utm_bounds.json")
    
    try:
        logger.info("Verifying corrected index structure...")
        with open(source_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        total_collections = len(data.get('data_collections', []))
        transformation_stats = data.get('transformation_metadata', {}).get('stats', {})
        
        logger.info(f"Index contains {total_collections} collections")
        logger.info(f"Transformation stats: {transformation_stats}")
        
        # Check for Brisbane campaigns with UTM bounds
        brisbane_found = False
        for collection in data['data_collections'][:100]:  # Check first 100
            if 'Brisbane' in collection.get('campaign_name', ''):
                bounds = collection['coverage_bounds']
                if 'min_x' in bounds and 'min_y' in bounds:
                    logger.info(f"Brisbane campaign verified: {collection['campaign_name']} has UTM bounds")
                    brisbane_found = True
                    break
        
        if not brisbane_found:
            logger.warning("No Brisbane campaigns found in first 100 collections")
        
        # Proceed with upload
        success = upload_utm_bounds_index()
        
        if success:
            logger.info("🎉 UTM Bounds Index successfully deployed to S3!")
            logger.info("✅ Brisbane coordinate system mismatch should now be fixed")
            logger.info("🔄 Railway will automatically reload the corrected index")
            return True
        else:
            logger.error("❌ Upload failed")
            return False
            
    except Exception as e:
        logger.error(f"Index verification failed: {e}")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)