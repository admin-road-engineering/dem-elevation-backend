#!/usr/bin/env python3
"""
Australian Government DEM Data Availability Checker

This script helps identify what higher-resolution DEM data is available
from Australian government sources for your specific area of interest.
"""

import requests
import json
from typing import Dict, List, Any

# Gold Coast bounding box for testing
GOLD_COAST_BOUNDS = {
    "west": 153.35,
    "south": -28.15,
    "east": 153.55,
    "north": -27.95
}

def check_geoscience_australia_data():
    """Check Geoscience Australia for available DEM products."""
    print("🇦🇺 Checking Geoscience Australia DEM Products...")
    print("=" * 60)
    
    # Known Geoscience Australia DEM products
    ga_products = [
        {
            "name": "1 Second SRTM Derived Digital Elevation Model Version 1.0",
            "resolution": "~30m",
            "coverage": "National",
            "url": "https://ecat.ga.gov.au/geonetwork/srv/api/records/a05f7892-eae3-7506-e044-00144fdd4fa6",
            "precision": "Low-Medium (often quantized to 1m intervals)",
            "format": "GeoTIFF"
        },
        {
            "name": "1 Second SRTM Derived Hydrologically Enforced Digital Elevation Model",
            "resolution": "~30m", 
            "coverage": "National",
            "url": "https://ecat.ga.gov.au/geonetwork/srv/api/records/a05f7892-eae1-7506-e044-00144fdd4fa6",
            "precision": "Low-Medium (hydrologically corrected)",
            "format": "GeoTIFF"
        },
        {
            "name": "National Digital Elevation Model 1 Arc Second Hydrologically Enforced",
            "resolution": "~30m",
            "coverage": "National", 
            "url": "https://ecat.ga.gov.au/geonetwork/srv/eng/catalog.search#/metadata/89644",
            "precision": "Medium (improved processing)",
            "format": "GeoTIFF"
        }
    ]
    
    for product in ga_products:
        print(f"📊 {product['name']}")
        print(f"   Resolution: {product['resolution']}")
        print(f"   Coverage: {product['coverage']}")
        print(f"   Precision: {product['precision']}")
        print(f"   Format: {product['format']}")
        print(f"   Info: {product['url']}")
        print()

def check_queensland_government_data():
    """Check Queensland Government for available DEM products."""
    print("🏛️ Queensland Government DEM Products...")
    print("=" * 60)
    
    qld_products = [
        {
            "name": "Queensland LiDAR Data",
            "resolution": "0.5m - 2m",
            "coverage": "Selected urban areas, Gold Coast included",
            "source": "QSpatial",
            "url": "https://www.qld.gov.au/environment/land/management/mapping/spatial-data",
            "precision": "High (raw LiDAR often has cm-level precision)",
            "format": "LAZ point clouds, DEM rasters"
        },
        {
            "name": "Elvis Elevation Data",
            "resolution": "Variable (1m-5m)",
            "coverage": "Statewide coverage available",
            "source": "Elvis Portal",
            "url": "https://elevation.fsdf.org.au/",
            "precision": "Medium-High (varies by source)",
            "format": "Various (GeoTIFF, LAZ)"
        },
        {
            "name": "Queensland Globe High Resolution Data",
            "resolution": "1m-2m",
            "coverage": "Urban areas, including Gold Coast",
            "source": "Queensland Government",
            "url": "https://qldglobe.information.qld.gov.au/",
            "precision": "High for urban areas",
            "format": "Web services, downloadable tiles"
        }
    ]
    
    for product in qld_products:
        print(f"📊 {product['name']}")
        print(f"   Resolution: {product['resolution']}")
        print(f"   Coverage: {product['coverage']}")
        print(f"   Source: {product['source']}")
        print(f"   Precision: {product['precision']}")
        print(f"   Format: {product['format']}")
        print(f"   Info: {product['url']}")
        print()

def check_elvis_portal():
    """Check the Elvis portal for specific elevation data."""
    print("🚁 Elvis Elevation Portal Check...")
    print("=" * 60)
    print("The Elvis portal (https://elevation.fsdf.org.au/) provides:")
    print("• LiDAR point clouds (highest precision)")
    print("• Photogrammetric point clouds")
    print("• Digital Elevation Models at various resolutions")
    print("• Coverage maps showing data availability")
    print()
    print("For Gold Coast area, you should look for:")
    print("• 1m LiDAR DEM")
    print("• 0.5m LiDAR DEM (if available)")
    print("• Raw LiDAR point clouds (.las/.laz files)")
    print()

def provide_data_access_instructions():
    """Provide instructions for accessing higher-resolution data."""
    print("💡 How to Access Higher-Resolution Data:")
    print("=" * 60)
    
    steps = [
        {
            "step": 1,
            "title": "Visit Elvis Portal",
            "action": "Go to https://elevation.fsdf.org.au/",
            "detail": "Search for your Gold Coast coordinates (-28.002, 153.414)"
        },
        {
            "step": 2, 
            "title": "Check Available Data",
            "action": "Use the coverage map to see what's available",
            "detail": "Look for LiDAR datasets with resolution < 2m"
        },
        {
            "step": 3,
            "title": "Request Access",
            "action": "Download or request access to higher-resolution datasets", 
            "detail": "Some data may require registration or have usage agreements"
        },
        {
            "step": 4,
            "title": "Contact Data Providers Directly",
            "action": "Email Queensland Spatial team or Geoscience Australia",
            "detail": "Request: 'raw LiDAR point clouds for Gold Coast area for engineering applications'"
        },
        {
            "step": 5,
            "title": "Check Local Council Data",
            "action": "Contact Gold Coast City Council directly",
            "detail": "Local councils often have the highest-resolution survey data"
        }
    ]
    
    for step in steps:
        print(f"Step {step['step']}: {step['title']}")
        print(f"   Action: {step['action']}")
        print(f"   Detail: {step['detail']}")
        print()

def suggest_precision_workarounds():
    """Suggest workarounds for precision limitations."""
    print("🔧 Workarounds for Existing Government Data:")
    print("=" * 60)
    
    workarounds = [
        {
            "approach": "Use Multiple Sources",
            "description": "Configure your system to use multiple DEM sources",
            "implementation": "Modify DEM_SOURCES in .env to include multiple datasets",
            "benefit": "Higher resolution data where available, fallback for gaps"
        },
        {
            "approach": "Nearest Neighbor Sampling", 
            "description": "Switch from bilinear to nearest neighbor interpolation",
            "implementation": "Modify dem_service.py to use pixel-center values",
            "benefit": "Shows actual DEM values without interpolation smoothing"
        },
        {
            "approach": "Raw Pixel Inspection",
            "description": "Add functionality to inspect surrounding pixel values",
            "implementation": "Add methods to examine 3x3 windows around sample points",
            "benefit": "Understand the underlying data precision patterns"
        },
        {
            "approach": "Statistical Sampling",
            "description": "Sample multiple nearby points and analyze distribution",
            "implementation": "Take 5-10 samples within 1m radius and analyze statistics",
            "benefit": "Better understanding of local terrain variation vs. data quantization"
        }
    ]
    
    for approach in workarounds:
        print(f"🛠️  {approach['approach']}")
        print(f"   Description: {approach['description']}")
        print(f"   Implementation: {approach['implementation']}")
        print(f"   Benefit: {approach['benefit']}")
        print()

def main():
    """Run the DEM availability checker."""
    print("🗺️  Australian Government DEM Data Availability Checker")
    print("=" * 80)
    print("Checking available high-precision elevation data for your area...")
    print()
    
    check_geoscience_australia_data()
    check_queensland_government_data()
    check_elvis_portal()
    provide_data_access_instructions()
    suggest_precision_workarounds()
    
    print("📞 KEY CONTACTS:")
    print("=" * 60)
    print("• Elvis Portal Support: elvis@ga.gov.au")
    print("• Geoscience Australia: clientservices@ga.gov.au") 
    print("• Queensland Spatial: qspatial@resources.qld.gov.au")
    print("• Gold Coast City Council: mail@goldcoast.qld.gov.au")
    print()
    
    print("💰 COST CONSIDERATIONS:")
    print("=" * 60)
    print("• Most government data is free for non-commercial use")
    print("• Some high-resolution datasets may have licensing costs")
    print("• Raw LiDAR data is often free but requires processing")
    print("• Commercial licenses may be required for business use")

if __name__ == "__main__":
    main() 