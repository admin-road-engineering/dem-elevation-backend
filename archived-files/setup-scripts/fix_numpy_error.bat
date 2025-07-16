@echo off
echo ========================================
echo   DEM Backend NumPy ABI Fix Script
echo ========================================
echo.
echo This script fixes the NumPy import error by:
echo 1. Installing Miniconda (if needed)
echo 2. Creating conda environment with compatible packages
echo 3. Verifying all imports work correctly
echo.

REM Check if conda is available
echo [1/5] Checking Conda installation...
conda --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Conda not found. Please install Miniconda first:
    echo.
    echo 1. Download Miniconda (free for all uses) from: https://docs.conda.io/en/latest/miniconda.html
    echo 2. Install with "Add to PATH" option checked
    echo 3. Restart command prompt
    echo 4. Run this script again
    echo.
    pause
    exit /b 1
) else (
    echo ✓ Conda found
)

REM Change to project root
cd /d "%~dp0"

echo.
echo [2/5] Creating conda environment...
REM Remove existing environment if it exists
conda env remove -n dem-backend-fixed -y >nul 2>&1

REM Create new environment with exact versions to avoid ABI mismatch
conda create -n dem-backend-fixed python=3.11 -y
if %errorlevel% neq 0 (
    echo ERROR: Failed to create conda environment
    pause
    exit /b 1
)

echo ✓ Environment created: dem-backend-fixed

echo.
echo [3/5] Installing geospatial packages from conda-forge...
call conda activate dem-backend-fixed

REM Install core geospatial stack with exact versions
conda install -c conda-forge -y ^
    numpy=1.26.4 ^
    rasterio=1.3.9 ^
    fiona=1.10.1 ^
    gdal=3.10.2 ^
    pyproj=3.6.1 ^
    shapely=2.0.4 ^
    scipy=1.13.1 ^
    matplotlib=3.8.4

if %errorlevel% neq 0 (
    echo ERROR: Failed to install conda packages
    pause
    exit /b 1
)

echo ✓ Geospatial packages installed

echo.
echo [4/5] Installing remaining packages with pip...
pip install --no-cache-dir ^
    fastapi==0.111.0 ^
    uvicorn[standard]==0.30.1 ^
    pydantic==2.7.3 ^
    pydantic-settings==2.3.3 ^
    boto3==1.34.0 ^
    scikit-image==0.24.0 ^
    httpx==0.25.0 ^
    PyJWT==2.10.1

if %errorlevel% neq 0 (
    echo ERROR: Failed to install pip packages
    pause
    exit /b 1
)

echo ✓ All packages installed

echo.
echo [5/5] Verifying imports...
python -c "import numpy; print('✓ NumPy:', numpy.__version__)"
if %errorlevel% neq 0 (
    echo ERROR: NumPy import failed
    pause
    exit /b 1
)

python -c "import rasterio; print('✓ Rasterio:', rasterio.__version__)"
if %errorlevel% neq 0 (
    echo ERROR: Rasterio import failed
    pause
    exit /b 1
)

python -c "import fiona; print('✓ Fiona:', fiona.__version__)"
if %errorlevel% neq 0 (
    echo ERROR: Fiona import failed
    pause
    exit /b 1
)

python -c "from src.config import Settings; print('✓ DEM Backend config loads')"
if %errorlevel% neq 0 (
    echo ERROR: DEM Backend config failed
    pause
    exit /b 1
)

echo.
echo ========================================
echo   SUCCESS: NumPy ABI Error Fixed! ✓
echo ========================================
echo.
echo Environment: dem-backend-fixed
echo All packages: Working correctly
echo.
echo To use the fixed environment:
echo   conda activate dem-backend-fixed
echo   python scripts\switch_environment.py local
echo   uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
echo.
echo Test endpoint:
echo   curl -X POST http://localhost:8001/api/v1/elevation/point ^
echo     -H "Content-Type: application/json" ^
echo     -d "{\"latitude\": -27.4698, \"longitude\": 153.0251}"
echo.
pause