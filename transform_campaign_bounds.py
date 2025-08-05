#!/usr/bin/env python3
"""
Transform Campaign Bounds: Phase 6 P0 Critical Fix

This script transforms Australian campaign bounds from WGS84 coordinates to native UTM coordinates
to fix the data-code contract violation identified in Phase 5.

Root Cause: Brisbane input (-27.4698, 153.0251) gets transformed to UTM Zone 56 (x=502k, y=6.9M)
but campaign bounds remain in WGS84 (min_lat=-27.67, max_lat=-27.01) causing no intersection.

Solution: Transform bounds from WGS84 to UTM using existing CRSTransformationService.
"""

import json
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import CRS service from existing implementation
from src.services.crs_service import CRSTransformationService

class BoundsTransformer:
    """Transforms campaign bounds from WGS84 to UTM coordinates"""
    
    def __init__(self):
        self.crs_service = CRSTransformationService()
        self.stats = {
            "processed": 0,
            "transformed": 0,
            "skipped": 0,
            "errors": 0
        }
    
    def transform_bounds_to_utm(self, bounds: Dict[str, float], epsg_code: str) -> Dict[str, float]:
        """
        Transform WGS84 bounds to UTM coordinates
        
        Args:
            bounds: WGS84 bounds with min_lat, max_lat, min_lon, max_lon
            epsg_code: Target EPSG code (e.g., "28356" for UTM Zone 56)
        
        Returns:
            UTM bounds with min_x, max_x, min_y, max_y
        """
        try:
            # Transform corner coordinates
            # Bottom-left corner (min_lat, min_lon)
            min_x, min_y = self.crs_service.transform_to_crs(
                bounds["min_lat"], bounds["min_lon"], epsg_code
            )
            
            # Top-right corner (max_lat, max_lon)  
            max_x, max_y = self.crs_service.transform_to_crs(
                bounds["max_lat"], bounds["max_lon"], epsg_code
            )
            
            # Ensure min/max are correctly ordered (pyproj may swap them)
            utm_bounds = {
                "min_x": min(min_x, max_x),
                "max_x": max(min_x, max_x),
                "min_y": min(min_y, max_y),
                "max_y": max(min_y, max_y)
            }
            
            logger.debug(f"Transformed WGS84 bounds {bounds} to UTM bounds {utm_bounds} using EPSG:{epsg_code}")
            return utm_bounds
            
        except Exception as e:
            logger.error(f"Failed to transform bounds {bounds} with EPSG:{epsg_code}: {e}")
            raise
    
    def is_wgs84_bounds(self, bounds: Dict[str, Any]) -> bool:
        """Check if bounds are in WGS84 format (lat/lon keys)"""
        return all(key in bounds for key in ["min_lat", "max_lat", "min_lon", "max_lon"])
    
    def is_utm_bounds(self, bounds: Dict[str, Any]) -> bool:
        """Check if bounds are already in UTM format (x/y keys)"""
        return all(key in bounds for key in ["min_x", "max_x", "min_y", "max_y"])
    
    def transform_collection(self, collection: Dict[str, Any]) -> Dict[str, Any]:
        """Transform a single collection's bounds if needed"""
        try:
            # Only process Australian UTM collections with EPSG codes
            if (collection.get("collection_type") != "australian_utm_zone" or 
                "epsg" not in collection or 
                "coverage_bounds" not in collection):
                self.stats["skipped"] += 1
                return collection
            
            bounds = collection["coverage_bounds"]
            epsg_code = collection["epsg"]
            
            # Check if already transformed
            if self.is_utm_bounds(bounds):
                logger.debug(f"Collection {collection.get('campaign_name', 'unknown')} already has UTM bounds")
                self.stats["skipped"] += 1
                return collection
            
            # Check if needs transformation
            if not self.is_wgs84_bounds(bounds):
                logger.warning(f"Collection {collection.get('campaign_name', 'unknown')} has unexpected bounds format: {bounds}")
                self.stats["skipped"] += 1
                return collection
            
            # Transform bounds
            logger.info(f"Transforming bounds for {collection.get('campaign_name', 'unknown')} using EPSG:{epsg_code}")
            utm_bounds = self.transform_bounds_to_utm(bounds, epsg_code)
            
            # Update collection with UTM bounds
            collection["coverage_bounds"] = utm_bounds
            
            # Add transformation metadata
            collection["bounds_transformation"] = {
                "original_format": "wgs84",
                "transformed_format": "utm",
                "epsg_code": epsg_code,
                "transformed_at": datetime.utcnow().isoformat()
            }
            
            self.stats["transformed"] += 1
            logger.info(f"Successfully transformed {collection.get('campaign_name', 'unknown')}: "
                       f"WGS84 {bounds} -> UTM {utm_bounds}")
            
            return collection
            
        except Exception as e:
            logger.error(f"Failed to transform collection {collection.get('campaign_name', 'unknown')}: {e}")
            self.stats["errors"] += 1
            return collection  # Return original on error
    
    def transform_unified_index(self, index_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform all collections in the unified index"""
        logger.info("Starting bounds transformation for unified index...")
        
        collections = index_data.get("data_collections", [])
        total_collections = len(collections)
        
        logger.info(f"Processing {total_collections} collections...")
        
        # Transform each collection
        transformed_collections = []
        for i, collection in enumerate(collections):
            if i % 100 == 0:
                logger.info(f"Progress: {i}/{total_collections} collections processed")
            
            transformed_collection = self.transform_collection(collection)
            transformed_collections.append(transformed_collection)
            self.stats["processed"] += 1
        
        # Update index with transformed collections
        index_data["data_collections"] = transformed_collections
        
        # Add transformation metadata to index
        index_data["transformation_metadata"] = {
            "transformed_at": datetime.utcnow().isoformat(),
            "transformation_type": "wgs84_to_utm_bounds",
            "stats": self.stats.copy(),
            "crs_service_version": "phase_5_implementation"
        }
        
        logger.info(f"Bounds transformation completed: {self.stats}")
        return index_data

def main():
    """Main function to transform campaign bounds"""
    logger.info("=== Phase 6 P0: Campaign Bounds Transformation ===")
    
    # Input and output paths
    input_path = Path("config/unified_spatial_index_v2_ideal.json")
    output_path = Path("config/unified_spatial_index_v2_utm_bounds.json")
    
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        return False
    
    try:
        # Load unified index
        logger.info(f"Loading unified index from {input_path}...")
        with open(input_path, 'r', encoding='utf-8') as f:
            index_data = json.load(f)
        
        logger.info(f"Loaded index with {len(index_data.get('collections', []))} collections")
        
        # Transform bounds
        transformer = BoundsTransformer()
        transformed_index = transformer.transform_unified_index(index_data)
        
        # Save transformed index
        logger.info(f"Saving transformed index to {output_path}...")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(transformed_index, f, indent=2, ensure_ascii=False)
        
        # Log file sizes
        original_size = input_path.stat().st_size / (1024 * 1024)  # MB
        new_size = output_path.stat().st_size / (1024 * 1024)  # MB
        
        logger.info(f"Transformation completed successfully!")
        logger.info(f"Original file: {original_size:.1f} MB")
        logger.info(f"Transformed file: {new_size:.1f} MB")
        logger.info(f"Statistics: {transformer.stats}")
        
        # Show sample Brisbane transformation
        for collection in transformed_index["data_collections"][:10]:
            if "Brisbane" in collection.get("campaign_name", ""):
                logger.info(f"Sample Brisbane campaign: {collection['campaign_name']}")
                logger.info(f"  EPSG: {collection['epsg']}")
                logger.info(f"  UTM Bounds: {collection['coverage_bounds']}")
                break
        
        return True
        
    except Exception as e:
        logger.error(f"Transformation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)