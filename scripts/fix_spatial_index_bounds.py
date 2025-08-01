#!/usr/bin/env python3
"""
Fix Spatial Index Coordinate Bounds
Updates existing spatial index with correct coordinate bounds using UTM converter
"""
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Optional

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))
from utm_converter import DEMFilenameParser

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)8s | %(message)s')
logger = logging.getLogger(__name__)

class SpatialIndexBoundsFixer:
    """Fix coordinate bounds in existing spatial index"""
    
    def __init__(self):
        self.config_dir = Path(__file__).parent.parent / "config"
        self.spatial_index_file = self.config_dir / "spatial_index.json"
        self.parser = DEMFilenameParser()
        self.fixes_applied = 0
        self.fixes_failed = 0
        
    def fix_spatial_index_bounds(self):
        """Fix coordinate bounds in the existing spatial index"""
        logger.info("🔧 Fixing coordinate bounds in spatial index...")
        
        # Load existing spatial index
        if not self.spatial_index_file.exists():
            logger.error(f"Spatial index file not found: {self.spatial_index_file}")
            return False
            
        with open(self.spatial_index_file, 'r') as f:
            spatial_index = json.load(f)
            
        logger.info(f"📊 Loaded spatial index with {spatial_index.get('file_count', 0)} files")
        
        # Fix bounds for each UTM zone
        for zone_name, zone_data in spatial_index.get("utm_zones", {}).items():
            logger.info(f"🗺️ Processing UTM zone {zone_name}...")
            
            files = zone_data.get("files", [])
            fixed_count = 0
            
            for file_info in files:
                filename = file_info.get("filename", "")
                current_bounds = file_info.get("bounds", {})
                
                # Check if bounds need fixing (placeholder values)
                if (current_bounds.get("min_lat") == 1.5 and 
                    current_bounds.get("max_lat") == 2.5):
                    
                    # Extract correct bounds using UTM converter
                    correct_bounds = self.parser.extract_bounds_from_filename(filename)
                    
                    if correct_bounds:
                        file_info["bounds"] = correct_bounds
                        fixed_count += 1
                        self.fixes_applied += 1
                        
                        if fixed_count <= 3:  # Log first few fixes per zone
                            logger.info(f"  ✅ Fixed {filename}: lat {correct_bounds['min_lat']:.2f}-{correct_bounds['max_lat']:.2f}")
                    else:
                        self.fixes_failed += 1
                        logger.warning(f"  ❌ Could not fix bounds for {filename}")
            
            logger.info(f"  📝 Fixed {fixed_count}/{len(files)} files in zone {zone_name}")
            
            # Recalculate zone coverage bounds
            if files:
                zone_data["coverage_bounds"] = self._calculate_coverage_bounds(files)
        
        # Update file count and save
        spatial_index["file_count"] = sum(len(zone_data.get("files", [])) 
                                        for zone_data in spatial_index.get("utm_zones", {}).values())
        
        # Backup original file
        backup_file = self.spatial_index_file.with_suffix('.json.backup')
        if not backup_file.exists():
            with open(backup_file, 'w') as f:
                json.dump(spatial_index, f, indent=2)
            logger.info(f"💾 Created backup: {backup_file}")
        
        # Save fixed spatial index
        with open(self.spatial_index_file, 'w') as f:
            json.dump(spatial_index, f, indent=2)
            
        logger.info(f"🎯 Bounds fixing complete!")
        logger.info(f"  ✅ Fixed: {self.fixes_applied} files")
        logger.info(f"  ❌ Failed: {self.fixes_failed} files")
        logger.info(f"  💾 Saved to: {self.spatial_index_file}")
        
        return True
    
    def _calculate_coverage_bounds(self, files: list) -> Optional[Dict]:
        """Calculate overall coverage bounds for a set of files"""
        if not files:
            return None
            
        valid_files = [f for f in files if f.get("bounds") and 
                      f["bounds"].get("min_lat") != 1.5]  # Exclude placeholder bounds
        
        if not valid_files:
            return None
            
        min_lat = min(f["bounds"]["min_lat"] for f in valid_files)
        max_lat = max(f["bounds"]["max_lat"] for f in valid_files)
        min_lon = min(f["bounds"]["min_lon"] for f in valid_files)
        max_lon = max(f["bounds"]["max_lon"] for f in valid_files)
        
        return {
            "min_lat": min_lat,
            "max_lat": max_lat,
            "min_lon": min_lon,
            "max_lon": max_lon
        }
    
    def test_coordinate_lookup(self, lat: float, lon: float):
        """Test coordinate lookup with fixed bounds"""
        logger.info(f"🧪 Testing coordinate lookup for ({lat}, {lon})...")
        
        with open(self.spatial_index_file, 'r') as f:
            spatial_index = json.load(f)
        
        matches = []
        for zone_name, zone_data in spatial_index.get("utm_zones", {}).items():
            for file_info in zone_data.get("files", []):
                bounds = file_info.get("bounds", {})
                if (bounds.get("min_lat", 999) <= lat <= bounds.get("max_lat", -999) and
                    bounds.get("min_lon", 999) <= lon <= bounds.get("max_lon", -999)):
                    matches.append({
                        "file": file_info.get("file", ""),
                        "filename": file_info.get("filename", ""),
                        "bounds": bounds
                    })
        
        logger.info(f"🎯 Found {len(matches)} matching files:")
        for i, match in enumerate(matches[:3]):  # Show first 3 matches
            logger.info(f"  {i+1}. {match['filename']}")
            logger.info(f"     Bounds: lat {match['bounds']['min_lat']:.2f}-{match['bounds']['max_lat']:.2f}")
        
        return matches

def main():
    """Main function"""
    import sys
    
    fixer = SpatialIndexBoundsFixer()
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Test coordinate lookup
        fixer.test_coordinate_lookup(-27.4698, 153.0251)  # Brisbane
        fixer.test_coordinate_lookup(-33.8688, 151.2093)  # Sydney
    else:
        # Fix bounds
        success = fixer.fix_spatial_index_bounds()
        if success:
            logger.info("🎉 Spatial index bounds fixing completed successfully!")
        else:
            logger.error("❌ Spatial index bounds fixing failed!")
            sys.exit(1)

if __name__ == "__main__":
    main()