#!/usr/bin/env python3
"""
Simple S3 Bucket Structure Explorer
Scans S3 bucket to understand folder structure and detect DEM files
"""

import boto3
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from typing import Dict, List
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class SimpleS3Explorer:
    """Simple S3 bucket explorer for DEM data"""
    
    def __init__(self, bucket_name: str):
        self.bucket_name = bucket_name
        
        # Load credentials manually from .env file
        env_file = Path(__file__).parent.parent / ".env"
        credentials = {}
        
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('AWS_ACCESS_KEY_ID='):
                    credentials['access_key'] = line.split('=', 1)[1]
                elif line.startswith('AWS_SECRET_ACCESS_KEY='):
                    credentials['secret_key'] = line.split('=', 1)[1]
        
        self.aws_access_key = credentials.get('access_key')
        self.aws_secret_key = credentials.get('secret_key')
        
        if not self.aws_access_key or not self.aws_secret_key:
            print("ERROR: AWS credentials not found in environment")
            print("Please check your .env file contains AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
            sys.exit(1)
            
        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=self.aws_access_key,
                aws_secret_access_key=self.aws_secret_key,
                region_name='ap-southeast-2'
            )
            print(f"Connected to S3 bucket: {bucket_name}")
        except Exception as e:
            print(f"ERROR: Failed to connect to S3: {str(e)}")
            sys.exit(1)
        
        # Known DEM file extensions
        self.dem_extensions = {'.tif', '.tiff', '.gdb', '.hgt', '.dem', '.asc', '.bil'}
        
    def test_connection(self):
        """Test S3 connection and bucket access"""
        print("Testing S3 connection...")
        try:
            # Test bucket access
            response = self.s3_client.head_bucket(Bucket=self.bucket_name)
            print("SUCCESS: Bucket access confirmed")
            return True
        except Exception as e:
            print(f"ERROR: Cannot access bucket: {str(e)}")
            return False
    
    def scan_top_level(self):
        """Scan top-level folders in bucket"""
        print("Scanning top-level folders...")
        
        try:
            # List objects with delimiter to get folders
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Delimiter='/',
                MaxKeys=100
            )
            
            folders = []
            if 'CommonPrefixes' in response:
                for prefix in response['CommonPrefixes']:
                    folder_name = prefix['Prefix'].rstrip('/')
                    folders.append(folder_name)
                    
            print(f"Found {len(folders)} top-level folders:")
            for folder in sorted(folders):
                print(f"  - {folder}")
                
            return folders
            
        except Exception as e:
            print(f"ERROR: Failed to scan folders: {str(e)}")
            return []
    
    def explore_folder(self, folder_path, max_depth=6, max_files=500):
        """Explore a specific folder structure"""
        print(f"\nExploring folder: {folder_path}")
        
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(
                Bucket=self.bucket_name,
                Prefix=f"{folder_path}/",
                MaxKeys=max_files
            )
            
            structure = defaultdict(list)
            dem_files = []
            file_count = 0
            
            for page in page_iterator:
                if 'Contents' not in page:
                    continue
                    
                for obj in page['Contents']:
                    file_count += 1
                    if file_count > max_files:
                        print(f"  (Limited to first {max_files} files)")
                        break
                        
                    key = obj['Key']
                    size_mb = obj['Size'] / (1024 * 1024)
                    
                    # Skip the folder itself
                    if key == f"{folder_path}/":
                        continue
                    
                    # Get relative path from folder
                    relative_path = key[len(folder_path)+1:]
                    path_parts = relative_path.split('/')
                    
                    # Track depth
                    depth = len(path_parts)
                    # Don't skip files based on depth, we want to find DEM files wherever they are
                    
                    # Check if it's a DEM file
                    filename = path_parts[-1]
                    if '.' in filename:
                        ext = '.' + filename.split('.')[-1].lower()
                        if ext in self.dem_extensions:
                            dem_files.append({
                                'filename': filename,
                                'path': relative_path,
                                'size_mb': round(size_mb, 2),
                                'extension': ext
                            })
                    
                    # Track folder structure
                    if depth <= 2:  # Only track first 2 levels
                        folder_key = '/'.join(path_parts[:min(2, len(path_parts)-1)]) if len(path_parts) > 1 else 'root'
                        structure[folder_key].append(filename if depth == 1 else path_parts[0])
                
                if file_count > max_files:
                    break
            
            # Print structure
            if structure:
                print(f"  Folder structure (first {max_depth} levels):")
                for folder, items in sorted(structure.items()):
                    unique_items = sorted(set(items))[:10]  # Show first 10 unique items
                    print(f"    {folder}/: {len(unique_items)} items")
                    for item in unique_items[:5]:  # Show first 5
                        print(f"      - {item}")
                    if len(unique_items) > 5:
                        print(f"      ... and {len(unique_items)-5} more")
            
            # Print DEM files
            if dem_files:
                print(f"  Found {len(dem_files)} DEM files:")
                for dem in dem_files[:10]:  # Show first 10
                    print(f"    - {dem['filename']} ({dem['size_mb']} MB)")
                if len(dem_files) > 10:
                    print(f"    ... and {len(dem_files)-10} more DEM files")
            else:
                print("  No DEM files found in this folder")
                
            return structure, dem_files
            
        except Exception as e:
            print(f"ERROR: Failed to explore folder {folder_path}: {str(e)}")
            return {}, []
    
    def generate_config_suggestion(self, folders, dem_data):
        """Generate suggested DEM_SOURCES configuration"""
        print("\nGenerating configuration suggestions...")
        
        suggested_sources = {}
        
        for folder in folders:
            structure, dem_files = dem_data.get(folder, ({}, []))
            
            if not dem_files:
                continue
                
            # Look for resolution patterns in folder structure
            resolution_hint = "unknown"
            crs_hint = "EPSG:3577"  # Default Australian Albers
            
            folder_lower = folder.lower()
            
            # Detect resolution
            if "50cm" in folder_lower or "0.5m" in folder_lower:
                resolution_hint = "50cm"
            elif "1m" in folder_lower:
                resolution_hint = "1m"
            elif "2m" in folder_lower:
                resolution_hint = "2m"
            elif "5m" in folder_lower:
                resolution_hint = "5m"
            
            # Detect CRS from zones
            if "z55" in folder_lower:
                crs_hint = "EPSG:28355"
            elif "z56" in folder_lower:
                crs_hint = "EPSG:28356"
            elif "z54" in folder_lower:
                crs_hint = "EPSG:28354"
            
            # Create source ID
            source_id = folder.replace('-', '_').replace('/', '_').lower()
            if resolution_hint != "unknown":
                source_id += f"_{resolution_hint}"
            
            total_size_mb = sum(dem['size_mb'] for dem in dem_files)
            
            suggested_sources[source_id] = {
                "path": f"s3://{self.bucket_name}/{folder}/",
                "layer": None,
                "crs": crs_hint,
                "description": f"{folder} - {len(dem_files)} DEM files (~{total_size_mb:.0f}MB total)"
            }
        
        return suggested_sources
    
    def export_config(self, suggested_sources):
        """Export configuration to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Export as environment variable format
        config_file = f"dem_sources_config_{timestamp}.txt"
        with open(config_file, 'w') as f:
            f.write("# DEM_SOURCES configuration for .env file\n")
            f.write("# Generated by S3 structure explorer\n\n")
            f.write("DEM_SOURCES=")
            f.write(json.dumps(suggested_sources, separators=(',', ':')))
            f.write("\n")
        
        print(f"\nConfiguration exported to: {config_file}")
        print("Copy the DEM_SOURCES line to your .env file")
        
        return config_file

def main():
    """Main execution"""
    bucket_name = os.getenv('AWS_S3_BUCKET_NAME', 'road-engineering-elevation-data')
    
    print("S3 Structure Explorer")
    print("=" * 40)
    print(f"Target bucket: {bucket_name}")
    
    # Initialize explorer
    explorer = SimpleS3Explorer(bucket_name)
    
    # Test connection
    if not explorer.test_connection():
        print("Connection test failed. Exiting.")
        sys.exit(1)
    
    # Scan top-level folders
    folders = explorer.scan_top_level()
    
    if not folders:
        print("No folders found in bucket")
        sys.exit(1)
    
    # Explore each folder
    print("\n" + "=" * 40)
    print("EXPLORING FOLDER STRUCTURES")
    print("=" * 40)
    
    dem_data = {}
    for folder in folders:
        structure, dem_files = explorer.explore_folder(folder, max_depth=4, max_files=100)
        dem_data[folder] = (structure, dem_files)
    
    # Generate configuration suggestions
    suggested_sources = explorer.generate_config_suggestion(folders, dem_data)
    
    if suggested_sources:
        print("\n" + "=" * 40)
        print("SUGGESTED CONFIGURATION")
        print("=" * 40)
        
        for source_id, config in suggested_sources.items():
            print(f"\n{source_id}:")
            print(f"  Path: {config['path']}")
            print(f"  CRS: {config['crs']}")
            print(f"  Description: {config['description']}")
        
        # Export configuration
        config_file = explorer.export_config(suggested_sources)
        
        print(f"\nSUCCESS: S3 exploration complete!")
        print(f"Next steps:")
        print(f"1. Review the suggested configuration above")
        print(f"2. Copy the DEM_SOURCES line from {config_file} to your .env file")
        print(f"3. Test with: python scripts/test_connections_simplified.py")
    else:
        print("\nNo DEM files found in bucket")

if __name__ == "__main__":
    main()