# NZ S3 Configuration Summary

## 🎯 **ANSWER: Minimal Configuration Required**

The NZ S3 data needs **very little configuration** because it's a public AWS Open Data bucket.

## 🔧 **Required Changes**

### **1. DEM_SOURCES Update**
```json
{
  "nz_auckland": {
    "path": "s3://nz-elevation/auckland/",
    "crs": "EPSG:2193",
    "description": "NZ Auckland 1m LiDAR DEM"
  },
  "nz_wellington": {
    "path": "s3://nz-elevation/wellington/",
    "crs": "EPSG:2193", 
    "description": "NZ Wellington 1m LiDAR DEM"
  },
  "nz_national": {
    "path": "s3://nz-elevation/",
    "crs": "EPSG:2193",
    "description": "NZ National 1m LiDAR DEM"
  }
}
```

### **2. Environment Variables**
```bash
USE_S3_SOURCES=true
AWS_DEFAULT_REGION=ap-southeast-2
```

### **3. What's NOT Required**
- ❌ **No AWS credentials** (public bucket)
- ❌ **No code changes** (service ready)
- ❌ **No special S3 setup** (works with existing boto3)
- ❌ **No CRS configuration** (GDAL handles EPSG:2193 → EPSG:4326)

## 🎯 **Key Points**

1. **Public Bucket**: `s3://nz-elevation` requires no authentication
2. **Directory Paths**: Use `s3://nz-elevation/region/` not specific files
3. **CRS Handling**: Service automatically converts EPSG:2193 to EPSG:4326
4. **Regional Coverage**: Add multiple regions for full NZ coverage

## 🚀 **Implementation**

**Replace current NZ config:**
```json
// OLD (limited)
"nz_elevation": {
  "path": "s3://nz-elevation/canterbury/canterbury_2018-2019_DEM_1m.tif"
}

// NEW (full coverage)
"nz_auckland": {"path": "s3://nz-elevation/auckland/", "crs": "EPSG:2193"},
"nz_wellington": {"path": "s3://nz-elevation/wellington/", "crs": "EPSG:2193"},
"nz_canterbury": {"path": "s3://nz-elevation/canterbury/", "crs": "EPSG:2193"}
```

**That's it!** Service will automatically:
- Access public bucket without credentials
- Transform coordinates from EPSG:2193 to EPSG:4326
- Find appropriate elevation files in each region directory

---

**Bottom Line**: Just update DEM_SOURCES with regional directory paths and set `USE_S3_SOURCES=true`. No special setup needed!