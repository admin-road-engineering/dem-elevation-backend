# DEM Backend API Documentation

## Base Information

**Base URL**: `https://dem-api.road.engineering` (production)  
**Development**: `http://localhost:8001`  
**API Version**: v1  
**Architecture**: S3 → GPXZ → Google fallback chain  
**Authentication**: Public access (JWT ready for production)

## Fallback Chain Overview

The service uses a **priority-based fallback chain** for maximum reliability:

1. **Priority 1**: S3 Sources (High-resolution regional data)
2. **Priority 2**: GPXZ.io API (Global coverage)
3. **Priority 3**: Google Elevation API (Final fallback)

## Core Endpoints

### Single Point Elevation

**`POST /api/v1/elevation/point`**

Get elevation for a single coordinate using the fallback chain.

**Request:**
```json
{
  "latitude": -27.4698,
  "longitude": 153.0251
}
```

**Response:**
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

**Source Types:**
- `"s3_sources"` - High-resolution S3 data
- `"gpxz_api"` - GPXZ.io global data
- `"google_api"` - Google Elevation API

---

### Multiple Points (Batch)

**`POST /api/v1/elevation/points`**

Get elevations for multiple discrete coordinates.

**Request:**
```json
{
  "points": [
    {"latitude": -27.4698, "longitude": 153.0251},
    {"latitude": -27.4705, "longitude": 153.0258},
    {"latitude": -27.4712, "longitude": 153.0265}
  ]
}
```

**Response:**
```json
[
  {
    "latitude": -27.4698,
    "longitude": 153.0251,
    "elevation_m": 11.523284,
    "crs": "EPSG:4326",
    "dem_source_used": "gpxz_api",
    "message": null
  },
  {
    "latitude": -27.4705,
    "longitude": 153.0258,
    "elevation_m": 12.145678,
    "crs": "EPSG:4326",
    "dem_source_used": "gpxz_api",
    "message": null
  }
]
```

---

### Line Elevation Profile

**`POST /api/v1/elevation/line`**

Get elevation profile along a line segment.

**Request:**
```json
{
  "start_point": {"latitude": -27.4698, "longitude": 153.0251},
  "end_point": {"latitude": -27.4705, "longitude": 153.0258},
  "num_points": 5
}
```

**Response:**
```json
{
  "points": [
    {
      "latitude": -27.4698,
      "longitude": 153.0251,
      "elevation_m": 11.523284,
      "distance_m": 0.0
    },
    {
      "latitude": -27.4699,
      "longitude": 153.0252,
      "elevation_m": 11.634567,
      "distance_m": 25.5
    }
  ],
  "total_distance_m": 102.3,
  "source_used": "gpxz_api"
}
```

---

### Path Elevation Profile

**`POST /api/v1/elevation/path`**

Get elevation profile for a complex path (road alignments, GPS tracks).

**Request:**
```json
{
  "points": [
    {"latitude": -27.4698, "longitude": 153.0251, "id": "start"},
    {"latitude": -27.4705, "longitude": 153.0258, "id": "waypoint1"},
    {"latitude": -27.4712, "longitude": 153.0265, "id": "end"}
  ]
}
```

**Response:**
```json
{
  "elevation_profile": [
    {
      "point_id": "start",
      "latitude": -27.4698,
      "longitude": 153.0251,
      "elevation_m": 11.523284,
      "distance_m": 0.0
    },
    {
      "point_id": "waypoint1",
      "latitude": -27.4705,
      "longitude": 153.0258,
      "elevation_m": 12.145678,
      "distance_m": 102.3
    }
  ],
  "total_distance_m": 204.6,
  "source_used": "gpxz_api"
}
```

---

### Contour Data Generation

**`POST /api/v1/elevation/contour-data`** *(Frontend Direct Only)*

Generate grid elevation data for contour line generation.

**Request:**
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
  "grid_resolution_m": 10.0
}
```

**Response:**
```json
{
  "grid_data": [
    {
      "latitude": -27.4698,
      "longitude": 153.0251,
      "elevation_m": 11.523284,
      "grid_x": 0,
      "grid_y": 0
    }
  ],
  "bounds": {
    "min_lat": -27.4712,
    "max_lat": -27.4698,
    "min_lon": 153.0251,
    "max_lon": 153.0265
  },
  "grid_size": {
    "width": 10,
    "height": 8
  },
  "resolution_m": 10.0,
  "source_used": "gpxz_api"
}
```

---

## Management Endpoints

### List Available Sources

**`GET /api/v1/elevation/sources`**

List all configured DEM sources and their status.

**Response:**
```json
{
  "sources": {
    "act_elvis": {
      "path": "s3://road-engineering-elevation-data/act-elvis/",
      "description": "Australia ACT 1m LiDAR DEM",
      "priority": 1,
      "status": "available"
    },
    "gpxz_usa_ned": {
      "path": "api://gpxz",
      "description": "USA NED 10m via GPXZ API",
      "priority": 2,
      "status": "available"
    },
    "google_elevation": {
      "path": "api://google",
      "description": "Google Elevation API - Global fallback",
      "priority": 3,
      "status": "available"
    }
  },
  "fallback_chain": [
    "Priority 1: S3 Sources (11 sources)",
    "Priority 2: GPXZ API (3 sources)",
    "Priority 3: Google API (1 source)"
  ]
}
```

### Health Check

**`GET /api/v1/health`**

Service health check with fallback chain status.

**Response:**
```json
{
  "status": "healthy",
  "service": "DEM Backend",
  "version": "1.0.0",
  "fallback_chain": {
    "s3_sources": "available",
    "gpxz_api": "available",
    "google_api": "available"
  },
  "rate_limits": {
    "gpxz_requests_remaining": 85,
    "google_requests_remaining": 2445
  },
  "uptime": "2 hours 34 minutes"
}
```

### Data Attribution

**`GET /attribution`**

Get data source attribution information.

**Response:**
```json
{
  "data_sources": {
    "s3_sources": {
      "australian_data": "© Geoscience Australia, CSIRO, State Governments",
      "nz_data": "© Land Information New Zealand (LINZ)",
      "url": "https://registry.opendata.aws/"
    },
    "gpxz_api": {
      "attribution": "© GPXZ.io, USGS, EU-DEM, NASA SRTM",
      "url": "https://gpxz.io"
    },
    "google_api": {
      "attribution": "© Google Maps Elevation API",
      "url": "https://developers.google.com/maps/documentation/elevation"
    }
  }
}
```

---

## Error Handling

### Standard Error Response

All endpoints return consistent error responses:

```json
{
  "latitude": -27.4698,
  "longitude": 153.0251,
  "elevation_m": null,
  "crs": "EPSG:4326",
  "dem_source_used": "none",
  "message": "All elevation sources failed for this location"
}
```

### HTTP Status Codes

- **200 OK**: Success (elevation may be null if no data available)
- **400 Bad Request**: Invalid request parameters
- **422 Unprocessable Entity**: Invalid coordinate values
- **500 Internal Server Error**: Service error
- **503 Service Unavailable**: All sources unavailable

### Common Error Messages

- `"S3 sources unavailable - using API fallback"`
- `"GPXZ API rate limit exceeded - using Google fallback"`
- `"All elevation sources failed for this location"`
- `"Coordinates outside available coverage area"`

---

## Rate Limits & Quotas

### API Limits (Free Tier)

- **GPXZ API**: 100 requests/day
- **Google API**: 2,500 requests/day
- **S3 Sources**: Unlimited (with cost tracking)

### Production Limits

- **GPXZ API**: Upgradeable to 10,000+ requests/day
- **Google API**: Upgradeable billing plans
- **Service**: 100 requests/hour (can be increased)

### Rate Limit Headers

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 85
X-RateLimit-Reset: 1642665600
```

---

## Integration Examples

### Frontend Integration (Direct)

```javascript
// Single point elevation
async function getElevation(lat, lon) {
  const response = await fetch('http://localhost:8001/api/v1/elevation/point', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ latitude: lat, longitude: lon })
  });
  
  const data = await response.json();
  return data.elevation_m;
}

// Batch elevation
async function getElevations(points) {
  const response = await fetch('http://localhost:8001/api/v1/elevation/points', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ points })
  });
  
  return await response.json();
}
```

### Backend Integration (Proxy)

```python
import httpx

class DEMBackendClient:
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.client = httpx.AsyncClient()
    
    async def get_elevation(self, lat: float, lon: float) -> float:
        response = await self.client.post(
            f"{self.base_url}/api/v1/elevation/point",
            json={"latitude": lat, "longitude": lon}
        )
        data = response.json()
        return data.get("elevation_m")
    
    async def get_path_elevation(self, points: list) -> dict:
        response = await self.client.post(
            f"{self.base_url}/api/v1/elevation/path",
            json={"points": points}
        )
        return response.json()
```

---

## CORS Configuration

The service supports direct frontend access with CORS enabled for:

- `http://localhost:3001` (Main backend)
- `http://localhost:5173` (Frontend dev server)
- `http://localhost:5174` (Frontend alternative)

### Production CORS

Configure production domains in the service configuration:

```python
# In main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com", "https://app.yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Testing

### Manual Testing

```bash
# Test single point
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'

# Test health check
curl "http://localhost:8001/api/v1/health"

# Test fallback chain
python test_fallback_chain.py
```

### Automated Testing

```bash
# Run all tests
pytest tests/

# Run integration tests
pytest tests/test_phase2_integration.py

# Run API tests
pytest tests/test_api_endpoints.py
```

---

## Production Deployment

### Environment Variables

```bash
# Production configuration
DEM_SOURCES='{"s3_sources": {...}, "gpxz_api": {...}, "google_api": {...}}'
USE_S3_SOURCES=true
USE_API_SOURCES=true
GPXZ_API_KEY=your_production_key
GOOGLE_ELEVATION_API_KEY=your_production_key
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
```

### Docker Deployment

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ ./src/
COPY .env ./

EXPOSE 8001
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

### Railway Deployment

```yaml
# railway.json
{
  "build": {
    "commands": ["pip install -r requirements.txt"]
  },
  "deploy": {
    "startCommand": "uvicorn src.main:app --host 0.0.0.0 --port $PORT"
  }
}
```

---

## Monitoring & Observability

### Health Monitoring

The service provides health endpoints for monitoring:

- Service uptime and status
- Fallback chain availability
- API rate limit status
- Error rates and circuit breaker states

### Logging

Structured logging with fallback chain information:

```json
{
  "timestamp": "2025-01-18T10:30:00Z",
  "level": "INFO",
  "message": "Enhanced selector returned 11.523284m from gpxz_api",
  "latitude": -27.4698,
  "longitude": 153.0251,
  "source": "gpxz_api",
  "attempts": ["s3_sources", "gpxz_api"]
}
```

### Metrics

Key metrics to monitor:

- Response times per source type
- Fallback chain success rates
- API quota usage
- Error rates by source

---

## Security

### Authentication (Production Ready)

JWT authentication is ready for production:

```python
# Set in environment
SUPABASE_JWT_SECRET=your_jwt_secret
REQUIRE_AUTH=true
```

### Rate Limiting

Built-in rate limiting with configurable limits:

```python
# Configure in settings
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_PER_HOUR=1000
```

### CORS Security

Production CORS configuration:

```python
# Restrict to specific domains
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
```

---

## Support

### Documentation

- **CLAUDE.md**: Complete configuration guide
- **README.md**: Quick start and overview
- **FRONTEND_INTEGRATION.md**: Frontend integration guide

### Common Issues

1. **S3 Access Denied**: Check AWS credentials
2. **API Rate Limits**: Monitor quota usage
3. **Service Unavailable**: Check fallback chain status

### Contact

For technical support or feature requests, refer to the main Road Engineering platform documentation.