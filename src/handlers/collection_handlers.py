"""
Collection Handler Strategy Pattern
Implements Gemini's recommendation for extensible collection-specific logic
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, Protocol
import logging

from ..models.unified_spatial_models import (
    DataCollection, AustralianUTMCollection, NewZealandCampaignCollection,
    FileEntry, CoverageBounds
)

logger = logging.getLogger(__name__)

class CollectionHandler(Protocol):
    """Protocol for collection-specific handling logic"""
    
    def can_handle(self, collection: DataCollection) -> bool:
        """Check if this handler can process the given collection"""
        ...
    
    def find_files_for_coordinate(self, collection: DataCollection, lat: float, lon: float) -> List[FileEntry]:
        """Find files within collection that contain the coordinate"""
        ...
    
    def get_collection_priority(self, collection: DataCollection, lat: float, lon: float) -> float:
        """Get priority score for this collection (higher = more preferred)"""
        ...

class BaseCollectionHandler(ABC):
    """Base implementation for collection handlers"""
    
    @abstractmethod
    def can_handle(self, collection: DataCollection) -> bool:
        """Check if this handler can process the given collection"""
        pass
    
    def find_files_for_coordinate(self, collection: DataCollection, lat: float, lon: float) -> List[FileEntry]:
        """Default implementation using bounds checking"""
        candidates = []
        
        for file_entry in collection.files:
            bounds = file_entry.bounds
            if (bounds.min_lat <= lat <= bounds.max_lat and
                bounds.min_lon <= lon <= bounds.max_lon):
                candidates.append(file_entry)
        
        logger.debug(f"Found {len(candidates)} file candidates in collection {collection.id}")
        return candidates
    
    def get_collection_priority(self, collection: DataCollection, lat: float, lon: float) -> float:
        """Default priority based on resolution (higher resolution = higher priority)"""
        if hasattr(collection, 'resolution_m'):
            return 1.0 / collection.resolution_m  # Higher resolution = higher priority
        return 1.0

class AustralianUTMHandler(BaseCollectionHandler):
    """Handler for Australian UTM zone collections"""
    
    def can_handle(self, collection: DataCollection) -> bool:
        return isinstance(collection, AustralianUTMCollection)
    
    def get_collection_priority(self, collection: AustralianUTMCollection, lat: float, lon: float) -> float:
        """Australian collections get priority based on resolution and region"""
        base_priority = super().get_collection_priority(collection, lat, lon)
        
        # Boost priority for specific high-performance regions
        if collection.region and 'brisbane' in collection.region.lower():
            base_priority *= 1.5  # Brisbane gets 54,000x speedup
        elif collection.state in ['QLD', 'NSW', 'VIC']:  # Major states
            base_priority *= 1.2
        
        return base_priority

class NewZealandCampaignHandler(BaseCollectionHandler):
    """Handler for New Zealand campaign collections"""
    
    def can_handle(self, collection: DataCollection) -> bool:
        return isinstance(collection, NewZealandCampaignCollection)
    
    def get_collection_priority(self, collection: NewZealandCampaignCollection, lat: float, lon: float) -> float:
        """NZ collections get priority based on data type and survey year"""
        base_priority = super().get_collection_priority(collection, lat, lon)
        
        # Prefer DEM over DSM for elevation queries
        if collection.data_type == "DEM":
            base_priority *= 1.3
        elif collection.data_type == "DSM":
            base_priority *= 1.0
        else:  # UNKNOWN
            base_priority *= 0.8
        
        # Prefer newer surveys
        if collection.survey_years:
            latest_year = max(collection.survey_years)
            if latest_year >= 2020:
                base_priority *= 1.2
            elif latest_year >= 2015:
                base_priority *= 1.1
        
        return base_priority

class CollectionHandlerRegistry:
    """Registry for managing collection handlers"""
    
    def __init__(self):
        self.handlers: List[CollectionHandler] = []
        
        # Register default handlers
        self.register_handler(AustralianUTMHandler())
        self.register_handler(NewZealandCampaignHandler())
        
        logger.info(f"CollectionHandlerRegistry initialized with {len(self.handlers)} handlers")
    
    def register_handler(self, handler: CollectionHandler):
        """Register a new collection handler"""
        self.handlers.append(handler)
        logger.debug(f"Registered handler: {handler.__class__.__name__}")
    
    def get_handler_for_collection(self, collection: DataCollection) -> Optional[CollectionHandler]:
        """Get the appropriate handler for a collection"""
        for handler in self.handlers:
            if handler.can_handle(collection):
                return handler
        
        logger.warning(f"No handler found for collection type: {collection.collection_type}")
        return None
    
    def find_files_for_coordinate(self, collection: DataCollection, lat: float, lon: float) -> List[FileEntry]:
        """Find files using the appropriate handler"""
        handler = self.get_handler_for_collection(collection)
        if not handler:
            return []
        
        return handler.find_files_for_coordinate(collection, lat, lon)
    
    def get_collection_priority(self, collection: DataCollection, lat: float, lon: float) -> float:
        """Get collection priority using the appropriate handler"""
        handler = self.get_handler_for_collection(collection)
        if not handler:
            return 0.0
        
        return handler.get_collection_priority(collection, lat, lon)
    
    def find_best_collections(self, collections: List[DataCollection], lat: float, lon: float, 
                            max_collections: int = 5) -> List[Tuple[DataCollection, float]]:
        """Find and rank the best collections for a coordinate"""
        collection_scores = []
        
        for collection in collections:
            # First check if coordinate is within collection bounds
            bounds = collection.coverage_bounds
            if not (bounds.min_lat <= lat <= bounds.max_lat and
                   bounds.min_lon <= lon <= bounds.max_lon):
                continue
            
            # Get priority score
            priority = self.get_collection_priority(collection, lat, lon)
            collection_scores.append((collection, priority))
        
        # Sort by priority (highest first) and limit results
        collection_scores.sort(key=lambda x: x[1], reverse=True)
        return collection_scores[:max_collections]