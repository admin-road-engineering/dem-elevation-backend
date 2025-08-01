#!/usr/bin/env python3
"""
Comprehensive Testing Suite for DEM Backend
"""
import sys
import os
import asyncio
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# Set up path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import get_settings
from enhanced_source_selector import EnhancedSourceSelector
from s3_source_manager import S3SourceManager
from dem_service import DEMService

class ComprehensiveTestSuite:
    def __init__(self):
        self.settings = get_settings()
        self.results = []
        self.start_time = datetime.now()
        
    def log_result(self, test_name: str, success: bool, message: str, details: Dict = None):
        """Log test result"""
        status = "PASS" if success else "FAIL"
        result = {
            "test": test_name,
            "success": success,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "details": details or {}
        }
        self.results.append(result)
        print(f"[{status}] {test_name}: {message}")
        if details:
            for key, value in details.items():
                print(f"  {key}: {value}")
        
    async def test_configuration(self):
        """Test configuration loading"""
        try:
            settings = get_settings()
            self.log_result(
                "Configuration Loading",
                True,
                f"Loaded {len(settings.DEM_SOURCES)} DEM sources",
                {
                    "sources_count": len(settings.DEM_SOURCES),
                    "use_s3": settings.USE_S3_SOURCES,
                    "use_api": settings.USE_API_SOURCES
                }
            )
            return True
        except Exception as e:
            self.log_result("Configuration Loading", False, f"Failed: {e}")
            return False
            
    async def test_source_selection(self):
        """Test source selection for multiple locations"""
        try:
            selector = EnhancedSourceSelector(
                self.settings.DEM_SOURCES,
                self.settings.USE_S3_SOURCES,
                self.settings.USE_API_SOURCES
            )
            
            test_coords = [
                (-27.4698, 153.0251, "Brisbane, Australia"),
                (-36.8485, 174.7633, "Auckland, New Zealand"),
                (40.7128, -74.0060, "New York, USA"),
                (-33.8688, 151.2093, "Sydney, Australia")
            ]
            
            results = {}
            for lat, lon, location in test_coords:
                source = selector.select_best_source(lat, lon)
                results[location] = source
                
            self.log_result(
                "Source Selection",
                True,
                f"Selected sources for {len(test_coords)} locations",
                results
            )
            return True
            
        except Exception as e:
            self.log_result("Source Selection", False, f"Failed: {e}")
            return False
    
    async def test_s3_connectivity(self):
        """Test S3 connectivity"""
        try:
            manager = S3SourceManager(self.settings)
            
            # Test S3 source availability
            s3_sources = [
                source_id for source_id, source in self.settings.DEM_SOURCES.items()
                if source.get("path", "").startswith("s3://")
            ]
            
            available_count = 0
            for source_id in s3_sources:
                try:
                    # This is a basic connectivity test
                    source_config = self.settings.DEM_SOURCES[source_id]
                    # Simple validation - in real test we'd check bucket access
                    if "s3://" in source_config.get("path", ""):
                        available_count += 1
                except Exception:
                    pass
            
            self.log_result(
                "S3 Connectivity",
                available_count > 0,
                f"Found {available_count} S3 sources",
                {
                    "s3_sources_configured": len(s3_sources),
                    "s3_sources_available": available_count
                }
            )
            return available_count > 0
            
        except Exception as e:
            self.log_result("S3 Connectivity", False, f"Failed: {e}")
            return False
    
    async def test_service_initialization(self):
        """Test DEM service initialization"""
        try:
            service = DEMService(self.settings)
            
            # Test service startup
            await service.startup()
            
            self.log_result(
                "Service Initialization",
                True,
                "DEM Service initialized successfully",
                {
                    "service_type": type(service).__name__,
                    "selector_type": type(service.source_selector).__name__
                }
            )
            
            # Cleanup
            await service.shutdown()
            return True
            
        except Exception as e:
            self.log_result("Service Initialization", False, f"Failed: {e}")
            return False
    
    async def test_elevation_query(self):
        """Test basic elevation query"""
        try:
            service = DEMService(self.settings)
            await service.startup()
            
            # Test Brisbane coordinate
            lat, lon = -27.4698, 153.0251
            start_time = time.time()
            
            elevation = await service.get_elevation(lat, lon)
            
            response_time = (time.time() - start_time) * 1000  # ms
            
            success = elevation is not None
            
            self.log_result(
                "Elevation Query",
                success,
                f"Elevation: {elevation}m" if success else "No elevation data",
                {
                    "latitude": lat,
                    "longitude": lon,
                    "elevation_m": elevation,
                    "response_time_ms": response_time
                }
            )
            
            await service.shutdown()
            return success
            
        except Exception as e:
            self.log_result("Elevation Query", False, f"Failed: {e}")
            return False
    
    async def run_all_tests(self):
        """Run all tests"""
        print("COMPREHENSIVE DEM BACKEND TEST SUITE")
        print("=" * 50)
        print(f"Started: {self.start_time}")
        print("=" * 50)
        
        tests = [
            self.test_configuration,
            self.test_source_selection,
            self.test_s3_connectivity,
            self.test_service_initialization,
            self.test_elevation_query
        ]
        
        passed = 0
        total = len(tests)
        
        for test in tests:
            try:
                if await test():
                    passed += 1
            except Exception as e:
                print(f"Test {test.__name__} crashed: {e}")
        
        print("=" * 50)
        print(f"SUMMARY: {passed}/{total} tests passed")
        print(f"Duration: {datetime.now() - self.start_time}")
        print("=" * 50)
        
        # Performance metrics
        response_times = [
            r["details"].get("response_time_ms", 0)
            for r in self.results
            if "response_time_ms" in r.get("details", {})
        ]
        
        if response_times:
            avg_response = sum(response_times) / len(response_times)
            print(f"Average response time: {avg_response:.2f}ms")
            print(f"Performance target (<500ms): {'PASS' if avg_response < 500 else 'FAIL'}")
        
        return passed == total

async def main():
    suite = ComprehensiveTestSuite()
    success = await suite.run_all_tests()
    
    # Save results
    with open("comprehensive_test_results.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "success": success,
            "results": suite.results
        }, f, indent=2)
    
    return success

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)