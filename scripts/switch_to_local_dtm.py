#!/usr/bin/env python3
"""
Helper script to switch from S3 DTM to local DTM configuration.
Run this script to see the exact changes needed in your .env file.
"""

print("=" * 80)
print("SWITCHING FROM S3 TO LOCAL DTM - Configuration Changes Needed")
print("=" * 80)

print("\n1. Open your .env file in a text editor")
print("\n2. Find the DEM_SOURCES line and replace it with:")
print("\nOLD (S3 configuration):")
print('DEM_SOURCES={"local_dtm_gdb": {"path": "s3://roadengineer-dem-files/DTM.gdb", ...}')

print("\nNEW (Local configuration):")
local_config = '''DEM_SOURCES={"local_dtm_gdb": {"path": "./data/source/DTM.gdb", "layer": null, "crs": null, "description": "Local DTM from geodatabase - auto-discovery enabled"}, "converted_dtm": {"path": "./data/dems/dtm.tif", "layer": null, "crs": null, "description": "Converted DTM in GeoTIFF format"}, "lidar_dtm": {"path": "./data/source/LiDAR.gdb", "layer": "DTM_1m", "crs": "EPSG:28356", "description": "High resolution LiDAR DTM with specific layer"}}'''
print(local_config)

print("\n3. Change the DEFAULT_DEM_ID to:")
print("DEFAULT_DEM_ID=local_dtm_gdb")

print("\n4. Comment out or remove the AWS S3 configuration lines:")
print("# AWS_S3_BUCKET_NAME=roadengineer-dem-files")
print("# AWS_ACCESS_KEY_ID=YOUR_READ_ONLY_ACCESS_KEY_ID")
print("# AWS_SECRET_ACCESS_KEY=YOUR_READ_ONLY_SECRET_ACCESS_KEY")

print("\n" + "=" * 80)
print("SUMMARY OF CHANGES:")
print("=" * 80)
print("✓ Switch DTM path from S3 to local: ./data/source/DTM.gdb")
print("✓ Set default DEM to local_dtm_gdb")
print("✓ Disable AWS S3 configuration")
print("✓ Keep local fallback options (converted_dtm, lidar_dtm)")

print("\nAfter making these changes, restart your DEM backend service.")
print("The service will now use your local DTM.gdb file instead of S3.")

# Also create a backup .env with the new configuration
backup_config = """# DEM Elevation Service Configuration
# Updated to use local DTM instead of S3

# Configure DEM sources (supports both GeoTIFF and Geodatabase formats)
# Note: JSON must be on a single line in .env files
DEM_SOURCES={"local_dtm_gdb": {"path": "./data/source/DTM.gdb", "layer": null, "crs": null, "description": "Local DTM from geodatabase - auto-discovery enabled"}, "converted_dtm": {"path": "./data/dems/dtm.tif", "layer": null, "crs": null, "description": "Converted DTM in GeoTIFF format"}, "lidar_dtm": {"path": "./data/source/LiDAR.gdb", "layer": "DTM_1m", "crs": "EPSG:28356", "description": "High resolution LiDAR DTM with specific layer"}}

# Set the default DEM source to use local DTM
DEFAULT_DEM_ID=local_dtm_gdb

# Geodatabase settings (optional)
GDB_AUTO_DISCOVER=true
GDB_PREFERRED_DRIVERS=OpenFileGDB,FileGDB

# Thread pool executor settings for async operations
MAX_WORKER_THREADS=20

# Cache settings for opened datasets (number of recently used datasets to keep open)
DATASET_CACHE_SIZE=10

# GDAL Error Handling Configuration
# Set to false to see all GDAL error messages (useful for debugging)
SUPPRESS_GDAL_ERRORS=true
GDAL_LOG_LEVEL=ERROR

# Google Elevation API Configuration (Fallback - Keep for hybrid approach)
# GOOGLE_ELEVATION_API_KEY=YOUR_GOOGLE_API_KEY

# AWS S3 Configuration (commented out - no longer needed for local DTM)
# AWS_S3_BUCKET_NAME=roadengineer-dem-files
# AWS_ACCESS_KEY_ID=YOUR_READ_ONLY_ACCESS_KEY_ID
# AWS_SECRET_ACCESS_KEY=YOUR_READ_ONLY_SECRET_ACCESS_KEY
"""

with open('.env.local', 'w') as f:
    f.write(backup_config)

print(f"\n📁 I've also created a '.env.local' file with the new configuration.")
print("You can copy this over your existing .env file if needed.") 