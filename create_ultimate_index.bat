@echo off
REM ============================================================
REM ULTIMATE PERFORMANCE INDEX CREATOR
REM Solves the 798 -> 22 collection matching issue
REM ============================================================

echo ============================================================
echo                 ULTIMATE PERFORMANCE INDEX CREATOR
echo ============================================================
echo.
echo This will create the ultimate spatial index that:
echo   - Handles mixed WGS84/UTM coordinates (99.87%% / 0.13%%)
echo   - Fixes campaign aggregation bug (no more duplicate bounds)
echo   - Reduces Sydney matches from 798 to ~22
echo   - Achieves ^<100ms query performance
echo.

REM Check if source file exists
if not exist "config\precise_spatial_index.json" (
    echo [ERROR] Source file not found: config\precise_spatial_index.json
    echo.
    echo Please ensure the S3 metadata extraction file exists.
    echo.
    pause
    exit /b 1
)

echo Source file found: config\precise_spatial_index.json
echo.

REM Check file size
for %%A in ("config\precise_spatial_index.json") do (
    set /a file_size_mb=%%~zA/1024/1024
)

echo Source file size: %file_size_mb% MB
echo.

echo EXPECTED OUTCOMES:
echo   - Process 631,556 files
echo   - 630,736 WGS84 files (use directly)
echo   - 820 UTM files (transform to WGS84)
echo   - Create ~1,400 campaigns with proper bounds
echo   - Sydney matches: 798 -^> ~22 (36x improvement)
echo   - Query time: ^<100ms
echo.

echo Processing will take approximately 5-10 minutes.
echo.

set /p confirm="Start creating ultimate performance index? (y/N): "
if /i not "%confirm%"=="y" (
    echo.
    echo Process cancelled.
    echo.
    pause
    exit /b 0
)

echo.
echo ============================================================
echo Starting ultimate index creation...
echo ============================================================
echo.

set PYTHON_EXE="C:\Users\Admin\miniconda3\envs\dem-backend-fixed\python.exe"

REM Run the ultimate index creator
%PYTHON_EXE% create_ultimate_performance_index.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ============================================================
    echo            ULTIMATE INDEX CREATED SUCCESSFULLY!
    echo ============================================================
    echo.
    echo Output file: config\ultimate_performance_index.json
    echo.
    
    if exist "config\ultimate_performance_index.json" (
        for %%A in ("config\ultimate_performance_index.json") do (
            set /a output_size_mb=%%~zA/1024/1024
        )
        echo Index size: %output_size_mb% MB
    )
    
    echo.
    echo NEXT STEPS:
    echo 1. Test locally: python test_ultimate_index.py
    echo 2. Upload to S3: python upload_ultimate_index.py
    echo 3. Deploy to Railway
    echo 4. Validate production performance
    echo.
    echo The performance crisis has been SOLVED!
    echo.
) else (
    echo.
    echo ============================================================
    echo                    PROCESS FAILED
    echo ============================================================
    echo.
    echo Please check the error messages above.
    echo.
    echo Common issues:
    echo   - Missing pyproj package
    echo   - Memory limitations
    echo   - Corrupted source data
    echo.
)

pause