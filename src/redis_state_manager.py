"""
Redis State Manager - Process-safe state management for multi-worker FastAPI deployment
Replaces JSON file-based state management with atomic Redis operations
"""
import logging
import redis
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
import asyncio
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class RedisStateManager:
    """Process-safe state management using Redis atomic operations"""
    
    def __init__(self, redis_url: Optional[str] = None, app_env: Optional[str] = None):
        """
        Initialize Redis connection with Railway or fallback configuration.
        
        Phase 3B.1: Added app_env parameter for production safety checks.
        """
        self.redis_url = redis_url or os.getenv('REDIS_URL') or os.getenv('REDIS_PRIVATE_URL') or 'redis://localhost:6379'
        self.app_env = app_env or os.getenv('APP_ENV', 'local')
        self._redis_client = None
        self._connection_tested = False
        
    def _get_redis_client(self) -> redis.Redis:
        """
        Get Redis client with lazy initialization and connection testing.
        
        Phase 3B.1: Fail-fast in production if Redis unavailable to prevent
        inconsistent state across multiple Railway workers.
        """
        if self._redis_client is None:
            try:
                self._redis_client = redis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True
                )
                
                # Test connection on first use
                if not self._connection_tested:
                    self._redis_client.ping()
                    self._connection_tested = True
                    logger.info(f"Redis connection established: {self.redis_url.split('@')[-1] if '@' in self.redis_url else self.redis_url}")
                    
            except Exception as e:
                logger.error(f"Redis connection failed: {e}")
                
                # Phase 3B.1: Fail-fast in production for safety
                if self.app_env == 'production':
                    logger.critical("FATAL: Redis connection failed in production environment. Service cannot start safely.")
                    raise RuntimeError(f"Redis connection failed in production: {e}") from e
                
                # Only allow fallback in local development
                logger.warning("Falling back to in-memory state (NOT process-safe) - LOCAL DEVELOPMENT ONLY")
                if not hasattr(self, '_fallback_storage'):
                    self._fallback_storage = {}
                return None
                
        return self._redis_client
    
    def _fallback_get(self, key: str) -> Optional[str]:
        """Fallback to in-memory storage when Redis unavailable"""
        if not hasattr(self, '_fallback_storage'):
            self._fallback_storage = {}
        return self._fallback_storage.get(key)
    
    def _fallback_set(self, key: str, value: str, ex: Optional[int] = None):
        """Fallback to in-memory storage when Redis unavailable"""
        if not hasattr(self, '_fallback_storage'):
            self._fallback_storage = {}
        self._fallback_storage[key] = value
        # Note: expiration not implemented in fallback
    
    def _fallback_incr(self, key: str) -> int:
        """Fallback to in-memory storage when Redis unavailable"""
        if not hasattr(self, '_fallback_storage'):
            self._fallback_storage = {}
        current = int(self._fallback_storage.get(key, '0'))
        self._fallback_storage[key] = str(current + 1)
        return current + 1

class RedisS3CostManager:
    """Redis-based S3 cost manager with atomic operations"""
    
    def __init__(self, redis_manager: RedisStateManager, daily_gb_limit: float = 1.0):
        self.redis_manager = redis_manager
        self.daily_gb_limit = daily_gb_limit
        self.usage_key_prefix = "s3_usage"
        
    def _get_daily_key(self) -> str:
        """Get Redis key for today's usage"""
        today = datetime.now().strftime("%Y-%m-%d")
        return f"{self.usage_key_prefix}:{today}"
    
    def can_access_s3(self, estimated_mb: float = 10) -> bool:
        """Check if we're within daily limits using atomic Redis operations"""
        try:
            redis_client = self.redis_manager._get_redis_client()
            if redis_client is None:
                # Fallback: always allow (risky but better than breaking)
                logger.warning("Redis unavailable for S3 cost check, allowing access")
                return True
            
            daily_key = self._get_daily_key()
            current_usage_mb = float(redis_client.hget(daily_key, "mb_used") or "0")
            
            estimated_total_mb = current_usage_mb + estimated_mb
            estimated_total_gb = estimated_total_mb / 1024
            
            within_limit = estimated_total_gb <= self.daily_gb_limit
            
            if not within_limit:
                logger.warning(f"S3 daily limit would be exceeded: {estimated_total_gb:.2f}GB > {self.daily_gb_limit}GB")
            
            return within_limit
            
        except Exception as e:
            logger.error(f"Error checking S3 limits: {e}")
            return True  # Fail open
    
    def record_access(self, size_mb: float):
        """Record S3 access using atomic Redis operations"""
        try:
            redis_client = self.redis_manager._get_redis_client()
            if redis_client is None:
                logger.warning("Redis unavailable for S3 usage recording")
                return
            
            daily_key = self._get_daily_key()
            
            # Atomic operations using Redis pipeline
            with redis_client.pipeline() as pipe:
                pipe.hincrbyfloat(daily_key, "mb_used", size_mb)
                pipe.hincrby(daily_key, "requests", 1)
                pipe.hset(daily_key, "last_access", datetime.now().isoformat())
                pipe.expire(daily_key, 86400 * 2)  # Keep for 2 days
                results = pipe.execute()
            
            total_mb = results[0]
            total_requests = results[1]
            
            logger.info(f"S3 Usage recorded: {total_mb:.2f}MB ({total_requests} requests) - {total_mb/1024:.3f}GB / {self.daily_gb_limit}GB limit")
            
        except Exception as e:
            logger.error(f"Error recording S3 access: {e}")
    
    def get_usage_stats(self) -> Dict[str, float]:
        """Get current usage statistics"""
        try:
            redis_client = self.redis_manager._get_redis_client()
            if redis_client is None:
                return {"mb_used": 0.0, "requests": 0, "gb_limit": self.daily_gb_limit}
            
            daily_key = self._get_daily_key()
            usage_data = redis_client.hgetall(daily_key)
            
            return {
                "mb_used": float(usage_data.get("mb_used", "0")),
                "requests": int(usage_data.get("requests", "0")),
                "gb_used": float(usage_data.get("mb_used", "0")) / 1024,
                "gb_limit": self.daily_gb_limit,
                "last_access": usage_data.get("last_access", "never")
            }
            
        except Exception as e:
            logger.error(f"Error getting usage stats: {e}")
            return {"mb_used": 0.0, "requests": 0, "gb_limit": self.daily_gb_limit}

class RedisCircuitBreaker:
    """Redis-based circuit breaker with process-safe state"""
    
    def __init__(self, redis_manager: RedisStateManager, service_name: str, 
                 failure_threshold: int = 3, recovery_timeout: int = 300):
        self.redis_manager = redis_manager
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_key = f"circuit_breaker:{service_name}:failures"
        self.last_failure_key = f"circuit_breaker:{service_name}:last_failure"
    
    def is_available(self) -> bool:
        """
        Check if service is available (circuit closed).
        
        Phase 3B.1: Fail-fast in production if Redis unavailable.
        """
        try:
            redis_client = self.redis_manager._get_redis_client()
            if redis_client is None:
                # Phase 3B.1: In production, Redis failure should have already raised an exception
                # If we somehow reach here in production, it's a critical error
                if self.redis_manager.app_env == 'production':
                    logger.critical(f"FATAL: Circuit breaker for {self.service_name} cannot function without Redis in production")
                    raise RuntimeError(f"Circuit breaker unavailable in production: Redis connection failed")
                
                # Only allow fail-open in local development
                logger.warning(f"Circuit breaker for {self.service_name} failing open - Redis unavailable (LOCAL DEV ONLY)")
                return True
            
            failure_count = int(redis_client.get(self.failure_key) or "0")
            
            if failure_count < self.failure_threshold:
                return True
            
            # Check if recovery timeout has passed
            last_failure_str = redis_client.get(self.last_failure_key)
            if last_failure_str:
                last_failure = datetime.fromisoformat(last_failure_str)
                recovery_time = last_failure + timedelta(seconds=self.recovery_timeout)
                if datetime.now() > recovery_time:
                    # Reset circuit breaker
                    self.reset()
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking circuit breaker for {self.service_name}: {e}")
            return True  # Fail open
    
    def record_failure(self):
        """Record a failure (atomic increment)"""
        try:
            redis_client = self.redis_manager._get_redis_client()
            if redis_client is None:
                return
            
            with redis_client.pipeline() as pipe:
                pipe.incr(self.failure_key)
                pipe.set(self.last_failure_key, datetime.now().isoformat())
                pipe.expire(self.failure_key, self.recovery_timeout * 2)
                pipe.expire(self.last_failure_key, self.recovery_timeout * 2)
                results = pipe.execute()
            
            failure_count = results[0]
            logger.warning(f"Circuit breaker failure recorded for {self.service_name}: {failure_count}/{self.failure_threshold}")
            
        except Exception as e:
            logger.error(f"Error recording circuit breaker failure for {self.service_name}: {e}")
    
    def record_success(self):
        """Record a success (reset failure count)"""
        try:
            redis_client = self.redis_manager._get_redis_client()
            if redis_client is None:
                return
            
            redis_client.delete(self.failure_key, self.last_failure_key)
            logger.debug(f"Circuit breaker reset for {self.service_name}")
            
        except Exception as e:
            logger.error(f"Error recording circuit breaker success for {self.service_name}: {e}")
    
    def reset(self):
        """Manually reset circuit breaker"""
        try:
            redis_client = self.redis_manager._get_redis_client()
            if redis_client is None:
                return
            
            redis_client.delete(self.failure_key, self.last_failure_key)
            logger.info(f"Circuit breaker manually reset for {self.service_name}")
            
        except Exception as e:
            logger.error(f"Error resetting circuit breaker for {self.service_name}: {e}")
    
    @property
    def failure_count(self) -> int:
        """Get current failure count from Redis"""
        try:
            redis_client = self.redis_manager._get_redis_client()
            if redis_client is None:
                return 0
            
            return int(redis_client.get(self.failure_key) or "0")
            
        except Exception as e:
            logger.error(f"Error getting failure count for {self.service_name}: {e}")
            return 0

class RedisRateLimiter:
    """Redis-based rate limiter for API clients"""
    
    def __init__(self, redis_manager: RedisStateManager, service_name: str, 
                 requests_per_second: int = 1, daily_limit: int = 100):
        self.redis_manager = redis_manager
        self.service_name = service_name
        self.requests_per_second = requests_per_second
        self.daily_limit = daily_limit
        self.rate_key = f"rate_limit:{service_name}:per_second"
        self.daily_key_prefix = f"rate_limit:{service_name}:daily"
    
    def _get_daily_key(self) -> str:
        """Get Redis key for today's requests"""
        today = datetime.now().strftime("%Y-%m-%d")
        return f"{self.daily_key_prefix}:{today}"
    
    async def wait_if_needed(self):
        """Enforce rate limiting with Redis atomic operations"""
        try:
            redis_client = self.redis_manager._get_redis_client()
            if redis_client is None:
                # Fallback: basic sleep
                await asyncio.sleep(1.0 / self.requests_per_second)
                return
            
            # Check daily limit first
            daily_key = self._get_daily_key()
            daily_count = int(redis_client.get(daily_key) or "0")
            
            if daily_count >= self.daily_limit:
                from ..error_handling import NonRetryableError, SourceType
                raise NonRetryableError(f"{self.service_name} daily limit reached ({self.daily_limit} requests)", SourceType.API)
            
            # Rate limiting using sliding window
            current_second = int(datetime.now().timestamp())
            rate_key_current = f"{self.rate_key}:{current_second}"
            
            # Atomic increment and check
            with redis_client.pipeline() as pipe:
                pipe.incr(rate_key_current)
                pipe.expire(rate_key_current, 2)  # Keep for 2 seconds
                pipe.incr(daily_key)
                pipe.expire(daily_key, 86400)  # Keep for 24 hours
                results = pipe.execute()
            
            current_second_count = results[0]
            
            if current_second_count > self.requests_per_second:
                # Need to wait
                sleep_time = 1.0
                logger.debug(f"Rate limiting {self.service_name}: sleeping {sleep_time}s")
                await asyncio.sleep(sleep_time)
            
        except Exception as e:
            logger.error(f"Error in rate limiting for {self.service_name}: {e}")
            # Fallback: basic sleep
            await asyncio.sleep(1.0 / self.requests_per_second)
    
    def get_usage_stats(self) -> Dict[str, int]:
        """Get current usage statistics"""
        try:
            redis_client = self.redis_manager._get_redis_client()
            if redis_client is None:
                return {"daily_requests_used": 0, "daily_limit": self.daily_limit, "requests_remaining": self.daily_limit}
            
            daily_key = self._get_daily_key()
            daily_count = int(redis_client.get(daily_key) or "0")
            
            return {
                "daily_requests_used": daily_count,
                "daily_limit": self.daily_limit,
                "requests_remaining": max(0, self.daily_limit - daily_count),
                "rate_limit_per_second": self.requests_per_second
            }
            
        except Exception as e:
            logger.error(f"Error getting rate limit stats for {self.service_name}: {e}")
            return {"daily_requests_used": 0, "daily_limit": self.daily_limit, "requests_remaining": self.daily_limit}