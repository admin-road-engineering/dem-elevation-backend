@echo off
title DEM Backend Server (S3 Cloud Storage)
color 0A

echo ========================================
echo    DEM ELEVATION BACKEND SERVER
echo       (Cloud Storage - Amazon S3)
echo ========================================
echo.
echo Starting DEM Backend Service...
echo Location: %~dp0..
echo Port: 8001
echo Storage: Amazon S3 (roadengineer-dem-files)
echo.

REM Change to the parent directory (project root)
cd /d "%~dp0.."

REM Check if .env file exists
if not exist ".env" (
    echo ERROR: .env file not found
    echo Please create a .env file with your AWS credentials
    echo Copy from env.example and add your AWS keys
    pause
    exit /b 1
)

REM Set AWS environment variables from .env file
echo Loading AWS credentials from .env file...
for /f "tokens=1,2 delims==" %%a in ('type .env ^| findstr /v "^#" ^| findstr /v "^$"') do (
    if "%%a"=="AWS_ACCESS_KEY_ID" set AWS_ACCESS_KEY_ID=%%b
    if "%%a"=="AWS_SECRET_ACCESS_KEY" set AWS_SECRET_ACCESS_KEY=%%b
    if "%%a"=="AWS_S3_BUCKET_NAME" set AWS_S3_BUCKET_NAME=%%b
)

REM Verify AWS credentials are set
if "%AWS_ACCESS_KEY_ID%"=="" (
    echo ERROR: AWS_ACCESS_KEY_ID not found in .env file
    pause
    exit /b 1
)
if "%AWS_SECRET_ACCESS_KEY%"=="" (
    echo ERROR: AWS_SECRET_ACCESS_KEY not found in .env file
    pause
    exit /b 1
)
if "%AWS_S3_BUCKET_NAME%"=="" (
    echo ERROR: AWS_S3_BUCKET_NAME not found in .env file
    pause
    exit /b 1
)

echo ✓ AWS credentials loaded successfully
echo   Bucket: %AWS_S3_BUCKET_NAME%
echo   Access Key: %AWS_ACCESS_KEY_ID:~0,4%...
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
python -c "import rasterio, fastapi, uvicorn, boto3" >nul 2>&1
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