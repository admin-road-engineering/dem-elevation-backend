"""
Simple rate limiter for deployment recovery.
This replaces the complex Redis rate limiter temporarily.
"""
import logging
from typing import Optional
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

# Simple in-memory rate limiter for deployment recovery
_simple_limiter: Optional[Limiter] = None

def get_rate_limiter() -> Optional[Limiter]:
    """Get a simple rate limiter instance."""
    global _simple_limiter
    if _simple_limiter is None:
        logger.info("Initializing simple in-memory rate limiter for deployment recovery")
        _simple_limiter = Limiter(key_func=get_remote_address)
    return _simple_limiter

def initialize_rate_limiter(redis_url: str, fallback_mode: str = "strict") -> Limiter:
    """Initialize simple rate limiter (ignores Redis for now)."""
    logger.warning(f"Using simple rate limiter (ignoring Redis URL for deployment recovery)")
    return get_rate_limiter()

async def shutdown_rate_limiter():
    """Shutdown rate limiter (no-op for simple implementation)."""
    logger.info("Shutting down simple rate limiter (no-op)")
    pass