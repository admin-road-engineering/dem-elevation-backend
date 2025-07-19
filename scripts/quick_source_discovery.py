#!/usr/bin/env python3
"""
Quick S3 Source Discovery
Rapidly identifies missing Queensland and Victoria sources
"""
import boto3
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config import Settings

def main():
    settings = Settings()
    s3 = boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_DEFAULT_REGION
    )
    
    print("QUICK SOURCE DISCOVERY")
    print("=" * 30)
    
    # Key findings from our analysis
    missing_sources = {
        # Queensland sources (for Brisbane)
        "csiro_qld_z56": {
            "path": "s3://road-engineering-elevation-data/csiro-elvis/elevation/1m-dem/z56/",
            "layer": None,
            "crs": "EPSG:32756", 
            "description": "Queensland/NSW 1m LiDAR (CSIRO) - Clarence & Richmond Rivers"
        },
        "dawe_qld_z56_burnett": {
            "path": "s3://road-engineering-elevation-data/dawe-elvis/elevation/50cm-dem/z56/",
            "layer": None,
            "crs": "EPSG:32756",
            "description": "Queensland 50cm LiDAR (DAWE) - Burnett, Fitzroy, Mary Rivers"
        },
        
        # Victoria sources (for Bendigo and Melbourne area)
        "ga_vic_z55": {
            "path": "s3://road-engineering-elevation-data/ga-elvis/elevation/1m-dem/ausgeoid/z55/",
            "layer": None,
            "crs": "EPSG:32755",
            "description": "Victoria 1m LiDAR (GA) - Including Bendigo, Melbourne regions"
        },
        "griffith_qld_z55": {
            "path": "s3://road-engineering-elevation-data/griffith-elvis/elevation/50cm-dem/z55/",
            "layer": None,
            "crs": "EPSG:32755",
            "description": "Queensland/Victoria 50cm LiDAR (Griffith) - Multiple regional areas"
        },
        
        # National coverage for gaps
        "ga_national_ausgeoid": {
            "path": "s3://road-engineering-elevation-data/ga-elvis/elevation/1m-dem/ausgeoid/",
            "layer": None,
            "crs": "EPSG:3577",
            "description": "Australia National 1m DEM (GA) - Multi-state coverage"
        }
    }
    
    # Validate these sources exist
    print("VALIDATING DISCOVERED SOURCES:")
    print("-" * 40)
    
    valid_sources = {}
    
    for source_id, source_config in missing_sources.items():
        s3_path = source_config['path'].replace('s3://road-engineering-elevation-data/', '')
        
        try:
            response = s3.list_objects_v2(
                Bucket=settings.AWS_S3_BUCKET_NAME,
                Prefix=s3_path,
                MaxKeys=5
            )
            
            file_count = len([obj for obj in response.get('Contents', []) if obj['Key'].endswith('.tif')])
            
            if file_count > 0 or 'CommonPrefixes' in response:
                print(f"[OK] {source_id}: {file_count} files found")
                valid_sources[source_id] = source_config
            else:
                print(f"[FAIL] {source_id}: No files found")
                
        except Exception as e:
            print(f"[ERROR] {source_id}: Error - {e}")
    
    print(f"\nVALID SOURCES TO ADD: {len(valid_sources)}")
    
    # Check current config issues
    print("\nCURRENT CONFIG VALIDATION:")
    print("-" * 30)
    
    current_sources = settings.DEM_SOURCES
    
    # Check configured sources that don't exist
    invalid_current = []
    for source_id, source_config in current_sources.items():
        if 'road-engineering-elevation-data' in source_config.get('path', ''):
            s3_path = source_config['path'].replace('s3://road-engineering-elevation-data/', '')
            try:
                response = s3.list_objects_v2(
                    Bucket=settings.AWS_S3_BUCKET_NAME,
                    Prefix=s3_path,
                    MaxKeys=1
                )
                if not ('Contents' in response or 'CommonPrefixes' in response):
                    invalid_current.append(source_id)
                    print(f"[FAIL] {source_id}: Configured but not found in S3")
                else:
                    print(f"[OK] {source_id}: Valid")
            except:
                invalid_current.append(source_id)
                print(f"[ERROR] {source_id}: Error checking")
    
    # Generate recommendations
    print("\nRECOMMENDATIONS:")
    print("=" * 20)
    
    print("1. ADD MISSING SOURCES:")
    for source_id in valid_sources:
        print(f"   + {source_id}")
    
    if invalid_current:
        print("2. REMOVE INVALID SOURCES:")
        for source_id in invalid_current:
            print(f"   - {source_id}")
    
    print("3. PRIORITY TESTING:")
    print("   - Test Brisbane coordinates with Queensland sources")
    print("   - Test Bendigo coordinates with Victoria sources")
    print("   - Verify source selection chooses S3 over GPXZ")
    
    # Save corrected config
    output_dir = Path(__file__).parent.parent / "config"
    output_dir.mkdir(exist_ok=True)
    
    # Merge current valid + new valid
    corrected_config = {k: v for k, v in current_sources.items() if k not in invalid_current}
    corrected_config.update(valid_sources)
    
    with open(output_dir / "corrected_dem_sources.json", 'w') as f:
        json.dump(corrected_config, f, indent=2)
    
    print(f"\n4. CORRECTED CONFIG SAVED:")
    print(f"   {output_dir / 'corrected_dem_sources.json'}")
    
    print("\n5. ROOT CAUSES IDENTIFIED:")
    print("   - Manual configuration without S3 validation")
    print("   - Assumed state-based folder structure (nsw-elvis, vic-elvis)")
    print("   - No automated discovery of available data")
    print("   - No geographic coverage testing")

if __name__ == "__main__":
    main()