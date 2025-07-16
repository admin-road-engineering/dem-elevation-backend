#!/usr/bin/env python3
"""
S3 Catalog Testing Script for Multi-Location DEM Data
Tests catalog integrity, discovery, and multi-location coverage for S3 buckets.
"""

import sys
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from s3_source_manager import S3SourceManager
    from enhanced_source_selector import EnhancedSourceSelector
    from config import get_settings
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure you're running from the DEM Backend directory")
    sys.exit(1)

class S3CatalogTester:
    """Test S3 catalog functionality and multi-location coverage"""
    
    def __init__(self):
        self.settings = get_settings()
        self.results = []
        
    def log_result(self, test_name: str, success: bool, message: str, details: Dict = None):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        result = {
            "test": test_name,
            "success": success,
            "message": message,
            "details": details or {},
            "timestamp": datetime.now().isoformat()
        }
        self.results.append(result)
        print(f"{status} {test_name}: {message}")
        
    def test_catalog_integrity(self, bucket_name: str = 'road-engineering-elevation-data'):
        """Test catalog integrity for a given bucket"""
        print(f"\n🗂️ Testing catalog integrity for: {bucket_name}")
        
        try:
            manager = S3SourceManager(bucket_name)
            catalog = manager.get_catalog()
            
            if not catalog:
                self.log_result("Catalog Existence", False, "No catalog found or empty")
                return
                
            self.log_result("Catalog Existence", True, f"Found {len(catalog)} entries")
            
            # Validate catalog structure
            required_fields = ['id', 'path', 'bounds', 'resolution_m', 'crs', 'region']
            valid_entries = 0
            
            for entry_id, metadata in catalog.items():
                missing_fields = [field for field in required_fields if not hasattr(metadata, field)]
                if missing_fields:
                    self.log_result(f"Entry Validation: {entry_id}", False, 
                                  f"Missing fields: {missing_fields}")
                else:
                    valid_entries += 1
                    
            self.log_result("Catalog Validation", valid_entries == len(catalog),
                          f"{valid_entries}/{len(catalog)} entries valid")
            
            # Test regional coverage
            regions = {}
            for entry_id, metadata in catalog.items():
                region = getattr(metadata, 'region', 'unknown')
                if region not in regions:
                    regions[region] = []
                regions[region].append(entry_id)
                
            self.log_result("Regional Coverage", len(regions) > 0, 
                          f"Covers {len(regions)} regions: {list(regions.keys())}")
            
            # Print detailed coverage
            for region, entries in regions.items():
                resolutions = []
                for entry_id in entries:
                    metadata = catalog[entry_id]
                    res = getattr(metadata, 'resolution_m', 'unknown')
                    resolutions.append(f"{res}m")
                print(f"  {region}: {len(entries)} datasets ({', '.join(set(resolutions))})")
                
        except Exception as e:
            self.log_result("Catalog Integrity", False, f"Error: {str(e)}")
            
    def test_catalog_discovery(self, bucket_name: str = 'road-engineering-elevation-data'):
        """Test catalog discovery of new datasets"""
        print(f"\n🔍 Testing catalog discovery for: {bucket_name}")
        
        try:
            manager = S3SourceManager(bucket_name)
            
            # Test discovery functionality
            new_datasets = manager.discover_new_datasets()
            self.log_result("Discovery Function", True, 
                          f"Discovery completed, found {len(new_datasets)} new datasets")
            
            if new_datasets:
                print("  New datasets discovered:")
                for dataset in new_datasets:
                    print(f"    - {dataset.get('id', 'unknown')}: {dataset.get('path', 'unknown')}")
                    
                # Test catalog update (dry run)
                self.log_result("Catalog Update Ready", True, 
                              "New datasets ready for catalog integration")
            else:
                self.log_result("Discovery Complete", True, 
                              "No new datasets found - catalog is up to date")
                
        except Exception as e:
            self.log_result("Discovery Test", False, f"Error: {str(e)}")
            
    def test_multi_location_queries(self):
        """Test queries across multiple Australian locations"""
        print(f"\n🌏 Testing multi-location queries")
        
        test_locations = [
            {"name": "QLD (Brisbane)", "lat": -27.4698, "lon": 153.0251, "expected_region": "queensland"},
            {"name": "NSW (Sydney)", "lat": -33.8688, "lon": 151.2093, "expected_region": "nsw"},
            {"name": "VIC (Melbourne)", "lat": -37.8136, "lon": 144.9631, "expected_region": "victoria"},
            {"name": "TAS (Hobart)", "lat": -42.8821, "lon": 147.3272, "expected_region": "tasmania"},
            {"name": "SA (Adelaide)", "lat": -34.9285, "lon": 138.6007, "expected_region": "south_australia"},
            {"name": "WA (Perth)", "lat": -31.9505, "lon": 115.8605, "expected_region": "western_australia"}
        ]
        
        try:
            selector = EnhancedSourceSelector(
                self.settings.DEM_SOURCES,
                getattr(self.settings, 'USE_S3_SOURCES', True),
                getattr(self.settings, 'USE_API_SOURCES', True)
            )
            
            for location in test_locations:
                try:
                    best_source = selector.select_best_source(location["lat"], location["lon"])
                    if best_source:
                        source_info = self.settings.DEM_SOURCES.get(best_source, {})
                        self.log_result(f"Location Query: {location['name']}", True,
                                      f"Selected source: {best_source}",
                                      {"source_path": source_info.get("path", "unknown")})
                    else:
                        self.log_result(f"Location Query: {location['name']}", False,
                                      "No suitable source found")
                except Exception as e:
                    self.log_result(f"Location Query: {location['name']}", False, 
                                  f"Query error: {str(e)}")
                    
        except Exception as e:
            self.log_result("Multi-Location Test", False, f"Setup error: {str(e)}")
            
    def test_source_prioritization(self):
        """Test source prioritization logic"""
        print(f"\n📊 Testing source prioritization")
        
        # Test point in area with multiple potential sources
        test_lat, test_lon = -27.4698, 153.0251  # Brisbane
        
        try:
            selector = EnhancedSourceSelector(
                self.settings.DEM_SOURCES,
                getattr(self.settings, 'USE_S3_SOURCES', True),
                getattr(self.settings, 'USE_API_SOURCES', True)
            )
            
            # Get all available sources for this location
            available_sources = []
            for source_id, source_config in self.settings.DEM_SOURCES.items():
                # Simple check if source might cover this location
                if 'AU' in source_id.upper() or 'australia' in source_id.lower():
                    available_sources.append(source_id)
                    
            best_source = selector.select_best_source(test_lat, test_lon)
            
            self.log_result("Source Prioritization", best_source is not None,
                          f"Selected '{best_source}' from {len(available_sources)} available sources",
                          {"available_sources": available_sources})
            
            # Test cost-aware selection
            if hasattr(selector, 'cost_manager'):
                self.log_result("Cost-Aware Selection", True,
                              "Cost management integrated in source selection")
            else:
                self.log_result("Cost-Aware Selection", False,
                              "Cost management not found in selector")
                
        except Exception as e:
            self.log_result("Source Prioritization", False, f"Error: {str(e)}")
            
    def test_bucket_connectivity(self):
        """Test connectivity to all configured S3 buckets"""
        print(f"\n🔗 Testing S3 bucket connectivity")
        
        # Test primary bucket
        primary_bucket = getattr(self.settings, 'AWS_S3_BUCKET_NAME', 'road-engineering-elevation-data')
        try:
            manager = S3SourceManager(primary_bucket)
            # Test basic connectivity
            catalog = manager.get_catalog()
            self.log_result("Primary Bucket Connectivity", True,
                          f"Successfully connected to {primary_bucket}")
        except Exception as e:
            self.log_result("Primary Bucket Connectivity", False,
                          f"Failed to connect to {primary_bucket}: {str(e)}")
            
        # Test high-res bucket if configured
        high_res_bucket = getattr(self.settings, 'AWS_S3_BUCKET_NAME_HIGH_RES', None)
        if high_res_bucket:
            try:
                manager = S3SourceManager(high_res_bucket)
                catalog = manager.get_catalog()
                self.log_result("High-Res Bucket Connectivity", True,
                              f"Successfully connected to {high_res_bucket}")
            except Exception as e:
                self.log_result("High-Res Bucket Connectivity", False,
                              f"Failed to connect to {high_res_bucket}: {str(e)}")
        else:
            self.log_result("High-Res Bucket Config", False,
                          "High-res bucket not configured")
            
        # Test NZ public bucket
        try:
            manager = S3SourceManager('nz-elevation')
            catalog = manager.get_catalog()
            self.log_result("NZ Public Bucket Connectivity", True,
                          "Successfully connected to nz-elevation")
        except Exception as e:
            self.log_result("NZ Public Bucket Connectivity", False,
                          f"Failed to connect to nz-elevation: {str(e)}")
            
    def generate_report(self):
        """Generate comprehensive test report"""
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r['success'])
        failed_tests = total_tests - passed_tests
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_tests": total_tests,
                "passed": passed_tests,
                "failed": failed_tests,
                "success_rate": (passed_tests / total_tests) * 100 if total_tests > 0 else 0
            },
            "test_results": self.results
        }
        
        return report
        
    def run_all_tests(self):
        """Run all S3 catalog tests"""
        print("🚀 Starting S3 Catalog Testing Suite")
        print("=" * 60)
        
        # Test bucket connectivity first
        self.test_bucket_connectivity()
        
        # Test catalog integrity
        self.test_catalog_integrity()
        
        # Test catalog discovery
        self.test_catalog_discovery()
        
        # Test multi-location queries
        self.test_multi_location_queries()
        
        # Test source prioritization
        self.test_source_prioritization()
        
        # Generate report
        print("\n" + "=" * 60)
        print("📊 S3 CATALOG TEST RESULTS")
        print("=" * 60)
        
        report = self.generate_report()
        
        print(f"Total Tests: {report['summary']['total_tests']}")
        print(f"Passed: {report['summary']['passed']}")
        print(f"Failed: {report['summary']['failed']}")
        print(f"Success Rate: {report['summary']['success_rate']:.1f}%")
        
        # Save report
        report_path = Path(__file__).parent.parent / "s3_catalog_test_report.json"
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\nDetailed report saved to: {report_path}")
        
        return report['summary']['failed'] == 0

def main():
    """Main entry point"""
    tester = S3CatalogTester()
    success = tester.run_all_tests()
    
    if success:
        print("\n✅ All S3 catalog tests passed!")
    else:
        print("\n❌ Some S3 catalog tests failed. Check the report for details.")
        
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()