@echo off
echo Switching to Production Environment...
python scripts\switch_environment.py production

echo.
echo Environment switched to PRODUCTION mode
echo DEM Sources: Full S3 + APIs + Local fallback
echo.
echo WARNING: This mode may incur S3 and API costs!
echo To start the service: uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload