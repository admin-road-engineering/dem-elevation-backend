#!/usr/bin/env python3
"""
Script to inspect geodatabase contents using GDAL Python bindings directly
"""
import os
from osgeo import gdal, ogr

def inspect_geodatabase(gdb_path):
    """Inspect geodatabase using GDAL Python bindings"""
    print(f"Inspecting geodatabase: {gdb_path}")
    
    # Enable all GDAL error messages for debugging
    gdal.UseExceptions()
    
    try:
        # Try to open as vector dataset first
        print("\n--- Trying to open as vector dataset ---")
        vector_ds = ogr.Open(gdb_path)
        if vector_ds:
            print(f"Successfully opened as vector dataset")
            print(f"Number of layers: {vector_ds.GetLayerCount()}")
            
            for i in range(vector_ds.GetLayerCount()):
                layer = vector_ds.GetLayer(i)
                print(f"Layer {i}: {layer.GetName()} ({layer.GetFeatureCount()} features)")
                
                # Check if it's a raster layer
                geom_type = layer.GetGeomType()
                print(f"  Geometry type: {geom_type}")
        else:
            print("Could not open as vector dataset")
            
    except Exception as e:
        print(f"Vector access error: {e}")
    
    try:
        # Try to open as raster dataset
        print("\n--- Trying to open as raster dataset ---")
        raster_ds = gdal.Open(gdb_path)
        if raster_ds:
            print(f"Successfully opened as raster dataset")
            print(f"Size: {raster_ds.RasterXSize} x {raster_ds.RasterYSize}")
            print(f"Bands: {raster_ds.RasterCount}")
            print(f"Driver: {raster_ds.GetDriver().GetDescription()}")
        else:
            print("Could not open as raster dataset")
            
    except Exception as e:
        print(f"Raster access error: {e}")
    
    # Try to list subdatasets
    try:
        print("\n--- Checking for subdatasets ---")
        ds = gdal.Open(gdb_path)
        if ds:
            subdatasets = ds.GetMetadata('SUBDATASETS')
            if subdatasets:
                print("Found subdatasets:")
                for key, value in subdatasets.items():
                    print(f"  {key}: {value}")
            else:
                print("No subdatasets found")
    except Exception as e:
        print(f"Subdataset check error: {e}")

if __name__ == "__main__":
    gdb_path = "./data/source/DTM.gdb"
    inspect_geodatabase(gdb_path) 