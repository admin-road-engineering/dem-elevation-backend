#!/usr/bin/env python3
"""
Automated DEM Source Addition Script
Implements the complete protocol for seamlessly adding new DEM sources
"""
import json
import sys
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple
import logging

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DEMSourceManager:
    """
    Automated manager for adding new DEM sources following the complete protocol
    """
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.env_file = self.project_root / ".env"
        self.spatial_config = self.project_root / "config" / "dem_sources.json"
        self.backup_dir = self.project_root / "config" / "backups"
        self.backup_dir.mkdir(exist_ok=True)
        
    def add_new_sources_complete_protocol(self, new_sources: List[Dict]) -> Dict:
        """
        Complete protocol for adding new DEM sources
        
        Args:
            new_sources: List of source dictionaries with keys:
                - id: Source identifier
                - name: Human readable name
                - path: S3 path or API path
                - crs: Coordinate reference system
                - resolution_m: Resolution in meters
                - bounds: Geographic bounds dict with min_lat, max_lat, min_lon, max_lon
                - provider: Data provider
                - data_type: Type of elevation data
                - priority: Priority (1=highest, 3=lowest)
        """
        
        results = {
            "success": False,
            "steps_completed": [],
            "errors": [],
            "validation_results": {},
            "backup_files": []
        }
        
        try:
            # Phase 1: Discovery and Validation
            logger.info("Phase 1: Discovery and Validation")
            
            # 1.1 Validate new sources exist in S3
            logger.info("Validating new sources exist in S3...")
            validation_results = self._validate_sources_exist(new_sources)
            results["validation_results"] = validation_results
            
            if not validation_results["all_valid"]:
                results["errors"].append(f"Invalid sources found: {validation_results['invalid_sources']}")
                return results
            
            results["steps_completed"].append("source_validation")
            
            # Phase 2: Configuration Updates
            logger.info("Phase 2: Configuration Updates")
            
            # 2.1 Backup current configurations
            logger.info("Creating configuration backups...")
            backup_files = self._create_backups()
            results["backup_files"] = backup_files
            results["steps_completed"].append("backup_creation")
            
            # 2.2 Update .env file
            logger.info("Updating .env configuration...")
            self._update_env_file(new_sources)
            results["steps_completed"].append("env_file_update")
            
            # 2.3 Update spatial selector configuration
            logger.info("Updating spatial selector configuration...")
            self._update_spatial_config(new_sources)
            results["steps_completed"].append("spatial_config_update")
            
            # Phase 3: Validation
            logger.info("Phase 3: Validation")
            
            # 3.1 Validate configuration syntax
            logger.info("Validating configuration syntax...")
            syntax_valid = self._validate_config_syntax()
            if not syntax_valid:
                results["errors"].append("Configuration syntax validation failed")
                return results
            
            results["steps_completed"].append("syntax_validation")
            
            # 3.2 Test geographic coverage
            logger.info("Testing geographic coverage...")
            coverage_results = self._test_geographic_coverage()
            results["coverage_test"] = coverage_results
            results["steps_completed"].append("coverage_testing")
            
            results["success"] = True
            logger.info("✅ All phases completed successfully!")
            
            # Provide next steps
            results["next_steps"] = [
                "Restart uvicorn server: uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload",
                "Test key coordinates with the new sources",
                "Run monitoring: python scripts/source_monitoring.py",
                "Set up automated daily checks"
            ]
            
        except Exception as e:
            logger.error(f"Error in protocol execution: {e}")
            results["errors"].append(str(e))
            
            # Attempt rollback if backups exist
            if results["backup_files"]:
                logger.info("Attempting rollback to previous configuration...")
                self._rollback_changes(results["backup_files"])
                results["rollback_attempted"] = True
        
        return results
    
    def _validate_sources_exist(self, new_sources: List[Dict]) -> Dict:
        """Validate that new sources actually exist in S3"""
        try:
            from config import Settings
            import boto3
            
            settings = Settings()
            s3 = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_DEFAULT_REGION
            )
            
            validation_results = {
                "all_valid": True,
                "valid_sources": [],
                "invalid_sources": [],
                "validation_details": {}
            }
            
            for source in new_sources:
                source_id = source["id"]
                path = source["path"]
                
                if path.startswith("s3://road-engineering-elevation-data/"):
                    # Validate S3 source
                    s3_path = path.replace("s3://road-engineering-elevation-data/", "")
                    
                    try:
                        response = s3.list_objects_v2(
                            Bucket=settings.AWS_S3_BUCKET_NAME,
                            Prefix=s3_path,
                            MaxKeys=5
                        )
                        
                        file_count = len([obj for obj in response.get('Contents', []) if obj['Key'].endswith('.tif')])
                        
                        if file_count > 0 or 'CommonPrefixes' in response:
                            validation_results["valid_sources"].append(source_id)
                            validation_results["validation_details"][source_id] = f"Found {file_count} files"
                        else:
                            validation_results["invalid_sources"].append(source_id)
                            validation_results["validation_details"][source_id] = "No files found"
                            validation_results["all_valid"] = False
                            
                    except Exception as e:
                        validation_results["invalid_sources"].append(source_id)
                        validation_results["validation_details"][source_id] = f"Error: {e}"
                        validation_results["all_valid"] = False
                        
                elif path.startswith("api://"):
                    # API sources are assumed valid for now
                    validation_results["valid_sources"].append(source_id)
                    validation_results["validation_details"][source_id] = "API source (not validated)"
                    
                else:
                    validation_results["invalid_sources"].append(source_id)
                    validation_results["validation_details"][source_id] = "Unknown path type"
                    validation_results["all_valid"] = False
            
            return validation_results
            
        except Exception as e:
            return {
                "all_valid": False,
                "error": str(e),
                "valid_sources": [],
                "invalid_sources": [s["id"] for s in new_sources]
            }
    
    def _create_backups(self) -> List[str]:
        """Create backups of current configuration files"""
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_files = []
        
        # Backup .env file
        if self.env_file.exists():
            backup_env = self.backup_dir / f".env.backup_{timestamp}"
            backup_env.write_text(self.env_file.read_text())
            backup_files.append(str(backup_env))
        
        # Backup spatial config
        if self.spatial_config.exists():
            backup_spatial = self.backup_dir / f"dem_sources.json.backup_{timestamp}"
            backup_spatial.write_text(self.spatial_config.read_text())
            backup_files.append(str(backup_spatial))
        
        return backup_files
    
    def _update_env_file(self, new_sources: List[Dict]):
        """Update .env file with new DEM sources"""
        from config import Settings
        
        # Load current settings
        settings = Settings()
        current_sources = settings.DEM_SOURCES.copy()
        
        # Add new sources to current sources
        for source in new_sources:
            current_sources[source["id"]] = {
                "path": source["path"],
                "layer": None,
                "crs": source["crs"],
                "description": source.get("name", f"{source['provider']} {source.get('resolution_m', 'Unknown')}m DEM")
            }
        
        # Read current .env content
        env_content = self.env_file.read_text()
        
        # Replace DEM_SOURCES line
        new_dem_sources_line = f'DEM_SOURCES={json.dumps(current_sources)}'
        
        # Update the content
        lines = env_content.split('\n')
        for i, line in enumerate(lines):
            if line.startswith('DEM_SOURCES='):
                lines[i] = new_dem_sources_line
                break
        
        # Write back to file
        self.env_file.write_text('\n'.join(lines))
    
    def _update_spatial_config(self, new_sources: List[Dict]):
        """Update spatial selector configuration file"""
        
        # Load current spatial config
        with open(self.spatial_config, 'r') as f:
            config = json.load(f)
        
        # Add new sources to elevation_sources
        for source in new_sources:
            spatial_source = {
                "id": source["id"],
                "name": source["name"],
                "source_type": "s3" if source["path"].startswith("s3://") else "api",
                "path": source["path"],
                "crs": source["crs"],
                "resolution_m": source["resolution_m"],
                "data_type": source.get("data_type", "DEM"),
                "provider": source["provider"],
                "priority": source.get("priority", 1),
                "bounds": {
                    "type": "bbox",
                    "min_lat": source["bounds"]["min_lat"],
                    "max_lat": source["bounds"]["max_lat"],
                    "min_lon": source["bounds"]["min_lon"],
                    "max_lon": source["bounds"]["max_lon"]
                },
                "cost_per_query": source.get("cost_per_query", 0.001),
                "accuracy": source.get("accuracy", "±1m"),
                "enabled": True,
                "visible_in_coverage": True,
                "metadata": {
                    "capture_date": source.get("capture_date", "Unknown"),
                    "point_density": source.get("point_density", "Unknown"),
                    "vertical_datum": source.get("vertical_datum", "AHD"),
                    "color": source.get("color", "#00AA00"),
                    "opacity": source.get("opacity", 0.4)
                }
            }
            
            config["elevation_sources"].append(spatial_source)
        
        # Write updated config
        with open(self.spatial_config, 'w') as f:
            json.dump(config, f, indent=2)
    
    def _validate_config_syntax(self) -> bool:
        """Validate that configuration files have valid syntax"""
        try:
            # Validate .env file can be loaded
            from config import Settings
            settings = Settings()
            
            # Validate spatial config is valid JSON
            with open(self.spatial_config, 'r') as f:
                json.load(f)
            
            return True
            
        except Exception as e:
            logger.error(f"Configuration syntax validation failed: {e}")
            return False
    
    def _test_geographic_coverage(self) -> Dict:
        """Test geographic coverage with key coordinates"""
        test_coordinates = {
            "brisbane": (-27.4698, 153.0251),
            "melbourne": (-37.8136, 144.9631),
            "sydney": (-33.8688, 151.2093),
            "bendigo": (-36.7570, 144.2794)
        }
        
        coverage_results = {
            "tested_locations": [],
            "successful_tests": 0,
            "failed_tests": 0,
            "details": {}
        }
        
        try:
            from dem_service import DEMService
            from config import Settings
            
            settings = Settings()
            dem_service = DEMService(settings)
            
            for location, (lat, lon) in test_coordinates.items():
                try:
                    elevation, source_used, error = dem_service.get_elevation_at_point(lat, lon, auto_select=True)
                    
                    coverage_results["tested_locations"].append(location)
                    
                    if elevation is not None:
                        coverage_results["successful_tests"] += 1
                        coverage_results["details"][location] = {
                            "elevation": elevation,
                            "source": source_used,
                            "status": "success"
                        }
                    else:
                        coverage_results["failed_tests"] += 1
                        coverage_results["details"][location] = {
                            "elevation": None,
                            "source": source_used,
                            "error": error,
                            "status": "failed"
                        }
                        
                except Exception as e:
                    coverage_results["failed_tests"] += 1
                    coverage_results["details"][location] = {
                        "error": str(e),
                        "status": "error"
                    }
            
            # Cleanup
            if hasattr(dem_service, 'close'):
                dem_service.close()
                
        except Exception as e:
            coverage_results["error"] = str(e)
        
        return coverage_results
    
    def _rollback_changes(self, backup_files: List[str]):
        """Rollback changes using backup files"""
        try:
            for backup_file in backup_files:
                backup_path = Path(backup_file)
                
                if ".env.backup_" in backup_file:
                    self.env_file.write_text(backup_path.read_text())
                elif "dem_sources.json.backup_" in backup_file:
                    self.spatial_config.write_text(backup_path.read_text())
                    
            logger.info("✅ Rollback completed successfully")
            
        except Exception as e:
            logger.error(f"❌ Rollback failed: {e}")

def main():
    """Main function for interactive source addition"""
    
    print("🗺️  DEM Source Addition Tool")
    print("=" * 50)
    
    # Example usage
    example_new_sources = [
        {
            "id": "example_new_qld",
            "name": "Example Queensland Region LiDAR",
            "path": "s3://road-engineering-elevation-data/example-elvis/elevation/1m-dem/z56/",
            "crs": "EPSG:32756",
            "resolution_m": 1,
            "bounds": {
                "min_lat": -28.0,
                "max_lat": -26.0,
                "min_lon": 151.0,
                "max_lon": 153.0
            },
            "provider": "Example Provider",
            "data_type": "LiDAR",
            "priority": 1,
            "capture_date": "2023",
            "point_density": "4 points/m²",
            "vertical_datum": "AHD"
        }
    ]
    
    print("Example new source format:")
    print(json.dumps(example_new_sources[0], indent=2))
    print()
    print("To add new sources:")
    print("1. Create source definitions following the example format")
    print("2. Use manager.add_new_sources_complete_protocol(new_sources)")
    print("3. Follow the validation results and next steps")
    print()
    print("For immediate use, run the discovery tools:")
    print("  python scripts/s3_bucket_scanner.py")
    print("  python scripts/quick_source_discovery.py")

if __name__ == "__main__":
    main()