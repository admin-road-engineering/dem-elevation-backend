"""
Google Elevation API Data Source implementation.

Phase 3B.3: Concrete implementation of DataSource for Google Elevation API.
Final fallback in the elevation data chain.
"""

import asyncio
import logging
import time
import httpx
from typing import Optional, Dict, Any

from ..interfaces import DataSource, CircuitBreaker
from .base_models import ElevationData, HealthStatus

logger = logging.getLogger(__name__)


class GoogleSource(DataSource):
    """
    Google Elevation API data source.
    
    Final fallback in elevation data chain providing global coverage.
    Uses Google's elevation service with SRTM and other datasets.
    """
    
    def __init__(
        self,
        circuit_breaker: CircuitBreaker,
        api_key: str,
        timeout_seconds: float = 15.0,
        name: str = "google_elevation"
    ):
        super().__init__(name, timeout_seconds, circuit_breaker)
        self.api_key = api_key
        self.base_url = "https://maps.googleapis.com/maps/api/elevation/json"
        self._client = None
        self._last_health_check = None
        self._is_healthy = True
    
    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy-initialized HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds)
            )
        return self._client
    
    async def close(self):
        """Close HTTP client resources."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def get_elevation(self, latitude: float, longitude: float) -> Optional[ElevationData]:
        """
        Get elevation from Google Elevation API.
        
        Process:
        1. Check circuit breaker status
        2. Make API request with timeout
        3. Parse response and return structured data
        4. Handle errors and update circuit breaker
        """
        start_time = time.time()
        
        # Check circuit breaker
        if await self.circuit_breaker.is_open(self.name):
            logger.debug(f"Google circuit breaker open, skipping for ({latitude}, {longitude})")
            return None
        
        try:
            response = await self.client.get(
                self.base_url,
                params={
                    "locations": f"{latitude},{longitude}",
                    "key": self.api_key
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('status') == 'OK' and data.get('results'):
                    result = data['results'][0]
                    elevation = result.get('elevation')
                    
                    if elevation is not None:
                        await self.circuit_breaker.record_success(self.name)
                        query_time = (time.time() - start_time) * 1000
                        
                        return ElevationData(
                            elevation=float(elevation),
                            latitude=latitude,
                            longitude=longitude,
                            source_name=self.name,
                            resolution_m=30.0,  # Typical Google resolution
                            accuracy='±16m',    # Google's stated accuracy
                            data_type='SRTM/Other',
                            message='Google Elevation API data',
                            provider='Google',
                            cost_per_query=0.005,
                            query_time_ms=query_time
                        )
                    else:
                        logger.debug(f"Google returned null elevation for ({latitude}, {longitude})")
                        return None
                
                elif data.get('status') == 'OVER_QUERY_LIMIT':
                    logger.warning("Google API quota exceeded")
                    await self.circuit_breaker.record_failure(self.name)
                    return None
                
                else:
                    logger.error(f"Google API error: {data.get('status')} - {data.get('error_message', '')}")
                    await self.circuit_breaker.record_failure(self.name)
                    return None
            
            else:
                logger.error(f"Google API HTTP error {response.status_code}: {response.text}")
                await self.circuit_breaker.record_failure(self.name)
                return None
                
        except httpx.TimeoutException:
            logger.warning(f"Google API timeout after {self.timeout_seconds}s for ({latitude}, {longitude})")
            await self.circuit_breaker.record_failure(self.name)
            return None
        except Exception as e:
            logger.error(f"Google API error for ({latitude}, {longitude}): {e}", exc_info=True)
            await self.circuit_breaker.record_failure(self.name)
            return None
    
    async def health_check(self) -> bool:
        """Check Google API health with test coordinates."""
        try:
            # Test with known coordinates (Mount Everest)
            test_lat, test_lon = 27.9881, 86.9250
            
            response = await self.client.get(
                self.base_url,
                params={
                    "locations": f"{test_lat},{test_lon}",
                    "key": self.api_key
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                if (data.get('status') == 'OK' and 
                    data.get('results') and 
                    data['results'][0].get('elevation') is not None):
                    self._is_healthy = True
                    self._last_health_check = time.time()
                    return True
            
            self._is_healthy = False
            return False
            
        except Exception as e:
            logger.error(f"Google health check failed: {e}")
            self._is_healthy = False
            return False
    
    def get_coverage_info(self) -> Dict[str, Any]:
        """Get Google API coverage information."""
        return {
            'source_name': self.name,
            'data_type': 'SRTM/Various',
            'resolution': '30m (typical)',
            'coverage_area': 'Global',
            'typical_accuracy': '±16m',
            'rate_limit': '2,500 requests/day (free)',
            'cost_model': 'Free tier + paid plans',
            'availability': '99.9%',
            'provider': 'Google'
        }
    
    def get_health_status(self) -> HealthStatus:
        """Get detailed health status."""
        return HealthStatus(
            source_name=self.name,
            is_healthy=self._is_healthy,
            last_check=str(self._last_health_check) if self._last_health_check else 'Never',
            response_time_ms=None,  # Would need to track this
            circuit_breaker_open=False  # Would need to check this async
        )