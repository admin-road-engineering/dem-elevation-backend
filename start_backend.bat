@echo off
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo Starting DEM Backend Service...
echo Port: 8001
echo Environment: Check .env file for current mode
echo.

REM Check if port 8001 is already in use
echo Checking port 8001...
netstat -ano | findstr ":8001" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo.
    echo WARNING: Port 8001 is already in use by other processes:
    netstat -ano | findstr ":8001" | findstr "LISTENING"
    echo.
    set /p "kill_choice=Do you want to kill these processes? (y/n): "
    if /i "!kill_choice!"=="y" (
        echo.
        echo Killing processes on port 8001...
        call "%~dp0kill_port_8001_working.bat"
        echo.
        echo Waiting 2 seconds before starting server...
        timeout /t 2 /nobreak >nul
    ) else (
        echo.
        echo Continuing with startup - server may fail to start if port is occupied...
        echo.
    )
) else (
    echo Port 8001 is available
)

REM Activate virtual environment if it exists
if exist ".venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call .venv\Scripts\activate.bat
)

REM Start the uvicorn server
echo Starting uvicorn server...
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload

pause