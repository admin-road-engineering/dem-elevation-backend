#!/usr/bin/env python3
"""
S3 Catalog Management Script
Manages catalog discovery, updates, and maintenance for multi-location S3 DEM data.
"""

import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from s3_source_manager import S3SourceManager
    from config import get_settings
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure you're running from the DEM Backend directory")
    sys.exit(1)

class S3CatalogManager:
    """Manage S3 catalog operations for multi-location DEM data"""
    
    def __init__(self, bucket_name: str):
        self.bucket_name = bucket_name
        self.manager = S3SourceManager(bucket_name)
        self.settings = get_settings()
        
    def discover_new_datasets(self) -> List[Dict[str, Any]]:
        """Discover new datasets in the S3 bucket"""
        print(f"🔍 Discovering new datasets in bucket: {self.bucket_name}")
        
        try:
            new_datasets = self.manager.discover_new_datasets()
            print(f"Found {len(new_datasets)} new datasets")
            
            if new_datasets:
                print("\nNew datasets discovered:")
                for i, dataset in enumerate(new_datasets, 1):
                    print(f"  {i}. {dataset.get('id', 'unknown')}")
                    print(f"     Path: {dataset.get('path', 'unknown')}")
                    print(f"     Region: {dataset.get('region', 'unknown')}")
                    print(f"     Resolution: {dataset.get('resolution_m', 'unknown')}m")
                    print(f"     Bounds: {dataset.get('bounds', 'unknown')}")
                    print()
            else:
                print("No new datasets found - catalog is up to date")
                
            return new_datasets
            
        except Exception as e:
            print(f"Error during discovery: {e}")
            return []
            
    def update_catalog(self, dry_run: bool = False) -> bool:
        """Update catalog with discovered datasets"""
        print(f"📝 Updating catalog for bucket: {self.bucket_name}")
        
        try:
            # Discover new datasets
            new_datasets = self.discover_new_datasets()
            
            if not new_datasets:
                print("No updates needed - catalog is current")
                return True
                
            if dry_run:
                print("\n🧪 DRY RUN - No changes will be made")
                print("The following datasets would be added to the catalog:")
                for dataset in new_datasets:
                    print(f"  - {dataset.get('id', 'unknown')}: {dataset.get('path', 'unknown')}")
                return True
                
            # Update catalog
            print(f"Adding {len(new_datasets)} new datasets to catalog...")
            updated_catalog = self.manager.update_catalog_with_discoveries()
            
            if updated_catalog:
                print("✅ Catalog updated successfully")
                print(f"Total catalog entries: {len(updated_catalog)}")
                return True
            else:
                print("❌ Failed to update catalog")
                return False
                
        except Exception as e:
            print(f"Error updating catalog: {e}")
            return False
            
    def validate_catalog(self) -> bool:
        """Validate catalog integrity"""
        print(f"✅ Validating catalog for bucket: {self.bucket_name}")
        
        try:
            catalog = self.manager.get_catalog()
            
            if not catalog:
                print("❌ No catalog found")
                return False
                
            print(f"Found {len(catalog)} catalog entries")
            
            # Validate each entry
            invalid_entries = []
            regions = {}
            
            for entry_id, metadata in catalog.items():
                # Check required fields
                required_fields = ['id', 'path', 'bounds', 'resolution_m', 'crs']
                missing_fields = [field for field in required_fields if not hasattr(metadata, field)]
                
                if missing_fields:
                    invalid_entries.append(f"{entry_id}: missing {missing_fields}")
                    continue
                    
                # Track regional coverage
                region = getattr(metadata, 'region', 'unknown')
                if region not in regions:
                    regions[region] = []
                regions[region].append(entry_id)
                
            if invalid_entries:
                print(f"❌ Found {len(invalid_entries)} invalid entries:")
                for entry in invalid_entries:
                    print(f"  - {entry}")
                return False
                
            # Report regional coverage
            print(f"✅ All {len(catalog)} entries are valid")
            print(f"Regional coverage ({len(regions)} regions):")
            for region, entries in regions.items():
                resolutions = []
                for entry_id in entries:
                    metadata = catalog[entry_id]
                    res = getattr(metadata, 'resolution_m', 'unknown')
                    resolutions.append(f"{res}m")
                print(f"  {region}: {len(entries)} datasets ({', '.join(set(resolutions))})")
                
            return True
            
        except Exception as e:
            print(f"Error validating catalog: {e}")
            return False
            
    def export_catalog(self, output_file: str) -> bool:
        """Export catalog to JSON file"""
        print(f"📤 Exporting catalog to: {output_file}")
        
        try:
            catalog = self.manager.get_catalog()
            
            if not catalog:
                print("❌ No catalog found to export")
                return False
                
            # Convert to exportable format
            export_data = {
                "bucket": self.bucket_name,
                "timestamp": datetime.now().isoformat(),
                "total_entries": len(catalog),
                "entries": {}
            }
            
            for entry_id, metadata in catalog.items():
                export_data["entries"][entry_id] = {
                    "id": getattr(metadata, 'id', entry_id),
                    "path": getattr(metadata, 'path', ''),
                    "bounds": getattr(metadata, 'bounds', []),
                    "resolution_m": getattr(metadata, 'resolution_m', 0),
                    "crs": getattr(metadata, 'crs', ''),
                    "region": getattr(metadata, 'region', 'unknown'),
                    "size_bytes": getattr(metadata, 'size_bytes', 0),
                    "description": getattr(metadata, 'description', ''),
                    "accuracy": getattr(metadata, 'accuracy', ''),
                    "last_updated": getattr(metadata, 'last_updated', '')
                }
                
            with open(output_file, 'w') as f:
                json.dump(export_data, f, indent=2)
                
            print(f"✅ Catalog exported successfully ({len(catalog)} entries)")
            return True
            
        except Exception as e:
            print(f"Error exporting catalog: {e}")
            return False
            
    def show_catalog_stats(self):
        """Show catalog statistics"""
        print(f"📊 Catalog statistics for bucket: {self.bucket_name}")
        
        try:
            catalog = self.manager.get_catalog()
            
            if not catalog:
                print("❌ No catalog found")
                return
                
            total_entries = len(catalog)
            total_size = 0
            regions = {}
            resolutions = {}
            crs_count = {}
            
            for entry_id, metadata in catalog.items():
                # Size tracking
                size = getattr(metadata, 'size_bytes', 0)
                total_size += size
                
                # Regional tracking
                region = getattr(metadata, 'region', 'unknown')
                if region not in regions:
                    regions[region] = {'count': 0, 'size': 0}
                regions[region]['count'] += 1
                regions[region]['size'] += size
                
                # Resolution tracking
                resolution = getattr(metadata, 'resolution_m', 0)
                if resolution not in resolutions:
                    resolutions[resolution] = 0
                resolutions[resolution] += 1
                
                # CRS tracking
                crs = getattr(metadata, 'crs', 'unknown')
                if crs not in crs_count:
                    crs_count[crs] = 0
                crs_count[crs] += 1
                
            # Print statistics
            print(f"Total entries: {total_entries}")
            print(f"Total size: {total_size / (1024**3):.2f} GB")
            print(f"Average size: {total_size / total_entries / (1024**2):.2f} MB per dataset")
            
            print(f"\nRegional distribution:")
            for region, stats in sorted(regions.items()):
                print(f"  {region}: {stats['count']} datasets ({stats['size'] / (1024**3):.2f} GB)")
                
            print(f"\nResolution distribution:")
            for resolution, count in sorted(resolutions.items()):
                print(f"  {resolution}m: {count} datasets")
                
            print(f"\nCRS distribution:")
            for crs, count in sorted(crs_count.items()):
                print(f"  {crs}: {count} datasets")
                
        except Exception as e:
            print(f"Error generating statistics: {e}")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Manage S3 catalog for multi-location DEM data")
    parser.add_argument('--bucket', default='road-engineering-elevation-data',
                       help='S3 bucket name (default: road-engineering-elevation-data)')
    parser.add_argument('--action', choices=['discover', 'update', 'validate', 'export', 'stats'],
                       default='stats', help='Action to perform (default: stats)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Perform dry run (no changes made)')
    parser.add_argument('--output', default='catalog_export.json',
                       help='Output file for export (default: catalog_export.json)')
    
    args = parser.parse_args()
    
    # Initialize manager
    manager = S3CatalogManager(args.bucket)
    
    print(f"🚀 S3 Catalog Manager - {args.action.upper()}")
    print("=" * 50)
    
    success = True
    
    if args.action == 'discover':
        new_datasets = manager.discover_new_datasets()
        success = len(new_datasets) >= 0  # Discovery always succeeds
        
    elif args.action == 'update':
        success = manager.update_catalog(dry_run=args.dry_run)
        
    elif args.action == 'validate':
        success = manager.validate_catalog()
        
    elif args.action == 'export':
        success = manager.export_catalog(args.output)
        
    elif args.action == 'stats':
        manager.show_catalog_stats()
        success = True
        
    if success:
        print(f"\n✅ {args.action.capitalize()} completed successfully")
    else:
        print(f"\n❌ {args.action.capitalize()} failed")
        
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()