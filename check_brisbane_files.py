#!/usr/bin/env python3
"""
Check what Brisbane files actually exist in the unified index
"""
import asyncio
import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import Settings
from data_sources.unified_s3_source import UnifiedS3Source

async def check_brisbane_files():
    """Check what Brisbane files are actually available"""
    settings = Settings()
    
    # Load environment from .env
    import os
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
    
    source = UnifiedS3Source(settings, None)
    await source.initialize()
    
    if not source.unified_index:
        print("Failed to load unified index")
        return
        
    print(f"Loaded {len(source.unified_index.data_collections)} collections")
    
    # Find Brisbane collections
    brisbane_collections = []
    for collection in source.unified_index.data_collections:
        if 'brisbane' in collection.id.lower():
            brisbane_collections.append(collection)
    
    print(f"\nFound {len(brisbane_collections)} Brisbane collections:")
    
    for collection in brisbane_collections:
        print(f"\n=== Collection: {collection.id} ===")
        print(f"Type: {collection.collection_type}")
        print(f"File count: {collection.file_count}")
        
        if hasattr(collection, 'files') and collection.files:
            print("Sample files:")
            for i, file_entry in enumerate(collection.files[:3]):
                print(f"  {i+1}. {file_entry.file}")
                if hasattr(file_entry, 'bounds') and file_entry.bounds:
                    print(f"     Bounds: {file_entry.bounds}")
    
    # Test Brisbane coordinates against these collections
    brisbane_lat, brisbane_lon = -27.4698, 153.0251
    print(f"\n=== Testing coordinates ({brisbane_lat}, {brisbane_lon}) ===")
    
    for collection in brisbane_collections[:2]:  # Test first 2 collections
        print(f"\nTesting collection: {collection.id}")
        
        # Use collection handler to find files
        from handlers.collection_handlers import CollectionHandlerRegistry
        handler_registry = CollectionHandlerRegistry()
        
        candidate_files = handler_registry.find_files_for_coordinate(collection, brisbane_lat, brisbane_lon)
        print(f"Found {len(candidate_files)} candidate files")
        
        for file_entry in candidate_files[:2]:
            print(f"  File: {file_entry.file}")
            if hasattr(file_entry, 'bounds'):
                print(f"  Bounds: {file_entry.bounds}")

if __name__ == "__main__":
    asyncio.run(check_brisbane_files())