import httpx
import asyncio
from typing import List, Dict, Optional, Tuple
from pydantic import BaseModel
import logging
from datetime import datetime, timedelta
from .error_handling import RetryableError, NonRetryableError, SourceType
from .redis_state_manager import RedisStateManager, RedisRateLimiter

logger = logging.getLogger(__name__)

class GPXZConfig(BaseModel):
    """GPXZ.io API configuration"""
    api_key: str
    base_url: str = "https://api.gpxz.io"
    timeout: int = 8
    daily_limit: int = 100  # Free tier limit
    rate_limit_per_second: int = 1  # Free tier limit

class GPXZRateLimiter:
    """Rate limiter for GPXZ.io API calls"""
    
    def __init__(self, requests_per_second: int = 1):
        self.requests_per_second = requests_per_second
        self.last_request_time = 0
        self.daily_requests = 0
        self.last_reset_date = datetime.now().date()
    
    async def wait_if_needed(self):
        """Enforce rate limiting"""
        now = datetime.now()
        
        # Reset daily counter if new day
        if now.date() != self.last_reset_date:
            self.daily_requests = 0
            self.last_reset_date = now.date()
        
        # Check daily limit
        if self.daily_requests >= 100:  # Free tier daily limit
            raise NonRetryableError("GPXZ daily limit reached (100 requests)", SourceType.API)
        
        # Rate limiting
        current_time = now.timestamp()
        time_since_last = current_time - self.last_request_time
        min_interval = 1.0 / self.requests_per_second
        
        if time_since_last < min_interval:
            sleep_time = min_interval - time_since_last
            await asyncio.sleep(sleep_time)
        
        self.last_request_time = current_time
        self.daily_requests += 1

class GPXZClient:
    """Client for GPXZ.io elevation API with Redis-based rate limiting"""
    
    def __init__(self, config: GPXZConfig, redis_manager: Optional[RedisStateManager] = None):
        self.config = config
        self.redis_manager = redis_manager if redis_manager else RedisStateManager()
        self.rate_limiter = RedisRateLimiter(
            self.redis_manager, 
            service_name="gpxz",
            requests_per_second=config.rate_limit_per_second,
            daily_limit=config.daily_limit
        )
        self._client = None
    
    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy initialization of HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.config.timeout)
        return self._client
    
    async def get_elevation_point(self, lat: float, lon: float) -> Optional[float]:
        """Get elevation for a single point"""
        try:
            await self.rate_limiter.wait_if_needed()
            
            response = await self.client.get(
                f"{self.config.base_url}/v1/elevation/point",
                params={
                    "lat": lat,
                    "lon": lon,
                    "key": self.config.api_key
                }
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Check for elevation in result object (GPXZ API format)
            if "result" in data and "elevation" in data["result"]:
                elevation_m = data["result"]["elevation"]
                logger.info(f"GPXZ elevation for ({lat}, {lon}): {elevation_m}m from {data['result'].get('data_source', 'unknown')}")
                return elevation_m
            # Fallback to direct elevation field
            elif "elevation" in data:
                elevation_m = data["elevation"]
                logger.info(f"GPXZ elevation for ({lat}, {lon}): {elevation_m}m")
                return elevation_m
            
            logger.warning(f"GPXZ API returned unexpected format: {data}")
            return None
            
        except NonRetryableError:
            # Re-raise non-retryable errors (e.g., daily limit exceeded)
            raise
        except httpx.TimeoutException as e:
            logger.warning(f"GPXZ timeout for ({lat}, {lon}): {e}")
            raise RetryableError(f"GPXZ timeout: {e}", SourceType.API)
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                logger.warning(f"GPXZ server error for ({lat}, {lon}): {e}")
                raise RetryableError(f"GPXZ server error: {e}", SourceType.API)
            elif e.response.status_code == 429:
                logger.warning(f"GPXZ rate limit for ({lat}, {lon}): {e}")
                raise NonRetryableError(f"GPXZ rate limit exceeded: {e}", SourceType.API)
            elif e.response.status_code in [401, 403]:
                logger.error(f"GPXZ authentication error for ({lat}, {lon}): {e}")
                raise NonRetryableError(f"GPXZ authentication failed: {e}", SourceType.API)
            else:
                logger.error(f"GPXZ client error for ({lat}, {lon}): {e}")
                raise NonRetryableError(f"GPXZ client error: {e}", SourceType.API)
        except Exception as e:
            logger.error(f"GPXZ unexpected error for ({lat}, {lon}): {e}")
            raise RetryableError(f"GPXZ unexpected error: {e}", SourceType.API)
    
    async def get_elevation_batch(self, points: List[Tuple[float, float]]) -> List[Optional[float]]:
        """Get elevations for multiple points (using points endpoint)"""
        try:
            await self.rate_limiter.wait_if_needed()
            
            # Format points for API
            locations = [{"lat": lat, "lon": lon} for lat, lon in points]
            
            response = await self.client.post(
                f"{self.config.base_url}/v1/elevation/points",
                json={
                    "locations": locations,
                    "key": self.config.api_key
                }
            )
            
            response.raise_for_status()
            data = response.json()
            
            results = []
            for result in data.get("results", []):
                if "elevation" in result:
                    results.append(result["elevation"])
                else:
                    results.append(None)
            
            logger.info(f"GPXZ batch request: {len(points)} points, {sum(1 for r in results if r is not None)} successful")
            return results
            
        except Exception as e:
            logger.error(f"GPXZ batch API error: {e}")
            return [None] * len(points)
    
    async def get_usage_stats(self) -> Dict:
        """Get current usage statistics from Redis"""
        return self.rate_limiter.get_usage_stats()
    
    async def close(self):
        """Close the HTTP client"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None