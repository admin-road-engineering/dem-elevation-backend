#!/usr/bin/env python3
"""
Test script to verify the sampling interval options work correctly
"""

import requests
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8001"
CONTOUR_URL = f"{BASE_URL}/api/v1/elevation/contour-data"

# Known good coordinates (Gold Coast area)
TEST_LAT = -27.975145
TEST_LON = 153.355888

def test_default_resolution():
    """Test with default DEM resolution (should be 1m)"""
    logger.info("=== Testing Default DEM Resolution ===")
    
    # Small polygon around test point
    offset = 0.0001  # approximately 10 meters
    polygon_coords = [
        {"latitude": TEST_LAT - offset, "longitude": TEST_LON - offset},
        {"latitude": TEST_LAT - offset, "longitude": TEST_LON + offset},
        {"latitude": TEST_LAT + offset, "longitude": TEST_LON + offset},
        {"latitude": TEST_LAT + offset, "longitude": TEST_LON - offset}
    ]
    
    payload = {
        "area_bounds": {
            "polygon_coordinates": polygon_coords
        },
        "max_points": 1000
        # sampling_interval_m not specified - should default to DEM resolution
    }
    
    response = requests.post(CONTOUR_URL, json=payload)
    logger.info(f"Response status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        logger.info(f"Default resolution test - Points returned: {data['total_points']}")
        logger.info(f"Grid info: {json.dumps(data['grid_info'], indent=2)}")
        logger.info(f"Sample point: {data['dem_points'][0] if data['dem_points'] else 'No points'}")
    else:
        logger.error(f"Error: {response.text}")

def test_custom_resolution_1m():
    """Test with explicit 1m resolution"""
    logger.info("=== Testing Custom 1m Resolution ===")
    
    # Small polygon around test point
    offset = 0.0001  # approximately 10 meters
    polygon_coords = [
        {"latitude": TEST_LAT - offset, "longitude": TEST_LON - offset},
        {"latitude": TEST_LAT - offset, "longitude": TEST_LON + offset},
        {"latitude": TEST_LAT + offset, "longitude": TEST_LON + offset},
        {"latitude": TEST_LAT + offset, "longitude": TEST_LON - offset}
    ]
    
    payload = {
        "area_bounds": {
            "polygon_coordinates": polygon_coords
        },
        "max_points": 1000,
        "sampling_interval_m": 1.0
    }
    
    response = requests.post(CONTOUR_URL, json=payload)
    logger.info(f"Response status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        logger.info(f"1m resolution test - Points returned: {data['total_points']}")
        logger.info(f"Grid resolution: {data['grid_info']['grid_resolution_m']}m")
        logger.info(f"DEM native resolution: {data['grid_info']['dem_native_resolution_m']}m")
    else:
        logger.error(f"Error: {response.text}")

def test_custom_resolution_5m():
    """Test with coarser 5m resolution"""
    logger.info("=== Testing Custom 5m Resolution ===")
    
    # Small polygon around test point
    offset = 0.0002  # approximately 20 meters
    polygon_coords = [
        {"latitude": TEST_LAT - offset, "longitude": TEST_LON - offset},
        {"latitude": TEST_LAT - offset, "longitude": TEST_LON + offset},
        {"latitude": TEST_LAT + offset, "longitude": TEST_LON + offset},
        {"latitude": TEST_LAT + offset, "longitude": TEST_LON - offset}
    ]
    
    payload = {
        "area_bounds": {
            "polygon_coordinates": polygon_coords
        },
        "max_points": 1000,
        "sampling_interval_m": 5.0
    }
    
    response = requests.post(CONTOUR_URL, json=payload)
    logger.info(f"Response status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        logger.info(f"5m resolution test - Points returned: {data['total_points']}")
        logger.info(f"Grid resolution: {data['grid_info']['grid_resolution_m']}m")
        logger.info(f"DEM native resolution: {data['grid_info']['dem_native_resolution_m']}m")
    else:
        logger.error(f"Error: {response.text}")

def test_custom_resolution_0_5m():
    """Test with finer 0.5m resolution (oversampling)"""
    logger.info("=== Testing Custom 0.5m Resolution (Oversampling) ===")
    
    # Very small polygon to keep point count manageable
    offset = 0.00005  # approximately 5 meters
    polygon_coords = [
        {"latitude": TEST_LAT - offset, "longitude": TEST_LON - offset},
        {"latitude": TEST_LAT - offset, "longitude": TEST_LON + offset},
        {"latitude": TEST_LAT + offset, "longitude": TEST_LON + offset},
        {"latitude": TEST_LAT + offset, "longitude": TEST_LON - offset}
    ]
    
    payload = {
        "area_bounds": {
            "polygon_coordinates": polygon_coords
        },
        "max_points": 1000,
        "sampling_interval_m": 0.5
    }
    
    response = requests.post(CONTOUR_URL, json=payload)
    logger.info(f"Response status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        logger.info(f"0.5m resolution test - Points returned: {data['total_points']}")
        logger.info(f"Grid resolution: {data['grid_info']['grid_resolution_m']}m")
        logger.info(f"DEM native resolution: {data['grid_info']['dem_native_resolution_m']}m")
    else:
        logger.error(f"Error: {response.text}")

if __name__ == "__main__":
    test_default_resolution()
    print("\n" + "="*50 + "\n")
    test_custom_resolution_1m()
    print("\n" + "="*50 + "\n")
    test_custom_resolution_5m()
    print("\n" + "="*50 + "\n")
    test_custom_resolution_0_5m() 