import logging
import os
import fiona
import rasterio
from rasterio.env import Env

# Configure logging to see detailed output
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

gdb_path = ".\\data\\source\\DTM.gdb"

logger.info(f"Checking geodatabase: {gdb_path}")

# Configure GDAL environment for error suppression during tests
gdal_env = {
    'CPL_LOG_ERRORS': 'OFF',
    'CPL_DEBUG': 'OFF',
    'GDAL_DISABLE_READDIR_ON_OPEN': 'EMPTY_DIR'
}

def check_fiona_layers(path):
    logger.info("\n--- Attempting to list layers with fiona ---")
    try:
        layers = fiona.listlayers(path)
        if layers:
            logger.info(f"✅ Found {len(layers)} layers using fiona: {layers}")
            for layer in layers:
                try:
                    full_layer_path = f"{path}/{layer}"
                    with Env(**gdal_env):
                        with rasterio.open(full_layer_path) as dataset:
                            logger.info(f"  ✅ Successfully opened layer '{layer}' as raster. Driver: {dataset.driver}")
                            return True
                except Exception as e:
                    logger.info(f"  ❌ Failed to open layer '{layer}' as raster: {e}")
        else:
            logger.warning("⚠️ No layers found using fiona.")
    except Exception as e:
        logger.error(f"❌ Fiona failed to list layers: {e}")
    return False

def check_rasterio_common_names(path):
    logger.info("\n--- Attempting common raster layer names with rasterio ---")
    common_names = [
        'dtm', 'DTM', 'elevation', 'dem', 'DEM', 'height', 'raster',
        'mosaic', 'Mosaic_Dataset', 'terrain', 'surface', 'elev'
    ]
    for name in common_names:
        test_path = f"{path}/{name}"
        try:
            with Env(**gdal_env):
                with rasterio.open(test_path) as dataset:
                    logger.info(f"✅ Found raster layer using common name '{name}'. Driver: {dataset.driver}")
                    return True
        except Exception as e:
            logger.info(f"  ❌ Failed to open '{test_path}': {e}")
    return False

def check_rasterio_access_patterns(path):
    logger.info("\n--- Attempting common rasterio access patterns ---")
    access_patterns = [
        path,
        f"{path}/Band_1",
        f"{path}/Raster",
        f"{path}/Layer_1",
    ]
    for pattern in access_patterns:
        try:
            with Env(**gdal_env):
                with rasterio.open(pattern) as dataset:
                    if dataset.count > 0:
                        logger.info(f"✅ Found raster using pattern '{pattern}'. Driver: {dataset.driver}")
                        return True
        except Exception as e:
            logger.info(f"  ❌ Failed to open '{pattern}': {e}")
    return False

if __name__ == "__main__":
    if not os.path.exists(gdb_path):
        logger.error(f"Geodatabase path does not exist: {gdb_path}")
    elif not os.path.isdir(gdb_path):
        logger.error(f"Geodatabase path is not a directory: {gdb_path}")
    else:
        logger.info("Geodatabase path exists and is a directory.")
        
        if check_fiona_layers(gdb_path):
            logger.info("Fiona successfully identified and opened a raster layer.")
        elif check_rasterio_common_names(gdb_path):
            logger.info("Rasterio successfully opened a raster layer using common name.")
        elif check_rasterio_access_patterns(gdb_path):
            logger.info("Rasterio successfully opened a raster layer using an access pattern.")
        else:
            logger.error("❌ Could not find or open any raster layers in the geodatabase.") 