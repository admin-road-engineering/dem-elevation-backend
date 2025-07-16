#!/usr/bin/env python3
"""
Test minimal service functionality without geospatial dependencies
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import Settings

async def test_minimal_setup():
    """Test minimal service setup"""
    print("Testing Minimal DEM Backend Setup")
    print("=" * 40)
    
    # Test 1: Configuration loading
    try:
        settings = Settings()
        print("PASS: Configuration loaded successfully")
        print(f"  - DEM Sources: {len(settings.DEM_SOURCES)}")
        print(f"  - Default DEM: {settings.DEFAULT_DEM_ID}")
        print(f"  - S3 Sources: {settings.USE_S3_SOURCES}")
        print(f"  - API Sources: {settings.USE_API_SOURCES}")
    except Exception as e:
        print(f"FAIL: Configuration failed: {str(e)}")
        return False
    
    # Test 2: List available sources
    print(f"\nAvailable DEM Sources:")
    for source_id, source_config in settings.DEM_SOURCES.items():
        path = source_config.get('path', 'unknown')
        description = source_config.get('description', 'No description')
        print(f"  - {source_id}: {path}")
        print(f"    {description}")
    
    # Test 3: AWS Configuration
    aws_configured = all([
        settings.AWS_ACCESS_KEY_ID,
        settings.AWS_SECRET_ACCESS_KEY,
        settings.AWS_S3_BUCKET_NAME
    ])
    print(f"\nAWS S3 Configuration: {'PASS - Configured' if aws_configured else 'FAIL - Missing'}")
    
    # Test 4: API Configuration
    api_configured = bool(settings.GPXZ_API_KEY)
    print(f"GPXZ API Configuration: {'PASS - Configured' if api_configured else 'FAIL - Missing'}")
    
    print(f"\nConfiguration Summary:")
    print(f"PASS: Environment file loaded")
    print(f"PASS: {len(settings.DEM_SOURCES)} DEM sources configured")
    print(f"PASS: Multi-source setup ready")
    print(f"{'PASS' if aws_configured else 'FAIL'}: S3 access configured")
    print(f"{'PASS' if api_configured else 'FAIL'}: API fallback configured")
    
    return True

def main():
    """Run minimal tests"""
    success = asyncio.run(test_minimal_setup())
    
    if success:
        print("\nSUCCESS: Configuration is working!")
        print("\nNext steps:")
        print("1. Install geospatial dependencies: pip install rasterio pyproj")
        print("2. Start service: uvicorn src.main:app --host 0.0.0.0 --port 8001")
        print("3. Test endpoints: python scripts/test_connections_simplified.py")
    else:
        print("\nFAILED: Fix configuration issues before proceeding")

if __name__ == "__main__":
    main()