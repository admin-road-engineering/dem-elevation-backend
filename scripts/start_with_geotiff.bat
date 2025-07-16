@echo off
echo Starting DEM Backend with GeoTIFF configuration...

REM Set environment variable to use GeoTIFF
set DEFAULT_DEM_ID=local_converted

REM Activate conda environment
call "C:\Users\Admin\miniconda3\Scripts\activate.bat" dem-backend-fixed

REM Verify environment variable is set
echo Current DEFAULT_DEM_ID: %DEFAULT_DEM_ID%

REM Start server with detailed logging
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload --log-level info

pause