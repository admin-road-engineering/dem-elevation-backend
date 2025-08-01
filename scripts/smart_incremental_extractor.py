#!/usr/bin/env python3
"""
Smart Incremental Metadata Extractor
Uses folder timestamps and AWS CLI for efficient new file detection
"""
import json
import time
import logging
import boto3
import subprocess
from pathlib import Path
from typing import Dict, List, Set
from datetime import datetime, timezone
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.direct_metadata_extractor import DirectMetadataExtractor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)8s | %(message)s'
)
logger = logging.getLogger(__name__)

class SmartIncrementalExtractor:
    def __init__(self, bucket_name: str = "road-engineering-elevation-data"):
        self.bucket_name = bucket_name
        self.config_dir = Path("config")
        self.extractor = DirectMetadataExtractor(bucket_name)
        
    def load_existing_index(self) -> Dict:
        """Load the current spatial index"""
        index_file = self.config_dir / "precise_spatial_index.json"
        logger.info(f"Loading existing spatial index from {index_file}")
        
        with open(index_file, 'r') as f:
            return json.load(f)
    
    def get_last_update_timestamp(self, spatial_index: Dict) -> datetime:
        """Get timestamp of last index update"""
        timestamp_str = spatial_index.get("index_timestamp", "2024-01-01T00:00:00")
        
        # Handle different timestamp formats
        try:
            if timestamp_str.endswith('Z'):
                timestamp = datetime.fromisoformat(timestamp_str[:-1] + '+00:00')
            elif '+' in timestamp_str or timestamp_str.endswith('00:00'):
                timestamp = datetime.fromisoformat(timestamp_str)
            else:
                timestamp = datetime.fromisoformat(timestamp_str).replace(tzinfo=timezone.utc)
        except:
            # Fallback to a safe old date
            timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
            
        logger.info(f"Last index update: {timestamp}")
        return timestamp
    
    def find_new_files_by_timestamp(self, since_timestamp: datetime) -> List[str]:
        """Find files modified/created since the given timestamp using AWS CLI"""
        logger.info(f"Finding files modified since {since_timestamp}")
        
        # Convert to epoch timestamp for AWS CLI
        since_epoch = int(since_timestamp.timestamp())
        
        try:
            # Use AWS CLI to find recently modified files
            # This is much faster than listing all files
            cmd = [
                'aws', 's3api', 'list-objects-v2',
                '--bucket', self.bucket_name,
                '--query', f'Contents[?LastModified >= `{since_timestamp.isoformat()}`].Key',
                '--output', 'json'
            ]
            
            logger.info("Running AWS CLI command to find new files...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                all_keys = json.loads(result.stdout) if result.stdout.strip() else []
                
                # Filter for GeoTIFF files
                geotiff_files = [
                    key for key in all_keys 
                    if key and key.lower().endswith(('.tif', '.tiff'))
                ]
                
                logger.info(f"Found {len(geotiff_files)} new GeoTIFF files since last update")
                return geotiff_files
                
            else:
                logger.warning(f"AWS CLI failed: {result.stderr}")
                return self.fallback_folder_detection()
                
        except Exception as e:
            logger.warning(f"AWS CLI approach failed: {e}")
            return self.fallback_folder_detection()
    
    def fallback_folder_detection(self) -> List[str]:
        """Fallback: Use folder-based detection for new files"""
        logger.info("Using fallback folder-based detection")
        
        # Get existing folders from the index
        existing_index = self.load_existing_index()
        processed_files = set()
        
        for zone_data in existing_index.get("utm_zones", {}).values():
            for file_info in zone_data.get("files", []):
                key = file_info.get("key", "")
                if key:
                    processed_files.add(key)
        
        existing_folders = set()
        for file_key in processed_files:
            if '/' in file_key:
                # Get top 2 levels of folder structure
                parts = file_key.split('/')
                if len(parts) >= 3:
                    folder = f"{parts[0]}/{parts[1]}"
                    existing_folders.add(folder)
        
        logger.info(f"Found {len(existing_folders)} existing folder patterns")
        
        # List current top-level folder structure
        s3 = boto3.client('s3')
        
        # Get all files (this is the slow part we're trying to avoid)
        logger.info("Getting current S3 file listing for folder analysis...")
        all_current_files = set()
        
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=self.bucket_name)
        
        for page in pages:
            for obj in page.get('Contents', []):
                key = obj['Key']
                if key.lower().endswith(('.tif', '.tiff')):
                    all_current_files.add(key)
        
        logger.info(f"Found {len(all_current_files)} total current files")
        
        # Find files in new folders or that weren't in the processed set
        new_files = list(all_current_files - processed_files)
        
        logger.info(f"Identified {len(new_files)} new files via folder analysis")
        return new_files
    
    def run_smart_incremental_update(self):
        """Main smart incremental update process"""
        start_time = time.time()
        
        # Step 1: Load existing index and get last update time
        existing_index = self.load_existing_index()
        last_update = self.get_last_update_timestamp(existing_index)
        
        # Step 2: Find new files using timestamp-based approach
        new_files = self.find_new_files_by_timestamp(last_update)
        
        if not new_files:
            logger.info("No new files found. Spatial index is up to date!")
            return
        
        # Step 3: Process new files
        logger.info(f"Processing {len(new_files):,} new files...")
        print(f"Expected processing time: {len(new_files) / 2.6 / 3600:.1f} hours")
        
        # Use parallel processing
        max_workers = 30
        new_results = self.extractor.extract_metadata_parallel(new_files, max_workers)
        
        # Step 4: Merge results into existing index
        logger.info(f"Merging {len(new_results):,} new results into spatial index")
        
        # Update metadata
        existing_index["index_timestamp"] = datetime.now(timezone.utc).isoformat()
        existing_index["file_count"] = existing_index.get("file_count", 0) + len(new_results)
        existing_index["last_incremental_update"] = datetime.now(timezone.utc).isoformat()
        existing_index["incremental_files_added"] = len(new_results)
        
        # Add new files to appropriate zones
        utm_zones = existing_index.setdefault("utm_zones", {})
        
        for result in new_results:
            zone_files = utm_zones.setdefault("geographic", {}).setdefault("files", [])
            zone_files.append(result)
        
        # Step 5: Save updated index
        output_file = self.config_dir / "precise_spatial_index.json"
        backup_file = self.config_dir / f"precise_spatial_index_backup_{int(time.time())}.json"
        
        # Backup existing index
        logger.info(f"Backing up existing index to {backup_file}")
        with open(output_file, 'r') as f:
            with open(backup_file, 'w') as b:
                b.write(f.read())
        
        # Save updated index
        logger.info(f"Saving updated spatial index to {output_file}")
        with open(output_file, 'w') as f:
            json.dump(existing_index, f, indent=2)
        
        # Step 6: Report summary
        elapsed = time.time() - start_time
        logger.info(f"\nSMART INCREMENTAL UPDATE COMPLETE")
        logger.info(f"Files processed: {len(new_files):,}")
        logger.info(f"Time elapsed: {elapsed/3600:.1f} hours")
        logger.info(f"Total files in index: {existing_index['file_count']:,}")
        
        # Save incremental report
        report_file = self.config_dir / f"smart_incremental_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(report_file, 'w') as f:
            f.write(f"# Smart Incremental Update Report\n\n")
            f.write(f"**Date:** {datetime.now().isoformat()}\n")
            f.write(f"**New Files Processed:** {len(new_files):,}\n")
            f.write(f"**Processing Time:** {elapsed/3600:.1f} hours\n")
            f.write(f"**Success Rate:** {len(new_results)/len(new_files)*100:.1f}%\n")
            f.write(f"**Total Files in Index:** {existing_index['file_count']:,}\n")
            f.write(f"**Last Update Timestamp:** {last_update}\n")

def main():
    logger.info("=== SMART INCREMENTAL METADATA EXTRACTOR ===")
    logger.info("Using timestamp-based detection for efficient updates")
    
    try:
        extractor = SmartIncrementalExtractor()
        extractor.run_smart_incremental_update()
    except Exception as e:
        logger.error(f"Smart incremental update failed: {e}")
        raise

if __name__ == "__main__":
    main()