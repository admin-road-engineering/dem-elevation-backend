import os
import logging
import requests
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# DEM Backend Service Configuration (Primary source)
DEM_SERVICE_URL = os.getenv("DEM_SERVICE_URL", "http://localhost:8001")
DEM_SERVICE_TIMEOUT = int(os.getenv("DEM_SERVICE_TIMEOUT", "30"))
DEM_SOURCE_ID = os.getenv("DEM_SOURCE_ID", "local_dtm_gdb")

# Google Elevation API Configuration (Fallback)
GOOGLE_ELEVATION_API_KEY = os.getenv("GOOGLE_ELEVATION_API_KEY")
GOOGLE_ELEVATION_API_URL = 'https://maps.googleapis.com/maps/api/elevation/json'

async def fetch_elevations_from_dem_service(points: List[Dict[str, float]], dem_source_id: str = None) -> List[Optional[Dict[str, Any]]]:
    """
    Fetches elevations from the local DEM elevation service using bulk endpoint.
    
    Args:
        points: List of dictionaries with 'lat' and 'lng' keys
        dem_source_id: Optional DEM source ID to use (defaults to configured default)
    
    Returns:
        List of elevation results or None for each point if failed
    """
    if not points:
        return []
        
    dem_source = dem_source_id or DEM_SOURCE_ID
    
    logger.info(f"Fetching {len(points)} elevations from DEM service at {DEM_SERVICE_URL} with bulk endpoint")
    
    try:
        # Prepare bulk request payload
        payload = {
            "points": points,
            "dem_source_id": dem_source
        }
        
        # Make bulk request to DEM service
        response = requests.post(
            f"{DEM_SERVICE_URL}/api/get_elevations",
            json=payload,
            timeout=DEM_SERVICE_TIMEOUT * 2  # Longer timeout for bulk requests
        )
        
        if response.status_code == 200:
            data = response.json()
            results = []
            
            # Process bulk response
            for result in data.get('results', []):
                elevation_result = {
                    'elevation': result.get('elevation'),
                    'lat': result.get('lat'),
                    'lng': result.get('lng'),
                    'source': 'dem_service',
                    'dem_source_id': result.get('dem_source_id'),
                    'message': result.get('message')
                }
                results.append(elevation_result if elevation_result['elevation'] is not None else None)
            
            successful_count = sum(1 for r in results if r is not None)
            logger.info(f"DEM service bulk endpoint returned {successful_count}/{len(points)} successful elevations")
            
            return results
            
        else:
            logger.warning(f"DEM service bulk endpoint returned status {response.status_code}")
            # Fallback to individual point requests if bulk fails
            return await fetch_elevations_from_dem_service_individual(points, dem_source_id)
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling DEM service bulk endpoint: {e}")
        # Fallback to individual point requests
        return await fetch_elevations_from_dem_service_individual(points, dem_source_id)
    except Exception as e:
        logger.error(f"Unexpected error calling DEM service bulk endpoint: {e}")
        # Fallback to individual point requests
        return await fetch_elevations_from_dem_service_individual(points, dem_source_id)

async def fetch_elevations_from_dem_service_individual(points: List[Dict[str, float]], dem_source_id: str = None) -> List[Optional[Dict[str, Any]]]:
    """
    Fallback method: Fetches elevations from the local DEM elevation service one by one.
    
    Args:
        points: List of dictionaries with 'lat' and 'lng' keys
        dem_source_id: Optional DEM source ID to use (defaults to configured default)
    
    Returns:
        List of elevation results or None for each point if failed
    """
    if not points:
        return []
        
    dem_source = dem_source_id or DEM_SOURCE_ID
    results = []
    
    logger.info(f"Fetching {len(points)} elevations from DEM service using individual point requests (fallback)")
    
    for point in points:
        try:
            # Prepare request payload
            payload = {
                "latitude": point['lat'],
                "longitude": point['lng']
            }
            
            # Add DEM source if specified
            if dem_source:
                payload["dem_source_id"] = dem_source
            
            # Make request to DEM service
            response = requests.post(
                f"{DEM_SERVICE_URL}/api/v1/elevation/point",
                json=payload,
                timeout=DEM_SERVICE_TIMEOUT
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Convert to format compatible with existing code
                elevation_result = {
                    'elevation': result.get('elevation_m'),
                    'lat': point['lat'],
                    'lng': point['lng'],
                    'source': 'dem_service',
                    'dem_source_id': result.get('dem_source_used'),
                    'crs': result.get('crs'),
                    'message': result.get('message')
                }
                
                results.append(elevation_result)
                logger.debug(f"DEM service returned elevation {result.get('elevation_m')}m for {point['lat']}, {point['lng']}")
                
            else:
                logger.warning(f"DEM service returned status {response.status_code} for point {point}")
                results.append(None)
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling DEM service for point {point}: {e}")
            results.append(None)
        except Exception as e:
            logger.error(f"Unexpected error calling DEM service for point {point}: {e}")
            results.append(None)
    
    successful_count = sum(1 for r in results if r is not None)
    logger.info(f"DEM service individual requests returned {successful_count}/{len(points)} successful elevations")
    
    return results

async def fetch_elevations_from_google_api(points: List[Dict[str, float]]) -> List[Optional[Dict[str, Any]]]:
    """
    Fetches elevations from Google Elevation API (fallback method).
    
    Args:
        points: List of dictionaries with 'lat' and 'lng' keys
    
    Returns:
        List of elevation results or None for each point if failed
    """
    if not GOOGLE_ELEVATION_API_KEY:
        logger.warning("Google Elevation API key not configured, skipping Google API fallback")
        return [None] * len(points)
    
    if not points:
        return []
    
    logger.info(f"Fetching {len(points)} elevations from Google Elevation API")
    
    try:
        # Prepare locations parameter for Google API
        locations = '|'.join([f"{point['lat']},{point['lng']}" for point in points])
        
        params = {
            'locations': locations,
            'key': GOOGLE_ELEVATION_API_KEY
        }
        
        response = requests.get(GOOGLE_ELEVATION_API_URL, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('status') == 'OK':
            results = []
            for i, result in enumerate(data.get('results', [])):
                elevation_result = {
                    'elevation': result.get('elevation'),
                    'lat': result['location']['lat'],
                    'lng': result['location']['lng'],
                    'source': 'google_api',
                    'resolution': result.get('resolution')
                }
                results.append(elevation_result)
            
            logger.info(f"Google API returned {len(results)} elevations successfully")
            return results
        else:
            logger.error(f"Google Elevation API error: {data.get('status')} - {data.get('error_message', 'Unknown error')}")
            return [None] * len(points)
            
    except Exception as e:
        logger.error(f"Error fetching elevations from Google API: {e}")
        return [None] * len(points)

async def fetch_elevations_hybrid(points: List[Dict[str, float]], dem_source_id: str = None) -> List[Dict[str, Any]]:
    """
    Fetches elevations using hybrid approach: DEM service first, Google API as fallback.
    
    Args:
        points: List of dictionaries with 'lat' and 'lng' keys
        dem_source_id: Optional specific DEM source to use
    
    Returns:
        List of elevation results with source information
    """
    if not points:
        return []
    
    logger.info(f"Starting hybrid elevation fetch for {len(points)} points")
    
    # Try DEM service first
    dem_results = await fetch_elevations_from_dem_service(points, dem_source_id)
    
    # Identify failed points for Google API fallback
    failed_points = []
    failed_indices = []
    
    for i, result in enumerate(dem_results):
        if result is None or result.get('elevation') is None:
            failed_points.append(points[i])
            failed_indices.append(i)
    
    # Use Google API for failed points
    google_results = []
    if failed_points:
        logger.info(f"Using Google API fallback for {len(failed_points)} failed points")
        google_results = await fetch_elevations_from_google_api(failed_points)
    
    # Combine results
    final_results = []
    google_index = 0
    
    for i, dem_result in enumerate(dem_results):
        if dem_result is not None and dem_result.get('elevation') is not None:
            # Use DEM service result
            final_results.append(dem_result)
        else:
            # Use Google API result if available
            if google_index < len(google_results) and google_results[google_index] is not None:
                final_results.append(google_results[google_index])
            else:
                # No elevation data available from either source
                final_results.append({
                    'elevation': None,
                    'lat': points[i]['lat'],
                    'lng': points[i]['lng'],
                    'source': 'none',
                    'error': 'No elevation data available from any source'
                })
            google_index += 1
    
    # Log summary
    dem_count = sum(1 for r in final_results if r.get('source') == 'dem_service')
    google_count = sum(1 for r in final_results if r.get('source') == 'google_api')
    failed_count = sum(1 for r in final_results if r.get('source') == 'none')
    
    logger.info(f"Elevation fetch complete: {dem_count} from DEM service, {google_count} from Google API, {failed_count} failed")
    
    return final_results

def fetch_route_polyline(start_point: Dict, end_point: Dict) -> Optional[List[Tuple[float, float]]]:
    """
    Fetches a route polyline from the OSRM demo server.

    Args:
        start_point: Dictionary with 'lat' and 'lng' keys for the start.
        end_point: Dictionary with 'lat' and 'lng' keys for the end.

    Returns:
        A list of (longitude, latitude) tuples representing the route polyline,
        or None if the route fetching fails.

    NOTE: Uses the public OSRM demo server (router.project-osrm.org),
          which is NOT suitable for production use due to usage limits and
          lack of reliability guarantees. Consider self-hosting OSRM or using
          a commercial routing provider for production applications.
    """
    logger.info(f"Fetching route between {start_point} and {end_point} using OSRM demo server...")

    # Format coordinates for OSRM URL: {longitude},{latitude};{longitude},{latitude}
    coords = f"{start_point['lng']},{start_point['lat']};{end_point['lng']},{end_point['lat']}"
    
    # Construct the URL for the OSRM route service
    # - overview=full: requests the most detailed geometry
    # - geometries=geojson: specifies the format for the geometry
    url = f"http://router.project-osrm.org/route/v1/driving/{coords}?overview=full&geometries=geojson"
    logger.debug(f"OSRM request URL: {url}")

    try:
        # Make the HTTP GET request with a timeout
        response = requests.get(url, timeout=15)
        response.raise_for_status()

        # Parse the JSON response
        data = response.json()
        
        # Check if the request was successful
        if data.get('code') != 'Ok':
            logger.error(f"OSRM API error: {data.get('message', 'Unknown error')}")
            return None

        # Extract the route geometry
        routes = data.get('routes', [])
        if not routes:
            logger.error("No routes found in OSRM response")
            return None

        # Get the first route's geometry
        geometry = routes[0].get('geometry', {})
        coordinates = geometry.get('coordinates', [])

        if not coordinates:
            logger.error("No coordinates found in route geometry")
            return None

        # Convert to list of (longitude, latitude) tuples
        # Note: OSRM returns [longitude, latitude] format
        route_points = [(coord[0], coord[1]) for coord in coordinates]
        
        logger.info(f"Successfully fetched route with {len(route_points)} points")
        logger.debug(f"Route distance: {routes[0].get('distance', 'unknown')}m, "
                    f"duration: {routes[0].get('duration', 'unknown')}s")
        
        return route_points

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching route from OSRM: {e}")
        return None
    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"Error parsing OSRM response: {e}")
        return None

# Main elevation function - USES HYBRID APPROACH BY DEFAULT
async def fetch_elevations(points: List[Dict[str, float]], use_dem_only: bool = False, use_google_only: bool = False) -> List[Dict[str, Any]]:
    """
    Main elevation fetching function with flexible source selection.
    
    Args:
        points: List of dictionaries with 'lat' and 'lng' keys
        use_dem_only: If True, only use DEM service (no Google fallback)
        use_google_only: If True, only use Google API
    
    Returns:
        List of elevation results with source information
    """
    
    if use_google_only:
        logger.info("Using Google API only")
        google_results = await fetch_elevations_from_google_api(points)
        return [result if result is not None else {
            'elevation': None,
            'lat': points[i]['lat'],
            'lng': points[i]['lng'],
            'source': 'google_api_failed',
            'error': 'Google API returned no data'
        } for i, result in enumerate(google_results)]
        
    elif use_dem_only:
        logger.info("Using DEM service only")
        dem_results = await fetch_elevations_from_dem_service(points)
        return [result if result is not None else {
            'elevation': None,
            'lat': points[i]['lat'],
            'lng': points[i]['lng'],
            'source': 'dem_service_failed',
            'error': 'DEM service returned no data'
        } for i, result in enumerate(dem_results)]
        
    else:
        # Default: Use hybrid approach (DEM first, Google fallback)
        logger.info("Using hybrid approach (DEM + Google fallback)")
        return await fetch_elevations_hybrid(points)

# Convenience functions for specific use cases
async def fetch_elevations_dem_priority(points: List[Dict[str, float]]) -> List[Dict[str, Any]]:
    """Convenience function that explicitly uses the hybrid approach."""
    return await fetch_elevations_hybrid(points)

async def fetch_elevations_dem_only(points: List[Dict[str, float]]) -> List[Dict[str, Any]]:
    """Convenience function that only uses DEM service."""
    return await fetch_elevations(points, use_dem_only=True)

async def fetch_elevations_google_only(points: List[Dict[str, float]]) -> List[Dict[str, Any]]:
    """Convenience function that only uses Google API."""
    return await fetch_elevations(points, use_google_only=True) 