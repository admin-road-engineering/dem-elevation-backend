#!/usr/bin/env python3
"""
Test script to diagnose DTM.gdb access issues
"""
import os
import sys
from pathlib import Path

def test_gdb_access():
    gdb_path = "./data/DTM.gdb"
    
    print(f"Testing access to: {gdb_path}")
    print(f"Absolute path: {os.path.abspath(gdb_path)}")
    print(f"Path exists: {os.path.exists(gdb_path)}")
    print(f"Is directory: {os.path.isdir(gdb_path)}")
    print(f"Is readable: {os.access(gdb_path, os.R_OK)}")
    print()
    
    # Test with fiona
    print("=== Testing with fiona ===")
    try:
        import fiona
        print(f"Fiona version: {fiona.__version__}")
        
        # Try to list layers
        print("Attempting to list layers...")
        layers = fiona.listlayers(gdb_path)
        print(f"Found {len(layers)} layers: {layers}")
        
        # Try to open each layer
        for layer in layers:
            try:
                with fiona.open(gdb_path, layer=layer) as src:
                    print(f"Layer '{layer}': {src.driver}, {len(src)} features, CRS: {src.crs}")
            except Exception as e:
                print(f"Error opening layer '{layer}': {e}")
                
    except ImportError:
        print("Fiona not available")
    except Exception as e:
        print(f"Fiona error: {e}")
    
    print()
    
    # Test with rasterio
    print("=== Testing with rasterio ===")
    try:
        import rasterio
        print(f"Rasterio version: {rasterio.__version__}")
        
        # Try to open as raster
        print("Attempting to open as raster dataset...")
        with rasterio.open(gdb_path) as src:
            print(f"Raster info: {src.width}x{src.height}, {src.count} bands, CRS: {src.crs}")
            
    except ImportError:
        print("Rasterio not available")
    except Exception as e:
        print(f"Rasterio error: {e}")
    
    print()
    
    # Test GDAL directly
    print("=== Testing with GDAL directly ===")
    try:
        from osgeo import gdal, ogr
        print(f"GDAL version: {gdal.__version__}")
        
        # Enable all drivers
        gdal.AllRegister()
        ogr.RegisterAll()
        
        # Test as vector dataset
        print("Testing as vector dataset...")
        vector_ds = ogr.Open(gdb_path)
        if vector_ds:
            print(f"Vector dataset opened successfully, {vector_ds.GetLayerCount()} layers")
            for i in range(vector_ds.GetLayerCount()):
                layer = vector_ds.GetLayerByIndex(i)
                print(f"  Layer {i}: {layer.GetName()}")
            vector_ds = None
        else:
            print("Failed to open as vector dataset")
        
        # Test as raster dataset
        print("Testing as raster dataset...")
        raster_ds = gdal.Open(gdb_path)
        if raster_ds:
            print(f"Raster dataset opened successfully: {raster_ds.RasterXSize}x{raster_ds.RasterYSize}")
            raster_ds = None
        else:
            print("Failed to open as raster dataset")
            
    except ImportError:
        print("GDAL not available")
    except Exception as e:
        print(f"GDAL error: {e}")

if __name__ == "__main__":
    test_gdb_access()