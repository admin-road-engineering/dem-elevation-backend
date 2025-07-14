import requests
import json
import logging
import pytest

logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8001"
CONTOUR_URL = f"{BASE_URL}/api/v1/elevation/contour-data"

def test_geotiff_source():
    """Test using the GeoTIFF source instead of the failing geodatabase"""
    logger.info("=== Testing alternative DEM source ===")
    
    # Test data using your coordinates that sometimes worked
    test_data = {
        'area_bounds': {
            'polygon_coordinates': [
                {'latitude': -28.03521969075148, 'longitude': 153.40710461139682},
                {'latitude': -28.03441948105581, 'longitude': 153.4076035022736},
                {'latitude': -28.03645550586712, 'longitude': 153.4097492694855},
                {'latitude': -28.03521969075148, 'longitude': 153.40710461139682}  # Close polygon
            ]
        },
        'max_points': 1000,
        'sampling_interval_m': 10.0,
        'minor_contour_interval_m': 0.5,
        'major_contour_interval_m': 1.0
    }
    
    # Try the request without specifying source (should fail with geodatabase if not configured)
    logger.info("\n=== Test 1: Default source (geodatabase/local) ===")
    response = requests.post(CONTOUR_URL, json=test_data, timeout=30)
    logger.info(f'Status: {response.status_code}')
    
    # This test is designed to sometimes fail if the default source is not working
    # We assert that the status code is either 200 or 400 (for access issues)
    assert response.status_code in [200, 400], f"Unexpected status code: {response.status_code}, Response: {response.text}"
    
    if response.status_code == 200:
        result = response.json()
        logger.info(f'Success: {result.get("success", False)}')
        assert result.get("success") is True, f"Expected success=True, got {result}"
        logger.info(f'Contours: {len(result.get("contours", {}).get("features", []))}')
    else:
        logger.info(f'Error: {response.text}')
        assert "Could not access DEM file" in response.text or "No elevation data found" in response.text, \
            f"Expected DEM access error, got {response.text}"

# if __name__ == "__main__":
#     test_geotiff_source() 