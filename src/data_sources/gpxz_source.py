"""
GPXZ API Data Source implementation.

Phase 3B.3: Concrete implementation of DataSource for GPXZ.io API.
Provides global elevation data with circuit breaker protection.
"""

import asyncio
import logging
import time
import httpx
from typing import Optional, Dict, Any

from ..interfaces import DataSource, CircuitBreaker
from .base_models import ElevationData, HealthStatus

logger = logging.getLogger(__name__)


class GPXZSource(DataSource):
    """
    GPXZ.io API elevation data source.
    
    Provides global elevation coverage as fallback to S3 campaigns.
    Implements circuit breaker pattern for API resilience.
    """
    
    def __init__(
        self,
        circuit_breaker: CircuitBreaker,
        api_key: str,
        timeout_seconds: float = 8.0,
        name: str = "gpxz_api"
    ):
        super().__init__(name, timeout_seconds, circuit_breaker)
        self.api_key = api_key
        self.base_url = "https://api.gpxz.io/v1/elevation"
        self._client = None
        self._last_health_check = None
        self._is_healthy = True
    
    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy-initialized HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds),
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
        return self._client
    
    async def close(self):
        """Close HTTP client resources."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def get_elevation(self, latitude: float, longitude: float) -> Optional[ElevationData]:
        """
        Get elevation from GPXZ API.
        
        Process:
        1. Check circuit breaker status
        2. Make API request with timeout
        3. Parse response and return structured data
        4. Handle errors and update circuit breaker
        """
        start_time = time.time()
        
        # Check circuit breaker
        if await self.circuit_breaker.is_open(self.name):
            logger.debug(f"GPXZ circuit breaker open, skipping for ({latitude}, {longitude})")
            return None
        
        try:
            response = await self.client.get(
                self.base_url,
                params={
                    "lat": latitude,
                    "lon": longitude,
                    "format": "json"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                elevation = data.get('elevation')
                
                if elevation is not None:
                    await self.circuit_breaker.record_success(self.name)
                    query_time = (time.time() - start_time) * 1000
                    
                    return ElevationData(
                        elevation=float(elevation),
                        latitude=latitude,
                        longitude=longitude,
                        source_name=self.name,
                        resolution_m=30.0,  # SRTM resolution
                        accuracy='±10m',
                        data_type='SRTM',
                        message='GPXZ API elevation data',
                        provider='GPXZ.io',
                        cost_per_query=0.01,
                        query_time_ms=query_time
                    )
                else:
                    logger.debug(f"GPXZ returned null elevation for ({latitude}, {longitude})")
                    return None
            
            elif response.status_code == 429:
                # Rate limit exceeded
                logger.warning(f"GPXZ rate limit exceeded")
                await self.circuit_breaker.record_failure(self.name)
                return None
            
            else:
                logger.error(f"GPXZ API error {response.status_code}: {response.text}")
                await self.circuit_breaker.record_failure(self.name) 
                return None
                
        except httpx.TimeoutException:
            logger.warning(f"GPXZ API timeout after {self.timeout_seconds}s for ({latitude}, {longitude})")
            await self.circuit_breaker.record_failure(self.name)
            return None
        except Exception as e:
            logger.error(f"GPXZ API error for ({latitude}, {longitude}): {e}", exc_info=True)
            await self.circuit_breaker.record_failure(self.name)
            return None
    
    async def health_check(self) -> bool:
        """Check GPXZ API health with test coordinates."""
        try:
            # Test with known coordinates (Sydney Opera House)
            test_lat, test_lon = -33.8568, 151.2153
            
            response = await self.client.get(
                self.base_url,
                params={
                    "lat": test_lat,
                    "lon": test_lon,
                    "format": "json"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('elevation') is not None:
                    self._is_healthy = True
                    self._last_health_check = time.time()
                    return True
            
            self._is_healthy = False
            return False
            
        except Exception as e:
            logger.error(f"GPXZ health check failed: {e}")
            self._is_healthy = False
            return False
    
    def get_coverage_info(self) -> Dict[str, Any]:
        """Get GPXZ API coverage information."""
        return {
            'source_name': self.name,
            'data_type': 'SRTM',
            'resolution': '30m',
            'coverage_area': 'Global',
            'typical_accuracy': '±10m',
            'rate_limit': '100 requests/day',
            'cost_model': 'Free tier + paid plans',
            'availability': '99.5%',
            'provider': 'GPXZ.io'
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