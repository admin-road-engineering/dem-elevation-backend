#!/usr/bin/env python3
"""
Test script for the contour data endpoint
"""

import requests
import json
import logging
import pytest # Import pytest

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test configuration
BASE_URL = "http://localhost:8001"
SINGLE_POINT_URL = f"{BASE_URL}/api/v1/elevation/point"
CONTOUR_URL = f"{BASE_URL}/api/v1/elevation/contour-data"
HEALTH_URL = f"{BASE_URL}/health"

# Known good coordinates that should return elevation data (Gold Coast area)
TEST_LAT = -27.975145
TEST_LON = 153.355888

def test_health():
    """Test health endpoint"""
    logger.info(f"Health check response: GET {HEALTH_URL}")
    response = requests.get(HEALTH_URL)
    logger.info(f"Health check status: {response.status_code}")
    assert response.status_code == 200, f"Health check failed with status {response.status_code}: {response.text}"
    health_data = response.json()
    logger.info("✅ Service is healthy!")
    logger.info(f"DEM sources configured: {health_data.get('dem_sources_configured', 'unknown')}")
    assert health_data.get("status") == "healthy", f"Health status not 'healthy': {health_data}"

def test_single_point():
    """Test single point endpoint first"""
    logger.info("=== Testing Single Point Endpoint ===")
    
    payload = {
        "latitude": TEST_LAT,
        "longitude": TEST_LON
    }
    
    logger.info(f"POST {SINGLE_POINT_URL} with payload: {payload}")
    response = requests.post(SINGLE_POINT_URL, json=payload)
    logger.info(f"Single point response status: {response.status_code}")
    
    assert response.status_code == 200, f"Single point failed with status {response.status_code}: {response.text}"
    data = response.json()
    elevation = data.get('elevation_m')
    logger.info(f"✅ Single point elevation: {elevation}m")
    assert elevation is not None, "Elevation is None"

def test_contour_endpoint():
    """Test contour data endpoint"""
    logger.info("=== Testing Contour Data Endpoint ===")
    
    # Create a very small polygon around the known good point
    # ~10m x 10m area around the test coordinate
    offset = 0.00009  # approximately 10 meters
    
    polygon_coords = [
        {"latitude": TEST_LAT - offset, "longitude": TEST_LON - offset},
        {"latitude": TEST_LAT - offset, "longitude": TEST_LON + offset},
        {"latitude": TEST_LAT + offset, "longitude": TEST_LON + offset},
        {"latitude": TEST_LAT + offset, "longitude": TEST_LON - offset},
        {"latitude": TEST_LAT - offset, "longitude": TEST_LON - offset}  # Close the polygon
    ]
    
    payload = {
        "area_bounds": {
            "polygon_coordinates": polygon_coords
        },
        "max_points": 100
    }
    
    logger.info(f"Testing contour data endpoint: POST {CONTOUR_URL}")
    logger.info(f"Polygon area: {len(polygon_coords)} coordinates")
    logger.info(f"Polygon center: ({TEST_LAT}, {TEST_LON})")
    
    response = requests.post(CONTOUR_URL, json=payload)
    logger.info(f"Response status code: {response.status_code}")
    
    assert response.status_code == 200, f"Contour endpoint failed with status {response.status_code}: {response.text}"
    data = response.json()
    logger.info("✅ SUCCESS: Contour data endpoint is working!")
    logger.info(f"Total DEM points returned: {data.get('total_points', 'unknown')}")
    logger.info(f"DEM source used: {data.get('dem_source_used', 'unknown')}")
    
    # Get grid info
    grid_info = data.get('grid_info', {})
    grid_resolution = grid_info.get('grid_resolution_m', 'unknown')
    logger.info(f"Grid resolution: {grid_resolution} meters")
    
    # Save response for analysis
    with open('contour_test_response.json', 'w') as f:
        json.dump(data, f, indent=2)
    logger.info("Response saved to 'contour_test_response.json'")
    
    # Show first few points if any
    dem_points = data.get('dem_points', [])
    assert len(dem_points) > 0, "No DEM points returned - may still be an issue with sparse data"
    logger.info("First few DEM points:")
    for i, point in enumerate(dem_points[:3]):
        logger.info(f"  Point {i+1}: lat={point['latitude']}, lon={point['longitude']}, elev={point['elevation_m']}m")

# main function is no longer needed as pytest will discover tests automatically
# def main():
#     """Main test function"""
#     logger.info("=== DEM Contour Data Endpoint Test ===")
#     
#     # Test health
#     if not test_health():
#         logger.error("Health check failed, stopping tests")
#         return
#     
#     # Test single point first
#     if not test_single_point():
#         logger.error("Single point test failed, stopping tests")
#         return
#     
#     # Test contour endpoint
#     test_contour_endpoint()
#     
#     logger.info("\n=== Test Complete ===")

# if __name__ == "__main__":
#     main() 