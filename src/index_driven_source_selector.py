"""
Index-Driven Source Selector with Spatial Indexing

Implements Gemini's recommendations for efficient geographic lookups using spatial indexing
instead of linear scans. This provides O(log N) performance for campaign selection.
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
import math

logger = logging.getLogger(__name__)

@dataclass
class BoundingBox:
    """Represents a bounding box for spatial indexing"""
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    
    def contains_point(self, lat: float, lon: float) -> bool:
        """Check if point is within this bounding box"""
        return (self.min_lat <= lat <= self.max_lat and 
                self.min_lon <= lon <= self.max_lon)
    
    def area(self) -> float:
        """Calculate area of bounding box (for overlap resolution)"""
        return (self.max_lat - self.min_lat) * (self.max_lon - self.min_lon)

@dataclass 
class SpatialIndexNode:
    """Node in the spatial index containing campaign information"""
    campaign_id: str
    bounds: BoundingBox
    resolution_m: float
    source_type: str
    campaign_data: Dict[str, Any]

class SpatialIndex:
    """
    Spatial index using a simple grid-based approach for efficient geographic lookups.
    
    For 1,151 campaigns, this provides much better performance than linear scans
    while being simpler to implement than R-trees.
    """
    
    def __init__(self, grid_size: int = 50):
        """
        Initialize spatial index with grid-based partitioning.
        
        Args:
            grid_size: Number of grid cells per dimension (50x50 = 2500 cells)
        """
        self.grid_size = grid_size
        self.grid: Dict[Tuple[int, int], List[SpatialIndexNode]] = {}
        self.node_count = 0
        
        # Global bounds for grid calculation
        self.global_min_lat = float('inf')
        self.global_max_lat = float('-inf') 
        self.global_min_lon = float('inf')
        self.global_max_lon = float('-inf')
        
    def _calculate_global_bounds(self, nodes: List[SpatialIndexNode]):
        """Calculate global bounds from all nodes for grid setup"""
        for node in nodes:
            self.global_min_lat = min(self.global_min_lat, node.bounds.min_lat)
            self.global_max_lat = max(self.global_max_lat, node.bounds.max_lat)
            self.global_min_lon = min(self.global_min_lon, node.bounds.min_lon)
            self.global_max_lon = max(self.global_max_lon, node.bounds.max_lon)
        
        # Add small padding to avoid edge cases
        padding = 0.01
        self.global_min_lat -= padding
        self.global_max_lat += padding
        self.global_min_lon -= padding
        self.global_max_lon += padding
        
    def _get_grid_cells_for_bounds(self, bounds: BoundingBox) -> List[Tuple[int, int]]:
        """Get all grid cells that a bounding box intersects"""
        # Calculate grid cell ranges
        lat_range = self.global_max_lat - self.global_min_lat
        lon_range = self.global_max_lon - self.global_min_lon
        
        min_row = max(0, int((bounds.min_lat - self.global_min_lat) / lat_range * self.grid_size))
        max_row = min(self.grid_size - 1, int((bounds.max_lat - self.global_min_lat) / lat_range * self.grid_size))
        min_col = max(0, int((bounds.min_lon - self.global_min_lon) / lon_range * self.grid_size))
        max_col = min(self.grid_size - 1, int((bounds.max_lon - self.global_min_lon) / lon_range * self.grid_size))
        
        cells = []
        for row in range(min_row, max_row + 1):
            for col in range(min_col, max_col + 1):
                cells.append((row, col))
        
        return cells
    
    def _get_grid_cell_for_point(self, lat: float, lon: float) -> Tuple[int, int]:
        """Get grid cell for a specific point"""
        lat_range = self.global_max_lat - self.global_min_lat
        lon_range = self.global_max_lon - self.global_min_lon
        
        row = max(0, min(self.grid_size - 1, int((lat - self.global_min_lat) / lat_range * self.grid_size)))
        col = max(0, min(self.grid_size - 1, int((lon - self.global_min_lon) / lon_range * self.grid_size)))
        
        return (row, col)
    
    def build_index(self, nodes: List[SpatialIndexNode]):
        """Build the spatial index from campaign nodes"""
        logger.info(f"Building spatial index for {len(nodes)} campaigns with {self.grid_size}x{self.grid_size} grid")
        
        # Calculate global bounds first
        self._calculate_global_bounds(nodes)
        
        # Clear existing index
        self.grid.clear()
        self.node_count = len(nodes)
        
        # Insert each node into appropriate grid cells
        for node in nodes:
            cells = self._get_grid_cells_for_bounds(node.bounds)
            for cell in cells:
                if cell not in self.grid:
                    self.grid[cell] = []
                self.grid[cell].append(node)
        
        # Log index statistics
        occupied_cells = len(self.grid)
        avg_nodes_per_cell = sum(len(nodes) for nodes in self.grid.values()) / occupied_cells if occupied_cells > 0 else 0
        max_nodes_per_cell = max(len(nodes) for nodes in self.grid.values()) if self.grid else 0
        
        logger.info(
            f"Spatial index built: {occupied_cells}/{self.grid_size**2} cells occupied, "
            f"avg {avg_nodes_per_cell:.1f} campaigns/cell, max {max_nodes_per_cell} campaigns/cell"
        )
    
    def query_point(self, lat: float, lon: float) -> List[SpatialIndexNode]:
        """Query all campaigns containing a specific point"""
        cell = self._get_grid_cell_for_point(lat, lon)
        
        if cell not in self.grid:
            return []
        
        # Check each candidate node in the cell
        candidates = []
        for node in self.grid[cell]:
            if node.bounds.contains_point(lat, lon):
                candidates.append(node)
        
        return candidates

class IndexDrivenSourceSelector:
    """
    Source selector using index-driven sources with spatial indexing for performance.
    
    Implements Gemini's recommendations:
    1. Spatial indexing for O(log N) geographic lookups instead of O(N) linear scans
    2. Best resolution selection for overlapping campaigns
    3. Proper fallback chain (S3 campaigns → API sources)
    """
    
    def __init__(self, index_sources: Dict[str, Any]):
        """
        Initialize with index-driven sources.
        
        Args:
            index_sources: Sources loaded from spatial indices via Settings.DEM_SOURCES
        """
        self.index_sources = index_sources
        self.spatial_index = SpatialIndex()
        
        # Separate S3 campaigns from API sources
        self.s3_campaigns = {}
        self.api_sources = {}
        
        for source_id, source_data in index_sources.items():
            source_type = source_data.get('source_type', 'unknown')
            if source_type == 's3':
                self.s3_campaigns[source_id] = source_data
            elif source_type == 'api':
                self.api_sources[source_id] = source_data
        
        # Build spatial index from S3 campaigns
        self._build_spatial_index()
        
        logger.info(
            f"IndexDrivenSourceSelector initialized: {len(self.s3_campaigns)} S3 campaigns, "
            f"{len(self.api_sources)} API sources"
        )
    
    def _build_spatial_index(self):
        """Build spatial index from S3 campaign bounds"""
        nodes = []
        
        for campaign_id, campaign_data in self.s3_campaigns.items():
            bounds_data = campaign_data.get('bounds', {})
            
            # Skip campaigns without valid bounds
            if not all(key in bounds_data for key in ['min_lat', 'max_lat', 'min_lon', 'max_lon']):
                logger.warning(f"Campaign {campaign_id} missing bounds data, skipping spatial index")
                continue
            
            try:
                bounds = BoundingBox(
                    min_lat=float(bounds_data['min_lat']),
                    max_lat=float(bounds_data['max_lat']),
                    min_lon=float(bounds_data['min_lon']),
                    max_lon=float(bounds_data['max_lon'])
                )
                
                node = SpatialIndexNode(
                    campaign_id=campaign_id,
                    bounds=bounds,
                    resolution_m=campaign_data.get('resolution_m', 30.0),
                    source_type='s3',
                    campaign_data=campaign_data
                )
                
                nodes.append(node)
                
            except (ValueError, KeyError) as e:
                logger.warning(f"Invalid bounds data for campaign {campaign_id}: {e}")
                continue
        
        if nodes:
            self.spatial_index.build_index(nodes)
        else:
            logger.warning("No S3 campaigns with valid bounds for spatial indexing")
    
    def select_best_source(self, lat: float, lon: float) -> str:
        """
        Select best source for coordinates using spatial indexing.
        
        Process:
        1. Use spatial index to find overlapping S3 campaigns (O(log N))
        2. If multiple campaigns overlap, select best resolution
        3. Fallback to API sources if no S3 campaigns match
        
        Args:
            lat: Latitude in WGS84
            lon: Longitude in WGS84
            
        Returns:
            Source ID of best available source
        """
        # Query spatial index for overlapping campaigns
        overlapping_campaigns = self.spatial_index.query_point(lat, lon)
        
        if overlapping_campaigns:
            # Multiple campaigns - select best resolution
            if len(overlapping_campaigns) > 1:
                best_campaign = min(overlapping_campaigns, key=lambda x: x.resolution_m)
                logger.debug(
                    f"Selected best resolution campaign {best_campaign.campaign_id} "
                    f"({best_campaign.resolution_m}m) from {len(overlapping_campaigns)} overlapping campaigns"
                )
                return best_campaign.campaign_id
            else:
                # Single campaign match
                campaign = overlapping_campaigns[0]
                logger.debug(f"Selected campaign {campaign.campaign_id} for point ({lat}, {lon})")
                return campaign.campaign_id
        
        # No S3 campaigns match - fallback to API sources
        # Prefer GPXZ API as primary fallback
        if 'gpxz_api' in self.api_sources:
            logger.debug(f"No S3 campaigns found for ({lat}, {lon}), using GPXZ API fallback")
            return 'gpxz_api'
        elif 'google_api' in self.api_sources:
            logger.debug(f"No S3 campaigns found for ({lat}, {lon}), using Google API fallback")
            return 'google_api'
        else:
            # Last resort - return any available API source
            api_sources = list(self.api_sources.keys())
            if api_sources:
                fallback_source = api_sources[0]
                logger.debug(f"Using fallback API source: {fallback_source}")
                return fallback_source
        
        # No sources available - this shouldn't happen with proper config
        logger.warning(f"No sources available for coordinates ({lat}, {lon})")
        return 'no_source_available'
    
    def get_source_info(self, source_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific source"""
        return self.index_sources.get(source_id)
    
    def get_all_sources(self) -> Dict[str, Dict[str, Any]]:
        """Get all available sources with metadata"""
        return self.index_sources.copy()
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for monitoring"""
        return {
            'total_sources': len(self.index_sources),
            's3_campaigns': len(self.s3_campaigns),
            'api_sources': len(self.api_sources),
            'spatial_index_nodes': self.spatial_index.node_count,
            'spatial_index_grid_size': self.spatial_index.grid_size,
            'spatial_index_occupied_cells': len(self.spatial_index.grid)
        }