#!/usr/bin/env python3
"""
S3 Index Validation Script
Phase 2 implementation for comprehensive index validation with CI/CD integration

Validates S3 spatial indexes for structural integrity, data consistency, and freshness
Designed for integration with CI/CD pipelines and scheduled monitoring
"""

import os
import sys
import json
import time
import boto3
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from botocore.exceptions import ClientError
from botocore.config import Config
import jsonschema
from jsonschema import validate, ValidationError

@dataclass
class ValidationResult:
    """Result of an index validation check"""
    index_name: str
    check_name: str
    success: bool
    details: str
    severity: str = "info"  # info, warning, error, critical
    execution_time_ms: float = 0.0

class S3IndexValidator:
    """Validate S3 spatial indexes for production readiness"""
    
    def __init__(self):
        self.bucket_name = os.getenv("S3_INDEX_BUCKET", "road-engineering-elevation-data")
        self.region = "ap-southeast-2"
        self.s3_client = None
        self.validation_results: List[ValidationResult] = []
        
        # Index files to validate
        self.indexes_to_validate = {
            "campaign": os.getenv('S3_CAMPAIGN_INDEX_KEY', 'indexes/campaign_index.json'),
            "spatial": os.getenv('S3_SPATIAL_INDEX_KEY', 'indexes/spatial_index.json'),
            "tiled": os.getenv('S3_TILED_INDEX_KEY', 'indexes/phase3_brisbane_tiled_index.json'),
            "nz_spatial": os.getenv('S3_NZ_INDEX_KEY', 'indexes/nz_spatial_index.json')
        }
        
        # JSON schemas for validation
        self.schemas = self._define_schemas()
        
    def _get_s3_client(self) -> boto3.client:
        """Get S3 client with production configuration"""
        if not self.s3_client:
            config = Config(
                connect_timeout=int(os.getenv("S3_CONNECT_TIMEOUT", "10")),
                read_timeout=int(os.getenv("S3_READ_TIMEOUT", "60")),
                retries={'max_attempts': int(os.getenv("S3_MAX_ATTEMPTS", "3"))},
                region_name=self.region
            )
            
            self.s3_client = boto3.client('s3', config=config)
            
        return self.s3_client
        
    def _define_schemas(self) -> Dict[str, Dict]:
        """Define JSON schemas for index validation"""
        return {
            "campaign": {
                "type": "object",
                "required": ["campaign_count", "campaigns", "metadata"],
                "properties": {
                    "campaign_count": {"type": "integer", "minimum": 1},
                    "campaigns": {"type": "object"},
                    "metadata": {
                        "type": "object",
                        "required": ["generated_at", "total_files"],
                        "properties": {
                            "generated_at": {"type": "string"},
                            "total_files": {"type": "integer", "minimum": 1}
                        }
                    }
                }
            },
            "spatial": {
                "type": "object", 
                "required": ["file_count", "files", "metadata"],
                "properties": {
                    "file_count": {"type": "integer", "minimum": 1},
                    "files": {"type": "object"},
                    "metadata": {
                        "type": "object",
                        "required": ["generated_at"],
                        "properties": {
                            "generated_at": {"type": "string"}
                        }
                    }
                }
            },
            "tiled": {
                "type": "object",
                "required": ["tile_count", "tiles", "metadata"],
                "properties": {
                    "tile_count": {"type": "integer", "minimum": 1},
                    "tiles": {"type": "object"},
                    "metadata": {
                        "type": "object",
                        "required": ["generated_at", "tile_size_m"],
                        "properties": {
                            "generated_at": {"type": "string"},
                            "tile_size_m": {"type": "number", "minimum": 1}
                        }
                    }
                }
            }
        }
        
    def _log_result(self, index_name: str, check_name: str, success: bool, 
                   details: str, severity: str = "info", execution_time_ms: float = 0.0):
        """Log validation result"""
        result = ValidationResult(
            index_name=index_name,
            check_name=check_name,
            success=success,
            details=details,
            severity=severity,
            execution_time_ms=execution_time_ms
        )
        
        self.validation_results.append(result)
        
        # Console output
        status = "✓" if success else "✗"
        severity_prefix = f"[{severity.upper()}]" if severity != "info" else ""
        print(f"{status} {severity_prefix} {index_name}/{check_name}: {details}")
        
    def validate_index_existence(self, index_name: str, s3_key: str) -> bool:
        """Validate that index file exists and is accessible"""
        start_time = time.time()
        
        try:
            s3_client = self._get_s3_client()
            response = s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            
            execution_time = (time.time() - start_time) * 1000
            file_size = response.get('ContentLength', 0)
            size_mb = round(file_size / (1024 * 1024), 2)
            last_modified = response.get('LastModified')
            
            self._log_result(
                index_name, "existence",
                success=True,
                details=f"Found {size_mb}MB file, modified {last_modified}",
                execution_time_ms=execution_time
            )
            return True
            
        except ClientError as e:
            execution_time = (time.time() - start_time) * 1000
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            
            self._log_result(
                index_name, "existence",
                success=False,
                details=f"Not found: {error_code}",
                severity="error",
                execution_time_ms=execution_time
            )
            return False
            
    def validate_json_structure(self, index_name: str, s3_key: str) -> Tuple[bool, Optional[Dict]]:
        """Validate JSON structure and syntax"""
        start_time = time.time()
        
        try:
            s3_client = self._get_s3_client()
            response = s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            body = response['Body'].read()
            
            # Parse JSON
            data = json.loads(body.decode('utf-8'))
            execution_time = (time.time() - start_time) * 1000
            
            self._log_result(
                index_name, "json_structure",
                success=True,
                details=f"Valid JSON ({len(body)} bytes)",
                execution_time_ms=execution_time
            )
            return True, data
            
        except json.JSONDecodeError as e:
            execution_time = (time.time() - start_time) * 1000
            self._log_result(
                index_name, "json_structure",
                success=False,
                details=f"JSON decode error: {e}",
                severity="critical",
                execution_time_ms=execution_time
            )
            return False, None
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self._log_result(
                index_name, "json_structure",
                success=False,
                details=f"Read error: {e}",
                severity="error",
                execution_time_ms=execution_time
            )
            return False, None
            
    def validate_schema_compliance(self, index_name: str, data: Dict) -> bool:
        """Validate index data against expected schema"""
        if index_name not in self.schemas:
            self._log_result(
                index_name, "schema_compliance",
                success=True,
                details="No schema defined, skipping",
                severity="warning"
            )
            return True
            
        try:
            validate(instance=data, schema=self.schemas[index_name])
            
            self._log_result(
                index_name, "schema_compliance",
                success=True,
                details="Schema validation passed"
            )
            return True
            
        except ValidationError as e:
            self._log_result(
                index_name, "schema_compliance",
                success=False,
                details=f"Schema violation: {e.message}",
                severity="error"
            )
            return False
            
    def validate_data_freshness(self, index_name: str, data: Dict) -> bool:
        """Validate that index data is reasonably fresh"""
        metadata = data.get('metadata', {})
        generated_at_str = metadata.get('generated_at')
        
        if not generated_at_str:
            self._log_result(
                index_name, "data_freshness",
                success=False,
                details="No generation timestamp found",
                severity="warning"
            )
            return False
            
        try:
            # Parse generation timestamp
            generated_at = datetime.fromisoformat(generated_at_str.replace('Z', '+00:00'))
            age_days = (datetime.utcnow().replace(tzinfo=generated_at.tzinfo) - generated_at).days
            
            # Freshness thresholds
            if age_days <= 30:
                severity = "info"
                success = True
            elif age_days <= 90:
                severity = "warning"
                success = True
            else:
                severity = "error"
                success = False
                
            self._log_result(
                index_name, "data_freshness",
                success=success,
                details=f"Index is {age_days} days old",
                severity=severity
            )
            return success
            
        except Exception as e:
            self._log_result(
                index_name, "data_freshness",
                success=False,
                details=f"Date parsing error: {e}",
                severity="warning"
            )
            return False
            
    def validate_data_consistency(self, index_name: str, data: Dict) -> bool:
        """Validate internal data consistency"""
        try:
            if index_name == "campaign":
                # Check campaign count matches actual campaigns
                declared_count = data.get('campaign_count', 0)
                actual_count = len(data.get('campaigns', {}))
                
                if declared_count == actual_count:
                    self._log_result(
                        index_name, "data_consistency", 
                        success=True,
                        details=f"Campaign count matches: {actual_count}"
                    )
                    return True
                else:
                    self._log_result(
                        index_name, "data_consistency",
                        success=False,
                        details=f"Count mismatch: declared {declared_count}, actual {actual_count}",
                        severity="error"
                    )
                    return False
                    
            elif index_name == "spatial":
                # Check file count matches actual files
                declared_count = data.get('file_count', 0)
                actual_count = len(data.get('files', {}))
                
                if declared_count == actual_count:
                    self._log_result(
                        index_name, "data_consistency",
                        success=True,
                        details=f"File count matches: {actual_count}"
                    )
                    return True
                else:
                    self._log_result(
                        index_name, "data_consistency",
                        success=False,
                        details=f"Count mismatch: declared {declared_count}, actual {actual_count}",
                        severity="error"
                    )
                    return False
                    
            elif index_name == "tiled":
                # Check tile count matches actual tiles
                declared_count = data.get('tile_count', 0)
                actual_count = len(data.get('tiles', {}))
                
                if declared_count == actual_count:
                    self._log_result(
                        index_name, "data_consistency",
                        success=True,
                        details=f"Tile count matches: {actual_count}"
                    )
                    return True
                else:
                    self._log_result(
                        index_name, "data_consistency",
                        success=False,
                        details=f"Count mismatch: declared {declared_count}, actual {actual_count}",
                        severity="error"
                    )
                    return False
            else:
                self._log_result(
                    index_name, "data_consistency",
                    success=True,
                    details="No consistency checks defined",
                    severity="info"
                )
                return True
                
        except Exception as e:
            self._log_result(
                index_name, "data_consistency",
                success=False,
                details=f"Consistency check error: {e}",
                severity="error"
            )
            return False
            
    def validate_sample_data_integrity(self, index_name: str, data: Dict) -> bool:
        """Validate sample entries for data integrity"""
        try:
            if index_name == "campaign":
                campaigns = data.get('campaigns', {})
                if not campaigns:
                    self._log_result(
                        index_name, "sample_data",
                        success=False,
                        details="No campaigns found",
                        severity="error"
                    )
                    return False
                    
                # Check sample campaign
                sample_campaign = next(iter(campaigns.values()))
                required_fields = ['campaign_id', 'provider', 'file_paths']
                
                missing_fields = [field for field in required_fields if field not in sample_campaign]
                if missing_fields:
                    self._log_result(
                        index_name, "sample_data",
                        success=False,
                        details=f"Missing fields in sample campaign: {missing_fields}",
                        severity="error"
                    )
                    return False
                    
            elif index_name == "spatial":
                files = data.get('files', {})
                if not files:
                    self._log_result(
                        index_name, "sample_data",
                        success=False,
                        details="No files found",
                        severity="error"
                    )
                    return False
                    
                # Check sample file entry
                sample_file = next(iter(files.values()))
                required_fields = ['bounds', 'crs']
                
                missing_fields = [field for field in required_fields if field not in sample_file]
                if missing_fields:
                    self._log_result(
                        index_name, "sample_data",
                        success=False,
                        details=f"Missing fields in sample file: {missing_fields}",
                        severity="error"
                    )
                    return False
                    
            self._log_result(
                index_name, "sample_data",
                success=True,
                details="Sample data integrity validated"
            )
            return True
            
        except Exception as e:
            self._log_result(
                index_name, "sample_data",
                success=False,
                details=f"Sample validation error: {e}",
                severity="error"
            )
            return False
            
    def validate_single_index(self, index_name: str) -> bool:
        """Validate a single index file comprehensively"""
        s3_key = self.indexes_to_validate.get(index_name)
        if not s3_key:
            self._log_result(
                index_name, "validation",
                success=False,
                details="Index not configured for validation",
                severity="warning"
            )
            return False
            
        print(f"\nValidating {index_name} index ({s3_key})...")
        
        # Step 1: Check existence
        if not self.validate_index_existence(index_name, s3_key):
            return False
            
        # Step 2: Validate JSON structure
        json_valid, data = self.validate_json_structure(index_name, s3_key)
        if not json_valid:
            return False
            
        # Step 3: Schema compliance
        schema_valid = self.validate_schema_compliance(index_name, data)
        
        # Step 4: Data freshness
        freshness_valid = self.validate_data_freshness(index_name, data)
        
        # Step 5: Data consistency
        consistency_valid = self.validate_data_consistency(index_name, data)
        
        # Step 6: Sample data integrity
        sample_valid = self.validate_sample_data_integrity(index_name, data)
        
        # Overall success
        overall_success = schema_valid and consistency_valid and sample_valid
        
        return overall_success
        
    def generate_validation_report(self) -> Dict[str, Any]:
        """Generate comprehensive validation report"""
        total_checks = len(self.validation_results)
        successful_checks = sum(1 for r in self.validation_results if r.success)
        
        # Group by severity
        by_severity = {}
        for result in self.validation_results:
            severity = result.severity
            if severity not in by_severity:
                by_severity[severity] = []
            by_severity[severity].append(result)
            
        # Group by index
        by_index = {}
        for result in self.validation_results:
            index = result.index_name
            if index not in by_index:
                by_index[index] = []
            by_index[index].append(result)
            
        report = {
            "summary": {
                "validation_timestamp": datetime.utcnow().isoformat(),
                "total_checks": total_checks,
                "successful_checks": successful_checks,
                "success_rate": round(successful_checks / total_checks * 100, 1) if total_checks > 0 else 0,
                "indexes_validated": len(by_index),
                "overall_status": "pass" if successful_checks == total_checks else "fail"
            },
            "severity_breakdown": {
                severity: len(results) for severity, results in by_severity.items()
            },
            "index_results": {},
            "failed_checks": [],
            "recommendations": []
        }
        
        # Index-specific results
        for index_name, results in by_index.items():
            index_success = all(r.success for r in results)
            report["index_results"][index_name] = {
                "status": "pass" if index_success else "fail",
                "checks_run": len(results),
                "checks_passed": sum(1 for r in results if r.success)
            }
            
        # Failed checks
        failed_checks = [r for r in self.validation_results if not r.success]
        report["failed_checks"] = [
            {
                "index": r.index_name,
                "check": r.check_name,
                "severity": r.severity,
                "details": r.details
            }
            for r in failed_checks
        ]
        
        # Generate recommendations
        critical_failures = [r for r in failed_checks if r.severity == "critical"]
        error_failures = [r for r in failed_checks if r.severity == "error"]
        
        if critical_failures:
            report["recommendations"].append({
                "priority": "CRITICAL",
                "action": "Fix critical index failures before deployment",
                "details": f"{len(critical_failures)} critical issues found"
            })
            
        if error_failures:
            report["recommendations"].append({
                "priority": "HIGH",
                "action": "Address index errors to ensure reliability",
                "details": f"{len(error_failures)} error-level issues found"
            })
            
        if report["summary"]["success_rate"] < 90:
            report["recommendations"].append({
                "priority": "MEDIUM",
                "action": "Improve index quality and validation coverage",
                "details": f"Success rate ({report['summary']['success_rate']}%) below 90% threshold"
            })
            
        return report
        
    def run_validation_suite(self) -> bool:
        """Run complete S3 index validation suite"""
        print("Starting S3 Index Validation Suite...")
        print(f"Target bucket: s3://{self.bucket_name}")
        print(f"Indexes to validate: {list(self.indexes_to_validate.keys())}")
        print(f"Validation timestamp: {datetime.utcnow().isoformat()}")
        
        overall_success = True
        
        # Validate each index
        for index_name in self.indexes_to_validate.keys():
            try:
                success = self.validate_single_index(index_name)
                if not success:
                    overall_success = False
            except Exception as e:
                print(f"Critical error validating {index_name}: {e}")
                overall_success = False
                
        # Generate report
        report = self.generate_validation_report()
        
        # Display summary
        print(f"\n=== Validation Summary ===")
        print(f"Indexes validated: {report['summary']['indexes_validated']}")
        print(f"Checks run: {report['summary']['total_checks']}")
        print(f"Success rate: {report['summary']['success_rate']}%")
        print(f"Overall status: {report['summary']['overall_status'].upper()}")
        
        if report["failed_checks"]:
            print(f"\nFailed checks: {len(report['failed_checks'])}")
            for failure in report["failed_checks"]:
                print(f"  [{failure['severity'].upper()}] {failure['index']}/{failure['check']}: {failure['details']}")
                
        if report["recommendations"]:
            print(f"\nRecommendations:")
            for rec in report["recommendations"]:
                print(f"  [{rec['priority']}] {rec['action']}: {rec['details']}")
                
        return overall_success

def main():
    """Main entry point for S3 index validation"""
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("""
S3 Index Validation Script

Usage:
    python scripts/validate_s3_indexes.py [--json] [--index INDEX_NAME]

Options:
    --json                Output results in JSON format
    --index INDEX_NAME    Validate specific index only (campaign, spatial, tiled, nz_spatial)
    --help               Show this help message

Environment Variables:
    S3_INDEX_BUCKET           - S3 bucket name (default: road-engineering-elevation-data)
    S3_CAMPAIGN_INDEX_KEY     - Campaign index S3 key
    S3_SPATIAL_INDEX_KEY      - Spatial index S3 key
    S3_TILED_INDEX_KEY        - Tiled index S3 key
    S3_NZ_INDEX_KEY          - New Zealand index S3 key

Exit Codes:
    0 - All validations passed
    1 - Some validations failed
    2 - Critical validation errors
    3 - Script execution error

CI/CD Integration Example:
    # Validate before deployment
    python scripts/validate_s3_indexes.py || exit 1
    
    # Scheduled monitoring (daily)
    python scripts/validate_s3_indexes.py --json > validation_report.json
        """)
        return
        
    try:
        validator = S3IndexValidator()
        
        # Check for specific index validation
        if "--index" in sys.argv:
            index_pos = sys.argv.index("--index")
            if index_pos + 1 < len(sys.argv):
                index_name = sys.argv[index_pos + 1]
                if index_name in validator.indexes_to_validate:
                    success = validator.validate_single_index(index_name)
                    report = validator.generate_validation_report()
                else:
                    print(f"Unknown index: {index_name}")
                    print(f"Available indexes: {list(validator.indexes_to_validate.keys())}")
                    sys.exit(3)
            else:
                print("--index option requires index name")
                sys.exit(3)
        else:
            # Run full validation suite
            success = validator.run_validation_suite()
            report = validator.generate_validation_report()
            
        # JSON output option
        if "--json" in sys.argv:
            print(json.dumps(report, indent=2, default=str))
            
        # Exit with appropriate code
        if success:
            sys.exit(0)
        elif any(r.severity == "critical" for r in validator.validation_results):
            sys.exit(2)  # Critical issues
        else:
            sys.exit(1)  # Some failures
            
    except KeyboardInterrupt:
        print("\nValidation interrupted by user")
        sys.exit(3)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(3)

if __name__ == "__main__":
    main()