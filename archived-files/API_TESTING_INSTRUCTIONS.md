# DEM Backend API Testing Instructions

## Quick Reference: External Connections

### APIs We Connect To:
- **GPXZ.io API**: `https://api.gpxz.io` (Global elevation data)
- **Main Platform**: `https://api.road.engineering` (Production integration)

### S3 Buckets We Access:
- **Primary**: `road-engineering-elevation-data` (Private, requires AWS credentials)
- **High-Resolution**: `AWS_S3_BUCKET_NAME_HIGH_RES` (High-res bucket, if configured)
- **Secondary**: `nz-elevation` (Public, NZ Open Data)

## Step-by-Step Testing Instructions

### Step 0: Multi-Location S3 Catalog Testing
```bash
# Test S3 catalog integrity and multi-location coverage
python scripts/test_s3_catalog.py

# View catalog statistics
python scripts/manage_s3_catalog.py --action stats

# Discover new datasets (if any)
python scripts/manage_s3_catalog.py --action discover

# Validate catalog integrity
python scripts/manage_s3_catalog.py --action validate
```

### Step 1: Environment Setup
```bash
# Navigate to project directory
cd "C:\Users\Admin\DEM Backend"

# Check current environment
python -c "from src.config import Settings; print('Current sources:', len(Settings().DEM_SOURCES))"

# Validate all config including high-res bucket
python -c "from src.config import get_settings; settings = get_settings(); print('High-Res Bucket:', getattr(settings, 'AWS_S3_BUCKET_NAME_HIGH_RES', 'Not configured'))"
```

### Step 2: Test Local Environment (Zero Cost)
```bash
# Switch to local environment
python scripts/switch_environment.py local

# Validate local DEM files exist
python tests/test_single_grid_point.py

# Start local server
scripts/start_with_geotiff.bat

# In new terminal, test local endpoints
python scripts/test_api_plan.py
```

### Step 3: Test API Integration (Free Tier)
```bash
# Switch to API test environment
scripts/switch_to_api_test.bat

# Verify GPXZ API key is set
python -c "import os; print('GPXZ Key:', os.getenv('GPXZ_API_KEY', 'NOT SET'))"

# Start server
scripts/start_with_geotiff.bat

# In new terminal, run API tests
python scripts/test_api_plan.py

# Test batch elevation requests
curl -X POST http://localhost:8001/api/v1/elevation/points -H "Content-Type: application/json" -d '[{"latitude": -27.4698, "longitude": 153.0251}, {"latitude": -33.8688, "longitude": 151.2093}]'
```

### Step 4: Test Production S3 Access (Costs Apply)
```bash
# Set AWS credentials (required for private S3 bucket)
set AWS_ACCESS_KEY_ID=your_access_key
set AWS_SECRET_ACCESS_KEY=your_secret_key

# Switch to production environment
scripts/switch_to_production.bat

# Start production server
scripts/start_production.bat

# In new terminal, run full tests
python scripts/test_api_plan.py

# Test high-res bucket (if configured)
aws s3 ls s3://$(python -c "from src.config import get_settings; print(getattr(get_settings(), 'AWS_S3_BUCKET_NAME_HIGH_RES', 'not-configured'))")/ 2>/dev/null || echo "High-res bucket not configured"
```

### Step 5: Test Production Deployment
```bash
# Test live production service
python scripts/post_deploy_smoke_test.py --url https://dem-api.road.engineering

# Test local production setup
python scripts/post_deploy_smoke_test.py --url http://localhost:8001
```

## Manual API Testing Commands

### Test GPXZ API Directly
```bash
# Test single point elevation (Brisbane - expected ~45m)
curl -H "X-API-Key: ak_zj8pF60R_1h0s4aVF52KDSBMq" "https://api.gpxz.io/v1/elevation/point?lat=-27.4698&lon=153.0251"

# Test batch elevation requests
curl -X POST "https://api.gpxz.io/v1/elevation/points" -H "X-API-Key: ak_zj8pF60R_1h0s4aVF52KDSBMq" -H "Content-Type: application/json" -d '[{"lat": -27.4698, "lon": 153.0251}, {"lat": -33.8688, "lon": 151.2093}]'
```

### Test S3 Bucket Access
```bash
# Test private bucket (requires credentials)
aws s3 ls s3://road-engineering-elevation-data/

# Test high-res bucket (if configured)
aws s3 ls s3://$(python -c "from src.config import get_settings; print(getattr(get_settings(), 'AWS_S3_BUCKET_NAME_HIGH_RES', 'not-configured'))")/ 2>/dev/null || echo "High-res bucket not configured"

# Test public NZ bucket
aws s3 ls s3://nz-elevation/ --no-sign-request
```

### Test DEM Backend Endpoints
```bash
# Health check
curl http://localhost:8001/health

# List sources
curl http://localhost:8001/api/v1/elevation/sources

# Get single point elevation (Brisbane - expected ~45m)
curl -X POST http://localhost:8001/api/v1/elevation/point -H "Content-Type: application/json" -d '{"latitude": -27.4698, "longitude": 153.0251}'

# Get batch elevation (Brisbane & Sydney - expected ~[45, 25])
curl -X POST http://localhost:8001/api/v1/elevation/points -H "Content-Type: application/json" -d '[{"latitude": -27.4698, "longitude": 153.0251}, {"latitude": -33.8688, "longitude": 151.2093}]'
```

## Expected Test Results

### ✅ Success Indicators:
- **GPXZ API**: Returns elevation data (e.g., `45.2` meters for Brisbane)
- **S3 Primary**: Lists DEM files (AU_QLD_LiDAR_1m.tif, AU_National_5m_DEM.tif, etc.)
- **S3 High-Res**: Lists high-resolution files (if configured)
- **S3 Secondary**: Lists NZ DEM files (canterbury/, north-island/, wellington/, etc.)
- **DEM Backend**: Returns `{"status": "healthy"}` and elevation data
- **Batch Requests**: Returns array of elevations (e.g., `[45.2, 25.1]` for Brisbane & Sydney)
- **Response Times**: < 500ms for all endpoints

### ❌ Common Failures:
- **GPXZ 401**: API key missing or invalid
- **S3 403**: AWS credentials not set or invalid
- **DEM Backend 404**: Service not running
- **Rate Limit**: Too many requests, wait for reset

## Quick Troubleshooting

### Fix Missing Credentials:
```bash
# Set GPXZ API key
set GPXZ_API_KEY=ak_zj8pF60R_1h0s4aVF52KDSBMq

# Set AWS credentials
set AWS_ACCESS_KEY_ID=your_key
set AWS_SECRET_ACCESS_KEY=your_secret
```

### Fix Environment Issues:
```bash
# Reset to working local environment
python scripts/switch_environment.py local

# Check what environment is active
python -c "from src.config import Settings; s=Settings(); print('Sources:', list(s.DEM_SOURCES.keys()))"
```

### Fix Service Issues:
```bash
# Restart service
# Stop current server (Ctrl+C)
scripts/start_with_geotiff.bat

# Check service is running
curl http://localhost:8001/health

# Debug DEM availability
python src/check_available_dems.py

# Check fallback behavior
python -c "from src.config import get_settings; print('Fallback enabled:', getattr(get_settings(), 'AUTO_SELECT_BEST_SOURCE', False))"
```

## Test Report Location

After running tests, find results in:
- **Console output**: Real-time test results
- **api_test_report.json**: Detailed JSON report
- **Terminal logs**: Error messages and debugging info

## Cost Warnings

⚠️ **API Test Mode**: Free tier limits (100 GPXZ requests/day)
⚠️ **Production Mode**: Incurs S3 transfer costs and paid API usage
✅ **Local Mode**: Zero external costs

## Next Steps After Testing

1. **If tests pass**: Environment is ready for development
2. **If tests fail**: Check credentials and service availability
3. **For production**: Set up monitoring and alerting
4. **For CI/CD**: Integrate test scripts into deployment pipeline