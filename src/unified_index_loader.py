"""
Unified Index Loader for Phase 1 Implementation
Supports both S3 (production) and filesystem (development) loading with data-driven configuration
"""
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config

logger = logging.getLogger(__name__)


class UnifiedIndexLoader:
    """
    Unified index loader supporting both S3 (production) and filesystem (development)
    
    Features:
    - Data-driven configuration via S3_INDEX_KEYS environment variable
    - Environment detection (APP_ENV=development uses local files)
    - Proper error handling and logging
    - Compatible with existing ServiceContainer pattern
    """
    
    def __init__(self, bucket_name: str = None, environment: str = None):
        self.bucket_name = bucket_name or os.getenv("S3_INDEX_BUCKET", "road-engineering-elevation-data")
        self.environment = environment or os.getenv("APP_ENV", "production")
        self.s3_client = None
        
        # Parse S3_INDEX_KEYS for data-driven configuration
        # Format: "key1,key2,key3" or JSON array string
        index_keys_env = os.getenv('S3_INDEX_KEYS', '')
        if index_keys_env:
            try:
                # Try parsing as JSON array first
                if index_keys_env.startswith('['):
                    self.index_keys = json.loads(index_keys_env)
                else:
                    # Fall back to comma-separated string
                    self.index_keys = [key.strip() for key in index_keys_env.split(',') if key.strip()]
            except json.JSONDecodeError:
                # Fall back to comma-separated string if JSON parsing fails
                self.index_keys = [key.strip() for key in index_keys_env.split(',') if key.strip()]
        else:
            # Default configuration matching current s3_index_loader.py
            self.index_keys = [
                'indexes/campaign_index.json',
                'indexes/phase3_brisbane_tiled_index.json', 
                'indexes/spatial_index.json'
            ]
        
        # Add NZ spatial index to default configuration
        if 'indexes/nz_spatial_index.json' not in self.index_keys:
            self.index_keys.append('indexes/nz_spatial_index.json')
            
        logger.info(f"UnifiedIndexLoader initialized: environment={self.environment}, "
                   f"bucket={self.bucket_name}, index_keys={len(self.index_keys)}")
    
    def _get_s3_client(self):
        """Lazy load S3 client with enhanced credential handling"""
        if not self.s3_client:
            try:
                logger.info("Initializing S3 client for unified index loading...")
                
                # Check credential availability (without exposing values)
                aws_access_key = os.getenv('AWS_ACCESS_KEY_ID', '')
                aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY', '') 
                aws_region = os.getenv('AWS_DEFAULT_REGION', 'ap-southeast-2')
                
                logger.info(f"AWS credential status: access_key_length={len(aws_access_key)}, "
                           f"secret_key_length={len(aws_secret_key)}, region={aws_region}")
                
                if not aws_access_key or not aws_secret_key:
                    logger.error("AWS credentials not found in environment variables")
                    raise NoCredentialsError()
                
                # Configure timeouts for production
                connect_timeout = int(os.getenv("S3_CONNECT_TIMEOUT", "10"))
                read_timeout = int(os.getenv("S3_READ_TIMEOUT", "60"))
                
                config = Config(
                    region_name=aws_region,
                    retries={'max_attempts': 3, 'mode': 'standard'},
                    connect_timeout=connect_timeout,
                    read_timeout=read_timeout
                )
                
                self.s3_client = boto3.client('s3', config=config)
                logger.info("S3 client initialized successfully")
                
            except Exception as e:
                logger.error(f"Failed to initialize S3 client: {e}")
                raise
        
        return self.s3_client
    
    def _get_local_path(self, s3_key: str) -> Path:
        """Map S3 key to local config/filename.json"""
        # Extract filename from S3 key (e.g., "indexes/nz_spatial_index.json" -> "nz_spatial_index.json")
        filename = Path(s3_key).name
        return Path("config") / filename
    
    async def load_index(self, index_name: str) -> Dict[str, Any]:
        """
        Load index from S3 (production) or filesystem (development)
        
        Args:
            index_name: Name of the index (e.g., "nz_spatial_index")
            
        Returns:
            Dict containing the parsed index data
            
        Raises:
            FileNotFoundError: If index not found in configured locations
            ValueError: If index data is invalid
        """
        # Find matching S3 key for the index name
        matching_key = None
        for key in self.index_keys:
            if index_name in key or Path(key).stem == index_name:
                matching_key = key
                break
        
        if not matching_key:
            raise FileNotFoundError(f"Index '{index_name}' not found in configured S3_INDEX_KEYS: {self.index_keys}")
        
        try:
            if self.environment == "development":
                return await self._load_from_filesystem(matching_key)
            else:
                return await self._load_from_s3(matching_key)
        except Exception as e:
            logger.error(f"Failed to load index '{index_name}' from key '{matching_key}': {e}")
            raise
    
    async def _load_from_filesystem(self, s3_key: str) -> Dict[str, Any]:
        """Load index from local filesystem (development mode)"""
        local_path = self._get_local_path(s3_key)
        
        if not local_path.exists():
            raise FileNotFoundError(f"Local index file not found: {local_path}")
        
        try:
            with open(local_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.info(f"Loaded index from filesystem: {local_path} ({len(str(data))} chars)")
            return data
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in local index file {local_path}: {e}")
        except Exception as e:
            raise RuntimeError(f"Error reading local index file {local_path}: {e}")
    
    async def _load_from_s3(self, s3_key: str) -> Dict[str, Any]:
        """Load index from S3 (production mode)"""
        try:
            s3_client = self._get_s3_client()
            
            logger.info(f"Loading index from S3: {self.bucket_name}/{s3_key}")
            
            response = s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            content = response['Body'].read().decode('utf-8')
            
            data = json.loads(content)
            
            logger.info(f"Loaded index from S3: {s3_key} ({len(content)} chars)")
            return data
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                raise FileNotFoundError(f"S3 index not found: {self.bucket_name}/{s3_key}")
            else:
                raise RuntimeError(f"S3 error loading {s3_key}: {error_code} - {e.response['Error']['Message']}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in S3 index {s3_key}: {e}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error loading S3 index {s3_key}: {e}")
    
    def get_available_indexes(self) -> List[str]:
        """Get list of available index names based on configuration"""
        return [Path(key).stem for key in self.index_keys]
    
    def is_production_mode(self) -> bool:
        """Check if running in production mode (S3 loading)"""
        return self.environment != "development"