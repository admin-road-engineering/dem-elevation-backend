"""
S3 Index Loader for Phase 3 Deployment
Loads spatial indexes from S3 instead of local files for Railway deployment
"""
import json
import logging
import boto3
from typing import Dict, Any, Optional
from functools import lru_cache
import os
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config

logger = logging.getLogger(__name__)

class S3IndexLoader:
    """Loads spatial indexes from S3 for production deployment"""
    
    def __init__(self, bucket_name: str = None):
        # Make bucket configurable via environment variables
        self.bucket_name = bucket_name or os.getenv("S3_INDEX_BUCKET", "road-engineering-elevation-data")
        self.s3_client = None
        
        # Shared source of truth for required indexes (configurable via env vars)
        self.required_indexes = [
            os.getenv('S3_CAMPAIGN_INDEX_KEY', 'indexes/campaign_index.json'),
            os.getenv('S3_TILED_INDEX_KEY', 'indexes/phase3_brisbane_tiled_index.json'),
            os.getenv('S3_SPATIAL_INDEX_KEY', 'indexes/spatial_index.json')
        ]
        
    def _get_s3_client(self):
        """Lazy load S3 client with enhanced credential handling and debugging"""
        if not self.s3_client:
            try:
                # Enhanced debugging for Railway environment
                logger.info("Initializing S3 client for Railway production...")
                
                # Log environment variable status (without exposing values)
                aws_access_key = os.getenv('AWS_ACCESS_KEY_ID', '')
                aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY', '')
                aws_region = os.getenv('AWS_DEFAULT_REGION', 'ap-southeast-2')
                
                logger.info(f"AWS credential status: access_key_length={len(aws_access_key)}, "
                           f"secret_key_length={len(aws_secret_key)}, region={aws_region}")
                
                if not aws_access_key or not aws_secret_key:
                    raise NoCredentialsError("AWS credentials not found in environment variables")
                
                # Configure timeouts for Railway production
                connect_timeout = int(os.getenv("S3_CONNECT_TIMEOUT", "10"))  # Increased for Railway
                read_timeout = int(os.getenv("S3_READ_TIMEOUT", "60"))       # Increased for Railway
                max_attempts = int(os.getenv("S3_MAX_ATTEMPTS", "3"))        # Increased for retry
                
                config = Config(
                    connect_timeout=connect_timeout,
                    read_timeout=read_timeout,  
                    retries={
                        'max_attempts': max_attempts,
                        'mode': 'adaptive'  # Better retry handling
                    },
                    region_name=aws_region
                )
                
                # Use session-based approach for better credential management (per web search)
                session = boto3.Session(
                    aws_access_key_id=aws_access_key,
                    aws_secret_access_key=aws_secret_key,
                    region_name=aws_region
                )
                
                self.s3_client = session.client('s3', config=config)
                
                # Test client immediately with a simple operation
                logger.info("Testing S3 client with credentials verification...")
                try:
                    # Simple operation that requires valid credentials
                    self.s3_client.list_buckets()
                    logger.info("S3 client credentials verified successfully")
                except Exception as test_error:
                    logger.error(f"S3 credentials test failed: {test_error}")
                    raise
                    
                logger.info("S3 client initialized successfully with session-based approach")
                return self.s3_client
                
            except NoCredentialsError as e:
                logger.error(f"AWS credentials not available: {e}")
                raise
            except Exception as e:
                logger.error(f"Failed to initialize S3 client: {type(e).__name__}: {e}")
                logger.error(f"Full error details: {e}", exc_info=True)
                raise
                
        return self.s3_client
    
    @lru_cache(maxsize=1)  # Reduce cache size to save memory
    def load_index(self, index_name: str) -> Dict[str, Any]:
        """
        Load spatial index from S3 with in-memory caching via LRU
        
        Args:
            index_name: One of 'spatial', 'campaign', 'tiled', 'nz_spatial'
            
        Returns:
            Dict containing the spatial index data
        """
        # Map index names to S3 keys (configurable via environment variables)
        index_mapping = {
            'spatial': os.getenv('S3_SPATIAL_INDEX_KEY', 'indexes/spatial_index.json'),
            'campaign': os.getenv('S3_CAMPAIGN_INDEX_KEY', 'indexes/campaign_index.json'), 
            'tiled': os.getenv('S3_TILED_INDEX_KEY', 'indexes/phase3_brisbane_tiled_index.json'),
            'nz_spatial': os.getenv('S3_NZ_INDEX_KEY', 'indexes/nz_spatial_index.json')
        }
        
        if index_name not in index_mapping:
            raise ValueError(f"Unknown index name: {index_name}. Must be one of: {list(index_mapping.keys())}")
            
        s3_key = index_mapping[index_name]
            
        try:
            logger.info(f"Loading {index_name} index from S3: s3://{self.bucket_name}/{s3_key}")
            
            # Download from S3
            s3_client = self._get_s3_client()
            response = s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            
            # Parse JSON
            index_data = json.loads(response['Body'].read().decode('utf-8'))
            
            # Log success with size info
            if 'file_count' in index_data:
                logger.info(f"Loaded {index_name} index: {index_data['file_count']} files")
            elif 'campaign_count' in index_data:
                logger.info(f"Loaded {index_name} index: {index_data['campaign_count']} campaigns")
            else:
                logger.info(f"Loaded {index_name} index successfully")
                
            return index_data
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                logger.error(f"Index not found in S3: s3://{self.bucket_name}/{s3_key}")
                raise FileNotFoundError(f"Spatial index not found: {index_name}")
            elif error_code == 'AccessDenied':
                logger.error(f"Access denied to S3 index: s3://{self.bucket_name}/{s3_key}")
                raise PermissionError(f"Access denied to spatial index: {index_name}")
            else:
                logger.error(f"S3 error loading {index_name} index: {e}")
                raise
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {index_name} index: {e}")
            raise ValueError(f"Corrupted spatial index: {index_name}")
            
        except Exception as e:
            logger.error(f"Unexpected error loading {index_name} index: {e}")
            raise
    
    def preload_essential_indexes(self):
        """Preload essential indexes for faster startup"""
        essential_indexes = ['campaign']  # Start with just campaign index
        
        for index_name in essential_indexes:
            try:
                self.load_index(index_name)
                logger.info(f"Preloaded {index_name} index")
            except Exception as e:
                logger.warning(f"Failed to preload {index_name} index: {e}")
    
    def get_index_info(self) -> Dict[str, Any]:
        """Get information about available indexes"""
        info = {
            'bucket': self.bucket_name,
            'available_indexes': ['spatial', 'campaign', 'tiled', 'nz_spatial'],
            'cache_info': self.load_index.cache_info()._asdict()
        }
        
        # Try to get size info from S3
        try:
            s3_client = self._get_s3_client()
            objects = s3_client.list_objects_v2(Bucket=self.bucket_name, Prefix='indexes/')
            
            if 'Contents' in objects:
                info['s3_indexes'] = []
                for obj in objects['Contents']:
                    info['s3_indexes'].append({
                        'key': obj['Key'],
                        'size_mb': round(obj['Size'] / (1024 * 1024), 2),
                        'last_modified': obj['LastModified'].isoformat()
                    })
                    
        except Exception as e:
            logger.warning(f"Could not get S3 index info: {e}")
            
        return info
    
    def clear_cache(self):
        """Clear the LRU index cache"""
        self.load_index.cache_clear()
        logger.info("Index cache cleared")
        
    def health_check(self) -> Dict[str, Any]:
        """Lightweight S3 health check with granular error handling"""
        try:
            s3_client = self._get_s3_client()
            
            # 1. Check bucket accessibility first
            try:
                s3_client.head_bucket(Bucket=self.bucket_name)
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                logger.warning(
                    f"S3 bucket check failed: {e}",
                    extra={"error_code": error_code, "bucket": self.bucket_name}
                )
                return {
                    "status": "failed",
                    "reason": "Bucket not accessible or does not exist", 
                    "error": str(e),
                    "error_code": error_code,
                    "bucket_accessible": False
                }
            
            # 2. Check critical index files exist (using shared configuration)
            missing_indexes = []
            for index_key in self.required_indexes:
                try:
                    s3_client.head_object(Bucket=self.bucket_name, Key=index_key)
                except ClientError as e:
                    error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                    # Check for 404 Not Found errors specifically
                    if error_code == 'NoSuchKey':
                        missing_indexes.append(index_key)
                    else:
                        # A different error occurred (e.g., permissions on the object)
                        logger.warning(
                            f"S3 index access failed: {e}",
                            extra={"error_code": error_code, "index": index_key}
                        )
                        return {
                            "status": "failed",
                            "reason": f"Error accessing index '{index_key}'",
                            "error": str(e),
                            "error_code": error_code,
                            "bucket_accessible": True  # Bucket was fine, object was not
                        }
            
            if missing_indexes:
                logger.warning(
                    f"Missing required S3 indexes: {missing_indexes}",
                    extra={"missing_count": len(missing_indexes), "bucket": self.bucket_name}
                )
                return {
                    "status": "degraded",
                    "reason": "One or more required indexes are missing",
                    "bucket_accessible": True,
                    "missing_indexes": missing_indexes,
                    "available_indexes": len(self.required_indexes) - len(missing_indexes)
                }
            
            return {
                "status": "healthy",
                "bucket_accessible": True,
                "indexes_available": len(self.required_indexes),
                "validation_method": "head_object"
            }
            
        except Exception as e:
            logger.error(f"Unexpected error during S3 health check: {e}")
            return {
                "status": "failed", 
                "error": f"Unexpected error: {e}",
                "bucket_accessible": False
            }

# Global instance for application use
s3_index_loader = S3IndexLoader()