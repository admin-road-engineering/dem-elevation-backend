@echo off
echo Switching to API Testing Environment...
python scripts\switch_environment.py api-test

echo.
echo Environment switched to API-TEST mode
echo DEM Sources: GPXZ API + NZ Open Data + Local fallback
echo.
echo To start the service: uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload