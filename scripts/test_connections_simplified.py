#!/usr/bin/env python3
"""
Simplified Connection Testing Script
Tests external API and S3 connections without requiring full GDAL stack
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import httpx
import boto3
from botocore.exceptions import ClientError

class ConnectionTestResult:
    """Container for connection test results"""
    def __init__(self, service_name: str, test_name: str):
        self.service_name = service_name
        self.test_name = test_name
        self.success = False
        self.error_message = ""
        self.response_time_ms = 0
        self.additional_info = {}
    
    def __str__(self):
        status = "PASS" if self.success else "FAIL"
        time_info = f"({self.response_time_ms:.0f}ms)" if self.response_time_ms > 0 else ""
        return f"{status} {self.service_name} - {self.test_name} {time_info}"

class ConnectionTestSuite:
    """Simplified connection testing suite"""
    
    def __init__(self):
        self.results: List[ConnectionTestResult] = []
        self.start_time = datetime.now()
        self.load_env_vars()
    
    def load_env_vars(self):
        """Load environment variables from .env file manually"""
        env_path = Path(__file__).parent.parent / ".env"
        
        print("Loading environment from .env file")
        
        if env_path.exists():
            # Load manually to avoid dotenv issues
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key] = value
            print("Environment loaded manually from .env")
        else:
            print("No .env file found")
    
    def add_result(self, result: ConnectionTestResult):
        """Add a test result"""
        self.results.append(result)
        print(result)
    
    async def test_gpxz_api_connectivity(self) -> List[ConnectionTestResult]:
        """Test GPXZ.io API connectivity"""
        results = []
        
        # Test 1: API Key Check
        result = ConnectionTestResult("GPXZ.io", "API Key Check")
        api_key = os.getenv('GPXZ_API_KEY')
        if not api_key:
            result.error_message = "GPXZ_API_KEY not set in environment"
        elif api_key.startswith('${') or api_key == '':
            result.error_message = "GPXZ_API_KEY is placeholder or empty"
        else:
            result.success = True
            result.additional_info["key_length"] = len(api_key)
        
        results.append(result)
        self.add_result(result)
        
        # Test 2: Direct API Test
        if result.success:
            result = ConnectionTestResult("GPXZ.io", "Direct API Test")
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    start_time = time.time()
                    response = await client.get(
                        "https://api.gpxz.io/v1/elevation/point",
                        params={"lat": -27.4698, "lon": 153.0251},
                        headers={"X-API-Key": api_key}
                    )
                    result.response_time_ms = (time.time() - start_time) * 1000
                    
                    if response.status_code == 200:
                        data = response.json()
                        result.success = True
                        result.additional_info["elevation"] = data.get("elevation")
                    else:
                        result.error_message = f"HTTP {response.status_code}: {response.text}"
            except Exception as e:
                result.error_message = str(e)
            
            results.append(result)
            self.add_result(result)
        
        return results
    
    async def test_s3_bucket_connectivity(self) -> List[ConnectionTestResult]:
        """Test S3 bucket connectivity"""
        results = []
        
        # Test 1: AWS Credentials
        result = ConnectionTestResult("AWS S3", "Credentials Check")
        access_key = os.getenv('AWS_ACCESS_KEY_ID')
        secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        
        if not access_key or not secret_key:
            result.error_message = "AWS credentials not set in environment"
        elif access_key.startswith('${') or secret_key.startswith('${'):
            result.error_message = "AWS credentials are placeholders"
        else:
            result.success = True
            result.additional_info["access_key_length"] = len(access_key)
        
        results.append(result)
        self.add_result(result)
        
        if result.success:
            # Test 2: Primary Bucket Access
            result = ConnectionTestResult("AWS S3", "Primary Bucket Access")
            try:
                s3_client = boto3.client(
                    's3',
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
                    region_name='ap-southeast-2'
                )
                
                bucket_name = os.getenv('AWS_S3_BUCKET_NAME', 'roadengineer-dem-files')
                start_time = time.time()
                response = s3_client.head_bucket(Bucket=bucket_name)
                result.response_time_ms = (time.time() - start_time) * 1000
                result.success = True
                result.additional_info["bucket_name"] = bucket_name
                
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
            
            # Test 3: List Objects in Bucket
            if result.success:
                result = ConnectionTestResult("AWS S3", "List Objects Test")
                try:
                    start_time = time.time()
                    response = s3_client.list_objects_v2(Bucket=bucket_name, MaxKeys=10)
                    result.response_time_ms = (time.time() - start_time) * 1000
                    
                    objects = response.get('Contents', [])
                    result.success = True
                    result.additional_info["object_count"] = len(objects)
                    result.additional_info["sample_objects"] = [obj['Key'] for obj in objects[:5]]
                    
                except ClientError as e:
                    result.error_message = f"List objects error: {e.response['Error']['Code']}"
                except Exception as e:
                    result.error_message = str(e)
                
                results.append(result)
                self.add_result(result)
        
        return results
    
    async def test_main_platform_connectivity(self) -> List[ConnectionTestResult]:
        """Test main platform connectivity"""
        results = []
        
        # Test production API
        result = ConnectionTestResult("Main Platform", "Production API")
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
    
    async def test_local_dem_backend(self) -> List[ConnectionTestResult]:
        """Test local DEM backend if running"""
        results = []
        
        result = ConnectionTestResult("DEM Backend", "Local Service Health")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                start_time = time.time()
                response = await client.get("http://localhost:8001/health")
                result.response_time_ms = (time.time() - start_time) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "healthy":
                        result.success = True
                        result.additional_info = data
                    else:
                        result.error_message = f"Service unhealthy: {data.get('status')}"
                else:
                    result.error_message = f"HTTP {response.status_code}"
        except Exception as e:
            result.error_message = "Service not running or connection failed"
        
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
    """Run simplified connection tests"""
    print("Starting DEM Backend Connection Tests (Simplified)")
    print("=" * 60)
    
    suite = ConnectionTestSuite()
    
    # Test GPXZ API
    print("\nTesting GPXZ.io API...")
    await suite.test_gpxz_api_connectivity()
    
    # Test S3 Connections
    print("\nTesting S3 Connections...")
    await suite.test_s3_bucket_connectivity()
    
    # Test Main Platform
    print("\nTesting Main Platform...")
    await suite.test_main_platform_connectivity()
    
    # Test Local DEM Backend
    print("\nTesting Local DEM Backend...")
    await suite.test_local_dem_backend()
    
    # Generate Report
    print("\n" + "=" * 60)
    print("CONNECTION TEST RESULTS")
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
    
    # Show failures
    failed_tests = [r for r in suite.results if not r.success]
    if failed_tests:
        print(f"\nFailed Tests ({len(failed_tests)}):")
        for test in failed_tests:
            print(f"  {test.service_name} - {test.test_name}: {test.error_message}")
    
    # Save detailed report
    report_path = Path(__file__).parent.parent / "connection_test_report.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\nDetailed report saved to: {report_path}")
    
    # Exit with appropriate code
    sys.exit(0 if report['summary']['failed'] == 0 else 1)

if __name__ == "__main__":
    asyncio.run(main())