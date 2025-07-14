import fiona
import logging
import sys

# Configure logging to see Fiona's output
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

gdb_path = "./data/source/DTM.gdb"

try:
    logger.info(f"Attempting to list layers in: {gdb_path}")
    # Fiona's listlayers can sometimes fail for raster datasets in FileGDBs
    # but it's worth a try for any type of layer.
    layers = fiona.listlayers(gdb_path)
    logger.info(f"Layers found in {gdb_path}: {layers}")
except Exception as e:
    logger.error(f"Failed to list layers in {gdb_path}: {e}")

print("\n--- Attempting to open the GeoDatabase with rasterio (GDAL) --- ")
import rasterio
from rasterio.errors import RasterioIOError

try:
    # Try opening with specific driver for FileGDB if needed, or let auto-detect
    # For FileGDB, GDAL might need the GDB_ARC_URL option or specific layer name.
    # Let's try without a layer name first, as it attempts auto-discovery for rasters
    with rasterio.open(gdb_path) as src:
        print(f"Successfully opened {gdb_path} with rasterio. Driver: {src.driver}, CRS: {src.crs}, Bounds: {src.bounds}")
        print(f"Band count: {src.count}")
        for i in range(1, src.count + 1):
            print(f"  Band {i} dtype: {src.dtypes[i-1]}")

except RasterioIOError as e:
    print(f"RasterioIOError: Could not open {gdb_path}: {e}")
except Exception as e:
    print(f"An unexpected error occurred with rasterio: {e}") 