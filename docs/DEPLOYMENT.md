# DEM Backend Deployment Guide

## 🚀 Railway Production Deployment

### Production Status
- **URL**: https://re-dem-elevation-backend.up.railway.app
- **Plan**: Hobby ($5/month, 8GB RAM) + Redis ($5/month)
- **Environment**: Production-only deployment (no local development needed)

### Prerequisites
- Railway account with existing Redis addon
- AWS S3 credentials for elevation data access
- GPXZ and Google API keys for fallback coverage

### Quick Deploy
```bash
# Clone and deploy
git clone <repository>
cd "DEM Backend"
railway up --detach
```

### Environment Configuration
Railway deployment uses single `.env` file with production settings:

```env
# Critical: Production environment detection
APP_ENV=production

# S3 Configuration (Required)
USE_S3_SOURCES=true
ENABLE_NZ_SOURCES=true
AWS_ACCESS_KEY_ID=your_key_here
AWS_SECRET_ACCESS_KEY=your_secret_here
AWS_S3_BUCKET_NAME=road-engineering-elevation-data
AWS_DEFAULT_REGION=ap-southeast-2
SPATIAL_INDEX_SOURCE=s3

# API Configuration
USE_API_SOURCES=true
GPXZ_API_KEY=your_gpxz_key_here
GOOGLE_ELEVATION_API_KEY=your_google_key_here

# Redis (auto-configured by Railway addon)
REDIS_URL=redis://default:***@redis.railway.internal:6379
REDIS_PRIVATE_URL=redis://default:***@redis.railway.internal:6379
```

### Redis Configuration (Critical)
- **Status**: **REQUIRED** - Railway Redis addon for process-safe state management
- **Connection**: Use existing Redis addon URL from Railway dashboard
- **Safety**: Service fails fast if Redis unavailable (Phase 3B.1 safety improvement)
- **Important**: NEVER create new Redis addons - always use existing one to avoid costs

#### Connect Redis Addon
1. Railway Dashboard → Your Service → Variables
2. Click "Connect" → Select existing Redis addon
3. Verify REDIS_URL and REDIS_PRIVATE_URL are set
4. Deploy: `railway up --detach`

## 🔍 Production Validation

### Health Checks
```bash
# Service health
curl https://re-dem-elevation-backend.up.railway.app/api/v1/health

# Expected response
{
  "status": "healthy",
  "service": "DEM Backend API",
  "s3_indexes": "loaded",
  "sources_available": 1169  # 1,153 AU + 16 NZ regions
}
```

### Performance Tests
```bash
# Brisbane (S3 campaign - 54,000x speedup)
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'

# Expected: Brisbane2009LGA campaign, ~11.5m elevation

# Auckland (NZ S3 sources - with ENABLE_NZ_SOURCES=true)
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -36.8485, "longitude": 174.7633}'

# Expected: nz_auckland S3 source, 1m resolution LiDAR data

# Wellington (NZ S3 sources)
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -41.2924, "longitude": 174.7787}'

# Expected: nz_wellington S3 source, sub-second response
```

## 🇳🇿 New Zealand S3 Integration

### Overview
- **Status**: ✅ Production Ready (Phase 3B.4)
- **Coverage**: 16 NZ regions with 1m resolution LiDAR data
- **Architecture**: Two-bucket system (indexes + public NZ data)
- **Performance**: Sub-second response times for major NZ cities

### S3 Bucket Architecture
```
road-engineering-elevation-data/     # Private bucket (indexes)
├── indexes/
│   ├── spatial_index.json          # 1,153 Australian campaigns  
│   └── nz_spatial_index.json       # 16 NZ regions (1.08MB)

nz-elevation/                        # Public bucket (NZ DEM data)
├── auckland/
│   ├── auckland-north_2016-2018/   # 40 files covering Auckland
│   └── auckland-part-2_2024/       # 39 files with 2024 data
├── wellington/
├── canterbury/
└── [13 other regions...]
```

### NZ Sources Configuration
The system automatically loads NZ sources when `ENABLE_NZ_SOURCES=true` is set:

```bash
# Set via Railway CLI
railway variables --set "ENABLE_NZ_SOURCES=true"

# Verify deployment logs show:
# "Loading NZ index: s3://road-engineering-elevation-data/indexes/nz_spatial_index.json"
# "NZ index loaded: 16 regions"
# "Data loading completed: 1,169 sources available"
```

### NZ Coverage Areas
- **Auckland**: 79 files, 53 covering Auckland CBD
- **Wellington**: Regional coverage with 1m resolution
- **Canterbury**: Including Christchurch metropolitan area  
- **Otago**: Including Dunedin region
- **Bay of Plenty**: Including Tauranga area
- **13 Additional Regions**: Comprehensive national coverage

### Fallback Behavior
- **With NZ Sources**: Auckland/Wellington use S3 (sub-second)
- **Without NZ Sources**: All NZ coordinates use GPXZ API (2-3 seconds)
- **Global Coverage**: API fallback for areas outside AU/NZ S3 coverage

## 🛠️ Local Development (Docker)

### Docker Compose Setup
```bash
# Start development environment
docker-dev up

# Services available:
# - API: http://localhost:8001
# - Redis: localhost:6379
# - Redis UI: http://localhost:8081 (with up-tools)
```

### Development Configuration
Uses `.env.development` with APP_ENV=development:
- Redis fallback allowed if unavailable
- Enhanced logging (DEBUG level)
- CORS includes localhost origins

See [DOCKER_DEVELOPMENT.md](DOCKER_DEVELOPMENT.md) for complete setup guide.

## 🚨 Troubleshooting

### Critical Production Issues

#### Service Fails to Start
**Most Common**: Redis addon not connected
```bash
# Check Railway variables
railway variables --service dem-elevation-backend

# Should see REDIS_URL and REDIS_PRIVATE_URL
# If missing: Railway Dashboard → Service → Variables → Connect Redis
```

#### "Redis connection failed in production environment"
**Expected Behavior**: Phase 3B.1 safety feature prevents inconsistent state
```bash
# Fix: Connect Railway Redis addon via dashboard
# Critical: NEVER create new Redis - use existing to avoid costs
```

#### Elevation Returns Null
```bash
# Check Railway logs
railway logs --service dem-elevation-backend

# Verify API keys
railway variables --service dem-elevation-backend

# Test health first
curl "https://re-dem-elevation-backend.up.railway.app/api/v1/health"
```

### Development Issues

#### Docker Services Won't Start
```bash
# Check ports
netstat -ano | findstr :8001
netstat -ano | findstr :6379

# Rebuild containers
docker-dev build
docker-dev up
```

#### Redis Connection in Development
```bash
# Check Redis container
docker-compose logs redis

# Test connection
docker-scripts shell
python -c "import redis; r=redis.from_url('redis://redis:6379'); print(r.ping())"
```

## 📊 Monitoring

### Railway Diagnostic Commands
```bash
# Service status
railway status

# Check logs
railway logs --service dem-elevation-backend

# Check variables
railway variables --service dem-elevation-backend

# Deploy latest
railway up --detach
```

### Performance Monitoring
```bash
# Check source count
curl "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/sources" | jq '.total_sources'
# Expected: 1153

# Check health details
curl "https://re-dem-elevation-backend.up.railway.app/api/v1/health" | jq '.'
```

### Circuit Breaker Status
```bash
# Check API circuit breaker state
curl "https://re-dem-elevation-backend.up.railway.app/debug/circuit-breaker-status"

# Shows GPXZ and Google API circuit breaker status with failure counts
```

## 🔒 Security

### Production Security
- APP_ENV=production enables fail-fast Redis safety
- CORS restricted to production domains only
- No authentication required (internal service)
- Credentials via environment variables only

### Development Security
- APP_ENV=development allows Redis fallback
- CORS includes localhost for development
- Non-root container execution
- Isolated Docker networks

## 📈 Scaling

### Railway Scaling
- **Current**: Hobby plan, 8GB RAM, sufficient for current load
- **Monitoring**: Check Railway dashboard for resource usage
- **Vertical Scaling**: Upgrade plan if memory/CPU limits reached
- **Horizontal Scaling**: Redis state management supports multiple workers

### Performance Optimization
- **S3 Campaign Indexing**: 54,000x speedup maintained
- **Circuit Breakers**: Prevent cascading failures during API issues
- **Spatial Indexing**: O(log N) geographic lookups
- **Memory Management**: LRU caching with automatic cleanup

This deployment configuration provides robust, scalable elevation services with production safety measures and development flexibility.