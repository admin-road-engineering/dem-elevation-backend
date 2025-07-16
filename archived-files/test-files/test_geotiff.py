#!/usr/bin/env python3
"""Test script to verify GeoTIFF DEM source is working"""

import requests
import json
import time

def test_dem_backend():
    """Test the DEM Backend with GeoTIFF source"""
    base_url = "http://localhost:8001"
    
    print("Testing DEM Backend with GeoTIFF source...")
    
    # Test 1: Health check
    try:
        response = requests.get(f"{base_url}/")
        print(f"[OK] Health check: {response.status_code}")
        if response.status_code == 200:
            print(f"   Service info: {response.json()}")
    except Exception as e:
        print(f"[ERROR] Health check failed: {e}")
        return False
    
    # Test 2: Check available sources
    try:
        response = requests.get(f"{base_url}/api/v1/elevation/sources")
        print(f"[OK] Sources check: {response.status_code}")
        if response.status_code == 200:
            sources = response.json()
            print(f"   Available sources: {list(sources.keys())}")
            print(f"   Default source: {sources.get('default_source', 'Not set')}")
    except Exception as e:
        print(f"[ERROR] Sources check failed: {e}")
        return False
    
    # Test 3: Test elevation query
    test_coord = {"latitude": -27.4698, "longitude": 153.0251}
    try:
        response = requests.post(
            f"{base_url}/api/v1/elevation/point",
            json=test_coord,
            headers={"Content-Type": "application/json"}
        )
        print(f"[OK] Elevation query: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"   Elevation: {result.get('elevation_m', 'N/A')}m")
            print(f"   Source: {result.get('source', 'Unknown')}")
        else:
            print(f"   Error: {response.text}")
    except Exception as e:
        print(f"[ERROR] Elevation query failed: {e}")
        return False
    
    print("\nAll tests completed!")
    return True

if __name__ == "__main__":
    # Wait a moment for server to be ready
    time.sleep(2)
    test_dem_backend()