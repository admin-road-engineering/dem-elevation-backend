"""
Bucket Detection Utility for S3 Access Pattern Management

Detects whether S3 paths require signed (private) or unsigned (public) requests
based on bucket naming patterns and known bucket configurations.
"""
from enum import Enum
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class BucketType(Enum):
    """S3 bucket access pattern types"""
    PRIVATE_SIGNED = "private_signed"      # Requires AWS credentials
    PUBLIC_UNSIGNED = "public_unsigned"    # Requires AWS_NO_SIGN_REQUEST=YES
    UNKNOWN = "unknown"                    # Unknown bucket type

class BucketDetector:
    """Utility for detecting S3 bucket access patterns"""
    
    # Known bucket configurations
    BUCKET_CONFIG: Dict[str, BucketType] = {
        # Australian elevation data (private bucket)
        "road-engineering-elevation-data": BucketType.PRIVATE_SIGNED,
        
        # New Zealand elevation data (public bucket)
        "nz-elevation": BucketType.PUBLIC_UNSIGNED,
    }
    
    @classmethod
    def detect_bucket_type(cls, file_path: str) -> BucketType:
        """
        Detect S3 bucket access pattern from file path
        
        Args:
            file_path: S3 file path (e.g., "/vsis3/bucket-name/path/file.tiff")
            
        Returns:
            BucketType indicating required access pattern
        """
        try:
            # Extract bucket name from S3 path
            bucket_name = cls._extract_bucket_name(file_path)
            
            if not bucket_name:
                logger.warning(f"Could not extract bucket name from path: {file_path}")
                return BucketType.UNKNOWN
            
            # Check known bucket configurations
            bucket_type = cls.BUCKET_CONFIG.get(bucket_name, BucketType.UNKNOWN)
            
            logger.debug(f"Bucket '{bucket_name}' detected as: {bucket_type.value}")
            return bucket_type
            
        except Exception as e:
            logger.error(f"Failed to detect bucket type for {file_path}: {e}")
            return BucketType.UNKNOWN
    
    @classmethod
    def _extract_bucket_name(cls, file_path: str) -> Optional[str]:
        """
        Extract bucket name from various S3 path formats
        
        Supported formats:
        - /vsis3/bucket-name/path/file.tiff
        - s3://bucket-name/path/file.tiff
        - https://bucket-name.s3.amazonaws.com/path/file.tiff
        """
        if not file_path:
            return None
        
        # Handle GDAL VSI S3 paths: /vsis3/bucket-name/...
        if file_path.startswith("/vsis3/"):
            parts = file_path[7:].split("/")  # Remove /vsis3/ prefix
            return parts[0] if parts else None
        
        # Handle standard S3 URLs: s3://bucket-name/...
        if file_path.startswith("s3://"):
            parts = file_path[5:].split("/")  # Remove s3:// prefix
            return parts[0] if parts else None
        
        # Handle HTTPS S3 URLs: https://bucket-name.s3.amazonaws.com/...
        if "s3.amazonaws.com" in file_path:
            # Extract bucket from subdomain
            import re
            match = re.search(r'https://([^.]+)\.s3\.amazonaws\.com', file_path)
            return match.group(1) if match else None
        
        logger.debug(f"Unknown S3 path format: {file_path}")
        return None
    
    @classmethod
    def is_known_bucket(cls, bucket_name: str) -> bool:
        """Check if bucket configuration is known"""
        return bucket_name in cls.BUCKET_CONFIG
    
    @classmethod
    def get_all_known_buckets(cls) -> Dict[str, BucketType]:
        """Get all known bucket configurations"""
        return cls.BUCKET_CONFIG.copy()