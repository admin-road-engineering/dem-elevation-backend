#!/usr/bin/env python3
"""
Test script to verify the max_points limit for contour data requests.
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

# Known good coordinates (Gold Coast area) - defining a larger area for high point counts
TEST_LAT_CENTER = -27.975145
TEST_LON_CENTER = 153.355888

def test_max_points_limit(max_points_requested: int, area_offset: float, expected_min_points: int = 0):
    """Test contour endpoint with a specified max_points limit and polygon area."""
    logger.info(f"\n=== Testing max_points: {max_points_requested} ===")
    
    # Create a polygon covering a certain area
    polygon_coords = [
        {"latitude": TEST_LAT_CENTER - area_offset, "longitude": TEST_LON_CENTER - area_offset},
        {"latitude": TEST_LAT_CENTER - area_offset, "longitude": TEST_LON_CENTER + area_offset},
        {"latitude": TEST_LAT_CENTER + area_offset, "longitude": TEST_LON_CENTER + area_offset},
        {"latitude": TEST_LAT_CENTER + area_offset, "longitude": TEST_LON_CENTER - area_offset}
    ]
    
    payload = {
        "area_bounds": {
            "polygon_coordinates": polygon_coords
        },
        "max_points": max_points_requested,
        "sampling_interval_m": 1.0 # Use 1m resolution for consistent testing
    }
    
    response = requests.post(CONTOUR_URL, json=payload)
    logger.info(f"Response status: {response.status_code}")
    
    assert response.status_code == 200, f"API request failed with status {response.status_code}: {response.text}"

    data = response.json()
    points_returned = data['total_points']
    grid_info = data['grid_info']
    
    logger.info(f"Requested max_points: {max_points_requested}")
    logger.info(f"Points returned: {points_returned}")
    logger.info(f"Grid resolution used: {grid_info['grid_resolution_m']}m")
    logger.info(f"DEM native resolution: {grid_info['dem_native_resolution_m']}m")
    logger.info(f"Total theoretical samples before reduction: {grid_info['sampled_area']['total_samples']}")

    assert points_returned <= max_points_requested, \
        f"Returned points ({points_returned}) exceeded requested max_points ({max_points_requested})"
    
    if expected_min_points > 0:
        assert points_returned >= expected_min_points, \
            f"Returned points ({points_returned}) were less than expected min_points ({expected_min_points})"

    logger.info(f"Max points test for {max_points_requested} PASSED.")

# Helper function to generate test cases for parametrize
def generate_max_points_test_cases():
    return [
        # Test with a small max_points limit and a small area
        (1000, 0.0001, 100),
        # Test with an intermediate max_points limit and a larger area
        (50000, 0.0005, 10000),
        # Test with the maximum allowed max_points limit and a very large area
        # This area should definitely exceed 200k * 2 = 400k theoretical points at 1m resolution,
        # triggering the density reduction in the backend.
        (200000, 0.01, 0) # No minimum expected for this large area test
    ]

@pytest.mark.parametrize("max_points_requested, area_offset, expected_min_points", generate_max_points_test_cases())
def test_max_points_functionality(max_points_requested, area_offset, expected_min_points):
    test_max_points_limit(max_points_requested, area_offset, expected_min_points)

# The original __main__ block is replaced by pytest discovery and parametrize
# if __name__ == "__main__":
#     # Test cases
#     
#     # Test with a small max_points limit and a small area
#     test_max_points_limit(max_points_requested=1000, area_offset=0.0001, expected_min_points=100)
#
#     # Test with an intermediate max_points limit and a larger area
#     test_max_points_limit(max_points_requested=50000, area_offset=0.0005, expected_min_points=10000)
#
#     # Test with the maximum allowed max_points limit and a very large area
#     # This area should definitely exceed 200k * 2 = 400k theoretical points at 1m resolution,
#     # triggering the density reduction in the backend.
#     test_max_points_limit(max_points_requested=200000, area_offset=0.01) 