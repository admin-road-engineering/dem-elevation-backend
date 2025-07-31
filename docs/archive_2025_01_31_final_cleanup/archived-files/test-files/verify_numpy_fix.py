#!/usr/bin/env python3
"""
Comprehensive verification script for NumPy ABI fix.
Tests all critical imports and DEM Backend functionality.
"""
import sys
import os
from typing import List, Tuple

def test_numpy_abi():
    """Test NumPy import and ABI compatibility."""
    print("=== NumPy ABI Test ===")
    try:
        import numpy as np
        print(f"✓ NumPy import: {np.__version__}")
        
        # Test that numpy.core.multiarray is accessible
        from numpy.core import multiarray
        print("✓ NumPy core.multiarray: OK")
        
        # Test basic array operations
        arr = np.array([1, 2, 3])
        result = np.sum(arr)
        print(f"✓ NumPy operations: sum([1,2,3]) = {result}")
        return True
    except Exception as e:
        print(f"❌ NumPy ABI Error: {e}")
        return False

def test_geospatial_imports():
    """Test geospatial package imports."""
    print("\n=== Geospatial Package Test ===")
    packages = [
        ("rasterio", "Raster I/O"),
        ("fiona", "Vector I/O"), 
        ("pyproj", "Projections"),
        ("shapely", "Geometry")
    ]
    
    results = []
    for package, description in packages:
        try:
            module = __import__(package)
            version = getattr(module, '__version__', 'unknown')
            print(f"✓ {package}: {version} - {description}")
            results.append(True)
        except Exception as e:
            print(f"❌ {package}: {str(e)[:50]} - {description}")
            results.append(False)
    
    return all(results)

def test_dem_backend_imports():
    """Test DEM Backend specific imports."""
    print("\n=== DEM Backend Import Test ===")
    try:
        # Test configuration
        from src.config import Settings, get_settings
        settings = get_settings()
        print(f"✓ Config: {len(settings.DEM_SOURCES)} sources configured")
        
        # Test DEM service (this will fail if rasterio/fiona broken)
        from src.dem_service import DEMService
        print("✓ DEM Service: Import successful")
        
        # Test API endpoints
        from src.api.v1.endpoints import router
        print("✓ API Endpoints: Import successful")
        
        return True
    except Exception as e:
        print(f"❌ DEM Backend: {e}")
        return False

def test_server_startup():
    """Test if FastAPI server can start."""
    print("\n=== Server Startup Test ===")
    try:
        from fastapi import FastAPI
        from src.main import app
        print("✓ FastAPI app: Created successfully")
        
        # Test if we can import uvicorn
        import uvicorn
        print(f"✓ Uvicorn: {uvicorn.__version__}")
        
        return True
    except Exception as e:
        print(f"❌ Server Startup: {e}")
        return False

def test_data_files():
    """Check if data files are available."""
    print("\n=== Data Files Test ===")
    data_files = [
        "./data/DTM.gdb",
        "./data/DTM.tif"
    ]
    
    found_files = []
    for file_path in data_files:
        if os.path.exists(file_path):
            size_mb = os.path.getsize(file_path) / (1024 * 1024)
            print(f"✓ {file_path}: {size_mb:.1f} MB")
            found_files.append(file_path)
        else:
            print(f"⚠ {file_path}: Not found")
    
    print(f"Found {len(found_files)}/{len(data_files)} data files")
    return len(found_files) > 0

def run_comprehensive_test():
    """Run all tests and provide summary."""
    print("🧪 DEM Backend NumPy ABI Fix Verification")
    print("=" * 50)
    
    # Environment info
    print(f"Python: {sys.version.split()[0]}")
    print(f"Platform: {sys.platform}")
    print(f"Working Directory: {os.getcwd()}")
    print()
    
    # Run tests
    tests = [
        ("NumPy ABI", test_numpy_abi),
        ("Geospatial Packages", test_geospatial_imports),
        ("DEM Backend", test_dem_backend_imports),
        ("Server Startup", test_server_startup),
        ("Data Files", test_data_files)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name}: Exception - {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Results Summary")
    print("=" * 50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "❌ FAIL"
        print(f"{status:<8} {test_name}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 SUCCESS: All tests passed!")
        print("NumPy ABI error is fixed. Ready to run:")
        print("  conda activate dem-backend-fixed")
        print("  uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload")
    else:
        print(f"\n⚠ ISSUES: {total - passed} tests failed")
        print("Check error messages above and run fix_numpy_error.bat")
    
    return passed == total

if __name__ == "__main__":
    success = run_comprehensive_test()
    sys.exit(0 if success else 1)