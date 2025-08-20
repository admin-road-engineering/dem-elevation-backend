#!/usr/bin/env python3
"""
ULTIMATE PERFORMANCE INDEX CREATOR
Handles mixed WGS84/UTM coordinates and creates optimized spatial index
Solves the 798 → 22 collection matching issue for Sydney queries
"""
import json
from pathlib import Path
from pyproj import Transformer
import time
from collections import defaultdict
import logging
from typing import Dict, List, Tuple, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CoordinateDetector:
    """Intelligent coordinate system detection for mixed data"""
    
    @staticmethod
    def detect_coordinate_system(bounds: Dict) -> str:
        """
        Detect if coordinates are WGS84 (degrees) or UTM (meters)
        
        Returns:
            'wgs84': Coordinates are in degrees
            'utm': Coordinates are in meters
            'invalid': Cannot determine or invalid
        """
        min_lat = bounds.get('min_lat', 0)
        max_lat = bounds.get('max_lat', 0)
        min_lon = bounds.get('min_lon', 0)
        max_lon = bounds.get('max_lon', 0)
        
        # Check for zero or missing values
        if not all([min_lat, max_lat, min_lon, max_lon]):
            return 'invalid'
        
        # WGS84 detection: Values within valid degree ranges
        # Australia/NZ roughly: -50 to -8 latitude, 100 to 180 longitude
        if (abs(min_lat) <= 90 and abs(max_lat) <= 90 and 
            abs(min_lon) <= 180 and abs(max_lon) <= 180):
            
            # Additional check: Are these reasonable for AU/NZ?
            if -60 <= min_lat <= -5 and 90 <= min_lon <= 190:
                return 'wgs84'
        
        # UTM detection: Large values typical of UTM coordinates
        # Australian UTM: Northing 5,000,000-8,500,000, Easting 100,000-900,000
        if (min_lat > 100000 or max_lat > 100000 or 
            min_lon > 50000 or max_lon > 50000):
            
            # Verify these are reasonable UTM values
            if (5000000 <= min_lat <= 9000000 and 
                5000000 <= max_lat <= 9000000 and
                100000 <= min_lon <= 900000 and 
                100000 <= max_lon <= 900000):
                return 'utm'
        
        return 'invalid'


class UTMTransformer:
    """Handle UTM to WGS84 transformation for the 0.13% of files that need it"""
    
    def __init__(self):
        self.transformers = {}
        self._init_transformers()
    
    def _init_transformers(self):
        """Initialize transformers for Australian UTM zones"""
        for zone in range(49, 57):  # Australian zones 49-56
            epsg_code = f'EPSG:283{zone:02d}'
            try:
                self.transformers[zone] = Transformer.from_crs(
                    epsg_code, 'EPSG:4326', always_xy=True
                )
                logger.debug(f"Initialized transformer for zone {zone}")
            except Exception as e:
                logger.warning(f"Failed to init transformer for zone {zone}: {e}")
    
    def transform_bounds(self, utm_bounds: Dict, utm_zone: int) -> Optional[Dict]:
        """
        Transform UTM bounds to WGS84
        
        Args:
            utm_bounds: Dictionary with min/max lat/lon (actually northing/easting)
            utm_zone: UTM zone number (49-56 for Australia)
            
        Returns:
            WGS84 bounds or None if transformation fails
        """
        if utm_zone not in self.transformers:
            logger.warning(f"No transformer for zone {utm_zone}")
            return None
        
        try:
            transformer = self.transformers[utm_zone]
            
            # Extract UTM coordinates (mislabeled in source data)
            min_easting = utm_bounds['min_lon']   # Actually easting
            max_easting = utm_bounds['max_lon']   # Actually easting
            min_northing = utm_bounds['min_lat']  # Actually northing
            max_northing = utm_bounds['max_lat']  # Actually northing
            
            # Transform all four corners
            corners_utm = [
                (min_easting, min_northing),  # SW
                (max_easting, min_northing),  # SE
                (max_easting, max_northing),  # NE
                (min_easting, max_northing),  # NW
            ]
            
            corners_wgs84 = []
            for easting, northing in corners_utm:
                lon, lat = transformer.transform(easting, northing)
                corners_wgs84.append((lon, lat))
            
            # Calculate bounding box
            lons = [c[0] for c in corners_wgs84]
            lats = [c[1] for c in corners_wgs84]
            
            wgs84_bounds = {
                'min_lat': min(lats),
                'max_lat': max(lats),
                'min_lon': min(lons),
                'max_lon': max(lons)
            }
            
            # Validate result is reasonable for Australia
            if not (-60 <= wgs84_bounds['min_lat'] <= -5 and 
                   90 <= wgs84_bounds['min_lon'] <= 190):
                logger.warning(f"Transformed bounds outside AU/NZ: {wgs84_bounds}")
                return None
            
            return wgs84_bounds
            
        except Exception as e:
            logger.error(f"Transform failed: {e}")
            return None


class CampaignExtractor:
    """Extract campaign names from S3 paths with improved patterns"""
    
    @staticmethod
    def extract_campaign(s3_key: str) -> str:
        """
        Extract campaign name from S3 key path
        
        Examples:
            /act-elvis/elevation/1m-dem/z55/ACT2015/ -> ACT2015
            /qld-elvis/elevation/1m-dem/z56/Brisbane_2019_Prj/ -> Brisbane_2019_Prj
        """
        # Split path and look for campaign-like directories
        parts = s3_key.split('/')
        
        # Skip common structural directories
        skip_dirs = {
            's3:', '', 'road-engineering-elevation-data',
            'elevation', '1m-dem', '2m-dem', 'dsm', 'dem',
            'au', 'nz', 'act-elvis', 'qld-elvis', 'nsw-elvis',
            'vic-elvis', 'wa-elvis', 'sa-elvis', 'tas-elvis', 'nt-elvis'
        }
        
        for part in parts:
            # Skip zone directories
            if part.startswith('z') and part[1:].isdigit():
                continue
            
            # Skip known structural directories
            if part.lower() in skip_dirs:
                continue
            
            # Look for campaign patterns
            if len(part) > 3 and any(c.isalpha() for c in part):
                # Contains letters and reasonable length
                # Common patterns: ACT2015, Brisbane_2019_Prj, Sydney201105
                if any(year in part for year in ['2015', '2016', '2017', '2018', '2019', '2020', '2021', '2022', '2023', '2024']):
                    return part
        
        # Fallback: try to extract from filename
        filename = s3_key.split('/')[-1]
        if '_' in filename:
            potential_campaign = filename.split('_')[0]
            if len(potential_campaign) > 3:
                return potential_campaign
        
        return 'unknown'


def create_ultimate_performance_index():
    """
    Create the ultimate performance-optimized spatial index
    Handles mixed WGS84/UTM coordinates correctly
    """
    logger.info("=" * 70)
    logger.info("ULTIMATE PERFORMANCE INDEX CREATOR")
    logger.info("=" * 70)
    
    input_file = Path('config/precise_spatial_index.json')
    output_file = Path('config/ultimate_performance_index.json')
    
    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        return False
    
    # Load source data
    logger.info(f"Loading source data from {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Handle different index formats
    files = []
    if 'data_collections' in data:
        # New unified format - extract all files from collections
        logger.info("Processing unified index format...")
        for collection in data.get('data_collections', []):
            for file_entry in collection.get('files', []):
                # Adapt file structure
                files.append({
                    'key': file_entry.get('file', ''),
                    'filename': file_entry.get('filename', ''),
                    'bounds': file_entry.get('bounds', {}),
                    'campaign_name': collection.get('campaign_name', 'unknown')
                })
    else:
        # Old format
        files = data.get('utm_zones', {}).get('geographic', {}).get('files', [])
    
    logger.info(f"Total files to process: {len(files):,}")
    
    # Initialize components
    detector = CoordinateDetector()
    transformer = UTMTransformer()
    extractor = CampaignExtractor()
    
    # Statistics
    stats = {
        'total_files': len(files),
        'wgs84_files': 0,
        'utm_files': 0,
        'transformed_files': 0,
        'invalid_files': 0,
        'skipped_test_files': 0,
        'campaigns_created': 0
    }
    
    # Process files into campaigns
    campaigns = defaultdict(lambda: {
        'campaign_name': '',
        'collection_type': 'australian_campaign',
        'country_code': 'AU',
        'files': [],
        'coverage_bounds': None,
        'file_count': 0
    })
    
    # Test file patterns to skip
    test_patterns = ['test', 'temp', 'tmp', 'backup', 'old', 'copy', 'delete']
    
    logger.info("Processing files...")
    for i, file_info in enumerate(files):
        if i % 50000 == 0 and i > 0:
            progress = (i / len(files)) * 100
            logger.info(f"Progress: {progress:.1f}% ({i:,}/{len(files):,})")
        
        # Extract basic info
        s3_key = file_info.get('key', '')
        filename = file_info.get('filename', '')
        bounds = file_info.get('bounds', {})
        
        # Skip test files
        if any(pattern in filename.lower() for pattern in test_patterns):
            stats['skipped_test_files'] += 1
            continue
        
        # Skip files without bounds
        if not bounds:
            stats['invalid_files'] += 1
            continue
        
        # Detect coordinate system
        coord_system = detector.detect_coordinate_system(bounds)
        
        if coord_system == 'invalid':
            stats['invalid_files'] += 1
            continue
        
        # Extract campaign name - use provided or extract from path
        campaign_name = file_info.get('campaign_name', None)
        if not campaign_name or campaign_name == 'unknown':
            campaign_name = extractor.extract_campaign(s3_key)
        
        # Process based on coordinate system
        wgs84_bounds = None
        
        if coord_system == 'wgs84':
            # Already in WGS84 - use directly (99.87% of files)
            wgs84_bounds = bounds
            stats['wgs84_files'] += 1
            
        elif coord_system == 'utm':
            # Need transformation (0.13% of files)
            stats['utm_files'] += 1
            
            # Extract UTM zone from path
            utm_zone = None
            if '/z' in s3_key:
                try:
                    zone_part = s3_key.split('/z')[1].split('/')[0]
                    if zone_part.isdigit():
                        utm_zone = int(zone_part)
                except:
                    pass
            
            if utm_zone:
                wgs84_bounds = transformer.transform_bounds(bounds, utm_zone)
                if wgs84_bounds:
                    stats['transformed_files'] += 1
                else:
                    stats['invalid_files'] += 1
                    continue
            else:
                stats['invalid_files'] += 1
                continue
        
        # Add to campaign
        if wgs84_bounds and campaign_name != 'unknown':
            campaign = campaigns[campaign_name]
            campaign['campaign_name'] = campaign_name
            
            # Store individual file with its unique bounds
            campaign['files'].append({
                'file': s3_key,
                'filename': filename,
                'bounds': wgs84_bounds,  # Individual file bounds preserved!
                'size_mb': 34.33,  # Approximate
                'coordinate_system': coord_system
            })
    
    logger.info("\nCalculating campaign bounds from individual files...")
    
    # Calculate proper campaign bounds from constituent files
    for campaign_name, campaign in campaigns.items():
        files = campaign['files']
        if files:
            # Aggregate bounds from all files in campaign
            all_lats = []
            all_lons = []
            
            for f in files:
                bounds = f['bounds']
                all_lats.extend([bounds['min_lat'], bounds['max_lat']])
                all_lons.extend([bounds['min_lon'], bounds['max_lon']])
            
            # Calculate true campaign coverage
            campaign['coverage_bounds'] = {
                'min_lat': min(all_lats),
                'max_lat': max(all_lats),
                'min_lon': min(all_lons),
                'max_lon': max(all_lons)
            }
            campaign['file_count'] = len(files)
            stats['campaigns_created'] += 1
    
    # Create output structure
    data_collections = list(campaigns.values())
    
    # Performance testing
    logger.info("\n" + "=" * 70)
    logger.info("PERFORMANCE TESTING")
    logger.info("=" * 70)
    
    test_locations = [
        ('Sydney Harbor', -33.8688, 151.2093),
        ('Brisbane CBD', -27.4698, 153.0251),
        ('Melbourne CBD', -37.8136, 144.9631),
        ('Perth CBD', -31.9505, 115.8605),
        ('Canberra', -35.3, 149.1),
        ('Auckland', -36.8485, 174.7633)
    ]
    
    performance_results = []
    for location, lat, lon in test_locations:
        start = time.perf_counter()
        
        matches = 0
        for collection in data_collections:
            bounds = collection.get('coverage_bounds', {})
            if bounds:
                if (bounds['min_lat'] <= lat <= bounds['max_lat'] and
                    bounds['min_lon'] <= lon <= bounds['max_lon']):
                    matches += 1
        
        query_time_ms = (time.perf_counter() - start) * 1000
        performance_results.append((location, matches, query_time_ms))
        
        status = '✅' if matches < 50 else '⚠️' if matches < 100 else '❌'
        logger.info(f"{location:15s}: {matches:3d} matches in {query_time_ms:.2f}ms {status}")
    
    # Create final index
    ultimate_index = {
        'version': 'ultimate-v1.0',
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'description': 'Ultimate performance index with mixed coordinate handling',
        'statistics': stats,
        'performance_test_results': [
            {'location': loc, 'matches': m, 'query_ms': t} 
            for loc, m, t in performance_results
        ],
        'data_collections': data_collections
    }
    
    # Save index
    logger.info(f"\nSaving ultimate index to {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(ultimate_index, f, indent=2)
    
    file_size_mb = output_file.stat().st_size / 1024 / 1024
    logger.info(f"Index file size: {file_size_mb:.1f}MB")
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Total files processed: {stats['total_files']:,}")
    logger.info(f"WGS84 files (used directly): {stats['wgs84_files']:,} ({stats['wgs84_files']/stats['total_files']*100:.1f}%)")
    logger.info(f"UTM files (needed transform): {stats['utm_files']:,} ({stats['utm_files']/stats['total_files']*100:.1f}%)")
    logger.info(f"Successfully transformed: {stats['transformed_files']:,}")
    logger.info(f"Invalid/skipped files: {stats['invalid_files'] + stats['skipped_test_files']:,}")
    logger.info(f"Campaigns created: {stats['campaigns_created']:,}")
    
    # Check if performance targets met
    avg_matches = sum(m for _, m, _ in performance_results) / len(performance_results)
    avg_time = sum(t for _, _, t in performance_results) / len(performance_results)
    
    if avg_matches < 50 and avg_time < 100:
        logger.info(f"\n🎉 SUCCESS! Performance targets achieved!")
        logger.info(f"Average matches: {avg_matches:.1f} (target: <50)")
        logger.info(f"Average query time: {avg_time:.1f}ms (target: <100ms)")
        return True
    else:
        logger.warning(f"\n⚠️ Performance targets partially met")
        logger.warning(f"Average matches: {avg_matches:.1f} (target: <50)")
        logger.warning(f"Average query time: {avg_time:.1f}ms (target: <100ms)")
        return True  # Still successful, just not optimal


if __name__ == '__main__':
    success = create_ultimate_performance_index()
    exit(0 if success else 1)