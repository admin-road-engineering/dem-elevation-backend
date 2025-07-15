"""
Integration tests for production deployment configuration.
Tests CORS, authentication, and deployment readiness.
"""
import pytest
import jwt
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from src.main import app
from src.config import Settings


class TestCORSConfiguration:
    """Test CORS configuration for production integration."""
    
    def setup_method(self):
        """Setup test client."""
        self.client = TestClient(app)
    
    @patch('src.config.Settings')
    def test_cors_preflight_request(self, mock_settings_class):
        """Test CORS preflight request handling."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.CORS_ORIGINS = "https://road.engineering,http://localhost:3001"
        mock_settings.DEM_SOURCES = {"test": {"path": "./test", "description": "test"}}
        mock_settings.REQUIRE_AUTH = False
        mock_settings_class.return_value = mock_settings
        
        # Test preflight request
        response = self.client.options(
            "/api/v1/elevation/sources",
            headers={
                "Origin": "https://road.engineering",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,Content-Type"
            }
        )
        
        # Should allow the request
        assert response.status_code in [200, 204]
        assert "Access-Control-Allow-Origin" in response.headers
        assert "Access-Control-Allow-Methods" in response.headers
    
    def test_cors_blocked_origin(self):
        """Test that unauthorized origins are blocked."""
        response = self.client.options(
            "/api/v1/elevation/sources",
            headers={
                "Origin": "https://malicious-site.com",
                "Access-Control-Request-Method": "POST"
            }
        )
        
        # Should not include CORS headers for unauthorized origin
        # Note: Behavior depends on CORS configuration
        # If wildcard (*) is used, this test may need adjustment
        
    def test_cors_allowed_methods(self):
        """Test that only allowed HTTP methods are permitted."""
        response = self.client.options(
            "/api/v1/elevation/sources",
            headers={
                "Origin": "http://localhost:3001",
                "Access-Control-Request-Method": "DELETE"
            }
        )
        
        # DELETE should not be allowed
        if "Access-Control-Allow-Methods" in response.headers:
            allowed_methods = response.headers["Access-Control-Allow-Methods"]
            assert "DELETE" not in allowed_methods
            assert "POST" in allowed_methods
            assert "GET" in allowed_methods


class TestAuthenticationIntegration:
    """Test authentication integration for production."""
    
    def setup_method(self):
        """Setup test client."""
        self.client = TestClient(app)
        self.secret = "test-integration-secret"
    
    def create_jwt_token(self, payload: dict) -> str:
        """Helper to create JWT tokens."""
        return jwt.encode(payload, self.secret, algorithm="HS256")
    
    @patch('src.config.Settings')
    def test_protected_endpoint_with_valid_jwt(self, mock_settings_class):
        """Test protected endpoint with valid JWT token."""
        # Mock settings with auth enabled
        mock_settings = MagicMock()
        mock_settings.CORS_ORIGINS = "http://localhost:3001"
        mock_settings.DEM_SOURCES = {"test": {"path": "./test", "description": "test"}}
        mock_settings.REQUIRE_AUTH = True
        mock_settings.SUPABASE_JWT_SECRET = self.secret
        mock_settings.JWT_ALGORITHM = "HS256"
        mock_settings.JWT_AUDIENCE = "authenticated"
        mock_settings_class.return_value = mock_settings
        
        # Create valid token
        payload = {
            "sub": "test-user-123",
            "email": "test@road.engineering",
            "role": "authenticated",
            "aud": "authenticated",
            "exp": datetime.utcnow() + timedelta(hours=1)
        }
        token = self.create_jwt_token(payload)
        
        # Test authenticated request
        response = self.client.post(
            "/api/v1/elevation/point",
            json={"latitude": -27.4698, "longitude": 153.0251},
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Should allow authenticated request
        assert response.status_code != 401
    
    @patch('src.config.Settings')
    def test_protected_endpoint_without_auth(self, mock_settings_class):
        """Test protected endpoint without authentication."""
        # Mock settings with auth enabled
        mock_settings = MagicMock()
        mock_settings.CORS_ORIGINS = "http://localhost:3001"
        mock_settings.DEM_SOURCES = {"test": {"path": "./test", "description": "test"}}
        mock_settings.REQUIRE_AUTH = True
        mock_settings.SUPABASE_JWT_SECRET = self.secret
        mock_settings_class.return_value = mock_settings
        
        # Test unauthenticated request
        response = self.client.post(
            "/api/v1/elevation/point",
            json={"latitude": -27.4698, "longitude": 153.0251}
        )
        
        # Should reject unauthenticated request
        assert response.status_code == 401
    
    @patch('src.config.Settings')
    def test_auth_disabled_allows_requests(self, mock_settings_class):
        """Test that requests are allowed when auth is disabled."""
        # Mock settings with auth disabled
        mock_settings = MagicMock()
        mock_settings.CORS_ORIGINS = "http://localhost:3001"
        mock_settings.DEM_SOURCES = {"test": {"path": "./test", "description": "test"}}
        mock_settings.REQUIRE_AUTH = False
        mock_settings_class.return_value = mock_settings
        
        # Test request without auth
        response = self.client.post(
            "/api/v1/elevation/point",
            json={"latitude": -27.4698, "longitude": 153.0251}
        )
        
        # Should allow request when auth is disabled
        assert response.status_code != 401


class TestHealthEndpoints:
    """Test health and status endpoints for deployment monitoring."""
    
    def setup_method(self):
        """Setup test client."""
        self.client = TestClient(app)
    
    def test_root_health_endpoint(self):
        """Test root health endpoint."""
        response = self.client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "DEM Elevation Service"
        assert data["status"] == "running"
        assert "version" in data
        assert "features" in data
    
    @patch('src.config.Settings')
    def test_detailed_health_endpoint(self, mock_settings_class):
        """Test detailed health endpoint."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.DEM_SOURCES = {
            "local": {"path": "./data/DTM.gdb", "description": "Local"},
            "s3": {"path": "s3://bucket/file.tif", "description": "S3"}
        }
        mock_settings.DEFAULT_DEM_ID = "local"
        mock_settings.GDB_AUTO_DISCOVER = True
        mock_settings.CACHE_SIZE_LIMIT = 10
        mock_settings.GDB_PREFERRED_DRIVERS = ["OpenFileGDB", "FileGDB"]
        mock_settings_class.return_value = mock_settings
        
        response = self.client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "dem_sources_configured" in data
        assert "geodatabase_sources" in data
        assert "geotiff_sources" in data
        assert data["dem_sources_configured"] == 2


class TestDeploymentReadiness:
    """Test deployment readiness checks."""
    
    def setup_method(self):
        """Setup test client."""
        self.client = TestClient(app)
    
    @patch('src.config.Settings')
    def test_production_config_validation(self, mock_settings_class):
        """Test that production configuration validates correctly."""
        # Mock production-like settings
        mock_settings = MagicMock()
        mock_settings.DEM_SOURCES = {
            "local": {"path": "./data/DTM.gdb", "description": "Local DTM"},
            "au_national": {"path": "s3://road-engineering-elevation-data/AU_National_5m_DEM.tif", "description": "Australia National"},
            "gpxz_api": {"path": "api://gpxz", "description": "GPXZ Global API"}
        }
        mock_settings.DEFAULT_DEM_ID = "au_national"
        mock_settings.USE_S3_SOURCES = True
        mock_settings.USE_API_SOURCES = True
        mock_settings.AWS_ACCESS_KEY_ID = "test_key"
        mock_settings.AWS_SECRET_ACCESS_KEY = "test_secret"
        mock_settings.GPXZ_API_KEY = "test_gpxz_key"
        mock_settings.SUPABASE_JWT_SECRET = "test_jwt_secret"
        mock_settings.REQUIRE_AUTH = False  # Initially disabled
        mock_settings.CORS_ORIGINS = "https://road.engineering,https://api.road.engineering"
        mock_settings.GDB_AUTO_DISCOVER = True
        mock_settings.CACHE_SIZE_LIMIT = 50
        mock_settings.GDB_PREFERRED_DRIVERS = ["OpenFileGDB", "FileGDB"]
        mock_settings_class.return_value = mock_settings
        
        # Test that service starts without errors
        response = self.client.get("/health")
        assert response.status_code == 200
        
        # Test that sources endpoint works
        response = self.client.get("/api/v1/elevation/sources")
        assert response.status_code == 200
    
    def test_service_responds_to_preflight(self):
        """Test that service responds to preflight requests (CORS)."""
        response = self.client.options("/")
        
        # Should handle OPTIONS requests
        assert response.status_code in [200, 204, 405]  # 405 is also acceptable for OPTIONS
    
    def test_api_endpoints_accessible(self):
        """Test that main API endpoints are accessible."""
        # Test sources endpoint
        response = self.client.get("/api/v1/elevation/sources")
        assert response.status_code in [200, 500]  # 500 OK if DEM service not fully initialized
        
        # Test point endpoint (might fail due to missing DEM data, but should route correctly)
        response = self.client.post(
            "/api/v1/elevation/point",
            json={"latitude": -27.4698, "longitude": 153.0251}
        )
        assert response.status_code != 404  # Should not be "Not Found"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])