@echo off
echo Killing all processes on port 8001...

REM Method 1: Kill all processes listening on port 8001
FOR /F "tokens=5 delims= " %%P IN ('netstat -ano ^| findstr "LISTENING" ^| findstr ":8001 "') DO (
    echo Killing process PID: %%P
    taskkill /F /PID %%P >nul 2>&1
    if errorlevel 1 (
        echo Failed to kill process %%P
    ) else (
        echo Successfully killed process %%P
    )
)

REM Method 2: Alternative approach for any remaining processes
FOR /F "tokens=5 delims= " %%P IN ('netstat -ano ^| findstr ":8001"') DO (
    taskkill /F /PID %%P >nul 2>&1
)

echo.
echo Checking remaining processes on port 8001...
netstat -ano | findstr ":8001"
if errorlevel 1 (
    echo No processes found on port 8001
) else (
    echo Some processes may still be running on port 8001
)
echo Done.