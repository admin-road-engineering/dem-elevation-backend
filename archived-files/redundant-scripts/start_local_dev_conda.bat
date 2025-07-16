@echo off
echo Starting DEM Backend with Conda Environment...
echo.

REM Check if conda is available
conda --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Conda not found. Please install Miniconda first.
    echo Download from: https://docs.conda.io/en/latest/miniconda.html
    echo.
    echo Alternative: Run scripts\start_local_dev.bat for basic testing
    pause
    exit /b 1
)

REM Change to project root directory  
cd /d "%~dp0\.."

REM Check if conda environment exists
conda info --envs | findstr "dem-backend" >nul
if %errorlevel% neq 0 (
    echo Creating conda environment...
    conda env create -f environment.yml
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create conda environment
        pause
        exit /b 1
    )
)

echo Activating conda environment...
call conda activate dem-backend

echo Installing any missing packages...
pip install PyJWT

echo.
echo Switching to local environment configuration...
python scripts\switch_environment.py local

echo.
echo Environment: LOCAL (Conda)
echo DEM Sources: Local DTM + full geospatial support
echo.

echo Starting service on http://localhost:8001
echo Press Ctrl+C to stop
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload