"""
Collection Handler Strategy Pattern
Implements Gemini's recommendation for extensible collection-specific logic with CRS-aware spatial queries
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, Protocol
import logging

from ..models.unified_spatial_models import (
    DataCollection, AustralianUTMCollection, NewZealandCampaignCollection,
    FileEntry, CoverageBounds
)
from ..models.coordinates import QueryPoint, PointWGS84
from ..services.crs_service import CRSTransformationService

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

class AustralianCampaignHandler(BaseCollectionHandler):
    """Handler for individual Australian campaign collections with CRS-aware spatial queries"""
    
    def __init__(self, crs_service: Optional[CRSTransformationService] = None):
        """Initialize with optional CRS transformation service for dependency injection"""
        self.crs_service = crs_service
        
    def can_handle(self, collection: DataCollection) -> bool:
        # Handle Australian collections that have campaign_name (individual campaigns)
        return (isinstance(collection, AustralianUTMCollection) and 
                hasattr(collection, 'campaign_name') and 
                collection.campaign_name is not None)
    
    def _is_point_in_collection_bounds(self, collection: AustralianUTMCollection, 
                                     query_point: QueryPoint) -> bool:
        """Check if point is within collection bounds using CRS-aware transformation
        
        Implements Transform-Once pattern: uses existing projection if available,
        creates new projection if needed for the collection's EPSG code.
        """
        if not self.crs_service:
            # Fallback to WGS84 bounds checking (existing behavior)
            bounds = collection.coverage_bounds
            return (bounds.min_lat <= query_point.wgs84.lat <= bounds.max_lat and
                   bounds.min_lon <= query_point.wgs84.lon <= bounds.max_lon)
        
        # Get EPSG code from collection metadata
        epsg_code = getattr(collection, 'epsg', None)
        if not epsg_code:
            logger.warning(f"Collection {collection.id} missing EPSG code, falling back to WGS84")
            bounds = collection.coverage_bounds
            return (bounds.min_lat <= query_point.wgs84.lat <= bounds.max_lat and
                   bounds.min_lon <= query_point.wgs84.lon <= bounds.max_lon)
        
        try:
            # Transform point to collection's native CRS
            projected_point = query_point.get_or_create_projection(epsg_code, self.crs_service)
            
            # Check if projected point is within UTM bounds  
            bounds = collection.coverage_bounds
            # Note: bounds are stored as min_lat/max_lat but for UTM they represent y coordinates (northing)
            # and min_lon/max_lon represent x coordinates (easting)
            is_inside = (bounds.min_lon <= projected_point.x <= bounds.max_lon and
                        bounds.min_lat <= projected_point.y <= bounds.max_lat)
            
            if is_inside:
                logger.debug(f"✅ Collection {collection.id} contains UTM point ({projected_point.x:.1f}, {projected_point.y:.1f})")
            
            return is_inside
            
        except Exception as e:
            logger.error(f"CRS transformation failed for collection {collection.id}: {e}")
            # Graceful degradation to WGS84 bounds checking
            bounds = collection.coverage_bounds
            return (bounds.min_lat <= query_point.wgs84.lat <= bounds.max_lat and
                   bounds.min_lon <= query_point.wgs84.lon <= bounds.max_lon)
    
    def find_files_for_coordinate(self, collection: DataCollection, lat: float, lon: float) -> List[FileEntry]:
        """Find files with CRS-aware coordinate transformation (overrides base implementation)"""
        if not isinstance(collection, AustralianUTMCollection):
            return super().find_files_for_coordinate(collection, lat, lon)
        
        # Create QueryPoint for Transform-Once pattern
        query_point = QueryPoint(wgs84=PointWGS84(lat=lat, lon=lon))
        
        # Use CRS-aware bounds checking for file discovery
        candidates = []
        for file_entry in collection.files:
            # Create a temporary collection-like object with file bounds for bounds checking
            # Note: This is a simplification - in a more complex system, files might have their own CRS
            if self.crs_service and hasattr(collection, 'epsg'):
                epsg_code = collection.epsg
                try:
                    projected_point = query_point.get_or_create_projection(epsg_code, self.crs_service)
                    bounds = file_entry.bounds
                    
                    # Check if projected point intersects file bounds (UTM coordinates)
                    if (bounds.min_lon <= projected_point.x <= bounds.max_lon and
                        bounds.min_lat <= projected_point.y <= bounds.max_lat):
                        candidates.append(file_entry)
                        logger.debug(f"✅ File {file_entry.file_path} contains UTM point ({projected_point.x:.1f}, {projected_point.y:.1f})")
                except Exception as e:
                    logger.error(f"CRS transformation failed for file {file_entry.file_path}: {e}")
                    # Fallback to standard bounds checking
                    bounds = file_entry.bounds
                    if (bounds.min_lat <= lat <= bounds.max_lat and
                        bounds.min_lon <= lon <= bounds.max_lon):
                        candidates.append(file_entry)
            else:
                # Standard WGS84 bounds checking (fallback)
                bounds = file_entry.bounds
                if (bounds.min_lat <= lat <= bounds.max_lat and
                    bounds.min_lon <= lon <= bounds.max_lon):
                    candidates.append(file_entry)
        
        logger.info(f"Found {len(candidates)} files in collection {collection.id} for coordinate ({lat}, {lon})")
        return candidates
    
    def get_collection_priority(self, collection: AustralianUTMCollection, lat: float, lon: float) -> float:
        """Australian campaigns get priority based on survey year and region"""
        base_priority = super().get_collection_priority(collection, lat, lon)
        
        # Extract campaign info
        campaign_name = getattr(collection, 'campaign_name', '').lower()
        survey_year = getattr(collection, 'survey_year', 2020)
        
        # Brisbane campaign prioritization: newer surveys get higher priority
        if 'brisbane' in campaign_name:
            base_priority *= 10.0  # Brisbane gets massive boost (54,000x speedup)
            
            # Year-based prioritization for Brisbane
            if survey_year >= 2019:
                base_priority *= 3.0  # Brisbane_2019_Prj gets highest priority
            elif survey_year >= 2014:
                base_priority *= 2.0  # Brisbane_2014_LGA gets medium priority  
            elif survey_year >= 2009:
                base_priority *= 1.5  # Brisbane_2009_LGA gets lower priority
                
            logger.info(f"🏆 Brisbane campaign '{campaign_name}' ({survey_year}) priority: {base_priority}")
            
        # Other major city boosts
        elif any(city in campaign_name for city in ['sydney', 'melbourne', 'perth', 'adelaide']):
            base_priority *= 5.0
            
        # State-based priority adjustments
        state = getattr(collection, 'state', '')
        if state in ['QLD', 'NSW', 'VIC']:  # Major states
            base_priority *= 1.2
        elif state in ['WA', 'SA']:
            base_priority *= 1.1
            
        # Survey year recency bonus (newer is better)
        year_bonus = max(0, (survey_year - 2000) * 0.05)  # 5% bonus per year after 2000
        base_priority *= (1.0 + year_bonus)
        
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
    """Registry for managing collection handlers with CRS-aware spatial queries"""
    
    def __init__(self, crs_service: Optional[CRSTransformationService] = None):
        """Initialize with optional CRS service for dependency injection"""
        self.handlers: List[CollectionHandler] = []
        self.crs_service = crs_service
        
        # Register default handlers with CRS service injection
        self.register_handler(AustralianCampaignHandler(crs_service))  # Individual campaigns (higher priority)
        self.register_handler(AustralianUTMHandler())                  # UTM zones (fallback)
        self.register_handler(NewZealandCampaignHandler())
        
        logger.info(f"CollectionHandlerRegistry initialized with {len(self.handlers)} handlers, CRS service: {crs_service is not None}")
    
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
        """Find and rank the best collections with CRS-aware bounds checking"""
        collection_scores = []
        
        # Create QueryPoint for Transform-Once pattern
        query_point = QueryPoint(wgs84=PointWGS84(lat=lat, lon=lon))
        
        for collection in collections:
            try:
                # Handle Australian UTM collections with CRS-aware bounds checking
                if (isinstance(collection, AustralianUTMCollection) and 
                    hasattr(collection, 'epsg') and self.crs_service):
                    
                    # Get the appropriate handler for CRS-aware checking
                    handler = self.get_handler_for_collection(collection)
                    if (isinstance(handler, AustralianCampaignHandler) and 
                        not handler._is_point_in_collection_bounds(collection, query_point)):
                        continue
                else:
                    # Standard WGS84 bounds checking for NZ and other collections
                    bounds = collection.coverage_bounds
                    if not (bounds.min_lat <= lat <= bounds.max_lat and
                           bounds.min_lon <= lon <= bounds.max_lon):
                        continue
                
                # Get priority score
                priority = self.get_collection_priority(collection, lat, lon)
                collection_scores.append((collection, priority))
                
            except Exception as e:
                logger.error(f"Failed to process collection {collection.id}: {e}")
                continue
        
        # Sort by priority (highest first) and limit results
        collection_scores.sort(key=lambda x: x[1], reverse=True)
        logger.info(f"Found {len(collection_scores)} eligible collections for ({lat}, {lon}), returning top {max_collections}")
        return collection_scores[:max_collections]