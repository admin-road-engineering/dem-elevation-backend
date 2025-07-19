# DEM Backend Service

A production-ready elevation data microservice for the Road Engineering SaaS platform, providing **S3 → GPXZ → Google fallback chain** for global elevation coverage.

## 🚀 Key Features

- **Priority-based fallback chain**: S3 → GPXZ API → Google API for maximum reliability
- **Global coverage**: Australian/NZ high-resolution S3 data + worldwide API coverage
- **Circuit breaker pattern**: Prevents cascading failures with automatic recovery
- **Rate limit awareness**: Intelligent API usage optimization
- **Cost management**: S3 usage tracking and daily limits
- **Production-ready**: Handles 500+ elevation points per request for road engineering

## 🏗️ Architecture

### Fallback Chain Priority
```
Priority 1: S3 Sources (High Resolution)
├── Australian S3 bucket (214,450+ files) - road-engineering-elevation-data
└── New Zealand S3 bucket (1,691 files) - nz-elevation

Priority 2: GPXZ.io API (Global Coverage)
├── USA NED 10m
├── Europe EU-DEM 25m
└── Global SRTM 30m

Priority 3: Google Elevation API (Final Fallback)
└── Global coverage (2,500 requests/day free tier)
```

### Integration with Main Platform
```
Frontend (React/Vercel) → DEM Backend → S3 → GPXZ → Google
Main API (FastAPI/Railway) → DEM Backend → S3 → GPXZ → Google
```

## 🔧 Environment Configuration

### Production Environment (.env.production)
```env
# API Testing Configuration - Use free tier APIs for testing
DEM_SOURCES={"act_elvis": {"path": "s3://road-engineering-elevation-data/act-elvis/", "priority": 1}, "nz_national": {"path": "s3://nz-elevation/", "priority": 1}, "gpxz_usa_ned": {"path": "api://gpxz", "priority": 2}, "google_elevation": {"path": "api://google", "priority": 3}}

USE_S3_SOURCES=true
USE_API_SOURCES=true

# GPXZ.io Configuration
GPXZ_API_KEY=your_gpxz_api_key
GPXZ_DAILY_LIMIT=100
GPXZ_RATE_LIMIT=1

# AWS Configuration
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_DEFAULT_REGION=ap-southeast-2

# Google Elevation Configuration
GOOGLE_ELEVATION_API_KEY=your_google_api_key
```

### Local Development (.env.local)
```env
# Local-only configuration for zero-cost development
DEM_SOURCES={"local_dtm": {"path": "./data/DTM.gdb", "priority": 1}}
USE_S3_SOURCES=false
USE_API_SOURCES=false
DEFAULT_DEM_ID=local_dtm
```

## 📡 API Endpoints

### Core Elevation Services
- `POST /api/v1/elevation/point` - Single coordinate elevation
- `POST /api/v1/elevation/points` - Multiple discrete coordinates
- `POST /api/v1/elevation/line` - Line segment elevation profile
- `POST /api/v1/elevation/path` - Complex path elevation profile
- `POST /api/v1/elevation/contour-data` - Grid elevation data for contours

### Management & Health
- `GET /api/v1/elevation/sources` - List available sources
- `GET /api/v1/health` - Service health check
- `GET /attribution` - Data attribution

## 🔄 Example Usage

### Single Point Elevation
```bash
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'
```

**Response with fallback chain:**
```json
{
  "latitude": -27.4698,
  "longitude": 153.0251,
  "elevation_m": 11.523284,
  "crs": "EPSG:4326",
  "dem_source_used": "gpxz_api",
  "message": null
}
```

### Contour Data Generation
```bash
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

## 🚀 Quick Start

### 1. Environment Setup
```bash
# Switch to desired environment
python scripts/switch_environment.py production  # or api-test, local

# Install dependencies
pip install -r requirements.txt
```

### 2. Start Service
```bash
# Development with auto-reload
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload

# Production
uvicorn src.main:app --host 0.0.0.0 --port 8001
```

### 3. Test Fallback Chain
```bash
# Test S3 → GPXZ → Google fallback
python test_fallback_chain.py
```

## 🔍 Fallback Chain Behavior

The service automatically tries sources in priority order:

1. **S3 Sources (Priority 1)**: High-resolution regional data
   - ✅ Success: Returns precise elevation data
   - ❌ Failure: Falls back to GPXZ API

2. **GPXZ API (Priority 2)**: Global coverage
   - ✅ Success: Returns elevation data
   - ❌ Rate limit: Falls back to Google API

3. **Google API (Priority 3)**: Final fallback
   - ✅ Success: Returns elevation data
   - ❌ Failure: Returns error response

## 📊 Performance & Reliability

### Key Metrics
- **Response time**: <100ms for single points
- **Batch processing**: 500+ points per request
- **Uptime**: 99.9% with fallback chain
- **Global coverage**: 100% via API fallbacks

### Circuit Breaker Features
- **Failure threshold**: 3-5 failures trigger circuit breaker
- **Recovery timeout**: 60-300 seconds automatic recovery
- **Graceful degradation**: Automatic fallback to next priority source

## 🌐 Integration with Main Platform

### Frontend Integration (Direct)
```javascript
// Direct frontend access with CORS support
const response = await fetch('http://localhost:8001/api/v1/elevation/point', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ latitude: -27.4698, longitude: 153.0251 })
});
```

### Backend Integration (Proxy)
```python
# Main platform backend integration
import httpx

async def get_elevation(lat: float, lon: float):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8001/api/v1/elevation/point",
            json={"latitude": lat, "longitude": lon}
        )
        return response.json()
```

## 📈 Production Considerations

### Rate Limits & Costs
- **GPXZ API**: 100 requests/day (free tier) → Upgrade for production
- **Google API**: 2,500 requests/day (free tier)
- **S3 costs**: Tracked and limited during development

### CORS Configuration
- Enabled for: `localhost:5173`, `localhost:5174`, `localhost:3001`
- Production: Configure for your domain

### Authentication
- Currently: Public access for development
- Production: JWT authentication ready (SUPABASE_JWT_SECRET)

## 🧪 Testing

### Unit Tests
```bash
pytest tests/
```

### Integration Tests
```bash
pytest tests/test_phase2_integration.py
```

### Fallback Chain Test
```bash
python test_fallback_chain.py
```

## 📚 Documentation

- **CLAUDE.md**: Detailed configuration and troubleshooting
- **API_DOCUMENTATION.md**: Complete API reference
- **FRONTEND_INTEGRATION.md**: Frontend integration guide

## 🔧 Troubleshooting

### Common Issues

**S3 Access Denied**
```bash
# Check AWS credentials
python -c "from src.config import get_settings; print(get_settings().AWS_ACCESS_KEY_ID)"
```

**API Rate Limits**
```bash
# Check API limits
curl http://localhost:8001/api/v1/health
```

**Service Not Starting**
```bash
# Check configuration
python scripts/switch_environment.py local
```

### Error Codes
- **elevation_m: null** - No elevation data available
- **dem_source_used: "gpxz_api"** - Using GPXZ fallback
- **dem_source_used: "google_api"** - Using Google fallback

## 📋 Dependencies

### Core Dependencies
- **FastAPI**: Web framework
- **Pydantic**: Settings management
- **rasterio**: DEM file reading
- **boto3**: AWS S3 access
- **httpx**: HTTP client for APIs

### External Services
- **GPXZ.io**: Global elevation API
- **Google Maps**: Elevation API
- **AWS S3**: High-resolution DEM storage

## 🏢 Business Context

This service supports the Road Engineering SaaS platform's professional features:
- **AASHTO sight distance calculations**
- **Operating speed analysis**
- **Road alignment profiling**
- **Contour generation**

**Pricing tiers integrate with:**
- Free tier: Limited elevation profiles
- Professional: Unlimited engineering tools
- Enterprise: API access and batch processing

## 📄 License

[Add your license information here]

## 🤝 Contributing

[Add contribution guidelines here]