#!/usr/bin/env python3
"""
Convert geodatabase to GeoTIFF using GDAL Python bindings directly
"""
import os
import sys
from osgeo import gdal
import argparse

def convert_gdb_to_tif_direct(gdb_path, tif_path):
    """
    Convert geodatabase to GeoTIFF using GDAL Python bindings directly
    """
    print(f"Converting {gdb_path} to {tif_path}")
    
    # Enable GDAL exceptions for better error handling
    gdal.UseExceptions()
    
    try:
        # Open the source geodatabase
        print("Opening source geodatabase...")
        src_ds = gdal.Open(gdb_path, gdal.GA_ReadOnly)
        if not src_ds:
            raise Exception(f"Could not open source geodatabase: {gdb_path}")
        
        print(f"Source info:")
        print(f"  Size: {src_ds.RasterXSize} x {src_ds.RasterYSize}")
        print(f"  Bands: {src_ds.RasterCount}")
        print(f"  Driver: {src_ds.GetDriver().GetDescription()}")
        
        # Get geotransform and projection
        geotransform = src_ds.GetGeoTransform()
        projection = src_ds.GetProjection()
        
        print(f"  Geotransform: {geotransform}")
        print(f"  Projection: {projection[:100]}..." if len(projection) > 100 else f"  Projection: {projection}")
        
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(tif_path), exist_ok=True)
        
        # Create the output GeoTIFF
        print("Creating output GeoTIFF...")
        driver = gdal.GetDriverByName('GTiff')
        
        # Create with compression and tiling for efficiency
        creation_options = [
            'COMPRESS=LZW',
            'TILED=YES',
            'BLOCKXSIZE=512',
            'BLOCKYSIZE=512'
        ]
        
        dst_ds = driver.Create(
            tif_path,
            src_ds.RasterXSize,
            src_ds.RasterYSize,
            src_ds.RasterCount,
            src_ds.GetRasterBand(1).DataType,
            creation_options
        )
        
        if not dst_ds:
            raise Exception(f"Could not create output file: {tif_path}")
        
        # Set geotransform and projection
        dst_ds.SetGeoTransform(geotransform)
        dst_ds.SetProjection(projection)
        
        # Copy data band by band
        for band_num in range(1, src_ds.RasterCount + 1):
            print(f"Copying band {band_num}...")
            src_band = src_ds.GetRasterBand(band_num)
            dst_band = dst_ds.GetRasterBand(band_num)
            
            # Copy band data
            data = src_band.ReadAsArray()
            dst_band.WriteArray(data)
            
            # Copy band metadata
            dst_band.SetNoDataValue(src_band.GetNoDataValue())
            dst_band.SetDescription(src_band.GetDescription())
        
        # Flush and close
        dst_ds.FlushCache()
        dst_ds = None
        src_ds = None
        
        print(f"Successfully converted to: {tif_path}")
        
        # Verify the output file
        verify_ds = gdal.Open(tif_path, gdal.GA_ReadOnly)
        if verify_ds:
            print(f"Verification successful:")
            print(f"  Output size: {verify_ds.RasterXSize} x {verify_ds.RasterYSize}")
            print(f"  Output bands: {verify_ds.RasterCount}")
            verify_ds = None
        else:
            print("Warning: Could not verify output file")
            
    except Exception as e:
        print(f"Error during conversion: {e}")
        return False
    
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Convert geodatabase to GeoTIFF using GDAL directly')
    parser.add_argument('--gdb-path', default='./data/source/DTM.gdb', help='Path to input geodatabase')
    parser.add_argument('--tif-path', default='./data/dems/dtm.tif', help='Path to output GeoTIFF')
    
    args = parser.parse_args()
    
    success = convert_gdb_to_tif_direct(args.gdb_path, args.tif_path)
    sys.exit(0 if success else 1) 