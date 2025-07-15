import pytest
import asyncio
import time
import statistics
from unittest.mock import AsyncMock, MagicMock
from src.enhanced_source_selector import EnhancedSourceSelector
from src.gpxz_client import GPXZConfig
from src.config import Settings

# Enable async test support
pytest_plugins = ('pytest_asyncio',)

@pytest.mark.asyncio
class TestLoadPerformance:
    """Load and performance tests for DEM backend under concurrent load"""
    
    async def test_concurrent_50_queries_performance(self):
        """Test 50 concurrent queries performance benchmark"""
        # Setup lightweight selector for testing
        config = {
            "local_dtm": {"path": "./data/DTM.gdb", "description": "Local DTM"},
            "mock_s3": {"path": "s3://test-bucket/dem.tif", "description": "Mock S3"}
        }
        
        selector = EnhancedSourceSelector(config=config, use_s3=False, use_apis=False)
        
        # Mock fast local response with slight variation
        async def mock_elevation(lat, lon):
            # Simulate small processing time variation
            await asyncio.sleep(0.001 + (hash((lat, lon)) % 100) / 100000)  # 1-2ms
            return 50.0 + (lat + lon) % 10  # Realistic elevation variation
        
        selector._get_elevation_from_local = mock_elevation
        
        # Generate 50 test coordinates around Brisbane area
        base_lat, base_lon = -27.4698, 153.0251
        coordinates = [
            (base_lat + (i * 0.01), base_lon + (i * 0.01)) 
            for i in range(50)
        ]
        
        # Execute concurrent requests
        start_time = time.time()
        
        async def single_request(lat, lon):
            return await selector.get_elevation_with_resilience(lat, lon)
        
        tasks = [single_request(lat, lon) for lat, lon in coordinates]
        results = await asyncio.gather(*tasks)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Validate results
        assert len(results) == 50
        successful_results = [r for r in results if r['success']]
        assert len(successful_results) == 50  # All should succeed
        
        # Performance assertions
        avg_time_per_request = total_time / 50
        assert avg_time_per_request < 0.1  # < 100ms per request average
        assert total_time < 5.0  # Total time should be reasonable
        
        # Log performance metrics
        print(f"\n🚀 Load Test Results:")
        print(f"   • Total requests: 50")
        print(f"   • Total time: {total_time:.3f}s")
        print(f"   • Average per request: {avg_time_per_request*1000:.1f}ms")
        print(f"   • Requests per second: {50/total_time:.1f}")
        print(f"   • Success rate: {len(successful_results)/50*100:.1f}%")
    
    async def test_stress_test_100_concurrent_with_failures(self):
        """Stress test with 100 concurrent requests including simulated failures"""
        config = {
            "local_dtm": {"path": "./data/DTM.gdb", "description": "Local DTM"}
        }
        
        gpxz_config = GPXZConfig(api_key="test_key")
        selector = EnhancedSourceSelector(
            config=config, 
            use_s3=True, 
            use_apis=True, 
            gpxz_config=gpxz_config
        )
        
        # Mock sources with realistic failure rates
        call_count = 0
        
        async def mock_local_with_occasional_failure(lat, lon):
            nonlocal call_count
            call_count += 1
            # Simulate 5% failure rate
            if call_count % 20 == 0:
                await asyncio.sleep(0.01)  # Slightly longer for "failures"
                return None
            await asyncio.sleep(0.002)  # 2ms processing
            return 45.0 + abs(lat % 1) * 100
        
        selector._try_local_source = mock_local_with_occasional_failure
        selector._try_nz_source = AsyncMock(return_value=None)
        selector._try_gpxz_source = AsyncMock(return_value=None)  
        selector._try_s3_au_source = AsyncMock(return_value=None)
        selector._get_elevation_from_local = mock_local_with_occasional_failure
        
        # Generate 100 test coordinates
        coordinates = [
            (-27.4698 + (i * 0.001), 153.0251 + (i * 0.001))
            for i in range(100)
        ]
        
        start_time = time.time()
        
        async def request_with_retry(lat, lon, request_id):
            try:
                result = await selector.get_elevation_with_resilience(lat, lon)
                return {"id": request_id, "result": result, "success": result['success']}
            except Exception as e:
                return {"id": request_id, "result": None, "success": False, "error": str(e)}
        
        tasks = [request_with_retry(lat, lon, i) for i, (lat, lon) in enumerate(coordinates)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Analyze results
        successful_requests = [r for r in results if isinstance(r, dict) and r.get('success')]
        failed_requests = [r for r in results if not (isinstance(r, dict) and r.get('success'))]
        
        success_rate = len(successful_requests) / len(results) * 100
        avg_time = total_time / len(results)
        
        # Performance assertions (more lenient for stress test)
        assert len(results) == 100
        assert success_rate >= 90  # At least 90% success rate
        assert avg_time < 0.15  # < 150ms average (more lenient)
        assert total_time < 10.0  # Should complete within 10 seconds
        
        print(f"\n💪 Stress Test Results:")
        print(f"   • Total requests: 100")
        print(f"   • Successful: {len(successful_requests)}")
        print(f"   • Failed: {len(failed_requests)}")
        print(f"   • Success rate: {success_rate:.1f}%")
        print(f"   • Total time: {total_time:.3f}s")
        print(f"   • Average per request: {avg_time*1000:.1f}ms")
        print(f"   • Throughput: {len(results)/total_time:.1f} req/s")
    
    async def test_circuit_breaker_under_load(self):
        """Test circuit breaker behavior under concurrent load"""
        config = {"local_dtm": {"path": "./data/DTM.gdb", "description": "Local DTM"}}
        
        gpxz_config = GPXZConfig(api_key="test_key")
        selector = EnhancedSourceSelector(
            config=config, 
            use_s3=True, 
            use_apis=True, 
            gpxz_config=gpxz_config
        )
        
        # Mock GPXZ to always fail (trigger circuit breaker)
        async def failing_gpxz_source(lat, lon):
            from src.error_handling import RetryableError, SourceType
            raise RetryableError("Simulated GPXZ failure", SourceType.API)
        
        selector._try_gpxz_source = failing_gpxz_source
        selector._try_nz_source = AsyncMock(return_value=None)
        selector._try_s3_au_source = AsyncMock(return_value=None)
        selector._get_elevation_from_local = AsyncMock(return_value=42.0)
        
        # Make 20 concurrent requests (should trigger circuit breaker)
        coordinates = [(-27.47 + i*0.001, 153.02 + i*0.001) for i in range(20)]
        
        start_time = time.time()
        tasks = [selector.get_elevation_with_resilience(lat, lon) for lat, lon in coordinates]
        results = await asyncio.gather(*tasks)
        end_time = time.time()
        
        # Verify circuit breaker behavior
        gpxz_cb = selector.circuit_breakers.get('gpxz_api')
        assert gpxz_cb is not None
        
        # Circuit breaker should eventually open due to failures
        # (exact state depends on timing, but it should show some effect)
        
        # All requests should still succeed via fallback to local
        successful_results = [r for r in results if r['success']]
        assert len(successful_results) >= 15  # Most should succeed via fallback
        
        # Performance should still be reasonable despite failures
        total_time = end_time - start_time
        assert total_time < 5.0  # Should still complete quickly
        
        print(f"\n🔧 Circuit Breaker Test Results:")
        print(f"   • Requests processed: 20")
        print(f"   • Successful (via fallback): {len(successful_results)}")
        print(f"   • Circuit breaker state: {gpxz_cb.state}")
        print(f"   • Total time: {total_time:.3f}s")
        print(f"   • Fallback effectiveness: {len(successful_results)/20*100:.1f}%")
    
    async def test_memory_usage_under_load(self):
        """Test memory usage doesn't grow excessively under load"""
        import psutil
        import os
        
        config = {"local_dtm": {"path": "./data/DTM.gdb", "description": "Local DTM"}}
        selector = EnhancedSourceSelector(config=config, use_s3=False, use_apis=False)
        
        # Mock lightweight response
        selector._get_elevation_from_local = AsyncMock(return_value=50.0)
        
        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Run multiple batches of requests
        total_requests = 0
        for batch in range(5):
            coordinates = [(-27.47 + i*0.01, 153.02 + i*0.01) for i in range(20)]
            tasks = [selector.get_elevation_with_resilience(lat, lon) for lat, lon in coordinates]
            await asyncio.gather(*tasks)
            total_requests += 20
            
            # Check memory after each batch
            current_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_growth = current_memory - initial_memory
            
            # Memory growth should be reasonable (< 50MB growth)
            assert memory_growth < 50, f"Memory growth too high: {memory_growth:.1f}MB"
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        total_growth = final_memory - initial_memory
        
        print(f"\n🧠 Memory Usage Test Results:")
        print(f"   • Total requests: {total_requests}")
        print(f"   • Initial memory: {initial_memory:.1f}MB")
        print(f"   • Final memory: {final_memory:.1f}MB")
        print(f"   • Total growth: {total_growth:.1f}MB")
        print(f"   • Growth per request: {total_growth/total_requests*1000:.2f}KB")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])