#!/usr/bin/env python3
"""
Check GDAL drivers and try different approaches to access the geodatabase
"""
import os

def check_gdal_drivers():
    try:
        from osgeo import gdal, ogr
        print(f"GDAL version: {gdal.__version__}")
        
        # Enable all drivers
        gdal.AllRegister()
        ogr.RegisterAll()
        
        print("\n=== Available GDAL drivers ===")
        driver_count = gdal.GetDriverCount()
        gdb_drivers = []
        
        for i in range(driver_count):
            driver = gdal.GetDriver(i)
            if 'gdb' in driver.GetDescription().lower() or 'geodatabase' in driver.GetDescription().lower():
                gdb_drivers.append(driver.GetDescription())
                print(f"Geodatabase driver found: {driver.GetDescription()}")
        
        print(f"\nTotal drivers: {driver_count}")
        print(f"Geodatabase drivers: {len(gdb_drivers)}")
        
        print("\n=== Testing different access methods ===")
        gdb_path = "./data/DTM.gdb"
        
        # Try different driver approaches
        drivers_to_try = ['OpenFileGDB', 'FileGDB', 'ESRI Shapefile']
        
        for driver_name in drivers_to_try:
            print(f"\nTrying driver: {driver_name}")
            try:
                # Try as vector
                vector_driver = ogr.GetDriverByName(driver_name)
                if vector_driver:
                    ds = vector_driver.Open(gdb_path, 0)  # 0 = read-only
                    if ds:
                        print(f"  Vector success with {driver_name}: {ds.GetLayerCount()} layers")
                        for i in range(ds.GetLayerCount()):
                            layer = ds.GetLayerByIndex(i)
                            print(f"    Layer {i}: {layer.GetName()} ({layer.GetFeatureCount()} features)")
                        ds = None
                    else:
                        print(f"  Vector failed with {driver_name}")
                else:
                    print(f"  Driver {driver_name} not available")
                    
                # Try as raster
                raster_driver = gdal.GetDriverByName(driver_name)
                if raster_driver:
                    ds = gdal.Open(gdb_path, gdal.GA_ReadOnly)
                    if ds:
                        print(f"  Raster success with {driver_name}: {ds.RasterXSize}x{ds.RasterYSize}")
                        ds = None
                    else:
                        print(f"  Raster failed with {driver_name}")
                        
            except Exception as e:
                print(f"  Error with {driver_name}: {e}")
                
        # Try to inspect the gdb file structure
        print(f"\n=== Inspecting GDB structure ===")
        print(f"GDB path: {os.path.abspath(gdb_path)}")
        
        # Check if there are any .tif files we can use instead
        data_dir = "./data"
        print(f"\n=== Alternative files in {data_dir} ===")
        for root, dirs, files in os.walk(data_dir):
            for file in files:
                if file.endswith(('.tif', '.tiff')):
                    full_path = os.path.join(root, file)
                    print(f"Found GeoTIFF: {full_path}")
                    
                    # Test if we can open this file
                    try:
                        ds = gdal.Open(full_path)
                        if ds:
                            print(f"  ✓ Can open: {ds.RasterXSize}x{ds.RasterYSize}, {ds.RasterCount} bands")
                            ds = None
                        else:
                            print(f"  ✗ Cannot open")
                    except Exception as e:
                        print(f"  ✗ Error: {e}")
                        
    except ImportError:
        print("GDAL not available")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_gdal_drivers()