#!/usr/bin/env python3
"""
Fix Brisbane File Bounds
Specifically fixes Brisbane files that are using Queensland fallback bounds
"""
import json
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))
from utm_converter import DEMFilenameParser

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)8s | %(message)s')
logger = logging.getLogger(__name__)

class BrisbaneBoundsFixer:
    """Fix Brisbane file bounds that are using regional fallback bounds"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.config_dir = self.project_root / "config"
        self.spatial_index_file = self.config_dir / "spatial_index.json"
        self.parser = DEMFilenameParser()
        
    def fix_brisbane_bounds(self):
        """Fix Brisbane files using Queensland fallback bounds"""
        logger.info("🔧 Fixing Brisbane file bounds with precise UTM calculation...")
        
        # Load existing spatial index
        if not self.spatial_index_file.exists():
            logger.error(f"Spatial index file not found: {self.spatial_index_file}")
            return False
            
        with open(self.spatial_index_file, 'r') as f:
            spatial_index = json.load(f)
        
        # Get Brisbane files from z56 zone
        z56_files = spatial_index.get("utm_zones", {}).get("z56", {}).get("files", [])
        brisbane_files = [
            f for f in z56_files 
            if "brisbane" in f.get("filename", "").lower()
        ]
        
        if not brisbane_files:
            logger.error("No Brisbane files found in z56 zone")
            return False
            
        logger.info(f"Found {len(brisbane_files)} Brisbane files to check")
        
        fixed_count = 0
        
        for file_info in brisbane_files:
            filename = file_info.get("filename", "")
            current_bounds = file_info.get("bounds", {})
            
            # Check if using Queensland fallback bounds (min_lat: -29.2, max_lat: -9.0)
            is_qld_fallback = (abs(current_bounds.get("min_lat", 0) - (-29.2)) < 0.1 and 
                              abs(current_bounds.get("max_lat", 0) - (-9.0)) < 0.1)
            
            if is_qld_fallback:
                # Calculate precise bounds using UTM converter
                precise_bounds = self.parser.extract_bounds_from_filename(filename)
                
                if precise_bounds:
                    # Validate the bounds are reasonable for Brisbane
                    lat_range = precise_bounds['max_lat'] - precise_bounds['min_lat']
                    lon_range = precise_bounds['max_lon'] - precise_bounds['min_lon']
                    
                    # Brisbane should be around -27.x latitude, 153.x longitude
                    # 1km tiles should have ~0.009 degree range
                    if (-28 < precise_bounds['min_lat'] < -26 and 
                        152 < precise_bounds['min_lon'] < 154 and
                        0.005 < lat_range < 0.02 and 0.005 < lon_range < 0.02):
                        
                        file_info["bounds"] = precise_bounds
                        fixed_count += 1
                        
                        if fixed_count <= 5:  # Log first 5 fixes
                            logger.info(f"  ✅ Fixed {filename}")
                            logger.info(f"     Old: lat {current_bounds.get('min_lat', 0):.2f}-{current_bounds.get('max_lat', 0):.2f}")
                            logger.info(f"     New: lat {precise_bounds['min_lat']:.4f}-{precise_bounds['max_lat']:.4f}")
                    else:
                        logger.warning(f"  ⚠️ Calculated bounds seem unreasonable for {filename}")
                        logger.warning(f"     Bounds: lat {precise_bounds['min_lat']:.4f}-{precise_bounds['max_lat']:.4f}")
                else:
                    logger.warning(f"  ❌ Could not calculate precise bounds for {filename}")
        
        if fixed_count > 0:
            # Recalculate zone coverage bounds
            zone_files = spatial_index["utm_zones"]["z56"]["files"]
            spatial_index["utm_zones"]["z56"]["coverage_bounds"] = self._calculate_coverage_bounds(zone_files)
            
            # Update total file count (should be same)
            spatial_index["file_count"] = sum(len(zone_data.get("files", [])) 
                                            for zone_data in spatial_index.get("utm_zones", {}).values())
            
            # Save updated spatial index
            with open(self.spatial_index_file, 'w') as f:
                json.dump(spatial_index, f, indent=2)
                
            logger.info(f"🎯 Brisbane bounds fixing complete!")
            logger.info(f"  ✅ Fixed: {fixed_count} Brisbane files")
            logger.info(f"  💾 Saved to: {self.spatial_index_file}")
        else:
            logger.info("✅ All Brisbane files already have precise bounds")
        
        return fixed_count > 0
    
    def _calculate_coverage_bounds(self, files: List[Dict]) -> Optional[Dict]:
        """Calculate overall coverage bounds for a set of files"""
        if not files:
            return None
            
        # Exclude fallback bounds from coverage calculation
        valid_files = []
        for f in files:
            bounds = f.get("bounds", {})
            min_lat = bounds.get("min_lat", 0)
            max_lat = bounds.get("max_lat", 0)
            
            # Skip Queensland fallback bounds and Australia-wide fallback bounds
            if not (abs(min_lat - (-29.2)) < 0.1 and abs(max_lat - (-9.0)) < 0.1) and \
               not (abs(min_lat - (-44.0)) < 0.1 and abs(max_lat - (-9.0)) < 0.1):
                valid_files.append(f)
        
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
    
    def test_brisbane_lookup(self):
        """Test Brisbane coordinate lookup after fixing bounds"""
        logger.info("🧪 Testing Brisbane coordinate lookup after bounds fix...")
        
        with open(self.spatial_index_file, 'r') as f:
            spatial_index = json.load(f)
        
        # Test Brisbane coordinates
        brisbane_coords = [
            (-27.4698, 153.0251, "Brisbane CBD"),
            (-27.3872, 153.1216, "Brisbane Airport"),
            (-27.5200, 153.0200, "South Brisbane"),
        ]
        
        for lat, lon, location in brisbane_coords:
            matches = []
            
            # Search through z56 zone for precise matches
            if "z56" in spatial_index.get("utm_zones", {}):
                for file_info in spatial_index["utm_zones"]["z56"]["files"]:
                    bounds = file_info.get("bounds", {})
                    
                    # Skip files with fallback bounds
                    min_lat = bounds.get("min_lat", 999)
                    max_lat = bounds.get("max_lat", -999)
                    
                    if not (abs(min_lat - (-29.2)) < 0.1 and abs(max_lat - (-9.0)) < 0.1) and \
                       not (abs(min_lat - (-44.0)) < 0.1 and abs(max_lat - (-9.0)) < 0.1):
                        if (min_lat <= lat <= max_lat and
                            bounds.get("min_lon", 999) <= lon <= bounds.get("max_lon", -999)):
                            matches.append(file_info)
            
            logger.info(f"📍 {location} ({lat}, {lon}): Found {len(matches)} precise matches")
            
            # Show Brisbane-specific files
            brisbane_matches = [m for m in matches if "brisbane" in m.get("filename", "").lower()]
            if brisbane_matches:
                best_match = brisbane_matches[0]
                bounds = best_match.get("bounds", {})
                logger.info(f"  🏙️ Brisbane file: {best_match.get('filename', '')}")
                logger.info(f"     Bounds: lat {bounds.get('min_lat', 0):.4f}-{bounds.get('max_lat', 0):.4f}")

def main():
    """Main function"""
    fixer = BrisbaneBoundsFixer()
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Test Brisbane lookup
        fixer.test_brisbane_lookup()
    else:
        # Fix Brisbane bounds
        success = fixer.fix_brisbane_bounds()
        if success:
            logger.info("🎉 Brisbane bounds fixing completed successfully!")
            # Test the lookup after fixing
            fixer.test_brisbane_lookup()
        else:
            logger.info("ℹ️ No Brisbane bounds needed fixing")
            # Test anyway to show current state
            fixer.test_brisbane_lookup()

if __name__ == "__main__":
    main()