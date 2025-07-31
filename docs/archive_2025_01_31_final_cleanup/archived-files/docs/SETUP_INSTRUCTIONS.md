# DEM Backend Setup Instructions

## Issue: Geospatial Package DLL Errors

The current virtual environment has corrupted rasterio/fiona packages causing DLL loading errors due to:
- Mismatched or missing GDAL dependencies
- Corrupted compiled extensions in virtual environment  
- Permission issues during Windows reinstallation

**Environment**: Windows 10/11, Python 3.11.9, venv with pip-installed packages

## Solution 1: Use Conda (Recommended)

```bash
# Install Miniconda if not installed
# Download from: https://docs.conda.io/en/latest/miniconda.html

# Create conda environment with geospatial packages
conda create -n dem-backend python=3.11
conda activate dem-backend

# Install ALL geospatial packages from conda-forge (pre-compiled with GDAL)
conda install -c conda-forge rasterio fiona gdal pyproj shapely scipy matplotlib

# Install remaining packages from requirements.txt
pip install fastapi uvicorn pydantic pydantic-settings
pip install boto3 scikit-image httpx PyJWT numpy

# Export environment for reproducibility
conda env export > environment.yml

# Verify setup
python -c "import rasterio, fiona; print('Geospatial packages OK')"
```

## Solution 2: OSGeo4W Distribution (Alternative)

```bash
# Download and install OSGeo4W (includes GDAL, PROJ)
# Download from: https://trac.osgeo.org/osgeo4w/

# Create new environment
deactivate
rmdir /s .venv
python -m venv .venv
.venv\Scripts\activate

# Install GDAL first, then geospatial packages
pip install GDAL==3.10.2 --find-links https://www.lfd.uci.edu/~gohlke/pythonlibs/
pip install rasterio==1.3.9 fiona==1.10.1
pip install -r requirements.txt

# Verify setup
python test_imports.py
```

## Solution 3: Docker (Production-ready)

```bash
# Build Docker container with multi-stage build
docker build -t dem-backend .

# Run container with volume mounts for data and secrets
docker run -p 8001:8000 \
  -v ./data:/app/data \
  -v ./secrets:/app/secrets:ro \
  dem-backend

# For development with live reload
docker run -p 8001:8000 \
  -v ./:/app \
  -v ./data:/app/data \
  dem-backend uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

## Post-Setup Verification

After implementing any solution, run these tests:

```bash
# 1. Test package imports
python test_imports.py
# Expected: "OK rasterio: 1.3.9", "OK fiona: 1.10.1"

# 2. Test DEM Backend startup
python scripts/switch_environment.py local
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
# Expected: "DEM Elevation Service started successfully"

# 3. Test elevation endpoint
curl -X POST http://localhost:8001/api/v1/elevation/point \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'
# Expected: {"elevation_m": 45.2, "source": "local_dtm_gdb", ...}

# 4. Run comprehensive smoke test (if available)
python scripts/post_deploy_smoke_test.py --url http://localhost:8001
```

## Quick Test (Current State - Limited Functionality)

For basic FastAPI testing without geospatial operations:

```bash
# Test web framework only (elevation endpoints will fail)
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
curl http://localhost:8001/health
```

## Troubleshooting

If DLL errors persist:
- **Windows DLL paths**: May require system restart after GDAL installation
- **Admin privileges**: Some installations require elevated permissions  
- **System dependencies**: Install Visual C++ Redistributable 2015-2022
- **Debugging tool**: Use Dependency Walker to check missing DLLs

## Recommendation

**Primary**: Use Solution 1 (Conda) for most reliable Windows geospatial package management
**Fallback**: Use Solution 2 (OSGeo4W) if conda unavailable
**Production**: Use Solution 3 (Docker) for deployment consistency