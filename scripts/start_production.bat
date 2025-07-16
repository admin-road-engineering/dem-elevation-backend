@echo off
title DEM Backend Server (Production Mode)
color 0C

echo ========================================
echo    DEM ELEVATION BACKEND SERVER
echo       PRODUCTION MODE - S3 + APIs
echo ========================================
echo.
echo WARNING: This mode incurs costs!
echo - AWS S3 data transfer charges
echo - GPXZ API usage (if configured)
echo.

REM Change to project root directory
cd /d "%~dp0\.."

REM Switch to production environment
echo Switching to production environment...
python scripts\switch_environment.py production
if errorlevel 1 (
    echo ERROR: Failed to switch to production environment
    echo Check that .env.production exists and is properly configured
    pause
    exit /b 1
)

echo.
echo ✓ Production environment activated
echo.

REM Verify critical environment variables
echo Verifying AWS credentials...
python -c "import os; assert os.getenv('AWS_ACCESS_KEY_ID'), 'AWS_ACCESS_KEY_ID not set'"
if errorlevel 1 (
    echo ERROR: AWS credentials not configured in .env file
    echo Please ensure AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are set
    pause
    exit /b 1
)

echo ✓ AWS credentials found
echo.

REM Check if conda environment is active (optional but recommended)
if defined CONDA_DEFAULT_ENV (
    echo Using conda environment: %CONDA_DEFAULT_ENV%
) else (
    echo Note: Running without conda environment
    echo Consider activating dem-backend-fixed for best compatibility
)

echo.
echo Starting production server on http://localhost:8001
echo API Documentation: http://localhost:8001/docs
echo.
echo *** Press Ctrl+C to stop the server ***
echo.

REM Start the server
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload

REM Server stopped
echo.
echo Production server stopped.
pause