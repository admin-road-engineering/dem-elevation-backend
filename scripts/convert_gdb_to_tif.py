import argparse
import logging
import os
import rasterio
from rasterio.windows import Window
import fiona

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def find_raster_layer(gdb_path: str) -> str:
    """Find the most likely raster layer in a geodatabase."""
    try:
        layer_names = fiona.listlayers(gdb_path)
    except Exception as e:
        logging.error(f"Could not list layers in geodatabase '{gdb_path}': {e}")
        raise
    
    for layer_name in layer_names:
        try:
            with rasterio.open(f"{gdb_path}/{layer_name}") as src:
                if src.count > 0: # Check if it has bands
                    logging.info(f"Found raster layer: {layer_name}")
                    return layer_name
        except rasterio.errors.RasterioIOError:
            continue # Skip non-raster layers
    
    raise ValueError(f"No raster layers found in {gdb_path}")

def convert_gdb_to_tif(gdb_path: str, tif_path: str, layer_name: str = None):
    """
    Converts a raster layer from a File Geodatabase (.gdb) to a GeoTIFF (.tif).
    """
    gdb_abs_path = os.path.abspath(gdb_path)
    tif_abs_path = os.path.abspath(tif_path)

    if not os.path.exists(gdb_abs_path):
        logging.error(f"Geodatabase not found at: {gdb_abs_path}")
        return

    if not layer_name:
        logging.info("Layer name not specified, attempting to auto-discover.")
        layer_name = find_raster_layer(gdb_abs_path)

    raster_path = f"{gdb_abs_path}/{layer_name}"
    logging.info(f"Opening raster layer: {raster_path}")

    try:
        with rasterio.open(raster_path) as src:
            profile = src.profile
            profile.update(
                driver='GTiff',
                compress='lzw',
                predictor=2, # Horizontal differencing for floating point data
                tiled=True,
                blockxsize=256,
                blockysize=256
            )

            logging.info(f"Converting {layer_name} to {tif_abs_path}...")
            os.makedirs(os.path.dirname(tif_abs_path), exist_ok=True)
            
            with rasterio.open(tif_abs_path, 'w', **profile) as dst:
                # Process in blocks for memory efficiency
                for ji, window in src.block_windows(1):
                    data = src.read(window=window)
                    dst.write(data, window=window)
            
            logging.info("Conversion successful!")
    
    except Exception as e:
        logging.error(f"An error occurred during conversion: {e}")
        raise

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Convert a GDB raster layer to a GeoTIFF.")
    parser.add_argument(
        "--gdb_path",
        default="./data/source/DTM.gdb",
        help="Path to the input File Geodatabase (.gdb)."
    )
    parser.add_argument(
        "--tif_path",
        default="./data/dems/dtm.tif",
        help="Path for the output GeoTIFF (.tif) file."
    )
    parser.add_argument(
        "--layer_name",
        default=None,
        help="Name of the raster layer within the GDB (optional, will be auto-discovered)."
    )
    
    args = parser.parse_args()
    
    convert_gdb_to_tif(args.gdb_path, args.tif_path, args.layer_name) 