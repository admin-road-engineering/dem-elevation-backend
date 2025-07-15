"""
Test suite for JWT authentication module.
Tests valid/invalid/expired token scenarios with mocked JWTs.
Uses shared fixtures for consistent testing.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

from src.auth import verify_token, get_current_user, require_auth, AuthConfig
from tests.conftest import assert_http_exception


class TestAuthConfig:
    """Test AuthConfig class initialization and configuration."""
    
    def test_auth_config_with_all_settings(self, mock_settings, test_secrets):
        """Test AuthConfig with all settings provided."""
        mock_settings.SUPABASE_JWT_SECRET = test_secrets.JWT_SECRET
        mock_settings.JWT_ALGORITHM = "HS512"
        mock_settings.JWT_AUDIENCE = "test-audience"
        mock_settings.REQUIRE_AUTH = False
        
        config = AuthConfig(mock_settings)
        
        assert config.supabase_jwt_secret == test_secrets.JWT_SECRET
        assert config.jwt_algorithm == "HS512"
        assert config.jwt_audience == "test-audience"
        assert config.require_auth == False
    
    def test_auth_config_with_defaults(self):
        """Test AuthConfig with default values."""
        mock_settings = MagicMock()
        mock_settings.SUPABASE_JWT_SECRET = None
        del mock_settings.JWT_ALGORITHM  # Attribute doesn't exist
        del mock_settings.JWT_AUDIENCE
        del mock_settings.REQUIRE_AUTH
        
        config = AuthConfig(mock_settings)
        
        assert config.supabase_jwt_secret is None
        assert config.jwt_algorithm == "HS256"
        assert config.jwt_audience == "authenticated"
        assert config.require_auth == True


class TestJWTVerification:
    """Test JWT token verification with various scenarios."""
    
    @pytest.fixture
    def valid_secret(self):
        return "test-jwt-secret-for-testing"
    
    @pytest.fixture
    def valid_payload(self):
        """Create a valid JWT payload."""
        return {
            "sub": "user-123",
            "email": "test@example.com",
            "role": "authenticated",
            "aud": "authenticated",
            "iss": "supabase",
            "exp": datetime.utcnow() + timedelta(hours=1)
        }
    
    @pytest.fixture
    def expired_payload(self):
        """Create an expired JWT payload."""
        return {
            "sub": "user-123", 
            "email": "test@example.com",
            "aud": "authenticated",
            "exp": datetime.utcnow() - timedelta(hours=1)  # Expired
        }
    
    def create_token(self, payload: dict, secret: str, algorithm: str = "HS256") -> str:
        """Helper to create JWT tokens."""
        return jwt.encode(payload, secret, algorithm=algorithm)
    
    @patch('src.auth.get_settings')
    @pytest.mark.asyncio
    async def test_verify_token_valid(self, mock_get_settings, valid_payload, valid_secret):
        """Test successful JWT token verification."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.SUPABASE_JWT_SECRET = valid_secret
        mock_settings.JWT_ALGORITHM = "HS256"
        mock_settings.JWT_AUDIENCE = "authenticated"
        mock_settings.REQUIRE_AUTH = True
        mock_get_settings.return_value = mock_settings
        
        # Create valid token
        token = self.create_token(valid_payload, valid_secret)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        
        # Verify token
        result = await verify_token(credentials)
        
        assert result is not None
        assert result["user_id"] == "user-123"
        assert result["email"] == "test@example.com"
        assert result["role"] == "authenticated"
        assert "exp" in result
    
    @patch('src.auth.get_settings')
    @pytest.mark.asyncio
    async def test_verify_token_expired(self, mock_get_settings, expired_payload, valid_secret):
        """Test JWT token verification with expired token."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.SUPABASE_JWT_SECRET = valid_secret
        mock_settings.JWT_ALGORITHM = "HS256"
        mock_settings.JWT_AUDIENCE = "authenticated"
        mock_settings.REQUIRE_AUTH = True
        mock_get_settings.return_value = mock_settings
        
        # Create expired token
        token = self.create_token(expired_payload, valid_secret)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        
        # Should raise HTTPException for expired token
        with pytest.raises(HTTPException) as exc_info:
            await verify_token(credentials)
        
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()
    
    @patch('src.auth.get_settings')
    @pytest.mark.asyncio
    async def test_verify_token_invalid_signature(self, mock_get_settings, valid_payload, valid_secret):
        """Test JWT token verification with invalid signature."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.SUPABASE_JWT_SECRET = valid_secret
        mock_settings.JWT_ALGORITHM = "HS256"
        mock_settings.JWT_AUDIENCE = "authenticated"
        mock_settings.REQUIRE_AUTH = True
        mock_get_settings.return_value = mock_settings
        
        # Create token with wrong secret
        token = self.create_token(valid_payload, "wrong-secret")
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        
        # Should raise HTTPException for invalid signature
        with pytest.raises(HTTPException) as exc_info:
            await verify_token(credentials)
        
        assert exc_info.value.status_code == 401
        assert "invalid" in exc_info.value.detail.lower()
    
    @patch('src.auth.get_settings')
    @pytest.mark.asyncio
    async def test_verify_token_missing_user_id(self, mock_get_settings, valid_secret):
        """Test JWT token verification with missing user ID."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.SUPABASE_JWT_SECRET = valid_secret
        mock_settings.JWT_ALGORITHM = "HS256"
        mock_settings.JWT_AUDIENCE = "authenticated"
        mock_settings.REQUIRE_AUTH = True
        mock_get_settings.return_value = mock_settings
        
        # Create token without 'sub' field
        payload = {
            "email": "test@example.com",
            "aud": "authenticated",
            "exp": datetime.utcnow() + timedelta(hours=1)
        }
        token = self.create_token(payload, valid_secret)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        
        # Should raise HTTPException for missing user ID
        with pytest.raises(HTTPException) as exc_info:
            await verify_token(credentials)
        
        assert exc_info.value.status_code == 401
        assert "missing user id" in exc_info.value.detail.lower()
    
    @patch('src.auth.get_settings')
    @pytest.mark.asyncio
    async def test_verify_token_auth_disabled(self, mock_get_settings):
        """Test JWT verification when authentication is disabled."""
        # Mock settings with auth disabled
        mock_settings = MagicMock()
        mock_settings.REQUIRE_AUTH = False
        mock_get_settings.return_value = mock_settings
        
        # No credentials provided
        result = await verify_token(None)
        
        assert result is None
    
    @patch('src.auth.get_settings')
    @pytest.mark.asyncio
    async def test_verify_token_no_secret_configured(self, mock_get_settings):
        """Test JWT verification when no secret is configured."""
        # Mock settings without JWT secret
        mock_settings = MagicMock()
        mock_settings.SUPABASE_JWT_SECRET = None
        mock_settings.REQUIRE_AUTH = True
        mock_get_settings.return_value = mock_settings
        
        # No credentials provided
        result = await verify_token(None)
        
        assert result is None
    
    @patch('src.auth.get_settings')
    @pytest.mark.asyncio
    async def test_verify_token_no_credentials_auth_required(self, mock_get_settings):
        """Test JWT verification when credentials required but not provided."""
        # Mock settings with auth required
        mock_settings = MagicMock()
        mock_settings.SUPABASE_JWT_SECRET = "test-secret"
        mock_settings.REQUIRE_AUTH = True
        mock_get_settings.return_value = mock_settings
        
        # Should raise HTTPException when auth required but no credentials
        with pytest.raises(HTTPException) as exc_info:
            await verify_token(None)
        
        assert exc_info.value.status_code == 401
        assert "authentication required" in exc_info.value.detail.lower()


class TestAuthHelpers:
    """Test authentication helper functions."""
    
    @pytest.mark.asyncio
    async def test_get_current_user_with_valid_data(self):
        """Test get_current_user with valid user data."""
        user_data = {
            "user_id": "user-123",
            "email": "test@example.com",
            "role": "authenticated"
        }
        
        result = await get_current_user(user_data)
        assert result == user_data
    
    @pytest.mark.asyncio
    async def test_get_current_user_with_none(self):
        """Test get_current_user when authentication disabled."""
        result = await get_current_user(None)
        assert result is None
    
    @patch('src.auth.get_settings')
    @pytest.mark.asyncio
    async def test_require_auth_with_valid_user(self, mock_get_settings):
        """Test require_auth with valid user data."""
        user_data = {
            "user_id": "user-123",
            "email": "test@example.com",
            "role": "authenticated"
        }
        
        result = await require_auth(user_data)
        assert result == user_data
    
    @patch('src.auth.get_settings')
    @pytest.mark.asyncio
    async def test_require_auth_with_none_auth_disabled(self, mock_get_settings):
        """Test require_auth when auth is disabled."""
        # Mock settings with auth disabled
        mock_settings = MagicMock()
        mock_settings.REQUIRE_AUTH = False
        mock_get_settings.return_value = mock_settings
        
        result = await require_auth(None)
        
        # Should return mock user for development
        assert result["user_id"] == "dev-user"
        assert result["role"] == "authenticated"
    
    @patch('src.auth.get_settings')
    @pytest.mark.asyncio
    async def test_require_auth_with_none_auth_enabled(self, mock_get_settings):
        """Test require_auth when auth is enabled but no user provided."""
        # Mock settings with auth enabled
        mock_settings = MagicMock()
        mock_settings.REQUIRE_AUTH = True
        mock_get_settings.return_value = mock_settings
        
        # Should raise HTTPException when auth required but no user
        with pytest.raises(HTTPException) as exc_info:
            await require_auth(None)
        
        assert exc_info.value.status_code == 401
        assert "authentication required" in exc_info.value.detail.lower()


class TestAuthIntegration:
    """Integration tests for authentication with actual settings."""
    
    @patch.dict('os.environ', {
        'SUPABASE_JWT_SECRET': 'test-integration-secret',
        'REQUIRE_AUTH': 'true',
        'JWT_ALGORITHM': 'HS256',
        'JWT_AUDIENCE': 'authenticated'
    })
    @pytest.mark.asyncio
    async def test_auth_integration_flow(self):
        """Test complete authentication flow with environment variables."""
        # Create a valid token
        payload = {
            "sub": "integration-user-123",
            "email": "integration@example.com",
            "role": "authenticated",
            "aud": "authenticated",
            "exp": datetime.utcnow() + timedelta(hours=1)
        }
        token = jwt.encode(payload, "test-integration-secret", algorithm="HS256")
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        
        # Test the full flow
        with patch('src.auth.get_settings') as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.SUPABASE_JWT_SECRET = "test-integration-secret"
            mock_settings.JWT_ALGORITHM = "HS256"
            mock_settings.JWT_AUDIENCE = "authenticated"
            mock_settings.REQUIRE_AUTH = True
            mock_get_settings.return_value = mock_settings
            
            # Verify token
            user_data = await verify_token(credentials)
            assert user_data["user_id"] == "integration-user-123"
            
            # Get current user
            current_user = await get_current_user(user_data)
            assert current_user == user_data
            
            # Require auth
            required_user = await require_auth(user_data)
            assert required_user == user_data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])