"""
Collection Handler Strategy Pattern
Implements Gemini's recommendation for extensible collection-specific logic with CRS-aware spatial queries
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, Protocol
import logging

from ..models.unified_spatial_models import (
    DataCollection, AustralianUTMCollection,
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
        
        # Special debug for Auckland
        is_auckland = abs(lat - (-36.8485)) < 0.001 and abs(lon - 174.7633) < 0.001
        
        for i, file_entry in enumerate(collection.files):
            bounds = file_entry.bounds
            
            # Debug first file for Auckland in NZ collections
            if is_auckland and i == 0 and hasattr(collection, 'country') and getattr(collection, 'country', None) == 'NZ':
                logger.debug(f"NZ file bounds check for {collection.name}:")
                logger.debug(f"  File: {file_entry.path.split('/')[-1] if hasattr(file_entry, 'path') else 'unknown'}")
                logger.debug(f"  Bounds type: {type(bounds)}")
                logger.debug(f"  Has min_lat attr: {hasattr(bounds, 'min_lat')}")
                logger.debug(f"  Is dict: {isinstance(bounds, dict)}")
                if hasattr(bounds, 'min_lat'):
                    logger.debug(f"  Bounds: lat [{bounds.min_lat:.4f}, {bounds.max_lat:.4f}], lon [{bounds.min_lon:.4f}, {bounds.max_lon:.4f}]")
                    logger.debug(f"  Auckland ({lat:.4f}, {lon:.4f}) in bounds: {bounds.min_lat <= lat <= bounds.max_lat and bounds.min_lon <= lon <= bounds.max_lon}")
            
            # Check both dict access and attribute access for compatibility
            if hasattr(bounds, 'min_lat') and hasattr(bounds, 'min_lon'):
                # Pydantic model with attributes
                if (bounds.min_lat <= lat <= bounds.max_lat and
                    bounds.min_lon <= lon <= bounds.max_lon):
                    candidates.append(file_entry)
                    if is_auckland and hasattr(collection, 'country') and getattr(collection, 'country', None) == 'NZ':
                        logger.info(f"✅ Found NZ file for Auckland: {file_entry.path.split('/')[-1]}")
            elif isinstance(bounds, dict) and 'min_lat' in bounds and 'min_lon' in bounds:
                # Plain dict (for backwards compatibility)
                if (bounds['min_lat'] <= lat <= bounds['max_lat'] and
                    bounds['min_lon'] <= lon <= bounds['max_lon']):
                    candidates.append(file_entry)
                    if is_auckland and hasattr(collection, 'country') and getattr(collection, 'country', None) == 'NZ':
                        logger.info(f"✅ Found NZ file for Auckland (dict): {file_entry.get('path', '').split('/')[-1]}")
        
        if len(candidates) == 0 and len(collection.files) > 0:
            # Debug logging if no files found but collection has files
            first_file = collection.files[0]
            logger.debug(f"No files found in collection {collection.id} for ({lat}, {lon}). "
                       f"First file bounds type: {type(first_file.bounds)}, "
                       f"hasattr min_lat: {hasattr(first_file.bounds, 'min_lat')}, "
                       f"isinstance dict: {isinstance(first_file.bounds, dict)}")
        
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
        # IMPORTANT: Check country first to avoid handling NZ collections
        # Only handle Australian collections (AU country)
        if hasattr(collection, 'country'):
            return getattr(collection, 'country', None) == 'AU'
            
        # Fallback: Handle Australian collections that have campaign_name (individual campaigns)
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
            
            # Check if projected point is within bounds  
            bounds = collection.coverage_bounds
            
            # Handle both UTM bounds (min_x/max_x/min_y/max_y) and WGS84 bounds (min_lat/max_lat/min_lon/max_lon)
            if hasattr(bounds, 'min_x') and hasattr(bounds, 'min_y'):
                # UTM bounds format (transformed data)
                is_inside = (bounds.min_x <= projected_point.x <= bounds.max_x and
                            bounds.min_y <= projected_point.y <= bounds.max_y)
                logger.debug(f"Using UTM bounds: x={bounds.min_x:.0f}-{bounds.max_x:.0f}, y={bounds.min_y:.0f}-{bounds.max_y:.0f}")
            else:
                # Legacy WGS84 bounds format (assume they represent UTM coordinates in lat/lon fields)
                is_inside = (bounds.min_lon <= projected_point.x <= bounds.max_lon and
                            bounds.min_lat <= projected_point.y <= bounds.max_lat)
                logger.debug(f"Using legacy UTM bounds: x={bounds.min_lon:.0f}-{bounds.max_lon:.0f}, y={bounds.min_lat:.0f}-{bounds.max_lat:.0f}")
            
            if is_inside:
                logger.debug(f"✅ Collection {collection.campaign_name} contains UTM point ({projected_point.x:.1f}, {projected_point.y:.1f})")
            else:
                logger.debug(f"❌ Collection {collection.campaign_name} does NOT contain UTM point ({projected_point.x:.1f}, {projected_point.y:.1f})")
            
            return is_inside
            
        except Exception as e:
            logger.error(f"CRS transformation failed for collection {collection.id}: {e}")
            # Graceful degradation - check if we can still do WGS84 bounds checking
            bounds = collection.coverage_bounds
            if hasattr(bounds, 'min_lat') and hasattr(bounds, 'min_lon'):
                # WGS84 bounds available
                return (bounds.min_lat <= query_point.wgs84.lat <= bounds.max_lat and
                       bounds.min_lon <= query_point.wgs84.lon <= bounds.max_lon)
            else:
                # UTM bounds only - cannot do WGS84 fallback safely
                logger.warning(f"Collection {collection.id} has UTM bounds but CRS transformation failed - skipping")
                return False
    
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
                    
                    # Check if point intersects file bounds
                    if hasattr(bounds, 'min_x') and hasattr(bounds, 'min_y'):
                        # UTM bounds format - use projected coordinates
                        is_inside = (bounds.min_x <= projected_point.x <= bounds.max_x and
                                    bounds.min_y <= projected_point.y <= bounds.max_y)
                    else:
                        # WGS84 bounds format - use original WGS84 coordinates for file bounds
                        is_inside = (bounds.min_lat <= lat <= bounds.max_lat and
                                    bounds.min_lon <= lon <= bounds.max_lon)
                    
                    if is_inside:
                        candidates.append(file_entry)
                        logger.debug(f"✅ File {file_entry.filename} contains UTM point ({projected_point.x:.1f}, {projected_point.y:.1f})")
                except Exception as e:
                    logger.error(f"CRS transformation failed for file {getattr(file_entry, 'filename', 'unknown')}: {e}")
                    # Fallback to standard bounds checking if WGS84 bounds available
                    bounds = file_entry.bounds
                    if hasattr(bounds, 'min_lat') and hasattr(bounds, 'min_lon'):
                        if (bounds.min_lat <= lat <= bounds.max_lat and
                            bounds.min_lon <= lon <= bounds.max_lon):
                            candidates.append(file_entry)
                    # If UTM bounds only, skip this file in fallback
            else:
                # Standard WGS84 bounds checking (fallback)
                bounds = file_entry.bounds
                if hasattr(bounds, 'min_lat') and hasattr(bounds, 'min_lon'):
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
        # Check for NZ collections by country attribute
        # This works for both unified v2.0 format and any other NZ collection types
        if hasattr(collection, 'country') and getattr(collection, 'country', None) == 'NZ':
            return True
            
        # Also check for specific type if available
        try:
            from src.models.unified_wgs84_models import NewZealandUnifiedCollection
            return isinstance(collection, NewZealandUnifiedCollection)
        except (ImportError, TypeError):
            return False
    
    def get_collection_priority(self, collection: DataCollection, lat: float, lon: float) -> float:
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
        
        # Debug for Auckland NZ
        is_auckland_nz = (hasattr(collection, 'country') and getattr(collection, 'country', None) == 'NZ' and
                         hasattr(collection, 'id') and collection.id == '35bb9ab2-3767-45ec-b1a6-8674dd5caf2a')
        
        if is_auckland_nz:
            logger.info(f"🔍 Finding handler for top NZ collection {collection.id}")
            logger.info(f"  Available handlers: {[h.__class__.__name__ for h in self.handlers]}")
        
        # CRITICAL FIX: Check for NZ country first, regardless of type
        if hasattr(collection, 'country') and getattr(collection, 'country', None) == 'NZ':
            # Return the NZ handler directly
            for handler in self.handlers:
                if isinstance(handler, NewZealandCampaignHandler):
                    if is_auckland_nz:
                        logger.info(f"  ✅ Force-selected: NewZealandCampaignHandler for NZ country")
                    return handler
        
        for handler in self.handlers:
            can_handle = handler.can_handle(collection)
            if is_auckland_nz:
                logger.info(f"  {handler.__class__.__name__}.can_handle() = {can_handle}")
            if can_handle:
                if is_auckland_nz:
                    logger.info(f"  ✅ Selected: {handler.__class__.__name__}")
                return handler
        
        logger.warning(f"No handler found for collection {collection.id} (type: {getattr(collection, 'collection_type', 'unknown')}, country: {getattr(collection, 'country', 'unknown')})")
        return None
    
    def find_files_for_coordinate(self, collection: DataCollection, lat: float, lon: float) -> List[FileEntry]:
        """Find files using the appropriate handler"""
        
        # ALWAYS log for Auckland NZ to debug
        is_auckland = abs(lat - (-36.8485)) < 0.001 and abs(lon - 174.7633) < 0.001
        is_nz = hasattr(collection, 'country') and getattr(collection, 'country', None) == 'NZ'
        
        if is_auckland and is_nz:
            logger.info(f"🔍🔍 Processing NZ collection {collection.id} for Auckland")
            logger.info(f"  Collection country: {getattr(collection, 'country', 'MISSING')}")
            logger.info(f"  Collection type: {getattr(collection, 'collection_type', 'MISSING')}")
        
        handler = self.get_handler_for_collection(collection)
        
        if is_auckland and is_nz:
            logger.info(f"  Selected handler: {handler.__class__.__name__ if handler else 'NONE'}")
            if handler:
                logger.info(f"  Files in collection: {len(getattr(collection, 'files', []))}")
        
        if not handler:
            logger.warning(f"No handler for collection {collection.id} (type: {getattr(collection, 'collection_type', 'unknown')})")
            return []
        
        files = handler.find_files_for_coordinate(collection, lat, lon)
        
        # Debug result for NZ
        if (hasattr(collection, 'country') and getattr(collection, 'country', None) == 'NZ' and
            abs(lat - (-36.8485)) < 0.001 and abs(lon - 174.7633) < 0.001):
            logger.info(f"  Files found: {len(files)}")
            if len(files) == 0 and len(getattr(collection, 'files', [])) > 0:
                # Check first file bounds
                first_file = collection.files[0]
                bounds = first_file.bounds
                logger.info(f"  First file bounds type: {type(bounds)}")
                logger.info(f"  First file bounds: {bounds}")
        
        return files
    
    def get_collection_priority(self, collection: DataCollection, lat: float, lon: float) -> float:
        """Get collection priority using the appropriate handler"""
        handler = self.get_handler_for_collection(collection)
        if not handler:
            # CRITICAL FIX: NZ collections misclassified as AustralianUTMCollection
            # Check if this is actually an NZ collection by country attribute
            if hasattr(collection, 'country') and getattr(collection, 'country', None) == 'NZ':
                # Use NZ handler logic directly
                base_priority = 1.0
                if hasattr(collection, 'resolution_m'):
                    base_priority = 1.0 / collection.resolution_m
                
                # Boost NZ collections significantly for NZ coordinates
                if (-47.5 <= lat <= -34.0) and (166.0 <= lon <= 179.0):
                    base_priority *= 100.0  # Massive boost for NZ collections in NZ
                
                # Prefer DEM over DSM
                if hasattr(collection, 'data_type'):
                    if collection.data_type == "DEM":
                        base_priority *= 1.3
                
                return base_priority
            
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
                # Check bounds format to determine which bounds checking method to use
                bounds = collection.coverage_bounds
                
                # Handle both dictionary and object bounds formats
                if isinstance(bounds, dict):
                    has_wgs84_bounds = ('min_lat' in bounds and 'max_lat' in bounds and
                                       'min_lon' in bounds and 'max_lon' in bounds)
                    has_utm_bounds = ('min_x' in bounds and 'max_x' in bounds and
                                     'min_y' in bounds and 'max_y' in bounds)
                else:
                    has_wgs84_bounds = (hasattr(bounds, 'min_lat') and hasattr(bounds, 'max_lat') and
                                       hasattr(bounds, 'min_lon') and hasattr(bounds, 'max_lon'))
                    has_utm_bounds = (hasattr(bounds, 'min_x') and hasattr(bounds, 'max_x') and
                                     hasattr(bounds, 'min_y') and hasattr(bounds, 'max_y'))
                
                # Use CRS-aware bounds checking only for AU collections with UTM bounds
                if (isinstance(collection, AustralianUTMCollection) and 
                    hasattr(collection, 'epsg') and self.crs_service and has_utm_bounds):
                    
                    # Get the appropriate handler for CRS-aware checking
                    handler = self.get_handler_for_collection(collection)
                    if (isinstance(handler, AustralianCampaignHandler) and 
                        not handler._is_point_in_collection_bounds(collection, query_point)):
                        continue
                elif has_wgs84_bounds:
                    # Standard WGS84 bounds checking for all collections with WGS84 bounds
                    # Handle both dictionary and object access patterns
                    if isinstance(bounds, dict):
                        if not (bounds['min_lat'] <= lat <= bounds['max_lat'] and
                               bounds['min_lon'] <= lon <= bounds['max_lon']):
                            continue
                    else:
                        if not (bounds.min_lat <= lat <= bounds.max_lat and
                               bounds.min_lon <= lon <= bounds.max_lon):
                            continue
                else:
                    # Skip collections with unknown bounds format
                    logger.warning(f"Collection {collection.id} has unknown bounds format")
                    continue
                
                # Get priority score
                priority = self.get_collection_priority(collection, lat, lon)
                collection_scores.append((collection, priority))
                
                # Debug logging for NZ collections
                if hasattr(collection, 'country') and getattr(collection, 'country', None) == 'NZ':
                    logger.info(f"✅ NZ collection {collection.id} passed bounds check for Auckland ({lat}, {lon})")
                
            except Exception as e:
                logger.error(f"Failed to process collection {collection.id}: {e}")
                continue
        
        # Sort by priority (highest first) and limit results
        collection_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Debug logging for Auckland coordinate
        if abs(lat - (-36.8485)) < 0.0001 and abs(lon - 174.7633) < 0.0001:
            nz_in_scores = [c for c, _ in collection_scores if hasattr(c, 'country') and getattr(c, 'country', None) == 'NZ']
            logger.info(f"🔍 Auckland search: Found {len(nz_in_scores)} NZ collections out of {len(collection_scores)} total eligible")
            if nz_in_scores:
                first_nz = nz_in_scores[0]
                logger.info(f"  Top NZ: {getattr(first_nz, 'survey_name', first_nz.id)}")
        
        logger.info(f"Found {len(collection_scores)} eligible collections for ({lat}, {lon}), returning top {max_collections}")
        return collection_scores[:max_collections]