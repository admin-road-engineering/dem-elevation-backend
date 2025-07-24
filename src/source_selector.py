"""
DEM Source Selection Service

Automatically selects the best available DEM source for a given location
based on priority, resolution, bounds, and data quality.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon
import math

from .config import Settings
from .models import DEMSourceMetadata

logger = logging.getLogger(__name__)

@dataclass
class SourceScore:
    """Score for a DEM source at a specific location."""
    source_id: str
    score: float
    within_bounds: bool
    resolution_m: Optional[float]
    priority: Optional[int]
    data_source: Optional[str]
    year: Optional[int]
    reason: str

class DEMSourceSelector:
    """Selects the best DEM source for a given location."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.source_metadata: Dict[str, DEMSourceMetadata] = {}
        self._load_source_metadata()
        
    def _load_source_metadata(self):
        """Load and validate source metadata from settings."""
        for source_id, source_config in self.settings.DEM_SOURCES.items():
            try:
                # Convert raw dict to DEMSourceMetadata
                metadata = DEMSourceMetadata(**source_config)
                self.source_metadata[source_id] = metadata
                logger.info(f"Loaded metadata for source: {source_id}")
            except Exception as e:
                logger.warning(f"Failed to load metadata for source {source_id}: {e}")
                # Fallback to basic metadata
                self.source_metadata[source_id] = DEMSourceMetadata(
                    path=source_config.get("path", ""),
                    description=source_config.get("description", "")
                )
    
    def is_point_within_bounds(self, latitude: float, longitude: float, bounds: Dict[str, float]) -> bool:
        """Check if a point is within the specified bounds."""
        if not bounds:
            return True  # No bounds specified, assume global coverage
            
        return (bounds["west"] <= longitude <= bounds["east"] and 
                bounds["south"] <= latitude <= bounds["north"])
    
    def calculate_source_score(self, source_id: str, latitude: float, longitude: float, 
                             prefer_high_resolution: bool = True, 
                             max_resolution_m: Optional[float] = None) -> SourceScore:
        """Calculate a score for a DEM source at a specific location."""
        metadata = self.source_metadata.get(source_id)
        if not metadata:
            return SourceScore(source_id, 0.0, False, None, None, None, None, "No metadata available")
        
        # Check if point is within bounds
        within_bounds = self.is_point_within_bounds(latitude, longitude, metadata.bounds)
        if not within_bounds:
            return SourceScore(source_id, 0.0, False, metadata.resolution_m, metadata.priority, 
                             metadata.data_source, metadata.year, "Outside coverage bounds")
        
        # Check resolution constraints
        if max_resolution_m and metadata.resolution_m and metadata.resolution_m > max_resolution_m:
            return SourceScore(source_id, 0.0, True, metadata.resolution_m, metadata.priority, 
                             metadata.data_source, metadata.year, "Resolution too coarse")
        
        # Calculate score based on multiple factors
        score = 100.0  # Base score
        
        # Priority factor (highest weight)
        if metadata.priority:
            score += (10 - metadata.priority) * 20  # Priority 1 = +180, Priority 10 = +0
        
        # Resolution factor
        if metadata.resolution_m and prefer_high_resolution:
            # Better resolution = higher score (logarithmic scale)
            resolution_score = max(0, 50 - math.log10(metadata.resolution_m) * 20)
            score += resolution_score
        
        # Data source quality factor
        data_source_scores = {
            "LiDAR": 30,
            "Photogrammetry": 20,
            "SAR": 10,
            "SRTM": 5
        }
        if metadata.data_source:
            score += data_source_scores.get(metadata.data_source, 0)
        
        # Recency factor
        if metadata.year:
            years_old = 2024 - metadata.year
            recency_score = max(0, 20 - years_old * 2)  # Newer data gets higher score
            score += recency_score
        
        reason = f"Score: {score:.1f}"
        if metadata.resolution_m:
            reason += f", Resolution: {metadata.resolution_m}m"
        if metadata.priority:
            reason += f", Priority: {metadata.priority}"
        if metadata.data_source:
            reason += f", Type: {metadata.data_source}"
        
        return SourceScore(source_id, score, True, metadata.resolution_m, metadata.priority, 
                         metadata.data_source, metadata.year, reason)
    
    def select_best_source(self, latitude: float, longitude: float, 
                          prefer_high_resolution: bool = True,
                          max_resolution_m: Optional[float] = None) -> Tuple[str, List[SourceScore]]:
        """
        Select the best DEM source for a given location.
        
        Returns:
            Tuple of (best_source_id, all_scores_sorted)
        """
        if not self.settings.AUTO_SELECT_BEST_SOURCE:
            # Return default source if auto-selection is disabled
            default_source = self.settings.DEFAULT_DEM_ID or list(self.settings.DEM_SOURCES.keys())[0]
            return default_source, []
        
        # Calculate scores for all sources
        scores = []
        for source_id in self.settings.DEM_SOURCES.keys():
            score = self.calculate_source_score(source_id, latitude, longitude, 
                                              prefer_high_resolution, max_resolution_m)
            scores.append(score)
        
        # Sort by score (highest first)
        scores.sort(key=lambda x: x.score, reverse=True)
        
        # Find the best source with non-zero score
        best_source_id = None
        for score in scores:
            if score.score > 0 and score.within_bounds:
                best_source_id = score.source_id
                break
        
        # Fallback to default if no source found
        if not best_source_id:
            best_source_id = self.settings.DEFAULT_DEM_ID or list(self.settings.DEM_SOURCES.keys())[0]
            logger.warning(f"No suitable source found for ({latitude}, {longitude}), using default: {best_source_id}")
        
        return best_source_id, scores
    
    def get_sources_for_bounds(self, west: float, south: float, east: float, north: float) -> List[str]:
        """Get all sources that overlap with the specified bounds."""
        overlapping_sources = []
        
        for source_id, metadata in self.source_metadata.items():
            if not metadata.bounds:
                # No bounds specified, assume global coverage
                overlapping_sources.append(source_id)
                continue
                
            # Check for overlap
            if (metadata.bounds["west"] <= east and metadata.bounds["east"] >= west and
                metadata.bounds["south"] <= north and metadata.bounds["north"] >= south):
                overlapping_sources.append(source_id)
        
        return overlapping_sources
    
    def get_coverage_summary(self) -> Dict[str, Any]:
        """Get a summary of coverage for all sources."""
        summary = {
            "total_sources": len(self.source_metadata),
            "sources_with_bounds": 0,
            "sources_by_type": {},
            "resolution_range": {"min": None, "max": None},
            "coverage_areas": []
        }
        
        for source_id, metadata in self.source_metadata.items():
            # Count sources with bounds
            if metadata.bounds:
                summary["sources_with_bounds"] += 1
                
                # Add coverage area
                area_info = {
                    "source_id": source_id,
                    "bounds": metadata.bounds,
                    "resolution_m": metadata.resolution_m,
                    "data_source": metadata.data_source,
                    "year": metadata.year
                }
                summary["coverage_areas"].append(area_info)
            
            # Count by data source type
            if metadata.data_source:
                summary["sources_by_type"][metadata.data_source] = summary["sources_by_type"].get(metadata.data_source, 0) + 1
            
            # Track resolution range
            if metadata.resolution_m:
                if summary["resolution_range"]["min"] is None or metadata.resolution_m < summary["resolution_range"]["min"]:
                    summary["resolution_range"]["min"] = metadata.resolution_m
                if summary["resolution_range"]["max"] is None or metadata.resolution_m > summary["resolution_range"]["max"]:
                    summary["resolution_range"]["max"] = metadata.resolution_m
        
        return summary 