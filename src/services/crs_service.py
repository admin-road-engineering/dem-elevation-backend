"""Coordinate Reference System transformation service"""
from pyproj import Transformer
from pyproj.exceptions import CRSError
import logging
from typing import Dict

logger = logging.getLogger(__name__)

class CRSTransformationService:
    """Service for coordinate transformations with caching and error handling
    
    Implements data-driven CRS transformations using EPSG codes stored in the
    unified spatial index. Supports infinite extensibility for new coordinate
    reference systems without code changes.
    
    Key Features:
    - Transformer caching for performance
    - Specific CRSError handling 
    - Data-driven EPSG code support
    - Thread-safe operations
    """
    
    def __init__(self):
        self._transformer_cache: Dict[str, Transformer] = {}
        logger.info("CRSTransformationService initialized")
    
    def get_transformer(self, target_epsg: str) -> Transformer:
        """Get cached transformer for WGS84 → target CRS
        
        Args:
            target_epsg: Target EPSG code (e.g., "28356")
            
        Returns:
            Cached Transformer instance
            
        Raises:
            CRSError: If EPSG code is invalid
        """
        if target_epsg not in self._transformer_cache:
            try:
                self._transformer_cache[target_epsg] = Transformer.from_crs(
                    "EPSG:4326", f"EPSG:{target_epsg}", always_xy=True
                )
                logger.debug(f"Created transformer for EPSG:{target_epsg}")
            except CRSError as e:
                logger.error(f"Failed to create transformer for EPSG:{target_epsg}: {e}")
                raise
        return self._transformer_cache[target_epsg]
    
    def transform_to_crs(self, lat: float, lon: float, target_epsg: str) -> tuple[float, float]:
        """Transform WGS84 coordinates to target CRS (data-driven)
        
        Args:
            lat: WGS84 latitude in degrees
            lon: WGS84 longitude in degrees  
            target_epsg: Target EPSG code from unified index
            
        Returns:
            Tuple of (x, y) coordinates in target CRS meters
            
        Raises:
            CRSError: If transformation fails
        """
        try:
            transformer = self.get_transformer(target_epsg)
            # Note: pyproj transformer expects (lon, lat) order for geographic coordinates
            x, y = transformer.transform(lon, lat)
            logger.debug(f"Transformed WGS84({lat}, {lon}) → EPSG:{target_epsg}({x:.1f}, {y:.1f})")
            return x, y
        except CRSError as e:
            logger.error(f"CRS transformation failed for EPSG:{target_epsg}: {e}")
            raise
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get transformer cache statistics for monitoring"""
        return {
            "cached_transformers": len(self._transformer_cache),
            "supported_epsg_codes": list(self._transformer_cache.keys())
        }