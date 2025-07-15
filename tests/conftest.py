"""
Shared test fixtures for DEM Backend test suite.
Provides reusable mocks and test data for authentication, configuration, and integration tests.
"""
import pytest
import jwt
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from fastapi.security import HTTPAuthorizationCredentials

from src.main import app


class TestSecrets:
    """Test secrets and keys for consistent testing."""
    JWT_SECRET = "test-jwt-secret-for-all-tests"
    INVALID_JWT_SECRET = "wrong-secret-for-testing"
    AWS_ACCESS_KEY = "test-aws-access-key"
    AWS_SECRET_KEY = "test-aws-secret-key"
    GPXZ_API_KEY = "test-gpxz-api-key"


@pytest.fixture
def test_secrets():
    """Provide test secrets for consistent testing."""
    return TestSecrets()


@pytest.fixture
def mock_settings():
    """Base mock settings for testing."""
    settings = MagicMock()
    settings.DEM_SOURCES = {
        "local_test": {
            "path": "./data/test.gdb",
            "description": "Test local source"
        },
        "s3_test": {
            "path": "s3://test-bucket/test.tif",
            "description": "Test S3 source"
        },
        "api_test": {
            "path": "api://gpxz",
            "description": "Test API source"
        }
    }
    settings.DEFAULT_DEM_ID = "local_test"
    settings.USE_S3_SOURCES = True
    settings.USE_API_SOURCES = True
    settings.AWS_ACCESS_KEY_ID = TestSecrets.AWS_ACCESS_KEY
    settings.AWS_SECRET_ACCESS_KEY = TestSecrets.AWS_SECRET_KEY
    settings.GPXZ_API_KEY = TestSecrets.GPXZ_API_KEY
    settings.SUPABASE_JWT_SECRET = TestSecrets.JWT_SECRET
    settings.JWT_ALGORITHM = "HS256"
    settings.JWT_AUDIENCE = "authenticated"
    settings.REQUIRE_AUTH = True
    settings.CORS_ORIGINS = "http://localhost:3001,https://road.engineering"
    settings.GDB_AUTO_DISCOVER = True
    settings.CACHE_SIZE_LIMIT = 10
    settings.GDB_PREFERRED_DRIVERS = ["OpenFileGDB", "FileGDB"]
    return settings


@pytest.fixture
def mock_settings_auth_disabled(mock_settings):
    """Mock settings with authentication disabled."""
    mock_settings.REQUIRE_AUTH = False
    mock_settings.SUPABASE_JWT_SECRET = None
    return mock_settings


@pytest.fixture
def mock_settings_production(mock_settings):
    """Mock settings for production-like configuration."""
    mock_settings.DEM_SOURCES = {
        "local_dtm": {
            "path": "./data/DTM.gdb",
            "description": "Local DTM Geodatabase"
        },
        "au_qld_lidar": {
            "path": "s3://road-engineering-elevation-data/AU_QLD_LiDAR_1m.tif",
            "description": "Queensland 1m LiDAR"
        },
        "au_national": {
            "path": "s3://road-engineering-elevation-data/AU_National_5m_DEM.tif",
            "description": "Australia National 5m"
        },
        "gpxz_api": {
            "path": "api://gpxz",
            "description": "GPXZ.io global elevation API"
        }
    }
    mock_settings.DEFAULT_DEM_ID = "au_national"
    mock_settings.CORS_ORIGINS = "https://road.engineering,https://api.road.engineering"
    mock_settings.CACHE_SIZE_LIMIT = 50
    return mock_settings


@pytest.fixture
def valid_jwt_payload():
    """Standard valid JWT payload for testing."""
    return {
        "sub": "test-user-123",
        "email": "test@road.engineering",
        "role": "authenticated",
        "aud": "authenticated",
        "iss": "supabase",
        "exp": datetime.utcnow() + timedelta(hours=1)
    }


@pytest.fixture
def expired_jwt_payload():
    """Expired JWT payload for testing."""
    return {
        "sub": "test-user-123",
        "email": "test@road.engineering",
        "role": "authenticated",
        "aud": "authenticated",
        "iss": "supabase",
        "exp": datetime.utcnow() - timedelta(hours=1)  # Expired
    }


@pytest.fixture
def invalid_jwt_payload():
    """Invalid JWT payload (missing required fields) for testing."""
    return {
        "email": "test@road.engineering",
        "aud": "authenticated",
        "exp": datetime.utcnow() + timedelta(hours=1)
        # Missing 'sub' field
    }


def create_jwt_token(payload: dict, secret: str = TestSecrets.JWT_SECRET, algorithm: str = "HS256") -> str:
    """Helper function to create JWT tokens for testing."""
    return jwt.encode(payload, secret, algorithm=algorithm)


@pytest.fixture
def valid_jwt_token(valid_jwt_payload):
    """Valid JWT token for testing."""
    return create_jwt_token(valid_jwt_payload)


@pytest.fixture
def expired_jwt_token(expired_jwt_payload):
    """Expired JWT token for testing."""
    return create_jwt_token(expired_jwt_payload)


@pytest.fixture
def invalid_signature_token(valid_jwt_payload):
    """JWT token with invalid signature for testing."""
    return create_jwt_token(valid_jwt_payload, secret=TestSecrets.INVALID_JWT_SECRET)


@pytest.fixture
def invalid_payload_token(invalid_jwt_payload):
    """JWT token with invalid payload for testing."""
    return create_jwt_token(invalid_jwt_payload)


@pytest.fixture
def auth_credentials(valid_jwt_token):
    """HTTP authorization credentials for testing."""
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=valid_jwt_token)


@pytest.fixture
def expired_auth_credentials(expired_jwt_token):
    """Expired HTTP authorization credentials for testing."""
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=expired_jwt_token)


@pytest.fixture
def invalid_auth_credentials(invalid_signature_token):
    """Invalid HTTP authorization credentials for testing."""
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=invalid_signature_token)


@pytest.fixture
def test_client():
    """FastAPI test client for integration testing."""
    return TestClient(app)


@pytest.fixture
def mock_dem_service():
    """Mock DEM service for testing."""
    service = MagicMock()
    service.get_elevation_at_point.return_value = (45.2, "test_source", "Success")
    service.get_elevation_along_line.return_value = ([45.0, 45.5, 46.0], "test_source", "Success")
    service.get_elevation_along_path.return_value = ([45.0, 45.5, 46.0], "test_source", "Success")
    service.close.return_value = None
    return service


@pytest.fixture
def test_coordinates():
    """Standard test coordinates for Brisbane area."""
    return {
        "latitude": -27.4698,
        "longitude": 153.0251,
        "elevation_expected": 45.2
    }


@pytest.fixture
def test_elevation_request():
    """Standard elevation request for testing."""
    return {
        "latitude": -27.4698,
        "longitude": 153.0251
    }


@pytest.fixture
def test_path_request():
    """Standard path elevation request for testing."""
    return {
        "points": [
            {"latitude": -27.4698, "longitude": 153.0251},
            {"latitude": -27.4699, "longitude": 153.0252},
            {"latitude": -27.4700, "longitude": 153.0253}
        ]
    }


@pytest.fixture
def cors_test_origins():
    """CORS origins for testing."""
    return {
        "allowed": [
            "https://road.engineering",
            "http://localhost:3001",
            "http://localhost:5173"
        ],
        "blocked": [
            "https://malicious-site.com",
            "http://evil.example.org"
        ]
    }


@pytest.fixture
def mock_get_settings(mock_settings):
    """Mock get_settings function for dependency injection testing."""
    with patch('src.config.get_settings', return_value=mock_settings) as mock:
        yield mock


@pytest.fixture
def mock_get_settings_auth_disabled(mock_settings_auth_disabled):
    """Mock get_settings with auth disabled for testing."""
    with patch('src.config.get_settings', return_value=mock_settings_auth_disabled) as mock:
        yield mock


@pytest.fixture
def mock_get_settings_production(mock_settings_production):
    """Mock get_settings with production config for testing."""
    with patch('src.config.get_settings', return_value=mock_settings_production) as mock:
        yield mock


@pytest.fixture(autouse=True)
def suppress_logging():
    """Suppress logging during tests to reduce noise."""
    import logging
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


# Helper functions for tests
def assert_http_exception(exception, expected_status_code: int, expected_detail_substring: str = None):
    """Helper to assert HTTPException properties."""
    assert exception.status_code == expected_status_code
    if expected_detail_substring:
        assert expected_detail_substring.lower() in exception.detail.lower()


def assert_cors_headers(response, expected_origin: str = None, should_have_cors: bool = True):
    """Helper to assert CORS headers in response."""
    if should_have_cors:
        assert "Access-Control-Allow-Origin" in response.headers
        if expected_origin:
            assert response.headers["Access-Control-Allow-Origin"] == expected_origin
        assert "Access-Control-Allow-Methods" in response.headers
    else:
        # Should not have CORS headers for blocked origins
        pass  # Implementation depends on CORS middleware behavior


def assert_health_response(response_data: dict):
    """Helper to assert health endpoint response structure."""
    required_fields = ["status", "dem_sources_configured"]
    for field in required_fields:
        assert field in response_data
    
    if response_data["status"] == "healthy":
        assert isinstance(response_data["dem_sources_configured"], int)
        assert response_data["dem_sources_configured"] >= 0