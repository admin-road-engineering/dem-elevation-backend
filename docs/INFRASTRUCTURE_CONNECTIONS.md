# Infrastructure Connections & Management Guide

## 🚀 Railway Platform Integration

### Authentication & Access
- **Logged in as**: `admin@road.engineering`
- **Project**: `road-engineering-DEM-Backend`
- **Environment**: `production`
- **Service**: `dem-elevation-backend`
- **Production URL**: https://re-dem-elevation-backend.up.railway.app

### Railway CLI Commands
```bash
# Check authentication status
railway whoami
# Output: Logged in as admin@road.engineering 👋

# Check current project link
railway status
# Output: Project: road-engineering-DEM-Backend
#         Environment: production
#         Service: dem-elevation-backend

# Environment variable management
railway variables                           # List all variables
railway variables --set "KEY=value"        # Set new variable
railway variables --set "ENABLE_NZ_SOURCES=true"  # Enable NZ integration
```

### Critical Environment Variables Set
```bash
ENABLE_NZ_SOURCES=true                     # Enables New Zealand S3 sources
USE_S3_SOURCES=true                        # Enables Australian S3 campaigns
SPATIAL_INDEX_SOURCE=s3                    # Use S3-hosted spatial indexes
APP_ENV=production                         # Production safety behaviors
AWS_ACCESS_KEY_ID=your_aws_access_key    # S3 access credentials
AWS_SECRET_ACCESS_KEY=[masked]             # S3 secret key
AWS_DEFAULT_REGION=ap-southeast-2          # Sydney region
GPXZ_API_KEY=your_gpxz_api_key # GPXZ fallback API
GOOGLE_ELEVATION_API_KEY=[masked]          # Google fallback API
REDIS_URL=[auto-configured]                # Railway Redis addon
```

## ☁️ AWS S3 Integration

### Bucket Architecture
```
road-engineering-elevation-data/           # Private bucket (credentials required)
├── indexes/
│   ├── spatial_index.json                # 1,153 Australian campaigns
│   └── nz_spatial_index.json             # 16 NZ regions (1.08MB)
└── [Australian campaign DEM files...]

nz-elevation/                              # Public bucket (no credentials)
├── auckland/
│   ├── auckland-north_2016-2018/
│   │   └── dem_1m/2193/*.tiff            # 40 Auckland files
│   └── auckland-part-2_2024/
│       └── dem_1m/2193/*.tiff            # 39 Auckland files (2024 data)
├── wellington/
├── canterbury/
├── otago/
└── [13 other NZ regions...]
```

### AWS Credentials & Access
- **Access Key**: `your_aws_access_key`
- **Region**: `ap-southeast-2` (Sydney)
- **Main Bucket**: Private access via AWS credentials
- **NZ Bucket**: Public access with `AWS_NO_SIGN_REQUEST=YES`

### S3 Operations Performed
```bash
# Upload NZ spatial index (completed)
python upload_nz_index.py
# Uploaded: config/nz_spatial_index.json → s3://road-engineering-elevation-data/indexes/nz_spatial_index.json
# Size: 1.08MB

# Generate NZ spatial index (completed)
python scripts/generate_nz_spatial_index.py generate
# Generated: 16 regions, 79 Auckland files, 53 covering Auckland CBD
```

## 🗃️ Data Source Coverage

### Australian Coverage (S3)
- **Sources**: 1,153 campaign sources
- **Performance**: 54,000x speedup for Brisbane (11.523m elevation)
- **Access**: Private S3 bucket with AWS credentials
- **Index**: `spatial_index.json` in main bucket

### New Zealand Coverage (S3) - Phase 3B.4
- **Sources**: 16 regional sources (Auckland, Wellington, Canterbury, etc.)
- **Performance**: Sub-second response for major cities
- **Access**: Public `nz-elevation` bucket
- **Index**: `nz_spatial_index.json` in main bucket (1.08MB)
- **Auckland Specific**: 79 files, 53 covering Auckland CBD coordinates

### Global Coverage (API Fallback)
- **GPXZ API**: Primary fallback with 30m resolution
- **Google Elevation API**: Final fallback with mixed resolution
- **Performance**: 2-3 seconds for API requests
- **Coverage**: Worldwide outside AU/NZ S3 regions

## 🔄 Deployment Process

### Automatic Deployment
1. **Code Changes**: Commit to GitHub `main` branch
2. **Railway Detection**: Automatic webhook triggers deployment
3. **Environment Loading**: Railway loads variables from dashboard
4. **Service Startup**: SourceProvider loads AU + NZ spatial indexes
5. **Health Check**: Verify 1,169+ sources available (1,153 AU + 16 NZ)

### Manual Environment Updates
```bash
# Set environment variable (triggers redeployment)
railway variables --set "ENABLE_NZ_SOURCES=true"

# Monitor deployment
curl "https://re-dem-elevation-backend.up.railway.app/api/v1/health"
# Expected: "sources_available": 1169
```

### Health Verification
```bash
# Check overall health
curl "https://re-dem-elevation-backend.up.railway.app/api/v1/health"

# Test Australian S3 performance
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'
# Expected: Brisbane2009LGA campaign, ~11.5m, <1s response

# Test New Zealand S3 performance
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -36.8485, "longitude": 174.7633}'
# Expected: nz_auckland source, 1m resolution, <1s response
```

## 🔧 Infrastructure Management

### Railway Dashboard Access
- **URL**: https://railway.app/
- **Account**: admin@road.engineering
- **Project Path**: Dashboard → road-engineering-DEM-Backend → Variables

### AWS Console Access
- **URL**: https://console.aws.amazon.com/
- **Account**: Road Engineering AWS account
- **S3 Buckets**: 
  - `road-engineering-elevation-data` (private)
  - `nz-elevation` (public - managed externally)

### Redis Management
- **Provider**: Railway Redis addon
- **Connection**: Auto-configured via Railway environment
- **Purpose**: Multi-worker state management and circuit breaker coordination
- **Criticality**: Service fails fast if Redis unavailable (production safety)

## 📊 Monitoring & Verification

### Key Metrics to Monitor
- **Health Check**: `/api/v1/health` should show 1,169+ sources
- **Response Times**: <1s for AU/NZ coordinates, <3s for global API
- **Source Selection**: Brisbane uses `Brisbane2009LGA`, Auckland uses `nz_auckland`
- **Uptime**: Railway provides automatic health monitoring

### Troubleshooting Access
- **Railway Logs**: Railway dashboard → Deployments → View logs
- **Environment Variables**: Railway dashboard → Variables tab
- **S3 Connectivity**: AWS Console → CloudWatch → S3 metrics
- **Redis Status**: Railway dashboard → Redis addon status

This infrastructure provides bi-national elevation coverage (Australia + New Zealand) with unified S3 performance architecture, automatic Railway deployment, and comprehensive fallback coverage for global coordinates.