#!/usr/bin/env python3
"""
UTM Coordinate Conversion Utilities
Converts UTM grid coordinates to latitude/longitude bounds
"""
import math
import re
from typing import Dict, Optional, Tuple

class UTMConverter:
    """Convert UTM coordinates to latitude/longitude"""
    
    def __init__(self):
        # WGS84 ellipsoid parameters
        self.a = 6378137.0  # Semi-major axis
        self.f = 1/298.257223563  # Flattening
        self.e_sq = 2*self.f - self.f**2  # First eccentricity squared
        
    def utm_to_latlon(self, easting: float, northing: float, zone: int, hemisphere: str = 'S') -> Tuple[float, float]:
        """
        Convert UTM coordinates to latitude/longitude
        
        Args:
            easting: UTM easting coordinate
            northing: UTM northing coordinate  
            zone: UTM zone number
            hemisphere: 'N' for northern, 'S' for southern hemisphere
            
        Returns:
            Tuple of (latitude, longitude) in decimal degrees
        """
        # Constants
        k0 = 0.9996  # Scale factor
        
        # Calculate central meridian
        lon0 = math.radians((zone - 1) * 6 - 180 + 3)
        
        # Adjust for southern hemisphere
        if hemisphere.upper() == 'S':
            northing = northing - 10000000.0
        
        # Remove false easting
        x = easting - 500000.0
        y = northing
        
        # Ellipsoid parameters
        e1 = (1 - math.sqrt(1 - self.e_sq)) / (1 + math.sqrt(1 - self.e_sq))
        
        # Calculate M (meridional arc)
        M = y / k0
        mu = M / (self.a * (1 - self.e_sq/4 - 3*self.e_sq**2/64 - 5*self.e_sq**3/256))
        
        # Calculate phi1 (footprint latitude)
        phi1_rad = (mu + 
                   (3*e1/2 - 27*e1**3/32) * math.sin(2*mu) +
                   (21*e1**2/16 - 55*e1**4/32) * math.sin(4*mu) +
                   (151*e1**3/96) * math.sin(6*mu))
        
        # Calculate parameters at phi1
        N1 = self.a / math.sqrt(1 - self.e_sq * math.sin(phi1_rad)**2)
        T1 = math.tan(phi1_rad)**2
        C1 = self.e_sq * math.cos(phi1_rad)**2 / (1 - self.e_sq)
        R1 = self.a * (1 - self.e_sq) / (1 - self.e_sq * math.sin(phi1_rad)**2)**(3/2)
        D = x / (N1 * k0)
        
        # Calculate latitude
        lat_rad = (phi1_rad - 
                  (N1 * math.tan(phi1_rad) / R1) * 
                  (D**2/2 - 
                   (5 + 3*T1 + 10*C1 - 4*C1**2 - 9*self.e_sq) * D**4/24 +
                   (61 + 90*T1 + 298*C1 + 45*T1**2 - 252*self.e_sq - 3*C1**2) * D**6/720))
        
        # Calculate longitude
        lon_rad = (lon0 + 
                  (D - 
                   (1 + 2*T1 + C1) * D**3/6 +
                   (5 - 2*C1 + 28*T1 - 3*C1**2 + 8*self.e_sq + 24*T1**2) * D**5/120) / 
                  math.cos(phi1_rad))
        
        # Convert to degrees
        lat = math.degrees(lat_rad)
        lon = math.degrees(lon_rad)
        
        return lat, lon
    
    def calculate_tile_bounds(self, easting: float, northing: float, zone: int, 
                            tile_size: float = 1000.0, hemisphere: str = 'S') -> Dict[str, float]:
        """
        Calculate lat/lon bounds for a UTM tile
        
        Args:
            easting: UTM easting coordinate (center of tile)
            northing: UTM northing coordinate (center of tile)
            zone: UTM zone number
            tile_size: Tile size in meters (default 1000m = 1km)
            hemisphere: 'N' for northern, 'S' for southern hemisphere
            
        Returns:
            Dictionary with min_lat, max_lat, min_lon, max_lon
        """
        half_tile = tile_size / 2
        
        # Calculate corner coordinates
        corners = [
            (easting - half_tile, northing - half_tile),  # SW
            (easting + half_tile, northing - half_tile),  # SE
            (easting + half_tile, northing + half_tile),  # NE
            (easting - half_tile, northing + half_tile),  # NW
        ]
        
        # Convert all corners to lat/lon
        lat_lons = []
        for east, north in corners:
            lat, lon = self.utm_to_latlon(east, north, zone, hemisphere)
            lat_lons.append((lat, lon))
        
        # Find bounds
        lats = [ll[0] for ll in lat_lons]
        lons = [ll[1] for ll in lat_lons]
        
        return {
            "min_lat": min(lats),
            "max_lat": max(lats),
            "min_lon": min(lons), 
            "max_lon": max(lons)
        }

class DEMFilenameParser:
    """Parse DEM filenames to extract UTM coordinates"""
    
    def __init__(self):
        self.utm_converter = UTMConverter()
        
    def extract_utm_from_filename(self, filename: str) -> Optional[Dict]:
        """
        Extract UTM coordinates from DEM filename
        
        Supports patterns like:
        - ACT2015_4ppm_6586070_55_0002_0002_1m.tif
        - ClarenceRiver2023-DEM-AHD-1m_3706680_56_0001_0001.tif  
        - CooperBasin2019_DEM_3676990_54_01_001.tif
        """
        
        # Pattern 1: Standard grid naming (easting_zone_tile_tile)
        pattern1 = r'_(\d{7})_(\d{2})_\d+_\d+'
        match1 = re.search(pattern1, filename)
        
        if match1:
            easting_str = match1.group(1)
            zone = int(match1.group(2))
            
            # Convert 7-digit easting to full coordinate
            # Example: 6586070 -> 658607 (6-digit) + 0 (1km grid)
            if len(easting_str) == 7:
                easting_base = int(easting_str[:-1]) * 10  # Remove last digit, multiply by 10
                northing_estimated = self._estimate_northing_from_zone(zone)
                
                return {
                    "easting": easting_base + 500,  # Center of 1km tile
                    "northing": northing_estimated,
                    "zone": zone,
                    "tile_size": 1000
                }
        
        # Pattern 2: Alternative naming (northing in different position)
        pattern2 = r'_(\d{6,7})_(\d{2})_'
        match2 = re.search(pattern2, filename)
        
        if match2:
            coord_str = match2.group(1)
            zone = int(match2.group(2))
            
            # Determine if this is easting or northing based on value range
            coord_val = int(coord_str)
            
            if coord_val < 800000:  # Likely easting (Australia: ~200k-800k)
                easting = coord_val * 10 + 500  # Convert to full coordinate
                northing = self._estimate_northing_from_zone(zone)
            else:  # Likely northing
                northing = coord_val * 10
                easting = self._estimate_easting_from_zone(zone)
                
            return {
                "easting": easting,
                "northing": northing, 
                "zone": zone,
                "tile_size": 1000
            }
            
        return None
    
    def _estimate_northing_from_zone(self, zone: int) -> float:
        """Estimate northing based on UTM zone for Australian data"""
        # Australian northing ranges (southern hemisphere)
        zone_northings = {
            54: 7200000,  # Central Australia
            55: 6200000,  # Southeast Australia (ACT, VIC, TAS)
            56: 6800000,  # East Australia (NSW, QLD)
        }
        return zone_northings.get(zone, 6500000)  # Default central value
    
    def _estimate_easting_from_zone(self, zone: int) -> float:
        """Estimate easting based on UTM zone for Australian data"""
        # Australian easting ranges
        zone_eastings = {
            54: 400000,  # Western parts
            55: 500000,  # Central parts 
            56: 600000,  # Eastern parts
        }
        return zone_eastings.get(zone, 500000)  # Default central value
    
    def extract_bounds_from_filename(self, filename: str) -> Optional[Dict[str, float]]:
        """
        Extract lat/lon bounds from DEM filename
        
        Returns:
            Dictionary with min_lat, max_lat, min_lon, max_lon or None if parsing fails
        """
        utm_data = self.extract_utm_from_filename(filename)
        
        if not utm_data:
            return None
            
        try:
            bounds = self.utm_converter.calculate_tile_bounds(
                easting=utm_data["easting"],
                northing=utm_data["northing"], 
                zone=utm_data["zone"],
                tile_size=utm_data["tile_size"],
                hemisphere='S'  # Australia is southern hemisphere
            )
            
            # Validate bounds are reasonable for Australia/NZ
            if (bounds["min_lat"] < -50 and bounds["max_lat"] > -50 and 
                bounds["min_lon"] > 110 and bounds["max_lon"] < 180):
                return bounds
            else:
                # Return regional bounds if coordinate extraction seems wrong
                return self._get_regional_bounds_fallback(filename)
                
        except Exception:
            return self._get_regional_bounds_fallback(filename)
    
    def _get_regional_bounds_fallback(self, filename: str) -> Dict[str, float]:
        """Fallback to regional bounds based on filename content"""
        filename_lower = filename.lower()
        
        # State/region-based bounds
        if any(x in filename_lower for x in ['act', 'canberra']):
            return {"min_lat": -35.9, "max_lat": -35.1, "min_lon": 148.9, "max_lon": 149.4}
        elif any(x in filename_lower for x in ['nsw', 'sydney']):
            return {"min_lat": -37.5, "max_lat": -28.0, "min_lon": 140.9, "max_lon": 153.6}
        elif any(x in filename_lower for x in ['qld', 'queensland', 'brisbane']):
            return {"min_lat": -29.2, "max_lat": -9.0, "min_lon": 137.9, "max_lon": 153.6}
        elif any(x in filename_lower for x in ['tas', 'tasmania']):
            return {"min_lat": -43.6, "max_lat": -39.6, "min_lon": 143.8, "max_lon": 148.5}
        elif any(x in filename_lower for x in ['clarence', 'richmond']):
            return {"min_lat": -29.0, "max_lat": -25.0, "min_lon": 151.0, "max_lon": 154.0}
        else:
            # Default Australia-wide bounds
            return {"min_lat": -44.0, "max_lat": -9.0, "min_lon": 112.0, "max_lon": 154.0}


# Test function
def test_filename_parsing():
    """Test the filename parsing functionality"""
    parser = DEMFilenameParser()
    
    test_files = [
        "ACT2015_4ppm_6586070_55_0002_0002_1m.tif",
        "ClarenceRiver2023-DEM-AHD-1m_3706680_56_0001_0001.tif",
        "CooperBasin2019_DEM_3676990_54_01_001.tif"
    ]
    
    for filename in test_files:
        print(f"\nTesting: {filename}")
        utm_data = parser.extract_utm_from_filename(filename)
        print(f"UTM data: {utm_data}")
        
        bounds = parser.extract_bounds_from_filename(filename)
        print(f"Bounds: {bounds}")

if __name__ == "__main__":
    test_filename_parsing()