# New Zealand S3 Configuration Guide

**For AWS Open Data NZ Elevation** (`s3://nz-elevation`)

## 🎯 Configuration Requirements Summary

### **NO SPECIAL SETUP NEEDED** - Public bucket works with existing service!

The NZ elevation data requires **minimal configuration changes** because:
- ✅ **No AWS credentials required** (public bucket)
- ✅ **GDAL/rasterio handles CRS transformation** automatically
- ✅ **Service already supports S3 paths**
- ✅ **Existing S3SourceManager has NZ support**

## 🔧 Required Configuration Changes

### 1. **DEM_SOURCES Configuration**

**Current (Limited):**
```json
{
  "nz_elevation": {
    "path": "s3://nz-elevation/canterbury/canterbury_2018-2019_DEM_1m.tif",
    "crs": "EPSG:2193",
    "description": "NZ Canterbury 1m DEM (AWS Open Data)"
  }
}
```

**Recommended (Full Coverage):**
```json
{
  "nz_auckland": {
    "path": "s3://nz-elevation/auckland/",
    "crs": "EPSG:2193",
    "description": "NZ Auckland 1m LiDAR DEM (LINZ Open Data)"
  },
  "nz_wellington": {
    "path": "s3://nz-elevation/wellington/",
    "crs": "EPSG:2193", 
    "description": "NZ Wellington 1m LiDAR DEM (LINZ Open Data)"
  },
  "nz_canterbury": {
    "path": "s3://nz-elevation/canterbury/",
    "crs": "EPSG:2193",
    "description": "NZ Canterbury 1m LiDAR DEM (LINZ Open Data)"
  },
  "nz_otago": {
    "path": "s3://nz-elevation/otago/",
    "crs": "EPSG:2193",
    "description": "NZ Otago 1m LiDAR DEM (LINZ Open Data)"
  },
  "nz_national": {
    "path": "s3://nz-elevation/",
    "crs": "EPSG:2193",
    "description": "NZ National 1m LiDAR DEM (LINZ Open Data)"
  }
}
```

### 2. **Environment Variables**

**Required:**
```bash
USE_S3_SOURCES=true
AWS_DEFAULT_REGION=ap-southeast-2
```

**Optional (for public bucket):**
```bash
# NOT REQUIRED - bucket is public
AWS_ACCESS_KEY_ID=not_needed
AWS_SECRET_ACCESS_KEY=not_needed
```

### 3. **Service Configuration**

**No changes needed** - existing service handles:
- ✅ **S3 access** via boto3
- ✅ **Public buckets** (unsigned requests)
- ✅ **CRS transformation** via GDAL
- ✅ **Directory-based paths** for multiple files

## 📁 File Structure Understanding

### **NZ Elevation Bucket Structure:**
```
s3://nz-elevation/
├── auckland/
│   ├── auckland-north_2016-2018/
│   │   └── dem_1m/2193/
│   │       ├── AY30_10000_0405.tiff
│   │       └── AY30_10000_0405.json
│   └── auckland-south_2017-2019/
│       └── dem_1m/2193/
├── wellington/
│   ├── hutt-city_2021/
│   │   └── dem_1m/2193/
│   └── wellington-city_2019/
│       └── dem_1m/2193/
├── canterbury/
│   ├── amberley_2012/
│   │   └── dem_1m/2193/
│   └── christchurch_2018/
│       └── dem_1m/2193/
```

### **Configuration Strategy:**
- **Regional paths**: `s3://nz-elevation/auckland/` - covers all surveys in region
- **Specific surveys**: `s3://nz-elevation/auckland/auckland-north_2016-2018/dem_1m/2193/` - single survey
- **National path**: `s3://nz-elevation/` - covers all of New Zealand

## 🚀 Implementation Steps

### **Step 1: Update Environment File**
```bash
# Edit .env or .env.api-test
DEM_SOURCES={"nz_auckland":{"path":"s3://nz-elevation/auckland/","crs":"EPSG:2193","description":"NZ Auckland 1m LiDAR DEM"},"nz_wellington":{"path":"s3://nz-elevation/wellington/","crs":"EPSG:2193","description":"NZ Wellington 1m LiDAR DEM"},"nz_canterbury":{"path":"s3://nz-elevation/canterbury/","crs":"EPSG:2193","description":"NZ Canterbury 1m LiDAR DEM"},"nz_national":{"path":"s3://nz-elevation/","crs":"EPSG:2193","description":"NZ National 1m LiDAR DEM"}}

USE_S3_SOURCES=true
AWS_DEFAULT_REGION=ap-southeast-2
```

### **Step 2: Restart Service**
```bash
# Kill current service
# Start with new configuration
uvicorn src.main:app --host 0.0.0.0 --port 8001
```

### **Step 3: Test NZ Coordinates**
```bash
# Test Auckland
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -36.8485, "longitude": 174.7633}'

# Test Wellington  
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -41.2924, "longitude": 174.7787}'
```

## 🔧 Service Code Changes (Optional)

### **S3SourceManager Already Supports NZ:**
```python
# In src/s3_source_manager.py line 47
if self.bucket_name == "nz-elevation":
    return self._build_nz_catalog()
```

### **No Code Changes Required** - Service handles:
- ✅ **Public bucket access** (unsigned requests)
- ✅ **EPSG:2193 to EPSG:4326** transformation
- ✅ **Directory-based S3 paths**
- ✅ **Multiple file discovery**

## 🎯 Testing Configuration

### **Test 1: Verify Sources**
```bash
curl http://localhost:8001/api/v1/elevation/sources
# Should show nz_* sources
```

### **Test 2: NZ Coordinates**
```bash
# Major NZ cities
Auckland:     -36.8485, 174.7633
Wellington:   -41.2924, 174.7787  
Christchurch: -43.5321, 172.6362
Queenstown:   -45.0312, 168.6626
```

### **Test 3: Performance**
```bash
# Should return elevation data within 10 seconds
# If timeout, check S3 connectivity
```

## ⚠️ Known Issues & Solutions

### **Issue 1: Timeout on NZ Queries**
**Cause:** Service trying to access wrong file path or S3 connectivity
**Solution:** 
- Ensure `USE_S3_SOURCES=true`
- Check AWS region setting
- Verify directory paths (not specific files)

### **Issue 2: CRS Transformation**
**Cause:** EPSG:2193 to EPSG:4326 conversion
**Solution:** 
- No action needed - GDAL handles automatically
- Ensure `crs: "EPSG:2193"` in DEM_SOURCES

### **Issue 3: Multiple Files per Region**
**Cause:** Each region has multiple surveys/files
**Solution:**
- Use directory paths: `s3://nz-elevation/auckland/`
- Service will find appropriate files automatically

## 🎉 Production Configuration

### **Complete Production DEM_SOURCES:**
```json
{
  "local_dtm_gdb": {
    "path": "./data/DTM.gdb",
    "crs": "EPSG:4326",
    "description": "Local DTM geodatabase"
  },
  "act_elvis": {
    "path": "s3://road-engineering-elevation-data/act-elvis/",
    "crs": "EPSG:3577",
    "description": "Australia ACT 1m LiDAR DEM"
  },
  "nz_auckland": {
    "path": "s3://nz-elevation/auckland/",
    "crs": "EPSG:2193",
    "description": "NZ Auckland 1m LiDAR DEM (LINZ Open Data)"
  },
  "nz_wellington": {
    "path": "s3://nz-elevation/wellington/",
    "crs": "EPSG:2193",
    "description": "NZ Wellington 1m LiDAR DEM (LINZ Open Data)"
  },
  "nz_canterbury": {
    "path": "s3://nz-elevation/canterbury/",
    "crs": "EPSG:2193",
    "description": "NZ Canterbury 1m LiDAR DEM (LINZ Open Data)"
  },
  "nz_otago": {
    "path": "s3://nz-elevation/otago/",
    "crs": "EPSG:2193",
    "description": "NZ Otago 1m LiDAR DEM (LINZ Open Data)"
  },
  "gpxz_api": {
    "path": "api://gpxz",
    "crs": "EPSG:4326",
    "description": "GPXZ.io Global Elevation API"
  }
}
```

### **Environment Settings:**
```bash
USE_S3_SOURCES=true
USE_API_SOURCES=true
AWS_DEFAULT_REGION=ap-southeast-2
DEFAULT_DEM_ID=local_dtm_gdb
```

## 📊 Expected Performance

### **Response Times:**
- **Local queries**: <1s
- **Australia S3**: 2-5s
- **NZ S3**: 3-8s (public bucket)
- **GPXZ fallback**: <2s

### **Coverage:**
- **Australia**: 5 regions via private S3
- **New Zealand**: 16 regions via public S3
- **Global**: GPXZ API fallback

---

## 📋 **SUMMARY**

**NZ S3 Configuration Requirements:**
- ✅ **Minimal setup** - use directory paths in DEM_SOURCES
- ✅ **No credentials** - public bucket works automatically
- ✅ **No code changes** - existing service supports NZ elevation
- ✅ **Regional coverage** - configure multiple NZ regions
- ✅ **CRS handling** - automatic EPSG:2193 to EPSG:4326 conversion

**Key change:** Update DEM_SOURCES to use `s3://nz-elevation/region/` directory paths instead of specific files.