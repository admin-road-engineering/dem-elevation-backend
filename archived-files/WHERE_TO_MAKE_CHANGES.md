# Where to Make NZ S3 Configuration Changes

## 🎯 **CURRENT ACTIVE FILE: `.env`**

Your service is currently using the `.env` file (api-test configuration).

## 📁 **File Location**
```
C:\Users\Admin\DEM Backend\.env
```

## 🔧 **What to Change**

### **Current Content (Line 2):**
```json
DEM_SOURCES={"gpxz_api": {"path": "api://gpxz", "layer": null, "crs": null, "description": "GPXZ.io API (free tier 100/day)"}, "nz_elevation": {"path": "s3://nz-elevation/canterbury/canterbury_2018-2019_DEM_1m.tif", "layer": null, "crs": "EPSG:2193", "description": "NZ Canterbury 1m DEM (AWS Open Data)"}, "local_fallback": {"path": "./data/DTM.gdb", "layer": null, "crs": null, "description": "Local fallback"}}
```

### **Updated Content (Replace line 2):**
```json
DEM_SOURCES={"gpxz_api": {"path": "api://gpxz", "layer": null, "crs": null, "description": "GPXZ.io API (free tier 100/day)"}, "nz_auckland": {"path": "s3://nz-elevation/auckland/", "layer": null, "crs": "EPSG:2193", "description": "NZ Auckland 1m LiDAR DEM (LINZ Open Data)"}, "nz_wellington": {"path": "s3://nz-elevation/wellington/", "layer": null, "crs": "EPSG:2193", "description": "NZ Wellington 1m LiDAR DEM (LINZ Open Data)"}, "nz_canterbury": {"path": "s3://nz-elevation/canterbury/", "layer": null, "crs": "EPSG:2193", "description": "NZ Canterbury 1m LiDAR DEM (LINZ Open Data)"}, "nz_otago": {"path": "s3://nz-elevation/otago/", "layer": null, "crs": "EPSG:2193", "description": "NZ Otago 1m LiDAR DEM (LINZ Open Data)"}, "nz_national": {"path": "s3://nz-elevation/", "layer": null, "crs": "EPSG:2193", "description": "NZ National 1m LiDAR DEM (LINZ Open Data)"}, "local_fallback": {"path": "./data/DTM.gdb", "layer": null, "crs": null, "description": "Local fallback"}}
```

## 🛠️ **How to Make the Change**

### **Option 1: Use Text Editor**
1. Open `C:\Users\Admin\DEM Backend\.env` in your text editor
2. Replace line 2 with the updated DEM_SOURCES above
3. Save the file

### **Option 2: Command Line**
```bash
# Create backup first
cp .env .env.backup.$(date +%Y%m%d_%H%M%S)

# Edit with your preferred editor
nano .env
# or
code .env
```

### **Option 3: I can make the change for you**
I can update the file directly if you'd like.

## 🔄 **After Making Changes**

### **1. Restart the Service**
```bash
# Stop current service (Ctrl+C)
# Start with new configuration
"/c/Users/Admin/miniconda3/Scripts/uvicorn.exe" src.main:app --host 0.0.0.0 --port 8001
```

### **2. Test the Changes**
```bash
# Check sources
curl http://localhost:8001/api/v1/elevation/sources

# Test NZ coordinates
curl -X POST "http://localhost:8001/api/v1/elevation/point" \
  -H "Content-Type: application/json" \
  -d '{"latitude": -36.8485, "longitude": 174.7633}'
```

## 📝 **Key Changes Made**

1. **Replaced single file path** with **directory paths**:
   - `s3://nz-elevation/canterbury/specific_file.tif` → `s3://nz-elevation/canterbury/`

2. **Added multiple NZ regions**:
   - `nz_auckland` → Auckland region
   - `nz_wellington` → Wellington region  
   - `nz_canterbury` → Canterbury region (updated)
   - `nz_otago` → Otago region
   - `nz_national` → All of New Zealand

3. **Kept existing sources**:
   - `gpxz_api` → GPXZ.io API (unchanged)
   - `local_fallback` → Local DTM (unchanged)

## 🎯 **Result**

After this change, your service will have:
- ✅ **GPXZ.io API** for global coverage
- ✅ **5 NZ regions** from AWS Open Data
- ✅ **Local fallback** for development
- ✅ **Full New Zealand coverage** with 1m resolution

---

## 📍 **SUMMARY**

**File to edit:** `C:\Users\Admin\DEM Backend\.env`  
**Line to change:** Line 2 (DEM_SOURCES)  
**Action:** Replace single NZ file with multiple NZ regions