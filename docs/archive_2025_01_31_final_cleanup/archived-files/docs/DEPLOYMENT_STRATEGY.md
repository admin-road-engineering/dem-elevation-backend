# DEM Backend Deployment Strategy

## 🎯 **Recommended Approach: Hybrid Development**

### **Development Environment: Miniconda**
```bash
# For local Windows development (fixes NumPy ABI error)
fix_numpy_error.bat
conda activate dem-backend-fixed
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
```

**Benefits**:
- ✅ Solves NumPy/rasterio import errors immediately
- ✅ Free for all commercial use (BSD license)
- ✅ Windows-optimized geospatial packages
- ✅ Fast setup and reliable dependencies

### **Production Environment: Docker**
```bash
# For Railway/cloud deployment (no conda dependencies)
docker build -t dem-backend .
railway up --detach
```

**Benefits**:
- ✅ No licensing concerns whatsoever
- ✅ Railway-native deployment
- ✅ Smaller production image (~200MB vs ~2GB)
- ✅ Consistent across cloud platforms

## 🔄 **Development Workflow**

### **1. Local Development**
```bash
# Use conda for reliable local development
conda activate dem-backend-fixed
python scripts/switch_environment.py local
uvicorn src.main:app --reload

# Test endpoints
curl -X POST http://localhost:8001/api/v1/elevation/point \
  -d '{"latitude": -27.4698, "longitude": 153.0251}'
```

### **2. Pre-deployment Testing**
```bash
# Test Docker build locally
docker build -t dem-backend-test .
docker run -p 8001:8000 -v ./data:/app/data dem-backend-test

# Run smoke tests
python scripts/post_deploy_smoke_test.py --url http://localhost:8001
```

### **3. Production Deployment**
```bash
# Deploy to Railway using Docker
git push origin master
railway up --detach

# Automated smoke tests run via Railway hooks
```

## 📦 **Docker Configuration (Production)**

Our `Dockerfile` already uses the optimal approach:
```dockerfile
# Uses official Python image (not conda)
FROM python:3.11-slim

# Install system dependencies for geospatial packages
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    gcc \
    g++

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```

**Why this works**:
- ✅ **apt-get gdal** provides system GDAL libraries
- ✅ **pip install** builds against system GDAL (no ABI mismatch)
- ✅ **Linux environment** doesn't have Windows DLL issues
- ✅ **No conda** in production container

## 🔍 **Comparison Matrix**

| Aspect | Miniconda (Dev) | Docker (Prod) |
|--------|-----------------|---------------|
| **NumPy ABI Issues** | ✅ Solved | ✅ Solved |
| **Windows Support** | ✅ Excellent | ⚠️ Via WSL/Docker |
| **Setup Speed** | ✅ 5 minutes | ✅ 10 minutes |
| **Licensing** | ✅ Free (BSD) | ✅ Free (MIT/BSD) |
| **Production Size** | ❌ ~2GB | ✅ ~200MB |
| **Railway Deploy** | ❌ Not supported | ✅ Native |
| **Reproducibility** | ✅ environment.yml | ✅ Dockerfile |

## 🚀 **Next Steps**

### **Immediate (Fix Local Development)**
```bash
# 1. Install Miniconda
# 2. Run fix script
fix_numpy_error.bat

# 3. Verify everything works
python verify_numpy_fix.py
```

### **Short Term (Test Production)**
```bash
# 1. Test Docker build locally
docker build -t dem-backend .
docker run -p 8001:8000 dem-backend

# 2. Verify Railway deployment still works
railway up --detach
```

### **Long Term (Full Pipeline)**
```bash
# Development workflow:
# conda activate dem-backend-fixed → develop → test → commit
# 
# Production workflow:  
# git push → Railway Docker build → automated testing → live
```

## 💡 **Alternative: Pure Docker Development**

If you prefer to avoid conda entirely:

```bash
# Use Docker for development too
docker build -t dem-backend-dev .
docker run -it -p 8001:8000 -v .:/app dem-backend-dev bash

# Inside container:
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

**Trade-offs**:
- ✅ No conda licensing questions
- ✅ Identical dev/prod environments  
- ❌ Slower Windows Docker performance
- ❌ More complex development workflow

## 🎯 **Final Recommendation**

**Use the hybrid approach**:
1. **Miniconda for local development** (fixes NumPy error, fast iteration)
2. **Docker for production** (Railway deployment, no licensing concerns)
3. **Test both environments** before major releases

This gives you the best of both worlds: reliable local development and clean production deployment.