#!/usr/bin/env python3
"""
Incremental Metadata Extractor
Processes only NEW files added to S3 since last spatial index build
"""
import json
import time
import logging
import boto3
from pathlib import Path
from typing import Dict, List, Set
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.direct_metadata_extractor import DirectMetadataExtractor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)8s | %(message)s'
)
logger = logging.getLogger(__name__)

class IncrementalMetadataExtractor:
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
    
    def get_processed_files(self, spatial_index: Dict) -> Set[str]:
        """Extract all file keys from existing spatial index, normalized for comparison"""
        processed_files = set()
        
        for zone_data in spatial_index.get("utm_zones", {}).values():
            for file_info in zone_data.get("files", []):
                key = file_info.get("key", "")
                if key:
                    # Normalize key format: remove s3://bucket-name/ prefix for comparison
                    if key.startswith(f"s3://{self.bucket_name}/"):
                        normalized_key = key.replace(f"s3://{self.bucket_name}/", "")
                        processed_files.add(normalized_key)
                    else:
                        processed_files.add(key)
        
        logger.info(f"Found {len(processed_files):,} files in existing index")
        return processed_files
    
    def list_current_s3_files(self) -> Set[str]:
        """List all current GeoTIFF files in S3 bucket"""
        logger.info(f"Listing all files in S3 bucket: {self.bucket_name}")
        
        s3 = boto3.client('s3')
        all_files = set()
        
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=self.bucket_name)
        
        for page in pages:
            for obj in page.get('Contents', []):
                key = obj['Key']
                if key.lower().endswith(('.tif', '.tiff')):
                    all_files.add(key)
        
        logger.info(f"Found {len(all_files):,} total GeoTIFF files in S3")
        return all_files
    
    def identify_new_files(self, current_files: Set[str], processed_files: Set[str]) -> List[str]:
        """Identify files that are new since last index build"""
        new_files = list(current_files - processed_files)
        logger.info(f"Identified {len(new_files):,} NEW files to process")
        return new_files
    
    def merge_results(self, existing_index: Dict, new_results: List[Dict]) -> Dict:
        """Merge new results into existing spatial index"""
        logger.info(f"Merging {len(new_results):,} new results into spatial index")
        
        # Update metadata
        existing_index["index_timestamp"] = datetime.now().isoformat()
        existing_index["file_count"] = existing_index.get("file_count", 0) + len(new_results)
        existing_index["last_incremental_update"] = datetime.now().isoformat()
        existing_index["incremental_files_added"] = len(new_results)
        
        # Add new files to appropriate zones
        utm_zones = existing_index.setdefault("utm_zones", {})
        
        for result in new_results:
            # All files go into 'geographic' zone as per current structure
            zone_files = utm_zones.setdefault("geographic", {}).setdefault("files", [])
            zone_files.append(result)
        
        logger.info(f"Updated index now contains {existing_index['file_count']:,} files")
        return existing_index
    
    def run_incremental_update(self):
        """Main incremental update process"""
        start_time = time.time()
        
        # Step 1: Load existing index
        existing_index = self.load_existing_index()
        processed_files = self.get_processed_files(existing_index)
        
        # Step 2: Get current S3 files
        current_files = self.list_current_s3_files()
        
        # Step 3: Identify new files
        new_files = self.identify_new_files(current_files, processed_files)
        
        if not new_files:
            logger.info("No new files found. Spatial index is up to date!")
            return
        
        # Step 4: Process new files with enhanced logging
        logger.info(f"Processing {len(new_files):,} new files...")
        print(f"\nExpected processing time: {len(new_files) / 2.6 / 3600:.1f} hours")
        
        # Use same parallel processing approach
        max_workers = 30
        new_results = self.extractor.extract_metadata_parallel(new_files, max_workers)
        
        # Step 5: Merge results
        updated_index = self.merge_results(existing_index, new_results)
        
        # Step 6: Save updated index
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
            json.dump(updated_index, f, indent=2)
        
        # Report summary
        elapsed = time.time() - start_time
        logger.info(f"\nINCREMENTAL UPDATE COMPLETE")
        logger.info(f"Files processed: {len(new_files):,}")
        logger.info(f"Time elapsed: {elapsed/3600:.1f} hours")
        logger.info(f"Total files in index: {updated_index['file_count']:,}")
        
        # Save incremental report
        report_file = self.config_dir / f"incremental_update_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(report_file, 'w') as f:
            f.write(f"# Incremental Update Report\n\n")
            f.write(f"**Date:** {datetime.now().isoformat()}\n")
            f.write(f"**New Files Processed:** {len(new_files):,}\n")
            f.write(f"**Processing Time:** {elapsed/3600:.1f} hours\n")
            f.write(f"**Success Rate:** {len(new_results)/len(new_files)*100:.1f}%\n")
            f.write(f"**Total Files in Index:** {updated_index['file_count']:,}\n")

def main():
    logger.info("=== INCREMENTAL METADATA EXTRACTOR ===")
    logger.info("Processing only NEW files added since last build")
    
    try:
        extractor = IncrementalMetadataExtractor()
        extractor.run_incremental_update()
    except Exception as e:
        logger.error(f"Incremental update failed: {e}")
        raise

if __name__ == "__main__":
    main()