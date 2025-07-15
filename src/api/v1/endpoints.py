import logging
from fastapi import APIRouter, HTTPException, Depends
from fastapi.concurrency import run_in_threadpool
from typing import Dict, Any, List, Optional

from src.config import Settings, get_settings
from src.dem_service import DEMService
from src.auth import get_current_user
from src.models import (
    PointRequest, LineRequest, PathRequest, ContourDataRequest,
    PointResponse, LineResponse, PathResponse, ContourDataResponse,
    LegacyContourDataResponse, GeoJSONFeatureCollection, ContourStatistics,
    DEMPoint, ErrorResponse, SourceSelectionRequest, SourceSelectionResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/elevation", tags=["elevation"])

# Global DEM service instance (initialized on startup)
dem_service: DEMService = None

def get_dem_service() -> DEMService:
    """Dependency to get the DEM service instance."""
    if dem_service is None:
        raise HTTPException(status_code=500, detail="DEM service not initialized")
    return dem_service

def init_dem_service(settings: Settings):
    """Initialize the global DEM service instance."""
    global dem_service
    try:
        dem_service = DEMService(settings)
        logger.info("DEM service initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize DEM service: {e}")
        raise e

@router.get("/sources", summary="List available DEM sources")
async def list_dem_sources(
    settings: Settings = Depends(get_settings)
) -> Dict[str, Any]:
    """List all configured DEM sources with their basic information."""
    try:
        sources_info = {}
        
        for source_id, source_config in settings.DEM_SOURCES.items():
            sources_info[source_id] = {
                "path": source_config["path"],
                "crs": source_config.get("crs"),
                "layer": source_config.get("layer"),
                "description": source_config.get("description"),
                "is_geodatabase": source_config["path"].lower().endswith('.gdb'),
                "is_default": source_id == settings.DEFAULT_DEM_ID
            }
        
        return {
            "sources": sources_info,
            "default_source": settings.DEFAULT_DEM_ID,
            "total_sources": len(sources_info)
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
        info = await run_in_threadpool(service.get_source_info, source_id)
        
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

@router.post("/point", response_model=PointResponse)
async def get_elevation_point(
    request: PointRequest,
    service: DEMService = Depends(get_dem_service),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user)
) -> PointResponse:
    """Get elevation for a single point."""
    try:
        # Run blocking DEM operations in thread pool
        elevation, dem_source_used, message = await run_in_threadpool(
            service.get_elevation_at_point,
            request.latitude,
            request.longitude,
            request.dem_source_id
        )
        
        return PointResponse(
            latitude=request.latitude,
            longitude=request.longitude,
            elevation_m=elevation,
            dem_source_used=dem_source_used,
            message=message
        )
        
    except ValueError as e:
        logger.error(f"ValueError in point elevation: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in point elevation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/line", response_model=LineResponse)
async def get_elevation_line(
    request: LineRequest,
    service: DEMService = Depends(get_dem_service)
) -> LineResponse:
    """Get elevations for points along a line segment."""
    try:
        # Run blocking DEM operations in thread pool
        points, dem_source_used, message = await run_in_threadpool(
            service.get_elevations_for_line,
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
        
    except ValueError as e:
        logger.error(f"ValueError in line elevation: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in line elevation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/path", response_model=PathResponse)
async def get_elevation_path(
    request: PathRequest,
    service: DEMService = Depends(get_dem_service)
) -> PathResponse:
    """Get elevations for a list of discrete points."""
    try:
        if not request.points:
            raise HTTPException(status_code=400, detail="Points list cannot be empty")
        
        # Convert request points to dict format for service
        points_data = []
        for point in request.points:
            points_data.append({
                "latitude": point.latitude,
                "longitude": point.longitude,
                "id": point.id
            })
        
        # Run blocking DEM operations in thread pool
        elevations, dem_source_used, message = await run_in_threadpool(
            service.get_elevations_for_path,
            points_data,
            request.dem_source_id
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
        
    except ValueError as e:
        logger.error(f"ValueError in path elevation: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in path elevation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/contour-data", response_model=ContourDataResponse)
async def generate_contour_data(
    request: ContourDataRequest,
    service: DEMService = Depends(get_dem_service)
) -> ContourDataResponse:
    """
    Generate GeoJSON contour lines from DEM data within a polygon area.
    
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
        
        # Run blocking DEM operations in thread pool to generate GeoJSON contours
        geojson_contours, statistics, dem_source_used, error_message = await run_in_threadpool(
            service.generate_geojson_contours,
            polygon_coords,
            request.max_points,
            request.sampling_interval_m,
            request.minor_contour_interval_m,
            request.major_contour_interval_m,
            request.dem_source_id
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
        
        # Run blocking DEM operations in thread pool
        dem_points, grid_info, dem_source_used, error_message = await run_in_threadpool(
            service.get_dem_points_in_polygon,
            polygon_coords,
            request.max_points,
            request.sampling_interval_m,
            request.dem_source_id
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
            grid_info=grid_info,
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
    service: DEMService = Depends(get_dem_service)
) -> SourceSelectionResponse:
    """Select the best DEM source for a specific location."""
    try:
        best_source_id, scores = await run_in_threadpool(
            service.select_best_source_for_point,
            request.latitude,
            request.longitude,
            request.prefer_high_resolution,
            request.max_resolution_m
        )
        
        # Get detailed info about the selected source
        source_info = await run_in_threadpool(service.get_source_info, best_source_id)
        
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
        summary = await run_in_threadpool(service.get_coverage_summary)
        return summary
        
    except Exception as e:
        logger.error(f"Error getting coverage summary: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting coverage summary: {str(e)}") 