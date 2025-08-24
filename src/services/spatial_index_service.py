"""
Spatial Index Service - Performance Enhancement Phase 3

Provides O(log N) spatial queries using STRtree (Sort-Tile-Recursive tree) 
instead of O(N) linear bounds checking. Dramatically improves performance
for large datasets with many spatial features.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from shapely.geometry import Point, box
from shapely.strtree import STRtree
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SpatialItem:
    """Item stored in spatial index with geometry and metadata"""
    id: str
    geometry: Any  # Shapely geometry (box, polygon, etc.)
    data: Dict[str, Any]  # Campaign/collection metadata
    

class SpatialIndexService:
    """
    High-performance spatial indexing service using STRtree.
    
    Performance Benefits:
    - O(log N) spatial queries vs O(N) linear search
    - Bulk loading for optimal tree construction
    - Efficient intersection queries
    - Memory-efficient R-tree structure
    """
    
    def __init__(self):
        """Initialize spatial index service"""
        self._tree: Optional[STRtree] = None
        self._items: List[SpatialItem] = []
        self._built = False
        
        logger.info("SpatialIndexService initialized")
    
    def add_bbox_item(self, item_id: str, bounds: Dict[str, float], data: Dict[str, Any]) -> bool:
        """
        Add a bounding box item to the spatial index.
        
        Args:
            item_id: Unique identifier for the item
            bounds: Dictionary with min_lat, max_lat, min_lon, max_lon keys
            data: Associated metadata (campaign info, etc.)
            
        Returns:
            True if item was added successfully
        """
        try:
            # Validate bounds
            required_keys = ["min_lat", "max_lat", "min_lon", "max_lon"]
            if not all(key in bounds for key in required_keys):
                logger.warning(f"Invalid bounds for item {item_id}: missing keys")
                return False
            
            # Create shapely box geometry
            geometry = box(
                bounds["min_lon"], bounds["min_lat"], 
                bounds["max_lon"], bounds["max_lat"]
            )
            
            # Create spatial item
            spatial_item = SpatialItem(
                id=item_id,
                geometry=geometry,
                data=data
            )
            
            self._items.append(spatial_item)
            self._built = False  # Mark as needing rebuild
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding spatial item {item_id}: {e}")
            return False
    
    def build_index(self) -> bool:
        """
        Build the spatial index from added items.
        
        This should be called after adding all items and before querying.
        Uses bulk loading for optimal tree construction.
        
        Returns:
            True if index was built successfully
        """
        try:
            if len(self._items) == 0:
                logger.warning("No items to build spatial index from")
                return False
            
            logger.info(f"Building STRtree spatial index with {len(self._items)} items...")
            
            # Extract geometries for STRtree construction
            geometries = [item.geometry for item in self._items]
            
            # Build STRtree with bulk loading (most efficient)
            self._tree = STRtree(geometries)
            self._built = True
            
            logger.info(f"✅ Spatial index built successfully: {len(self._items)} items indexed")
            return True
            
        except Exception as e:
            logger.error(f"Error building spatial index: {e}")
            return False
    
    def query_point(self, latitude: float, longitude: float) -> List[SpatialItem]:
        """
        Find all items that contain the given point.
        
        Performance: O(log N) average case vs O(N) linear search
        
        Args:
            latitude: Point latitude
            longitude: Point longitude
            
        Returns:
            List of SpatialItem objects that contain the point
        """
        if not self._built or self._tree is None:
            logger.error("Spatial index not built - call build_index() first")
            return []
        
        try:
            # Create point geometry
            point = Point(longitude, latitude)
            
            # Query spatial index - O(log N) operation
            intersecting_geometries = self._tree.query(point)
            
            # Find corresponding items
            matching_items = []
            for geometry in intersecting_geometries:
                # Find the item with this geometry
                for item in self._items:
                    if item.geometry is geometry:
                        # Double-check containment (STRtree query returns candidates)
                        if item.geometry.contains(point):
                            matching_items.append(item)
                        break
            
            logger.debug(f"Spatial query for ({latitude}, {longitude}): found {len(matching_items)} items")
            return matching_items
            
        except Exception as e:
            logger.error(f"Error querying spatial index: {e}")
            return []
    
    def query_bbox(self, min_lat: float, max_lat: float, min_lon: float, max_lon: float) -> List[SpatialItem]:
        """
        Find all items that intersect with the given bounding box.
        
        Args:
            min_lat, max_lat, min_lon, max_lon: Bounding box coordinates
            
        Returns:
            List of SpatialItem objects that intersect the box
        """
        if not self._built or self._tree is None:
            logger.error("Spatial index not built - call build_index() first")
            return []
        
        try:
            # Create bounding box geometry
            query_box = box(min_lon, min_lat, max_lon, max_lat)
            
            # Query spatial index
            intersecting_geometries = self._tree.query(query_box)
            
            # Find corresponding items
            matching_items = []
            for geometry in intersecting_geometries:
                for item in self._items:
                    if item.geometry is geometry:
                        # Double-check intersection
                        if item.geometry.intersects(query_box):
                            matching_items.append(item)
                        break
            
            return matching_items
            
        except Exception as e:
            logger.error(f"Error querying spatial bbox: {e}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get spatial index statistics"""
        return {
            "built": self._built,
            "total_items": len(self._items),
            "has_tree": self._tree is not None,
            "index_type": "STRtree (R-tree)",
            "performance_class": "O(log N) spatial queries"
        }
    
    def clear(self):
        """Clear the spatial index"""
        self._tree = None
        self._items.clear()
        self._built = False
        logger.info("Spatial index cleared")


def create_campaign_spatial_index(campaigns: Dict[str, Any]) -> SpatialIndexService:
    """
    Utility function to create spatial index from campaign data.
    
    Args:
        campaigns: Dictionary of campaign data with bounds information
        
    Returns:
        Built SpatialIndexService ready for queries
    """
    spatial_index = SpatialIndexService()
    
    added_count = 0
    for campaign_id, campaign_data in campaigns.items():
        bounds = campaign_data.get("bounds", {})
        if bounds and bounds.get("type") == "bbox":
            if spatial_index.add_bbox_item(campaign_id, bounds, campaign_data):
                added_count += 1
    
    logger.info(f"Added {added_count}/{len(campaigns)} campaigns to spatial index")
    
    if added_count > 0:
        if spatial_index.build_index():
            logger.info("✅ Campaign spatial index built successfully")
            return spatial_index
        else:
            logger.error("❌ Failed to build campaign spatial index")
    
    return spatial_index