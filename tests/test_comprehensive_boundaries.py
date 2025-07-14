#!/usr/bin/env python3
"""
Comprehensive test for boundary artifacts across different polygon sizes and shapes.
"""

import requests
import json
import logging
from math import sqrt
import pytest

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8001"
CONTOUR_URL = f"{BASE_URL}/api/v1/elevation/contour-data"

# Test coordinates for Gold Coast area
TEST_LAT_CENTER = -27.975145
TEST_LON_CENTER = 153.355888

def calculate_segment_length(coord1, coord2):
    """Calculate approximate distance between two coordinates in degrees."""
    lon_diff = coord2[0] - coord1[0]
    lat_diff = coord2[1] - coord1[1]
    return sqrt(lon_diff**2 + lat_diff**2)

def test_polygon_boundaries(test_name, polygon_coords, max_points=10000):
    """Test a specific polygon for boundary artifacts."""
    logger.info(f"\n=== {test_name} ===")
    
    # Request contour data
    contour_request_data = {
        "area_bounds": {
            "polygon_coordinates": polygon_coords
        },
        "minor_contour_interval_m": 2.0,
        "major_contour_interval_m": 10.0,
        "max_points": max_points
    }
    
    response = requests.post(CONTOUR_URL, json=contour_request_data, timeout=30)
    response.raise_for_status()
    
    result = response.json()
    
    assert result.get("success"), f"{test_name} failed: {result.get('error', 'Unknown error')}"
    
    contours = result.get("contours", {})
    features = contours.get("features", [])
    
    logger.info(f"✅ Received {len(features)} contour line features")
    
    # Analyze for artifacts
    long_segments = []
    very_long_segments = []
    
    for i, feature in enumerate(features):
        if feature["geometry"]["type"] != "LineString":
            continue
            
        coordinates = feature["geometry"]["coordinates"]
        elevation = feature["properties"]["elevation"]
        
        for j in range(len(coordinates) - 1):
            segment_length = calculate_segment_length(coordinates[j], coordinates[j+1])
            
            if segment_length > 0.0005:  # roughly 50 meters in degrees
                long_segments.append({
                    "length": segment_length,
                    "elevation": elevation
                })
                
            if segment_length > 0.001:  # roughly 100 meters in degrees
                very_long_segments.append({
                    "length": segment_length,
                    "elevation": elevation
                })
    
    # Report results
    logger.info(f"   📊 Results: {len(features)} contours, {len(long_segments)} long segments, {len(very_long_segments)} very long segments")
    
    assert len(very_long_segments) == 0, f"{len(very_long_segments)} potential artifacts detected"
    logger.info("   ✅ No boundary artifacts detected!")

# Helper function to generate test cases
def generate_test_cases():
    test_cases = []

    # Test 1: Small square polygon (100m x 100m)
    offset1 = 0.0009  # approximately 100 meters
    polygon1 = [
        {"latitude": TEST_LAT_CENTER - offset1, "longitude": TEST_LON_CENTER - offset1},
        {"latitude": TEST_LAT_CENTER + offset1, "longitude": TEST_LON_CENTER - offset1},
        {"latitude": TEST_LAT_CENTER + offset1, "longitude": TEST_LON_CENTER + offset1},
        {"latitude": TEST_LAT_CENTER - offset1, "longitude": TEST_LON_CENTER + offset1},
        {"latitude": TEST_LAT_CENTER - offset1, "longitude": TEST_LON_CENTER - offset1}
    ]
    test_cases.append(("Small Square (100m x 100m)", polygon1, 10000))

    # Test 2: Medium square polygon (300m x 300m)
    offset2 = 0.0027  # approximately 300 meters
    polygon2 = [
        {"latitude": TEST_LAT_CENTER - offset2, "longitude": TEST_LON_CENTER - offset2},
        {"latitude": TEST_LAT_CENTER + offset2, "longitude": TEST_LON_CENTER - offset2},
        {"latitude": TEST_LAT_CENTER + offset2, "longitude": TEST_LON_CENTER + offset2},
        {"latitude": TEST_LAT_CENTER - offset2, "longitude": TEST_LON_CENTER + offset2},
        {"latitude": TEST_LAT_CENTER - offset2, "longitude": TEST_LON_CENTER - offset2}
    ]
    test_cases.append(("Medium Square (300m x 300m)", polygon2, 10000))

    # Test 3: Rectangular polygon (200m x 500m)
    offset_lat = 0.0018  # approximately 200 meters
    offset_lon = 0.0045  # approximately 500 meters
    polygon3 = [
        {"latitude": TEST_LAT_CENTER - offset_lat, "longitude": TEST_LON_CENTER - offset_lon},
        {"latitude": TEST_LAT_CENTER + offset_lat, "longitude": TEST_LON_CENTER - offset_lon},
        {"latitude": TEST_LAT_CENTER + offset_lat, "longitude": TEST_LON_CENTER + offset_lon},
        {"latitude": TEST_LAT_CENTER - offset_lat, "longitude": TEST_LON_CENTER + offset_lon},
        {"latitude": TEST_LAT_CENTER - offset_lat, "longitude": TEST_LON_CENTER - offset_lon}
    ]
    test_cases.append(("Rectangle (200m x 500m)", polygon3, 10000))

    # Test 4: Triangular polygon
    offset = 0.002
    polygon4 = [
        {"latitude": TEST_LAT_CENTER - offset, "longitude": TEST_LON_CENTER},
        {"latitude": TEST_LAT_CENTER + offset, "longitude": TEST_LON_CENTER - offset},
        {"latitude": TEST_LAT_CENTER + offset, "longitude": TEST_LON_CENTER + offset},
        {"latitude": TEST_LAT_CENTER - offset, "longitude": TEST_LON_CENTER}
    ]
    test_cases.append(("Triangle", polygon4, 10000))

    # Test 5: Irregular polygon (pentagon-like)
    polygon5 = [
        {"latitude": TEST_LAT_CENTER - 0.003, "longitude": TEST_LON_CENTER},
        {"latitude": TEST_LAT_CENTER - 0.001, "longitude": TEST_LON_CENTER - 0.003},
        {"latitude": TEST_LAT_CENTER + 0.002, "longitude": TEST_LON_CENTER - 0.002},
        {"latitude": TEST_LAT_CENTER + 0.002, "longitude": TEST_LON_CENTER + 0.003},
        {"latitude": TEST_LAT_CENTER - 0.001, "longitude": TEST_LON_CENTER + 0.002},
        {"latitude": TEST_LAT_CENTER - 0.003, "longitude": TEST_LON_CENTER}
    ]
    test_cases.append(("Irregular Pentagon", polygon5, 10000))

    return test_cases

@pytest.mark.parametrize("test_name, polygon_coords, max_points", generate_test_cases())
def test_comprehensive_boundary_artifacts(test_name, polygon_coords, max_points):
    test_polygon_boundaries(test_name, polygon_coords, max_points) 