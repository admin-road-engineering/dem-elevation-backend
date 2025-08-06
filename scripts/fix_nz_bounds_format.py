#!/usr/bin/env python3
"""
Fix NZ spatial index bounds format to use canonical WGS84 keys.

This script ensures the NZ index conforms to the unified data-code contract
by using standard WGS84 bounds keys: min_lat, max_lat, min_lon, max_lon

Author: Claude (Recovery Phase)
Date: 2025-08-07
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def fix_bounds_format(bounds: Dict[str, Any]) -> Dict[str, float]:
    """
    Convert bounds to canonical WGS84 format.
    
    Handles multiple input formats:
    - Already correct: {min_lat, max_lat, min_lon, max_lon}
    - X/Y format: {min_x, max_x, min_y, max_y} where x=lon, y=lat
    - Rasterio format: {left, right, bottom, top}
    """
    # If already in correct format, return as-is
    if all(k in bounds for k in ['min_lat', 'max_lat', 'min_lon', 'max_lon']):
        return {
            'min_lat': float(bounds['min_lat']),
            'max_lat': float(bounds['max_lat']),
            'min_lon': float(bounds['min_lon']),
            'max_lon': float(bounds['max_lon'])
        }
    
    # Handle x/y format (common in GIS where x=lon, y=lat)
    if all(k in bounds for k in ['min_x', 'max_x', 'min_y', 'max_y']):
        return {
            'min_lat': float(bounds['min_y']),
            'max_lat': float(bounds['max_y']),
            'min_lon': float(bounds['min_x']),
            'max_lon': float(bounds['max_x'])
        }
    
    # Handle rasterio BoundingBox format (left, bottom, right, top)
    if all(k in bounds for k in ['left', 'right', 'bottom', 'top']):
        return {
            'min_lat': float(bounds['bottom']),
            'max_lat': float(bounds['top']),
            'min_lon': float(bounds['left']),
            'max_lon': float(bounds['right'])
        }
    
    # Unknown format - log warning and return empty bounds
    logger.warning(f"Unknown bounds format: {list(bounds.keys())}")
    return bounds

def fix_nz_spatial_index(input_path: str, output_path: str) -> None:
    """
    Fix the NZ spatial index to use canonical WGS84 bounds format.
    """
    logger.info(f"Loading NZ index from: {input_path}")
    
    with open(input_path, 'r') as f:
        index_data = json.load(f)
    
    # Track statistics
    total_collections = 0
    total_files = 0
    fixed_collections = 0
    fixed_files = 0
    
    # Process each collection
    collections = index_data.get('collections', [])
    for collection in collections:
        total_collections += 1
        
        # Fix collection bounds if present
        if 'bounds' in collection:
            old_bounds = collection['bounds']
            new_bounds = fix_bounds_format(old_bounds)
            if old_bounds != new_bounds:
                collection['bounds'] = new_bounds
                fixed_collections += 1
                logger.debug(f"Fixed collection bounds for: {collection.get('name', 'unknown')}")
        
        # Fix file bounds
        files = collection.get('files', [])
        for file_entry in files:
            total_files += 1
            
            if 'bounds' in file_entry:
                old_bounds = file_entry['bounds']
                new_bounds = fix_bounds_format(old_bounds)
                if old_bounds != new_bounds:
                    file_entry['bounds'] = new_bounds
                    fixed_files += 1
    
    # Add schema metadata to indicate fixed format
    if 'metadata' not in index_data:
        index_data['metadata'] = {}
    
    index_data['metadata']['schema_version'] = '1.1'
    index_data['metadata']['bounds_format'] = 'wgs84_canonical'
    index_data['metadata']['bounds_crs'] = 'EPSG:4326'
    index_data['metadata']['fixed_by'] = 'fix_nz_bounds_format.py'
    
    # Save fixed index
    logger.info(f"Writing fixed index to: {output_path}")
    with open(output_path, 'w') as f:
        json.dump(index_data, f, indent=2)
    
    # Report statistics
    logger.info(f"✅ Fixed NZ spatial index:")
    logger.info(f"   Total collections: {total_collections}")
    logger.info(f"   Fixed collections: {fixed_collections}")
    logger.info(f"   Total files: {total_files}")
    logger.info(f"   Fixed files: {fixed_files}")
    
    # Validate a sample file to confirm fix
    if collections and collections[0].get('files'):
        sample_file = collections[0]['files'][0]
        sample_bounds = sample_file.get('bounds', {})
        has_wgs84 = all(k in sample_bounds for k in ['min_lat', 'max_lat', 'min_lon', 'max_lon'])
        logger.info(f"   Sample file has WGS84 keys: {has_wgs84}")
        if has_wgs84:
            logger.info(f"   Sample bounds: lat [{sample_bounds['min_lat']:.4f}, {sample_bounds['max_lat']:.4f}], "
                       f"lon [{sample_bounds['min_lon']:.4f}, {sample_bounds['max_lon']:.4f}]")

def main():
    """Main entry point"""
    # Paths
    project_root = Path(__file__).parent.parent
    input_path = project_root / 'data' / 'indexes' / 'nz_spatial_index.json'
    output_path = project_root / 'data' / 'indexes' / 'nz_spatial_index_fixed.json'
    
    # Check if input exists
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        logger.info("Attempting to download from S3...")
        
        # Try to download from S3
        import boto3
        from botocore.exceptions import NoCredentialsError
        
        try:
            s3 = boto3.client('s3', region_name='ap-southeast-2')
            s3.download_file(
                'road-engineering-elevation-data',
                'indexes/nz_spatial_index.json',
                str(input_path)
            )
            logger.info("✅ Downloaded NZ index from S3")
        except NoCredentialsError:
            logger.error("AWS credentials not configured. Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to download from S3: {e}")
            sys.exit(1)
    
    # Fix the index
    fix_nz_spatial_index(str(input_path), str(output_path))
    
    logger.info(f"\n✅ Success! Fixed index saved to: {output_path}")
    logger.info("Next steps:")
    logger.info("1. Upload to S3: python scripts/upload_indexes_to_s3.py")
    logger.info("2. Test Auckland: curl https://re-dem-elevation-backend.up.railway.app/api/v1/elevation?lat=-36.8485&lon=174.7633")

if __name__ == "__main__":
    main()