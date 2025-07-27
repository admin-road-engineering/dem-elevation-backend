"""Campaign service for managing survey campaign data."""

import json
import logging
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union
import asyncio
from functools import lru_cache

from ..models.campaign_models import (
    CampaignData, CampaignFilters, CampaignQuery, CampaignResponse,
    CampaignCluster, CampaignClusterResponse, Bounds, GeoJSONGeometry,
    DataType, Provider, CampaignMetadata, CampaignFile
)

logger = logging.getLogger(__name__)


class CampaignService:
    """Service for managing survey campaign data."""
    
    def __init__(self):
        self._campaigns_data: Optional[Dict] = None
        self._campaigns_list: Optional[List[CampaignData]] = None
        self._spatial_index: Optional[Dict] = None
        
    async def initialize(self):
        """Initialize campaign service with data loading."""
        await self._load_campaign_data()
        self._build_spatial_index()
        
    async def _load_campaign_data(self):
        """Load campaign data from index file."""
        try:
            # Try config directory first, fallback to deploy config
            config_paths = [
                Path("config/phase3_campaign_populated_index.json"),
                Path("deploy_config/phase3_campaign_populated_index.json")
            ]
            
            campaign_file = None
            for path in config_paths:
                if path.exists():
                    campaign_file = path
                    break
                    
            if not campaign_file:
                raise FileNotFoundError("Campaign index file not found")
                
            with open(campaign_file, 'r') as f:
                self._campaigns_data = json.load(f)
                
            # Convert to campaign data models
            self._campaigns_list = []
            datasets = self._campaigns_data.get("datasets", {})
            
            for campaign_id, campaign_info in datasets.items():
                try:
                    campaign = self._convert_to_campaign_data(campaign_id, campaign_info)
                    self._campaigns_list.append(campaign)
                except Exception as e:
                    logger.warning(f"Failed to process campaign {campaign_id}: {e}")
                    continue
                    
            logger.info(f"Loaded {len(self._campaigns_list)} campaigns")
            
        except Exception as e:
            logger.error(f"Failed to load campaign data: {e}")
            self._campaigns_data = {"datasets": {}}
            self._campaigns_list = []
    
    def _convert_to_campaign_data(self, campaign_id: str, campaign_info: Dict) -> CampaignData:
        """Convert raw campaign data to CampaignData model."""
        bounds_data = campaign_info.get("bounds", {})
        bounds = Bounds(
            min_lat=bounds_data.get("min_lat", 0),
            max_lat=bounds_data.get("max_lat", 0),
            min_lon=bounds_data.get("min_lon", 0),
            max_lon=bounds_data.get("max_lon", 0)
        )
        
        # Extract metadata
        metadata_raw = campaign_info.get("metadata", {})
        metadata = CampaignMetadata(
            capture_method=metadata_raw.get("capture_method", "Unknown"),
            vertical_datum=metadata_raw.get("vertical_datum", "Unknown")
        )
        
        # Convert files if present
        files = None
        if "files" in campaign_info and campaign_info["files"]:
            files = []
            for file_info in campaign_info["files"]:
                file_bounds_data = file_info.get("bounds", {})
                file_bounds = Bounds(
                    min_lat=file_bounds_data.get("min_lat", 0),
                    max_lat=file_bounds_data.get("max_lat", 0),
                    min_lon=file_bounds_data.get("min_lon", 0),
                    max_lon=file_bounds_data.get("max_lon", 0)
                )
                
                campaign_file = CampaignFile(
                    key=file_info.get("key", ""),
                    filename=file_info.get("filename", ""),
                    bounds=file_bounds
                )
                files.append(campaign_file)
        
        # Parse data type
        data_type_str = campaign_info.get("data_type", "LiDAR")
        try:
            data_type = DataType(data_type_str)
        except ValueError:
            data_type = DataType.LIDAR
            
        # Parse provider
        provider_str = campaign_info.get("provider", "Elvis")
        try:
            provider = Provider(provider_str)
        except ValueError:
            provider = Provider.ELVIS
        
        # Generate campaign year from campaign_year or name
        campaign_year = campaign_info.get("campaign_year")
        if not campaign_year and campaign_info.get("name"):
            # Try to extract year from name
            import re
            year_match = re.search(r'(20\d{2})', campaign_info["name"])
            if year_match:
                campaign_year = year_match.group(1)
        
        # Generate start/end dates from campaign year
        start_date = None
        end_date = None
        if campaign_year:
            start_date = f"{campaign_year}-01-01T00:00:00Z"
            end_date = f"{campaign_year}-12-31T23:59:59Z"
        
        return CampaignData(
            id=campaign_id,
            name=campaign_info.get("name", campaign_id),
            provider=provider,
            data_type=data_type,
            resolution_m=campaign_info.get("resolution_m", 1.0),
            bounds=bounds,
            start_date=start_date,
            end_date=end_date,
            geographic_region=campaign_info.get("geographic_region", "unknown"),
            file_count=campaign_info.get("file_count", len(files) if files else 0),
            accuracy=campaign_info.get("accuracy"),
            campaign_year=campaign_year,
            metadata=metadata,
            files=files
        )
    
    def _build_spatial_index(self):
        """Build spatial index for efficient bounds queries."""
        if not self._campaigns_list:
            self._spatial_index = {}
            return
            
        # Simple grid-based spatial index
        self._spatial_index = {
            "campaigns": {},
            "grid_size": 1.0  # 1 degree grid cells
        }
        
        for campaign in self._campaigns_list:
            # Calculate grid cells that campaign overlaps
            bounds = campaign.bounds
            min_grid_x = int(bounds.min_lon // self._spatial_index["grid_size"])
            max_grid_x = int(bounds.max_lon // self._spatial_index["grid_size"])
            min_grid_y = int(bounds.min_lat // self._spatial_index["grid_size"])
            max_grid_y = int(bounds.max_lat // self._spatial_index["grid_size"])
            
            for grid_x in range(min_grid_x, max_grid_x + 1):
                for grid_y in range(min_grid_y, max_grid_y + 1):
                    grid_key = f"{grid_x},{grid_y}"
                    if grid_key not in self._spatial_index["campaigns"]:
                        self._spatial_index["campaigns"][grid_key] = []
                    self._spatial_index["campaigns"][grid_key].append(campaign.id)
    
    async def get_campaigns(self, query: CampaignQuery) -> CampaignResponse:
        """Get campaigns with filtering and pagination."""
        if not self._campaigns_list:
            await self.initialize()
        
        # Apply filters
        filtered_campaigns = self._apply_filters(self._campaigns_list, query)
        
        # Apply spatial filtering if bbox provided
        if query.bbox:
            filtered_campaigns = self._filter_by_bounds(filtered_campaigns, query.bbox)
        
        # Calculate pagination
        total_count = len(filtered_campaigns)
        start_idx = (query.page - 1) * query.page_size
        end_idx = start_idx + query.page_size
        page_campaigns = filtered_campaigns[start_idx:end_idx]
        
        # Generate geometry if requested
        if query.include_geometry:
            for campaign in page_campaigns:
                campaign.geometry = await self._generate_campaign_geometry(campaign)
        
        # Include files if requested
        if not query.include_files:
            for campaign in page_campaigns:
                campaign.files = None
        
        return CampaignResponse(
            campaigns=page_campaigns,
            total_count=total_count,
            page=query.page,
            page_size=query.page_size,
            has_next=end_idx < total_count
        )
    
    async def get_campaign_by_id(self, campaign_id: str, include_files: bool = True, include_geometry: bool = True) -> Optional[CampaignData]:
        """Get specific campaign by ID."""
        if not self._campaigns_list:
            await self.initialize()
        
        campaign = next((c for c in self._campaigns_list if c.id == campaign_id), None)
        if not campaign:
            return None
        
        # Generate geometry if requested
        if include_geometry:
            campaign.geometry = await self._generate_campaign_geometry(campaign)
        
        # Include files if requested
        if not include_files:
            campaign.files = None
        
        return campaign
    
    async def get_campaigns_in_bounds(self, bounds: Bounds, include_geometry: bool = False) -> List[CampaignData]:
        """Get campaigns that intersect with given bounds."""
        if not self._campaigns_list:
            await self.initialize()
        
        # Use spatial index for efficiency
        candidate_campaigns = self._get_candidates_from_spatial_index(bounds)
        
        # Filter by exact bounds intersection
        intersecting_campaigns = []
        for campaign in candidate_campaigns:
            if self._bounds_intersect(campaign.bounds, bounds):
                if include_geometry:
                    campaign.geometry = await self._generate_campaign_geometry(campaign)
                intersecting_campaigns.append(campaign)
        
        return intersecting_campaigns
    
    async def get_campaign_clusters(self, bounds: Bounds, zoom_level: int) -> CampaignClusterResponse:
        """Get campaign clusters for performance optimization."""
        campaigns_in_bounds = await self.get_campaigns_in_bounds(bounds)
        
        # Simple clustering based on zoom level
        if zoom_level >= 11:
            # High zoom - no clustering
            clusters = []
            for campaign in campaigns_in_bounds:
                cluster = CampaignCluster(
                    id=campaign.id,
                    center_lat=(campaign.bounds.min_lat + campaign.bounds.max_lat) / 2,
                    center_lon=(campaign.bounds.min_lon + campaign.bounds.max_lon) / 2,
                    campaign_count=1,
                    bounds=campaign.bounds,
                    zoom_level=zoom_level
                )
                clusters.append(cluster)
        else:
            # Low zoom - cluster campaigns
            clusters = self._cluster_campaigns(campaigns_in_bounds, zoom_level)
        
        return CampaignClusterResponse(
            clusters=clusters,
            zoom_level=zoom_level,
            total_campaigns=len(campaigns_in_bounds)
        )
    
    def _apply_filters(self, campaigns: List[CampaignData], query: CampaignQuery) -> List[CampaignData]:
        """Apply filtering criteria to campaigns."""
        if not query.filters:
            return campaigns
        
        filtered = campaigns
        filters = query.filters
        
        # Filter by data types
        if filters.data_types:
            filtered = [c for c in filtered if c.data_type in filters.data_types]
        
        # Filter by resolution
        if filters.min_resolution is not None:
            filtered = [c for c in filtered if c.resolution_m >= filters.min_resolution]
        if filters.max_resolution is not None:
            filtered = [c for c in filtered if c.resolution_m <= filters.max_resolution]
        
        # Filter by providers
        if filters.providers:
            filtered = [c for c in filtered if c.provider in filters.providers]
        
        # Filter by regions
        if filters.regions:
            filtered = [c for c in filtered if c.geographic_region in filters.regions]
        
        return filtered
    
    def _filter_by_bounds(self, campaigns: List[CampaignData], bounds: Bounds) -> List[CampaignData]:
        """Filter campaigns by bounding box intersection."""
        return [c for c in campaigns if self._bounds_intersect(c.bounds, bounds)]
    
    def _bounds_intersect(self, bounds1: Bounds, bounds2: Bounds) -> bool:
        """Check if two bounding boxes intersect."""
        return not (
            bounds1.max_lon < bounds2.min_lon or
            bounds1.min_lon > bounds2.max_lon or
            bounds1.max_lat < bounds2.min_lat or
            bounds1.min_lat > bounds2.max_lat
        )
    
    def _get_candidates_from_spatial_index(self, bounds: Bounds) -> List[CampaignData]:
        """Get candidate campaigns from spatial index."""
        if not self._spatial_index or not self._campaigns_list:
            return self._campaigns_list or []
        
        grid_size = self._spatial_index["grid_size"]
        candidate_ids = set()
        
        # Calculate grid cells that bounds overlaps
        min_grid_x = int(bounds.min_lon // grid_size)
        max_grid_x = int(bounds.max_lon // grid_size)
        min_grid_y = int(bounds.min_lat // grid_size)
        max_grid_y = int(bounds.max_lat // grid_size)
        
        for grid_x in range(min_grid_x, max_grid_x + 1):
            for grid_y in range(min_grid_y, max_grid_y + 1):
                grid_key = f"{grid_x},{grid_y}"
                if grid_key in self._spatial_index["campaigns"]:
                    candidate_ids.update(self._spatial_index["campaigns"][grid_key])
        
        # Return campaign objects
        campaigns_dict = {c.id: c for c in self._campaigns_list}
        return [campaigns_dict[cid] for cid in candidate_ids if cid in campaigns_dict]
    
    async def _generate_campaign_geometry(self, campaign: CampaignData) -> Optional[GeoJSONGeometry]:
        """Generate GeoJSON geometry from campaign file bounds."""
        if not campaign.files or len(campaign.files) == 0:
            # Fallback to campaign bounds as simple rectangle
            bounds = campaign.bounds
            coordinates = [[
                [bounds.min_lon, bounds.min_lat],
                [bounds.max_lon, bounds.min_lat],
                [bounds.max_lon, bounds.max_lat],
                [bounds.min_lon, bounds.max_lat],
                [bounds.min_lon, bounds.min_lat]
            ]]
            
            return GeoJSONGeometry(
                type="Polygon",
                coordinates=coordinates
            )
        
        # Generate geometry from file bounds using shapely
        try:
            polygons = []
            for file_info in campaign.files:
                bounds = file_info.bounds
                # Create polygon from file bounds
                coords = [
                    (bounds.min_lon, bounds.min_lat),
                    (bounds.max_lon, bounds.min_lat),
                    (bounds.max_lon, bounds.max_lat),
                    (bounds.min_lon, bounds.max_lat),
                    (bounds.min_lon, bounds.min_lat)
                ]
                polygons.append(Polygon(coords))
            
            # Union all polygons to create campaign boundary
            union_geom = unary_union(polygons)
            
            # Convert to GeoJSON format
            if isinstance(union_geom, Polygon):
                # Single polygon
                coordinates = [list(union_geom.exterior.coords)]
                return GeoJSONGeometry(type="Polygon", coordinates=coordinates)
            elif isinstance(union_geom, MultiPolygon):
                # Multiple polygons
                coordinates = []
                for poly in union_geom.geoms:
                    coordinates.append([list(poly.exterior.coords)])
                return GeoJSONGeometry(type="MultiPolygon", coordinates=coordinates)
                
        except Exception as e:
            logger.warning(f"Failed to generate geometry for campaign {campaign.id}: {e}")
            # Fallback to campaign bounds
            bounds = campaign.bounds
            coordinates = [[
                [bounds.min_lon, bounds.min_lat],
                [bounds.max_lon, bounds.min_lat],
                [bounds.max_lon, bounds.max_lat],
                [bounds.min_lon, bounds.max_lat],
                [bounds.min_lon, bounds.min_lat]
            ]]
            
            return GeoJSONGeometry(
                type="Polygon",
                coordinates=coordinates
            )
        
        return None
    
    def _cluster_campaigns(self, campaigns: List[CampaignData], zoom_level: int) -> List[CampaignCluster]:
        """Create campaign clusters based on zoom level."""
        if not campaigns:
            return []
        
        # Simple grid-based clustering
        grid_size = self._get_cluster_grid_size(zoom_level)
        clusters_dict = {}
        
        for campaign in campaigns:
            # Calculate grid cell for campaign center
            center_lat = (campaign.bounds.min_lat + campaign.bounds.max_lat) / 2
            center_lon = (campaign.bounds.min_lon + campaign.bounds.max_lon) / 2
            
            grid_x = int(center_lon // grid_size)
            grid_y = int(center_lat // grid_size)
            grid_key = f"{grid_x},{grid_y}"
            
            if grid_key not in clusters_dict:
                clusters_dict[grid_key] = {
                    "campaigns": [],
                    "bounds": {
                        "min_lat": float('inf'),
                        "max_lat": float('-inf'),
                        "min_lon": float('inf'),
                        "max_lon": float('-inf')
                    }
                }
            
            clusters_dict[grid_key]["campaigns"].append(campaign)
            
            # Update cluster bounds
            cluster_bounds = clusters_dict[grid_key]["bounds"]
            cluster_bounds["min_lat"] = min(cluster_bounds["min_lat"], campaign.bounds.min_lat)
            cluster_bounds["max_lat"] = max(cluster_bounds["max_lat"], campaign.bounds.max_lat)
            cluster_bounds["min_lon"] = min(cluster_bounds["min_lon"], campaign.bounds.min_lon)
            cluster_bounds["max_lon"] = max(cluster_bounds["max_lon"], campaign.bounds.max_lon)
        
        # Convert to cluster objects
        clusters = []
        for i, (grid_key, cluster_data) in enumerate(clusters_dict.items()):
            cluster_bounds = cluster_data["bounds"]
            center_lat = (cluster_bounds["min_lat"] + cluster_bounds["max_lat"]) / 2
            center_lon = (cluster_bounds["min_lon"] + cluster_bounds["max_lon"]) / 2
            
            cluster = CampaignCluster(
                id=f"cluster_{zoom_level}_{grid_key}",
                center_lat=center_lat,
                center_lon=center_lon,
                campaign_count=len(cluster_data["campaigns"]),
                bounds=Bounds(
                    min_lat=cluster_bounds["min_lat"],
                    max_lat=cluster_bounds["max_lat"],
                    min_lon=cluster_bounds["min_lon"],
                    max_lon=cluster_bounds["max_lon"]
                ),
                zoom_level=zoom_level
            )
            clusters.append(cluster)
        
        return clusters
    
    def _get_cluster_grid_size(self, zoom_level: int) -> float:
        """Get appropriate grid size for clustering based on zoom level."""
        # Larger grid for lower zoom levels
        if zoom_level <= 6:
            return 5.0  # 5 degree grid
        elif zoom_level <= 8:
            return 2.0  # 2 degree grid
        else:
            return 1.0  # 1 degree grid


# Global campaign service instance
campaign_service = CampaignService()