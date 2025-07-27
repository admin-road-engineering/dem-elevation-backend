"""Campaign API endpoints for survey campaign visualization."""

import logging
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional

from ....models.campaign_models import (
    CampaignData, CampaignQuery, CampaignResponse, CampaignFilters,
    CampaignClusterResponse, Bounds, DataType, Provider
)
from ....services.campaign_service import campaign_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


async def get_campaign_service():
    """Dependency to get initialized campaign service."""
    if campaign_service._campaigns_list is None:
        await campaign_service.initialize()
    return campaign_service


@router.get("", response_model=CampaignResponse)
async def get_campaigns(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page"),
    include_files: bool = Query(False, description="Include file details"),
    include_geometry: bool = Query(False, description="Include GeoJSON geometry"),
    
    # Spatial filtering
    min_lat: Optional[float] = Query(None, description="Minimum latitude"),
    max_lat: Optional[float] = Query(None, description="Maximum latitude"),
    min_lon: Optional[float] = Query(None, description="Minimum longitude"),
    max_lon: Optional[float] = Query(None, description="Maximum longitude"),
    
    # Data filtering
    data_types: Optional[List[DataType]] = Query(None, description="Filter by data types"),
    providers: Optional[List[Provider]] = Query(None, description="Filter by providers"),
    min_resolution: Optional[float] = Query(None, description="Minimum resolution in meters"),
    max_resolution: Optional[float] = Query(None, description="Maximum resolution in meters"),
    regions: Optional[List[str]] = Query(None, description="Filter by geographic regions"),
    
    service = Depends(get_campaign_service)
):
    """
    Get paginated list of survey campaigns with optional filtering.
    
    Supports spatial filtering, data type filtering, and pagination.
    """
    try:
        # Build bounds if provided
        bbox = None
        if all(v is not None for v in [min_lat, max_lat, min_lon, max_lon]):
            bbox = Bounds(
                min_lat=min_lat,
                max_lat=max_lat,
                min_lon=min_lon,
                max_lon=max_lon
            )
        
        # Build filters
        filters = None
        if any([data_types, providers, min_resolution, max_resolution, regions]):
            filters = CampaignFilters(
                data_types=data_types,
                providers=providers,
                min_resolution=min_resolution,
                max_resolution=max_resolution,
                regions=regions
            )
        
        # Create query
        query = CampaignQuery(
            bbox=bbox,
            filters=filters,
            page=page,
            page_size=page_size,
            include_files=include_files,
            include_geometry=include_geometry
        )
        
        # Get campaigns
        response = await service.get_campaigns(query)
        
        logger.info(f"Retrieved {len(response.campaigns)} campaigns (page {page})")
        return response
        
    except Exception as e:
        logger.error(f"Failed to get campaigns: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve campaigns: {str(e)}")


@router.get("/{campaign_id}", response_model=CampaignData)
async def get_campaign_by_id(
    campaign_id: str,
    include_files: bool = Query(True, description="Include file details"),
    include_geometry: bool = Query(True, description="Include GeoJSON geometry"),
    service = Depends(get_campaign_service)
):
    """
    Get detailed information about a specific campaign.
    
    Returns complete campaign data including files and geometry if requested.
    """
    try:
        campaign = await service.get_campaign_by_id(
            campaign_id, 
            include_files=include_files,
            include_geometry=include_geometry
        )
        
        if not campaign:
            raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} not found")
        
        logger.info(f"Retrieved campaign {campaign_id}")
        return campaign
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve campaign: {str(e)}")


@router.get("/in-bounds", response_model=List[CampaignData])
async def get_campaigns_in_bounds(
    min_lat: float = Query(..., description="Minimum latitude"),
    max_lat: float = Query(..., description="Maximum latitude"),
    min_lon: float = Query(..., description="Minimum longitude"),
    max_lon: float = Query(..., description="Maximum longitude"),
    include_geometry: bool = Query(False, description="Include GeoJSON geometry"),
    service = Depends(get_campaign_service)
):
    """
    Get campaigns that intersect with the specified bounding box.
    
    Optimized for map viewport queries with spatial indexing.
    """
    try:
        # Validate bounds
        if min_lat >= max_lat or min_lon >= max_lon:
            raise HTTPException(status_code=400, detail="Invalid bounding box coordinates")
        
        bounds = Bounds(
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon
        )
        
        campaigns = await service.get_campaigns_in_bounds(bounds, include_geometry=include_geometry)
        
        logger.info(f"Found {len(campaigns)} campaigns in bounds")
        return campaigns
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get campaigns in bounds: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve campaigns: {str(e)}")


@router.get("/clusters", response_model=CampaignClusterResponse)
async def get_campaign_clusters(
    min_lat: float = Query(..., description="Minimum latitude"),
    max_lat: float = Query(..., description="Maximum latitude"),
    min_lon: float = Query(..., description="Minimum longitude"),
    max_lon: float = Query(..., description="Maximum longitude"),
    zoom_level: int = Query(..., ge=0, le=18, description="Map zoom level"),
    service = Depends(get_campaign_service)
):
    """
    Get campaign clusters optimized for the specified zoom level.
    
    Returns clustered campaigns for performance at low zoom levels,
    individual campaigns at high zoom levels.
    """
    try:
        # Validate bounds
        if min_lat >= max_lat or min_lon >= max_lon:
            raise HTTPException(status_code=400, detail="Invalid bounding box coordinates")
        
        bounds = Bounds(
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon
        )
        
        clusters = await service.get_campaign_clusters(bounds, zoom_level)
        
        logger.info(f"Generated {len(clusters.clusters)} clusters for zoom level {zoom_level}")
        return clusters
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get campaign clusters: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve clusters: {str(e)}")


@router.post("/query", response_model=CampaignResponse)
async def query_campaigns(
    query: CampaignQuery,
    service = Depends(get_campaign_service)
):
    """
    Advanced campaign query with full filtering capabilities.
    
    Supports complex filtering combinations and pagination.
    """
    try:
        response = await service.get_campaigns(query)
        
        logger.info(f"Query returned {len(response.campaigns)} campaigns")
        return response
        
    except Exception as e:
        logger.error(f"Failed to query campaigns: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to query campaigns: {str(e)}")


@router.get("/stats/summary")
async def get_campaign_stats(service = Depends(get_campaign_service)):
    """
    Get summary statistics about available campaigns.
    
    Returns counts by data type, provider, resolution, and geographic coverage.
    """
    try:
        if not service._campaigns_list:
            await service.initialize()
        
        campaigns = service._campaigns_list
        
        # Calculate statistics
        stats = {
            "total_campaigns": len(campaigns),
            "total_files": sum(c.file_count for c in campaigns),
            "data_types": {},
            "providers": {},
            "resolutions": {},
            "regions": {},
            "coverage": {
                "min_lat": min(c.bounds.min_lat for c in campaigns) if campaigns else 0,
                "max_lat": max(c.bounds.max_lat for c in campaigns) if campaigns else 0,
                "min_lon": min(c.bounds.min_lon for c in campaigns) if campaigns else 0,
                "max_lon": max(c.bounds.max_lon for c in campaigns) if campaigns else 0
            }
        }
        
        # Count by categories
        for campaign in campaigns:
            # Data types
            data_type = campaign.data_type.value
            stats["data_types"][data_type] = stats["data_types"].get(data_type, 0) + 1
            
            # Providers
            provider = campaign.provider.value
            stats["providers"][provider] = stats["providers"].get(provider, 0) + 1
            
            # Resolutions
            resolution = f"{campaign.resolution_m}m"
            stats["resolutions"][resolution] = stats["resolutions"].get(resolution, 0) + 1
            
            # Regions
            region = campaign.geographic_region
            stats["regions"][region] = stats["regions"].get(region, 0) + 1
        
        logger.info("Generated campaign statistics")
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get campaign stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve statistics: {str(e)}")


@router.get("/health")
async def campaign_health_check(service = Depends(get_campaign_service)):
    """
    Health check for campaign service.
    
    Returns service status and data availability.
    """
    try:
        if not service._campaigns_list:
            await service.initialize()
        
        health_info = {
            "status": "healthy",
            "campaigns_loaded": len(service._campaigns_list) if service._campaigns_list else 0,
            "spatial_index_ready": bool(service._spatial_index),
            "service": "Campaign API",
            "version": "1.0.0"
        }
        
        return health_info
        
    except Exception as e:
        logger.error(f"Campaign health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "service": "Campaign API",
            "version": "1.0.0"
        }