@echo off
setlocal enabledelayedexpansion

echo Checking for processes on port 8001...

REM Get list of PIDs using port 8001
set "pids="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8001" ^| findstr "LISTENING"') do (
    set "pids=!pids! %%a"
)

if "%pids%" == "" (
    echo No processes found on port 8001
    goto :end
)

echo Found processes on port 8001: %pids%
echo.
echo Attempting to kill processes...

REM Try to kill each process
for %%p in (%pids%) do (
    echo Killing process %%p...
    taskkill /F /PID %%p >nul 2>&1
    if errorlevel 1 (
        echo   Failed to kill %%p ^(may require admin rights^)
    ) else (
        echo   Successfully killed %%p
    )
)

echo.
echo Final check...
netstat -ano | findstr ":8001" >nul 2>&1
if errorlevel 1 (
    echo Port 8001 is now free
) else (
    echo Some processes may still be running on port 8001
    echo You may need to run this script as administrator
    netstat -ano | findstr ":8001"
)

:end
echo Done.
pause