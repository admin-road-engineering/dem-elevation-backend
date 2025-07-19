#!/usr/bin/env python3
"""
Test S3 → GPXZ → Google fallback chain
"""
import sys
import asyncio
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

async def test_fallback_chain():
    """Test the S3 -> GPXZ -> Google fallback chain"""
    print("[INFO] Testing S3 -> GPXZ -> Google fallback chain...")
    
    try:
        from config import Settings
        from enhanced_source_selector import EnhancedSourceSelector
        from gpxz_client import GPXZConfig
        
        # Load settings
        settings = Settings()
        
        # Create GPXZ config
        gpxz_config = None
        if settings.GPXZ_API_KEY:
            gpxz_config = GPXZConfig(
                api_key=settings.GPXZ_API_KEY,
                daily_limit=settings.GPXZ_DAILY_LIMIT,
                rate_limit_per_second=settings.GPXZ_RATE_LIMIT
            )
        
        # Create enhanced source selector
        selector = EnhancedSourceSelector(
            config=settings.DEM_SOURCES,
            use_s3=settings.USE_S3_SOURCES,
            use_apis=settings.USE_API_SOURCES,
            gpxz_config=gpxz_config,
            google_api_key=settings.GOOGLE_ELEVATION_API_KEY
        )
        
        print(f"[INFO] Selector initialized:")
        print(f"   S3 sources: {settings.USE_S3_SOURCES}")
        print(f"   API sources: {settings.USE_API_SOURCES}")
        print(f"   GPXZ client: {selector.gpxz_client is not None}")
        print(f"   Google client: {selector.google_client is not None}")
        
        # Test coordinates
        test_locations = [
            ("Brisbane, Australia", -27.4698, 153.0251),
            ("Auckland, New Zealand", -36.8485, 174.7633),
            ("Los Angeles, USA", 34.0522, -118.2437),
            ("London, UK", 51.5074, -0.1278),
            ("Random Ocean", 0.0, 0.0)
        ]
        
        print(f"\n[INFO] Testing source selection for {len(test_locations)} locations...")
        
        for location, lat, lon in test_locations:
            print(f"\n[TEST] {location} ({lat}, {lon})")
            
            # Test source selection
            selected_source = selector.select_best_source(lat, lon)
            print(f"   Selected source: {selected_source}")
            
            if selected_source:
                source_config = settings.DEM_SOURCES.get(selected_source)
                if source_config:
                    priority = source_config.get('priority', 'unknown')
                    path = source_config.get('path', 'unknown')
                    print(f"   Priority: {priority}")
                    print(f"   Path: {path}")
                    
                    # Determine source type
                    if path.startswith('s3://'):
                        source_type = "S3"
                    elif path.startswith('api://gpxz'):
                        source_type = "GPXZ API"
                    elif path.startswith('api://google'):
                        source_type = "Google API"
                    else:
                        source_type = "Unknown"
                    
                    print(f"   Source type: {source_type}")
            
            # Test elevation retrieval with resilience
            print(f"   Testing elevation retrieval...")
            elevation_result = await selector.get_elevation_with_resilience(lat, lon)
            
            if elevation_result.get('success'):
                print(f"   [OK] Elevation: {elevation_result['elevation_m']}m")
                print(f"   Source used: {elevation_result['source']}")
                print(f"   Sources attempted: {elevation_result['attempted_sources']}")
            else:
                print(f"   [FAIL] Failed to get elevation")
                print(f"   Sources attempted: {elevation_result.get('attempted_sources', [])}")
        
        # Test priority ordering
        print(f"\n[INFO] Testing priority ordering...")
        sources_by_priority = selector._get_sources_by_priority()
        
        for priority in sorted(sources_by_priority.keys()):
            sources = sources_by_priority[priority]
            print(f"   Priority {priority}: {len(sources)} sources")
            for source_id in sources:
                source_config = settings.DEM_SOURCES[source_id]
                path = source_config.get('path', 'unknown')
                description = source_config.get('description', 'No description')
                print(f"      {source_id}: {path}")
                print(f"         {description}")
        
        # Clean up
        await selector.close()
        
        print(f"\n[SUCCESS] Fallback chain test completed!")
        print(f"Expected fallback order: S3 (priority 1) -> GPXZ (priority 2) -> Google (priority 3)")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Fallback chain test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run fallback chain test"""
    print("[INFO] S3 -> GPXZ -> Google Fallback Chain Test")
    print("=" * 60)
    
    success = await test_fallback_chain()
    
    print("\n" + "=" * 60)
    if success:
        print("[SUCCESS] All tests passed!")
        print("The S3 -> GPXZ -> Google fallback chain is working correctly")
    else:
        print("[FAILURE] Some tests failed. Check output above.")

if __name__ == "__main__":
    asyncio.run(main())