@echo off
echo Starting DEM Backend in Local Development Mode...
echo.

REM Change to project root directory
cd /d "%~dp0\.."

REM Check if conda environment exists and is activated
echo Checking environment...
if defined CONDA_DEFAULT_ENV (
    if "%CONDA_DEFAULT_ENV%"=="dem-backend-fixed" (
        echo ✓ Using conda environment: %CONDA_DEFAULT_ENV%
        goto :start_service
    )
)

REM Check if conda is available
conda --version >nul 2>&1
if %errorlevel% equ 0 (
    echo.
    echo Conda detected but DEM Backend environment not active.
    echo.
    echo Options:
    echo   1. Run 'fix_numpy_error.bat' to create conda environment
    echo   2. Run 'conda activate dem-backend-fixed' then run this script
    echo   3. Continue with current environment (may have NumPy errors)
    echo.
    choice /c 123 /m "Choose option"
    if %errorlevel%==1 (
        echo Running NumPy fix script...
        call fix_numpy_error.bat
        exit /b
    )
    if %errorlevel%==2 (
        echo Please run: conda activate dem-backend-fixed
        echo Then run this script again.
        pause
        exit /b
    )
    echo Continuing with current environment...
) else (
    echo ⚠ Conda not detected. Using current Python environment.
    echo If you get NumPy import errors, install Miniconda and run fix_numpy_error.bat
)

:start_service
echo.
REM Switch to local environment
python scripts\switch_environment.py local

echo.
echo Environment switched to LOCAL mode
echo DEM Sources: Local DTM only (no S3 costs)
echo.

REM Start the service
echo Starting service on http://localhost:8001
echo Press Ctrl+C to stop
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload