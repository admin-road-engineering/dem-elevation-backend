@echo off
echo === DEM Backend Simple Setup ===
echo.

REM Stay open on error
setlocal EnableDelayedExpansion

echo 1. Checking conda...
conda --version
if %errorlevel% neq 0 (
    echo ERROR: Conda not found
    echo Please install Miniconda first
    pause
    exit /b 1
)

echo 2. Creating environment...
conda create -n dem-backend-fixed python=3.11 -y
if %errorlevel% neq 0 (
    echo Note: Environment may already exist
)

echo 3. Activating environment...
call conda activate dem-backend-fixed

echo 4. Installing core packages...
conda install -c conda-forge numpy=1.26.4 rasterio=1.3.9 -y

echo 5. Installing remaining packages...
pip install fastapi uvicorn pydantic pydantic-settings boto3 httpx PyJWT pyproj shapely fiona

echo 6. Testing imports...
python -c "import numpy, rasterio, fiona; print('SUCCESS: All packages work!')"

echo.
echo === Setup Complete ===
echo To start server: uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
echo.
pause