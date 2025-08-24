"""
Redis-based rate limiter for multi-worker environments.

This replaces the vulnerable in-memory rate limiting that fails
in production multi-worker setups like Railway.
"""
import redis.asyncio as redis
from datetime import datetime
import logging
from typing import Optional
from ..security_logger import security_logger

logger = logging.getLogger(__name__)


class RedisRateLimiter:
    """
    Redis-based rate limiter that works correctly in multi-worker environments.
    
    Provides configurable fallback behavior when Redis is unavailable:
    - strict: fail closed (raise exception)
    - degraded: fail open (log warning but allow)
    - local: use in-memory fallback
    """
    
    def __init__(self, redis_url: str, fallback_mode: str = "strict"):
        """
        Initialize Redis rate limiter.
        
        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379)
            fallback_mode: Behavior when Redis unavailable ("strict", "degraded", "local")
        """
        self.redis_url = redis_url
        self.fallback_mode = fallback_mode
        self.redis: Optional[redis.Redis] = None
        self._connected = False
        
        # Local fallback cache for development only
        self._local_cache = {} if fallback_mode == "local" else None
        self._cache_timestamps = {} if fallback_mode == "local" else None
    
    async def _ensure_connection(self) -> bool:
        """Ensure Redis connection is established."""
        if not self._connected:
            try:
                self.redis = redis.from_url(self.redis_url)
                # Test connection
                await self.redis.ping()
                self._connected = True
                logger.info("Redis rate limiter connected successfully")
            except Exception as e:
                logger.warning(f"Redis rate limiter connection failed: {e}")
                self._connected = False
                return False
        return True
    
    async def _check_local_rate_limit(self, key: str, limit: int, window: int) -> bool:
        """
        Local in-memory rate limiting fallback for development.
        WARNING: Only suitable for single-worker development environments.
        """
        import time
        
        current_time = time.time()
        
        # Clean expired entries
        if self._cache_timestamps:
            expired_keys = [
                k for k, timestamp in self._cache_timestamps.items()
                if current_time - timestamp > window
            ]
            for k in expired_keys:
                self._local_cache.pop(k, None)
                self._cache_timestamps.pop(k, None)
        
        # Initialize or increment counter
        if key not in self._local_cache:
            self._local_cache[key] = 1
            self._cache_timestamps[key] = current_time
            return True
        
        # Check if within limit
        current_count = self._local_cache[key]
        if current_count < limit:
            self._local_cache[key] += 1
            return True
        
        # Rate limited
        logger.warning(f"Local rate limit exceeded for {key}: {current_count}/{limit}")
        return False
    
    async def check_rate_limit(self, key: str, limit: int, window: int) -> bool:
        """
        Check if request is within rate limit with configurable fallback behavior.
        
        Args:
            key: Unique identifier for rate limiting (e.g., IP address)
            limit: Maximum number of requests allowed
            window: Time window in seconds
            
        Returns:
            True if request is allowed, False if rate limited
            
        Raises:
            HTTPException: In strict mode when Redis unavailable
        """
        try:
            if not await self._ensure_connection():
                # Handle based on fallback mode
                return await self._handle_redis_unavailable(key, limit, window)
            
            # Normal Redis operation
            pipe = self.redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, window)
            results = await pipe.execute()
            
            current_count = results[0]
            is_allowed = current_count <= limit
            
            # Log rate limiting decision
            security_logger.log_rate_limit(
                key=key,
                allowed=is_allowed,
                current_count=current_count,
                limit=limit,
                window_seconds=window
            )
            
            if not is_allowed:
                logger.warning(f"Rate limit exceeded for {key}: {current_count}/{limit} in {window}s")
            
            return is_allowed
            
        except Exception as e:
            logger.error(f"Rate limiter error: {e}")
            # Apply fallback mode to errors too
            return await self._handle_redis_error(key, limit, window, e)
    
    async def _handle_redis_unavailable(self, key: str, limit: int, window: int) -> bool:
        """Handle Redis unavailability based on fallback mode"""
        # Log Redis fallback event for security monitoring
        security_logger.log_redis_fallback(
            fallback_mode=self.fallback_mode,
            reason="Redis connection unavailable",
            service="rate_limiter"
        )
        
        if self.fallback_mode == "strict":
            # Production: Fail closed for security
            logger.error("Redis unavailable in strict mode - failing closed")
            from fastapi import HTTPException
            raise HTTPException(
                status_code=503,
                detail="Rate limiting service temporarily unavailable"
            )
        elif self.fallback_mode == "degraded":
            # Development: Allow but warn
            logger.warning(f"Rate limiting degraded for {key} - Redis unavailable")
            return True
        else:  # local
            # Local development: Use in-memory
            logger.info(f"Using local rate limiting fallback for {key}")
            return await self._check_local_rate_limit(key, limit, window)
    
    async def _handle_redis_error(self, key: str, limit: int, window: int, error: Exception) -> bool:
        """Handle Redis errors based on fallback mode"""
        # Log Redis error event for security monitoring
        security_logger.log_redis_fallback(
            fallback_mode=self.fallback_mode,
            reason=f"Redis error: {str(error)}",
            service="rate_limiter"
        )
        
        if self.fallback_mode == "strict":
            logger.error(f"Redis error in strict mode: {error}")
            from fastapi import HTTPException
            raise HTTPException(503, "Rate limiting service error")
        elif self.fallback_mode == "degraded":
            logger.warning(f"Redis error in degraded mode - allowing request: {error}")
            return True
        else:  # local
            logger.warning(f"Redis error - using local fallback: {error}")
            return await self._check_local_rate_limit(key, limit, window)
    
    async def get_remaining_requests(self, key: str, limit: int) -> int:
        """
        Get remaining requests for a key.
        
        Args:
            key: Rate limit key
            limit: Maximum requests allowed
            
        Returns:
            Number of remaining requests (or limit if Redis unavailable)
        """
        try:
            if not await self._ensure_connection():
                return limit
                
            current = await self.redis.get(key)
            if not current:
                return limit
                
            return max(0, limit - int(current))
            
        except Exception as e:
            logger.error(f"Error getting remaining requests for {key}: {e}")
            return limit
    
    async def reset_rate_limit(self, key: str) -> bool:
        """
        Reset rate limit for a specific key.
        
        Args:
            key: Rate limit key to reset
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not await self._ensure_connection():
                return False
                
            await self.redis.delete(key)
            logger.info(f"Rate limit reset for key: {key}")
            return True
            
        except Exception as e:
            logger.error(f"Error resetting rate limit for {key}: {e}")
            return False
    
    async def close(self):
        """Close Redis connection."""
        if self.redis:
            try:
                await self.redis.close()
                logger.info("Redis rate limiter connection closed")
            except Exception as e:
                logger.warning(f"Error closing Redis connection: {e}")
            finally:
                self._connected = False
                self.redis = None


# Global rate limiter instance (initialized at startup)
_rate_limiter: Optional[RedisRateLimiter] = None


def get_rate_limiter() -> Optional[RedisRateLimiter]:
    """Get the global rate limiter instance."""
    return _rate_limiter


def initialize_rate_limiter(redis_url: str, fallback_mode: str = "strict") -> RedisRateLimiter:
    """
    Initialize the global rate limiter instance.
    
    Args:
        redis_url: Redis connection URL
        fallback_mode: Fallback behavior when Redis unavailable
        
    Returns:
        Initialized RedisRateLimiter instance
    """
    global _rate_limiter
    _rate_limiter = RedisRateLimiter(redis_url, fallback_mode)
    logger.info(f"Redis rate limiter initialized with fallback mode: {fallback_mode}")
    return _rate_limiter


async def shutdown_rate_limiter():
    """Shutdown the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter:
        await _rate_limiter.close()
        _rate_limiter = None
        logger.info("Redis rate limiter shutdown complete")