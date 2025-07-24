"""
Campaign Dataset Selector - Phase 3 Implementation
Smart selection of survey campaigns with temporal preferences and spatial optimization
"""

import json
import logging
import os
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class CampaignMatch:
    """Represents a campaign that potentially contains files for given coordinates"""
    campaign_id: str
    campaign_info: Dict[str, Any]
    priority: int
    file_count: int
    confidence_score: float  # 0.0 to 1.0, higher means more likely to contain data
    temporal_score: float   # 0.0 to 1.0, higher means more recent
    spatial_score: float    # 0.0 to 1.0, higher means more spatially specific
    resolution_score: float # 0.0 to 1.0, higher means better resolution
    provider_score: float   # 0.0 to 1.0, higher means more reliable provider
    total_score: float      # Combined weighted score

class CampaignDatasetSelector:
    """
    Smart campaign selection for Phase 3 optimization.
    
    Achieves target performance improvements through:
    - Temporal preference (newer campaigns first)  
    - Spatial specificity (smaller coverage areas preferred)
    - Smart single-campaign selection when confidence is high
    - Fallback to multiple campaigns when needed
    """
    
    def __init__(self, config_dir: Path = None):
        self.config_dir = config_dir or Path(__file__).parent.parent / "config"
        self.campaign_index = None
        self.tiled_index = None
        self._load_campaign_index()
        self._load_tiled_index()
        
        # Configurable scoring weights (can be overridden by environment variables)
        self.resolution_weight = float(os.getenv("RESOLUTION_WEIGHT", "0.5"))
        self.temporal_weight = float(os.getenv("TEMPORAL_WEIGHT", "0.3"))
        self.spatial_weight = float(os.getenv("SPATIAL_WEIGHT", "0.15"))
        self.provider_weight = float(os.getenv("PROVIDER_WEIGHT", "0.05"))
    
    def _load_campaign_index(self) -> None:
        """Load the campaign-based spatial index"""
        campaign_index_file = self.config_dir / "phase3_campaign_populated_index.json"
        
        if not campaign_index_file.exists():
            logger.warning(f"Campaign index not found at {campaign_index_file}")
            # Fallback to grouped index
            fallback_file = self.config_dir / "grouped_spatial_index.json"
            if fallback_file.exists():
                logger.info("Falling back to grouped spatial index")
                with open(fallback_file, 'r') as f:
                    grouped_index = json.load(f)
                self.campaign_index = self._convert_grouped_to_campaign(grouped_index)
            else:
                logger.error("No spatial index files found")
                self.campaign_index = {"datasets": {}}
            return
        
        try:
            with open(campaign_index_file, 'r') as f:
                self.campaign_index = json.load(f)
            logger.info(f"Loaded campaign index with {len(self.campaign_index.get('datasets', {}))} campaigns")
        except Exception as e:
            logger.error(f"Failed to load campaign index: {e}")
            self.campaign_index = {"datasets": {}}
    
    def _load_tiled_index(self) -> None:
        """Load the tiled spatial index for metro areas"""
        tiled_index_file = self.config_dir / "phase3_brisbane_tiled_index.json"
        
        if tiled_index_file.exists():
            try:
                with open(tiled_index_file, 'r') as f:
                    self.tiled_index = json.load(f)
                logger.info(f"Loaded tiled index with {len(self.tiled_index.get('datasets', {}))} tiles")
            except Exception as e:
                logger.error(f"Failed to load tiled index: {e}")
                self.tiled_index = None
        else:
            logger.info("No tiled index found - using campaign-level selection only")
            self.tiled_index = None
    
    def _convert_grouped_to_campaign(self, grouped_index: Dict) -> Dict:
        """Convert grouped index to campaign format for fallback"""
        return {
            "datasets": grouped_index.get("datasets", {}),
            "total_campaigns": len(grouped_index.get("datasets", {})),
            "total_files": sum(d.get("file_count", 0) for d in grouped_index.get("datasets", {}).values())
        }
    
    def _is_brisbane_metro(self, latitude: float, longitude: float) -> bool:
        """Check if coordinate is in Brisbane metro area for tiled optimization"""
        return (-28.0 <= latitude <= -26.5 and 152.0 <= longitude <= 154.0)
    
    def _calculate_resolution_score(self, campaign_info: Dict[str, Any]) -> float:
        """Calculate resolution preference score (0.0 to 1.0, higher resolution = higher score)"""
        resolution_m = campaign_info.get("resolution_m", 30)
        
        # High-resolution preference with refined thresholds
        if resolution_m <= 0.5:    # 50cm LiDAR (premium quality)
            return 1.0
        elif resolution_m <= 1.0:  # 1m LiDAR (high quality)
            return 0.9
        elif resolution_m <= 2.0:  # 2m DEM (good quality)
            return 0.7
        elif resolution_m <= 5.0:  # 5m DEM (moderate quality)
            return 0.6
        elif resolution_m <= 10.0: # 10m DEM (standard quality)
            return 0.4
        elif resolution_m <= 30.0: # 30m DEM (basic quality)
            return 0.3
        else:
            return 0.1  # Very low resolution
    
    def _calculate_provider_score(self, campaign_info: Dict[str, Any]) -> float:
        """Calculate provider reliability score (0.0 to 1.0, higher = more reliable)"""
        provider = campaign_info.get("provider", "").lower()
        
        if "elvis" in provider:
            return 1.0      # Government LiDAR program (highest reliability)
        elif "ga" in provider or "geoscience" in provider:
            return 0.9      # Geoscience Australia (very reliable)
        elif "csiro" in provider:
            return 0.8      # Research institution (reliable)
        elif any(gov in provider for gov in ["government", "state", "federal"]):
            return 0.7      # Other government sources
        else:
            return 0.5      # Unknown/private (neutral)
    
    def select_campaigns_for_coordinate(self, latitude: float, longitude: float) -> List[CampaignMatch]:
        """
        Smart campaign selection with enhanced multi-factor scoring.
        
        Strategy:
        1. Validate input coordinates
        2. Find all campaigns containing the coordinate
        3. Score by resolution preference (50% - highest priority)
        4. Score by temporal preference (30% - newer = better)
        5. Score by spatial confidence (15% - spatial match quality)
        6. Score by provider reliability (5% - data source quality)
        7. Select best campaign(s) based on total score and confidence
        
        Args:
            latitude: Point latitude in WGS84 (-90 to 90)
            longitude: Point longitude in WGS84 (-180 to 180)
            
        Returns:
            List of CampaignMatch objects sorted by total score (highest first)
        """
        # Input validation
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            raise ValueError(f"Invalid coordinates: ({latitude}, {longitude})")
        
        if not self.campaign_index or "datasets" not in self.campaign_index:
            logger.warning("No campaign index available for smart campaign selection")
            return []
        
        matches = []
        datasets = self.campaign_index["datasets"]
        
        logger.debug(f"Evaluating {len(datasets)} campaigns for coordinate ({latitude}, {longitude})")
        
        for campaign_id, campaign_info in datasets.items():
            if len(campaign_info.get("files", [])) == 0:
                continue  # Skip empty campaigns
            
            # Check if coordinate is within bounds
            if not self._coordinate_in_bounds(latitude, longitude, campaign_info.get("bounds", {})):
                continue
            
            # Calculate all scoring components
            confidence = self._calculate_spatial_confidence(latitude, longitude, campaign_info)
            temporal_score = self._calculate_temporal_score(campaign_info)
            spatial_score = self._calculate_spatial_specificity(campaign_info)
            resolution_score = self._calculate_resolution_score(campaign_info)
            provider_score = self._calculate_provider_score(campaign_info)
            
            # Combined score with configurable weights (resolution prioritized)
            total_score = (resolution_score * self.resolution_weight +
                          temporal_score * self.temporal_weight +
                          confidence * self.spatial_weight +
                          provider_score * self.provider_weight)
            
            if total_score > 0.0:
                matches.append(CampaignMatch(
                    campaign_id=campaign_id,
                    campaign_info=campaign_info,
                    priority=campaign_info.get("priority", 99),
                    file_count=len(campaign_info.get("files", [])),
                    confidence_score=confidence,
                    temporal_score=temporal_score,
                    spatial_score=spatial_score,
                    resolution_score=resolution_score,
                    provider_score=provider_score,
                    total_score=total_score
                ))
        
        # Sort by total score (highest first), then by priority
        matches.sort(key=lambda x: (-x.total_score, x.priority))
        
        # Log selection details with enhanced scoring
        if matches:
            logger.info(f"Selected {len(matches)} campaigns for ({latitude}, {longitude}):")
            for i, match in enumerate(matches[:3]):
                logger.info(f"  {i+1}. {match.campaign_id}: {match.file_count} files, "
                           f"total={match.total_score:.3f}, "
                           f"res={match.resolution_score:.2f}, "
                           f"temp={match.temporal_score:.2f}, "
                           f"spatial={match.confidence_score:.2f}")
        
        return matches
    
    def _coordinate_in_bounds(self, latitude: float, longitude: float, bounds: Dict) -> bool:
        """Check if coordinate is within campaign bounds"""
        if not bounds or bounds.get("type") != "bbox":
            return False
        
        min_lat = bounds.get("min_lat", 999)
        max_lat = bounds.get("max_lat", -999)
        min_lon = bounds.get("min_lon", 999)
        max_lon = bounds.get("max_lon", -999)
        
        return (min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon)
    
    def _calculate_spatial_confidence(self, latitude: float, longitude: float, 
                                    campaign_info: Dict[str, Any]) -> float:
        """Calculate spatial confidence score (0.0 to 1.0)"""
        bounds = campaign_info.get("bounds", {})
        if not bounds:
            return 0.0
        
        confidence = 0.0
        
        min_lat = bounds.get("min_lat", 999)
        max_lat = bounds.get("max_lat", -999)
        min_lon = bounds.get("min_lon", 999)
        max_lon = bounds.get("max_lon", -999)
        
        # Base confidence for being within bounds
        confidence += 0.5
        
        # Distance from center bonus
        center_lat = (min_lat + max_lat) / 2
        center_lon = (min_lon + max_lon) / 2
        lat_distance = abs(latitude - center_lat)
        lon_distance = abs(longitude - center_lon)
        
        lat_range = max_lat - min_lat
        lon_range = max_lon - min_lon
        
        # Bonus for being near center
        if lat_distance < lat_range * 0.25 and lon_distance < lon_range * 0.25:
            confidence += 0.3  # Center 25%
        elif lat_distance < lat_range * 0.5 and lon_distance < lon_range * 0.5:
            confidence += 0.2  # Center 50%
        
        return min(confidence, 1.0)
    
    def _calculate_temporal_score(self, campaign_info: Dict[str, Any]) -> float:
        """Calculate temporal preference score (0.0 to 1.0, newer = higher)"""
        campaign_year = campaign_info.get("campaign_year", "unknown")
        
        if campaign_year == "unknown" or not campaign_year.isdigit():
            return 0.5  # Neutral score for unknown years
        
        year = int(campaign_year)
        current_year = 2024  # Approximate current year
        
        # Score based on recency (2020+ gets highest scores)
        if year >= 2020:
            return 1.0  # Very recent
        elif year >= 2015:
            return 0.8  # Recent  
        elif year >= 2010:
            return 0.6  # Moderate
        elif year >= 2005:
            return 0.4  # Older
        else:
            return 0.2  # Very old
    
    def _calculate_spatial_specificity(self, campaign_info: Dict[str, Any]) -> float:
        """Calculate spatial specificity score (0.0 to 1.0, smaller bounds = higher)"""
        bounds = campaign_info.get("bounds", {})
        if not bounds:
            return 0.0
        
        min_lat = bounds.get("min_lat", 999)
        max_lat = bounds.get("max_lat", -999)
        min_lon = bounds.get("min_lon", 999)
        max_lon = bounds.get("max_lon", -999)
        
        lat_range = max_lat - min_lat
        lon_range = max_lon - min_lon
        
        # Score based on coverage area (smaller = more specific)
        if lat_range < 0.1 and lon_range < 0.1:
            return 1.0  # Very specific (city-level)
        elif lat_range < 0.5 and lon_range < 0.5:
            return 0.8  # Specific (metropolitan area)
        elif lat_range < 1.0 and lon_range < 1.0:
            return 0.6  # Moderate (regional)
        elif lat_range < 2.0 and lon_range < 2.0:
            return 0.4  # Large (state-level)
        else:
            return 0.2  # Very large (multi-state)
    
    def find_files_for_coordinate(self, latitude: float, longitude: float, 
                                max_campaigns: int = 1) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Find files using smart campaign selection with tiled optimization.
        
        Phase 3 optimization strategy:
        1. Use tiled index for Brisbane metro area (ultra-fast)
        2. Use enhanced campaign selection for other areas
        3. Apply confidence thresholding for single vs multi-campaign selection
        4. Achieve target performance through smart selection
        
        Args:
            latitude: Point latitude in WGS84
            longitude: Point longitude in WGS84
            max_campaigns: Maximum campaigns to search (default: 1 for optimization)
            
        Returns:
            Tuple of (matching_files, campaign_ids_searched)
        """
        # Try tiled search for Brisbane metro area first
        if self._is_brisbane_metro(latitude, longitude) and self.tiled_index:
            return self._search_tiled_index(latitude, longitude)
        
        # Fallback to campaign-based selection
        return self._search_campaign_index(latitude, longitude, max_campaigns)
    
    def _search_tiled_index(self, latitude: float, longitude: float) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Search using tiled index for maximum performance"""
        matching_tiles = []
        
        for tile_id, tile_info in self.tiled_index["datasets"].items():
            if not tile_info.get("is_tile", False):
                continue  # Skip non-tile datasets
            
            if self._coordinate_in_bounds(latitude, longitude, tile_info.get("bounds", {})):
                matching_tiles.append((tile_id, tile_info))
        
        if not matching_tiles:
            logger.warning(f"No tiles found for Brisbane metro coordinate ({latitude}, {longitude})")
            return [], []
        
        # Sort by file count (prefer smallest tiles)
        matching_tiles.sort(key=lambda x: len(x[1].get("files", [])))
        
        # Use the smallest tile for maximum performance
        best_tile_id, best_tile = matching_tiles[0]
        tile_files = best_tile.get("files", [])
        
        matching_files = []
        for file_info in tile_files:
            if self._file_contains_coordinate(file_info, latitude, longitude):
                matching_files.append(file_info)
        
        logger.info(f"Tiled search: {best_tile_id} ({len(tile_files)} files), found {len(matching_files)} matches")
        return matching_files, [best_tile_id]
    
    def _search_campaign_index(self, latitude: float, longitude: float, 
                             max_campaigns: int) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Search using campaign-based selection with confidence thresholding"""
        # Get the best campaign matches
        campaign_matches = self.select_campaigns_for_coordinate(latitude, longitude)
        
        if not campaign_matches:
            logger.warning(f"No campaigns selected for coordinate ({latitude}, {longitude})")
            return [], []
        
        # Enhanced confidence thresholding strategy
        top_match = campaign_matches[0]
        
        # High-confidence single selection (total score > 0.8)
        if top_match.total_score >= 0.8:
            selected_campaigns = campaign_matches[:1]
            logger.info(f"High-confidence single campaign: {top_match.campaign_id} (score: {top_match.total_score:.3f})")
        # Medium-confidence multi selection (0.5 < score < 0.8)
        elif top_match.total_score >= 0.5:
            selected_campaigns = campaign_matches[:min(2, max_campaigns)]
            logger.info(f"Medium-confidence multi-campaign: {[c.campaign_id for c in selected_campaigns]}")
        # Low-confidence broad search
        else:
            selected_campaigns = campaign_matches[:min(3, max_campaigns)]
            logger.info(f"Low-confidence broad search: {[c.campaign_id for c in selected_campaigns]}")
        
        matching_files = []
        campaigns_searched = []
        
        for campaign_match in selected_campaigns:
            campaign_id = campaign_match.campaign_id
            campaign_files = campaign_match.campaign_info.get("files", [])
            campaigns_searched.append(campaign_id)
            
            logger.debug(f"Searching {len(campaign_files)} files in campaign '{campaign_id}'")
            
            # Search for files containing the coordinate
            for file_info in campaign_files:
                if self._file_contains_coordinate(file_info, latitude, longitude):
                    matching_files.append(file_info)
        
        total_files_searched = sum(len(self.campaign_index["datasets"][cs].get("files", [])) 
                                 for cs in campaigns_searched if cs in self.campaign_index["datasets"])
        logger.info(f"Campaign selection: searched {total_files_searched} files across {len(campaigns_searched)} campaigns, "
                   f"found {len(matching_files)} matches")
        
        return matching_files, campaigns_searched
    
    def _file_contains_coordinate(self, file_info: Dict[str, Any], 
                                 latitude: float, longitude: float) -> bool:
        """Check if a file's bounds contain the given coordinate"""
        bounds = file_info.get("bounds", {})
        if not bounds:
            return False
        
        min_lat = bounds.get("min_lat", 999)
        max_lat = bounds.get("max_lat", -999)
        min_lon = bounds.get("min_lon", 999)
        max_lon = bounds.get("max_lon", -999)
        
        return (min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for the campaign index"""
        if not self.campaign_index or "datasets" not in self.campaign_index:
            return {}
        
        campaigns = self.campaign_index["datasets"]
        total_files = sum(len(c.get("files", [])) for c in campaigns.values())
        
        # Calculate regional statistics
        brisbane_campaigns = [c for c in campaigns.values() if c.get("geographic_region") == "brisbane_metro"]
        sydney_campaigns = [c for c in campaigns.values() if c.get("geographic_region") == "sydney_metro"]
        
        return {
            "total_campaigns": len(campaigns),
            "total_files": total_files,
            "brisbane_metro_campaigns": len(brisbane_campaigns),
            "brisbane_metro_files": sum(len(c.get("files", [])) for c in brisbane_campaigns),
            "sydney_metro_campaigns": len(sydney_campaigns),
            "sydney_metro_files": sum(len(c.get("files", [])) for c in sydney_campaigns),
            "average_files_per_campaign": total_files / len(campaigns) if campaigns else 0
        }