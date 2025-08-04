"""Coordinate system models for CRS-aware spatial queries"""
from pydantic import BaseModel
from typing import Optional

class PointWGS84(BaseModel):
    """Point in WGS84 geographic coordinates (degrees)"""
    lat: float
    lon: float

class PointProjected(BaseModel):
    """Point in projected coordinate system (meters)"""
    x: float
    y: float
    epsg: str

class QueryPoint(BaseModel):
    """Coordinate point with optional projection for efficient reuse
    
    Implements Transform-Once pattern: transform coordinates once and reuse
    the projected coordinates for multiple spatial operations.
    """
    wgs84: PointWGS84
    projected: Optional[PointProjected] = None
    
    def get_or_create_projection(self, target_epsg: str, transformer_service) -> PointProjected:
        """Get existing projection or create new one if EPSG differs
        
        Args:
            target_epsg: Target EPSG code (e.g., "28356" for Brisbane UTM Zone 56)
            transformer_service: CRS transformation service instance
            
        Returns:
            PointProjected with coordinates in target CRS
        """
        if self.projected is None or self.projected.epsg != target_epsg:
            x, y = transformer_service.transform_to_crs(
                self.wgs84.lat, self.wgs84.lon, target_epsg
            )
            self.projected = PointProjected(x=x, y=y, epsg=target_epsg)
        return self.projected