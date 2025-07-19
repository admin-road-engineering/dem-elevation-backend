#!/usr/bin/env python3
"""
Wrapper to run API test plan with proper imports
"""
import sys
import os
from pathlib import Path

# Set up path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Define __file__ for the exec context
globals_dict = globals().copy()
globals_dict['__file__'] = str(Path(__file__).parent / "scripts" / "test_api_plan.py")

# Read and execute the test script
with open('scripts/test_api_plan.py', 'r', encoding='utf-8') as f:
    exec(f.read(), globals_dict)