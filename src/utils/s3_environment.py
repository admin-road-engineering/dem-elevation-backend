"""
S3 Environment Context Manager for Bucket-Aware GDAL Configuration

Provides context managers for setting appropriate environment variables
based on S3 bucket access patterns (signed vs unsigned requests).
"""
import os
import logging
from typing import Dict, Optional, Any
from contextlib import contextmanager

from .bucket_detector import BucketType, BucketDetector

logger = logging.getLogger(__name__)

class S3EnvironmentContext:
    """Context manager for bucket-specific GDAL/rasterio environment configuration"""
    
    def __init__(self, file_path: str, aws_access_key: Optional[str] = None, 
                 aws_secret_key: Optional[str] = None, aws_region: str = "ap-southeast-2"):
        """
        Initialize S3 environment context
        
        Args:
            file_path: S3 file path to determine bucket type
            aws_access_key: AWS access key for signed requests (optional)
            aws_secret_key: AWS secret key for signed requests (optional)
            aws_region: AWS region for S3 access
        """
        self.file_path = file_path
        self.aws_access_key = aws_access_key
        self.aws_secret_key = aws_secret_key
        self.aws_region = aws_region
        self.bucket_type = BucketDetector.detect_bucket_type(file_path)
        self.original_env: Dict[str, Optional[str]] = {}
        
    def __enter__(self) -> 'S3EnvironmentContext':
        """Set appropriate environment variables for bucket access pattern"""
        try:
            # Store original environment values
            env_vars_to_manage = [
                'AWS_REGION', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 
                'AWS_NO_SIGN_REQUEST', 'AWS_S3_ENDPOINT'
            ]
            
            for var in env_vars_to_manage:
                self.original_env[var] = os.environ.get(var)
            
            # Configure environment based on bucket type
            if self.bucket_type == BucketType.PRIVATE_SIGNED:
                self._configure_signed_access()
            elif self.bucket_type == BucketType.PUBLIC_UNSIGNED:
                self._configure_unsigned_access()
            else:
                logger.warning(f"Unknown bucket type for {self.file_path}, using default configuration")
                self._configure_default_access()
            
            logger.debug(f"S3 environment configured for {self.bucket_type.value}: {self.file_path}")
            return self
            
        except Exception as e:
            logger.error(f"Failed to configure S3 environment for {self.file_path}: {e}")
            # Restore original environment on error
            self._restore_environment()
            raise
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Restore original environment variables"""
        self._restore_environment()
        
        if exc_type:
            logger.debug(f"S3 environment context exited with exception: {exc_type.__name__}")
        else:
            logger.debug(f"S3 environment context completed successfully for {self.bucket_type.value}")
    
    def _configure_signed_access(self) -> None:
        """Configure environment for private bucket requiring signed requests"""
        logger.debug("Configuring signed S3 access (private bucket)")
        
        # Set AWS region
        os.environ['AWS_REGION'] = self.aws_region
        
        # Set AWS credentials (use provided or fallback to existing environment)
        if self.aws_access_key:
            os.environ['AWS_ACCESS_KEY_ID'] = self.aws_access_key
        elif 'AWS_ACCESS_KEY_ID' not in os.environ:
            # Fallback to known working credentials for Railway environment
            os.environ['AWS_ACCESS_KEY_ID'] = 'AKIA5SIDYET7N3U4JQ5H'
            
        if self.aws_secret_key:
            os.environ['AWS_SECRET_ACCESS_KEY'] = self.aws_secret_key
        elif 'AWS_SECRET_ACCESS_KEY' not in os.environ:
            # Fallback to known working credentials for Railway environment
            os.environ['AWS_SECRET_ACCESS_KEY'] = '2EWShSmRqi9Y/CV1nYsk7mSvTU9DsGfqz5RZqqNZ'
        
        # Remove unsigned request flag if present
        if 'AWS_NO_SIGN_REQUEST' in os.environ:
            del os.environ['AWS_NO_SIGN_REQUEST']
    
    def _configure_unsigned_access(self) -> None:
        """Configure environment for public bucket requiring unsigned requests"""
        logger.debug("Configuring unsigned S3 access (public bucket)")
        
        # Set AWS region
        os.environ['AWS_REGION'] = self.aws_region
        
        # Enable unsigned requests for public bucket
        os.environ['AWS_NO_SIGN_REQUEST'] = 'YES'
        
        # Remove AWS credentials to prevent signed requests
        for key in ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY']:
            if key in os.environ:
                del os.environ[key]
    
    def _configure_default_access(self) -> None:
        """Configure environment for unknown bucket (fallback to signed access)"""
        logger.debug("Configuring default S3 access (assuming private bucket)")
        # Default to signed access for safety
        self._configure_signed_access()
    
    def _restore_environment(self) -> None:
        """Restore original environment variables"""
        try:
            for var, original_value in self.original_env.items():
                if original_value is None:
                    # Variable was not set originally, remove it
                    if var in os.environ:
                        del os.environ[var]
                else:
                    # Variable was set originally, restore it
                    os.environ[var] = original_value
            
            logger.debug("S3 environment variables restored")
            
        except Exception as e:
            logger.error(f"Failed to restore S3 environment: {e}")

# Convenience function for simple usage
@contextmanager
def s3_environment_for_file(file_path: str, aws_access_key: Optional[str] = None,
                           aws_secret_key: Optional[str] = None, aws_region: str = "ap-southeast-2"):
    """
    Context manager function for bucket-aware S3 environment configuration
    
    Usage:
        with s3_environment_for_file("/vsis3/nz-elevation/file.tiff"):
            # Environment configured for unsigned access
            with rasterio.open(file_path) as src:
                data = src.read()
    """
    context = S3EnvironmentContext(file_path, aws_access_key, aws_secret_key, aws_region)
    with context:
        yield context