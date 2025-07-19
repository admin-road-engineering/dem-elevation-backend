@echo off
echo Force killing specific processes on port 8001...

REM Kill the specific PIDs we found
taskkill /F /PID 12788
taskkill /F /PID 31144  
taskkill /F /PID 10064

echo.
echo Checking port 8001 status...
netstat -ano | findstr ":8001"
echo Done.