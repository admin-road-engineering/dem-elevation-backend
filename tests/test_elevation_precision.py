import requests
import json
import numpy as np
from pyproj import Geod
import logging
import pytest # Import pytest

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration for your DEM service
DEM_SERVICE_URL = "http://localhost:8001"

# Gold Coast coordinates (multiple test points)
TEST_COORDINATES = [
    (-28.0023731, 153.4145987, "Surfers Paradise"),
    (-28.0050000, 153.4100000, "Gold Coast City"),
    (-28.0100000, 153.4200000, "Broadbeach"),
    (-28.0200000, 153.4300000, "Burleigh Heads"),
    (-27.9900000, 153.4000000, "Southport")
]

# Define start and end points for the precision test using TEST_COORDINATES
START_LAT, START_LNG, _ = TEST_COORDINATES[0]
END_LAT, END_LNG, _ = TEST_COORDINATES[1]

def generate_line_points(start_lat, start_lng, end_lat, end_lng, spacing_meters=0.1):
    """Generates points along a line at a specified spacing in meters."""
    geod = Geod(ellps='WGS84')
    # Calculate the geodesic line between start and end
    lonlats = geod.npts(start_lng, start_lat, end_lng, end_lat, 2) # Get two points first to measure total distance
    
    # Recalculate with proper spacing
    az12, az21, dist = geod.inv(start_lng, start_lat, end_lng, end_lat)
    num_points = int(dist / spacing_meters) + 1
    lonlats = geod.npts(start_lng, start_lat, end_lng, end_lat, num_points)
    
    points = []
    for lon, lat in lonlats:
        points.append({"latitude": lat, "longitude": lon})
    return points

def test_elevation_precision():
    """Test the precision of elevation data along a very short line segment."""
    logger.info("=== Testing Elevation Precision ===")
    
    # Generate a very short line with high density of points (e.g., 10 cm spacing)
    test_points = generate_line_points(START_LAT, START_LNG, END_LAT, END_LNG, spacing_meters=0.1)
    
    payload = {
        "points": test_points
    }
    
    logger.info(f"Querying {len(test_points)} points along a line.")
    
    response = requests.post(f"{DEM_SERVICE_URL}/api/v1/elevation/path", json=payload)
    
    assert response.status_code == 200, f"API request failed with status {response.status_code}: {response.text}"
    
    data = response.json()
    logger.info(f"Response data: {json.dumps(data, indent=2)}")
    path_elevations = data.get('path_elevations')
    
    assert path_elevations is not None and len(path_elevations) > 0, "No path elevations returned."
    
    elevations = [p['elevation_m'] for p in path_elevations if p['elevation_m'] is not None]
    
    assert len(elevations) > 0, "No valid elevations received for analysis"
    
    # Calculate statistical properties of elevations
    min_elev = np.min(elevations)
    max_elev = np.max(elevations)
    avg_elev = np.mean(elevations)
    std_dev = np.std(elevations)
    
    logger.info(f"Total points queried: {len(test_points)}")
    logger.info(f"Points with elevation data: {len(elevations)}")
    logger.info(f"Elevation Range: {min_elev:.2f}m - {max_elev:.2f}m")
    logger.info(f"Average Elevation: {avg_elev:.2f}m")
    logger.info(f"Standard Deviation: {std_dev:.4f}m")
    
    # Define a reasonable tolerance for elevation variation over a short distance
    # For a flat-ish area, std dev should be very small. For varied terrain, more. 
    # This is a general test, so setting a moderate threshold.
    tolerance = 0.5  # meters. Adjust based on expected terrain characteristics
    
    assert std_dev < tolerance, f"Elevation precision issue: Standard deviation ({std_dev:.4f}m) exceeds tolerance ({tolerance}m)"
    logger.info("✅ Elevation precision test passed! Standard deviation is within acceptable limits.")

# The main function is no longer needed for pytest
# if __name__ == "__main__":
#     test_elevation_precision() 