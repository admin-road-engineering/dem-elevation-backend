import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from typing import Dict, Any, List, Optional

from ...config import Settings
from ...dem_service import DEMService
from ...dem_exceptions import DEMCoordinateError, DEMServiceError
from ...dependencies import get_dem_service, get_contour_service, get_dataset_manager, get_elevation_service
from ...dataset_manager import DatasetManager
from ...contour_service import ContourService
from ...unified_elevation_service import UnifiedElevationService
from ...auth import get_current_user
from ...models import (
    PointRequest, LineRequest, PathRequest, ContourDataRequest,
    PointResponse, LineResponse, PathResponse, ContourDataResponse,
    LegacyContourDataResponse, GeoJSONFeatureCollection, ContourStatistics,
    DEMPoint, ErrorResponse, SourceSelectionRequest, SourceSelectionResponse,
    # Enhanced response models with structured resolution fields
    EnhancedPointResponse, EnhancedLineResponse, EnhancedPathResponse,
    # Frontend-specific models
    FrontendContourDataRequest, FrontendContourDataResponse,
    # New standardized models
    StandardCoordinate, PointsRequest, LineRequest_Standard, PathRequest_Standard,
    StandardElevationResult, StandardMetadata, StandardResponse, StandardErrorResponse,
    StandardErrorDetail
)
# Import campaigns models
from ...models.api_campaign_models import CampaignSummary, CampaignDetails, CampaignsResult

logger = logging.getLogger(__name__)

# Create rate limiter for endpoints
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/v1/elevation", tags=["elevation"])

@router.get("", summary="Get elevation for a single point via query parameters")
@limiter.limit("60/minute")  # Generous for S3, restrictive for API abuse  
async def get_elevation_simple(
    request: Request,
    lat: float,
    lon: float, 
    source_id: Optional[str] = None,
    service: DEMService = Depends(get_dem_service)
) -> Dict[str, Any]:
    """Get elevation for a single point using simple query parameters.
    
    This is a simplified GET endpoint for basic elevation queries.
    For more advanced features, use the POST /point endpoint.
    """
    try:
        # Check for API fallback abuse (same logic as POST endpoint)
        if is_api_fallback_coordinate(lat, lon):
            # Apply stricter rate limiting for expensive API coordinates
            from slowapi.errors import RateLimitExceeded
            import time
            current_minute = int(time.time() // 60)
            rate_key = f"api_fallback:{get_remote_address(request)}:{current_minute}"
            
            # Simple in-memory rate limiting for API coordinates (10/minute)
            if not hasattr(get_elevation_simple, '_api_rate_cache'):
                get_elevation_simple._api_rate_cache = {}
            
            current_count = get_elevation_simple._api_rate_cache.get(rate_key, 0)
            if current_count >= 10:
                logger.warning(f"API fallback rate limit exceeded for {get_remote_address(request)}")
                raise HTTPException(
                    status_code=429, 
                    detail="Rate limit exceeded for non-Australian coordinates (10/minute). These coordinates require expensive API calls."
                )
            get_elevation_simple._api_rate_cache[rate_key] = current_count + 1
            
            # Clean old cache entries
            get_elevation_simple._api_rate_cache = {k: v for k, v in get_elevation_simple._api_rate_cache.items() 
                                                  if k.endswith(f":{current_minute}")}
        
        # Use unified elevation service
        result = await service.elevation_service.get_elevation(lat, lon, source_id)
        
        # Return enhanced JSON response with unit-explicit fields
        response_data = {
            "elevation_m": result.elevation_m,  # Unit-explicit for global app
            "latitude": lat,
            "longitude": lon,
            "dem_source_used": result.dem_source_used,  # Standard field name
            "message": result.message
        }
        
        # Add enhanced metadata fields if available
        if result.metadata:
            response_data["resolution_m"] = result.metadata.get("grid_resolution_m", 1.0)
            response_data["grid_resolution_m"] = result.metadata.get("grid_resolution_m", 1.0)
            response_data["data_type"] = result.metadata.get("data_type", "LiDAR")
            response_data["accuracy"] = result.metadata.get("accuracy", "±0.1m")
            
            # Include processing metadata for debugging
            if "processing_time_ms" in result.metadata:
                response_data["processing_time_ms"] = result.metadata["processing_time_ms"]
        else:
            # Default enhanced fields for consistent API
            response_data["resolution_m"] = 1.0
            response_data["grid_resolution_m"] = 1.0  
            response_data["data_type"] = "LiDAR"
            response_data["accuracy"] = "±0.1m"
        
        return response_data
        
    except DEMCoordinateError as e:
        logger.warning(f"Invalid coordinates in simple elevation: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid coordinates: {str(e)}")
    except DEMServiceError as e:
        logger.error(f"DEM service error in simple elevation: {e}")
        raise HTTPException(status_code=502, detail=f"Elevation service error: {str(e)}")
    except ValueError as e:
        logger.warning(f"ValueError in simple elevation: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in simple elevation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

def is_api_fallback_coordinate(lat: float, lon: float) -> bool:
    """Check if coordinates will likely trigger expensive API fallback"""
    # Australia/NZ bounds (S3 coverage)
    if (-47 <= lat <= -10 and 112 <= lon <= 179):
        return False  # S3 coverage, cheap
    # Ocean coordinates or international = API fallback
    return True

def _process_elevation_point(point_data):
    """Extract lat, lon, elevation from various data structures"""
    
    # Handle tuple/list
    if isinstance(point_data, (tuple, list)):
        if len(point_data) == 2:
            lat, lon = point_data
            return lat, lon, None  # Elevation to be fetched
        elif len(point_data) == 3:
            return point_data  # lat, lon, elevation
        else:
            raise ValueError(f"Expected 2 or 3 elements, got {len(point_data)}")
    
    # Handle dict/object
    elif isinstance(point_data, dict):
        lat = point_data.get('lat') or point_data.get('latitude')
        lon = point_data.get('lon') or point_data.get('longitude')
        elevation = point_data.get('elevation') or point_data.get('elevation_m')
        
        if lat is None or lon is None:
            raise ValueError(f"Missing lat/lon in dict: {list(point_data.keys())}")
        
        return lat, lon, elevation
    
    # Handle custom objects
    elif hasattr(point_data, 'lat') and hasattr(point_data, 'lon'):
        return point_data.lat, point_data.lon, getattr(point_data, 'elevation', None)
    elif hasattr(point_data, 'latitude') and hasattr(point_data, 'longitude'):
        return point_data.latitude, point_data.longitude, getattr(point_data, 'elevation_m', None)
    
    else:
        raise ValueError(f"Unsupported point data type: {type(point_data)}")

def create_error_response(status_code: int, message: str, details: Optional[str] = None) -> StandardErrorResponse:
    """Create a standardized error response."""
    return StandardErrorResponse(
        status="ERROR",
        error=StandardErrorDetail(
            code=status_code,
            message=message,
            details=details,
            timestamp=datetime.utcnow().isoformat() + "Z"
        )
    )

def raise_standard_http_exception(status_code: int, message: str, details: Optional[str] = None):
    """Raise an HTTPException with standardized error format."""
    error_response = create_error_response(status_code, message, details)
    raise HTTPException(status_code=status_code, detail=error_response.dict())

# Service dependencies are now managed by the dependency injection container
# See src/dependencies.py for service initialization and management

@router.get("/sources", summary="List available DEM sources")
async def list_dem_sources(
    service: DEMService = Depends(get_dem_service)
) -> Dict[str, Any]:
    """List all configured DEM sources with their basic information."""
    try:
        # Use the same Settings instance from ServiceContainer that other services use
        settings = service.settings
        sources_info = {}
        
        for source_id, source_config in settings.DEM_SOURCES.items():
            sources_info[source_id] = {
                "path": source_config["path"],
                "crs": source_config.get("crs"),
                "layer": source_config.get("layer"),
                "description": source_config.get("description"),
                "is_geodatabase": source_config["path"].lower().endswith('.gdb'),
                "is_default": source_id == settings.DEFAULT_DEM_ID,
                # Enhanced info for index-driven sources
                "source_type": source_config.get("source_type", "file"),
                "priority": source_config.get("priority", 3),
                "resolution_m": source_config.get("resolution_m"),
                "data_type": source_config.get("data_type"),
                "provider": source_config.get("provider"),
                "file_count": source_config.get("file_count"),
                "campaign_id": source_config.get("campaign_id"),
                "bounds": source_config.get("bounds"),
                "accuracy": source_config.get("accuracy"),
                "cost_per_query": source_config.get("cost_per_query")
            }
        
        # Add environment debug information
        import os
        s3_sources = [s for s in sources_info.values() if s.get('source_type') == 's3']
        api_sources = [s for s in sources_info.values() if s.get('source_type') == 'api']
        
        env_debug = {
            "USE_S3_SOURCES": getattr(settings, 'USE_S3_SOURCES', False),
            "USE_API_SOURCES": getattr(settings, 'USE_API_SOURCES', False),
            "SPATIAL_INDEX_SOURCE": os.getenv("SPATIAL_INDEX_SOURCE", "local"),
            "has_aws_credentials": bool(os.getenv("AWS_ACCESS_KEY_ID")),
            "has_gpxz_key": bool(os.getenv("GPXZ_API_KEY")),
            "railway_env": bool(os.getenv("RAILWAY_ENVIRONMENT")),
            "dem_sources_env_var": os.getenv("DEM_SOURCES", "not_set"),
            "index_driven_approach": True,
            "s3_campaign_count": len(s3_sources),
            "api_fallback_count": len(api_sources),
            "source_discovery_method": "spatial_index" if len(s3_sources) > 0 else "api_fallback"
        }
        
        # Add performance statistics for index-driven sources
        performance_stats = {
            "spatial_indexing_enabled": len(s3_sources) > 0,
            "campaign_based_selection": len(s3_sources) > 0,
            "expected_performance_improvement": "54,000x speedup for Brisbane area" if len(s3_sources) > 0 else "API fallback only",
            "selection_algorithm": "O(log N) spatial index" if len(s3_sources) > 0 else "linear fallback",
            "integration_status": "Index-driven approach active" if len(s3_sources) > 0 else "Legacy fallback mode"
        }
        
        return {
            "sources": sources_info,
            "default_source": settings.DEFAULT_DEM_ID,
            "total_sources": len(sources_info),
            "source_breakdown": {
                "s3_campaigns": len(s3_sources),
                "api_fallbacks": len(api_sources),
                "local_sources": len([s for s in sources_info.values() if s.get('source_type') not in ['s3', 'api']])
            },
            "performance_stats": performance_stats,
            "environment_debug": env_debug
        }
        
    except Exception as e:
        logger.error(f"Error listing DEM sources: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing sources: {str(e)}")

@router.get("/sources/{source_id}/info", summary="Get detailed information about a DEM source")
async def get_source_info(
    source_id: str,
    service: DEMService = Depends(get_dem_service)
) -> Dict[str, Any]:
    """Get detailed information about a specific DEM source."""
    try:
        # Use DEMService method directly (it's already lean and delegates to DatasetManager)
        info = service.get_source_info(source_id)
        
        if "error" in info:
            raise HTTPException(status_code=400, detail=info["error"])
        
        return info
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"ValueError getting source info for {source_id}: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error getting source info for {source_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/point", response_model=EnhancedPointResponse)
@limiter.limit("60/minute")  # Generous for S3, restrictive for API abuse
async def get_elevation_point(
    request: Request,
    point_request: PointRequest,
    service: DEMService = Depends(get_dem_service)
) -> EnhancedPointResponse:
    """Get elevation for a single point using the unified elevation service."""
    try:
        # Check for API fallback abuse (more restrictive rate limiting)
        if is_api_fallback_coordinate(point_request.latitude, point_request.longitude):
            # Apply stricter rate limiting for expensive API coordinates
            from slowapi.errors import RateLimitExceeded
            import time
            current_minute = int(time.time() // 60)
            rate_key = f"api_fallback:{get_remote_address(request)}:{current_minute}"
            
            # Simple in-memory rate limiting for API coordinates (10/minute)
            if not hasattr(get_elevation_point, '_api_rate_cache'):
                get_elevation_point._api_rate_cache = {}
            
            current_count = get_elevation_point._api_rate_cache.get(rate_key, 0)
            if current_count >= 10:
                logger.warning(f"API fallback rate limit exceeded for {get_remote_address(request)}")
                raise HTTPException(
                    status_code=429, 
                    detail="Rate limit exceeded for non-Australian coordinates (10/minute). These coordinates require expensive API calls."
                )
            get_elevation_point._api_rate_cache[rate_key] = current_count + 1
            
            # Clean old cache entries (keep only current minute)
            get_elevation_point._api_rate_cache = {k: v for k, v in get_elevation_point._api_rate_cache.items() 
                                                  if k.endswith(f":{current_minute}")}
        
        # Use the same approach as the working test endpoint
        result = await service.elevation_service.get_elevation(
            point_request.latitude,
            point_request.longitude,
            point_request.dem_source_id
        )
        
        # Create enhanced response with structured metadata
        return EnhancedPointResponse(
            latitude=point_request.latitude,
            longitude=point_request.longitude,
            elevation=result.elevation_m,  # Note: EnhancedPointResponse uses 'elevation', not 'elevation_m'
            dem_source_used=result.dem_source_used,
            resolution=result.resolution,
            grid_resolution_m=result.grid_resolution_m,
            data_type=result.data_type,
            accuracy=result.accuracy,
            message=result.message
        )
        
    except DEMCoordinateError as e:
        logger.warning(f"Invalid coordinates in point elevation: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid coordinates: {str(e)}")
    except DEMServiceError as e:
        logger.error(f"DEM service error in point elevation: {e}")
        raise HTTPException(status_code=502, detail=f"Elevation service error: {str(e)}")
    except ValueError as e:
        logger.warning(f"ValueError in point elevation: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in point elevation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/line", response_model=EnhancedLineResponse)
async def get_elevation_line(
    request: LineRequest,
    service: DEMService = Depends(get_dem_service)
) -> EnhancedLineResponse:
    """Get elevations for points along a line segment using unified elevation service."""
    try:
        # Use the new unified service for line elevation
        points, dem_source_used, message = await service.get_elevations_for_line_unified(
            request.start_point.latitude,
            request.start_point.longitude,
            request.end_point.latitude,
            request.end_point.longitude,
            request.num_points,
            request.dem_source_id
        )
        
        # Convert to response model
        line_points = []
        for point in points:
            line_points.append({
                "latitude": point["latitude"],
                "longitude": point["longitude"],
                "elevation_m": point["elevation_m"],
                "sequence": point["sequence"],
                "message": point["message"]
            })
        
        return LineResponse(
            points=line_points,
            dem_source_used=dem_source_used,
            message=message
        )
        
    except DEMCoordinateError as e:
        logger.warning(f"Invalid coordinates in line elevation: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid coordinates: {str(e)}")
    except DEMServiceError as e:
        logger.error(f"DEM service error in line elevation: {e}")
        raise HTTPException(status_code=502, detail=f"Elevation service error: {str(e)}")
    except ValueError as e:
        logger.warning(f"ValueError in line elevation: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in line elevation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/path", response_model=PathResponse)
@limiter.limit("20/minute")  # More restrictive for batch operations
async def get_elevation_path(
    request: Request,
    path_request: PathRequest,
    service: DEMService = Depends(get_dem_service)
) -> PathResponse:
    """Get elevations for a list of discrete points using unified elevation service."""
    try:
        if not path_request.points:
            raise HTTPException(status_code=400, detail="Points list cannot be empty")
        
        # Emergency protection: Limit path size to prevent API quota abuse  
        if len(path_request.points) > 100:
            raise HTTPException(status_code=400, detail="Maximum 100 points per path request to prevent API quota abuse")
        
        # Convert request points to dict format for service
        points_data = []
        for point in path_request.points:
            points_data.append({
                "latitude": point.latitude,
                "longitude": point.longitude,
                "id": point.id
            })
        
        # Use the new unified service for batch elevation
        elevations, dem_source_used, message = await service.get_elevations_for_path_unified(
            points_data,
            path_request.dem_source_id
        )
        
        # Convert to response model
        path_elevations = []
        for elev in elevations:
            path_elevations.append({
                "input_latitude": elev["input_latitude"],
                "input_longitude": elev["input_longitude"],
                "input_id": elev["input_id"],
                "elevation_m": elev["elevation_m"],
                "sequence": elev["sequence"],
                "message": elev["message"]
            })
        
        return PathResponse(
            path_elevations=path_elevations,
            dem_source_used=dem_source_used,
            message=message
        )
        
    except DEMCoordinateError as e:
        logger.warning(f"Invalid coordinates in path elevation: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid coordinates: {str(e)}")
    except DEMServiceError as e:
        logger.error(f"DEM service error in path elevation: {e}")
        raise HTTPException(status_code=502, detail=f"Elevation service error: {str(e)}")
    except ValueError as e:
        logger.warning(f"ValueError in path elevation: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in path elevation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/contour-data", response_model=FrontendContourDataResponse)
async def generate_contour_data(
    request: FrontendContourDataRequest,
    service: DEMService = Depends(get_dem_service)
) -> FrontendContourDataResponse:
    """
    Generate grid elevation data for contour generation within a polygon area.
    
    This endpoint returns native DEM points as a grid for frontend contour processing,
    matching the exact format expected by the main backend's contour service.
    """
    import traceback
    
    logger.info(f"=== Starting contour data generation ===")
    logger.info(f"Request data: {request.dict()}")
    
    try:
        if not request.area_bounds.polygon_coordinates:
            raise HTTPException(status_code=400, detail="Polygon coordinates cannot be empty")
        
        if len(request.area_bounds.polygon_coordinates) < 3:
            raise HTTPException(status_code=400, detail="Polygon must have at least 3 coordinates")
        
        # Convert coordinates to the format expected by the service
        polygon_coords = [(coord.latitude, coord.longitude) for coord in request.area_bounds.polygon_coordinates]
        logger.info(f"Converted polygon coordinates: {polygon_coords}")
        logger.info(f"Source: {request.source or 'auto'}")
        
        # Use DEMService delegation method (which calls ContourService internally)
        logger.info("Calling service.get_dem_points_in_polygon...")
        dem_points, dem_source_used, error_message = service.get_dem_points_in_polygon(
            polygon_coords,
            request.source or "auto",
            50000  # max_points
        )
        
        logger.info(f"Service call completed:")
        logger.info(f"  dem_points type: {type(dem_points)}")
        logger.info(f"  dem_points length: {len(dem_points) if dem_points else 'None'}")
        logger.info(f"  dem_source_used: {dem_source_used}")
        logger.info(f"  error_message: {error_message}")
        
        if error_message:
            logger.error(f"Service returned error: {error_message}")
            raise HTTPException(status_code=400, detail=error_message)
        
        if not dem_points:
            logger.error("No elevation points generated")
            raise HTTPException(status_code=400, detail="No elevation points could be generated for the specified area")
        
        # Convert to response model format with enhanced error handling
        response_points = []
        for i, point in enumerate(dem_points):
            try:
                logger.debug(f"Processing point {i}: {point}")
                
                # Flexible point data handling
                point_data = _process_elevation_point(point)
                lat, lon, elevation = point_data
                
                response_points.append(DEMPoint(
                    latitude=lat,
                    longitude=lon,
                    elevation_m=elevation,
                    x_crs=point.get("x_crs", lon),
                    y_crs=point.get("y_crs", lat)
                ))
                
            except Exception as e:
                logger.error(f"Failed to process point {i}: {type(e).__name__}: {e}")
                logger.error(f"Point data: {repr(point)}")
                continue
        
        logger.info(f"Successfully processed {len(response_points)} points")
        
        return FrontendContourDataResponse(
            status="OK",
            dem_points=response_points,
            total_points=len(response_points),
            dem_source_used=dem_source_used,
            grid_info={},  # Empty grid info for backward compatibility
            crs="EPSG:4326",
            message="Contour data generated successfully."
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"=== Contour ValueError ===")
        logger.error(f"Error message: {e}")
        logger.error(f"Full traceback:")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"=== Contour Unexpected Error ===")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error message: {e}")
        logger.error(f"Full traceback:")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/contour-data/geojson", response_model=ContourDataResponse)
async def generate_geojson_contour_data(
    request: ContourDataRequest,
    contour_service: ContourService = Depends(get_contour_service)
) -> ContourDataResponse:
    """
    Generate GeoJSON contour lines from DEM data within a polygon area using ContourService.
    
    This endpoint generates server-side contour lines as GeoJSON features that can be
    directly displayed on the frontend map, eliminating browser memory issues.
    """
    try:
        if not request.area_bounds.polygon_coordinates:
            raise HTTPException(status_code=400, detail="Polygon coordinates cannot be empty")
        
        if len(request.area_bounds.polygon_coordinates) < 3:
            raise HTTPException(status_code=400, detail="Polygon must have at least 3 coordinates")
        
        # Convert coordinates to the format expected by the service
        polygon_coords = [(coord.latitude, coord.longitude) for coord in request.area_bounds.polygon_coordinates]
        
        # Use ContourService directly for contour generation
        geojson_contours, statistics, dem_source_used, error_message = contour_service.generate_geojson_contours(
            polygon_coords=polygon_coords,
            dem_source_id=request.dem_source_id or "auto",
            max_points=request.max_points,
            minor_contour_interval_m=request.minor_contour_interval_m,
            major_contour_interval_m=request.major_contour_interval_m,
            simplify_tolerance=request.sampling_interval_m / 1000.0  # Convert to degrees approximately
        )
        
        if error_message:
            raise HTTPException(status_code=400, detail=error_message)
        
        if not geojson_contours or not statistics:
            raise HTTPException(status_code=400, detail="No contours could be generated for the specified area")
        
        # Convert to response model format
        contours = GeoJSONFeatureCollection(**geojson_contours)
        stats = ContourStatistics(**statistics)
        
        return ContourDataResponse(
            success=True,
            contours=contours,
            statistics=stats,
            area_bounds=request.area_bounds,
            dem_source_used=dem_source_used,
            crs="EPSG:4326",
            message=f"Successfully generated {stats.contour_count} contour lines from {stats.total_points} elevation points"
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"ValueError in contour data generation: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in contour data generation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/contour-data/legacy", response_model=LegacyContourDataResponse)
async def generate_legacy_contour_data(
    request: ContourDataRequest,
    service: DEMService = Depends(get_dem_service)
) -> LegacyContourDataResponse:
    """
    Legacy endpoint that returns raw DEM points for client-side contour generation.
    
    This endpoint maintains backward compatibility by returning the original format
    of native DEM points within the specified polygon area.
    """
    try:
        if not request.area_bounds.polygon_coordinates:
            raise HTTPException(status_code=400, detail="Polygon coordinates cannot be empty")
        
        if len(request.area_bounds.polygon_coordinates) < 3:
            raise HTTPException(status_code=400, detail="Polygon must have at least 3 coordinates")
        
        # Convert coordinates to the format expected by the service
        polygon_coords = [(coord.latitude, coord.longitude) for coord in request.area_bounds.polygon_coordinates]
        
        # Use DEMService delegation method (which calls ContourService internally)
        dem_points, dem_source_used, error_message = service.get_dem_points_in_polygon(
            polygon_coords,
            request.dem_source_id or "auto",
            request.max_points
        )
        
        if error_message:
            raise HTTPException(status_code=400, detail=error_message)
        
        # Convert to response model format
        response_points = []
        for point in dem_points:
            response_points.append(DEMPoint(**point))
        
        return LegacyContourDataResponse(
            dem_points=response_points,
            total_points=len(response_points),
            area_bounds=request.area_bounds,
            dem_source_used=dem_source_used,
            grid_info={},  # Empty grid info for backward compatibility
            crs="EPSG:4326",
            message=f"Successfully extracted {len(response_points)} native DEM points from polygon area"
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"ValueError in legacy contour data generation: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in legacy contour data generation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") 

@router.post("/select-source", response_model=SourceSelectionResponse)
async def select_best_source(
    request: SourceSelectionRequest,
    elevation_service: UnifiedElevationService = Depends(get_elevation_service),
    service: DEMService = Depends(get_dem_service)
) -> SourceSelectionResponse:
    """Select the best DEM source for a specific location using unified elevation service."""
    try:
        # Use the unified elevation service to get elevation and determine which source was used
        result = await elevation_service.get_elevation(request.latitude, request.longitude)
        best_source_id = result.dem_source_used
        
        # Create mock scores for backward compatibility (unified service handles selection internally)
        scores = [{
            "source_id": best_source_id,
            "score": 1.0,
            "within_bounds": True,
            "reason": "Selected by unified elevation service"
        }]
        
        # Get detailed info about the selected source
        source_info = service.get_source_info(best_source_id)
        
        # Get list of available sources for this location
        available_sources = [score["source_id"] for score in scores if score["within_bounds"]]
        
        # Generate selection reason
        best_score = next((score for score in scores if score["source_id"] == best_source_id), None)
        selection_reason = best_score["reason"] if best_score else "Default source"
        
        return SourceSelectionResponse(
            selected_source_id=best_source_id,
            selected_source_info=source_info,
            available_sources=available_sources,
            selection_reason=selection_reason
        )
        
    except ValueError as e:
        logger.error(f"ValueError in source selection: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in source selection: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/coverage", summary="Get coverage summary for all DEM sources")
async def get_coverage_summary(
    service: DEMService = Depends(get_dem_service)
) -> Dict[str, Any]:
    """Get a summary of coverage for all configured DEM sources."""
    try:
        # Use DEMService method directly (it's already lean and delegates appropriately)
        summary = service.get_coverage_summary()
        return summary
        
    except Exception as e:
        logger.error(f"Error getting coverage summary: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting coverage summary: {str(e)}")

@router.get("/internal-debug", summary="Debug service container state and settings objects")
async def internal_debug(service: DEMService = Depends(get_dem_service)) -> Dict[str, Any]:
    """Debug endpoint to diagnose service container state and settings object identity."""
    try:
        from ...dependencies import get_service_container
        from ...config import get_settings
        
        # Get global instances for comparison
        container = get_service_container()
        global_settings = get_settings()
        
        debug_info = {
            # Service State
            "service_settings_source_count": len(service.settings.DEM_SOURCES),
            "service_settings_object_id": id(service.settings),
            "elevation_service_type": type(service.elevation_service).__name__,
            "using_index_driven": getattr(service.elevation_service, 'using_index_driven_selector', False),
            "source_selector_type": type(service.elevation_service.source_selector).__name__ if hasattr(service.elevation_service, 'source_selector') else 'None',
            
            # Global State for Comparison  
            "global_settings_source_count": len(global_settings.DEM_SOURCES),
            "global_settings_object_id": id(global_settings),
            
            # Container State for Comparison
            "container_settings_object_id": id(container.settings),
            "container_service_object_id": id(container.dem_service),
            
            # Additional diagnosis
            "service_elevation_service_id": id(service.elevation_service),
            "container_elevation_service_id": id(container.elevation_service),
            "settings_objects_match": id(service.settings) == id(global_settings),
            "services_match": id(service) == id(container.dem_service),
            
            # S3 Source Analysis
            "s3_sources_in_service_settings": [k for k, v in service.settings.DEM_SOURCES.items() if v.get('source_type') == 's3'],
            "s3_sources_in_global_settings": [k for k, v in global_settings.DEM_SOURCES.items() if v.get('source_type') == 's3'],
        }
        
        return debug_info
        
    except Exception as e:
        logger.error(f"Error in internal debug endpoint: {e}", exc_info=True)
        return {"error": str(e), "error_type": type(e).__name__}

@router.get("/debug/source-selection", summary="Debug source selection configuration")
async def debug_source_selection(
    lat: float = -27.4698,
    lon: float = 153.0251,
    service: DEMService = Depends(get_dem_service)
) -> Dict[str, Any]:
    """
    Debug endpoint to show source selection configuration and process.
    This helps diagnose why attempted_sources might be empty.
    """
    try:
        logger.info(f"=== Debug Source Selection Endpoint Called ===")
        logger.info(f"Testing coordinates: ({lat}, {lon})")
        
        debug_info = {
            "request_coordinates": {"lat": lat, "lon": lon},
            "timestamp": datetime.utcnow().isoformat(),
            "service_info": {},
            "source_selection_debug": {},
            "elevation_attempt": {}
        }
        
        # Get service information
        if hasattr(service, 'elevation_service') and service.elevation_service:
            elevation_service = service.elevation_service
            debug_info["service_info"]["elevation_service_type"] = type(elevation_service).__name__
            
            # Check if it has an enhanced source selector
            if hasattr(elevation_service, 'source_selector'):
                selector = elevation_service.source_selector
                debug_info["service_info"]["source_selector_type"] = type(selector).__name__
                
                # Debug source selector configuration
                if hasattr(selector, 'config'):
                    debug_info["source_selection_debug"]["configured_sources"] = list(selector.config.keys())
                
                if hasattr(selector, 'use_s3'):
                    debug_info["source_selection_debug"]["use_s3"] = selector.use_s3
                
                if hasattr(selector, 'use_apis'):
                    debug_info["source_selection_debug"]["use_apis"] = selector.use_apis
                
                if hasattr(selector, 'campaign_selector'):
                    debug_info["source_selection_debug"]["campaign_selector_available"] = selector.campaign_selector is not None
                
                if hasattr(selector, 'gpxz_client'):
                    debug_info["source_selection_debug"]["gpxz_client_available"] = selector.gpxz_client is not None
                
                if hasattr(selector, 'google_client'):
                    debug_info["source_selection_debug"]["google_client_available"] = selector.google_client is not None
                
                # Check circuit breakers
                if hasattr(selector, 'circuit_breakers'):
                    cb_status = {}
                    for name, cb in selector.circuit_breakers.items():
                        cb_status[name] = {
                            "available": cb.is_available(),
                            "failures": cb.failure_count,
                            "threshold": cb.failure_threshold
                        }
                    debug_info["source_selection_debug"]["circuit_breakers"] = cb_status
        
        # Try to get elevation and capture the process
        try:
            logger.info("Attempting elevation query for debugging...")
            elevation, dem_source_used, message = await service.get_elevation_unified(lat, lon)
            
            debug_info["elevation_attempt"] = {
                "elevation_m": elevation,
                "dem_source_used": dem_source_used,
                "message": message,
                "success": elevation is not None
            }
            
        except Exception as e:
            debug_info["elevation_attempt"] = {
                "error": str(e),
                "error_type": type(e).__name__,
                "success": False
            }
        
        return debug_info
        
    except Exception as e:
        logger.error(f"Error in debug endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Debug endpoint error: {str(e)}")

# =============================================================================
# NEW STANDARDIZED API ENDPOINTS
# =============================================================================

@router.post("/points", response_model=StandardResponse, summary="Get elevations for multiple discrete coordinates")
@limiter.limit("10/minute")  # Most restrictive for bulk operations
async def get_elevation_points(
    request: Request,
    points_request: PointsRequest,
    service: DEMService = Depends(get_dem_service)
) -> StandardResponse:
    """Get elevations for multiple discrete coordinates (batch endpoint)."""
    try:
        if not points_request.points:
            raise HTTPException(status_code=400, detail="Points list cannot be empty")
        
        # Emergency protection: Limit batch size to prevent API quota abuse
        if len(points_request.points) > 50:
            raise HTTPException(status_code=400, detail="Maximum 50 points per batch request to prevent API quota abuse")
        
        # Convert to format expected by existing service
        points_data = []
        for i, point in enumerate(points_request.points):
            points_data.append({
                "latitude": point.lat,
                "longitude": point.lon,
                "id": i
            })
        
        # Use unified elevation service for batch processing
        elevations, dem_source_used, message = await service.get_elevations_for_path_unified(
            points_data,
            points_request.source
        )
        
        # Convert to standardized response format
        results = []
        successful_points = 0
        
        for elev in elevations:
            elevation_value = elev["elevation_m"]
            if elevation_value is not None:
                successful_points += 1
            
            results.append(StandardElevationResult(
                lat=elev["input_latitude"],
                lon=elev["input_longitude"],
                elevation=elevation_value,
                data_source=dem_source_used,
                resolution=1.0  # TODO: Get actual resolution from source
            ))
        
        metadata = StandardMetadata(
            total_points=len(results),
            successful_points=successful_points
        )
        
        return StandardResponse(
            results=results,
            metadata=metadata
        )
        
    except DEMCoordinateError as e:
        logger.warning(f"Invalid coordinates in points elevation: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid coordinates: {str(e)}")
    except DEMServiceError as e:
        logger.error(f"DEM service error in points elevation: {e}")
        raise HTTPException(status_code=502, detail=f"Elevation service error: {str(e)}")
    except ValueError as e:
        logger.warning(f"ValueError in points elevation: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in points elevation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Campaigns endpoints for unified spatial index
@router.get("/campaigns", response_model=CampaignsResult, summary="List available elevation data campaigns/collections")
async def list_campaigns(
    elevation_service: UnifiedElevationService = Depends(get_elevation_service)
) -> CampaignsResult:
    """
    List all available elevation data campaigns/collections grouped by country.
    
    Returns campaigns from the unified spatial index including:
    - Australian campaigns (1,394 collections)  
    - New Zealand campaigns (188 collections)
    - Campaign metadata, bounds, resolution, and file counts
    """
    try:
        from ...dem_exceptions import DEMServiceError, DEMSourceError
        from fastapi import status as http_status
        
        # Get collections from the unified provider
        if not hasattr(elevation_service, 'unified_provider') or not elevation_service.unified_provider:
            raise HTTPException(status_code=503, detail="Unified provider not available")
            
        unified_provider = elevation_service.unified_provider
        
        # The unified provider contains the UnifiedWGS84S3Source as elevation_source
        if not hasattr(unified_provider, 'elevation_source') or not unified_provider.elevation_source:
            raise HTTPException(status_code=503, detail="Elevation source not available")
            
        elevation_source = unified_provider.elevation_source
        
        # Handle both direct source and FallbackDataSource cases
        unified_s3_source = None
        if hasattr(elevation_source, 'unified_index') and elevation_source.unified_index:
            # Direct UnifiedWGS84S3Source
            unified_s3_source = elevation_source
        elif hasattr(elevation_source, 'sources'):
            # FallbackDataSource - find the UnifiedWGS84S3Source
            for source in elevation_source.sources:
                if hasattr(source, 'unified_index') and source.unified_index:
                    unified_s3_source = source
                    break
        
        if not unified_s3_source:
            raise HTTPException(status_code=503, detail="Unified S3 source not found")
            
        collections = unified_s3_source.unified_index.data_collections
        
        # Group by country
        campaigns_by_country = {}
        country_counts = {}
        
        for collection in collections:
            country = collection.country
            if country not in campaigns_by_country:
                campaigns_by_country[country] = []
                country_counts[country] = 0
            
            # Extract bounds as dictionary for API response
            bounds_dict = None
            if collection.coverage_bounds_wgs84:
                bounds_dict = {
                    "min_lat": collection.coverage_bounds_wgs84.min_lat,
                    "max_lat": collection.coverage_bounds_wgs84.max_lat,
                    "min_lon": collection.coverage_bounds_wgs84.min_lon,
                    "max_lon": collection.coverage_bounds_wgs84.max_lon
                }
            
            # Get survey year and name - different field names for AU vs NZ
            year = None
            name = collection.id  # fallback to ID
            if hasattr(collection, 'survey_year') and collection.survey_year:
                year = collection.survey_year
            if hasattr(collection, 'survey_years') and collection.survey_years:
                year = max(collection.survey_years)  # Use most recent year
            
            # Get collection name based on type
            if hasattr(collection, 'campaign_name'):
                name = collection.campaign_name
            elif hasattr(collection, 'survey_name'):
                name = collection.survey_name
            
            campaign_summary = CampaignSummary(
                id=collection.id,
                name=name,
                country=country,
                region=getattr(collection, 'region', None),
                year=year,
                file_count=collection.file_count,
                data_type=collection.data_type,
                resolution_m=collection.resolution_m,
                bounds=bounds_dict,
                crs=collection.native_crs
            )
            campaigns_by_country[country].append(campaign_summary)
            country_counts[country] += 1
        
        return CampaignsResult(
            total_campaigns=len(collections),
            campaigns_by_country=campaigns_by_country,
            country_summary=country_counts,
            status="success"
        )
        
    except DEMSourceError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DEMServiceError as e:
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error listing campaigns: {e}")
        logger.error(f"Traceback: {error_details}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/campaigns/{campaign_id}", response_model=CampaignDetails, summary="Get detailed campaign information")
async def get_campaign_details(
    campaign_id: str,
    file_page: int = 1,
    file_limit: int = 10,
    elevation_service: UnifiedElevationService = Depends(get_elevation_service)
) -> CampaignDetails:
    """
    Get detailed information about a specific elevation data campaign.
    
    Parameters:
    - campaign_id: Unique identifier for the campaign
    - file_page: Page number for file listings (default: 1)
    - file_limit: Number of files per page (default: 10, max: 100)
    
    Returns campaign details including:
    - Campaign metadata and bounds
    - Paginated list of files with bounds and metadata
    - Total file count and pagination info
    """
    try:
        from ...dem_exceptions import DEMServiceError, DEMSourceError
        from fastapi import status as http_status
        
        # Get specific collection from the unified provider
        if not hasattr(elevation_service, 'unified_provider') or not elevation_service.unified_provider:
            raise HTTPException(status_code=503, detail="Unified provider not available")
            
        unified_provider = elevation_service.unified_provider
        
        # The unified provider contains the UnifiedWGS84S3Source as elevation_source
        if not hasattr(unified_provider, 'elevation_source') or not unified_provider.elevation_source:
            raise HTTPException(status_code=503, detail="Elevation source not available")
            
        elevation_source = unified_provider.elevation_source
        
        # Handle both direct source and FallbackDataSource cases
        unified_s3_source = None
        if hasattr(elevation_source, 'unified_index') and elevation_source.unified_index:
            # Direct UnifiedWGS84S3Source
            unified_s3_source = elevation_source
        elif hasattr(elevation_source, 'sources'):
            # FallbackDataSource - find the UnifiedWGS84S3Source
            for source in elevation_source.sources:
                if hasattr(source, 'unified_index') and source.unified_index:
                    unified_s3_source = source
                    break
        
        if not unified_s3_source:
            raise HTTPException(status_code=503, detail="Unified S3 source not found")
            
        collections = unified_s3_source.unified_index.data_collections
        
        # Find the specific collection by ID
        collection = None
        for coll in collections:
            if coll.id == campaign_id:
                collection = coll
                break
        
        if not collection:
            raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} not found")
        
        files = collection.files
        
        # Paginate files
        start_idx = (file_page - 1) * file_limit
        end_idx = start_idx + file_limit
        paginated_files = files[start_idx:end_idx]
        
        # Create FileInfo objects
        file_info_list = []
        for file_entry in paginated_files:
            # Convert file size from MB to bytes
            size_bytes = int(file_entry.size_mb * 1024 * 1024) if file_entry.size_mb else 0
            
            # Extract bounds as dictionary for API response
            bounds_dict = {
                "min_lat": file_entry.bounds.min_lat,
                "max_lat": file_entry.bounds.max_lat,
                "min_lon": file_entry.bounds.min_lon,
                "max_lon": file_entry.bounds.max_lon
            } if file_entry.bounds else {}
            
            file_info = FileInfo(
                filename=file_entry.filename,
                file_path=file_entry.file,
                bounds=bounds_dict,
                size_bytes=size_bytes
            )
            file_info_list.append(file_info)
        
        # Extract bounds as dictionary for API response
        bounds_dict = None
        if collection.coverage_bounds_wgs84:
            bounds_dict = {
                "min_lat": collection.coverage_bounds_wgs84.min_lat,
                "max_lat": collection.coverage_bounds_wgs84.max_lat,
                "min_lon": collection.coverage_bounds_wgs84.min_lon,
                "max_lon": collection.coverage_bounds_wgs84.max_lon
            }
        
        # Get survey year and name - different field names for AU vs NZ  
        year = None
        name = collection.id  # fallback to ID
        if hasattr(collection, 'survey_year') and collection.survey_year:
            year = collection.survey_year
        if hasattr(collection, 'survey_years') and collection.survey_years:
            year = max(collection.survey_years)  # Use most recent year
            
        # Get collection name based on type
        if hasattr(collection, 'campaign_name'):
            name = collection.campaign_name
        elif hasattr(collection, 'survey_name'):
            name = collection.survey_name
        
        return CampaignDetails(
            id=collection.id,
            name=name,
            country=collection.country,
            region=getattr(collection, 'region', None),
            year=year,
            file_count=collection.file_count,
            data_type=collection.data_type,
            resolution_m=collection.resolution_m,
            bounds=bounds_dict,
            crs=collection.native_crs,
            files=file_info_list,
            files_truncated=len(files) > end_idx,
            total_files=len(files)
        )
        
    except DEMSourceError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DEMServiceError as e:
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error getting campaign details for {campaign_id}: {e}")
        logger.error(f"Traceback: {error_details}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")