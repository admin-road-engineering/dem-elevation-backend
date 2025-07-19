"""
Fallback elevation handler - Transparent final resort
"""
from typing import Optional, Dict
import logging
from .google_elevation_client import GoogleElevationClient

logger = logging.getLogger(__name__)

class FallbackElevationHandler:
    """
    Manages invisible fallback elevation sources
    These are NOT included in coverage maps or source selection
    """
    
    def __init__(self):
        self.google_client = GoogleElevationClient()
        self.fallback_attempts = 0
        self.fallback_successes = 0
    
    async def get_fallback_elevation(
        self, 
        lat: float, 
        lon: float,
        failed_sources: list
    ) -> Optional[Dict]:
        """
        Try fallback sources when all mapped sources fail
        
        Returns dict with elevation and metadata, or None
        """
        self.fallback_attempts += 1
        
        # Try Google Elevation API
        elevation = await self.google_client.get_elevation(lat, lon)
        
        if elevation is not None:
            self.fallback_successes += 1
            
            return {
                "elevation_m": elevation,
                "source": "fallback",  # Generic name
                "actual_source": "google_elevation",  # Internal tracking
                "resolution_m": 10,
                "accuracy": "±3m",
                "data_type": "SRTM/ASTER",
                "is_fallback": True,
                "failed_sources": failed_sources,
                "metadata": {
                    "note": "Elevation obtained from fallback source",
                    "primary_sources_attempted": len(failed_sources)
                }
            }
        
        # All fallbacks exhausted
        logger.error(
            f"All elevation sources failed for ({lat}, {lon}), "
            f"including fallback. Attempted: {failed_sources}"
        )
        
        return None
    
    def get_stats(self) -> Dict:
        """Get fallback usage statistics"""
        return {
            "fallback_attempts": self.fallback_attempts,
            "fallback_successes": self.fallback_successes,
            "success_rate": (
                self.fallback_successes / self.fallback_attempts 
                if self.fallback_attempts > 0 else 0
            ),
            "google_api_available": self.google_client.api_key is not None
        }
    
    async def close(self):
        await self.google_client.close()