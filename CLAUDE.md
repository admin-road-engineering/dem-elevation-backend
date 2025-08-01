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

### Phase 3B.3.2: Advanced Pattern Refinements (Next)
**Gemini Roadmap**: *"Strategic refinements to build upon this outstanding foundation for ultimate A+ composability"*

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

This service achieves "Excellent" architecture status through systematic application of safety-first engineering, performance optimization, and operational excellence while maintaining clear separation between production requirements and development convenience.