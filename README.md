# DEM Backend - FastAPI Elevation Service

**Status**: ✅ **PRODUCTION SECURE - ALL CRITICAL ISSUES RESOLVED**  
**Security**: Redis state management for Railway multi-worker deployment  
**Performance**: 1,000-54,000x speedup for Australian coordinates  
**Coverage**: 1,153 sources (1,151 S3 campaigns + 2 API fallbacks)  
**Architecture**: Process-safe Redis state with fail-fast timeout strategy

A production-ready Digital Elevation Model (DEM) backend service delivering secure global elevation data through S3 campaign selection and comprehensive API fallback chains for professional road engineering applications.

## 🚀 Key Features

- **🔒 PRODUCTION SECURE** - All security vulnerabilities resolved via bundled fix
- **⚡ Redis State Management** - Process-safe atomic operations for Railway deployment
- **🛡️ Rate Limiting Protection** - Multi-layer geographic-aware abuse prevention  
- **🚀 54,000x PERFORMANCE** - Brisbane coordinates via S3 campaign selection
- **🎯 Campaign-Based Selection** - 1,151 survey campaigns with spatial indexing
- **🌐 Global Coverage** - S3 regional data + GPXZ/Google API fallbacks
- **⚡ Fail-Fast Timeouts** - S3(2s) → GPXZ(8s) → Google(15s) strategy
- **🔄 Singleton Clients** - FastAPI lifespan-managed clients prevent resource leaks
- **🏗️ Circuit Breakers** - Redis-backed failure state shared across workers

## 🏗️ Architecture

### Service Integration
```
Frontend (React) → DEM Backend (8001) → S3 → GPXZ → Google
Main Platform (3001) → DEM Backend (8001) → S3 → GPXZ → Google
```

### Data Sources (Priority Order)
1. **S3 Campaigns**: 1,151 Australian campaigns (1m resolution)
2. **GPXZ.io API**: Global coverage (100 req/day free)
3. **Google Elevation**: Final fallback (2,500 req/day free)

## 🔧 Quick Start

### 1. Environment Setup
```bash
# Production environment (S3 + APIs)
python scripts/switch_environment.py production

# Local development (no cost)
python scripts/switch_environment.py local
```

### 2. Install & Start
```bash
# Install dependencies
.\venv\Scripts\activate.bat
pip install -r requirements.txt

# Start service (check port first)
netstat -ano | findstr :8001
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
```

### 3. Test Endpoints
```bash
# Health check
curl http://localhost:8001/api/v1/health

# Brisbane elevation (S3 campaign expected)
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'

# Expected: Brisbane2009LGA, ~11.5m elevation
```

## 📡 API Endpoints

### Core Elevation Services
- `POST /api/v1/elevation/point` - Single coordinate elevation
- `POST /api/v1/elevation/points` - Multiple coordinates (batch)
- `POST /api/v1/elevation/line` - Line elevation profile
- `POST /api/v1/elevation/path` - Path elevation profile
- `POST /api/v1/elevation/contour-data` - Grid data for contours

### Management & Debug
- `GET /api/v1/elevation/sources` - List 1,153 available sources
- `GET /api/v1/health` - Service health with S3 index status
- `GET /debug/settings-info` - Settings diagnostics
- `GET /attribution` - Data source attribution

## 🎯 Performance Results

| Location | Elevation | Source | Performance |
|----------|-----------|--------|-------------|
| **Brisbane CBD** | 11.523m | Brisbane2009LGA | **54,000x speedup** |
| **Sydney Harbor** | 21.710m | Sydney201304 | **672x speedup** |
| **Auckland, NZ** | 25.022m | gpxz_api | API fallback |
| **Wellington, NZ** | 2.663m | gpxz_api | API fallback |

## 🌐 Production Deployment

### Railway Deployment
- **URL**: `https://dem-elevation-backend-production-9c7a.up.railway.app`
- **Requirements**: Railway Redis addon (REQUIRED)
- **Cost**: Hobby ($5/month) + Redis ($5/month)

```bash
# Deploy to Railway
railway up --detach

# Connect Redis addon (via Railway dashboard)
# Variables → Connect → Select Redis addon
```

### Environment Variables (Auto-configured)
```env
# S3 Configuration
USE_S3_SOURCES=true
SPATIAL_INDEX_SOURCE=s3
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=ap-southeast-2

# API Configuration
USE_API_SOURCES=true
GPXZ_API_KEY=...
GOOGLE_ELEVATION_API_KEY=...

# Redis (auto-added when connected)
REDIS_URL=redis://...
REDIS_PRIVATE_URL=redis://...
```

## 🔍 Health Monitoring

### Service Status
```bash
# Check all sources loaded
curl https://dem-elevation-backend-production-9c7a.up.railway.app/api/v1/elevation/sources | jq '.total_sources'
# Expected: 1153

# Check S3 indexes
curl https://dem-elevation-backend-production-9c7a.up.railway.app/api/v1/health | jq '.s3_indexes'
```

### Performance Validation
```bash
# Brisbane (should use S3 campaign)
curl -X POST "https://dem-elevation-backend-production-9c7a.up.railway.app/api/v1/elevation/point" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}' | jq '.dem_source_used'
# Expected: "Brisbane2009LGA"

# Auckland (should use API fallback)  
curl -X POST "https://dem-elevation-backend-production-9c7a.up.railway.app/api/v1/elevation/point" \
  -d '{"latitude": -36.8485, "longitude": 174.7633}' | jq '.dem_source_used'
# Expected: "gpxz_api"
```

## 🛠️ Development

### Local Testing
```bash
# Switch to local mode (no APIs)
python scripts/switch_environment.py local
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload

# Test with local data
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'
```

### Running Tests
```bash
# All tests
pytest tests/

# Integration validation  
python test_integration.py

# S3 connectivity
python test_s3_simple.py
```

## 🚨 Troubleshooting

See **[CLAUDE.md](CLAUDE.md)** for comprehensive troubleshooting guide including:

### Critical Issues Resolved
- ✅ **500 Internal Server Error** - SlowAPI parameter order fixed
- ✅ **Redis Circuit Breaker Error** - failure_count property added
- ✅ **S3 Sources Not Working** - Redis connection established

### Common Issues
- **Service won't start**: Check `.env` exists, reset with `python scripts/switch_environment.py local`
- **Elevation returns null**: Check logs, verify API keys, test fallback chain
- **Redis connection issues**: Ensure Railway Redis addon is connected
- **Rate limits exceeded**: GPXZ (100/day), check usage with health endpoint

### Diagnostic Commands
```bash
# Test configuration
python -c "from src.config import Settings; print(Settings())"

# Check Railway logs
railway logs --service dem-elevation-backend

# Check environment variables
railway variables --service dem-elevation-backend
```

## 📚 Documentation

### Active Documentation
- **[CLAUDE.md](CLAUDE.md)** - Primary operational guide and troubleshooting
- **[docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md)** - Complete API reference
- **[docs/FRONTEND_INTEGRATION.md](docs/FRONTEND_INTEGRATION.md)** - React integration guide
- **[docs/S3_DATA_MANAGEMENT_GUIDE.md](docs/S3_DATA_MANAGEMENT_GUIDE.md)** - Data management

### Scripts & Utilities
- **Environment switching**: `python scripts/switch_environment.py [local|api-test|production]`
- **Campaign updates**: `python scripts/manual_campaign_update.py [--analyze|--update|--validate]`
- **Spatial indexing**: `python scripts/generate_spatial_index.py generate`

## 🔄 Data Management

### Adding New S3 DEM Files
```bash
# 1. Analyze what's new (safe, no changes)
python scripts/manual_campaign_update.py --analyze

# 2. Update campaign index with new campaigns  
python scripts/manual_campaign_update.py --update

# 3. Validate the updated index
python scripts/manual_campaign_update.py --validate

# 4. Deploy updated index to Railway
git add config/ && git commit -m "Update campaign index" && git push
```

## 📊 Architecture Status

### Security Fixes (ALL COMPLETE)
- ✅ **Timeout Strategy Inversion** - S3(2s) → GPXZ(8s) → Google(15s)
- ✅ **Redis State Management** - Process-safe atomic operations
- ✅ **Singleton Client Lifecycle** - FastAPI lifespan management
- ✅ **Rate Limiting Protection** - Multi-layer geographic-aware prevention

### Performance Achievements
- **Brisbane CBD**: 54,000x speedup via Brisbane2009LGA campaign
- **Sydney Harbor**: 672x speedup via Sydney201304 campaign
- **Global Coverage**: API fallback for international coordinates
- **Response Time**: <100ms metro, <200ms regional
- **Memory Usage**: ~600MB for spatial indexes

---

**Status**: ✅ **PRODUCTION READY - ALL CRITICAL ISSUES RESOLVED**  
**Last Updated**: 2025-01-31 - Documentation cleanup and Redis fixes complete  
**Service**: Railway deployment with Redis state management  
**Coverage**: 1,153 sources providing global elevation data