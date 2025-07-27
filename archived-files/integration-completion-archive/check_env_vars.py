#!/usr/bin/env python3
import os

required_files = [
    os.getenv("S3_CAMPAIGN_INDEX_KEY", "indexes/campaign_index.json"),
    os.getenv("S3_TILED_INDEX_KEY", "indexes/phase3_brisbane_tiled_index.json"), 
    os.getenv("S3_SPATIAL_INDEX_KEY", "indexes/spatial_index.json")
]

print("Updated required files:")
for f in required_files:
    print(f"  - {f}")