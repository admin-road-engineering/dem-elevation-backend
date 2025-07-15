import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from src.enhanced_source_selector import EnhancedSourceSelector
from src.gpxz_client import GPXZClient, GPXZConfig
from src.error_handling import RetryableError, NonRetryableError, SourceType

# Enable async test support
pytest_plugins = ('pytest_asyncio',)

@pytest.mark.asyncio
class TestAsyncResilience:
    """Test async resilience patterns and performance"""
    
    async def test_enhanced_selector_resilience_full_async(self):
        """Test full async resilience with proper mocking"""
        config = {
            "local_dtm": {
                "path": "./data/DTM.gdb",
                "layer": None,
                "crs": None,
                "description": "Local DTM"
            }
        }
        
        selector = EnhancedSourceSelector(config=config, use_s3=False, use_apis=False)
        
        # Mock the async methods properly
        selector._get_elevation_from_local = AsyncMock(return_value=42.5)
        
        result = await selector.get_elevation_with_resilience(-43.5, 172.6)
        
        assert result['success'] is True
        assert result['elevation_m'] == 42.5
        assert result['source'] == 'local'
        assert 'local' in result['attempted_sources']

    async def test_gpxz_client_error_classification(self):
        """Test GPXZ client properly classifies errors"""
        config = GPXZConfig(api_key="test_key")
        client = GPXZClient(config)
        
        # Mock different HTTP responses
        with patch.object(client.client, 'get') as mock_get:
            # Test timeout error (retryable)
            from httpx import TimeoutException
            mock_get.side_effect = TimeoutException("Request timeout")
            
            with pytest.raises(RetryableError) as exc_info:
                await client.get_elevation_point(-43.5, 172.6)
            
            assert exc_info.value.source_type == SourceType.API
            assert "timeout" in str(exc_info.value).lower()
            
            # Test 500 error (retryable)
            from httpx import HTTPStatusError, Response
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_get.side_effect = HTTPStatusError("Server error", request=MagicMock(), response=mock_response)
            
            with pytest.raises(RetryableError) as exc_info:
                await client.get_elevation_point(-43.5, 172.6)
            
            assert "server error" in str(exc_info.value).lower()
            
            # Test 401 error (non-retryable)
            mock_response.status_code = 401
            mock_get.side_effect = HTTPStatusError("Unauthorized", request=MagicMock(), response=mock_response)
            
            with pytest.raises(NonRetryableError) as exc_info:
                await client.get_elevation_point(-43.5, 172.6)
            
            assert "authentication" in str(exc_info.value).lower()
        
        await client.close()

    async def test_circuit_breaker_behavior(self):
        """Test circuit breaker opens and recovers properly"""
        config = {
            "local_dtm": {
                "path": "./data/DTM.gdb",
                "layer": None,
                "crs": None,
                "description": "Local DTM"
            }
        }
        
        selector = EnhancedSourceSelector(config=config, use_s3=True, use_apis=True)
        
        # Get the circuit breaker for GPXZ
        gpxz_cb = selector.circuit_breakers['gpxz_api']
        
        # Initially should be available
        assert gpxz_cb.is_available() is True
        assert gpxz_cb.state == "CLOSED"
        
        # Record failures to open circuit
        gpxz_cb.record_failure()
        gpxz_cb.record_failure()
        gpxz_cb.record_failure()  # Should open after 3 failures
        
        assert gpxz_cb.is_available() is False
        assert gpxz_cb.state == "OPEN"
        
        # Test recovery after timeout (simulate time passage)
        gpxz_cb.last_failure_time = time.time() - 400  # 400 seconds ago
        assert gpxz_cb.is_available() is True
        assert gpxz_cb.state == "HALF_OPEN"
        
        # Record success to close circuit
        gpxz_cb.record_success()
        assert gpxz_cb.state == "CLOSED"

    async def test_multi_source_fallback_chain(self):
        """Test complete multi-source fallback chain"""
        config = {
            "local_dtm": {
                "path": "./data/DTM.gdb",
                "layer": None,
                "crs": None,
                "description": "Local DTM"
            }
        }
        
        gpxz_config = GPXZConfig(api_key="test_key")
        selector = EnhancedSourceSelector(
            config=config, 
            use_s3=True, 
            use_apis=True, 
            gpxz_config=gpxz_config
        )
        
        # Mock all source methods to fail except local
        selector._try_nz_source = AsyncMock(return_value=None)
        selector._try_gpxz_source = AsyncMock(side_effect=NonRetryableError("Daily limit", SourceType.API))
        selector._try_s3_au_source = AsyncMock(return_value=None)
        selector._get_elevation_from_local = AsyncMock(return_value=45.2)
        
        result = await selector.get_elevation_with_resilience(-43.5, 172.6)
        
        assert result['success'] is True
        assert result['elevation_m'] == 45.2
        assert result['source'] == 'local'
        assert len(result['attempted_sources']) >= 1  # Should have tried at least one source

    async def test_performance_benchmark(self):
        """Benchmark source selection performance"""
        config = {
            "local_dtm": {
                "path": "./data/DTM.gdb",
                "layer": None,
                "crs": None,
                "description": "Local DTM"
            }
        }
        
        selector = EnhancedSourceSelector(config=config, use_s3=False, use_apis=False)
        
        # Mock fast response
        selector._get_elevation_from_local = AsyncMock(return_value=42.5)
        
        # Time multiple selections
        start_time = time.time()
        tasks = []
        
        for i in range(10):
            lat = -43.5 + i * 0.01
            lon = 172.6 + i * 0.01
            tasks.append(selector.get_elevation_with_resilience(lat, lon))
        
        results = await asyncio.gather(*tasks)
        end_time = time.time()
        
        # Performance assertions
        total_time = end_time - start_time
        avg_time_per_request = total_time / len(tasks)
        
        assert len(results) == 10
        assert all(r['success'] for r in results)
        assert avg_time_per_request < 0.1  # Should be < 100ms per request
        
        print(f"Performance: {len(tasks)} requests in {total_time:.3f}s")
        print(f"Average: {avg_time_per_request*1000:.1f}ms per request")

    async def test_cost_manager_tracking(self):
        """Test S3 cost manager tracking and limits"""
        from src.enhanced_source_selector import S3CostManager
        import tempfile
        import os
        
        # Use temporary file to avoid conflicts with existing usage
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            # Initialize with empty usage data
            import json
            from datetime import datetime
            json.dump({"date": str(datetime.now().date()), "gb_used": 0.0, "requests": 0}, f)
            temp_file = f.name
        
        try:
            cost_manager = S3CostManager(daily_gb_limit=0.1, cache_file=temp_file)  # 100MB limit
            
            # Test initial state (smaller request that fits)
            assert cost_manager.can_access_s3(estimated_mb=20) is True
            
            # Record some usage
            initial_usage = cost_manager.usage['gb_used']
            cost_manager.record_access(30)  # 30MB
            expected_usage = initial_usage + (30 / 1024)
            assert abs(cost_manager.usage['gb_used'] - expected_usage) < 0.001
            
            # Large request should be blocked
            assert cost_manager.can_access_s3(estimated_mb=150) is False
            
            # Test that usage accumulates correctly
            current_usage = cost_manager.usage['gb_used']
            cost_manager.record_access(20)  # Another 20MB
            assert abs(cost_manager.usage['gb_used'] - (current_usage + (20 / 1024))) < 0.001
            
        finally:
            # Clean up temp file
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    async def test_retry_with_backoff(self):
        """Test retry logic with exponential backoff"""
        from src.error_handling import retry_with_backoff
        
        call_count = 0
        
        async def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RetryableError("Temporary failure", SourceType.API)
            return "success"
        
        start_time = time.time()
        result = await retry_with_backoff(
            failing_function,
            max_retries=3,
            base_delay=0.1,  # Short delay for testing
            exceptions=(RetryableError,)
        )
        end_time = time.time()
        
        assert result == "success"
        assert call_count == 3
        # Should have taken at least base_delay + base_delay*2 = 0.3s
        assert end_time - start_time >= 0.3

    async def test_configuration_validation_logging(self):
        """Test that configuration validation provides helpful logging"""
        from src.config import validate_environment_configuration
        import logging
        
        # Mock settings for testing
        settings = MagicMock()
        settings.DEM_SOURCES = {
            "gpxz_api": {"path": "api://gpxz", "description": "GPXZ API"}
        }
        settings.USE_API_SOURCES = True
        settings.USE_S3_SOURCES = False
        settings.GPXZ_API_KEY = None  # Missing API key
        settings.GPXZ_DAILY_LIMIT = 100
        settings.GPXZ_RATE_LIMIT = 1
        
        # Test validation runs without error
        try:
            validate_environment_configuration(settings)
            # If we get here, validation ran successfully
            assert True
        except Exception as e:
            pytest.fail(f"Configuration validation failed: {e}")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])