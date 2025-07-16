#!/usr/bin/env python3
"""Test script to verify DEM Backend package dependencies."""

import sys
print("=== DEM Backend Package Verification ===")
print("Python version:", sys.version.split()[0])
print("Platform:", sys.platform)
print()

# Core packages for DEM Backend functionality
test_packages = [
    ("numpy", "Numerical computing"),
    ("rasterio", "Raster I/O (DEM files)"),
    ("fiona", "Vector I/O (geodatabase)"),
    ("pyproj", "Coordinate transformations"),
    ("shapely", "Geometric operations"),
    ("fastapi", "Web framework"),
    ("uvicorn", "ASGI server"),
    ("pydantic", "Data validation"),
    ("boto3", "AWS S3 access"),
    ("httpx", "HTTP client"),
    ("scipy", "Scientific computing"),
    ("matplotlib", "Plotting"),
    ("PyJWT", "JWT authentication")
]

passed = 0
failed = 0

for package_name, description in test_packages:
    try:
        module = __import__(package_name.replace("-", "_"))
        version = getattr(module, '__version__', 'unknown')
        print(f"OK   {package_name:12} {version:15} - {description}")
        passed += 1
    except Exception as e:
        print(f"FAIL {package_name:12} {str(e)[:50]:50} - {description}")
        failed += 1

print()
print(f"=== Results: {passed} passed, {failed} failed ===")

if failed == 0:
    print("SUCCESS: All packages imported successfully!")
    print("Ready to run: uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload")
else:
    print("ISSUES: Some packages failed to import.")
    if any(pkg in ["rasterio", "fiona"] for pkg, _ in test_packages):
        print("Geospatial packages failed - see SETUP_INSTRUCTIONS.md")

# Test basic geospatial functionality if packages loaded
if failed == 0:
    try:
        import rasterio
        import fiona
        print()
        print("=== Geospatial Package Test ===")
        print("Rasterio drivers:", len(rasterio.drivers.get_gdal_drivers()))
        print("Fiona drivers:", len(fiona.drivers.get_gdal_drivers()))
        print("GDAL functionality: OK")
    except:
        print("GDAL functionality: Limited")