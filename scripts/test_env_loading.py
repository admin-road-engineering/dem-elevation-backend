#!/usr/bin/env python3
"""
Test environment variable loading from .env file
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

def test_env_loading():
    """Test if environment variables load correctly"""
    print("Testing Environment Variable Loading")
    print("=" * 40)
    
    # Load .env file
    env_file = Path(__file__).parent.parent / ".env"
    print(f"Loading from: {env_file}")
    
    result = load_dotenv(env_file)
    print(f"Load result: {result}")
    
    # Test AWS credentials
    aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    aws_bucket = os.getenv('AWS_S3_BUCKET_NAME')
    default_dem = os.getenv('DEFAULT_DEM_ID')
    
    print(f"\nAWS_ACCESS_KEY_ID: {'Found' if aws_access_key else 'Missing'}")
    print(f"AWS_SECRET_ACCESS_KEY: {'Found' if aws_secret_key else 'Missing'}")
    print(f"AWS_S3_BUCKET_NAME: {aws_bucket}")
    print(f"DEFAULT_DEM_ID: {default_dem}")
    
    # Test DEM_SOURCES
    dem_sources_raw = os.getenv('DEM_SOURCES')
    print(f"\nDEM_SOURCES raw: {'Found' if dem_sources_raw else 'Missing'}")
    
    if dem_sources_raw:
        print(f"Length: {len(dem_sources_raw)} characters")
        print(f"First 100 chars: {dem_sources_raw[:100]}...")
        
        try:
            dem_sources = json.loads(dem_sources_raw)
            print(f"JSON parsing: SUCCESS")
            print(f"Number of sources: {len(dem_sources)}")
            print("Sources found:")
            for source_id in dem_sources.keys():
                print(f"  - {source_id}")
        except json.JSONDecodeError as e:
            print(f"JSON parsing: FAILED - {str(e)}")
            
            # Try to fix common multiline issues
            fixed_sources = dem_sources_raw.replace('\n', '').replace('  ', '')
            print("Attempting to fix multiline JSON...")
            try:
                dem_sources = json.loads(fixed_sources)
                print("Fixed JSON parsing: SUCCESS")
                print(f"Number of sources: {len(dem_sources)}")
            except json.JSONDecodeError as e2:
                print(f"Fixed JSON parsing: STILL FAILED - {str(e2)}")
    
    return aws_access_key and aws_secret_key and dem_sources_raw

if __name__ == "__main__":
    success = test_env_loading()
    
    if success:
        print("\nSUCCESS: Environment variables loaded correctly")
    else:
        print("\nFAILED: Some environment variables are missing")
        print("Check your .env file formatting")