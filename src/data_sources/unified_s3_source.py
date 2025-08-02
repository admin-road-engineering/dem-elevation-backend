"""
Unified S3 Source with Collection Handler Strategy
Implements Gemini's recommended country-agnostic architecture
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import asyncio
from datetime import datetime

from ..models.unified_spatial_models import UnifiedSpatialIndex, DataCollection, FileEntry
from ..handlers import CollectionHandlerRegistry
from ..s3_client_factory import S3ClientFactory
from .base_source import BaseDataSource, ElevationResult

logger = logging.getLogger(__name__)

class UnifiedS3Source(BaseDataSource):
    """
    Unified S3 source using discriminated unions and collection handlers
    Country-agnostic elevation data source
    """
    
    def __init__(self, 
                 use_unified_index: bool = False,
                 unified_index_key: str = "indexes/unified_spatial_index_v2.json",
                 s3_client_factory: Optional[S3ClientFactory] = None):
        """
        Initialize unified S3 source
        
        Args:
            use_unified_index: If True, use unified v2.0 index
            unified_index_key: S3 key for unified index
            s3_client_factory: S3 client factory for AWS access
        """
        super().__init__()
        self.use_unified_index = use_unified_index
        self.unified_index_key = unified_index_key
        self.s3_client_factory = s3_client_factory
        
        # Core components
        self.unified_index: Optional[UnifiedSpatialIndex] = None
        self.handler_registry = CollectionHandlerRegistry()
        
        # Local fallback
        self.config_dir = Path("config")
        
        logger.info(f"UnifiedS3Source initialized (unified_index={use_unified_index})")
    
    async def initialize(self) -> bool:
        """Initialize the source by loading spatial indexes"""
        try:
            if self.use_unified_index:
                logger.info("🔄 Loading unified spatial index v2.0...")
                success = await self._load_unified_index_from_s3()
                if not success:
                    logger.warning("S3 loading failed, falling back to filesystem")
                    success = self._load_unified_index_from_filesystem()
            else:
                logger.info("📊 Using legacy index mode (unified disabled)")
                success = False  # Force fallback to legacy system
            
            if success:
                count = len(self.unified_index.data_collections) if self.unified_index else 0
                logger.info(f"✅ Unified index loaded: {count} collections")
            else:
                logger.warning("❌ Failed to load unified index")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to initialize UnifiedS3Source: {e}")
            return False
    
    async def get_elevation(self, lat: float, lon: float) -> ElevationResult:
        """Get elevation using unified collection handlers"""
        if not self.unified_index:
            return ElevationResult(
                elevation=None,
                error="Unified index not loaded",
                source="unified_s3",
                metadata={}
            )
        
        try:
            # Find best collections for coordinate
            best_collections = self.handler_registry.find_best_collections(
                self.unified_index.data_collections, lat, lon, max_collections=3
            )
            
            if not best_collections:
                return ElevationResult(
                    elevation=None,
                    error="No collections found for coordinate",
                    source="unified_s3",
                    metadata={"coordinate": (lat, lon)}
                )
            
            # Try each collection in priority order
            for collection, priority in best_collections:
                try:
                    # Find files within collection
                    candidate_files = self.handler_registry.find_files_for_coordinate(
                        collection, lat, lon
                    )
                    
                    if not candidate_files:
                        continue
                    
                    # Try to extract elevation from first file
                    for file_entry in candidate_files[:2]:  # Try top 2 files
                        elevation = await self._extract_elevation_from_file(
                            file_entry, lat, lon
                        )
                        
                        if elevation is not None:
                            return ElevationResult(
                                elevation=elevation,
                                error=None,
                                source="unified_s3",
                                metadata={
                                    "collection_id": collection.id,
                                    "collection_type": collection.collection_type,
                                    "country": collection.country,
                                    "file": file_entry.filename,
                                    "priority": priority
                                }
                            )
                
                except Exception as e:
                    logger.warning(f"Error processing collection {collection.id}: {e}")
                    continue
            
            return ElevationResult(
                elevation=None,
                error="Failed to extract elevation from available files",
                source="unified_s3",
                metadata={"collections_tried": len(best_collections)}
            )
            
        except Exception as e:
            logger.error(f"Error in unified elevation lookup: {e}")
            return ElevationResult(
                elevation=None,
                error=f"Unified elevation lookup failed: {e}",
                source="unified_s3",
                metadata={}
            )
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of unified S3 source"""
        health = {
            "status": "healthy",
            "unified_index_loaded": self.unified_index is not None,
            "use_unified_index": self.use_unified_index,
            "collection_count": 0,
            "total_files": 0,
            "countries": [],
            "collection_types": []
        }
        
        if self.unified_index:
            health.update({
                "collection_count": len(self.unified_index.data_collections),
                "total_files": self.unified_index.schema_metadata.total_files,
                "countries": self.unified_index.schema_metadata.countries,
                "collection_types": self.unified_index.schema_metadata.collection_types
            })
        
        return health
    
    async def coverage_info(self) -> Dict[str, Any]:
        """Get coverage information"""
        if not self.unified_index:
            return {"error": "Unified index not loaded"}
        
        coverage = {
            "version": self.unified_index.version,
            "generated_at": self.unified_index.schema_metadata.generated_at.isoformat(),
            "total_collections": len(self.unified_index.data_collections),
            "total_files": self.unified_index.schema_metadata.total_files,
            "countries": {}
        }
        
        # Group by country
        for country in self.unified_index.schema_metadata.countries:
            country_collections = self.unified_index.get_collections_by_country(country)
            coverage["countries"][country] = {
                "collection_count": len(country_collections),
                "file_count": sum(c.file_count for c in country_collections),
                "collection_types": list(set(c.collection_type for c in country_collections))
            }
        
        return coverage
    
    async def _load_unified_index_from_s3(self) -> bool:
        """Load unified index from S3"""
        if not self.s3_client_factory:
            logger.warning("No S3 client factory available")
            return False
        
        try:
            # Get S3 client for main bucket
            s3_client = self.s3_client_factory.get_client("private", "ap-southeast-2")
            
            # Download unified index
            response = await asyncio.to_thread(
                s3_client.get_object,
                Bucket="road-engineering-elevation-data",
                Key=self.unified_index_key
            )
            
            content = await asyncio.to_thread(response['Body'].read)
            index_data = json.loads(content.decode('utf-8'))
            
            # Parse with Pydantic
            self.unified_index = UnifiedSpatialIndex(**index_data)
            
            logger.info(f"✅ Loaded unified index from S3: {len(self.unified_index.data_collections)} collections")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to load unified index from S3: {e}")
            return False
    
    def _load_unified_index_from_filesystem(self) -> bool:
        """Load unified index from local filesystem"""
        index_file = self.config_dir / "unified_spatial_index_v2.json"
        
        if not index_file.exists():
            logger.warning(f"Unified index file not found: {index_file}")
            return False
        
        try:
            with open(index_file, 'r') as f:
                index_data = json.load(f)
            
            self.unified_index = UnifiedSpatialIndex(**index_data)
            
            logger.info(f"✅ Loaded unified index from filesystem: {len(self.unified_index.data_collections)} collections")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load unified index from filesystem: {e}")
            return False
    
    async def _extract_elevation_from_file(self, file_entry: FileEntry, lat: float, lon: float) -> Optional[float]:
        """Extract elevation from a specific file"""
        try:
            # Use GDAL VSI path for S3 access
            vsi_path = f"/vsis3/{file_entry.file[5:]}"  # Remove 's3://' prefix
            
            # Import rasterio here to avoid import issues
            import rasterio
            from rasterio.transform import from_bounds
            from rasterio.warp import transform as warp_transform
            
            # Open raster file
            with rasterio.open(vsi_path) as dataset:
                # Transform coordinate to dataset CRS if needed
                if dataset.crs.to_string() != 'EPSG:4326':
                    # Transform from WGS84 to dataset CRS
                    xs, ys = warp_transform('EPSG:4326', dataset.crs, [lon], [lat])
                    x, y = xs[0], ys[0]
                else:
                    x, y = lon, lat
                
                # Sample elevation at coordinate
                row, col = dataset.index(x, y)
                
                # Check if coordinate is within raster bounds
                if (0 <= row < dataset.height and 0 <= col < dataset.width):
                    elevation = dataset.read(1)[row, col]
                    
                    # Handle nodata values
                    if dataset.nodata is not None and elevation == dataset.nodata:
                        return None
                    
                    return float(elevation)
                else:
                    return None
                    
        except Exception as e:
            logger.debug(f"Failed to extract elevation from {file_entry.filename}: {e}")
            return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get source statistics"""
        if not self.unified_index:
            return {"error": "Unified index not loaded"}
        
        return {
            "source_type": "unified_s3",
            "collections": len(self.unified_index.data_collections),
            "total_files": self.unified_index.schema_metadata.total_files,
            "countries": self.unified_index.schema_metadata.countries,
            "collection_types": self.unified_index.schema_metadata.collection_types
        }