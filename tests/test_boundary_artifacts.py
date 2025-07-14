#!/usr/bin/env python3
"""
Test script to check for boundary connection artifacts in contour generation.
"""

import requests
import json
import logging
from math import sqrt
import pytest # Import pytest

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

def test_contour_boundary_artifacts():
    """Analyze contour lines for potential boundary connection artifacts."""
    logger.info("=== Testing Contour Boundary Artifacts ===")
    
    # Create a test polygon area
    offset = 0.002  # approximately 200 meters
    
    polygon_coords = [
        {"latitude": TEST_LAT_CENTER - offset, "longitude": TEST_LON_CENTER - offset},
        {"latitude": TEST_LAT_CENTER + offset, "longitude": TEST_LON_CENTER - offset},
        {"latitude": TEST_LAT_CENTER + offset, "longitude": TEST_LON_CENTER + offset},
        {"latitude": TEST_LAT_CENTER - offset, "longitude": TEST_LON_CENTER + offset},
        {"latitude": TEST_LAT_CENTER - offset, "longitude": TEST_LON_CENTER - offset}  # Close the polygon
    ]
    
    # Request contour data
    contour_request_data = {
        "area_bounds": {
            "polygon_coordinates": polygon_coords
        },
        "minor_contour_interval_m": 2.0,
        "major_contour_interval_m": 10.0,
        "max_points": 10000
    }
    
    logger.info(f"Requesting contours for {offset*2:.3f}° x {offset*2:.3f}° area")
    
    response = requests.post(CONTOUR_URL, json=contour_request_data, timeout=30)
    response.raise_for_status() # Raise an exception for HTTP errors
    
    result = response.json()
    
    assert result.get("success"), f"Contour request failed: {result.get('error', 'Unknown error')}"
    
    contours = result.get("contours", {})
    features = contours.get("features", [])
    
    logger.info(f"✅ Received {len(features)} contour line features")
    
    # Analyze each contour for potential artifacts
    long_segments = []
    very_long_segments = []
    suspicious_contours = []
    
    for i, feature in enumerate(features):
        if feature["geometry"]["type"] != "LineString":
            continue
            
        coordinates = feature["geometry"]["coordinates"]
        elevation = feature["properties"]["elevation"]
        
        # Check each segment in this contour
        max_segment_length = 0
        total_length = 0
        long_segment_count = 0
        
        for j in range(len(coordinates) - 1):
            segment_length = calculate_segment_length(coordinates[j], coordinates[j+1])
            total_length += segment_length
            max_segment_length = max(max_segment_length, segment_length)
            
            # Flag potentially problematic segments
            if segment_length > 0.0005:  # roughly 50 meters in degrees
                long_segment_count += 1
                long_segments.append({
                    "contour_index": i,
                    "segment_index": j,
                    "length": segment_length,
                    "elevation": elevation,
                    "start": coordinates[j],
                    "end": coordinates[j+1]
                })
                
            if segment_length > 0.001:  # roughly 100 meters in degrees
                very_long_segments.append({
                    "contour_index": i,
                    "segment_index": j,
                    "length": segment_length,
                    "elevation": elevation,
                    "start": coordinates[j],
                    "end": coordinates[j+1]
                })
        
        # Flag suspicious contours (those with many long segments)
        if long_segment_count > len(coordinates) * 0.3:  # More than 30% long segments
            suspicious_contours.append({
                "contour_index": i,
                "elevation": elevation,
                "total_segments": len(coordinates) - 1,
                "long_segments": long_segment_count,
                "max_segment_length": max_segment_length,
                "total_length": total_length
            })
    
    # Report results
    logger.info(f"📊 Analysis Results:")
    logger.info(f"   Total contour features: {len(features)}")
    logger.info(f"   Long segments (>50m): {len(long_segments)}")
    logger.info(f"   Very long segments (>100m): {len(very_long_segments)}")
    logger.info(f"   Suspicious contours: {len(suspicious_contours)}")
    
    if very_long_segments:
        logger.warning(f"⚠️  Found {len(very_long_segments)} very long segments that may be artifacts:")
        for seg in very_long_segments[:5]:  # Show first 5
            logger.warning(f"     Elevation {seg['elevation']}m: {seg['length']:.6f}° from {seg['start']} to {seg['end']}")
            
    if suspicious_contours:
        logger.warning(f"⚠️  Found {len(suspicious_contours)} suspicious contours:")
        for contour in suspicious_contours[:3]:  # Show first 3
            logger.warning(f"     Elevation {contour['elevation']}m: {contour['long_segments']}/{contour['total_segments']} long segments")
    
    assert len(very_long_segments) == 0 and len(suspicious_contours) == 0, \
        f"Boundary artifacts detected: {len(very_long_segments)} very long segments, {len(suspicious_contours)} suspicious contours"
    logger.info("✅ No boundary connection artifacts detected!")
    
    # Save detailed analysis
    analysis_result = {
        "total_features": len(features),
        "long_segments": long_segments,
        "very_long_segments": very_long_segments,
        "suspicious_contours": suspicious_contours,
        "summary": {
            "long_segment_count": len(long_segments),
            "very_long_segment_count": len(very_long_segments),
            "suspicious_contour_count": len(suspicious_contours)
        }
    }
    
    with open("boundary_artifacts_analysis.json", "w") as f:
        json.dump(analysis_result, f, indent=2)
    logger.info("Analysis saved to 'boundary_artifacts_analysis.json'")

# The main function is no longer needed for pytest
# if __name__ == "__main__":
#     analyze_contour_artifacts() 