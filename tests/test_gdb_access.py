#!/usr/bin/env python3
"""
Simple test script to diagnose geodatabase access issues
"""
import os
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_file_access():
    """Test basic file system access to the geodatabase"""
    gdb_path = "./data/source/DTM.gdb"
    abs_path = os.path.abspath(gdb_path)
    
    print(f"Testing file access to: {abs_path}")
    print(f"Path exists: {os.path.exists(abs_path)}")
    print(f"Is directory: {os.path.isdir(abs_path)}")
    
    if os.path.exists(abs_path):
        try:
            files = os.listdir(abs_path)
            print(f"Number of files in geodatabase: {len(files)}")
            print(f"First few files: {files[:5]}")
        except Exception as e:
            print(f"Error listing files: {e}")

def test_fiona_access():
    """Test Fiona access to the geodatabase"""
    print("\n--- Testing Fiona Access ---")
    try:
        import fiona
        gdb_path = "./data/source/DTM.gdb"
        print(f"Fiona version: {fiona.__version__}")
        
        # Try to list layers
        layers = fiona.listlayers(gdb_path)
        print(f"Found {len(layers)} layers: {layers}")
        
    except ImportError:
        print("Fiona not available")
    except Exception as e:
        print(f"Fiona error: {e}")

def test_rasterio_access():
    """Test Rasterio access to the geodatabase"""
    print("\n--- Testing Rasterio Access ---")
    try:
        import rasterio
        gdb_path = "./data/source/DTM.gdb"
        print(f"Rasterio version: {rasterio.__version__}")
        
        # Try to open the geodatabase directly
        try:
            with rasterio.open(gdb_path) as src:
                print(f"Opened geodatabase directly: {src.count} bands")
        except Exception as e:
            print(f"Cannot open geodatabase directly: {e}")
            
        # Try with common layer names
        common_names = ['dtm', 'DTM', 'elevation', 'dem', 'DEM']
        for name in common_names:
            try:
                layer_path = f"{gdb_path}/{name}"
                with rasterio.open(layer_path) as src:
                    print(f"Successfully opened layer '{name}': {src.count} bands, {src.width}x{src.height}")
                    break
            except Exception as e:
                print(f"Cannot open layer '{name}': {e}")
                
    except ImportError:
        print("Rasterio not available")
    except Exception as e:
        print(f"Rasterio error: {e}")

def test_gdal_info():
    """Test GDAL environment and drivers"""
    print("\n--- Testing GDAL Environment ---")
    try:
        from osgeo import gdal
        print(f"GDAL version: {gdal.VersionInfo()}")
        
        # List available drivers
        driver_count = gdal.GetDriverCount()
        print(f"Available drivers: {driver_count}")
        
        # Check for geodatabase drivers
        gdb_drivers = []
        for i in range(driver_count):
            driver = gdal.GetDriver(i)
            if 'gdb' in driver.GetDescription().lower() or 'geodatabase' in driver.GetDescription().lower():
                gdb_drivers.append(driver.GetDescription())
        
        print(f"Geodatabase drivers: {gdb_drivers}")
        
    except ImportError:
        print("GDAL not available")
    except Exception as e:
        print(f"GDAL error: {e}")

if __name__ == "__main__":
    print("=== Geodatabase Access Diagnostic ===")
    test_file_access()
    test_fiona_access()
    test_rasterio_access()
    test_gdal_info()
    print("\n=== Diagnostic Complete ===") 