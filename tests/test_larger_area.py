#!/usr/bin/env python3
"""
Test script for larger area contour extraction
"""

import requests
import json
import logging
import pytest

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8001"
CONTOUR_URL = f"{BASE_URL}/api/v1/elevation/contour-data"

# Known good coordinates (Gold Coast area)
TEST_LAT = -27.975145
TEST_LON = 153.355888

def test_larger_area():
    """Test contour endpoint with a larger area"""
    logger.info("=== Testing Larger Area ===")
    
    # Create a larger polygon (~100m x 100m area)
    offset = 0.0005  # approximately 50 meters
    
    polygon_coords = [
        {"latitude": TEST_LAT - offset, "longitude": TEST_LON - offset},
        {"latitude": TEST_LAT - offset, "longitude": TEST_LON + offset},
        {"latitude": TEST_LAT + offset, "longitude": TEST_LON + offset},
        {"latitude": TEST_LAT + offset, "longitude": TEST_LON - offset},
        {"latitude": TEST_LAT - offset, "longitude": TEST_LON - offset}
    ]
    
    payload = {
        "area_bounds": {
            "polygon_coordinates": polygon_coords
        },
        "max_points": 5000
    }
    
    logger.info(f"Testing larger area around: ({TEST_LAT}, {TEST_LON})")
    logger.info(f"Area size: ±{offset} degrees (~100m x 100m)")
    
    response = requests.post(CONTOUR_URL, json=payload)
    assert response.status_code == 200, f"Request failed with status {response.status_code}: {response.text}"

    data = response.json()
    points_returned = data.get('total_points', 0)
    logger.info(f"✅ SUCCESS: {points_returned} points returned")
    
    # Get sampling info
    grid_info = data.get('grid_info', {})
    sampled_area = grid_info.get('sampled_area', {})
    logger.info(f"Sampling grid: {sampled_area.get('lat_samples')} x {sampled_area.get('lon_samples')} = {sampled_area.get('total_samples')} samples")
    logger.info(f"Grid resolution: {grid_info.get('grid_resolution_m')} meters")
    
    # Save response
    with open('larger_area_test_response.json', 'w') as f:
        json.dump(data, f, indent=2)
    logger.info("Response saved to 'larger_area_test_response.json'")
    
    # Show elevation statistics
    dem_points = data.get('dem_points', [])
    assert len(dem_points) > 0, "No DEM points returned for larger area."
    elevations = [p['elevation_m'] for p in dem_points if p['elevation_m'] is not None]
    assert len(elevations) > 0, "No valid elevations found in returned points."
    min_elev = min(elevations)
    max_elev = max(elevations)
    avg_elev = sum(elevations) / len(elevations)
    logger.info(f"Elevation range: {min_elev:.2f}m to {max_elev:.2f}m (avg: {avg_elev:.2f}m)")
    
    # Show a few sample points
    logger.info("Sample points:")
    for i, point in enumerate(dem_points[:5]):
        logger.info(f"  Point {i+1}: lat={point['latitude']:.6f}, lon={point['longitude']:.6f}, elev={point['elevation_m']}m")

def test_very_large_area():
    """Test with a very large area to test max_points limiting"""
    logger.info("=== Testing Very Large Area (Max Points Test) ===")
    
    # Create a very large polygon (~500m x 500m area)
    offset = 0.002  # approximately 200+ meters
    
    polygon_coords = [
        {"latitude": TEST_LAT - offset, "longitude": TEST_LON - offset},
        {"latitude": TEST_LAT - offset, "longitude": TEST_LON + offset},
        {"latitude": TEST_LAT + offset, "longitude": TEST_LON + offset},
        {"latitude": TEST_LAT + offset, "longitude": TEST_LON - offset},
        {"latitude": TEST_LAT - offset, "longitude": TEST_LON - offset}
    ]
    
    payload = {
        "area_bounds": {
            "polygon_coordinates": polygon_coords
        },
        "max_points": 1000  # Limit to test truncation
    }
    
    logger.info(f"Testing very large area: ±{offset} degrees (~400m x 400m)")
    logger.info(f"Max points limit: {payload['max_points']}")
    
    response = requests.post(CONTOUR_URL, json=payload)
    assert response.status_code == 200, f"Request failed with status {response.status_code}: {response.text}"
    
    data = response.json()
    points_returned = data.get('total_points', 0)
    logger.info(f"Points returned: {points_returned}")
    
    assert points_returned <= payload['max_points'], \
        f"Returned points ({points_returned}) exceeded requested max_points ({payload['max_points']})"
    
    # Get sampling info
    grid_info = data.get('grid_info', {})
    sampled_area = grid_info.get('sampled_area', {})
    logger.info(f"Sampling grid: {sampled_area.get('lat_samples')} x {sampled_area.get('lon_samples')} = {sampled_area.get('total_samples')} samples")

# The main function is no longer needed for pytest
# def main():
#     """Main test function"""
#     logger.info("=== Large Area Contour Test ===")
#     
#     # Test 1: Larger area
#     success1 = test_larger_area()
#     
#     # Test 2: Very large area (max points test)
#     success2 = test_very_large_area()
#     
#     if success1 and success2:
#         logger.info("✅ All large area tests passed!")
#     else:
#         logger.warning("⚠️  Some tests failed")
#     
#     logger.info("\n=== Large Area Test Complete ===")
#
# if __name__ == "__main__":
#     main() 