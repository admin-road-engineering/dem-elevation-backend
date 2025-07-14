import rasterio
from rasterio.env import Env
from pyproj import Transformer, Geod
import os
import logging
import pytest

# Configure logging to see what's happening
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from config.py or .env (simplified for test)
LOCAL_DEM_PATH = "./data/source/DTM.gdb"
LOCAL_DEM_LAYER = "dtm"

def test_raw_rasterio_precision():
    print("=" * 80)
    print("TESTING RAW RASTERIO PRECISION - Direct Dataset Access")
    print("=" * 80)
    
    # S3 DEM path (same as in your config)
    dem_path = "s3://roadengineer-dem-files/DTM.gdb/DTM"
    
    # Configure GDAL environment for S3 access
    gdal_env = {
        'CPL_LOG_ERRORS': 'OFF',
        'CPL_DEBUG': 'OFF',
        'GDAL_DISABLE_READDIR_ON_OPEN': 'EMPTY_DIR'
    }
    
    # Gold Coast test coordinates
    test_coords = [
        (-28.0020000, 153.4140000),
        (-28.0020001, 153.4140001),
        (-28.0020002, 153.4140002),
        (-28.0020003, 153.4140003),
        (-28.0020004, 153.4140004),
        (-28.0020005, 153.4140005),
    ]
    
    try:
        with Env(**gdal_env):
            with rasterio.open(dem_path) as dataset:
                print(f"Dataset CRS: {dataset.crs}")
                print(f"Dataset bounds: {dataset.bounds}")
                print(f"Dataset nodata: {dataset.nodata}")
                print(f"Dataset dtype: {dataset.dtypes[0]}")
                print()
                
                # Create transformer
                transformer = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True)
                
                print("RAW RASTERIO ELEVATION VALUES:")
                print("-" * 80)
                print("Lat        | Lng        | X         | Y         | Raw Sample Value")
                print("-" * 80)
                
                for lat, lng in test_coords:
                    # Transform coordinates
                    x, y = transformer.transform(lng, lat)
                    
                    # Sample directly from rasterio
                    elevation_values = list(dataset.sample([(x, y)]))
                    raw_value = elevation_values[0][0]
                    
                    print(f"{lat:.7f} | {lng:.7f} | {x:.1f} | {y:.1f} | {raw_value}")
                    
                    # Show the exact type and representation
                    print(f"  Raw value type: {type(raw_value)}")
                    print(f"  Raw value repr: {repr(raw_value)}")
                    print(f"  As float: {float(raw_value)}")
                    print(f"  Float repr: {repr(float(raw_value))}")
                    print()
                
                # Test a small grid around one point to see pixel-level variation
                print("TESTING SMALL GRID AROUND ONE POINT:")
                print("-" * 50)
                
                center_lat, center_lng = -28.0020000, 153.4140000
                center_x, center_y = transformer.transform(center_lng, center_lat)
                
                # Create a small grid around the center point
                offsets = [-1, -0.5, 0, 0.5, 1]  # Small offsets in dataset units
                
                for dy in offsets:
                    for dx in offsets:
                        test_x = center_x + dx
                        test_y = center_y + dy
                        
                        elevation_values = list(dataset.sample([(test_x, test_y)]))
                        raw_value = elevation_values[0][0]
                        
                        print(f"Offset ({dx:4.1f}, {dy:4.1f}): {raw_value} ({repr(raw_value)})")
                
    except Exception as e:
        print(f"Error accessing dataset: {e}")
        print("Note: Make sure your DEM service is running and AWS credentials are configured")

def test_rasterio_read_direct():
    """Directly test if rasterio can read the local DEM file."""
    logger.info("=== Testing Direct Rasterio Read ===")
    
    # Check if the file exists
    if not os.path.exists(LOCAL_DEM_PATH):
        pytest.skip(f"Local DEM file not found at {LOCAL_DEM_PATH}. Skipping direct rasterio read test.")

    try:
        # Attempt to open the GeoDataBase layer directly with the full path
        # Rasterio can open GDAL-supported formats like File Geodatabase directly
        # The syntax for opening a layer within a GDAL datasource is often 'datasource:layername'
        full_data_source_path = f"{LOCAL_DEM_PATH}:{LOCAL_DEM_LAYER}"
        
        logger.info(f"Attempting to open: {full_data_source_path}")
        with rasterio.open(full_data_source_path) as src:
            logger.info(f"✅ Successfully opened {full_data_source_path} with Rasterio")
            
            # Log some basic info
            logger.info(f"  Driver: {src.driver}")
            logger.info(f"  Bounds: {src.bounds}")
            logger.info(f"  Width: {src.width}, Height: {src.height}")
            logger.info(f"  CRS: {src.crs}")
            logger.info(f"  Transform: {src.transform}")
            logger.info(f"  Number of bands: {src.count}")
            
            # Read a small block of data (e.g., top-left corner)
            band1 = src.read(1, window=((0, 1), (0, 1)))
            logger.info(f"  Sample data from band 1 (top-left pixel): {band1[0,0]}")
            
            assert src.driver == "OpenFileGDB", f"Expected driver OpenFileGDB, got {src.driver}"
            assert src.count > 0, "No bands found in the dataset"
            assert band1[0,0] is not None, "Could not read sample data from the dataset"
            
    except rasterio.errors.RasterioIOError as e:
        logger.error(f"❌ RasterioIOError: Could not open {full_data_source_path}. Error: {e}")
        logger.info("This might indicate an issue with GDAL drivers or pathing to the GDB.")
        pytest.fail(f"RasterioIOError: {e}")
    except Exception as e:
        logger.error(f"❌ An unexpected error occurred: {e}")
        pytest.fail(f"Unexpected error: {e}")

# The main function is no longer needed for pytest
# if __name__ == "__main__":
#     test_raw_rasterio_precision() 