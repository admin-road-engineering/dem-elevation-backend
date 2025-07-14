#!/usr/bin/env python3
"""
Test script to verify GDAL error suppression is working.
Run this to check if the GDAL filegdbtable.cpp errors are being suppressed.
"""

import os
import sys
import logging
from pathlib import Path
import requests
import json
import pytest

# Add the current directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent))

# Set up logging to see what happens
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

BASE_URL = "http://localhost:8001"
CONTOUR_URL = f"{BASE_URL}/api/v1/elevation/contour-data"

# Coordinates outside a likely DEM coverage area (e.g., in the ocean or far from defined DEM)
TEST_LAT_OUTSIDE = -20.0000
TEST_LON_OUTSIDE = 160.0000

def test_error_suppression_with_no_data():
    """Test that the service handles areas with no data gracefully without 500 errors."""
    logger.info("=== Testing Error Suppression for No Data ===")
    
    # Create a polygon in an area where there is likely no DEM data
    offset = 0.01  # A reasonably large area
    
    polygon_coords = [
        {"latitude": TEST_LAT_OUTSIDE - offset, "longitude": TEST_LON_OUTSIDE - offset},
        {"latitude": TEST_LAT_OUTSIDE - offset, "longitude": TEST_LON_OUTSIDE + offset},
        {"latitude": TEST_LAT_OUTSIDE + offset, "longitude": TEST_LON_OUTSIDE + offset},
        {"latitude": TEST_LAT_OUTSIDE + offset, "longitude": TEST_LON_OUTSIDE - offset},
        {"latitude": TEST_LAT_OUTSIDE - offset, "longitude": TEST_LON_OUTSIDE - offset}  # Close the polygon
    ]
    
    payload = {
        "area_bounds": {
            "polygon_coordinates": polygon_coords
        },
        "max_points": 100
    }
    
    logger.info(f"Requesting contour data for an area outside DEM coverage: ({TEST_LAT_OUTSIDE}, {TEST_LON_OUTSIDE})")
    
    response = requests.post(CONTOUR_URL, json=payload)
    
    # Expect a 200 OK status code even if no data is found, but with appropriate message and no points
    assert response.status_code == 200, f"Expected 200 OK, but got {response.status_code}. Response: {response.text}"
    
    data = response.json()
    logger.info(f"Response: {data}")
    
    assert data.get("success") is True, f"Expected success=True, but got {data.get('success')}"
    assert data.get("total_points") == 0, f"Expected 0 total_points, but got {data.get('total_points')}"
    assert "no elevation data found" in data.get("message", "").lower(), \
        f"Expected 'no elevation data found' message, but got {data.get('message')}"
    
    logger.info("✅ Error suppression test (no data) passed! Service handled no data gracefully.")

def test_error_suppression_with_invalid_input():
    """Test that the service handles invalid input gracefully with 422 (Unprocessable Entity)."""
    logger.info("=== Testing Error Suppression for Invalid Input ===")
    
    # Test case 1: Missing required field (polygon_coordinates)
    invalid_payload_1 = {
        "area_bounds": {
            # "polygon_coordinates": [] # Missing
        },
        "max_points": 100
    }
    
    logger.info("Testing with missing polygon_coordinates...")
    response_1 = requests.post(CONTOUR_URL, json=invalid_payload_1)
    assert response_1.status_code == 422, f"Expected 422 for missing field, got {response_1.status_code}"
    logger.info(f"✅ Invalid input test 1 passed (missing field): Status {response_1.status_code}")
    
    # Test case 2: Invalid coordinate format (e.g., string instead of number)
    invalid_payload_2 = {
        "area_bounds": {
            "polygon_coordinates": [
                {"latitude": "invalid", "longitude": TEST_LON_OUTSIDE}
            ]
        },
        "max_points": 100
    }
    
    logger.info("Testing with invalid coordinate format...")
    response_2 = requests.post(CONTOUR_URL, json=invalid_payload_2)
    assert response_2.status_code == 422, f"Expected 422 for invalid format, got {response_2.status_code}"
    logger.info(f"✅ Invalid input test 2 passed (invalid format): Status {response_2.status_code}")
    
    logger.info("✅ All invalid input tests passed! Service handled errors gracefully.")

# The main function is no longer needed for pytest
# if __name__ == "__main__":
#     test_error_suppression_with_no_data()
#     test_error_suppression_with_invalid_input() 