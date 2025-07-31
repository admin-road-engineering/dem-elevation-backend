# DEM Backend Production Deployment Guide

## Phase 3: Production Deployment to Railway (dem-api.road.engineering)

This guide covers the complete deployment of the DEM Backend to production on Railway hosting platform.

## Prerequisites

### 1. Railway Account Setup
- Railway CLI installed and authenticated
- Access to Road Engineering Railway project
- Domain `dem-api.road.engineering` configured

### 2. Required Environment Variables (Set in Railway)
```bash
# AWS Credentials for S3 bucket access
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key

# GPXZ.io API for global elevation coverage
GPXZ_API_KEY=your_gpxz_api_key

# Supabase JWT for main platform integration
SUPABASE_JWT_SECRET=your_supabase_jwt_secret
```

### 3. Main Platform Integration
- Main platform at `https://api.road.engineering`
- Frontend at `https://road.engineering`
- JWT authentication alignment required

## Deployment Steps

### Step 1: Prepare Repository
```bash
# Ensure all files are committed
git add .
git commit -m "Production deployment configuration"
git push origin master
```

### Step 2: Deploy to Railway
```bash
# Connect to Railway project
railway login
railway link

# Deploy with production environment
railway up --detach
```

### Step 3: Configure Environment Variables
In Railway dashboard, set the following variables:

#### Critical Variables
- `AWS_ACCESS_KEY_ID` - S3 bucket access
- `AWS_SECRET_ACCESS_KEY` - S3 bucket access
- `GPXZ_API_KEY` - Global elevation API
- `SUPABASE_JWT_SECRET` - JWT verification (from main platform)

#### Optional Variables (defaults in code)
- `LOG_LEVEL=INFO`
- `REQUIRE_AUTH=false` (enable after testing)

### Step 4: Verify Deployment & Post-Deployment Checklist

#### Immediate Verification (< 2 minutes)
```bash
# 1. Service health check
curl https://dem-api.road.engineering/health
# Expected: {"status": "healthy", "dem_sources_configured": 4+}

# 2. Root endpoint check
curl https://dem-api.road.engineering/
# Expected: {"service": "DEM Elevation Service", "status": "running"}

# 3. Sources endpoint check  
curl https://dem-api.road.engineering/api/v1/elevation/sources
# Expected: {"sources": {...}, "total_sources": 4+}
```

#### Functional Testing (< 5 minutes)
```bash
# 4. Test single point elevation
curl -X POST https://dem-api.road.engineering/api/v1/elevation/point \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'
# Expected: {"elevation_m": 45.2, "source": "au_national", ...}

# 5. Test batch elevation (3 points)
curl -X POST https://dem-api.road.engineering/api/v1/elevation/path \
  -H "Content-Type: application/json" \
  -d '{"points": [{"latitude": -27.4698, "longitude": 153.0251}, {"latitude": -27.4699, "longitude": 153.0252}, {"latitude": -27.4700, "longitude": 153.0253}]}'
# Expected: {"elevations": [...], "source": "...", "total_points": 3}

# 6. Test CORS preflight
curl -X OPTIONS https://dem-api.road.engineering/api/v1/elevation/sources \
  -H "Origin: https://road.engineering" \
  -H "Access-Control-Request-Method: POST"
# Expected: 200/204 with CORS headers
```

#### Performance Validation (< 10 minutes)
```bash
# 7. Response time check (should be < 500ms)
time curl -s https://dem-api.road.engineering/health > /dev/null
# Expected: real 0m0.200s (or similar < 500ms)

# 8. Load test (basic)
for i in {1..10}; do 
  curl -s https://dem-api.road.engineering/health > /dev/null &
done
wait
# Expected: All requests complete without errors

# 9. Memory and CPU check
# In Railway dashboard: Memory < 512MB, CPU < 50%
```

#### Integration Testing (< 15 minutes)
```bash
# 10. Test main platform integration
curl -X POST https://api.road.engineering/api/elevations \
  -H "Content-Type: application/json" \
  -d '{"points": [{"lat": -27.4698, "lng": 153.0251}]}'
# Expected: Valid elevation data from DEM backend

# 11. Test with JWT authentication (if enabled)
curl -X POST https://dem-api.road.engineering/api/v1/elevation/point \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'
# Expected: Valid response with authentication

# 12. Test error handling
curl -X POST https://dem-api.road.engineering/api/v1/elevation/point \
  -H "Content-Type: application/json" \
  -d '{"latitude": 999, "longitude": 999}'
# Expected: {"elevation_m": null, ...} with graceful handling
```

#### Monitoring Setup Verification (< 5 minutes)
```bash
# 13. Check Railway logs
railway logs --service dem-backend | head -20
# Expected: INFO level logs, no ERROR entries

# 14. Verify health check endpoint working in Railway
# Railway dashboard -> Service -> Health checks: Green status

# 15. Test rollback capability (dry run)
railway rollback --dry-run --service dem-backend
# Expected: Shows previous deployment available for rollback
```

### ✅ Post-Deployment Checklist

#### Critical Checks (Must Pass)
- [ ] **Health endpoint returns 200** (`/health`)
- [ ] **Root endpoint accessible** (`/`)
- [ ] **Sources endpoint returns data** (`/api/v1/elevation/sources`)
- [ ] **Single point elevation works** (Brisbane coordinates)
- [ ] **Batch elevation works** (3+ points)
- [ ] **Response times < 500ms** (health endpoint)
- [ ] **Railway health checks green**
- [ ] **No ERROR logs in Railway dashboard**

#### Integration Checks (Should Pass)
- [ ] **Main platform can fetch elevations** (via `/api/elevations`)
- [ ] **CORS headers present** for allowed origins
- [ ] **Error handling graceful** (invalid coordinates)
- [ ] **Memory usage < 512MB** (Railway dashboard)
- [ ] **CPU usage < 50%** (Railway dashboard)

#### Security Checks (Should Pass)
- [ ] **Environment variables secured** (no plain text secrets)
- [ ] **JWT authentication ready** (if REQUIRE_AUTH=true)
- [ ] **CORS restricted** (not wildcard in production)
- [ ] **HTTPS enforced** (no HTTP endpoints exposed)

#### Documentation Checks (Should Pass)
- [ ] **Rollback procedure tested** (dry run)
- [ ] **Team notified of deployment**
- [ ] **Monitoring alerts configured**
- [ ] **Backup deployment tagged** (previous stable version)

### ⚠️ Rollback Triggers
If any of these occur, consider immediate rollback:
- Health endpoint returns 5xx errors
- Response times consistently > 1000ms
- Memory usage > 90%
- Error rate > 5% in logs
- Main platform integration fails
- User-reported elevation data issues

## Integration Testing with Main Platform

### 1. Update Main Platform Configuration
In main platform's environment variables, set:
```bash
DEM_BACKEND_URL=https://dem-api.road.engineering
```

### 2. Test End-to-End Integration
```bash
# From main platform, test elevation request
curl -X POST https://api.road.engineering/api/elevations \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"points": [{"lat": -27.4698, "lng": 153.0251}]}'
```

### 3. Enable Authentication
Once integration is confirmed:
```bash
# In Railway dashboard, set:
REQUIRE_AUTH=true
```

## Performance Monitoring

### Expected Performance Metrics
- **Response Time**: < 500ms for single point
- **Throughput**: 50+ concurrent requests
- **Availability**: 99.9% uptime
- **Error Rate**: < 1% for valid requests

### Monitoring Endpoints
- Health: `https://dem-api.road.engineering/health`
- Metrics: Available through Railway dashboard
- Logs: Railway logging interface

## Troubleshooting

### Common Issues

#### 1. Service Won't Start
```bash
# Check logs
railway logs

# Common causes:
# - Missing environment variables
# - Invalid DEM_SOURCES configuration
# - GDAL/PROJ dependency issues
```

#### 2. S3 Access Denied
```bash
# Verify AWS credentials
# Check bucket permissions
# Ensure region is correct (ap-southeast-2)
```

#### 3. JWT Authentication Errors
```bash
# Verify SUPABASE_JWT_SECRET matches main platform
# Check JWT algorithm (HS256)
# Verify token audience (authenticated)
```

#### 4. Elevation Returns Null
```bash
# Check coordinates are within source bounds
# Verify S3 sources are accessible
# Check GPXZ API quota and key validity
```

### Debug Commands
```bash
# Test configuration loading
railway run python -c "from src.config import Settings; print('Config OK')"

# Test DEM service initialization
railway run python -c "
from src.dem_service import DEMService
from src.config import Settings
service = DEMService(Settings())
print('Service OK')
"

# Check source availability
railway run python scripts/check_available_dems.py
```

## Rollback Procedures

### Quick Rollback (< 5 minutes)
```bash
# 1. Immediate rollback to last working deployment
railway rollback --service dem-backend

# 2. If Railway rollback unavailable, deploy previous commit
git log --oneline -n 5  # Find last known good commit
git checkout COMMIT_HASH
railway up --detach

# 3. Verify rollback success
curl https://dem-api.road.engineering/health
```

### Emergency Fallback (< 2 minutes)
If DEM service is completely down:

1. **Immediate service shutdown (Railway CLI):**
```bash
# Stop the failing service immediately
railway down --service dem-backend

# Check service status
railway status --service dem-backend
```

2. **Switch main platform to fallback:**
```bash
# In main platform Railway dashboard, set:
DEM_BACKEND_URL=http://localhost:8001  # Emergency local fallback

# Or use backup service:
DEM_BACKEND_URL=https://backup-dem-api.railway.app

# Verify fallback working:
curl https://api.road.engineering/api/elevations \
  -X POST -H "Content-Type: application/json" \
  -d '{"points": [{"lat": -27.4698, "lng": 153.0251}]}'
```

3. **Emergency notification (Tool-specific):**
```bash
# Railway dashboard alerts
railway alerts create --service main-backend \
  --message "DEM service degraded - using fallback"

# Update status page (if using)
# GitHub Issues for team notification
gh issue create --title "🚨 DEM Backend Emergency Fallback Active" \
  --body "DEM service temporarily down, using fallback. ETA: 30 minutes"

# Slack/Discord notification (webhook)
curl -X POST YOUR_WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d '{"text": "🚨 DEM Backend down - fallback active"}'
```

### Configuration Rollback
```bash
# Revert to previous environment configuration
cp .env.production.railway.backup .env.production.railway
railway up

# Or reset specific variables in Railway dashboard:
# - REQUIRE_AUTH=false (disable auth if JWT issues)
# - USE_S3_SOURCES=false (disable S3 if access issues)
# - USE_API_SOURCES=false (disable GPXZ if API issues)
```

### Database/Storage Rollback
```bash
# If S3 bucket issues, switch to local-only mode:
python scripts/switch_environment.py local
railway deploy

# If geodatabase corruption:
# Restore from backup (automated daily backups in S3)
aws s3 cp s3://road-engineering-backups/dtm/latest/ ./data/ --recursive
```

### Health Check Validation Post-Rollback
```bash
# 1. Service health
curl https://dem-api.road.engineering/health
# Expected: {"status": "healthy", ...}

# 2. Integration with main platform
curl -X POST https://api.road.engineering/api/elevations \
  -H "Content-Type: application/json" \
  -d '{"points": [{"lat": -27.4698, "lng": 153.0251}]}'
# Expected: Valid elevation data

# 3. Performance check
ab -n 100 -c 10 https://dem-api.road.engineering/health
# Expected: < 500ms average response time

# 4. Error rate monitoring
# Check Railway logs for error patterns
railway logs --service dem-backend | grep ERROR
```

### Prevention Measures
```bash
# 1. Always tag stable releases
git tag -a v1.0.0 -m "Production stable release"
git push origin v1.0.0

# 2. Keep backup deployment ready
# Maintain a backup Railway service from stable tag

# 3. Automated health monitoring
# Railway alerts configured for:
# - Response time > 1000ms
# - Error rate > 5%
# - Memory usage > 90%
# - CPU usage > 80%
```

### Communication Templates

#### Internal Team Alert
```
🚨 DEM Backend Issue Detected
Service: dem-api.road.engineering
Issue: [Brief description]
Impact: [User-facing impact]
ETA: [Expected resolution time]
Action: [Current mitigation steps]
```

#### User-Facing Status Update
```
⚠️ Service Temporarily Degraded
We're experiencing issues with elevation data services.
Impact: Some elevation profiles may be unavailable.
Workaround: Manual elevation entry available.
Status: Working on resolution (ETA: 30 minutes)
```

## Known Limitations & Default Fallbacks

### Initial Deployment Considerations
- **S3 Initial Sync**: First access to large S3 datasets (>1GB) may take 30-60 seconds for Railway to download and cache
- **Cold Start Latency**: Initial requests after deployment may take 2-3 seconds due to Railway container warming
- **Geodatabase Loading**: Local DTM.gdb requires 5-10 seconds initial load time on service startup

### Default Fallback Behaviors
The service automatically handles missing configuration with graceful degradation:

#### Authentication Fallbacks
```bash
# If JWT secret missing, auth disabled with warning
SUPABASE_JWT_SECRET=unset → REQUIRE_AUTH=false (logs warning)

# If auth required but no secret provided → Critical error (prevents startup)
REQUIRE_AUTH=true + SUPABASE_JWT_SECRET=unset → Service won't start
```

#### Data Source Fallbacks
```bash
# Multi-source fallback chain (automatic)
S3 Sources → API Sources → Local Sources → Error response

# If AWS credentials missing → S3 sources disabled (logs warning)
AWS_ACCESS_KEY_ID=unset → USE_S3_SOURCES=false

# If GPXZ API key missing → API sources disabled (logs warning)  
GPXZ_API_KEY=unset → USE_API_SOURCES=false

# If all sources fail → Returns elevation_m: null with source info
```

#### Network & Performance Fallbacks
```bash
# Request timeouts
Health checks: 120s timeout (Railway)
S3 requests: 30s timeout → Falls back to next source
API requests: 30s timeout → Falls back to next source

# Rate limiting (automatic)
GPXZ API: 100 requests/day (free) → Switches to S3/local
S3 usage: 1GB/day limit → Switches to API/local
```

### Performance Limitations
- **Concurrent Users**: Optimized for 50+ concurrent users, may degrade beyond 100
- **Batch Size**: Maximum 500 points per `/api/v1/elevation/path` request
- **Memory Usage**: Service uses ~200-400MB, Railway limit 512MB
- **Response Time**: Target <500ms, may increase during S3 cold starts

### Data Coverage Limitations
- **Australian Coverage**: Full coverage via S3 datasets
- **New Zealand**: North Island only (1m resolution)
- **Global Coverage**: SRTM 30m resolution via GPXZ API (paid tier required)
- **Local Coverage**: Brisbane area DTM geodatabase only

### Monitoring Limitations
- **Health Checks**: 120s timeout may not catch transient issues
- **Error Alerting**: Railway built-in only, no custom metrics initially
- **Usage Tracking**: Basic Railway metrics, detailed analytics require implementation

## Configuration Reference

### Required Environment Variables
```bash
# Production deployment (must be set in Railway dashboard)
AWS_ACCESS_KEY_ID=your_aws_access_key         # Required for S3 sources
AWS_SECRET_ACCESS_KEY=your_aws_secret_key     # Required for S3 sources  
GPXZ_API_KEY=your_gpxz_api_key               # Required for global coverage
SUPABASE_JWT_SECRET=your_supabase_jwt_secret  # Required if REQUIRE_AUTH=true
```

### Optional Environment Variables (with defaults)
```bash
# Authentication (defaults)
REQUIRE_AUTH=false              # Start disabled, enable after testing
JWT_ALGORITHM=HS256             # Supabase standard
JWT_AUDIENCE=authenticated      # Supabase standard

# Performance (defaults)
CACHE_SIZE_LIMIT=50            # Number of datasets to cache
MAX_WORKER_THREADS=20          # Thread pool size
DATASET_CACHE_SIZE=20          # In-memory dataset cache

# Logging (defaults)  
LOG_LEVEL=INFO                 # Standard production logging
SUPPRESS_GDAL_ERRORS=true      # Reduce noise in logs

# Network (defaults)
CORS_ORIGINS=https://road.engineering,https://api.road.engineering
PORT=8000                      # Railway standard
```

## Post-Deployment Smoke Test

### Automated Testing
```bash
# Run comprehensive smoke test after deployment
python scripts/post_deploy_smoke_test.py --url https://dem-api.road.engineering

# Expected output:
# ✅ DEM Backend Smoke Test Results PASSED
# ⏱️  Duration: 15.42s
# 📊 Tests: 6 total, 6 passed, 0 failed
# 🚀 Avg Response Time: 234ms
```

### Manual Verification (Quick)
```bash
# 1. Health check (< 5 seconds)
curl https://dem-api.road.engineering/health
# Expected: {"status": "healthy", "dem_sources_configured": 4}

# 2. Sample elevation (< 5 seconds)
curl -X POST https://dem-api.road.engineering/api/v1/elevation/point \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'
# Expected: {"elevation_m": 45.2, "source": "au_national", ...}
```

## Security Considerations

### Production Security
- All environment variables encrypted in Railway
- HTTPS termination at Railway edge
- JWT verification for protected endpoints
- S3 bucket access via IAM roles

### API Security
- Rate limiting (implemented in main platform)
- CORS restricted to road.engineering domains
- No sensitive data in responses
- Comprehensive error handling

## Success Criteria

### Deployment Complete When:
- [ ] Service accessible at `https://dem-api.road.engineering`
- [ ] Health endpoint returns 200 OK
- [ ] Elevation API returns valid data
- [ ] Main platform integration working
- [ ] JWT authentication functional
- [ ] Performance meets SLA targets
- [ ] All 30+ tests passing in production

## Monitoring & Maintenance

### Daily Monitoring
- Check Railway dashboard for errors
- Monitor response times and error rates
- Verify S3 and API usage within limits
- Check main platform integration health

### Weekly Maintenance
- Review logs for unusual patterns
- Update dependencies if needed
- Performance optimization if required
- Cost monitoring and optimization

### Monthly Tasks
- Security audit and updates
- Performance benchmarking
- Backup and disaster recovery testing
- Documentation updates

## Support Contacts

- **Technical Issues**: Check Railway logs first
- **S3 Issues**: AWS console and billing dashboard
- **API Issues**: GPXZ.io dashboard and usage stats
- **Integration Issues**: Main platform logs and Supabase dashboard

---

**Deployment Version**: Phase 3 Production
**Last Updated**: July 2025
**Next Milestone**: 90% complete with live production service