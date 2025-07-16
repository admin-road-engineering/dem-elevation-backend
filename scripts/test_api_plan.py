#!/usr/bin/env python3
"""
Comprehensive API Testing Plan for DEM Backend
Tests all external API and S3 connections systematically
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
import httpx
import boto3
from botocore.exceptions import ClientError
import os
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gpxz_client import GPXZClient
from config import Settings

class APITestResult:
    """Container for test results"""
    def __init__(self, service_name: str, test_name: str):
        self.service_name = service_name
        self.test_name = test_name
        self.success = False
        self.error_message = ""
        self.response_time_ms = 0
        self.additional_info = {}
    
    def __str__(self):
        status = "✅ PASS" if self.success else "❌ FAIL"
        time_info = f"({self.response_time_ms:.0f}ms)" if self.response_time_ms > 0 else ""
        return f"{status} {self.service_name} - {self.test_name} {time_info}"

class APITestSuite:
    """Comprehensive API testing suite for DEM Backend"""
    
    def __init__(self):
        self.results: List[APITestResult] = []
        self.settings = None
        self.start_time = datetime.now()
    
    def add_result(self, result: APITestResult):
        """Add a test result"""
        self.results.append(result)
        print(result)
    
    async def test_gpxz_api(self) -> List[APITestResult]:
        """Test GPXZ.io API connectivity and functionality"""
        results = []
        
        # Test 1: API Key Validation
        result = APITestResult("GPXZ.io", "API Key Validation")
        try:
            api_key = os.getenv('GPXZ_API_KEY')
            if not api_key:
                result.error_message = "GPXZ_API_KEY not set in environment"
            elif api_key == "${GPXZ_API_KEY}":
                result.error_message = "GPXZ_API_KEY is placeholder, not actual key"
            else:
                result.success = True
                result.additional_info["key_length"] = len(api_key)
        except Exception as e:
            result.error_message = str(e)
        
        results.append(result)
        self.add_result(result)
        
        # Test 2: Client Initialization
        result = APITestResult("GPXZ.io", "Client Initialization")
        gpxz_client = None
        try:
            gpxz_client = GPXZClient(
                api_key=os.getenv('GPXZ_API_KEY', ''),
                daily_limit=100,
                rate_limit=1
            )
            result.success = True
        except Exception as e:
            result.error_message = str(e)
        
        results.append(result)
        self.add_result(result)
        
        if gpxz_client and result.success:
            # Test 3: Single Point Elevation
            result = APITestResult("GPXZ.io", "Single Point Elevation")
            try:
                start_time = time.time()
                elevation = await gpxz_client.get_elevation(-27.4698, 153.0251)  # Brisbane
                result.response_time_ms = (time.time() - start_time) * 1000
                
                if elevation is not None:
                    result.success = True
                    result.additional_info["elevation"] = elevation
                else:
                    result.error_message = "API returned null elevation"
            except Exception as e:
                result.error_message = str(e)
            
            results.append(result)
            self.add_result(result)
            
            # Test 4: Rate Limiting
            result = APITestResult("GPXZ.io", "Rate Limiting")
            try:
                # Make multiple rapid requests to test rate limiting
                start_time = time.time()
                for i in range(3):
                    await gpxz_client.get_elevation(-27.4698 + i*0.001, 153.0251)
                
                result.response_time_ms = (time.time() - start_time) * 1000
                result.success = True
                result.additional_info["requests_made"] = 3
            except Exception as e:
                if "rate limit" in str(e).lower():
                    result.success = True  # Rate limiting working as expected
                    result.additional_info["rate_limit_triggered"] = True
                else:
                    result.error_message = str(e)
            
            results.append(result)
            self.add_result(result)
        
        return results
    
    async def test_s3_connections(self) -> List[APITestResult]:
        """Test S3 bucket connections"""
        results = []
        
        # Test AWS Credentials
        result = APITestResult("AWS S3", "Credentials Check")
        try:
            access_key = os.getenv('AWS_ACCESS_KEY_ID')
            secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
            
            if not access_key or not secret_key:
                result.error_message = "AWS credentials not set in environment"
            elif access_key == "${AWS_ACCESS_KEY_ID}":
                result.error_message = "AWS credentials are placeholders, not actual keys"
            else:
                result.success = True
                result.additional_info["access_key_length"] = len(access_key)
        except Exception as e:
            result.error_message = str(e)
        
        results.append(result)
        self.add_result(result)
        
        # Test Primary S3 Bucket Access
        result = APITestResult("AWS S3", "Primary Bucket Access")
        try:
            s3_client = boto3.client(
                's3',
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                region_name='ap-southeast-2'
            )
            
            start_time = time.time()
            response = s3_client.head_bucket(Bucket='road-engineering-elevation-data')
            result.response_time_ms = (time.time() - start_time) * 1000
            result.success = True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '403':
                result.error_message = "Access denied - check AWS credentials"
            elif error_code == '404':
                result.error_message = "Bucket not found"
            else:
                result.error_message = f"AWS Error: {error_code}"
        except Exception as e:
            result.error_message = str(e)
        
        results.append(result)
        self.add_result(result)
        
        # Test NZ Open Data Bucket (Public)
        result = APITestResult("AWS S3", "NZ Open Data Bucket")
        try:
            s3_client = boto3.client('s3', region_name='ap-southeast-2')
            
            start_time = time.time()
            response = s3_client.head_bucket(Bucket='nz-elevation')
            result.response_time_ms = (time.time() - start_time) * 1000
            result.success = True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            result.error_message = f"AWS Error: {error_code}"
        except Exception as e:
            result.error_message = str(e)
        
        results.append(result)
        self.add_result(result)
        
        # Test DEM File Access
        if results[-2].success:  # If primary bucket access worked
            result = APITestResult("AWS S3", "DEM File Access")
            try:
                start_time = time.time()
                response = s3_client.head_object(
                    Bucket='road-engineering-elevation-data',
                    Key='AU_National_5m_DEM.tif'
                )
                result.response_time_ms = (time.time() - start_time) * 1000
                result.success = True
                result.additional_info["file_size"] = response.get('ContentLength', 0)
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                result.error_message = f"File access error: {error_code}"
            except Exception as e:
                result.error_message = str(e)
            
            results.append(result)
            self.add_result(result)
        
        return results
    
    async def test_dem_backend_endpoints(self) -> List[APITestResult]:
        """Test DEM Backend's own API endpoints"""
        results = []
        base_url = "http://localhost:8001"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Test 1: Health Check
            result = APITestResult("DEM Backend", "Health Check")
            try:
                start_time = time.time()
                response = await client.get(f"{base_url}/health")
                result.response_time_ms = (time.time() - start_time) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "healthy":
                        result.success = True
                        result.additional_info = data
                    else:
                        result.error_message = f"Unhealthy status: {data.get('status')}"
                else:
                    result.error_message = f"HTTP {response.status_code}"
            except Exception as e:
                result.error_message = str(e)
            
            results.append(result)
            self.add_result(result)
            
            # Test 2: Sources Endpoint
            result = APITestResult("DEM Backend", "Sources Endpoint")
            try:
                start_time = time.time()
                response = await client.get(f"{base_url}/api/v1/elevation/sources")
                result.response_time_ms = (time.time() - start_time) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    result.success = True
                    result.additional_info["total_sources"] = data.get("total_sources", 0)
                    result.additional_info["sources"] = list(data.get("sources", {}).keys())
                else:
                    result.error_message = f"HTTP {response.status_code}"
            except Exception as e:
                result.error_message = str(e)
            
            results.append(result)
            self.add_result(result)
            
            # Test 3: Point Elevation
            result = APITestResult("DEM Backend", "Point Elevation")
            try:
                start_time = time.time()
                response = await client.post(
                    f"{base_url}/api/v1/elevation/point",
                    json={"latitude": -27.4698, "longitude": 153.0251}
                )
                result.response_time_ms = (time.time() - start_time) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    result.success = True
                    result.additional_info["elevation"] = data.get("elevation_m")
                    result.additional_info["source"] = data.get("source")
                else:
                    result.error_message = f"HTTP {response.status_code}"
            except Exception as e:
                result.error_message = str(e)
            
            results.append(result)
            self.add_result(result)
        
        return results
    
    async def test_multi_location_elevation(self) -> List[APITestResult]:
        """Test elevation queries across multiple Australian locations"""
        results = []
        base_url = "http://localhost:8001"
        
        test_locations = [
            {"name": "QLD (Brisbane)", "lat": -27.4698, "lon": 153.0251, "expected_sources": ["au_qld_lidar", "au_national"]},
            {"name": "NSW (Sydney)", "lat": -33.8688, "lon": 151.2093, "expected_sources": ["au_nsw_dem", "au_national"]},
            {"name": "VIC (Melbourne)", "lat": -37.8136, "lon": 144.9631, "expected_sources": ["au_national", "global_srtm"]},
            {"name": "TAS (Hobart)", "lat": -42.8821, "lon": 147.3272, "expected_sources": ["au_tas_lidar", "au_national"]},
            {"name": "SA (Adelaide)", "lat": -34.9285, "lon": 138.6007, "expected_sources": ["au_national", "global_srtm"]},
            {"name": "WA (Perth)", "lat": -31.9505, "lon": 115.8605, "expected_sources": ["au_national", "global_srtm"]}
        ]
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for location in test_locations:
                result = APITestResult("Multi-Location", f"{location['name']}")
                try:
                    start_time = time.time()
                    response = await client.post(
                        f"{base_url}/api/v1/elevation/point",
                        json={"latitude": location["lat"], "longitude": location["lon"]}
                    )
                    result.response_time_ms = (time.time() - start_time) * 1000
                    
                    if response.status_code == 200:
                        data = response.json()
                        elevation = data.get("elevation_m")
                        source = data.get("source")
                        
                        if elevation is not None:
                            result.success = True
                            result.additional_info = {
                                "elevation": elevation,
                                "source": source,
                                "coordinates": {"lat": location["lat"], "lon": location["lon"]}
                            }
                            
                            # Log source selection for analysis
                            expected_any = any(exp in source for exp in location["expected_sources"]) if source else False
                            if not expected_any:
                                result.additional_info["source_warning"] = f"Unexpected source, expected one of: {location['expected_sources']}"
                        else:
                            result.error_message = "Elevation data not available for this location"
                    else:
                        result.error_message = f"HTTP {response.status_code}"
                except Exception as e:
                    result.error_message = str(e)
                
                results.append(result)
                self.add_result(result)
        
        return results

    async def test_main_platform_integration(self) -> List[APITestResult]:
        """Test integration with main platform"""
        results = []
        
        # Test production main platform
        result = APITestResult("Main Platform", "Production API Health")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                start_time = time.time()
                response = await client.get("https://api.road.engineering/health")
                result.response_time_ms = (time.time() - start_time) * 1000
                
                if response.status_code == 200:
                    result.success = True
                    result.additional_info = response.json()
                else:
                    result.error_message = f"HTTP {response.status_code}"
        except Exception as e:
            result.error_message = str(e)
        
        results.append(result)
        self.add_result(result)
        
        return results
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive test report"""
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.success)
        failed_tests = total_tests - passed_tests
        
        # Group results by service
        by_service = {}
        for result in self.results:
            if result.service_name not in by_service:
                by_service[result.service_name] = []
            by_service[result.service_name].append(result)
        
        # Calculate service success rates
        service_stats = {}
        for service, results in by_service.items():
            total = len(results)
            passed = sum(1 for r in results if r.success)
            service_stats[service] = {
                "total": total,
                "passed": passed,
                "failed": total - passed,
                "success_rate": (passed / total) * 100 if total > 0 else 0
            }
        
        return {
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": (datetime.now() - self.start_time).total_seconds(),
            "summary": {
                "total_tests": total_tests,
                "passed": passed_tests,
                "failed": failed_tests,
                "success_rate": (passed_tests / total_tests) * 100 if total_tests > 0 else 0
            },
            "services": service_stats,
            "detailed_results": [
                {
                    "service": r.service_name,
                    "test": r.test_name,
                    "success": r.success,
                    "error": r.error_message,
                    "response_time_ms": r.response_time_ms,
                    "additional_info": r.additional_info
                } for r in self.results
            ]
        }

async def main():
    """Run comprehensive API tests"""
    print("🚀 Starting DEM Backend API Testing Suite")
    print("=" * 60)
    
    suite = APITestSuite()
    
    # Test GPXZ API
    print("\n📡 Testing GPXZ.io API...")
    await suite.test_gpxz_api()
    
    # Test S3 Connections
    print("\n☁️ Testing S3 Connections...")
    await suite.test_s3_connections()
    
    # Test DEM Backend Endpoints
    print("\n🏠 Testing DEM Backend Endpoints...")
    await suite.test_dem_backend_endpoints()
    
    # Test Multi-Location Elevation
    print("\n🌏 Testing Multi-Location Elevation...")
    await suite.test_multi_location_elevation()
    
    # Test Main Platform Integration
    print("\n🔗 Testing Main Platform Integration...")
    await suite.test_main_platform_integration()
    
    # Generate Report
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 60)
    
    report = suite.generate_report()
    
    print(f"Total Tests: {report['summary']['total_tests']}")
    print(f"Passed: {report['summary']['passed']}")
    print(f"Failed: {report['summary']['failed']}")
    print(f"Success Rate: {report['summary']['success_rate']:.1f}%")
    print(f"Duration: {report['duration_seconds']:.2f}s")
    
    print("\nBy Service:")
    for service, stats in report['services'].items():
        print(f"  {service}: {stats['passed']}/{stats['total']} ({stats['success_rate']:.1f}%)")
    
    # Save detailed report
    report_path = Path(__file__).parent.parent / "api_test_report.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\nDetailed report saved to: {report_path}")
    
    # Exit with appropriate code
    sys.exit(0 if report['summary']['failed'] == 0 else 1)

if __name__ == "__main__":
    asyncio.run(main())