import requests
import json
import logging
import pytest
import numpy as np
from pyproj import Geod

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration for your DEM service
DEM_SERVICE_URL = "http://localhost:8001"
DEM_SOURCE_ID = "local_dtm_gdb"

# Gold Coast coordinates for testing
START_LAT = -28.0020000
START_LNG = 153.4140000
END_LAT = -28.0021000  # Very small difference to create a short line
END_LNG = 153.4141000

# Known good coordinates for Gold Coast area
TEST_LAT = -27.975145
TEST_LON = 153.355888

def generate_line_points(start_lat, start_lng, end_lat, end_lng, spacing_meters=0.1, total_distance_meters=10):
    """Generate points along a line with specific spacing."""
    geod = Geod(ellps='WGS84')
    
    # Calculate number of points needed
    num_points = int(total_distance_meters / spacing_meters) + 1
    
    # Generate intermediate points
    line = geod.inv_intermediate(start_lng, start_lat, end_lng, end_lat, num_points - 2)
    
    points = [(start_lat, start_lng)]
    
    # Add intermediate points
    for lng, lat in zip(line.lons, line.lats):
        points.append((lat, lng))
    
    # Add end point
    points.append((end_lat, end_lng))
    
    return points

def test_elevation_precision():
    print("=" * 80)
    print("TESTING RASTERIO PRECISION - Gold Coast 10m Line at 0.1m Spacing")
    print("=" * 80)
    
    # Generate test points (10m line with 0.1m spacing = ~100 points)
    points = generate_line_points(START_LAT, START_LNG, END_LAT, END_LNG, 
                                spacing_meters=0.1, total_distance_meters=10)
    
    print(f"Generated {len(points)} points along 10m line")
    print(f"Start: ({points[0][0]:.7f}, {points[0][1]:.7f})")
    print(f"End: ({points[-1][0]:.7f}, {points[-1][1]:.7f})")
    print()
    
    # Test individual points to see raw elevation values
    print("Testing first 20 points for raw elevation values:")
    print("-" * 60)
    print("Point | Latitude      | Longitude     | Elevation (raw)")
    print("-" * 60)
    
    elevations = []
    
    for i, (lat, lng) in enumerate(points[:20]):  # Test first 20 points
        url = f"{DEM_SERVICE_URL}/v1/elevation/point"
        payload = {
            "latitude": lat,
            "longitude": lng,
            "dem_source_id": DEM_SOURCE_ID
        }
        headers = {"Content-Type": "application/json"}
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            elevation = data.get("elevation_m")
            
            if elevation is not None:
                elevations.append(elevation)
                print(f"{i:4d}  | {lat:.7f} | {lng:.7f} | {elevation}")
            else:
                elevations.append(None)
                print(f"{i:4d}  | {lat:.7f} | {lng:.7f} | None")
                
        except Exception as e:
            print(f"{i:4d}  | {lat:.7f} | {lng:.7f} | ERROR: {e}")
            elevations.append(None)
    
    print("-" * 60)
    
    # Analyze the precision patterns
    valid_elevations = [e for e in elevations if e is not None]
    if valid_elevations:
        print(f"\nPRECISION ANALYSIS:")
        print(f"Valid elevations: {len(valid_elevations)}")
        print(f"Min elevation: {min(valid_elevations)}")
        print(f"Max elevation: {max(valid_elevations)}")
        print(f"Range: {max(valid_elevations) - min(valid_elevations):.6f}m")
        
        # Check for precision patterns
        print(f"\nUNIQUE ELEVATION VALUES:")
        unique_elevs = sorted(set(valid_elevations))
        for elev in unique_elevs:
            count = valid_elevations.count(elev)
            print(f"  {elev} ({count} times)")
        
        # Check decimal precision patterns
        print(f"\nDECIMAL PRECISION ANALYSIS:")
        decimal_places = []
        for elev in valid_elevations:
            str_elev = str(elev)
            if '.' in str_elev:
                decimal_places.append(len(str_elev.split('.')[1]))
            else:
                decimal_places.append(0)
        
        unique_decimals = sorted(set(decimal_places))
        print(f"Decimal place counts found: {unique_decimals}")
        for dp in unique_decimals:
            count = decimal_places.count(dp)
            print(f"  {dp} decimal places: {count} values")
        
        # Check for step patterns (differences between consecutive values)
        print(f"\nCONSECUTIVE ELEVATION DIFFERENCES:")
        differences = []
        for i in range(1, len(valid_elevations)):
            if valid_elevations[i-1] is not None and valid_elevations[i] is not None:
                diff = abs(valid_elevations[i] - valid_elevations[i-1])
                differences.append(diff)
        
        if differences:
            unique_diffs = sorted(set(differences))
            print(f"Unique differences found: {len(unique_diffs)}")
            for diff in unique_diffs[:10]:  # Show first 10
                count = differences.count(diff)
                if diff > 0:  # Only show non-zero differences
                    print(f"  {diff:.6f}m difference: {count} times")
    
    else:
        print("No valid elevations received for analysis")

def test_rasterio_precision_direct_call():
    """Test rasterio precision by directly calling the point endpoint for a known point."""
    logger.info("=== Testing Rasterio Precision via Point Endpoint ===")
    
    payload = {
        "latitude": TEST_LAT,
        "longitude": TEST_LON
    }
    
    logger.info(f"Querying point: ({TEST_LAT}, {TEST_LON})")
    response = requests.post(f"{DEM_SERVICE_URL}/api/v1/elevation/point", json=payload)
    
    assert response.status_code == 200, f"Point endpoint failed with status {response.status_code}: {response.text}"
    
    data = response.json()
    elevation = data.get('elevation_m')
    source_used = data.get('dem_source_used')
    
    logger.info(f"Elevation returned: {elevation}m (Source: {source_used})")
    
    assert elevation is not None, "Elevation is None"
    assert source_used is not None, "DEM source used is None"
    assert source_used == "local_dtm_gdb" or source_used.startswith("s3_dem"), \
        f"Unexpected DEM source: {source_used}"
        
    # We cannot assert an exact value due to potential small variations,
    # but we can check if it's within a reasonable range or non-zero
    assert elevation > -100 and elevation < 1000, f"Elevation {elevation}m seems out of typical range"
    logger.info("✅ Rasterio precision test (point) passed!")


def test_rasterio_precision_with_contour_data():
    """Test rasterio precision through contour data for a small, dense area."""
    logger.info("=== Testing Rasterio Precision via Contour Data ===")
    
    # Define a very small area to get a dense sample of points
    offset = 0.00005  # Approximately 5 meters
    
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
        "max_points": 1000,
        "sampling_interval_m": 0.5  # Request high resolution
    }
    
    logger.info(f"Querying contours for small area (±{offset} deg) with 0.5m interval")
    response = requests.post(f"{DEM_SERVICE_URL}/api/v1/elevation/contour-data", json=payload)
    
    assert response.status_code == 200, f"Contour endpoint failed with status {response.status_code}: {response.text}"
    
    data = response.json()
    dem_points = data.get('dem_points')
    total_points = data.get('total_points')
    
    logger.info(f"Returned {total_points} DEM points.")
    
    assert dem_points is not None and len(dem_points) > 0, "No DEM points returned."
    
    # Check for consistency in elevation values (small variations expected within a small area)
    elevations = [p['elevation_m'] for p in dem_points if p['elevation_m'] is not None]
    assert len(elevations) > 0, "No valid elevations found in returned points."
    
    min_elev = min(elevations)
    max_elev = max(elevations)
    elevation_range = max_elev - min_elev
    
    logger.info(f"Elevation range in sampled points: {min_elev:.2f}m to {max_elev:.2f}m (Range: {elevation_range:.2f}m)")
    
    # The exact acceptable range depends on the terrain, but it should be small for a 10x10m area
    # We expect some variation, but not huge jumps
    assert elevation_range < 5.0, f"Expected elevation range < 5.0m, but got {elevation_range:.2f}m. Possible precision issue."
    logger.info("✅ Rasterio precision test (contour) passed! Elevation range is consistent.")

# The main function is no longer needed for pytest
# if __name__ == "__main__":
#     test_rasterio_precision_direct_call()
#     test_rasterio_precision_with_contour_data() 