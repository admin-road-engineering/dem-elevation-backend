import rasterio
import os
import logging
import traceback

# Configure logging to show all messages from rasterio and GDAL
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_gdb_access_verbose(gdb_path):
    logger.info(f"Attempting to open geodatabase with verbose logging: {gdb_path}")

    # Set GDAL environment variables for verbose logging
    os.environ['CPL_DEBUG'] = 'ON'
    os.environ['CPL_LOG_ERRORS'] = 'ON'
    os.environ['GDAL_DEBUG'] = 'ON'

    try:
        # Check if the path exists on the file system
        if not os.path.exists(gdb_path):
            logger.error(f"Error: Path does not exist: {gdb_path}")
            return False

        # Check read permissions directly
        if not os.access(gdb_path, os.R_OK):
            logger.error(f"Error: No read permission for: {gdb_path}")
            return False

        with rasterio.open(gdb_path) as src:
            logger.info(f"Successfully opened geodatabase: {gdb_path}")
            logger.info(f"Driver: {src.driver}")
            logger.info(f"CRS: {src.crs}")
            logger.info(f"Bounds: {src.bounds}")
            logger.info(f"Width: {src.width}, Height: {src.height}")
            logger.info(f"Number of bands: {src.count}")
            if src.count > 0:
                logger.info(f"Data type of band 1: {src.dtypes[0]}")
            
            # Try reading a small part of the data to ensure full access
            try:
                # Read a small window from the first band
                # Adjust window size if necessary based on your DTM.gdb dimensions
                data_sample = src.read(1, window=((0, min(src.height, 10)), (0, min(src.width, 10))))
                logger.info(f"Successfully read a sample of data. Sample shape: {data_sample.shape}")
                logger.debug(f"Sample data values (first 5): {data_sample.flatten()[:5]}")
            except Exception as e:
                logger.error(f"Failed to read data sample from {gdb_path}: {e}")
                traceback.print_exc()

        return True

    except rasterio.errors.RasterioIOError as e:
        logger.error(f"RasterioIOError while accessing {gdb_path}: {e}")
        traceback.print_exc()
    except Exception as e:
        logger.error(f"An unexpected error occurred while accessing {gdb_path}: {e}")
        traceback.print_exc()
    finally:
        # Unset GDAL debug environment variables
        del os.environ['CPL_DEBUG']
        del os.environ['CPL_LOG_ERRORS']
        del os.environ['GDAL_DEBUG']
    return False

if __name__ == "__main__":
    gdb_file_path = "./data/source/DTM.gdb"
    logger.info(f"Starting test for: {gdb_file_path}")
    if test_gdb_access_verbose(gdb_file_path):
        logger.info("Test completed successfully. Geodatabase is accessible.")
    else:
        logger.error("Test failed. Geodatabase is not accessible. Review the error messages above.") 