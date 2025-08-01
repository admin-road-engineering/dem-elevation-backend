# CLAUDE.md

DEM Backend - Production elevation microservice for Road Engineering SaaS platform.

## 🎯 Project Context & Mission

**Role**: Critical elevation data microservice providing sub-100ms responses for road engineering applications through intelligent data source selection and spatial indexing.

**Current Status**: ✅ **A- "Excellent" Architecture** (Gemini validated)  
**Target**: A+ "Exceptional" through enhanced developer experience

## 🏗️ Architectural Principles

### 1. Safety-First Engineering
- **Fail-Fast Production**: Service fails immediately rather than operating in degraded state
- **Redis Dependency**: Multi-worker state management prevents race conditions
- **Environment Isolation**: Production vs development behavior clearly separated
- **Process Safety**: Atomic operations for shared state across Railway workers

### 2. Performance Engineering  
- **Domain-Specific Optimization**: 54,000x Brisbane speedup through spatial indexing
- **Async-First Architecture**: All I/O operations are truly asynchronous
- **Resource Management**: Proper cleanup and memory efficiency
- **Response Time Targets**: <100ms metro, <200ms regional Australia

### 3. Operational Excellence
- **Observable Systems**: Comprehensive logging without performance impact  
- **Graceful Degradation**: S3 → GPXZ API → Google API fallback chain
- **Health Check Integration**: Kubernetes/Railway compatible startup patterns
- **Circuit Breaker Resilience**: Prevents cascading failures during API issues

## 🚀 Production Deployment Philosophy

**Target Platform**: Railway (https://re-dem-elevation-backend.up.railway.app)  
**Deployment Strategy**: Production-focused with development Docker environment  
**Safety Model**: Redis fail-fast prevents dangerous fallbacks in multi-worker environment

### Critical Dependencies
- **Redis**: REQUIRED for production - service fails fast if unavailable
- **S3 Access**: 1,153 campaigns providing 54,000x Australian coordinate speedup  
- **API Fallbacks**: GPXZ → Google chain for global coverage outside S3 regions

## 📊 Performance Metrics

- **Brisbane CBD**: 11.523m elevation, 54,000x speedup vs API calls
- **Sydney Harbor**: 21.710m elevation, 672x speedup vs API calls  
- **Startup Time**: <500ms with complete 1,153 campaign index loading
- **Memory Usage**: ~600MB for spatial indexes in production
- **Coverage**: 1,153 S3 campaigns + global API fallback coverage

## 🎯 Development Approach

### Phase 3B.2 Completed: Developer Experience Enhancement ✅
- ✅ **Docker Compose**: Complete local development environment (`docker-dev up`)
- ✅ **Enhanced Config**: Pydantic Literal types for type-safe configuration
- ✅ **Containerized Scripts**: Operational tasks in consistent environment
- ✅ **Focused Documentation**: Architecture, deployment, and troubleshooting guides
- ✅ **Gemini Validation**: A+ roadmap confirmed through comprehensive architectural review

### Phase 3B.3.1 Completed: Core Architectural Decoupling ✅
**Gemini Assessment**: *"Top-tier refactoring demonstrating deep understanding of modern software architecture principles. Project is no longer just 'well-written'—it is **well-architected**."*

#### ✅ DataSource Strategy Pattern Implementation (COMPLETED)
- ✅ **Abstract DataSource Interface**: Clean protocol with get_elevation, health_check, coverage_info
- ✅ **S3Source Implementation**: Maintains 54,000x Brisbane speedup with spatial indexing
- ✅ **GPXZSource Implementation**: Global API coverage with circuit breaker protection
- ✅ **GoogleSource Implementation**: Final fallback with comprehensive error handling
- ✅ **UnifiedElevationProvider**: Chain of Responsibility with usage tracking and statistics

#### ✅ Circuit Breaker Dependency Injection (COMPLETED)
- ✅ **CircuitBreaker Protocol**: Abstract interface enabling dependency inversion
- ✅ **RedisCircuitBreaker**: Production implementation with shared worker state
- ✅ **InMemoryCircuitBreaker**: Testing/development implementation without external dependencies
- ✅ **Enhanced Monitoring**: Detailed status tracking, admin reset, multi-service support

### Phase 3B.4: New Zealand S3 Integration (COMPLETED ✅)
**Achievement**: *"Complete bi-national elevation coverage with unified S3 performance architecture"*

#### ✅ NZ S3 Sources Implementation (COMPLETED)
- ✅ **NZ Spatial Index Generated**: 16 regions, 1.08MB comprehensive index covering Auckland, Wellington, Canterbury
- ✅ **S3 Integration**: Uploaded to `s3://road-engineering-elevation-data/indexes/nz_spatial_index.json`
- ✅ **Two-Bucket Architecture**: Main bucket (indexes) + `nz-elevation` bucket (public DEM data)
- ✅ **Environment Configuration**: `ENABLE_NZ_SOURCES=true` set in Railway production
- ✅ **Auckland Coverage**: 79 files with 53 covering Auckland CBD coordinates (-36.8485, 174.7633)

#### 🌏 Production Coverage Enhancement
- **Australia**: 1,153 S3 campaigns maintaining 54,000x Brisbane speedup
- **New Zealand**: 16 regions with 1m resolution LiDAR data via public S3 bucket  
- **Global Fallback**: GPXZ → Google API chain for worldwide coverage
- **Response Times**: Sub-second for AU/NZ coordinates, <2s for global API fallback

### Phase 3B.5: Future Advanced Pattern Refinements
**Gemini Roadmap**: *"Strategic refinements to build upon this outstanding bi-national foundation"*

**Priority 1: Advanced Architectural Patterns**
- **Composite Pattern**: FallbackDataSource treating fallback chain as first-class citizen
- **Decorator Pattern**: CircuitBreakerWrappedDataSource for ultimate decoupling
- **DI Container**: Centralized containers.py for clean application assembly

**Priority 2: Configuration & Lifecycle Enhancement**  
- **Environment-Specific Settings**: BaseAppSettings → ProdAppSettings/DevAppSettings classes
- **FastAPI Lifespan Management**: Replace AsyncSingleton with idiomatic app.state pattern
- **Custom Exception Hierarchy**: DataSourceError → TimeoutError/NotFoundError for telemetry

## 🔒 Security & Reliability Model

### Production Safety (Phase 3B.1)
- **APP_ENV=production**: Enables Redis fail-fast and production-specific behaviors
- **Multi-Worker Safety**: Prevents dangerous in-memory fallback across processes
- **Credential Management**: All secrets via environment variables, no hardcoded values
- **CORS Protection**: Restricted origins for production security

### Development Flexibility  
- **APP_ENV=development**: Allows Redis fallback for local development convenience
- **Docker Environment**: Isolated, reproducible development stack
- **Enhanced Logging**: DEBUG level logging for development troubleshooting

## 📚 Documentation Architecture

**CLAUDE.md** (this file): Architectural principles, mission, and high-level guidance  
**[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**: Technical architecture, patterns, and design decisions  
**[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**: Railway production and Docker development deployment  
**[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)**: Systematic debugging and issue resolution  
**[docs/DOCKER_DEVELOPMENT.md](docs/DOCKER_DEVELOPMENT.md)**: Local development environment setup  
**[docs/CONTAINERIZED_SCRIPTS.md](docs/CONTAINERIZED_SCRIPTS.md)**: Operational script execution  

## 🛠️ Development Workflow Principles

### 1. Safety-First Development
- All configuration changes validated against production requirements
- Redis dependency maintained consistently across environments  
- No changes that could compromise production stability

### 2. Performance Preservation
- 54,000x Brisbane speedup maintained through all architectural changes
- Spatial indexing performance verified with each enhancement
- Memory usage monitored and optimized continuously

### 3. Operational Transparency
- All changes documented with clear impact assessment
- Deployment procedures validated and reproducible
- Troubleshooting procedures maintained and updated

## 🎯 Guiding Technical Decisions

### Configuration Management
- **Literal Types**: Use Pydantic Literal types for type-safe configuration
- **Environment Detection**: APP_ENV drives environment-specific behavior
- **Fail-Fast Validation**: Configuration errors prevent startup rather than runtime failures

### Data Source Management  
- **SourceProvider Pattern**: Async data loading with FastAPI lifespan integration
- **Spatial Indexing**: O(log N) geographic lookups for performance
- **Fallback Chains**: Graceful degradation through multiple data sources

### State Management
- **Redis-First**: All shared state managed through Redis for multi-worker safety
- **Circuit Breakers**: API resilience through intelligent failure detection
- **Atomic Operations**: Race condition prevention through proper state management

## 🚀 Deployment & Infrastructure Management

### Railway Platform Integration
**Production Platform**: Railway (https://re-dem-elevation-backend.up.railway.app)  
**Authentication**: Logged in as `admin@road.engineering`  
**Project**: `road-engineering-DEM-Backend`  

#### Railway CLI Connection Process
```bash
# Check authentication status
railway whoami
# Output: Logged in as admin@road.engineering 👋

# Check project status  
railway status
# Output: Project: road-engineering-DEM-Backend
#         Environment: production
#         Service: dem-elevation-backend

# Manage environment variables
railway variables                           # List all variables
railway variables --set "KEY=value"        # Set new variable
railway variables --set "ENABLE_NZ_SOURCES=true"  # Example: Enable NZ sources
```

#### Critical Environment Variables
- `ENABLE_NZ_SOURCES=true` - Enables New Zealand S3 elevation sources
- `USE_S3_SOURCES=true` - Enables Australian S3 campaign sources  
- `SPATIAL_INDEX_SOURCE=s3` - Use S3-hosted spatial indexes
- `APP_ENV=production` - Production safety behaviors
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` - S3 access credentials

### AWS S3 Integration Architecture
**Main Bucket**: `road-engineering-elevation-data` (Private, contains indexes)  
**NZ Data Bucket**: `nz-elevation` (Public, contains NZ DEM files)  
**Region**: `ap-southeast-2` (Sydney)  

#### S3 Bucket Structure
```
road-engineering-elevation-data/
├── indexes/
│   ├── spatial_index.json           # 1,153 Australian campaigns
│   └── nz_spatial_index.json        # 16 NZ regions (1.08MB)
└── [campaign data files...]

nz-elevation/                         # Public bucket
├── auckland/
│   ├── auckland-north_2016-2018/
│   └── auckland-part-2_2024/
├── wellington/
├── canterbury/
└── [other NZ regions...]
```

#### AWS Connection Process
```bash
# Using environment variables from .env or Railway
AWS_ACCESS_KEY_ID=AKIA5SIDYET7N3U4JQ5H
AWS_SECRET_ACCESS_KEY=[credential]
AWS_DEFAULT_REGION=ap-southeast-2

# Upload spatial indexes (when needed)
python upload_nz_index.py              # Uploads NZ index to S3
python scripts/upload_indexes_to_s3.py # Uploads AU indexes to S3
```

#### S3 Access Patterns
- **Australian Data**: Private bucket access with AWS credentials
- **NZ Data**: Public bucket with unsigned access (`AWS_NO_SIGN_REQUEST=YES`)
- **Index Loading**: SourceProvider loads indexes from main bucket during startup
- **File Access**: Direct S3 access via GDAL VSI (`/vsis3/bucket/path`)

### Deployment Workflow
1. **Code Changes**: Commit and push to GitHub main branch
2. **Automatic Deploy**: Railway detects changes and redeploys  
3. **Environment Updates**: Use Railway CLI to set variables
4. **Health Verification**: Check `/api/v1/health` endpoint
5. **Performance Testing**: Validate response times for AU/NZ coordinates

This service achieves "Excellent" architecture status through systematic application of safety-first engineering, performance optimization, and operational excellence while maintaining clear separation between production requirements and development convenience.