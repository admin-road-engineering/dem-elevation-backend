#!/usr/bin/env python3
"""
Validate production-like imports to catch issues before deployment.
This script mimics how Railway/production would import the application.
"""

import sys
import importlib
import traceback
from pathlib import Path

# Add the project root to Python path (like production would)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_import(module_name, description):
    """Test importing a module and report results."""
    try:
        module = importlib.import_module(module_name)
        print(f"PASS {description}: {module_name}")
        return True
    except Exception as e:
        print(f"FAIL {description}: {module_name}")
        print(f"   Error: {e}")
        traceback.print_exc()
        return False

def main():
    """Run production import validation."""
    print("Production Import Validation")
    print("=" * 50)
    
    all_passed = True
    
    # Test critical imports
    tests = [
        ("src.main", "Main application"),
        ("src.api.v1.endpoints", "Main elevation endpoints"),
        ("src.api.v1.campaigns_endpoints", "Campaign endpoints"),
        ("src.api.v1.dataset_endpoints", "Dataset endpoints"),
        ("src.models", "Models package"),
        ("src.config", "Configuration"),
        ("src.unified_elevation_service", "Elevation service"),
        ("src.index_driven_source_selector", "Index-driven selector"),
    ]
    
    for module_name, description in tests:
        if not test_import(module_name, description):
            all_passed = False
    
    print("=" * 50)
    
    if all_passed:
        print("SUCCESS: All imports passed! Safe to deploy to production.")
        
        # Test app instantiation
        try:
            from src.main import app
            print("SUCCESS: FastAPI app instantiation successful")
        except Exception as e:
            print(f"ERROR: FastAPI app instantiation failed: {e}")
            all_passed = False
            
    else:
        print("ERROR: Import failures detected! DO NOT deploy to production.")
        return 1
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    exit(main())