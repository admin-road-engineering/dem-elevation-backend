"""
Unified Index Loader - Phase 2B Critical Async Fixes
Implements Gemini's approved design with true O(1) index discovery and async I/O
"""
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional, List

import aiofiles
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)


class UnifiedIndexLoader:
    """
    Multi-bucket S3 index loader with true O(1) discovery and async I/O
    
    Phase 2B: Critical Async Fixes
    - True O(1) discovery with short_name_map for single dictionary lookup
    - Async file operations using aiofiles (non-blocking I/O)
    - Async S3 operations using aiobotocore context managers
    - Concurrent startup validation
    
    Features:
    - O(1) index discovery using source configuration mapping
    - Multi-bucket support (AU private, NZ public, future sources)
    - Region-aware S3 client factory integration
    - Backward compatibility with existing index loading patterns
    - Graceful fallback and error handling
    """
    
    def __init__(self, s3_client_factory=None, s3_sources: List=None, environment: str = None):
        """
        Initialize with S3 client factory and source configuration
        
        Phase 2B: Clean DI Architecture - factory injected explicitly
        
        Args:
            s3_client_factory: S3ClientFactory instance for multi-bucket access (injected via DI)
            s3_sources: List of S3SourceConfig objects defining available sources
            environment: Environment mode ("development" uses local files, defaults to "production")
        """
        from .s3_config import S3SourceConfig
        
        self.s3_client_factory = s3_client_factory  # Injected explicitly via DI
        self.s3_sources = s3_sources or self._get_legacy_sources()
        self.environment = environment or os.getenv("APP_ENV", "production")
        
        # Phase 2B: True O(1) index discovery maps
        self.index_map: Dict[str, Any] = {}  # Full key -> source mapping
        self.short_name_map: Dict[str, Any] = {}  # Short name -> (source, key) mapping for O(1) lookup
        self._build_index_mapping()
        
        logger.info(f"UnifiedIndexLoader initialized: environment={self.environment}, "
                   f"sources={len(self.s3_sources)}, index_mappings={len(self.index_map)}, "
                   f"short_names={len(self.short_name_map)}")
        
        # Log source configuration
        for source in self.s3_sources:
            logger.info(f"  Source '{source.name}': {source.bucket} ({source.access_type}, {source.region}) "
                       f"- {len(source.index_keys)} indexes, required={source.required}")
    
    def _get_legacy_sources(self) -> List:
        """
        Create legacy-compatible source configuration for backward compatibility
        Used when no S3 sources are provided during initialization
        """
        from .s3_config import S3SourceConfig
        
        # Legacy AU source configuration
        return [S3SourceConfig(
            name="au",
            bucket=os.getenv("S3_INDEX_BUCKET", "road-engineering-elevation-data"),
            access_type="private",
            index_keys=[
                'indexes/campaign_index.json',
                'indexes/phase3_brisbane_tiled_index.json', 
                'indexes/spatial_index.json'
            ],
            region="ap-southeast-2",
            required=True
        )]
    
    def _build_index_mapping(self) -> None:
        """
        Build true O(1) index discovery mapping with short_name_map
        Phase 2B: Creates both full key mapping and short name mapping for single dictionary lookup
        Raises ValueError if duplicate index keys found across sources
        """
        for source in self.s3_sources:
            for key in source.index_keys:
                # Full key mapping (existing functionality)
                if key in self.index_map:
                    existing_source = self.index_map[key].name
                    raise ValueError(
                        f"Duplicate index key '{key}' found in sources '{existing_source}' and '{source.name}'. "
                        "Each index key must be unique across all sources."
                    )
                self.index_map[key] = source
                
                # Phase 2B: True O(1) short name mapping
                short_name = Path(key).stem  # Extract filename without extension
                if short_name in self.short_name_map:
                    existing_info = self.short_name_map[short_name]
                    logger.warning(f"Duplicate short name '{short_name}' found. "
                                 f"Existing: {existing_info[0].name}/{existing_info[1]}, "
                                 f"New: {source.name}/{key}. Using first occurrence.")
                else:
                    # Store (source, key) tuple for O(1) access
                    self.short_name_map[short_name] = (source, key)
        
        logger.info(f"Index mapping built: {len(self.index_map)} unique index keys, "
                   f"{len(self.short_name_map)} short names across {len(self.s3_sources)} sources")
    
    def _get_s3_client_for_source(self, source):
        """Get appropriate S3 client for the given source configuration"""
        return self.s3_client_factory.get_client(source.access_type, source.region)
    
    def _get_local_path(self, s3_key: str) -> Path:
        """Map S3 key to local config/filename.json"""
        # Extract filename from S3 key (e.g., "indexes/nz_spatial_index.json" -> "nz_spatial_index.json")
        filename = Path(s3_key).name
        return Path("config") / filename
    
    async def load_index(self, index_name: str) -> Dict[str, Any]:
        """
        Load index with true O(1) source discovery and async I/O
        
        Phase 2B: True O(1) lookup using short_name_map (single dictionary access)
        
        Args:
            index_name: Name of the index (e.g., "nz_spatial_index", "campaign", "spatial")
            
        Returns:
            Dict containing the parsed index data
            
        Raises:
            FileNotFoundError: If index not found in any configured source
            ValueError: If index data is invalid
        """
        # Phase 2B: True O(1) index discovery - single dictionary lookup
        if index_name in self.short_name_map:
            source_config, exact_key = self.short_name_map[index_name]
        else:
            # Fallback: Check for exact key match (backward compatibility)  
            source_config = None
            exact_key = None
            
            for key in self.index_map:
                if key.endswith(f"{index_name}.json") or Path(key).stem == index_name:
                    source_config = self.index_map[key]
                    exact_key = key
                    break
            
            if not source_config:
                available_indexes = list(self.short_name_map.keys())
                raise FileNotFoundError(
                    f"Index '{index_name}' not found in any configured source. "
                    f"Available indexes: {available_indexes}"
                )
        
        try:
            if self.environment == "development":
                return await self._load_from_filesystem(exact_key)
            else:
                return await self._load_from_s3_with_source(source_config, exact_key)
        except Exception as e:
            logger.error(f"Failed to load index '{index_name}' from {source_config.name}/{exact_key}: {e}")
            raise
    
    async def _load_from_filesystem(self, s3_key: str) -> Dict[str, Any]:
        """Load index from local filesystem using async I/O (development mode)"""
        local_path = self._get_local_path(s3_key)
        
        if not local_path.exists():
            raise FileNotFoundError(f"Local index file not found: {local_path}")
        
        try:
            # Phase 2B: Use aiofiles for non-blocking file I/O
            async with aiofiles.open(local_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
            
            logger.info(f"Loaded index from filesystem: {local_path} ({len(content)} chars)")
            return data
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in local index file {local_path}: {e}")
        except Exception as e:
            raise RuntimeError(f"Error reading local index file {local_path}: {e}")
    
    async def _load_from_s3_with_source(self, source_config, s3_key: str) -> Dict[str, Any]:
        """Load index from S3 using async aiobotocore client context manager"""
        try:
            logger.info(f"Loading index from {source_config.name} source: {source_config.bucket}/{s3_key} "
                       f"({source_config.access_type} access, {source_config.region} region)")
            
            # Phase 2B: Use async context manager for S3 client
            async with self.s3_client_factory.get_client(source_config.access_type, source_config.region) as s3_client:
                response = await s3_client.get_object(Bucket=source_config.bucket, Key=s3_key)
                
                # Read response body asynchronously
                content_bytes = await response['Body'].read()
                content = content_bytes.decode('utf-8')
                
                data = json.loads(content)
                
                logger.info(f"Successfully loaded index from {source_config.name}: {s3_key} ({len(content)} chars)")
                return data
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                raise FileNotFoundError(f"Index not found in {source_config.name} source: {source_config.bucket}/{s3_key}")
            elif error_code == 'AccessDenied':
                raise RuntimeError(f"Access denied to {source_config.name} source ({source_config.access_type}): {source_config.bucket}/{s3_key}")
            else:
                raise RuntimeError(f"S3 error loading from {source_config.name}: {error_code} - {e.response['Error']['Message']}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {source_config.name} index {s3_key}: {e}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error loading from {source_config.name}/{s3_key}: {e}")
    
    def get_available_indexes(self) -> List[str]:
        """Get list of available index names using O(1) short_name_map"""
        return list(self.short_name_map.keys())
    
    def get_source_for_index(self, index_name: str):
        """Get source configuration for a specific index using O(1) lookup"""
        if index_name in self.short_name_map:
            return self.short_name_map[index_name][0]  # Return source (first element of tuple)
        return None
    
    def get_index_status(self) -> Dict[str, Any]:
        """Get detailed status of all configured indexes and sources"""
        status = {
            "total_sources": len(self.s3_sources),
            "total_indexes": len(self.index_map),
            "environment": self.environment,
            "sources": [],
            "index_mapping": {}
        }
        
        for source in self.s3_sources:
            source_info = {
                "name": source.name,
                "bucket": source.bucket,
                "access_type": source.access_type,
                "region": source.region,
                "required": source.required,
                "index_count": len(source.index_keys)
            }
            status["sources"].append(source_info)
        
        for key, source in self.index_map.items():
            index_name = Path(key).stem
            status["index_mapping"][index_name] = {
                "key": key,
                "source": source.name,
                "bucket": source.bucket,
                "access_type": source.access_type
            }
        
        return status
    
    def is_production_mode(self) -> bool:
        """Check if running in production mode (S3 loading)"""
        return self.environment != "development"