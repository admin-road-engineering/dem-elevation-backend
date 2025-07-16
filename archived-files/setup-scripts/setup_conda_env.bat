@echo off
echo Setting up DEM Backend with Conda...
echo.

echo Checking if conda is available...
conda --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Conda not found. Please install Miniconda first:
    echo https://docs.conda.io/en/latest/miniconda.html
    pause
    exit /b 1
)

echo Creating conda environment from environment.yml...
conda env create -f environment.yml

echo.
echo Activating environment...
call conda activate dem-backend

echo.
echo Installing additional pip packages...
pip install PyJWT

echo.
echo Verifying setup...
python test_imports.py

echo.
echo Setup complete! To use:
echo   conda activate dem-backend
echo   python scripts/start_local_dev.bat
echo.
pause