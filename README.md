# DEM Elevation Backend

A specialized microservice providing elevation data for the Road Engineering SaaS platform. Supports multiple DEM sources including local geodatabases, S3-hosted data, and external elevation APIs.

## Overview

This FastAPI-based service provides high-performance elevation queries to support:
- AASHTO-compliant sight distance calculations
- Operating speed analysis workflows  
- Elevation profile generation for road alignments
- Contour line generation for terrain visualization
- Professional engineering standards compliance

## Features

- **Multi-Source Support**: Local DTM, S3 DEMs, GPXZ.io API, NZ Open Data
- **Smart Source Selection**: Automatic resolution and region-based optimization
- **Australian Regional Coverage**: Dynamic catalog for state and corridor-specific data
- **Error Resilience**: Circuit breakers, retry logic, graceful fallbacks
- **Authentication**: JWT integration with subscription-based rate limiting
- **Cost Management**: Development modes for zero-cost testing

## Architecture

```
Frontend (React) → Main API (FastAPI) → DEM Backend → Multiple DEM Sources
                                           ↓
                    Local DTM ← S3 Australia ← NZ Open Data ← GPXZ.io
```

## Quick Start

### Local Development
```bash
# Set up environment
cp env.example .env.local
python scripts/switch_environment.py local

# Install dependencies
pip install -r requirements.txt

# Run service
uvicorn src.main:app --reload --port 8001
```

### API Testing Mode
```bash
# Switch to API testing (free tiers)
python scripts/switch_environment.py api-test

# Sign up for GPXZ.io free API key (100 requests/day)
# Update .env.api-test with GPXZ_API_KEY

# Test multi-source integration
curl "http://localhost:8001/v1/elevation/point" -X POST \
  -H "Content-Type: application/json" \
  -d '{"latitude": -33.8688, "longitude": 151.2093}'
```

## Documentation

- **Implementation Plan**: [`docs/DEM_BACKEND_IMPLEMENTATION_PLAN.md`](docs/DEM_BACKEND_IMPLEMENTATION_PLAN.md)
- **Development Guide**: [`CLAUDE.md`](CLAUDE.md)
- **API Documentation**: Available at `/docs` when running

## Regional Coverage

### Supported Australian Regions
- **National**: 5m Australia-wide (EPSG:3577)
- **Queensland**: 1m LiDAR + 50cm urban (EPSG:28356)
- **NSW**: 2m DEM + 50cm Sydney metro (EPSG:28356)  
- **Tasmania**: 50cm LiDAR state-wide (EPSG:28355)
- **Transport Corridors**: Pacific Highway, Bruce Highway (50cm)

### Data Sources
- **GA Australia**: 3.6TB multi-resolution DEM collection
- **NZ Open Data**: Free LiDAR via AWS Registry
- **GPXZ.io**: Global elevation API with high-resolution regions
- **Local DTM**: High-accuracy geodatabase for development

## Deployment

### Railway Production
```bash
# Environment variables
DEM_SOURCES={"multi_region_config": "..."}
USE_S3_SOURCES=true
USE_API_SOURCES=true
GPXZ_API_KEY=${GPXZ_API_KEY}
```

### Docker
```bash
docker-compose up --build
```

## Development Modes

| Mode | Sources | Cost | Use Case |
|------|---------|------|----------|
| `local` | Local DTM only | $0 | Development |
| `api-test` | GPXZ + NZ + Local | $0 | Integration testing |
| `production` | Full multi-source | $95-343/mo | Production |

## Cost Management

- **Development**: $0 (local data + free APIs)
- **Testing**: $0 (100 GPXZ requests/day + NZ Open Data)
- **Production**: $95-343/month based on GPXZ tier and S3 usage

## Security

- JWT authentication via Supabase
- Subscription-based rate limiting  
- Input validation with Pydantic
- No credentials in code or logs
- Circuit breakers for external dependencies

## Contributing

1. Review implementation plan in `docs/`
2. Follow existing FastAPI patterns
3. Maintain multi-source compatibility
4. Add comprehensive error handling
5. Update tests for new features

## Integration

This service integrates with the main Road Engineering platform:
- **Main Repo**: [road-engineering](https://github.com/LFriske/road-engineering)
- **API Domain**: `dem-api.road.engineering`
- **Auth**: Shared Supabase JWT tokens
- **Rate Limits**: Aligned with main platform tiers

## License

[Add your license here]