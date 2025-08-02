"""
Composite Data Source Pattern
Implements Gemini's recommended Composite pattern for fallback chains
"""
import logging
from typing import List, Dict, Any
import asyncio

from data_sources.base_source import BaseDataSource, ElevationResult

logger = logging.getLogger(__name__)

class FallbackDataSource(BaseDataSource):
    """
    Composite data source that tries multiple sources in order
    Implements the Composite pattern for clean fallback logic
    """
    
    def __init__(self, sources: List[BaseDataSource], name: str = "fallback"):
        """
        Initialize fallback data source
        
        Args:
            sources: List of data sources to try in order
            name: Name for this composite source
        """
        super().__init__()
        self.sources = sources
        self.name = name
        self.source_stats = {source.__class__.__name__: {"attempts": 0, "successes": 0} 
                           for source in sources}
        
        logger.info(f"FallbackDataSource '{name}' initialized with {len(sources)} sources: "
                   f"{[s.__class__.__name__ for s in sources]}")
    
    async def initialize(self) -> bool:
        """Initialize all component sources"""
        logger.info(f"Initializing FallbackDataSource '{self.name}'...")
        
        init_results = []
        for i, source in enumerate(self.sources):
            try:
                logger.debug(f"Initializing source {i+1}/{len(self.sources)}: {source.__class__.__name__}")
                result = await source.initialize()
                init_results.append(result)
                
                if result:
                    logger.debug(f"✅ Source {source.__class__.__name__} initialized successfully")
                else:
                    logger.warning(f"⚠️ Source {source.__class__.__name__} failed to initialize")
                    
            except Exception as e:
                logger.error(f"❌ Source {source.__class__.__name__} initialization error: {e}")
                init_results.append(False)
        
        # Consider successful if at least one source initialized
        success_count = sum(init_results)
        total_sources = len(self.sources)
        
        if success_count > 0:
            logger.info(f"✅ FallbackDataSource initialized: {success_count}/{total_sources} sources ready")
            return True
        else:
            logger.error(f"❌ FallbackDataSource failed: 0/{total_sources} sources initialized")
            return False
    
    async def get_elevation(self, lat: float, lon: float) -> ElevationResult:
        """
        Get elevation by trying sources in order until one succeeds
        """
        last_error = None
        attempts = []
        
        for i, source in enumerate(self.sources):
            source_name = source.__class__.__name__
            self.source_stats[source_name]["attempts"] += 1
            
            try:
                logger.debug(f"Trying source {i+1}/{len(self.sources)}: {source_name}")
                
                result = await source.get_elevation(lat, lon)
                
                # Track attempt
                attempts.append({
                    "source": source_name,
                    "success": result.elevation is not None,
                    "error": result.error
                })
                
                # If successful, return immediately
                if result.elevation is not None:
                    self.source_stats[source_name]["successes"] += 1
                    
                    # Enhance metadata with fallback information
                    result.metadata = result.metadata or {}
                    result.metadata.update({
                        "fallback_chain": self.name,
                        "source_position": i + 1,
                        "total_sources": len(self.sources),
                        "attempts": attempts
                    })
                    
                    logger.debug(f"✅ Elevation found via {source_name}: {result.elevation}m")
                    return result
                
                # Source returned None elevation, continue to next
                last_error = result.error or f"No elevation data from {source_name}"
                logger.debug(f"⚠️ {source_name} returned no elevation: {last_error}")
                
            except Exception as e:
                error_msg = f"Source {source_name} failed: {e}"
                last_error = error_msg
                logger.warning(error_msg)
                
                attempts.append({
                    "source": source_name,
                    "success": False,
                    "error": error_msg
                })
                
                continue
        
        # All sources failed
        logger.info(f"❌ All {len(self.sources)} sources failed for coordinate ({lat}, {lon})")
        
        return ElevationResult(
            elevation=None,
            error=f"All sources failed. Last error: {last_error}",
            source=f"fallback_{self.name}",
            metadata={
                "fallback_chain": self.name,
                "total_sources": len(self.sources),
                "attempts": attempts,
                "all_failed": True
            }
        )
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of all component sources"""
        logger.debug(f"Running health check for FallbackDataSource '{self.name}'")
        
        health_results = {}
        overall_healthy = False
        
        for source in self.sources:
            source_name = source.__class__.__name__
            try:
                source_health = await source.health_check()
                health_results[source_name] = source_health
                
                # Consider overall healthy if at least one source is healthy
                if source_health.get("status") == "healthy":
                    overall_healthy = True
                    
            except Exception as e:
                health_results[source_name] = {
                    "status": "error",
                    "error": str(e)
                }
        
        return {
            "status": "healthy" if overall_healthy else "degraded",
            "fallback_chain": self.name,
            "total_sources": len(self.sources),
            "healthy_sources": sum(1 for h in health_results.values() 
                                 if h.get("status") == "healthy"),
            "source_health": health_results,
            "statistics": self.source_stats
        }
    
    async def coverage_info(self) -> Dict[str, Any]:
        """Get combined coverage information from all sources"""
        coverage_results = {}
        
        for source in self.sources:
            source_name = source.__class__.__name__
            try:
                coverage = await source.coverage_info()
                coverage_results[source_name] = coverage
            except Exception as e:
                coverage_results[source_name] = {"error": str(e)}
        
        return {
            "fallback_chain": self.name,
            "total_sources": len(self.sources),
            "source_coverage": coverage_results
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics for the fallback chain"""
        return {
            "source_type": f"fallback_{self.name}",
            "total_sources": len(self.sources),
            "source_stats": self.source_stats,
            "success_rates": {
                source: (stats["successes"] / max(stats["attempts"], 1)) * 100
                for source, stats in self.source_stats.items()
            }
        }
    
    def add_source(self, source: BaseDataSource):
        """Add a new source to the fallback chain"""
        self.sources.append(source)
        self.source_stats[source.__class__.__name__] = {"attempts": 0, "successes": 0}
        logger.info(f"Added {source.__class__.__name__} to fallback chain '{self.name}'")
    
    def remove_source(self, source_class_name: str) -> bool:
        """Remove a source from the fallback chain by class name"""
        for i, source in enumerate(self.sources):
            if source.__class__.__name__ == source_class_name:
                removed_source = self.sources.pop(i)
                if source_class_name in self.source_stats:
                    del self.source_stats[source_class_name]
                logger.info(f"Removed {source_class_name} from fallback chain '{self.name}'")
                return True
        
        logger.warning(f"Source {source_class_name} not found in fallback chain '{self.name}'")
        return False