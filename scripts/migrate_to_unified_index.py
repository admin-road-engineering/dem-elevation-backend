#!/usr/bin/env python3
"""
Migration Script: Legacy Indexes → Unified v2.0 Schema
Implements Gemini's validation with 10,000 coordinate test
"""
import json
import sys
import logging
import random
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import uuid

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from models.unified_spatial_models import (
    UnifiedSpatialIndex, SchemaMetadata, AustralianUTMCollection, 
    NewZealandCampaignCollection, FileEntry, CoverageBounds, CollectionMetadata
)
from handlers import CollectionHandlerRegistry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UnifiedIndexMigrator:
    """Migrates legacy Australian and NZ indexes to unified v2.0 schema"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.config_dir = self.project_root / "config"
        
        # Input files
        self.au_index_file = self.config_dir / "spatial_index.json"
        self.nz_index_file = self.config_dir / "nz_spatial_index.json"
        
        # Output file
        self.unified_index_file = self.config_dir / "unified_spatial_index_v2.json"
        
        # Validation
        self.validation_coordinates = []
        self.handler_registry = CollectionHandlerRegistry()
    
    def load_legacy_indexes(self) -> Tuple[Dict, Dict]:
        """Load both legacy spatial indexes"""
        logger.info("Loading legacy spatial indexes...")
        
        if not self.au_index_file.exists():
            raise FileNotFoundError(f"Australian index not found: {self.au_index_file}")
        if not self.nz_index_file.exists():
            raise FileNotFoundError(f"NZ index not found: {self.nz_index_file}")
        
        with open(self.au_index_file, 'r') as f:
            au_index = json.load(f)
        
        with open(self.nz_index_file, 'r') as f:
            nz_index = json.load(f)
        
        logger.info(f"Loaded AU index: {au_index.get('file_count', 0)} files")
        logger.info(f"Loaded NZ index: {nz_index.get('file_count', 0)} files")
        
        return au_index, nz_index
    
    def migrate_australian_index(self, au_index: Dict) -> List[AustralianUTMCollection]:
        """Convert Australian utm_zones to unified collections"""
        logger.info("Converting Australian UTM zones to collections...")
        
        collections = []
        
        for zone_name, zone_data in au_index.get("utm_zones", {}).items():
            # Extract UTM zone number
            utm_zone = int(zone_name.replace('z', ''))
            
            # Convert files
            files = []
            for file_info in zone_data.get("files", []):
                file_entry = FileEntry(
                    file=file_info["file"],
                    filename=file_info["filename"],
                    bounds=CoverageBounds(**file_info["bounds"]),
                    size_mb=file_info.get("size_mb", 0.0),
                    last_modified=file_info.get("last_modified", ""),
                    resolution=file_info.get("resolution", "1m"),
                    coordinate_system=file_info.get("coordinate_system", "GDA94"),
                    method=file_info.get("method", "utm_conversion")
                )
                files.append(file_entry)
            
            # Create collection
            collection = AustralianUTMCollection(
                id=str(uuid.uuid4()),
                utm_zone=utm_zone,
                state=self._extract_state_from_zone(zone_data),
                region=self._extract_region_from_zone(zone_data),
                files=files,
                coverage_bounds=CoverageBounds(**zone_data["coverage_bounds"]),
                file_count=len(files),
                metadata=CollectionMetadata(
                    source_bucket="road-engineering-elevation-data",
                    coordinate_system="GDA94",
                    original_path=zone_data.get("utm_zone_path", ""),
                    performance_note=f"UTM Zone {utm_zone}"
                )
            )
            
            collections.append(collection)
            logger.debug(f"Converted UTM zone {utm_zone}: {len(files)} files")
        
        logger.info(f"Converted {len(collections)} Australian collections")
        return collections
    
    def migrate_nz_index(self, nz_index: Dict) -> List[NewZealandCampaignCollection]:
        """Convert NZ campaigns to unified collections"""
        logger.info("Converting NZ campaigns to collections...")
        
        collections = []
        
        for campaign_name, campaign_data in nz_index.get("campaigns", {}).items():
            # Extract campaign details
            region = campaign_data.get("region", "unknown")
            survey = campaign_data.get("survey", campaign_name)
            raw_data_type = campaign_data.get("data_type", "DEM")
            
            # Map data types to valid literals
            if raw_data_type.upper() in ["DEM", "DSM"]:
                data_type = raw_data_type.upper()
            else:
                data_type = "UNKNOWN"
            
            # Extract years from survey name
            survey_years = self._extract_years_from_survey(survey)
            
            # Convert files
            files = []
            for file_info in campaign_data.get("files", []):
                file_entry = FileEntry(
                    file=file_info["file"],
                    filename=file_info["filename"],
                    bounds=CoverageBounds(**file_info["bounds"]),
                    size_mb=file_info.get("size_mb", 0.0),
                    last_modified=file_info.get("last_modified", ""),
                    resolution=file_info.get("resolution", "1m"),
                    coordinate_system=file_info.get("coordinate_system", "NZGD2000"),
                    method=file_info.get("method", "geotiff_extraction")
                )
                files.append(file_entry)
            
            # Create collection
            collection = NewZealandCampaignCollection(
                id=str(uuid.uuid4()),
                region=region,
                survey_name=survey,
                survey_years=survey_years,
                data_type=data_type,
                files=files,
                coverage_bounds=CoverageBounds(**campaign_data["coverage_bounds"]),
                file_count=len(files),
                metadata=CollectionMetadata(
                    source_bucket="nz-elevation",
                    coordinate_system="NZGD2000 / NZTM 2000",
                    original_campaign=campaign_name
                )
            )
            
            collections.append(collection)
            logger.debug(f"Converted campaign {campaign_name}: {len(files)} files")
        
        logger.info(f"Converted {len(collections)} NZ collections")
        return collections
    
    def generate_unified_index(self, dry_run: bool = False) -> UnifiedSpatialIndex:
        """Generate the unified spatial index"""
        logger.info("🔄 Generating unified spatial index v2.0...")
        
        # Load legacy indexes
        au_index, nz_index = self.load_legacy_indexes()
        
        # Migrate to new format
        au_collections = self.migrate_australian_index(au_index)
        nz_collections = self.migrate_nz_index(nz_index)
        
        all_collections = au_collections + nz_collections
        
        # Generate metadata
        countries = list(set(c.country for c in all_collections))
        collection_types = list(set(c.collection_type for c in all_collections))
        total_files = sum(c.file_count for c in all_collections)
        
        metadata = SchemaMetadata(
            total_collections=len(all_collections),
            total_files=total_files,
            countries=countries,
            collection_types=collection_types
        )
        
        # Create unified index
        unified_index = UnifiedSpatialIndex(
            schema_metadata=metadata,
            data_collections=all_collections
        )
        
        logger.info(f"✅ Generated unified index:")
        logger.info(f"   Collections: {len(all_collections)}")
        logger.info(f"   Total files: {total_files}")
        logger.info(f"   Countries: {countries}")
        logger.info(f"   Types: {collection_types}")
        
        if not dry_run:
            self._save_unified_index(unified_index)
        
        return unified_index
    
    def validate_migration(self, num_test_coords: int = 10000) -> bool:
        """Validate migration with coordinate comparison test"""
        logger.info(f"🧪 Starting migration validation with {num_test_coords} test coordinates...")
        
        # Load indexes
        au_index, nz_index = self.load_legacy_indexes()
        unified_index = self.load_unified_index()
        
        if not unified_index:
            logger.error("Unified index not found. Run migration first.")
            return False
        
        # Generate test coordinates
        test_coords = self._generate_test_coordinates(au_index, nz_index, num_test_coords)
        
        logger.info(f"Generated {len(test_coords)} test coordinates")
        
        mismatches = 0
        for i, (lat, lon) in enumerate(test_coords):
            if i % 1000 == 0:
                logger.info(f"Validated {i}/{len(test_coords)} coordinates...")
            
            # Test legacy system
            legacy_files = self._find_files_legacy(au_index, nz_index, lat, lon)
            
            # Test unified system
            unified_files = self._find_files_unified(unified_index, lat, lon)
            
            # Compare results
            if not self._compare_file_results(legacy_files, unified_files):
                mismatches += 1
                if mismatches <= 10:  # Log first 10 mismatches
                    logger.warning(f"Mismatch at ({lat}, {lon}): "
                                 f"legacy={len(legacy_files)}, unified={len(unified_files)}")
        
        success_rate = (len(test_coords) - mismatches) / len(test_coords) * 100
        
        if mismatches == 0:
            logger.info("✅ Migration validation PASSED: 100% coordinate matches")
            return True
        else:
            logger.error(f"❌ Migration validation FAILED: {mismatches} mismatches "
                        f"({success_rate:.1f}% success rate)")
            return False
    
    def _extract_state_from_zone(self, zone_data: Dict) -> str:
        """Extract state from zone data"""
        # Simple heuristic based on file paths
        files = zone_data.get("files", [])
        if files:
            file_path = files[0].get("file", "")
            if "qld" in file_path.lower():
                return "QLD"
            elif "nsw" in file_path.lower():
                return "NSW"
            elif "vic" in file_path.lower():
                return "VIC"
            elif "act" in file_path.lower():
                return "ACT"
        return "UNKNOWN"
    
    def _extract_region_from_zone(self, zone_data: Dict) -> Optional[str]:
        """Extract region from zone data"""
        files = zone_data.get("files", [])
        if files:
            file_path = files[0].get("file", "")
            if "brisbane" in file_path.lower():
                return "brisbane"
            elif "sydney" in file_path.lower():
                return "sydney"
        return None
    
    def _extract_years_from_survey(self, survey_name: str) -> List[int]:
        """Extract years from survey name"""
        import re
        years = re.findall(r'\b(19|20)\d{2}\b', survey_name)
        return [int(year) for year in years] if years else [2020]  # Default year
    
    def _generate_test_coordinates(self, au_index: Dict, nz_index: Dict, num_coords: int) -> List[Tuple[float, float]]:
        """Generate test coordinates from both indexes"""
        coords = []
        
        # Extract coordinates from AU files
        au_coords = []
        for zone_data in au_index.get("utm_zones", {}).values():
            for file_info in zone_data.get("files", [])[:50]:  # Limit per zone
                bounds = file_info.get("bounds", {})
                if bounds:
                    lat = (bounds["min_lat"] + bounds["max_lat"]) / 2
                    lon = (bounds["min_lon"] + bounds["max_lon"]) / 2
                    au_coords.append((lat, lon))
        
        # Extract coordinates from NZ files  
        nz_coords = []
        for campaign_data in nz_index.get("campaigns", {}).values():
            for file_info in campaign_data.get("files", [])[:20]:  # Limit per campaign
                bounds = file_info.get("bounds", {})
                if bounds:
                    lat = (bounds["min_lat"] + bounds["max_lat"]) / 2
                    lon = (bounds["min_lon"] + bounds["max_lon"]) / 2
                    nz_coords.append((lat, lon))
        
        # Sample coordinates
        all_coords = au_coords + nz_coords
        if len(all_coords) <= num_coords:
            coords = all_coords
        else:
            coords = random.sample(all_coords, num_coords)
        
        return coords
    
    def _find_files_legacy(self, au_index: Dict, nz_index: Dict, lat: float, lon: float) -> List[str]:
        """Find files using legacy logic"""
        files = []
        
        # AU logic
        for zone_data in au_index.get("utm_zones", {}).values():
            for file_info in zone_data.get("files", []):
                bounds = file_info.get("bounds", {})
                if (bounds.get("min_lat", 0) <= lat <= bounds.get("max_lat", 0) and
                    bounds.get("min_lon", 0) <= lon <= bounds.get("max_lon", 0)):
                    files.append(file_info["filename"])
        
        # NZ logic
        for campaign_data in nz_index.get("campaigns", {}).values():
            for file_info in campaign_data.get("files", []):
                bounds = file_info.get("bounds", {})
                if (bounds.get("min_lat", 0) <= lat <= bounds.get("max_lat", 0) and
                    bounds.get("min_lon", 0) <= lon <= bounds.get("max_lon", 0)):
                    files.append(file_info["filename"])
        
        return files
    
    def _find_files_unified(self, unified_index: UnifiedSpatialIndex, lat: float, lon: float) -> List[str]:
        """Find files using unified logic"""
        files = []
        
        for collection in unified_index.data_collections:
            collection_files = self.handler_registry.find_files_for_coordinate(collection, lat, lon)
            files.extend([f.filename for f in collection_files])
        
        return files
    
    def _compare_file_results(self, legacy_files: List[str], unified_files: List[str]) -> bool:
        """Compare file results (order-independent)"""
        return set(legacy_files) == set(unified_files)
    
    def _save_unified_index(self, unified_index: UnifiedSpatialIndex):
        """Save unified index to file"""
        with open(self.unified_index_file, 'w') as f:
            json.dump(unified_index.dict(), f, indent=2, default=str)
        
        logger.info(f"💾 Saved unified index to: {self.unified_index_file}")
    
    def load_unified_index(self) -> Optional[UnifiedSpatialIndex]:
        """Load existing unified index"""
        if not self.unified_index_file.exists():
            return None
        
        try:
            with open(self.unified_index_file, 'r') as f:
                data = json.load(f)
            return UnifiedSpatialIndex(**data)
        except Exception as e:
            logger.error(f"Failed to load unified index: {e}")
            return None

def main():
    """Main function"""
    migrator = UnifiedIndexMigrator()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "generate":
            migrator.generate_unified_index()
        elif command == "dry-run":
            migrator.generate_unified_index(dry_run=True)
        elif command == "validate":
            num_coords = 10000
            if len(sys.argv) > 2:
                num_coords = int(sys.argv[2])
            success = migrator.validate_migration(num_coords)
            sys.exit(0 if success else 1)
        else:
            print("Unknown command. Use: generate, dry-run, or validate")
    else:
        print("[MIGRATOR] Unified Index Migration Tool v2.0")
        print("Migrates legacy AU and NZ indexes to unified schema")
        print("Commands:")
        print("  generate  - Generate unified index")
        print("  dry-run   - Generate without saving")
        print("  validate  - Validate with 10k coordinate test")
        print()
        print("Example: python scripts/migrate_to_unified_index.py generate")

if __name__ == "__main__":
    main()