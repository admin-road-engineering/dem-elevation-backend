#!/usr/bin/env python3
"""
Test script to debug grid sampling by testing the exact grid coordinate
that corresponds to our known good point.
"""

import requests
import json
import logging
import pytest # Import pytest

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8001"
CONTOUR_URL = f"{BASE_URL}/api/v1/elevation/contour-data"

# Known good coordinates
TEST_LAT = -27.975145
TEST_LON = 153.355888

def test_exact_point_as_polygon():
    """Test contour endpoint with a polygon containing just the exact test point"""
    logger.info("=== Testing Exact Point as Polygon ===")
    
    # Create a very tiny polygon that basically represents just the test point
    tiny_offset = 0.000001  # About 0.1 meters
    
    polygon_coords = [
        {"latitude": TEST_LAT - tiny_offset, "longitude": TEST_LON - tiny_offset},
        {"latitude": TEST_LAT - tiny_offset, "longitude": TEST_LON + tiny_offset},
        {"latitude": TEST_LAT + tiny_offset, "longitude": TEST_LON + tiny_offset},
        {"latitude": TEST_LAT + tiny_offset, "longitude": TEST_LON - tiny_offset},
        {"latitude": TEST_LAT - tiny_offset, "longitude": TEST_LON - tiny_offset}  # Close the polygon
    ]
    
    payload = {
        "area_bounds": {
            "polygon_coordinates": polygon_coords
        },
        "max_points": 100
    }
    
    logger.info(f"Testing with tiny polygon around exact point: ({TEST_LAT}, {TEST_LON})")
    logger.info(f"Polygon offset: ±{tiny_offset} (about 0.1m)")
    
    response = requests.post(CONTOUR_URL, json=payload)
    assert response.status_code == 200, f"Request failed with status {response.status_code}: {response.text}"

    data = response.json()
    points_returned = data.get('total_points', 0)
    logger.info(f"Points returned: {points_returned}")
    
    assert points_returned > 0, "No points found with tiny polygon"
    logger.info("✅ SUCCESS: Found points with tiny polygon!")
    for i, point in enumerate(data.get('dem_points', [])[:3]):
        logger.info(f"  Point {i+1}: lat={point['latitude']:.8f}, lon={point['longitude']:.8f}, elev={point['elevation_m']}m")
        logger.info(f"    Grid: ({point['x_grid_index']}, {point['y_grid_index']})")
        
    # Check the queried area details
    grid_info = data.get('grid_info', {})
    # queried_area = grid_info.get('queried_area', {})
    # logger.info(f"Queried grid area:")
    # logger.info(f"  Columns: {queried_area.get('col_start')} to {queried_area.get('col_end')}")
    # logger.info(f"  Rows: {queried_area.get('row_start')} to {queried_area.get('row_end')}")

def test_single_pixel_polygon():
    """Test with a polygon that should capture exactly one pixel"""
    logger.info("=== Testing Single Pixel Polygon ===")
    
    # Create polygon based on the known grid coordinate
    # From previous tests: center point is around grid (33500, 20000)
    # Let's create a polygon that targets exactly one pixel
    
    # Calculate the exact boundaries for one pixel
    # Grid resolution is 1m, so we need bounds that capture just one pixel
    pixel_size = 0.000009  # About 1 meter in degrees at this latitude
    
    polygon_coords = [
        {"latitude": TEST_LAT - pixel_size/2, "longitude": TEST_LON - pixel_size/2},
        {"latitude": TEST_LAT - pixel_size/2, "longitude": TEST_LON + pixel_size/2},
        {"latitude": TEST_LAT + pixel_size/2, "longitude": TEST_LON + pixel_size/2},
        {"latitude": TEST_LAT + pixel_size/2, "longitude": TEST_LON - pixel_size/2},
        {"latitude": TEST_LAT - pixel_size/2, "longitude": TEST_LON - pixel_size/2}  # Close the polygon
    ]
    
    payload = {
        "area_bounds": {
            "polygon_coordinates": polygon_coords
        },
        "max_points": 100
    }
    
    logger.info(f"Testing with single-pixel polygon around: ({TEST_LAT}, {TEST_LON})")
    logger.info(f"Pixel size: ±{pixel_size/2} (about 0.5m)")
    
    response = requests.post(CONTOUR_URL, json=payload)
    assert response.status_code == 200, f"Request failed with status {response.status_code}: {response.text}"

    data = response.json()
    points_returned = data.get('total_points', 0)
    logger.info(f"Points returned: {points_returned}")
    
    # Save detailed response
    with open('single_pixel_test_response.json', 'w') as f:
        json.dump(data, f, indent=2)
    logger.info("Response saved to \'single_pixel_test_response.json\'")
    
    assert points_returned > 0, "No points found with single-pixel polygon"
    logger.info("✅ SUCCESS: Found points with single-pixel polygon!")
    for i, point in enumerate(data.get('dem_points', [])):
        logger.info(f"  Point {i+1}: lat={point['latitude']:.8f}, lon={point['longitude']:.8f}, elev={point['elevation_m']}m")
        logger.info(f"    Grid: ({point['x_grid_index']}, {point['y_grid_index']})")

# The main function is no longer needed for pytest
# def main():
#     """Main test function"""
#     logger.info("=== Grid Point Debugging Test ===")
#     
#     # Test 1: Tiny polygon
#     success1 = test_exact_point_as_polygon()
#     
#     # Test 2: Single pixel polygon
#     success2 = test_single_pixel_polygon()
#     
#     if success1 or success2:
#         logger.info("✅ At least one test succeeded!")
#     else:
#         logger.warning("⚠️  Both tests failed - there may be a fundamental issue with the data sampling approach")
#     
#     logger.info("\n=== Debug Test Complete ===")
#
# if __name__ == "__main__":
#     main() 