"""
Unified Elevation Provider implementation.

Phase 3B.3: Orchestrates multiple DataSource strategies using Chain of Responsibility pattern.
Provides the main interface for elevation data retrieval with fallback chain.
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, List

from ..interfaces import ElevationProvider, DataSource
from .base_models import ElevationData, HealthStatus

logger = logging.getLogger(__name__)


class UnifiedElevationProvider(ElevationProvider):
    """
    Unified elevation provider implementing Chain of Responsibility pattern.
    
    Orchestrates multiple DataSource strategies in priority order:
    1. S3 campaigns (fastest, highest accuracy)
    2. GPXZ API (global coverage, medium speed)
    3. Google API (final fallback, comprehensive coverage)
    """
    
    def __init__(self, sources: List[DataSource]):
        super().__init__(sources)
        self._request_count = 0
        self._source_usage_stats = {}
        
        # Initialize usage tracking
        for source in sources:
            self._source_usage_stats[source.name] = {
                'requests': 0,
                'successes': 0,
                'failures': 0,
                'total_time_ms': 0.0
            }
    
    async def get_elevation(self, latitude: float, longitude: float) -> Optional[ElevationData]:
        """
        Get elevation using fallback chain.
        
        Tries each data source in priority order until one returns data.
        Tracks usage statistics for monitoring and optimization.
        """
        self._request_count += 1
        start_time = time.time()
        
        logger.debug(f"Getting elevation for ({latitude}, {longitude}) using {len(self.sources)} sources")
        
        for source in self.sources:
            try:
                source_start = time.time()
                result = await source.get_elevation(latitude, longitude)
                source_time = (time.time() - source_start) * 1000
                
                # Update statistics
                stats = self._source_usage_stats[source.name]
                stats['requests'] += 1
                stats['total_time_ms'] += source_time
                
                if result:
                    stats['successes'] += 1
                    total_time = (time.time() - start_time) * 1000
                    
                    logger.info(
                        f"Elevation found via {source.name}: {result.elevation}m "
                        f"for ({latitude}, {longitude}) in {total_time:.1f}ms"
                    )
                    
                    # Add total query time to result
                    result.query_time_ms = total_time
                    return result
                
                else:
                    # Source didn't have data, try next one
                    logger.debug(f"No data from {source.name} for ({latitude}, {longitude})")
                    continue
                    
            except Exception as e:
                # Update failure statistics
                self._source_usage_stats[source.name]['failures'] += 1
                logger.error(f"Error from {source.name} for ({latitude}, {longitude}): {e}")
                continue
        
        # No source provided data
        total_time = (time.time() - start_time) * 1000
        logger.warning(f"No elevation data found for ({latitude}, {longitude}) after {total_time:.1f}ms")
        return None
    
    async def get_elevation_batch(self, coordinates: List[tuple[float, float]]) -> List[Optional[ElevationData]]:
        """
        Get elevation for multiple coordinates efficiently.
        
        Currently processes sequentially, but could be optimized for concurrent processing
        with appropriate rate limiting per source.
        """
        results = []
        
        # Process coordinates sequentially to respect rate limits
        # TODO: Implement intelligent batching per source type
        for lat, lon in coordinates:
            result = await self.get_elevation(lat, lon)
            results.append(result)
        
        return results
    
    def get_available_sources(self) -> List[str]:
        """Get list of available data source names."""
        return [source.name for source in self.sources]
    
    async def health_check(self) -> Dict[str, Any]:
        """Get comprehensive health status of all data sources."""
        health_results = {}
        overall_healthy = True
        
        # Check each source concurrently
        health_tasks = []
        for source in self.sources:
            health_tasks.append(self._check_source_health(source))
        
        source_healths = await asyncio.gather(*health_tasks, return_exceptions=True)
        
        for i, source in enumerate(self.sources):
            health_result = source_healths[i]
            
            if isinstance(health_result, Exception):
                health_results[source.name] = {
                    'healthy': False,
                    'error': str(health_result),
                    'last_check': 'error'
                }
                overall_healthy = False
            else:
                health_results[source.name] = health_result
                if not health_result.get('healthy', False):
                    overall_healthy = False
        
        return {
            'overall_healthy': overall_healthy,
            'sources': health_results,
            'total_requests': self._request_count,
            'usage_statistics': self._get_usage_statistics()
        }
    
    async def _check_source_health(self, source: DataSource) -> Dict[str, Any]:
        """Check health of a single source."""
        try:
            start_time = time.time()
            is_healthy = await source.health_check()
            response_time = (time.time() - start_time) * 1000
            
            return {
                'healthy': is_healthy,
                'response_time_ms': response_time,
                'coverage_info': source.get_coverage_info(),
                'last_check': time.time()
            }
        except Exception as e:
            return {
                'healthy': False,
                'error': str(e),
                'last_check': time.time()
            }
    
    def _get_usage_statistics(self) -> Dict[str, Any]:
        """Get usage statistics for all sources."""
        stats = {}
        
        for source_name, source_stats in self._source_usage_stats.items():
            requests = source_stats['requests']
            successes = source_stats['successes']
            
            stats[source_name] = {
                'requests': requests,
                'successes': successes,
                'failures': source_stats['failures'],
                'success_rate': successes / requests if requests > 0 else 0,
                'avg_response_time_ms': (
                    source_stats['total_time_ms'] / requests 
                    if requests > 0 else 0
                )
            }
        
        return stats
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get detailed performance metrics for monitoring."""
        return {
            'total_requests': self._request_count,
            'source_count': len(self.sources),
            'source_names': self.get_available_sources(),
            'usage_statistics': self._get_usage_statistics(),
            'fallback_chain': [
                {
                    'name': source.name,
                    'timeout_seconds': source.timeout_seconds,
                    'coverage': source.get_coverage_info()
                }
                for source in self.sources
            ]
        }
    
    async def close(self):
        """Close all source connections."""
        for source in self.sources:
            if hasattr(source, 'close'):
                try:
                    await source.close()
                except Exception as e:
                    logger.error(f"Error closing {source.name}: {e}")