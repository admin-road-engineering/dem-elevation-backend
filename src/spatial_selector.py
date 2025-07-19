"""
Spatial Source Selector with Enhanced Tie-Breaking Logic
Implements Phase 2 of SPATIAL_COVERAGE_IMPLEMENTATION_PLAN_V2.md
"""
from typing import List, Dict, Optional, Tuple
import logging
from src.coverage_database import CoverageDatabase

logger = logging.getLogger(__name__)

class AutomatedSourceSelector:
    """
    Automated source selection based on spatial coverage and priority
    
    Features:
    - Geographic bounds checking with edge case handling
    - Clear tie-breaking rules for deterministic selection
    - Input validation and comprehensive error handling
    - Performance optimized for real-time queries
    """
    
    def __init__(self, coverage_db: CoverageDatabase):
        """
        Initialize selector with coverage database
        
        Args:
            coverage_db: Configured coverage database instance
        """
        self.coverage_db = coverage_db
        self.sources = coverage_db.get_enabled_sources()
        self._selection_count = 0
        self._cache_hits = 0
        
        # Simple cache for repeated queries (LRU would be better for production)
        self._cache = {}
        self._cache_max_size = 1000
        
        logger.info(
            f"Spatial selector initialized with {len(self.sources)} enabled sources"
        )
    
    def select_best_source(self, lat: float, lon: float) -> Dict:
        """
        Select highest resolution source with clear tie-breaking rules
        
        Tie-breaking order:
        1. Priority (lower number = higher priority)
        2. Resolution (lower meters = better)
        3. Cost per query (lower = better)
        4. Alphabetical ID (for deterministic behavior)
        
        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees
            
        Returns:
            Dict containing selected source information
            
        Raises:
            ValueError: If coordinates are invalid or no coverage available
        """
        # Input validation
        self._validate_coordinates(lat, lon)
        
        # Check cache first
        cache_key = f"{lat:.6f},{lon:.6f}"
        if cache_key in self._cache:
            self._cache_hits += 1
            logger.debug(f"Cache hit for ({lat}, {lon})")
            return self._cache[cache_key]
        
        # Find covering sources
        covering_sources = self._get_covering_sources(lat, lon)
        
        if not covering_sources:
            raise ValueError(
                f"No elevation data coverage available for coordinates ({lat}, {lon}). "
                f"Searched {len(self.sources)} enabled sources."
            )
        
        # Sort with explicit tie-breaking rules
        best_source = min(
            covering_sources,
            key=lambda s: (
                s['priority'],           # Primary: Lower priority number = higher priority
                s['resolution_m'],       # Secondary: Lower resolution = better
                s['cost_per_query'],     # Tertiary: Lower cost = better
                s['id']                  # Quaternary: Alphabetical for determinism
            )
        )
        
        # Cache the result
        if len(self._cache) >= self._cache_max_size:
            # Simple cache eviction (remove oldest)
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        
        self._cache[cache_key] = best_source
        self._selection_count += 1
        
        logger.info(
            f"Selected source '{best_source['id']}' for ({lat:.6f}, {lon:.6f}): "
            f"priority={best_source['priority']}, "
            f"resolution={best_source['resolution_m']}m, "
            f"provider={best_source['provider']}"
        )
        
        return best_source
    
    def _validate_coordinates(self, lat: float, lon: float) -> None:
        """
        Validate coordinate inputs with comprehensive checking
        
        Args:
            lat: Latitude to validate
            lon: Longitude to validate
            
        Raises:
            ValueError: If coordinates are invalid
            TypeError: If coordinates are not numeric
        """
        # Type checking
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            raise TypeError(
                f"Coordinates must be numeric. Got lat={type(lat)}, lon={type(lon)}"
            )
        
        # Range checking
        if not (-90 <= lat <= 90):
            raise ValueError(
                f"Latitude must be between -90 and 90 degrees. Got: {lat}"
            )
        
        if not (-180 <= lon <= 180):
            raise ValueError(
                f"Longitude must be between -180 and 180 degrees. Got: {lon}"
            )
        
        # Check for special values
        if lat != lat or lon != lon:  # NaN check
            raise ValueError("Coordinates cannot be NaN")
        
        if abs(lat) == float('inf') or abs(lon) == float('inf'):
            raise ValueError("Coordinates cannot be infinite")
    
    def _get_covering_sources(self, lat: float, lon: float) -> List[Dict]:
        """
        Get all enabled sources that cover the given point
        
        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees
            
        Returns:
            List of source dictionaries that cover the point
        """
        covering = []
        
        for source in self.sources:
            if not source['enabled']:
                continue
                
            if self._point_in_bounds(lat, lon, source['bounds']):
                covering.append(source)
        
        logger.debug(f"Found {len(covering)} sources covering ({lat}, {lon})")
        return covering
    
    def _point_in_bounds(self, lat: float, lon: float, bounds: Dict) -> bool:
        """
        Check if point is within bounds with edge case handling
        
        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees
            bounds: Bounds dictionary from source configuration
            
        Returns:
            True if point is within bounds (inclusive boundaries)
            
        Raises:
            ValueError: If bounds type is unsupported
        """
        if bounds['type'] == 'bbox':
            # Inclusive boundaries (>= and <=) - points exactly on boundary are included
            return (
                bounds['min_lat'] <= lat <= bounds['max_lat'] and
                bounds['min_lon'] <= lon <= bounds['max_lon']
            )
        elif bounds['type'] == 'polygon':
            # Future enhancement: GeoJSON polygon support using shapely
            raise NotImplementedError(
                "Polygon bounds not yet implemented. Use 'bbox' type for now."
            )
        else:
            raise ValueError(f"Unknown bounds type: {bounds['type']}")
    
    def get_coverage_summary(self, lat: float, lon: float) -> Dict:
        """
        Get detailed coverage information for a point including all options
        
        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees
            
        Returns:
            Dict with coverage summary including best source and alternatives
        """
        self._validate_coordinates(lat, lon)
        
        covering_sources = self._get_covering_sources(lat, lon)
        
        if not covering_sources:
            return {
                "coordinates": {"lat": lat, "lon": lon},
                "best_source": None,
                "all_options": [],
                "total_sources": 0,
                "reason": "No coverage available at this location",
                "searched_sources": len(self.sources)
            }
        
        # Sort all options using same logic as selection
        sorted_sources = sorted(
            covering_sources,
            key=lambda s: (s['priority'], s['resolution_m'], s['cost_per_query'], s['id'])
        )
        
        best = sorted_sources[0]
        
        # Create selection reasoning
        if len(sorted_sources) == 1:
            reason = f"Only source available: '{best['id']}'"
        else:
            reason = (
                f"Selected '{best['id']}' from {len(sorted_sources)} options "
                f"(priority {best['priority']}, {best['resolution_m']}m resolution)"
            )
        
        return {
            "coordinates": {"lat": lat, "lon": lon},
            "best_source": best,
            "all_options": sorted_sources,
            "total_sources": len(sorted_sources),
            "reason": reason,
            "selection_criteria": {
                "primary": "priority",
                "secondary": "resolution_m", 
                "tertiary": "cost_per_query",
                "quaternary": "alphabetical_id"
            }
        }
    
    def get_selector_stats(self) -> Dict:
        """
        Get selector performance and usage statistics
        
        Returns:
            Dict with selector statistics
        """
        return {
            "total_selections": self._selection_count,
            "cache_hits": self._cache_hits,
            "cache_size": len(self._cache),
            "cache_hit_rate": (
                self._cache_hits / self._selection_count 
                if self._selection_count > 0 else 0
            ),
            "enabled_sources": len(self.sources),
            "total_configured_sources": len(self.coverage_db.sources)
        }
    
    def clear_cache(self) -> None:
        """Clear the selection cache"""
        self._cache.clear()
        logger.info("Selection cache cleared")
    
    def test_coverage_at_points(self, test_points: List[Tuple[float, float]]) -> Dict:
        """
        Test coverage at multiple points for validation
        
        Args:
            test_points: List of (lat, lon) tuples to test
            
        Returns:
            Dict with coverage test results
        """
        results = {
            "total_points": len(test_points),
            "covered_points": 0,
            "uncovered_points": [],
            "source_usage": {},
            "resolution_distribution": {}
        }
        
        for lat, lon in test_points:
            try:
                source = self.select_best_source(lat, lon)
                results["covered_points"] += 1
                
                # Track source usage
                source_id = source['id']
                results["source_usage"][source_id] = results["source_usage"].get(source_id, 0) + 1
                
                # Track resolution distribution
                resolution = source['resolution_m']
                results["resolution_distribution"][resolution] = (
                    results["resolution_distribution"].get(resolution, 0) + 1
                )
                
            except ValueError:
                results["uncovered_points"].append((lat, lon))
        
        results["coverage_percentage"] = (
            results["covered_points"] / results["total_points"] * 100
            if results["total_points"] > 0 else 0
        )
        
        return results