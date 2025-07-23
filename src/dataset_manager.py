"""
DatasetManager: Handles all rasterio dataset I/O, caching, and coordinate transformations.

This class extracts the low-level dataset management logic from DEMService,
following the Single Responsibility Principle and improving testability.
"""

import logging
import os
import threading
from typing import Dict, Optional, Tuple
import rasterio
from cachetools import LRUCache
from pyproj import Transformer
from rasterio.env import Env
from rasterio.errors import RasterioIOError
import fiona

from src.config import Settings, DEMSource
from src.dem_exceptions import DEMFileError, DEMCacheError

logger = logging.getLogger(__name__)


class ClosingLRUCache(LRUCache):
    """
    An LRU cache that calls .close() on evicted items.
    This is essential for caches that store objects with open file handles,
    like rasterio datasets, to prevent resource leaks.
    """
    def popitem(self):
        """Evict the least recently used item, closing it if possible."""
        key, value = super().popitem()
        if hasattr(value, 'close') and callable(value.close):
            try:
                value.close()
                logger.info(f"Closed evicted cache item: {key}")
            except Exception as e:
                logger.warning(f"Error closing evicted cache item {key}: {e}")
        return key, value

    def clear(self):
        """Clear the cache and close all remaining items."""
        for key, value in self.items():
            if hasattr(value, 'close') and callable(value.close):
                try:
                    value.close()
                    logger.info(f"Closed cache item on clear: {key}")
                except Exception as e:
                    logger.warning(f"Error closing cache item {key} on clear: {e}")
        super().clear()


class DatasetManager:
    """
    Manages rasterio dataset I/O, caching, and coordinate transformations.
    
    This class encapsulates all low-level dataset operations, providing a clean
    interface for higher-level services while maintaining resource safety.
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.dem_sources = settings.DEM_SOURCES
        
        # Resource-safe caches with size limits
        self._dataset_cache = ClosingLRUCache(maxsize=settings.DATASET_CACHE_SIZE)
        self._transformer_cache = LRUCache(maxsize=settings.DATASET_CACHE_SIZE)
        
        # Thread lock for thread-safe dataset access
        self._dataset_lock = threading.RLock()
        
        logger.info(f"DatasetManager initialized with cache size: {settings.DATASET_CACHE_SIZE}")

    def get_dataset(self, dem_source_id: str, lat: float = None, lon: float = None) -> rasterio.DatasetReader:
        """
        Get a rasterio dataset for the specified DEM source with thread-safe caching.
        
        Args:
            dem_source_id: ID of the DEM source
            lat: Optional latitude for cache key differentiation
            lon: Optional longitude for cache key differentiation
            
        Returns:
            Open rasterio dataset
            
        Raises:
            DEMFileError: If dataset cannot be opened
            DEMCacheError: If cache operations fail
        """
        if dem_source_id not in self.dem_sources:
            raise DEMFileError(f"DEM source '{dem_source_id}' not found in configuration")
        
        source = self.dem_sources[dem_source_id]
        cache_key = f"{dem_source_id}_{lat}_{lon}" if lat is not None and lon is not None else dem_source_id
        
        with self._dataset_lock:
            try:
                if cache_key not in self._dataset_cache:
                    logger.debug(f"Opening dataset for source '{dem_source_id}' (cache miss)")
                    
                    dataset = self._open_dataset_with_fallbacks(
                        source.path, 
                        source.layer,
                        lat=lat, 
                        lon=lon
                    )
                    
                    if dataset is None:
                        raise DEMFileError(f"Failed to open dataset for source '{dem_source_id}'")
                    
                    self._dataset_cache[cache_key] = dataset
                    logger.debug(f"Cached dataset for source '{dem_source_id}'")
                else:
                    logger.debug(f"Using cached dataset for source '{dem_source_id}' (cache hit)")
                
                return self._dataset_cache[cache_key]
                
            except Exception as e:
                logger.error(f"Error getting dataset for source '{dem_source_id}': {e}")
                raise DEMCacheError(f"Dataset access failed for '{dem_source_id}': {str(e)}")

    def _open_dataset_with_fallbacks(self, path: str, layer_name: Optional[str] = None, 
                                   lat: float = None, lon: float = None) -> Optional[rasterio.DatasetReader]:
        """
        Open a rasterio dataset with multiple fallback strategies for different file types.
        
        Args:
            path: Path to the dataset file
            layer_name: Optional layer name for geodatabases
            lat: Optional latitude for logging
            lon: Optional longitude for logging
            
        Returns:
            Open rasterio dataset or None if all attempts fail
        """
        try:
            # Strategy 1: Direct path access (works for GeoTIFF, network files, S3)
            if not path.endswith('.gdb'):
                with Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR'):
                    dataset = rasterio.open(path)
                    logger.debug(f"Opened dataset directly: {path}")
                    return dataset
            
            # Strategy 2: Geodatabase with specified layer
            if layer_name:
                gdb_path = f"{path}/{layer_name}"
                try:
                    with Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR'):
                        dataset = rasterio.open(gdb_path)
                        logger.debug(f"Opened geodatabase layer: {gdb_path}")
                        return dataset
                except Exception as e:
                    logger.debug(f"Failed to open specified layer '{layer_name}': {e}")
            
            # Strategy 3: Auto-discover raster layers in geodatabase
            return self._auto_discover_raster_layer(path)
            
        except Exception as e:
            logger.error(f"All dataset opening strategies failed for {path}: {e}")
            return None

    def _auto_discover_raster_layer(self, gdb_path: str) -> Optional[rasterio.DatasetReader]:
        """
        Auto-discover and open the first suitable raster layer in a geodatabase.
        
        Args:
            gdb_path: Path to the geodatabase
            
        Returns:
            Open rasterio dataset or None if no suitable layer found
        """
        common_raster_patterns = ['dtm', 'dem', 'elevation', 'height', 'raster']
        
        try:
            # List all layers in the geodatabase
            layers = fiona.listlayers(gdb_path)
            logger.debug(f"Found {len(layers)} layers in geodatabase: {layers}")
            
            # Try common raster patterns first
            for pattern in common_raster_patterns:
                for layer in layers:
                    if pattern.lower() in layer.lower():
                        try:
                            layer_path = f"{gdb_path}/{layer}"
                            with Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR'):
                                dataset = rasterio.open(layer_path)
                                logger.info(f"Auto-discovered raster layer: {layer}")
                                return dataset
                        except Exception as e:
                            logger.debug(f"Failed to open discovered layer '{layer}': {e}")
                            continue
            
            # If no pattern match, try the first layer
            if layers:
                try:
                    layer_path = f"{gdb_path}/{layers[0]}"
                    with Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR'):
                        dataset = rasterio.open(layer_path)
                        logger.info(f"Opened first available layer: {layers[0]}")
                        return dataset
                except Exception as e:
                    logger.debug(f"Failed to open first layer '{layers[0]}': {e}")
            
        except Exception as e:
            logger.error(f"Failed to list layers in geodatabase {gdb_path}: {e}")
        
        return None

    def get_transformer(self, dem_source_id: str) -> Transformer:
        """
        Get a coordinate transformer for the specified DEM source with caching.
        
        Args:
            dem_source_id: ID of the DEM source
            
        Returns:
            Pyproj transformer for coordinate conversion
            
        Raises:
            DEMFileError: If source not found or CRS invalid
        """
        if dem_source_id not in self.dem_sources:
            raise DEMFileError(f"DEM source '{dem_source_id}' not found in configuration")
        
        if dem_source_id not in self._transformer_cache:
            source = self.dem_sources[dem_source_id]
            source_crs = source.crs
            
            try:
                # Create transformer from WGS84 (longitude, latitude) to source CRS
                transformer = Transformer.from_crs(
                    "EPSG:4326",  # WGS84
                    source_crs,
                    always_xy=True  # Ensure (lon, lat) input order
                )
                
                self._transformer_cache[dem_source_id] = transformer
                logger.debug(f"Created and cached transformer for source '{dem_source_id}' (CRS: {source_crs})")
                
            except Exception as e:
                logger.error(f"Failed to create transformer for source '{dem_source_id}': {e}")
                raise DEMFileError(f"Invalid CRS '{source_crs}' for source '{dem_source_id}': {str(e)}")
        
        return self._transformer_cache[dem_source_id]

    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get cache statistics for monitoring and debugging.
        
        Returns:
            Dictionary with cache statistics
        """
        return {
            "dataset_cache_size": len(self._dataset_cache),
            "dataset_cache_maxsize": self._dataset_cache.maxsize,
            "transformer_cache_size": len(self._transformer_cache),
            "transformer_cache_maxsize": self._transformer_cache.maxsize,
        }

    def clear_caches(self):
        """Clear all caches and close open datasets."""
        with self._dataset_lock:
            if hasattr(self._dataset_cache, 'clear'):
                self._dataset_cache.clear()
            if hasattr(self._transformer_cache, 'clear'):
                self._transformer_cache.clear()
            logger.info("DatasetManager caches cleared")

    async def close(self):
        """Close all cached datasets and clean up resources."""
        self.clear_caches()
        logger.info("DatasetManager closed and all resources cleaned up")