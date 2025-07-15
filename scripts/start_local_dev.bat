@echo off
echo Starting DEM Backend in Local Development Mode...
echo.

REM Switch to local environment
python scripts\switch_environment.py local

echo.
echo Environment switched to LOCAL mode
echo DEM Sources: Local DTM only (no S3 costs)
echo.

REM Start the service
echo Starting service on http://localhost:8001
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload