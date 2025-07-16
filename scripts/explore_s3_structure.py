#!/usr/bin/env python3
"""
S3 Bucket Structure Explorer
Scans S3 bucket to understand folder structure and automatically detect DEM files
"""

import boto3
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple

class S3StructureExplorer:
    """Explore and catalog S3 bucket structure for DEM data"""
    
    def __init__(self, bucket_name: str, aws_access_key: str = None, aws_secret_key: str = None):
        self.bucket_name = bucket_name
        self.aws_access_key = aws_access_key or os.getenv('AWS_ACCESS_KEY_ID')
        self.aws_secret_key = aws_secret_key or os.getenv('AWS_SECRET_ACCESS_KEY')
        
        if not self.aws_access_key or not self.aws_secret_key:
            print("❌ AWS credentials not found. Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
            sys.exit(1)
            
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=self.aws_access_key,
            aws_secret_access_key=self.aws_secret_key,
            region_name='ap-southeast-2'
        )
        
        # Known DEM file extensions
        self.dem_extensions = {'.tif', '.tiff', '.gdb', '.hgt', '.dem', '.asc', '.bil', '.flt'}
        
    def scan_bucket_structure(self, max_depth: int = 4, max_objects: int = 10000) -> Dict:
        """Scan bucket and build folder structure tree"""
        print(f"🔍 Scanning S3 bucket: {self.bucket_name}")
        print(f"📊 Max depth: {max_depth}, Max objects: {max_objects}")
        
        structure = {
            "bucket_name": self.bucket_name,
            "scan_timestamp": datetime.now().isoformat(),
            "folder_tree": defaultdict(lambda: defaultdict(dict)),
            "dem_files": [],
            "file_extensions": defaultdict(int),
            "folder_stats": defaultdict(int),
            "size_stats": {"total_size_bytes": 0, "file_count": 0}
        }
        
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(Bucket=self.bucket_name)
            
            object_count = 0
            
            for page in page_iterator:
                if 'Contents' not in page:
                    continue
                    
                for obj in page['Contents']:
                    object_count += 1
                    if object_count > max_objects:
                        print(f"⚠️ Reached max objects limit ({max_objects}), stopping scan")
                        break
                        
                    key = obj['Key']
                    size = obj['Size']
                    last_modified = obj['LastModified']
                    
                    # Update size stats
                    structure["size_stats"]["total_size_bytes"] += size
                    structure["size_stats"]["file_count"] += 1
                    
                    # Parse folder structure
                    path_parts = key.split('/')
                    
                    # Skip if too deep
                    if len(path_parts) > max_depth:
                        continue
                        
                    # Track file extensions
                    if '.' in path_parts[-1]:
                        ext = '.' + path_parts[-1].split('.')[-1].lower()
                        structure["file_extensions"][ext] += 1
                        
                        # Check if it's a DEM file
                        if ext in self.dem_extensions:
                            dem_info = {
                                "key": key,
                                "size_bytes": size,
                                "size_mb": round(size / (1024*1024), 2),
                                "last_modified": last_modified.isoformat(),
                                "extension": ext,
                                "folder_path": '/'.join(path_parts[:-1]) if len(path_parts) > 1 else "",
                                "filename": path_parts[-1]
                            }
                            structure["dem_files"].append(dem_info)
                    
                    # Build folder tree (first 3 levels)
                    current_level = structure["folder_tree"]
                    for i, part in enumerate(path_parts[:3]):
                        if i == len(path_parts) - 1 and '.' in part:
                            # It's a file, not a folder
                            break
                        if part not in current_level:
                            current_level[part] = defaultdict(dict)
                        current_level = current_level[part]
                        
                        # Track folder stats
                        folder_path = '/'.join(path_parts[:i+1])
                        structure["folder_stats"][folder_path] += 1
                
                if object_count > max_objects:
                    break
                    
            print(f"✅ Scan complete: {object_count} objects processed")
            
        except Exception as e:
            print(f"❌ Error scanning bucket: {str(e)}")
            return None
            
        return structure
    
    def analyze_dem_patterns(self, structure: Dict) -> Dict:
        """Analyze DEM file patterns to suggest optimal source configurations"""
        dem_files = structure.get("dem_files", [])
        
        if not dem_files:
            print("⚠️ No DEM files found in bucket")
            return {}
            
        print(f"\n📊 ANALYZING {len(dem_files)} DEM FILES")
        print("=" * 50)
        
        # Group by folder patterns
        folder_patterns = defaultdict(list)
        resolution_patterns = set()
        zone_patterns = set()
        organization_patterns = set()
        
        for dem_file in dem_files:
            folder_path = dem_file["folder_path"]
            filename = dem_file["filename"]
            
            # Extract patterns from folder path
            parts = folder_path.split('/')
            
            if len(parts) >= 1:
                organization_patterns.add(parts[0])
            
            # Look for resolution patterns (1m, 50cm, 5m, etc.)
            for part in parts:
                if any(res in part.lower() for res in ['1m', '2m', '5m', '10m', '50cm', '25cm']):
                    resolution_patterns.add(part)
                if any(zone in part.lower() for zone in ['z54', 'z55', 'z56', 'utm']):
                    zone_patterns.add(part)
            
            # Group by folder pattern (first 3 levels)
            pattern = '/'.join(parts[:3]) if len(parts) >= 3 else folder_path
            folder_patterns[pattern].append(dem_file)
        
        analysis = {
            "organizations": sorted(organization_patterns),
            "resolution_folders": sorted(resolution_patterns),
            "zone_folders": sorted(zone_patterns),
            "folder_patterns": dict(folder_patterns),
            "total_dem_files": len(dem_files),
            "total_size_gb": round(sum(f["size_bytes"] for f in dem_files) / (1024**3), 2)
        }
        
        return analysis
    
    def suggest_dem_sources_config(self, analysis: Dict) -> Dict:
        """Suggest optimal DEM_SOURCES configuration based on analysis"""
        if not analysis:
            return {}
            
        suggested_sources = {}
        
        # Generate source configs based on folder patterns
        for pattern, files in analysis.get("folder_patterns", {}).items():
            if not files:
                continue
                
            # Skip if too few files
            if len(files) < 5:
                continue
                
            # Create source ID from pattern
            source_id = pattern.replace('/', '_').replace('-', '_').lower()
            if not source_id:
                continue
                
            # Determine CRS based on zone or organization
            crs = "EPSG:3577"  # Default Australian Albers
            if "z55" in pattern.lower():
                crs = "EPSG:28355"  # UTM Zone 55S
            elif "z56" in pattern.lower():
                crs = "EPSG:28356"  # UTM Zone 56S
            elif "z54" in pattern.lower():
                crs = "EPSG:28354"  # UTM Zone 54S
            
            # Calculate total size for this pattern
            total_size_mb = sum(f["size_mb"] for f in files)
            avg_size_mb = total_size_mb / len(files) if files else 0
            
            suggested_sources[source_id] = {
                "path": f"s3://{self.bucket_name}/{pattern}/",
                "layer": None,
                "crs": crs,
                "description": f"Auto-detected: {len(files)} DEM files, ~{total_size_mb:.0f}MB total",
                "metadata": {
                    "file_count": len(files),
                    "total_size_mb": round(total_size_mb, 2),
                    "avg_file_size_mb": round(avg_size_mb, 2),
                    "sample_files": [f["filename"] for f in files[:3]]
                }
            }
        
        return suggested_sources
    
    def print_structure_summary(self, structure: Dict, analysis: Dict):
        """Print a human-readable summary of the bucket structure"""
        print(f"\n🗂️ S3 BUCKET STRUCTURE SUMMARY")
        print("=" * 60)
        print(f"Bucket: {structure['bucket_name']}")
        print(f"Scanned: {structure['size_stats']['file_count']} files")
        print(f"Total Size: {structure['size_stats']['total_size_bytes'] / (1024**3):.2f} GB")
        
        print(f"\n📁 TOP-LEVEL ORGANIZATIONS:")
        for org in analysis.get("organizations", []):
            print(f"  • {org}")
        
        print(f"\n📏 RESOLUTION PATTERNS FOUND:")
        for res in analysis.get("resolution_folders", []):
            print(f"  • {res}")
            
        print(f"\n🌏 ZONE PATTERNS FOUND:")
        for zone in analysis.get("zone_folders", []):
            print(f"  • {zone}")
        
        print(f"\n📄 FILE EXTENSIONS:")
        for ext, count in sorted(structure["file_extensions"].items()):
            print(f"  • {ext}: {count} files")
        
        print(f"\n🗺️ DEM FILES SUMMARY:")
        dem_files = structure.get("dem_files", [])
        if dem_files:
            print(f"  • Total DEM files: {len(dem_files)}")
            print(f"  • Total DEM size: {analysis.get('total_size_gb', 0)} GB")
            print(f"  • Largest file: {max(dem_files, key=lambda x: x['size_mb'])['filename']} ({max(dem_files, key=lambda x: x['size_mb'])['size_mb']} MB)")
            print(f"  • Sample files:")
            for i, dem in enumerate(dem_files[:5]):
                print(f"    - {dem['filename']} ({dem['size_mb']} MB)")
        else:
            print("  • No DEM files found")
    
    def export_results(self, structure: Dict, analysis: Dict, suggested_sources: Dict):
        """Export results to JSON files"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Export full structure
        structure_file = f"s3_structure_{timestamp}.json"
        with open(structure_file, 'w') as f:
            # Convert defaultdict to regular dict for JSON serialization
            structure_copy = dict(structure)
            structure_copy["folder_tree"] = dict(structure_copy["folder_tree"])
            json.dump(structure_copy, f, indent=2, default=str)
        
        # Export suggested config
        config_file = f"suggested_dem_sources_{timestamp}.json"
        with open(config_file, 'w') as f:
            json.dump(suggested_sources, f, indent=2)
        
        # Export environment config format
        env_config_file = f"dem_sources_config_{timestamp}.txt"
        with open(env_config_file, 'w') as f:
            f.write("# Generated DEM_SOURCES configuration\n")
            f.write("# Add this to your .env file\n\n")
            f.write(f"DEM_SOURCES={json.dumps(suggested_sources)}\n")
        
        print(f"\n💾 EXPORTED FILES:")
        print(f"  • Full structure: {structure_file}")
        print(f"  • Suggested sources: {config_file}")
        print(f"  • Environment config: {env_config_file}")
        
        return structure_file, config_file, env_config_file

def main():
    """Main execution function"""
    bucket_name = os.getenv('AWS_S3_BUCKET_NAME', 'road-engineering-elevation-data')
    
    print("🚀 S3 Structure Explorer")
    print("=" * 40)
    print(f"Target bucket: {bucket_name}")
    
    # Initialize explorer
    explorer = S3StructureExplorer(bucket_name)
    
    # Scan bucket structure
    structure = explorer.scan_bucket_structure(max_depth=6, max_objects=50000)
    if not structure:
        print("❌ Failed to scan bucket structure")
        sys.exit(1)
    
    # Analyze DEM patterns
    analysis = explorer.analyze_dem_patterns(structure)
    
    # Suggest source configurations
    suggested_sources = explorer.suggest_dem_sources_config(analysis)
    
    # Print summary
    explorer.print_structure_summary(structure, analysis)
    
    # Show suggested configuration
    if suggested_sources:
        print(f"\n⚙️ SUGGESTED DEM_SOURCES CONFIGURATION:")
        print("=" * 60)
        for source_id, config in suggested_sources.items():
            print(f"\n📍 {source_id}:")
            print(f"   Path: {config['path']}")
            print(f"   CRS: {config['crs']}")
            print(f"   Files: {config['metadata']['file_count']} ({config['metadata']['total_size_mb']:.0f} MB)")
            print(f"   Description: {config['description']}")
    
    # Export results
    explorer.export_results(structure, analysis, suggested_sources)
    
    print(f"\n✅ Exploration complete!")
    print("💡 Copy the suggested DEM_SOURCES configuration to your .env file")

if __name__ == "__main__":
    main()