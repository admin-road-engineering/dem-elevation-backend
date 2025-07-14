"""
LiDAR Point Cloud Service for Raw LAS/LAZ Data

This module extends the DEM service to handle raw LiDAR point clouds
for higher precision elevation queries.
"""

import logging
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from scipy.spatial import cKDTree
import laspy
from pyproj import Transformer
import threading
import os

logger = logging.getLogger(__name__)

class LiDARService:
    """Service for handling raw LiDAR point cloud data (.las/.laz files)."""
    
    def __init__(self):
        self._point_cloud_cache: Dict[str, Dict] = {}
        self._transformer_cache: Dict[str, Transformer] = {}
        self._cache_lock = threading.RLock()
    
    def _load_las_file(self, file_path: str) -> Dict[str, Any]:
        """Load LAS/LAZ file and return point cloud data with spatial index."""
        logger.info(f"Loading LiDAR point cloud: {file_path}")
        
        try:
            # Read LAS file
            las_file = laspy.read(file_path)
            
            # Extract coordinates and elevations
            x = las_file.x
            y = las_file.y
            z = las_file.z
            
            # Get CRS information
            crs = las_file.header.parse_crs()
            
            # Create spatial index for fast nearest neighbor queries
            points_2d = np.column_stack([x, y])
            spatial_index = cKDTree(points_2d)
            
            # Store point cloud data
            point_cloud_data = {
                'x': x,
                'y': y, 
                'z': z,
                'crs': crs,
                'spatial_index': spatial_index,
                'bounds': {
                    'min_x': float(np.min(x)),
                    'max_x': float(np.max(x)),
                    'min_y': float(np.min(y)),
                    'max_y': float(np.max(y)),
                    'min_z': float(np.min(z)),
                    'max_z': float(np.max(z))
                },
                'point_count': len(x)
            }
            
            logger.info(f"Loaded {len(x):,} points from {file_path}")
            logger.info(f"Elevation range: {point_cloud_data['bounds']['min_z']:.3f}m to {point_cloud_data['bounds']['max_z']:.3f}m")
            
            return point_cloud_data
            
        except Exception as e:
            logger.error(f"Failed to load LAS file {file_path}: {e}")
            raise
    
    def _get_point_cloud(self, source_id: str, file_path: str) -> Dict[str, Any]:
        """Get point cloud data with caching."""
        with self._cache_lock:
            if source_id not in self._point_cloud_cache:
                self._point_cloud_cache[source_id] = self._load_las_file(file_path)
            return self._point_cloud_cache[source_id]
    
    def get_elevation_at_point(self, latitude: float, longitude: float, 
                              source_id: str, file_path: str,
                              search_radius: float = 1.0,
                              interpolation_method: str = 'nearest') -> Tuple[Optional[float], Dict[str, Any]]:
        """
        Get elevation at a specific point from LiDAR data.
        
        Args:
            latitude: Query latitude (WGS84)
            longitude: Query longitude (WGS84) 
            source_id: LiDAR source identifier
            file_path: Path to LAS/LAZ file
            search_radius: Search radius in meters for nearby points
            interpolation_method: 'nearest', 'idw' (inverse distance weighted), or 'mean'
            
        Returns:
            Tuple of (elevation, metadata)
        """
        try:
            # Load point cloud data
            point_cloud = self._get_point_cloud(source_id, file_path)
            
            # Transform query point to point cloud CRS
            if source_id not in self._transformer_cache:
                self._transformer_cache[source_id] = Transformer.from_crs(
                    "EPSG:4326", point_cloud['crs'], always_xy=True
                )
            
            transformer = self._transformer_cache[source_id]
            query_x, query_y = transformer.transform(longitude, latitude)
            
            # Check if point is within bounds
            bounds = point_cloud['bounds']
            if not (bounds['min_x'] <= query_x <= bounds['max_x'] and 
                   bounds['min_y'] <= query_y <= bounds['max_y']):
                return None, {
                    'error': 'Point outside LiDAR coverage area',
                    'bounds': bounds,
                    'query_point': {'x': query_x, 'y': query_y}
                }
            
            # Find nearby points within search radius
            spatial_index = point_cloud['spatial_index']
            nearby_indices = spatial_index.query_ball_point([query_x, query_y], search_radius)
            
            if not nearby_indices:
                # Expand search radius and try again
                expanded_radius = search_radius * 3
                nearby_indices = spatial_index.query_ball_point([query_x, query_y], expanded_radius)
                
                if not nearby_indices:
                    return None, {
                        'error': f'No points found within {expanded_radius}m radius',
                        'search_radius': expanded_radius,
                        'point_count': point_cloud['point_count']
                    }
            
            # Get elevations of nearby points
            nearby_elevations = point_cloud['z'][nearby_indices]
            nearby_x = point_cloud['x'][nearby_indices]
            nearby_y = point_cloud['y'][nearby_indices]
            
            # Calculate elevation based on interpolation method
            if interpolation_method == 'nearest':
                # Use closest point
                distances = np.sqrt((nearby_x - query_x)**2 + (nearby_y - query_y)**2)
                closest_idx = np.argmin(distances)
                elevation = float(nearby_elevations[closest_idx])
                closest_distance = float(distances[closest_idx])
                
            elif interpolation_method == 'idw':
                # Inverse Distance Weighted interpolation
                distances = np.sqrt((nearby_x - query_x)**2 + (nearby_y - query_y)**2)
                # Avoid division by zero for exact matches
                distances = np.maximum(distances, 1e-10)
                weights = 1.0 / (distances ** 2)
                elevation = float(np.sum(weights * nearby_elevations) / np.sum(weights))
                closest_distance = float(np.min(distances))
                
            elif interpolation_method == 'mean':
                # Simple mean of nearby points
                elevation = float(np.mean(nearby_elevations))
                distances = np.sqrt((nearby_x - query_x)**2 + (nearby_y - query_y)**2)
                closest_distance = float(np.min(distances))
                
            else:
                raise ValueError(f"Unknown interpolation method: {interpolation_method}")
            
            metadata = {
                'source_id': source_id,
                'interpolation_method': interpolation_method,
                'nearby_points_count': len(nearby_indices),
                'closest_distance_m': closest_distance,
                'search_radius_m': search_radius,
                'elevation_stats': {
                    'min': float(np.min(nearby_elevations)),
                    'max': float(np.max(nearby_elevations)),
                    'std': float(np.std(nearby_elevations)),
                    'range': float(np.max(nearby_elevations) - np.min(nearby_elevations))
                }
            }
            
            return elevation, metadata
            
        except Exception as e:
            logger.error(f"Error getting elevation from LiDAR data: {e}")
            return None, {'error': str(e)}
    
    def get_point_density(self, latitude: float, longitude: float,
                         source_id: str, file_path: str,
                         analysis_radius: float = 5.0) -> Dict[str, Any]:
        """
        Analyze point density around a location.
        Useful for understanding data quality and resolution.
        """
        try:
            point_cloud = self._get_point_cloud(source_id, file_path)
            
            # Transform query point
            if source_id not in self._transformer_cache:
                self._transformer_cache[source_id] = Transformer.from_crs(
                    "EPSG:4326", point_cloud['crs'], always_xy=True
                )
            
            transformer = self._transformer_cache[source_id]
            query_x, query_y = transformer.transform(longitude, latitude)
            
            # Find points within analysis radius
            spatial_index = point_cloud['spatial_index']
            nearby_indices = spatial_index.query_ball_point([query_x, query_y], analysis_radius)
            
            if not nearby_indices:
                return {
                    'point_count': 0,
                    'density_per_m2': 0.0,
                    'analysis_radius_m': analysis_radius
                }
            
            # Calculate density
            area_m2 = np.pi * (analysis_radius ** 2)
            density = len(nearby_indices) / area_m2
            
            # Get elevation statistics
            nearby_elevations = point_cloud['z'][nearby_indices]
            
            return {
                'point_count': len(nearby_indices),
                'density_per_m2': density,
                'analysis_radius_m': analysis_radius,
                'elevation_stats': {
                    'min': float(np.min(nearby_elevations)),
                    'max': float(np.max(nearby_elevations)),
                    'mean': float(np.mean(nearby_elevations)),
                    'std': float(np.std(nearby_elevations)),
                    'range': float(np.max(nearby_elevations) - np.min(nearby_elevations))
                }
            }
            
        except Exception as e:
            logger.error(f"Error analyzing point density: {e}")
            return {'error': str(e)}
    
    def close(self):
        """Clean up resources."""
        with self._cache_lock:
            self._point_cloud_cache.clear()
            self._transformer_cache.clear() 