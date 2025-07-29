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
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GOOGLE_ELEVATION_API_KEY")
        self.base_url = "https://maps.googleapis.com/maps/api/elevation/json"
        self._client = None
        self._daily_requests = 0
        self._reset_time = None
        
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
            
        # Simple rate limit check (2,500/day for free tier)
        if self._daily_requests >= 2500:
            if self._reset_time and datetime.now() < self._reset_time:
                logger.warning("Google Elevation API daily limit reached")
                return None
            else:
                # Reset counter after 24 hours
                self._daily_requests = 0
                self._reset_time = datetime.now() + timedelta(days=1)
        
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
                self._daily_requests += 1
                
                logger.info(
                    f"Google Elevation fallback used for ({lat}, {lon}): "
                    f"{elevation}m (daily requests: {self._daily_requests}/2500)"
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
            
        # Check daily limit (2,500/day for free tier)
        if self._daily_requests >= 2500:
            if self._reset_time and datetime.now() < self._reset_time:
                return False
            else:
                # Reset counter after 24 hours
                self._daily_requests = 0
                self._reset_time = datetime.now() + timedelta(days=1)
        
        return True
    
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
        return {
            "provider": "Google Elevation API",
            "coverage": "Global",
            "resolution_m": 10,  # Approximate
            "accuracy": "±3m",
            "visible_in_coverage": False,  # Key flag
            "daily_limit": 2500,
            "requests_today": self._daily_requests,
            "cost_per_query": 0.0  # Free tier
        }