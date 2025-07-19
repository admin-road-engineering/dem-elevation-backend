#!/usr/bin/env python3
"""
DEM Source Management CLI
Simple command-line interface for managing DEM sources
"""
import sys
import json
from pathlib import Path

# Add src to path  
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def show_help():
    print("""
DEM Source Management CLI
========================

Commands:
  discover    - Scan S3 bucket and discover all available sources
  validate    - Validate current configuration against S3 reality  
  monitor     - Test geographic coverage with key coordinates
  status      - Show current source configuration status
  add         - Interactive tool to add new sources
  help        - Show this help message

Examples:
  python scripts/dem_source_cli.py discover
  python scripts/dem_source_cli.py validate
  python scripts/dem_source_cli.py monitor
""")

def cmd_discover():
    """Run S3 bucket discovery"""
    print("🔍 Discovering S3 DEM sources...")
    import subprocess
    result = subprocess.run([sys.executable, "scripts/s3_bucket_scanner.py"], 
                          capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print("Errors:", result.stderr)

def cmd_validate():
    """Validate current configuration"""
    print("✅ Validating current configuration...")
    import subprocess
    result = subprocess.run([sys.executable, "scripts/quick_source_discovery.py"], 
                          capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print("Errors:", result.stderr)

def cmd_monitor():
    """Test geographic coverage"""
    print("📍 Testing geographic coverage...")
    import subprocess
    result = subprocess.run([sys.executable, "scripts/source_monitoring.py"], 
                          capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print("Errors:", result.stderr)

def cmd_status():
    """Show current status"""
    try:
        from config import Settings
        settings = Settings()
        
        print("📊 Current DEM Source Status")
        print("=" * 40)
        print(f"Total sources: {len(settings.DEM_SOURCES)}")
        print(f"S3 sources enabled: {settings.USE_S3_SOURCES}")
        print(f"API sources enabled: {settings.USE_API_SOURCES}")
        print()
        
        print("Configured sources:")
        for source_id, source_config in settings.DEM_SOURCES.items():
            path = source_config.get('path', 'Unknown')
            desc = source_config.get('description', 'No description')
            if 's3://' in path:
                print(f"  [S3] {source_id}: {desc}")
            elif 'api://' in path:
                print(f"  [API] {source_id}: {desc}")
            else:
                print(f"  [LOCAL] {source_id}: {desc}")
        
        print()
        print("Quick test coordinates:")
        from dem_service import DEMService
        
        service = DEMService(settings)
        test_coords = [
            ("Brisbane", -27.4698, 153.0251),
            ("Bendigo", -36.7570, 144.2794)
        ]
        
        for name, lat, lon in test_coords:
            try:
                elevation, source, error = service.get_elevation_at_point(lat, lon)
                if elevation:
                    print(f"  {name}: {elevation:.1f}m via {source}")
                else:
                    print(f"  {name}: FAILED - {error}")
            except Exception as e:
                print(f"  {name}: ERROR - {e}")
                
    except Exception as e:
        print(f"Error getting status: {e}")

def cmd_add():
    """Interactive source addition"""
    print("📂 Interactive DEM Source Addition")
    print("=" * 40)
    print()
    print("This tool helps you add new DEM sources following the complete protocol.")
    print("You'll need:")
    print("  - Source ID (unique identifier)")
    print("  - S3 path or API path")
    print("  - Geographic bounds (lat/lon)")
    print("  - CRS (coordinate reference system)")
    print("  - Resolution and metadata")
    print()
    
    # Get source details interactively
    source_id = input("Source ID (e.g., 'new_qld_region'): ").strip()
    if not source_id:
        print("Source ID is required.")
        return
    
    name = input("Display name (e.g., 'Queensland Region LiDAR'): ").strip()
    if not name:
        name = source_id.replace('_', ' ').title()
    
    path = input("S3 path (e.g., 's3://bucket/path/'): ").strip()
    if not path:
        print("Path is required.")
        return
    
    crs = input("CRS (e.g., 'EPSG:32756'): ").strip()
    if not crs:
        crs = "EPSG:4326"
    
    try:
        resolution = float(input("Resolution in meters (e.g., 1.0): ").strip() or "1.0")
    except ValueError:
        resolution = 1.0
    
    print("\nGeographic bounds (decimal degrees):")
    try:
        min_lat = float(input("  Minimum latitude: ").strip())
        max_lat = float(input("  Maximum latitude: ").strip())
        min_lon = float(input("  Minimum longitude: ").strip())
        max_lon = float(input("  Maximum longitude: ").strip())
    except ValueError:
        print("Invalid coordinates entered.")
        return
    
    provider = input("Provider (e.g., 'GA', 'CSIRO'): ").strip() or "Unknown"
    data_type = input("Data type (e.g., 'LiDAR', 'DEM'): ").strip() or "DEM"
    
    # Create source definition
    new_source = {
        "id": source_id,
        "name": name,
        "path": path,
        "crs": crs,
        "resolution_m": resolution,
        "bounds": {
            "min_lat": min_lat,
            "max_lat": max_lat,
            "min_lon": min_lon,
            "max_lon": max_lon
        },
        "provider": provider,
        "data_type": data_type,
        "priority": 1,
        "capture_date": "Unknown",
        "point_density": "Unknown",
        "vertical_datum": "AHD"
    }
    
    print("\nSource definition:")
    print(json.dumps(new_source, indent=2))
    print()
    
    confirm = input("Add this source? (y/N): ").strip().lower()
    if confirm == 'y':
        try:
            from add_new_dem_sources import DEMSourceManager
            
            manager = DEMSourceManager()
            results = manager.add_new_sources_complete_protocol([new_source])
            
            if results["success"]:
                print("\n✅ Source added successfully!")
                print("Steps completed:", ", ".join(results["steps_completed"]))
                
                if "next_steps" in results:
                    print("\nNext steps:")
                    for step in results["next_steps"]:
                        print(f"  - {step}")
            else:
                print("\n❌ Failed to add source:")
                for error in results["errors"]:
                    print(f"  - {error}")
                    
                if results.get("rollback_attempted"):
                    print("Configuration has been rolled back.")
                    
        except Exception as e:
            print(f"\n❌ Error adding source: {e}")
    else:
        print("Source addition cancelled.")

def main():
    """Main CLI function"""
    if len(sys.argv) < 2:
        show_help()
        return
    
    command = sys.argv[1].lower()
    
    if command == "discover":
        cmd_discover()
    elif command == "validate":
        cmd_validate()
    elif command == "monitor":
        cmd_monitor()
    elif command == "status":
        cmd_status()
    elif command == "add":
        cmd_add()
    elif command == "help":
        show_help()
    else:
        print(f"Unknown command: {command}")
        show_help()

if __name__ == "__main__":
    main()