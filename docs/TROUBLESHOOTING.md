# DEM Backend Troubleshooting Guide

## 🚨 Critical Production Issues

### 500 Internal Server Error on Elevation Endpoints

**Symptoms**: `/api/v1/elevation/point` returns `500 Internal Server Error`

**Root Cause**: SlowAPI rate limiter expects first parameter to be `starlette.requests.Request`

**Error**: `Exception: parameter 'request' must be an instance of starlette.requests.Request`

**Fix**: Ensure correct parameter order in FastAPI endpoints:
```python
# ❌ WRONG - Causes 500 error
@limiter.limit("60/minute")
async def endpoint(
    request_http: Request,    # SlowAPI gets confused
    request: PydanticModel,   # Tries to use this as Request
    service: Service = Depends(get_service)
):

# ✅ CORRECT - Works properly  
@limiter.limit("60/minute")
async def endpoint(
    request: Request,         # SlowAPI uses this correctly
    point_request: PydanticModel,  # Clear distinction
    service: Service = Depends(get_service)
):
```

### "RedisCircuitBreaker object has no attribute 'failure_count'"

**Symptoms**: Elevation returns `"index_driven_error"` with circuit breaker error

**Root Causes**:
1. **Missing Redis Connection**: Service not connected to Railway Redis addon
2. **Missing Property**: Debug endpoint accessing non-existent `failure_count` attribute

**Fixes**:
1. **Connect Redis Addon**: Via Railway dashboard → Service → Variables → Connect Redis
2. **Add Property**: Added `failure_count` property to `RedisCircuitBreaker` class

### Service Fails to Start (Production)

**🚨 "Redis connection failed in production environment"**:
- **Expected Behavior**: Phase 3B.1 safety feature prevents inconsistent state
- **Fix**: Connect Railway Redis addon via dashboard → Service → Connect Redis
- **Critical**: NEVER create new Redis addons - use existing one to avoid costs

**Most Common Issue**: Redis addon not connected in Railway
- **Check**: Railway dashboard → Service → Variables → REDIS_URL should be set
- **Solution**: Connect existing Redis addon through Railway dashboard

## 🔧 Development Issues

### Docker Development Environment

#### Services Won't Start
```bash
# Check Docker is running
docker --version

# Check port conflicts
netstat -ano | findstr :8001  # API port
netstat -ano | findstr :6379  # Redis port

# Rebuild containers
docker-dev build
docker-dev up
```

#### Redis Connection Issues in Development
```bash
# Check Redis container health
docker-compose exec redis redis-cli ping

# Check Redis logs
docker-compose logs redis

# Restart Redis service
docker-compose restart redis

# Verify Redis connection from API
docker-compose exec dem-backend python -c "import redis; r=redis.from_url('redis://redis:6379'); print(r.ping())"
```

#### API Returns 500 Errors in Development
```bash
# Check API logs
docker-dev logs

# Verify environment configuration
cat .env.development

# Test health endpoint
curl http://localhost:8001/api/v1/health

# Check container status
docker-compose ps
```

### Configuration Issues

#### Environment File Problems
```bash
# Check if .env exists
ls -la .env*

# For development, ensure .env.development exists
cp .env.example .env.development

# Edit with appropriate values
nano .env.development
```

#### Missing API Keys
```bash
# Symptoms: Elevation returns null for non-S3 coordinates
# Check environment variables
echo $GPXZ_API_KEY
echo $GOOGLE_ELEVATION_API_KEY

# Add to environment file
# GPXZ_API_KEY=your_key_from_gpxz.io
# GOOGLE_ELEVATION_API_KEY=your_key_from_google_cloud
```

## 📊 Diagnostic Commands

### Railway Production Diagnostics
```bash
# Check Railway service status
railway status

# Check production health
curl "https://re-dem-elevation-backend.up.railway.app/api/v1/health"

# Check Railway logs for errors
railway logs --service dem-elevation-backend

# Check environment variables (especially REDIS_URL and APP_ENV)
railway variables --service dem-elevation-backend

# Deploy latest changes
railway up --detach
```

### Development Diagnostics
```bash
# Check Docker container status
docker-compose ps

# Check API container logs
docker-compose logs -f dem-backend

# Check Redis container logs
docker-compose logs -f redis

# Test API endpoints
docker-dev test

# Access container shell for debugging
docker-compose exec dem-backend bash
```

### Health Check Validation
```bash
# Production health check
curl "https://re-dem-elevation-backend.up.railway.app/api/v1/health" | jq '.'

# Development health check
curl "http://localhost:8001/api/v1/health" | jq '.'

# Expected healthy response:
{
  "status": "healthy",
  "service": "DEM Backend API",
  "s3_indexes": "loaded",
  "sources_available": 1153
}
```

## 🧪 Testing & Validation

### Endpoint Testing

#### Brisbane Test (S3 Campaign Expected)
```bash
# Production
curl -X POST "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'

# Development
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'

# Expected Result:
{
  "elevation": 11.523284,
  "dem_source_used": "Brisbane2009LGA",
  "message": "Index-driven S3 campaign: Brisbane2009LGA (resolution: 1m)"
}
```

#### Auckland Test (API Fallback Expected)
```bash
curl -X POST "${BASE_URL}/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -36.8485, "longitude": 174.7633}'

# Expected Result:
{
  "elevation": 25.022,  
  "dem_source_used": "gpxz_api",
  "message": "GPXZ API elevation data"
}
```

### Circuit Breaker Testing
```bash
# Check circuit breaker status
curl "${BASE_URL}/debug/circuit-breaker-status"

# Expected when healthy:
{
  "gpxz_api": {
    "state": "closed",
    "failure_count": 0,
    "last_failure": null
  }
}
```

## 🛠️ Debugging Protocol

When elevation endpoints fail, follow this systematic approach:

### Phase 1: Initial Diagnosis
1. **Reproduce Issue**: Test specific coordinates consistently
2. **Check Health**: Verify `/api/v1/health` endpoint responds correctly
3. **Review Logs**: Check service logs for error patterns and stack traces
4. **Isolate Problem**: Create minimal test case to isolate the fault

### Phase 2: Root Cause Analysis
5. **Check Configuration**: Verify environment variables and Redis connection
6. **Test Components**: Test individual components (Redis, S3, APIs) separately
7. **Review Recent Changes**: Check if issue correlates with recent deployments
8. **Gather Evidence**: Collect logs, error messages, and reproduction steps

### Phase 3: Resolution & Validation
9. **Implement Fix**: Apply targeted solution based on root cause analysis
10. **Test Fix**: Verify fix resolves issue without introducing regressions
11. **Deploy**: Push changes and validate in production environment
12. **Monitor**: Confirm issue resolution and monitor for recurrence

## 🚨 Emergency Procedures

### Production Service Down
1. **Check Railway Status**: Ensure Railway platform is operational
2. **Verify Redis**: Confirm Redis addon is connected and responding
3. **Check Logs**: Review Railway logs for critical errors
4. **Rollback**: If recent deployment caused issue, rollback via Railway
5. **Escalate**: Contact Railway support if platform-level issue

### Data Corruption or Inconsistency
1. **Stop Service**: Prevent further data corruption
2. **Backup Current State**: Export current configuration and logs
3. **Restore from Backup**: Use last known good configuration
4. **Validate Data**: Run validation scripts to confirm data integrity
5. **Resume Service**: Restart with validated configuration

### Rate Limit Exceeded
1. **Check Usage**: Verify actual API usage against limits
2. **Review Circuit Breakers**: Ensure breakers are preventing excessive calls
3. **Temporary Mitigation**: Disable problematic API sources if needed
4. **Monitor Recovery**: Wait for rate limit reset (midnight UTC for GPXZ)
5. **Optimize Usage**: Review and optimize API call patterns

This troubleshooting guide provides systematic approaches to resolving common issues while maintaining service availability and data integrity.