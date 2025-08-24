#!/usr/bin/env python3
"""
Railway startup script with detailed logging for debugging deployment issues.
This script will help us understand where the deployment is failing.
"""

import sys
import os
import logging
import traceback
from datetime import datetime

# Set up basic logging immediately
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | RAILWAY_STARTUP | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def main():
    """Main startup function with detailed error reporting."""
    try:
        logger.info("=== RAILWAY STARTUP BEGINNING ===")
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Python path: {sys.path[:3]}")
        logger.info(f"Current working directory: {os.getcwd()}")
        logger.info(f"Environment variables:")
        for key in ['APP_ENV', 'PORT', 'PYTHONPATH', 'LOG_LEVEL']:
            logger.info(f"  {key} = {os.getenv(key, 'NOT_SET')}")
        
        logger.info("Step 1: Attempting to import FastAPI and uvicorn...")
        import uvicorn
        from fastapi import FastAPI
        logger.info("✅ FastAPI and uvicorn imported successfully")
        
        logger.info("Step 2: Attempting to import src.main...")
        from src.main import app
        logger.info("✅ src.main imported successfully")
        logger.info(f"App type: {type(app)}")
        
        logger.info("Step 3: Getting configuration...")
        port = int(os.getenv('PORT', '8001'))
        host = '0.0.0.0'
        logger.info(f"Will start server on {host}:{port}")
        
        logger.info("Step 4: Starting uvicorn server...")
        uvicorn.run(
            app, 
            host=host, 
            port=port,
            log_level="info"
        )
        
    except ImportError as e:
        logger.error(f"❌ IMPORT ERROR: {e}")
        logger.error(f"Module path: {e.name if hasattr(e, 'name') else 'unknown'}")
        logger.error("Traceback:")
        logger.error(traceback.format_exc())
        sys.exit(1)
        
    except Exception as e:
        logger.error(f"❌ STARTUP ERROR: {e}")
        logger.error("Full traceback:")
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()