# Docker Development Guide

This guide covers local development using Docker Compose for the DEM Backend service.

## 🚀 Quick Start

### Prerequisites
- Docker Desktop installed and running
- Git repository cloned locally

### Start Development Environment
```bash
# Start API + Redis
docker-dev up

# Start with Redis UI for debugging
docker-dev up-tools
```

### Verify Services
```bash
# Check health
docker-dev test

# View API logs
docker-dev logs
```

## 🏗️ Architecture

The Docker Compose setup includes:

- **DEM Backend API** (port 8001) - FastAPI service
- **Redis** (port 6379) - State management and circuit breakers  
- **Redis Commander** (port 8081) - Web UI for Redis (optional)

## 📡 Service URLs

| Service | URL | Description |
|---------|-----|-------------|
| **API** | http://localhost:8001 | DEM Backend FastAPI |
| **Health Check** | http://localhost:8001/api/v1/health | Service health status |
| **API Docs** | http://localhost:8001/docs | Interactive API documentation |
| **Redis UI** | http://localhost:8081 | Redis management (with `up-tools`) |

## 🔧 Development Commands

### Basic Operations
```bash
# Start services
docker-dev up

# Stop services  
docker-dev down

# View logs (follow mode)
docker-dev logs

# Restart API service
docker-dev restart
```

### Advanced Operations
```bash
# Rebuild containers
docker-dev build

# Clean up (removes volumes)
docker-dev clean

# Test endpoints
docker-dev test
```

### Manual Docker Compose
```bash
# Start all services
docker-compose up -d

# Start with Redis UI
docker-compose --profile dev-tools up -d

# View logs
docker-compose logs -f dem-backend

# Stop services
docker-compose down
```

## ⚙️ Configuration

### Environment Variables
Development configuration is in `.env.development`:

```env
# Development mode
APP_ENV=development

# Redis connection (Docker service)
REDIS_URL=redis://redis:6379

# S3 sources (optional - add your credentials)
USE_S3_SOURCES=true
AWS_ACCESS_KEY_ID=your_key_here
AWS_SECRET_ACCESS_KEY=your_secret_here

# API sources (optional - add your keys)
USE_API_SOURCES=true
GPXZ_API_KEY=your_gpxz_key_here
GOOGLE_ELEVATION_API_KEY=your_google_key_here
```

### Adding API Keys (Optional)
Edit `.env.development` to add your API keys for external services:

1. **GPXZ API** - Get free key from https://gpxz.io/
2. **Google Elevation API** - Get key from Google Cloud Console  
3. **AWS S3** - Add your credentials for private bucket access

## 🧪 Testing

### Health Check
```bash
curl http://localhost:8001/api/v1/health
```

### Brisbane Elevation (S3 Campaign)
```bash
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'
```

Expected response:
```json
{
  "elevation": 11.523284,
  "dem_source_used": "Brisbane2009LGA",
  "message": "Index-driven S3 campaign: Brisbane2009LGA (resolution: 1m)"
}
```

### Auckland Elevation (API Fallback)
```bash
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -36.8485, "longitude": 174.7633}'
```

Expected response:
```json
{
  "elevation": 25.022,
  "dem_source_used": "gpxz_api",
  "message": "GPXZ API elevation data"
}
```

## 🔍 Debugging

### View Service Logs
```bash
# API service logs
docker-compose logs -f dem-backend

# Redis logs
docker-compose logs -f redis

# All logs
docker-compose logs -f
```

### Redis Management
Start with Redis UI to inspect state:
```bash
docker-dev up-tools
# Open http://localhost:8081
```

### Container Shell Access
```bash
# Access API container
docker-compose exec dem-backend bash

# Access Redis container
docker-compose exec redis redis-cli
```

## 🚨 Troubleshooting

### Services Won't Start
```bash
# Check Docker is running
docker --version

# Check port conflicts
netstat -ano | findstr :8001
netstat -ano | findstr :6379

# Rebuild containers
docker-dev build
docker-dev up
```

### Redis Connection Issues
```bash
# Check Redis health
docker-compose exec redis redis-cli ping

# Check Redis logs
docker-compose logs redis

# Restart Redis
docker-compose restart redis
```

### API Returns 500 Errors
```bash
# Check API logs
docker-dev logs

# Verify environment file
cat .env.development

# Test health endpoint
curl http://localhost:8001/api/v1/health
```

### Performance Issues
```bash
# Check container resources
docker stats

# Check if S3 indexes loaded
curl http://localhost:8001/api/v1/elevation/sources | jq '.total_sources'
```

## 🔄 Development Workflow

### Typical Development Session
```bash
# 1. Start services
docker-dev up

# 2. Verify health
docker-dev test

# 3. Make code changes (auto-restart in development)

# 4. Test changes
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'

# 5. View logs if needed
docker-dev logs

# 6. Stop when done
docker-dev down
```

### Code Changes
- Code changes trigger automatic restart (watch mode)
- Configuration changes require container restart: `docker-dev restart`
- Dependency changes require rebuild: `docker-dev build`

## 📊 Monitoring

### Service Health
```bash
# Check all services
docker-compose ps

# Check health endpoints
curl http://localhost:8001/api/v1/health
```

### Redis State
```bash
# Using Redis UI
open http://localhost:8081

# Using Redis CLI
docker-compose exec redis redis-cli
> keys *
> get circuit_breaker:gpxz_api
```

## 🔒 Security Notes

- Development environment uses `APP_ENV=development`
- Redis fallback allowed in development (not in production)
- No authentication required for local development
- API keys in `.env.development` are optional

## 🎯 Next Steps

After setting up Docker development:

1. **Add API Keys** - Configure GPXZ and Google API keys for testing
2. **Add S3 Credentials** - Configure AWS credentials for S3 campaign testing
3. **Run Integration Tests** - Use `pytest tests/` inside container
4. **Explore Redis UI** - Use http://localhost:8081 to inspect circuit breaker state

This Docker setup provides a complete local development environment matching the production architecture while maintaining development convenience.