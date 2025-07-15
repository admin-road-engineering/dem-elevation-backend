#!/usr/bin/env python3
"""
Post-deployment smoke test for DEM Backend.
Automatically verifies live configuration immediately after Railway deployment.
Can be run manually or via Railway deployment hooks.
"""
import asyncio
import json
import time
import sys
from typing import Dict, Any, List
import httpx
from datetime import datetime


class SmokeTestConfig:
    """Configuration for smoke tests."""
    def __init__(self, base_url: str = None):
        self.base_url = base_url or "https://dem-api.road.engineering"
        self.timeout = 30.0
        self.retry_attempts = 3
        self.retry_delay = 2.0
        
        # Test coordinates (Brisbane area)
        self.test_lat = -27.4698
        self.test_lng = 153.0251
        
        # Expected response thresholds
        self.max_response_time_ms = 500
        self.min_sources = 2


class SmokeTestResult:
    """Container for smoke test results."""
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures: List[str] = []
        self.warnings: List[str] = []
        self.start_time = datetime.now()
        self.response_times: Dict[str, float] = {}
    
    def add_failure(self, test_name: str, error: str):
        """Add a test failure."""
        self.tests_failed += 1
        self.failures.append(f"{test_name}: {error}")
    
    def add_warning(self, warning: str):
        """Add a test warning."""
        self.warnings.append(warning)
    
    def add_success(self, test_name: str, response_time_ms: float = None):
        """Add a successful test."""
        self.tests_passed += 1
        if response_time_ms:
            self.response_times[test_name] = response_time_ms
    
    def is_success(self) -> bool:
        """Check if all tests passed."""
        return self.tests_failed == 0
    
    def summary(self) -> str:
        """Generate test summary."""
        duration = (datetime.now() - self.start_time).total_seconds()
        status = "✅ PASSED" if self.is_success() else "❌ FAILED"
        
        summary = [
            f"🧪 DEM Backend Smoke Test Results {status}",
            f"⏱️  Duration: {duration:.2f}s",
            f"📊 Tests: {self.tests_run} total, {self.tests_passed} passed, {self.tests_failed} failed",
        ]
        
        if self.response_times:
            avg_time = sum(self.response_times.values()) / len(self.response_times)
            summary.append(f"🚀 Avg Response Time: {avg_time:.0f}ms")
        
        if self.failures:
            summary.append("\n❌ Failures:")
            summary.extend([f"  - {failure}" for failure in self.failures])
        
        if self.warnings:
            summary.append("\n⚠️  Warnings:")
            summary.extend([f"  - {warning}" for warning in self.warnings])
        
        return "\n".join(summary)


class DemBackendSmokeTest:
    """Smoke test suite for DEM Backend deployment."""
    
    def __init__(self, config: SmokeTestConfig):
        self.config = config
        self.result = SmokeTestResult()
        self.client = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.client = httpx.AsyncClient(timeout=self.config.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.aclose()
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        """Make HTTP request with retry logic."""
        url = f"{self.config.base_url}{endpoint}"
        
        for attempt in range(self.config.retry_attempts):
            try:
                response = await self.client.request(method, url, **kwargs)
                return response
            except (httpx.RequestError, httpx.TimeoutException) as e:
                if attempt == self.config.retry_attempts - 1:
                    raise
                await asyncio.sleep(self.config.retry_delay * (attempt + 1))
        
        raise Exception("Max retry attempts exceeded")
    
    async def test_health_endpoint(self):
        """Test health endpoint availability and response."""
        test_name = "health_endpoint"
        self.result.tests_run += 1
        
        try:
            start_time = time.time()
            response = await self._make_request("GET", "/health")
            response_time_ms = (time.time() - start_time) * 1000
            
            if response.status_code != 200:
                self.result.add_failure(test_name, f"Health check returned {response.status_code}")
                return
            
            data = response.json()
            if data.get("status") != "healthy":
                self.result.add_failure(test_name, f"Health status: {data.get('status')}")
                return
            
            # Check response time
            if response_time_ms > self.config.max_response_time_ms:
                self.result.add_warning(f"Health endpoint slow: {response_time_ms:.0f}ms > {self.config.max_response_time_ms}ms")
            
            self.result.add_success(test_name, response_time_ms)
            
        except Exception as e:
            self.result.add_failure(test_name, str(e))
    
    async def test_root_endpoint(self):
        """Test root endpoint availability."""
        test_name = "root_endpoint"
        self.result.tests_run += 1
        
        try:
            start_time = time.time()
            response = await self._make_request("GET", "/")
            response_time_ms = (time.time() - start_time) * 1000
            
            if response.status_code != 200:
                self.result.add_failure(test_name, f"Root endpoint returned {response.status_code}")
                return
            
            data = response.json()
            if data.get("service") != "DEM Elevation Service":
                self.result.add_failure(test_name, f"Unexpected service name: {data.get('service')}")
                return
            
            self.result.add_success(test_name, response_time_ms)
            
        except Exception as e:
            self.result.add_failure(test_name, str(e))
    
    async def test_sources_endpoint(self):
        """Test elevation sources endpoint."""
        test_name = "sources_endpoint"
        self.result.tests_run += 1
        
        try:
            start_time = time.time()
            response = await self._make_request("GET", "/api/v1/elevation/sources")
            response_time_ms = (time.time() - start_time) * 1000
            
            if response.status_code != 200:
                self.result.add_failure(test_name, f"Sources endpoint returned {response.status_code}")
                return
            
            data = response.json()
            sources_count = data.get("total_sources", 0)
            
            if sources_count < self.config.min_sources:
                self.result.add_failure(test_name, f"Too few sources: {sources_count} < {self.config.min_sources}")
                return
            
            self.result.add_success(test_name, response_time_ms)
            
        except Exception as e:
            self.result.add_failure(test_name, str(e))
    
    async def test_elevation_endpoint(self):
        """Test single point elevation endpoint."""
        test_name = "elevation_endpoint"
        self.result.tests_run += 1
        
        try:
            start_time = time.time()
            response = await self._make_request(
                "POST", 
                "/api/v1/elevation/point",
                json={"latitude": self.config.test_lat, "longitude": self.config.test_lng}
            )
            response_time_ms = (time.time() - start_time) * 1000
            
            if response.status_code not in [200, 404]:  # 404 acceptable if no auth
                self.result.add_failure(test_name, f"Elevation endpoint returned {response.status_code}")
                return
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if we got elevation data or proper null handling
                if "elevation_m" not in data:
                    self.result.add_failure(test_name, "Missing elevation_m field in response")
                    return
                
                # Check for source information
                if "source" not in data:
                    self.result.add_warning("Missing source field in elevation response")
            
            self.result.add_success(test_name, response_time_ms)
            
        except Exception as e:
            self.result.add_failure(test_name, str(e))
    
    async def test_cors_configuration(self):
        """Test CORS configuration."""
        test_name = "cors_configuration"
        self.result.tests_run += 1
        
        try:
            response = await self._make_request(
                "OPTIONS",
                "/api/v1/elevation/sources",
                headers={
                    "Origin": "https://road.engineering",
                    "Access-Control-Request-Method": "POST"
                }
            )
            
            if response.status_code not in [200, 204]:
                self.result.add_failure(test_name, f"CORS preflight returned {response.status_code}")
                return
            
            # Check for CORS headers (basic validation)
            cors_headers = [
                "Access-Control-Allow-Origin",
                "Access-Control-Allow-Methods"
            ]
            
            missing_headers = [h for h in cors_headers if h not in response.headers]
            if missing_headers:
                self.result.add_warning(f"Missing CORS headers: {missing_headers}")
            
            self.result.add_success(test_name)
            
        except Exception as e:
            self.result.add_failure(test_name, str(e))
    
    async def test_error_handling(self):
        """Test error handling with invalid coordinates."""
        test_name = "error_handling"
        self.result.tests_run += 1
        
        try:
            response = await self._make_request(
                "POST",
                "/api/v1/elevation/point", 
                json={"latitude": 999, "longitude": 999}
            )
            
            # Should handle gracefully (200 with null elevation or 4xx error)
            if response.status_code not in [200, 400, 404, 422]:
                self.result.add_failure(test_name, f"Poor error handling: {response.status_code}")
                return
            
            if response.status_code == 200:
                data = response.json()
                # Should return null elevation for invalid coordinates
                if data.get("elevation_m") is not None:
                    self.result.add_warning("Invalid coordinates returned elevation data")
            
            self.result.add_success(test_name)
            
        except Exception as e:
            self.result.add_failure(test_name, str(e))
    
    async def run_all_tests(self):
        """Run all smoke tests."""
        print(f"🚀 Starting DEM Backend smoke tests for {self.config.base_url}")
        print(f"⏱️  Timeout: {self.config.timeout}s, Max retries: {self.config.retry_attempts}")
        
        tests = [
            self.test_health_endpoint,
            self.test_root_endpoint,
            self.test_sources_endpoint,
            self.test_elevation_endpoint,
            self.test_cors_configuration,
            self.test_error_handling
        ]
        
        for test in tests:
            test_name = test.__name__.replace("test_", "").replace("_", " ").title()
            print(f"🧪 Running {test_name}...")
            await test()
        
        return self.result


async def main():
    """Main entry point for smoke tests."""
    import argparse
    
    parser = argparse.ArgumentParser(description="DEM Backend Post-Deployment Smoke Test")
    parser.add_argument("--url", default="https://dem-api.road.engineering", 
                       help="Base URL for DEM Backend (default: https://dem-api.road.engineering)")
    parser.add_argument("--timeout", type=float, default=30.0,
                       help="Request timeout in seconds (default: 30)")
    parser.add_argument("--retries", type=int, default=3,
                       help="Number of retry attempts (default: 3)")
    parser.add_argument("--json", action="store_true",
                       help="Output results in JSON format")
    parser.add_argument("--fail-fast", action="store_true",
                       help="Exit on first failure")
    
    args = parser.parse_args()
    
    config = SmokeTestConfig(base_url=args.url)
    config.timeout = args.timeout
    config.retry_attempts = args.retries
    
    try:
        async with DemBackendSmokeTest(config) as smoke_test:
            result = await smoke_test.run_all_tests()
        
        if args.json:
            output = {
                "success": result.is_success(),
                "tests_run": result.tests_run,
                "tests_passed": result.tests_passed,
                "tests_failed": result.tests_failed,
                "failures": result.failures,
                "warnings": result.warnings,
                "response_times": result.response_times,
                "duration_seconds": (datetime.now() - result.start_time).total_seconds()
            }
            print(json.dumps(output, indent=2))
        else:
            print("\n" + "="*60)
            print(result.summary())
            print("="*60)
        
        # Exit with appropriate code
        sys.exit(0 if result.is_success() else 1)
        
    except Exception as e:
        error_msg = f"❌ Smoke test failed with exception: {e}"
        if args.json:
            print(json.dumps({"success": False, "error": str(e)}))
        else:
            print(error_msg)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())