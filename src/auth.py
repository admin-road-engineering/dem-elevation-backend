"""
JWT Authentication module for DEM Backend.
Integrates with Supabase JWT from the main Road Engineering platform.
"""
import logging
from typing import Optional, Dict, Any
import jwt
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .config import get_settings

logger = logging.getLogger(__name__)

# JWT Security scheme
security = HTTPBearer(auto_error=False)

class AuthConfig:
    """Authentication configuration."""
    def __init__(self, settings):
        self.supabase_jwt_secret = getattr(settings, 'SUPABASE_JWT_SECRET', None)
        self.jwt_algorithm = getattr(settings, 'JWT_ALGORITHM', 'HS256')
        self.jwt_audience = getattr(settings, 'JWT_AUDIENCE', 'authenticated')
        self.require_auth = getattr(settings, 'REQUIRE_AUTH', True)

async def verify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Any]]:
    """
    Verify JWT token from Supabase.
    
    Returns:
        Dict containing user information if token is valid
        None if authentication is disabled or token is optional
    
    Raises:
        HTTPException: If token is invalid or required but missing
    """
    settings = get_settings()
    auth_config = AuthConfig(settings)
    
    # If authentication is disabled, return None
    if not auth_config.require_auth:
        logger.debug("Authentication disabled, allowing request")
        return None
    
    # If no JWT secret is configured, log warning and allow request
    if not auth_config.supabase_jwt_secret:
        logger.warning("SUPABASE_JWT_SECRET not configured, authentication disabled")
        return None
    
    # If no credentials provided
    if not credentials:
        if auth_config.require_auth:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return None
    
    try:
        # Decode and verify JWT token
        payload = jwt.decode(
            credentials.credentials,
            auth_config.supabase_jwt_secret,
            algorithms=[auth_config.jwt_algorithm],
            audience=auth_config.jwt_audience
        )
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID"
            )
        
        logger.debug(f"Successfully authenticated user: {user_id}")
        
        return {
            "user_id": user_id,
            "email": payload.get("email"),
            "role": payload.get("role", "authenticated"),
            "exp": payload.get("exp"),
            "aud": payload.get("aud"),
            "iss": payload.get("iss")
        }
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except HTTPException:
        # Re-raise HTTPExceptions as-is (they're already properly formatted)
        raise
    except Exception as e:
        logger.error(f"Unexpected authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service error"
        )

async def get_current_user(
    user_data: Optional[Dict[str, Any]] = Depends(verify_token)
) -> Optional[Dict[str, Any]]:
    """
    Get current authenticated user.
    Returns None if authentication is disabled.
    """
    return user_data

# Convenience function for endpoints that require authentication
async def require_auth(
    user_data: Optional[Dict[str, Any]] = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Require authentication for an endpoint.
    Raises HTTPException if user is not authenticated.
    """
    if user_data is None:
        # This should only happen if auth is disabled
        settings = get_settings()
        if not getattr(settings, 'REQUIRE_AUTH', True):
            # Return a mock user for development
            return {"user_id": "dev-user", "role": "authenticated"}
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    return user_data