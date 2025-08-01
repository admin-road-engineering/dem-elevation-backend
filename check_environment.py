#!/usr/bin/env python3
"""
Check environment detection
"""
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def check_environment():
    """Check what environment is being detected"""
    print("=== Environment Detection ===")
    
    app_env = os.getenv('APP_ENV', 'production')
    print(f"APP_ENV: {app_env}")
    
    # Check config
    try:
        from config import Settings
        settings = Settings()
        print(f"USE_S3_SOURCES: {settings.USE_S3_SOURCES}")
        print(f"Config environment effectively: {'production' if settings.USE_S3_SOURCES else 'development'}")
    except Exception as e:
        print(f"Config error: {e}")
    
    # Check UnifiedIndexLoader environment detection
    try:
        from unified_index_loader import UnifiedIndexLoader
        loader = UnifiedIndexLoader()
        print(f"UnifiedIndexLoader environment: {loader.environment}")
        print(f"UnifiedIndexLoader index_keys: {loader.index_keys}")
    except Exception as e:
        print(f"UnifiedIndexLoader error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_environment()