#!/usr/bin/env python3
"""
Simple Railway startup script that handles PORT variable properly
"""
import os
import sys

def main():
    # Get port from environment
    port = os.getenv("PORT", "8000")
    
    print(f"Starting DEM Backend on port {port}")
    
    # Launch uvicorn
    os.system(f"uvicorn src.main:app --host 0.0.0.0 --port {port} --workers 1")

if __name__ == "__main__":
    main()