@echo OFF
REM Activates the virtual environment and runs gdal_translate.

SET "VENV_PATH=%~dp0.venv"
IF NOT EXIST "%VENV_PATH%\Scripts\activate.bat" (
    echo Virtual environment not found. Please run 'python -m venv .venv' first.
    exit /b 1
)

CALL "%VENV_PATH%\Scripts\activate.bat"

gdal_translate -of GTiff -co "COMPRESS=LZW" -co "TILED=YES" "./data/source/DTM.gdb" "./data/dems/dtm.tif"

deactivate 