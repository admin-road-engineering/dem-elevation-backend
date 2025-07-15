import pytest
import asyncio
import time
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer
import jwt
from datetime import datetime, timedelta

# Enable async test support
pytest_plugins = ('pytest_asyncio',)

@pytest.mark.asyncio 
class TestMainPlatformIntegration:
    """Test integration with main Road Engineering SaaS platform"""
    
    def create_test_jwt(self, user_id: str = "test_user", tier: str = "professional"):
        """Create test JWT token mimicking main platform"""
        payload = {
            "sub": user_id,
            "aud": "authenticated", 
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow(),
            "app_metadata": {
                "subscription_tier": tier
            }
        }
        return jwt.encode(payload, "test_secret", algorithm="HS256")
    
    async def test_elevation_endpoint_with_jwt_auth(self):
        """Test elevation endpoint with JWT authentication simulation"""
        from src.main import app
        from src.dem_service import DEMService
        from src.config import Settings
        
        # Mock the DEM service to avoid file dependencies
        with patch('src.main.get_dem_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_elevation_for_point = AsyncMock(return_value=42.5)
            mock_get_service.return_value = mock_service
            
            # Mock JWT verification
            with patch('src.api.v1.endpoints.get_current_user') as mock_auth:
                mock_auth.return_value = {
                    "sub": "test_user_123",
                    "app_metadata": {"subscription_tier": "professional"}
                }
                
                client = TestClient(app)
                
                # Simulate main platform call with JWT
                token = self.create_test_jwt("test_user_123", "professional")
                headers = {"Authorization": f"Bearer {token}"}
                
                response = client.post(
                    "/api/v1/elevation/point",
                    json={"latitude": -27.4698, "longitude": 153.0251},
                    headers=headers
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["elevation_m"] == 42.5
                assert "coordinates" in data
                assert "metadata" in data
                
                # Verify DEM service was called
                mock_service.get_elevation_for_point.assert_called_once_with(-27.4698, 153.0251)

    async def test_rate_limiting_by_subscription_tier(self):
        """Test rate limiting based on subscription tiers"""
        from src.main import app
        
        with patch('src.main.get_dem_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_elevation_for_point = AsyncMock(return_value=45.0)
            mock_get_service.return_value = mock_service
            
            # Test free tier limits
            with patch('src.api.v1.endpoints.get_current_user') as mock_auth:
                mock_auth.return_value = {
                    "sub": "free_user",
                    "app_metadata": {"subscription_tier": "free"}
                }
                
                with patch('src.api.v1.endpoints.rate_limiter') as mock_limiter:
                    mock_limiter.check_limit = AsyncMock(return_value=False)  # Rate limit exceeded
                    
                    client = TestClient(app)
                    token = self.create_test_jwt("free_user", "free")
                    headers = {"Authorization": f"Bearer {token}"}
                    
                    response = client.post(
                        "/api/v1/elevation/point",
                        json={"latitude": -27.4698, "longitude": 153.0251},
                        headers=headers
                    )
                    
                    assert response.status_code == 429
                    assert "rate limit" in response.json()["detail"].lower()

    async def test_batch_endpoint_professional_tier(self):
        """Test batch endpoint requires professional tier"""
        from src.main import app
        
        with patch('src.main.get_dem_service') as mock_get_service:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service
            
            # Test free user accessing professional endpoint
            with patch('src.api.v1.endpoints.require_subscription_tier') as mock_tier_check:
                mock_tier_check.side_effect = HTTPException(
                    status_code=403, 
                    detail="Requires professional subscription or higher"
                )
                
                client = TestClient(app)
                token = self.create_test_jwt("free_user", "free")
                headers = {"Authorization": f"Bearer {token}"}
                
                response = client.post(
                    "/api/v1/elevation/batch",
                    json={"points": [
                        {"id": "p1", "latitude": -27.4698, "longitude": 153.0251},
                        {"id": "p2", "latitude": -27.4700, "longitude": 153.0253}
                    ]},
                    headers=headers
                )
                
                assert response.status_code == 403
                assert "professional subscription" in response.json()["detail"]

    async def test_service_health_check_integration(self):
        """Test health check aligns with main platform monitoring"""
        from src.main import app
        
        with patch('src.main.check_dem_service_health') as mock_health, \
             patch('src.main.check_external_dependencies') as mock_deps:
            
            mock_health.return_value = {
                "healthy": True,
                "sources_available": 3,
                "default_source": "local_dtm"
            }
            
            mock_deps.return_value = {
                "healthy": True,
                "services": {
                    "gpxz": {"status": "healthy", "response_time_ms": 150},
                    "s3": {"status": "healthy"}
                }
            }
            
            client = TestClient(app)
            response = client.get("/health")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "integration" in data
            assert data["integration"]["main_platform"] == "connected"
            assert "timestamp" in data

    async def test_error_response_format_alignment(self):
        """Test error responses align with main platform format"""
        from src.main import app
        
        with patch('src.main.get_dem_service') as mock_get_service:
            mock_service = MagicMock()
            # Simulate service error
            mock_service.get_elevation_for_point = AsyncMock(side_effect=Exception("DEM service unavailable"))
            mock_get_service.return_value = mock_service
            
            with patch('src.api.v1.endpoints.get_current_user') as mock_auth:
                mock_auth.return_value = {
                    "sub": "test_user",
                    "app_metadata": {"subscription_tier": "professional"}
                }
                
                client = TestClient(app)
                token = self.create_test_jwt()
                headers = {"Authorization": f"Bearer {token}"}
                
                response = client.post(
                    "/api/v1/elevation/point",
                    json={"latitude": -27.4698, "longitude": 153.0251},
                    headers=headers
                )
                
                # Should return 200 with error details (not 500)
                assert response.status_code == 200
                data = response.json()
                assert data["elevation_m"] is None
                assert data["success"] is False
                assert "error" in data
                assert "metadata" in data

    async def test_multi_source_resilience_integration(self):
        """Test multi-source resilience in main platform context"""
        from src.enhanced_source_selector import EnhancedSourceSelector
        from src.config import Settings
        
        # Mock settings for integration test
        settings = MagicMock()
        settings.DEM_SOURCES = {
            "local_dtm": {"path": "./data/DTM.gdb", "description": "Local DTM"},
            "gpxz_api": {"path": "api://gpxz", "description": "GPXZ API"}
        }
        settings.USE_S3_SOURCES = True
        settings.USE_API_SOURCES = True
        settings.GPXZ_API_KEY = "test_key"
        
        # Test resilience chain
        from src.gpxz_client import GPXZConfig
        gpxz_config = GPXZConfig(api_key="test_key")
        
        selector = EnhancedSourceSelector(
            config=settings.DEM_SOURCES,
            use_s3=True,
            use_apis=True,
            gpxz_config=gpxz_config
        )
        
        # Mock all sources to fail except local
        selector._try_nz_source = AsyncMock(return_value=None)
        selector._try_gpxz_source = AsyncMock(return_value=None)
        selector._try_s3_au_source = AsyncMock(return_value=None)
        selector._get_elevation_from_local = AsyncMock(return_value=38.7)
        
        # Simulate main platform request coordinates (Brisbane area)
        result = await selector.get_elevation_with_resilience(-27.4698, 153.0251)
        
        assert result['success'] is True
        assert result['elevation_m'] == 38.7
        assert result['source'] == 'local'
        assert len(result['attempted_sources']) >= 1
        
        # Cleanup
        await selector.close()

    async def test_concurrent_request_simulation(self):
        """Test concurrent requests simulating main platform load"""
        from src.enhanced_source_selector import EnhancedSourceSelector
        from src.config import Settings
        
        # Mock a lightweight selector for performance testing
        config = {"local_dtm": {"path": "./data/DTM.gdb", "description": "Local DTM"}}
        selector = EnhancedSourceSelector(config=config, use_s3=False, use_apis=False)
        
        # Mock fast local response
        selector._get_elevation_from_local = AsyncMock(return_value=42.0)
        
        # Simulate 10 concurrent requests from main platform
        async def simulate_request(request_id: int):
            lat = -27.4698 + (request_id * 0.001)  # Slightly different coordinates
            lon = 153.0251 + (request_id * 0.001)
            return await selector.get_elevation_with_resilience(lat, lon)
        
        start_time = time.time()
        tasks = [simulate_request(i) for i in range(10)]
        results = await asyncio.gather(*tasks)
        end_time = time.time()
        
        # Verify all requests succeeded
        assert len(results) == 10
        assert all(r['success'] for r in results)
        assert all(r['elevation_m'] == 42.0 for r in results)
        
        # Performance check - should complete in reasonable time
        total_time = end_time - start_time
        avg_time_per_request = total_time / 10
        assert avg_time_per_request < 0.1  # < 100ms average per request
        
        print(f"Concurrent test: 10 requests in {total_time:.3f}s")
        print(f"Average: {avg_time_per_request*1000:.1f}ms per request")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])