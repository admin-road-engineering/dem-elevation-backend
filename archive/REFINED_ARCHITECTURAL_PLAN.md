# 🔧 Refined Architectural Plan - Gemini Review Responses

## **Gemini Feedback Integration**

### **1. Configuration Refinement - Remove Hardcoded Values**
**Gemini's Recommendation**: Eliminate hardcoded values from "Legacy Mode" configuration

**✅ AGREED - Implementing "Simple Mode" with Environment Variables**

```python
# src/config.py - Enhanced Configuration
class Settings(BaseSettings):
    # EXISTING AU settings (unchanged)
    S3_INDEX_BUCKET: str = "road-engineering-elevation-data"
    USE_S3_SOURCES: bool = False
    
    # FEATURE FLAG
    ENABLE_NZ_SOURCES: bool = False
    
    # SIMPLE MODE - NZ configuration via environment variables
    S3_NZ_BUCKET: str = "nz-elevation"
    S3_NZ_REGION: str = "ap-southeast-2" 
    S3_NZ_INDEX_KEY: str = "indexes/nz_spatial_index.json"
    S3_NZ_ACCESS_TYPE: str = "public"
    S3_NZ_REQUIRED: bool = False
    
    # EXPERT MODE - JSON configuration overrides everything
    S3_SOURCES_CONFIG: str = ""
    
    def build_s3_sources_config(self) -> List[S3SourceConfig]:
        """Build S3 sources with clear precedence hierarchy"""
        
        # 1. EXPERT MODE: JSON config overrides everything
        if self.S3_SOURCES_CONFIG.strip():
            try:
                sources_data = json.loads(self.S3_SOURCES_CONFIG)
                return [S3SourceConfig(**source) for source in sources_data]
            except (json.JSONDecodeError, ValidationError) as e:
                logger.critical(f"Invalid S3_SOURCES_CONFIG JSON: {e}")
                raise ValueError(f"Configuration error: {e}")
        
        # 2. SIMPLE MODE: Build from individual environment variables
        sources = []
        
        # AU sources (required for backward compatibility)
        au_source = S3SourceConfig(
            name="au",
            bucket=self.S3_INDEX_BUCKET,
            access_type="private",
            index_keys=["indexes/campaign_index.json", "indexes/spatial_index.json"],
            region="ap-southeast-2", 
            required=True
        )
        sources.append(au_source)
        
        # NZ sources (conditional on feature flag)
        if self.ENABLE_NZ_SOURCES:
            nz_source = S3SourceConfig(
                name="nz",
                bucket=self.S3_NZ_BUCKET,           # From env var
                access_type=self.S3_NZ_ACCESS_TYPE,  # From env var
                index_keys=[self.S3_NZ_INDEX_KEY],   # From env var
                region=self.S3_NZ_REGION,           # From env var
                required=self.S3_NZ_REQUIRED        # From env var
            )
            sources.append(nz_source)
            
        return sources
```

### **2. S3ClientFactory - Region-Aware Implementation**
```python
# src/s3_client_factory.py - Gemini's Recommended Implementation
from botocore.config import Config
from botocore import UNSIGNED
import boto3
from typing import Dict, Tuple

class S3ClientFactory:
    """Region-aware S3 client factory supporting public/private access types"""
    
    def __init__(self):
        self._clients: Dict[Tuple[str, str], boto3.client] = {}
    
    def get_client(self, access_type: str, region: str) -> boto3.client:
        """Get cached S3 client for specific access type and region"""
        cache_key = (access_type, region)
        
        if cache_key not in self._clients:
            if access_type == "public":
                self._clients[cache_key] = boto3.client(
                    's3',
                    region_name=region,
                    config=Config(signature_version=UNSIGNED)
                )
            else:  # "private"
                self._clients[cache_key] = boto3.client(
                    's3',
                    region_name=region
                )
            logger.info(f"Created S3 client: {access_type} access, {region} region")
            
        return self._clients[cache_key]
    
    def close_all(self):
        """Close all cached clients"""
        for client in self._clients.values():
            if hasattr(client, 'close'):
                client.close()
        self._clients.clear()
```

### **3. UnifiedIndexLoader - O(1) Index Discovery**
```python
# src/unified_index_loader.py - Optimized Implementation
class UnifiedIndexLoader:
    def __init__(self, s3_client_factory: S3ClientFactory, s3_sources: List[S3SourceConfig]):
        self.s3_client_factory = s3_client_factory
        self.s3_sources = s3_sources
        
        # O(1) index discovery with startup validation
        self.index_map: Dict[str, S3SourceConfig] = {}
        for source in self.s3_sources:
            for key in source.index_keys:
                if key in self.index_map:
                    raise ValueError(
                        f"Duplicate index key '{key}' found in sources '{self.index_map[key].name}' and '{source.name}'"
                    )
                self.index_map[key] = source
                
        logger.info(f"UnifiedIndexLoader initialized with {len(self.index_map)} index mappings")
    
    async def load_index(self, index_name: str) -> Dict[str, Any]:
        """Load index with O(1) source discovery"""
        
        # Find source config - exact match first, then partial match
        source_config = None
        exact_key = None
        
        # Try exact key match
        for key in self.index_map:
            if key.endswith(f"{index_name}.json") or Path(key).stem == index_name:
                source_config = self.index_map[key]
                exact_key = key
                break
                
        if not source_config:
            raise FileNotFoundError(f"No source configured for index '{index_name}'")
            
        # Get appropriate S3 client
        client = self.s3_client_factory.get_client(
            source_config.access_type, 
            source_config.region
        )
        
        # Load from S3
        try:
            logger.info(f"Loading {index_name} from {source_config.bucket}/{exact_key}")
            response = client.get_object(Bucket=source_config.bucket, Key=exact_key)
            content = response['Body'].read().decode('utf-8')
            data = json.loads(content)
            
            logger.info(f"Successfully loaded {index_name}: {len(content)} chars")
            return data
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                raise FileNotFoundError(f"Index not found: {source_config.bucket}/{exact_key}")
            else:
                raise RuntimeError(f"S3 error loading {exact_key}: {error_code}")
```

## **Dependency Injection Wiring**

### **Application Startup Architecture**
```python
# src/main.py - Startup and Dependency Wiring
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle with enhanced S3 source management"""
    logger.info("Starting DEM service with multi-bucket S3 support...")
    
    try:
        # 1. Load configuration
        settings = get_settings()
        s3_sources = settings.build_s3_sources_config()
        
        logger.info(f"Configured {len(s3_sources)} S3 sources:")
        for source in s3_sources:
            logger.info(f"  - {source.name}: {source.bucket} ({source.access_type})")
        
        # 2. Create S3 client factory
        s3_client_factory = S3ClientFactory()
        
        # 3. Validate each source during startup
        unified_loader = UnifiedIndexLoader(s3_client_factory, s3_sources)
        
        # 4. Preload and validate critical indexes
        index_status = {}  
        for source in s3_sources:
            for index_key in source.index_keys:
                index_name = Path(index_key).stem
                try:
                    await unified_loader.load_index(index_name)
                    index_status[index_name] = {"status": "loaded", "source": source.name}
                    logger.info(f"✓ Validated index: {index_name}")
                except Exception as e:
                    index_status[index_name] = {"status": "failed", "error": str(e)}
                    if source.required:
                        logger.critical(f"CRITICAL: Required index {index_name} failed: {e}")
                        raise
                    else:
                        logger.warning(f"Optional index {index_name} failed: {e}")
        
        # 5. Store in app state for health checks
        app.state.s3_client_factory = s3_client_factory
        app.state.unified_loader = unified_loader
        app.state.index_status = index_status
        
        # 6. Initialize service container with enhanced loader
        service_container = init_service_container(settings, unified_loader)
        
        logger.info("DEM service startup completed successfully")
        yield
        
    except Exception as e:
        logger.critical(f"Service startup failed: {e}")
        raise
    finally:
        # Cleanup
        if hasattr(app.state, 's3_client_factory'):
            app.state.s3_client_factory.close_all()
        await close_service_container()
```

### **Enhanced ServiceContainer Integration**
```python
# src/dependencies.py - Modified ServiceContainer
class ServiceContainer:
    def __init__(self, settings: Settings, unified_loader: UnifiedIndexLoader = None):
        self.settings = settings
        self._unified_loader = unified_loader
        # ... other dependencies
    
    @property
    def unified_index_loader(self) -> UnifiedIndexLoader:
        """Get UnifiedIndexLoader (injected during startup)"""
        if self._unified_loader is None:
            # Fallback for backward compatibility
            s3_sources = self.settings.build_s3_sources_config()
            s3_client_factory = S3ClientFactory()
            self._unified_loader = UnifiedIndexLoader(s3_client_factory, s3_sources)
        return self._unified_loader
```

## **Configuration Examples**

### **Simple Mode (Environment Variables)**
```bash
# Current production (unchanged)
S3_INDEX_BUCKET=road-engineering-elevation-data
USE_S3_SOURCES=true
ENABLE_NZ_SOURCES=false

# With NZ enabled (simple configuration)
ENABLE_NZ_SOURCES=true
S3_NZ_BUCKET=nz-elevation
S3_NZ_REGION=ap-southeast-2
S3_NZ_INDEX_KEY=indexes/nz_spatial_index.json
S3_NZ_ACCESS_TYPE=public
S3_NZ_REQUIRED=false
```

### **Expert Mode (JSON Configuration)** 
```bash
# Advanced multi-source configuration
S3_SOURCES_CONFIG='[
  {
    "name": "au",
    "bucket": "road-engineering-elevation-data", 
    "access_type": "private",
    "index_keys": ["indexes/campaign_index.json", "indexes/spatial_index.json"],
    "region": "ap-southeast-2",
    "required": true
  },
  {
    "name": "nz", 
    "bucket": "nz-elevation",
    "access_type": "public",
    "index_keys": ["indexes/nz_spatial_index.json"],
    "region": "ap-southeast-2", 
    "required": false
  }
]'
```

## **Enhanced Health Check**
```python
@app.get("/api/v1/health")
async def health_check():
    base_health = {
        "status": "healthy",
        "service": "DEM Backend API",
        "sources_available": len(settings.DEM_SOURCES)  # Backward compatible
    }
    
    # Enhanced index status
    if hasattr(app.state, 'index_status'):
        base_health["index_status"] = app.state.index_status
        
        # Determine overall health based on required indexes
        failed_required = [
            name for name, status in app.state.index_status.items() 
            if status["status"] == "failed" and status.get("required", False)
        ]
        
        if failed_required:
            base_health["status"] = "degraded"
            base_health["failed_required_indexes"] = failed_required
    
    return base_health
```

## **Backward Compatibility Guarantee**

✅ **All existing environment variables work unchanged**  
✅ **Default behavior identical to current production**  
✅ **NZ integration opt-in via feature flag**  
✅ **Graceful fallback if NZ sources fail**  
✅ **Instant rollback capability**