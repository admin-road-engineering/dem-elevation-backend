@echo off
title DEM Backend Server (Local Storage)
color 0A

echo ========================================
echo    DEM ELEVATION BACKEND SERVER
echo       (Local Storage - DTM.gdb)
echo ========================================
echo.
echo Starting DEM Backend Service...
echo Location: %~dp0..
echo Port: 8001
echo Storage: Local DTM (./data/DTM.gdb)
echo.

REM Change to the parent directory (project root)
cd /d "%~dp0.."

REM Activate the virtual environment
call .\.venv\Scripts\activate.bat

REM Check if .env file exists
if not exist ".env" (
    echo ERROR: .env file not found
    echo Please create a .env file with your DEM configuration
    echo Copy from env.example and update paths
    pause
    exit /b 1
)

REM Check if local DTM file exists
if not exist "./data/DTM.gdb" (
    echo ERROR: Local DTM file not found at ./data/DTM.gdb
    echo Please ensure your DTM.gdb file is in the correct location
    pause
    exit /b 1
)

echo ✓ Local DTM file found at ./data/DTM.gdb
echo ✓ Configuration file (.env) found
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python or add it to your system PATH
    pause
    exit /b 1
)

REM Check if main.py exists in src directory
if not exist "src\main.py" (
    echo ERROR: src\main.py not found
    echo Please run this batch file from the DEM Backend directory
    pause
    exit /b 1
)

REM Check if requirements are installed
python -c "import rasterio, fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo WARNING: Some required packages may not be installed
    echo Installing/updating requirements...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install requirements
        pause
        exit /b 1
    )
    echo.
)

echo Starting server on http://localhost:8001
echo API Documentation: http://localhost:8001/docs
echo.
echo *** Press Ctrl+C to stop the server ***
echo.

REM Start the server with the new module path
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload

REM If we reach here, the server stopped
echo.
echo Server stopped.
pause 