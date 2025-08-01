"""
S3 Client Factory with Region-Aware Caching
Implements Gemini's approved design for mixed public/private bucket support
Phase 2B: Critical Async Fixes - aiobotocore with async context managers
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Dict, Tuple, Optional, AsyncGenerator

import aiobotocore.session
from aiobotocore.config import AioConfig
from botocore import UNSIGNED

logger = logging.getLogger(__name__)


class S3ClientFactory:
    """
    Async S3 client factory with region-aware caching
    
    Phase 2B: Critical Async Fixes
    - Uses aiobotocore for true async operations
    - Async context managers prevent resource leaks
    - Singleton pattern for shared rate limiters
    - Non-blocking I/O operations
    
    Features:
    - Async context managers for proper lifecycle management
    - Supports unsigned access for public buckets
    - Supports credentialed access for private buckets
    - Region-aware client creation
    - Fail-fast timeout strategy
    """
    
    def __init__(self):
        """Initialize async client factory"""
        self._session = aiobotocore.session.get_session()  # CRITICAL FIX: Use get_session() not AioSession()
        self._config: Optional['S3ClientConfig'] = None  # Will be set by create_s3_client_factory
        logger.info("Async S3ClientFactory initialized")
    
    @asynccontextmanager
    async def get_client(self, access_type: str, region: str) -> AsyncGenerator:
        """
        Get async S3 client as context manager
        
        Args:
            access_type: "public" for unsigned access, "private" for credentialed access
            region: AWS region (e.g., "ap-southeast-2")
            
        Yields:
            aiobotocore client: Configured async S3 client
            
        Raises:
            ValueError: If access_type is invalid
            Exception: If client creation fails
        """
        if access_type not in ["public", "private"]:
            raise ValueError(f"Invalid access_type '{access_type}'. Must be 'public' or 'private'")
        
        try:
            # Use configuration from dependency injection or fallback to defaults
            cfg = self._config or S3ClientConfig()
            
            if access_type == "public":
                # Public bucket - unsigned access
                config = AioConfig(
                    signature_version=UNSIGNED,
                    region_name=region,
                    retries={'max_attempts': cfg.max_attempts, 'mode': 'standard'},
                    connect_timeout=cfg.connect_timeout,
                    read_timeout=cfg.read_timeout,
                    max_pool_connections=cfg.max_pool_connections
                )
                logger.debug(f"Creating public S3 client for region {region} with pool_size={cfg.max_pool_connections}")
                    
            else:  # access_type == "private"
                # Private bucket - credentialed access
                config = AioConfig(
                    region_name=region,
                    retries={'max_attempts': cfg.max_attempts, 'mode': 'standard'},
                    connect_timeout=cfg.connect_timeout,
                    read_timeout=cfg.read_timeout,
                    max_pool_connections=cfg.max_pool_connections
                )
                logger.debug(f"Creating private S3 client for region {region} with pool_size={cfg.max_pool_connections}")
            
            # Use async context manager for proper lifecycle
            async with self._session.create_client('s3', config=config) as client:
                yield client
                
        except Exception as e:
            logger.error(f"Failed to create async S3 client ({access_type}, {region}): {e}")
            raise
    
    async def get_client_info(self) -> Dict[str, any]:
        """Get information about the factory"""
        return {
            "factory_type": "aiobotocore_async",
            "session_created": self._session is not None,
            "supports_async": True
        }
    
    def clear_session(self) -> None:
        """Clear session reference - cleanup handled automatically by aiobotocore 2.x"""
        try:
            if self._session:
                # aiobotocore 2.x handles session cleanup automatically via context managers
                # No explicit close() method exists on AioSession
                self._session = None
                logger.info("Cleared aiobotocore session reference - cleanup handled automatically")
        except Exception as e:
            logger.warning(f"Error clearing aiobotocore session reference: {e}")
    
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        self.clear_session()


# Dependency Injection Configuration Class
class S3ClientConfig:
    """Configuration for S3 client connection pooling and timeouts"""
    
    def __init__(
        self,
        max_pool_connections: int = 50,  # Increased from default 10 for production
        connect_timeout: int = 10,
        read_timeout: int = 60,
        max_attempts: int = 3
    ):
        self.max_pool_connections = max_pool_connections
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.max_attempts = max_attempts


# Clean Dependency Injection Functions (replaces singleton pattern)
def create_s3_client_factory(config: Optional[S3ClientConfig] = None) -> S3ClientFactory:
    """
    Factory function to create S3ClientFactory with configuration
    Used in FastAPI lifespan for dependency injection
    """
    if config is None:
        # Load from environment or use defaults
        import os
        config = S3ClientConfig(
            max_pool_connections=int(os.getenv("S3_MAX_POOL_CONNECTIONS", "50")),
            connect_timeout=int(os.getenv("S3_CONNECT_TIMEOUT", "10")),
            read_timeout=int(os.getenv("S3_READ_TIMEOUT", "60")),
            max_attempts=int(os.getenv("S3_MAX_ATTEMPTS", "3"))
        )
    
    factory = S3ClientFactory()
    factory._config = config  # Store config for client creation
    logger.info(f"Created S3ClientFactory with config: max_pool={config.max_pool_connections}")
    return factory