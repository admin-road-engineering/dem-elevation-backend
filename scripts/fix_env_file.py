#!/usr/bin/env python3
"""
Fix .env file formatting issues
"""

from pathlib import Path

def fix_env_file():
    """Fix the .env file by putting DEM_SOURCES on a single line"""
    env_file = Path(__file__).parent.parent / ".env"
    
    print("Fixing .env file formatting...")
    print(f"File: {env_file}")
    
    # Read current content
    with open(env_file, 'r') as f:
        lines = f.readlines()
    
    new_lines = []
    in_dem_sources = False
    dem_sources_content = ""
    
    for line in lines:
        line = line.strip()
        
        # Skip empty lines and comments in DEM_SOURCES section
        if in_dem_sources and (not line or line.startswith('#')):
            continue
            
        if line.startswith('DEM_SOURCES='):
            in_dem_sources = True
            dem_sources_content = line
            continue
        elif in_dem_sources:
            if line and not line.startswith('#') and ('elvis' in line or 'total' in line):
                # Continue building the DEM_SOURCES line
                dem_sources_content += line
                continue
            else:
                # End of DEM_SOURCES, add the complete line
                in_dem_sources = False
                
                # Use the Elvis configuration we discovered
                elvis_config = '{"act_elvis":{"path":"s3://road-engineering-elevation-data/act-elvis/","layer":null,"crs":"EPSG:3577","description":"act-elvis - 100 DEM files (~3359MB total)"},"csiro_elvis":{"path":"s3://road-engineering-elevation-data/csiro-elvis/","layer":null,"crs":"EPSG:3577","description":"csiro-elvis - 100 DEM files (~180MB total)"},"dawe_elvis":{"path":"s3://road-engineering-elevation-data/dawe-elvis/","layer":null,"crs":"EPSG:3577","description":"dawe-elvis - 100 DEM files (~256MB total)"},"ga_elvis":{"path":"s3://road-engineering-elevation-data/ga-elvis/","layer":null,"crs":"EPSG:3577","description":"ga-elvis - 100 DEM files (~200MB total)"},"griffith_elvis":{"path":"s3://road-engineering-elevation-data/griffith-elvis/","layer":null,"crs":"EPSG:3577","description":"griffith-elvis - 98 DEM files (~614MB total)"},"local_dtm_gdb":{"path":"./data/DTM.gdb","layer":null,"crs":null,"description":"Local DTM geodatabase"},"converted_dtm":{"path":"./data/dems/dtm.tif","layer":null,"crs":null,"description":"Converted DTM in GeoTIFF format"}}'
                
                new_lines.append(f"DEM_SOURCES={elvis_config}\n")
                new_lines.append(f"{line}\n" if line else "\n")
        else:
            new_lines.append(f"{line}\n" if line else "\n")
    
    # If we ended while still in DEM_SOURCES
    if in_dem_sources:
        elvis_config = '{"act_elvis":{"path":"s3://road-engineering-elevation-data/act-elvis/","layer":null,"crs":"EPSG:3577","description":"act-elvis - 100 DEM files (~3359MB total)"},"csiro_elvis":{"path":"s3://road-engineering-elevation-data/csiro-elvis/","layer":null,"crs":"EPSG:3577","description":"csiro-elvis - 100 DEM files (~180MB total)"},"dawe_elvis":{"path":"s3://road-engineering-elevation-data/dawe-elvis/","layer":null,"crs":"EPSG:3577","description":"dawe-elvis - 100 DEM files (~256MB total)"},"ga_elvis":{"path":"s3://road-engineering-elevation-data/ga-elvis/","layer":null,"crs":"EPSG:3577","description":"ga-elvis - 100 DEM files (~200MB total)"},"griffith_elvis":{"path":"s3://road-engineering-elevation-data/griffith-elvis/","layer":null,"crs":"EPSG:3577","description":"griffith-elvis - 98 DEM files (~614MB total)"},"local_dtm_gdb":{"path":"./data/DTM.gdb","layer":null,"crs":null,"description":"Local DTM geodatabase"},"converted_dtm":{"path":"./data/dems/dtm.tif","layer":null,"crs":null,"description":"Converted DTM in GeoTIFF format"}}'
        new_lines.append(f"DEM_SOURCES={elvis_config}\n")
    
    # Write fixed content
    with open(env_file, 'w') as f:
        f.writelines(new_lines)
    
    print("Fixed .env file!")
    print("- Put DEM_SOURCES on single line")
    print("- Added Elvis configuration with local fallbacks")
    print("- Preserved all other settings")

if __name__ == "__main__":
    fix_env_file()