# Local DEM Backend Server Setup

## Overview
This guide provides detailed instructions for configuring and running the DEM Backend server locally with support for direct frontend integration.

## Quick Start

### 1. Environment Setup
```bash
# Switch to local development mode
python scripts/switch_environment.py local

# Verify environment configuration
python -c "from src.config import Settings; s=Settings(); print(f'Sources: {len(s.DEM_SOURCES)}, CORS: {s.CORS_ORIGINS}')"
```

### 2. Start the Service
```bash
# Primary development command (with auto-reload)
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload

# Alternative: Using batch script (Windows)
scripts\start_local_dev.bat
```

### 3. Verify Service
```bash
# Health check
curl http://localhost:8001/api/v1/health

# Test contour endpoint
curl -X POST "http://localhost:8001/api/v1/elevation/contour-data" \
  -H "Content-Type: application/json" \
  -d '{
    "area_bounds": {
      "polygon_coordinates": [
        {"latitude": -27.4698, "longitude": 153.0251},
        {"latitude": -27.4705, "longitude": 153.0258},
        {"latitude": -27.4712, "longitude": 153.0265},
        {"latitude": -27.4698, "longitude": 153.0251}
      ]
    },
    "grid_resolution_m": 10.0
  }'
```

## Environment Configuration

### Required `.env` Variables
```bash
# Core DEM configuration
DEM_SOURCES={"local_dtm_gdb": {"path": "./data/DTM.gdb", "crs": null, "layer": null, "description": "Local high-resolution DTM geodatabase"}}
DEFAULT_DEM_ID=local_dtm_gdb

# Frontend integration settings
CORS_ORIGINS=http://localhost:3001,http://localhost:5173,http://localhost:5174
USE_S3_SOURCES=false
USE_API_SOURCES=false
REQUIRE_AUTH=false

# Performance and logging
SUPPRESS_GDAL_ERRORS=true
CACHE_SIZE_LIMIT=10
LOG_LEVEL=INFO
```

### Environment Switching
```bash
# Switch to different modes
python scripts/switch_environment.py local      # Local DTM only
python scripts/switch_environment.py api-test  # With external APIs
python scripts/switch_environment.py production # Full S3 + APIs
```

## Dependencies

### Core Requirements
```bash
pip install -r requirements.txt

# Or install individually if needed:
pip install fastapi uvicorn pydantic pydantic-settings
pip install rasterio fiona pyproj boto3 shapely
pip install matplotlib scikit-image PyJWT
```

### Verify Installation
```bash
# Test imports
python -c "from src.main import app; print('✅ All imports successful')"

# Test GDAL drivers
python -c "from osgeo import gdal; print(f'GDAL drivers available: {gdal.GetDriverCount()}')"
```

## API Endpoints

### Available Endpoints
| Endpoint | Method | Purpose | Frontend Integration |
|----------|--------|---------|---------------------|
| `/api/v1/health` | GET | Service health check | ✅ |
| `/api/v1/elevation/point` | POST | Single point elevation | ✅ |
| `/api/v1/elevation/points` | POST | Batch point elevation | ✅ |
| `/api/v1/elevation/line` | POST | Line elevation profile | ✅ |
| `/api/v1/elevation/path` | POST | Complex path elevation | ✅ |
| `/api/v1/elevation/contour-data` | POST | **NEW**: Grid elevation for contours | ✅ **Direct** |
| `/api/v1/elevation/sources` | GET | Available DEM sources | ✅ |

### New Contour Data Endpoint

**Request Format:**
```json
{
  "area_bounds": {
    "polygon_coordinates": [
      {"latitude": -27.4698, "longitude": 153.0251},
      {"latitude": -27.4705, "longitude": 153.0258},
      {"latitude": -27.4712, "longitude": 153.0265},
      {"latitude": -27.4698, "longitude": 153.0251}
    ]
  },
  "grid_resolution_m": 10.0,
  "source": "local_dtm_gdb"
}
```

**Response Format:**
```json
{
  "status": "OK",
  "dem_points": [
    {
      "latitude": -27.4698,
      "longitude": 153.0251,
      "elevation_m": 45.2,
      "x_grid_index": 0,
      "y_grid_index": 0,
      "grid_resolution_m": 10.0
    }
  ],
  "total_points": 1000,
  "dem_source_used": "local_dtm_gdb",
  "grid_info": {
    "total_width": 50,
    "total_height": 20,
    "grid_resolution_m": 10.0,
    "dem_native_resolution_m": 1.0
  },
  "crs": "EPSG:4326",
  "message": "Contour data generated successfully."
}
```

## Frontend Integration

### CORS Configuration
The service is configured for direct frontend access with CORS enabled for:
- `http://localhost:5173` (Vite default)
- `http://localhost:5174` (Vite alternate)
- `http://localhost:3001` (Main backend)

### Frontend Environment Variables
Add to your frontend `.env` file:
```bash
VITE_DEM_BACKEND_URL=http://localhost:8001
```

### Test Cross-Origin Requests
```javascript
// Test from browser console (frontend running on 5173)
fetch('http://localhost:8001/api/v1/elevation/sources')
  .then(response => response.json())
  .then(data => console.log('✅ CORS working:', data))
  .catch(error => console.error('❌ CORS issue:', error));
```

## Development Workflow

### Terminal Setup
```bash
# Terminal 1: Start DEM Backend
cd "C:\Users\Admin\DEM Backend"
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload

# Terminal 2: Start Frontend (if testing integration)
cd "C:\Users\Admin\road-engineering-branch\road-engineering"
npm run dev

# Terminal 3: Monitor/test
curl http://localhost:8001/api/v1/health
```

### Live Development
- Service auto-reloads on code changes (with `--reload` flag)
- CORS allows direct frontend testing
- Structured logging helps debug issues
- Health endpoint for service monitoring

## Troubleshooting

### Common Issues

#### Port Already in Use
```bash
# Check what's using port 8001
netstat -an | findstr :8001

# Kill process if needed (Windows)
taskkill /F /PID <process_id>
```

#### Import Errors
```bash
# Test specific imports
python -c "import rasterio; print('✅ rasterio OK')"
python -c "import fiona; print('✅ fiona OK')"
python -c "from src.main import app; print('✅ app OK')"
```

#### GDAL/Geodatabase Issues
```bash
# Test geodatabase access
python scripts/test_gdb_access.py

# Check available drivers
python -c "from osgeo import gdal; print([gdal.GetDriver(i).GetDescription() for i in range(min(10, gdal.GetDriverCount()))])"
```

#### CORS Issues
```bash
# Test CORS headers
curl -H "Origin: http://localhost:5173" \
     -H "Access-Control-Request-Method: POST" \
     -H "Access-Control-Request-Headers: Content-Type" \
     -X OPTIONS http://localhost:8001/api/v1/elevation/contour-data
```

### Performance Monitoring
```bash
# Simple health check script
echo 'curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/v1/health' > health_check.sh

# Monitor response times
time curl http://localhost:8001/api/v1/elevation/sources
```

## Production Readiness

### Pre-deployment Checklist
- [ ] Service starts without errors
- [ ] All endpoints return 200 status
- [ ] CORS headers present in responses
- [ ] Contour endpoint returns valid data
- [ ] Frontend can make direct API calls
- [ ] No regression in existing functionality
- [ ] Error responses use standardized format
- [ ] Health monitoring is functional

### Load Testing
```bash
# Test concurrent requests
ab -n 100 -c 10 http://localhost:8001/api/v1/health

# Test contour endpoint under load
# (Use appropriate test data for your region)
```

## Integration with Main Platform

### Hybrid Architecture
The service now supports both:
1. **Direct Frontend Access**: For simple elevation queries (contour data, point lookups)
2. **Main Backend Proxy**: For complex engineering calculations requiring business logic

### Service Responsibilities
- **DEM Backend**: Raw elevation data, grid sampling, source management
- **Main Backend**: Business logic, authentication, complex calculations, rate limiting
- **Frontend**: Direct calls for performance, proxied calls for protected features

This setup enables optimal performance while maintaining the platform's IP protection and business logic separation.