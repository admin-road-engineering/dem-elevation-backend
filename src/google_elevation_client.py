"""
Google Elevation API Client - Final fallback for elevation queries
Not included in coverage maps as it's a transparent fallback
"""
import os
import httpx
import asyncio
from typing import Optional, Dict
import logging
from datetime import datetime, timedelta
from .redis_state_manager import RedisStateManager, RedisRateLimiter

logger = logging.getLogger(__name__)

class GoogleElevationClient:
    """
    Google Elevation API client for final fallback
    
    Features:
    - Simple, reliable global coverage
    - Rate limiting aware (2,500 requests/day free tier)
    - Caching to minimize API calls
    - Not advertised in coverage maps
    """
    
    def __init__(self, api_key: Optional[str] = None, redis_manager: Optional[RedisStateManager] = None):
        self.api_key = api_key or os.getenv("GOOGLE_ELEVATION_API_KEY")
        self.base_url = "https://maps.googleapis.com/maps/api/elevation/json"
        self._client = None
        
        # Redis-based rate limiting
        self.redis_manager = redis_manager if redis_manager else RedisStateManager()
        self.rate_limiter = RedisRateLimiter(
            self.redis_manager,
            service_name="google_elevation",
            requests_per_second=1,  # Conservative rate limiting
            daily_limit=2500
        )
        
        if not self.api_key:
            logger.warning("Google Elevation API key not configured - fallback unavailable")
    
    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy initialization of HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client
    
    async def get_elevation(self, lat: float, lon: float) -> Optional[float]:
        """
        Get elevation from Google as final fallback
        
        Returns None if:
        - No API key configured
        - Rate limit exceeded
        - API error
        """
        if not self.api_key:
            return None
        
        # Check rate limits with Redis
        await self.rate_limiter.wait_if_needed()
        
        try:
            params = {
                "locations": f"{lat},{lon}",
                "key": self.api_key
            }
            
            response = await self.client.get(self.base_url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("status") == "OK" and data.get("results"):
                elevation = data["results"][0].get("elevation")
                
                stats = self.rate_limiter.get_usage_stats()
                logger.info(
                    f"Google Elevation fallback used for ({lat}, {lon}): "
                    f"{elevation}m (daily requests: {stats['daily_requests_used']}/{stats['daily_limit']})"
                )
                
                return elevation
            else:
                logger.error(f"Google Elevation API error: {data.get('status')}")
                return None
                
        except Exception as e:
            logger.error(f"Google Elevation API request failed: {e}")
            return None
    
    def can_make_request(self) -> bool:
        """Check if we can make a request (within daily limits)"""
        if not self.api_key:
            return False
        
        stats = self.rate_limiter.get_usage_stats()
        return stats["requests_remaining"] > 0
    
    async def get_elevation_async(self, lat: float, lon: float) -> Optional[float]:
        """Async wrapper for get_elevation to match interface"""
        return await self.get_elevation(lat, lon)
    
    async def close(self):
        """Close the HTTP client"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def get_info(self) -> Dict:
        """
        Get fallback service info (not included in coverage maps)
        """
        stats = self.rate_limiter.get_usage_stats()
        return {
            "provider": "Google Elevation API",
            "coverage": "Global",
            "resolution_m": 10,  # Approximate
            "accuracy": "±3m",
            "visible_in_coverage": False,  # Key flag
            "daily_limit": stats["daily_limit"],
            "requests_today": stats["daily_requests_used"],
            "cost_per_query": 0.0  # Free tier
        }