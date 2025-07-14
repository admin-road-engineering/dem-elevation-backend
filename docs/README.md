# DEM Elevation Service

A dedicated elevation data service using FastAPI that serves elevation data extracted directly from configured Digital Elevation Model (DEM) files **and geodatabases** based on input geospatial queries.

## Features

- **Multiple DEM Source Support**: Configure multiple DEM sources with unique identifiers
- **📊 Geodatabase Support**: Direct support for ESRI File Geodatabases (.gdb) with automatic layer discovery
- **Automatic CRS Handling**: Transforms coordinates from WGS84 to native DEM CRS automatically
- **Bilinear Interpolation**: Uses bilinear interpolation for accurate elevation sampling
- **Great Circle Line Generation**: Generates equally spaced points along great circle paths
- **Async Support**: Utilizes FastAPI's async capabilities with thread pooling for blocking I/O
- **Intelligent Caching**: Implements caching for DEM datasets and CRS transformers for performance
- **Comprehensive Error Handling**: Robust error handling for various edge cases
- **Auto Layer Discovery**: Automatically finds raster layers within geodatabases

## API Endpoints

### Health Check
- `GET /` - Basic health check with feature list
- `GET /health` - Detailed health check with configuration info

### DEM Source Management
- `GET /v1/elevation/sources` - List all configured DEM sources
- `GET /v1/elevation/sources/{source_id}/info` - Get detailed information about a specific source

### Elevation Services
- `POST /v1/elevation/point` - Get elevation for a single point
- `POST /v1/elevation/line` - Get elevations along a line segment
- `POST /v1/elevation/path` - Get elevations for a list of discrete points

## Configuration

The service uses environment variables for configuration. Create a `.env` file in the project root:

```env
# DEM Sources Configuration - Supports both GeoTIFF and Geodatabase formats
DEM_SOURCES={
  "local_dtm_gdb": {
    "path": "./data/source/DTM.gdb",
    "layer": null,
    "crs": null,
    "description": "Local DTM from geodatabase - auto-discovery enabled"
  },
  "converted_dtm": {
    "path": "./data/dems/dtm.tif",
    "layer": null,
    "crs": null,
    "description": "Converted DTM in GeoTIFF format"
  },
  "specific_layer_gdb": {
    "path": "./data/source/LiDAR.gdb",
    "layer": "DTM_1m",
    "crs": "EPSG:28356",
    "description": "High resolution LiDAR DTM with specific layer"
  }
}

# Set the default DEM source
DEFAULT_DEM_ID=local_dtm_gdb

# Geodatabase settings
GDB_AUTO_DISCOVER=true
GDB_PREFERRED_DRIVERS=["OpenFileGDB", "FileGDB"]

# Performance settings
CACHE_SIZE_LIMIT=10
```

### Configuration Notes

1. **DEM_SOURCES**: A JSON object mapping unique source IDs to DEM configuration
   - `path`: File path to GeoTIFF file OR geodatabase (.gdb directory)
   - `layer`: Optional - specific layer name within geodatabase (auto-discovered if null)
   - `crs`: Optional explicit CRS (EPSG code or WKT). If null, reads from file metadata
   - `description`: Optional description for documentation

2. **DEFAULT_DEM_ID**: Optional. If not set, uses the first source in DEM_SOURCES

3. **Geodatabase Settings**:
   - `GDB_AUTO_DISCOVER`: Enable automatic raster layer discovery in geodatabases
   - `GDB_PREFERRED_DRIVERS`: Order of GDAL drivers to try for geodatabase access

4. **Supported Formats**: 
   - GeoTIFF files (.tif, .tiff)
   - ESRI File Geodatabases (.gdb) with automatic layer discovery

## Installation & Setup

### Local Development

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd dem-elevation-service
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   # Create .env file with your DEM sources configuration
   cp env.example .env
   # Edit .env with your actual DEM file paths and geodatabase paths
   ```

4. **Run the service**
   ```bash
   python main.py
   # Or using uvicorn directly:
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

### Docker Deployment

1. **Build the Docker image**
   ```bash
   docker build -t dem-elevation-service .
   ```

2. **Run with Docker**
   ```bash
   # Mount your DEM data directory and .env file
   docker run -p 8000:8000 \
     -v /path/to/your/data:/data:ro \
     -v /path/to/your/.env:/app/.env:ro \
     dem-elevation-service
   ```

3. **Using Docker Compose** (recommended)
   ```bash
   docker-compose up --build
   ```

## API Usage Examples

### List Available Sources
```bash
curl "http://localhost:8000/v1/elevation/sources"
```

### Get Source Information
```bash
curl "http://localhost:8000/v1/elevation/sources/local_dtm_gdb/info"
```

### Point Elevation
```bash
curl -X POST "http://localhost:8000/v1/elevation/point" \
     -H "Content-Type: application/json" \
     -d '{
       "latitude": -33.8688,
       "longitude": 151.2093,
       "dem_source_id": "local_dtm_gdb"
     }'
```

### Line Elevation
```bash
curl -X POST "http://localhost:8000/v1/elevation/line" \
     -H "Content-Type: application/json" \
     -d '{
       "start_point": {"latitude": -33.8688, "longitude": 151.2093},
       "end_point": {"latitude": -33.8700, "longitude": 151.2100},
       "num_points": 5,
       "dem_source_id": "local_dtm_gdb"
     }'
```

### Path Elevation
```bash
curl -X POST "http://localhost:8000/v1/elevation/path" \
     -H "Content-Type: application/json" \
     -d '{
       "points": [
         {"latitude": -33.8688, "longitude": 151.2093, "id": "point1"},
         {"latitude": -33.8700, "longitude": 151.2100, "id": "point2"}
       ],
       "dem_source_id": "local_dtm_gdb"
     }'
```

## Geodatabase Support

### Automatic Layer Discovery
The service automatically discovers raster layers within geodatabases by:
1. Trying common raster layer names (DTM, DEM, elevation, etc.)
2. Listing all layers and testing each for raster content
3. Using various access patterns and drivers

### Manual Layer Specification
For geodatabases with multiple raster layers or non-standard names:
```env
DEM_SOURCES={
  "specific_layer": {
    "path": "./data/my_geodatabase.gdb",
    "layer": "Custom_DTM_Layer_Name"
  }
}
```

### Supported Geodatabase Types
- ESRI File Geodatabases (.gdb)
- Uses OpenFileGDB and FileGDB drivers
- Automatic fallback between drivers
- Support for both raster and potentially mixed geodatabases

## Dependencies

- **FastAPI**: Web framework
- **Pydantic**: Data validation and settings management
- **rasterio**: Reading DEM files and elevation sampling
- **fiona**: Geodatabase layer discovery and access
- **pyproj**: CRS transformations and great circle calculations
- **numpy**: Numerical operations
- **uvicorn**: ASGI server

## Error Handling

The service provides comprehensive error handling:

- **400 Bad Request**: Invalid input data, coordinates out of range
- **404 Not Found**: DEM source not found in configuration
- **500 Internal Server Error**: File access issues, processing errors
- **503 Service Unavailable**: Service initialization failures

**Geodatabase-specific handling**:
- Automatic fallback between different geodatabase drivers
- Informative error messages for layer discovery issues
- Graceful handling of permission and access issues

Points outside DEM bounds return `null` elevation with descriptive messages.

## Performance Considerations

- **Intelligent Caching**: DEM datasets and CRS transformers are cached per source
- **Thread Pool**: Blocking I/O operations run in thread pools to maintain async performance
- **Resource Management**: Proper cleanup of resources on service shutdown
- **Geodatabase Optimization**: Efficient layer discovery and caching for geodatabases

## Logging

The service includes comprehensive logging:
- Service initialization and configuration
- Geodatabase layer discovery process
- DEM file access and caching
- Request processing and errors
- Performance metrics

Logs are output in structured format with timestamps and log levels.

## Production Deployment

For production deployment:

1. **Configure appropriate CORS origins** in `main.py`
2. **Use environment-specific logging levels**
3. **Mount DEM data as read-only volumes**
4. **Set up proper monitoring and health checks**
5. **Consider using a reverse proxy** (nginx, Traefik)
6. **Implement rate limiting** if needed
7. **Optimize cache settings** based on available memory

## Integration Example

This service can be used as a backend for other applications. For example, to replace elevation fetching in an existing `fetching.py` component:

```python
import httpx

async def get_elevation_from_service(latitude: float, longitude: float, dem_source: str = None):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://dem-service:8000/v1/elevation/point",
            json={
                "latitude": latitude,
                "longitude": longitude,
                "dem_source_id": dem_source
            }
        )
        if response.status_code == 200:
            data = response.json()
            return data["elevation_m"]
        else:
            return None

# List available sources
async def get_available_dem_sources():
    async with httpx.AsyncClient() as client:
        response = await client.get("http://dem-service:8000/v1/elevation/sources")
        if response.status_code == 200:
            return response.json()["sources"]
        return {}
```

## License

[Add your license information here]

## Contributing

[Add contribution guidelines here]

## Troubleshooting

### GDAL Errors with .gdb Files

If you see GDAL errors like these in your logs:
```
GDAL signalled an error: err_no=1, msg='Error occurred in C:\vcpkg\buildtrees\gdal\src\v3.9.3-e3a570b154.clean\ogr\ogrsf_frmts\openfilegdb\filegdbtable.cpp at line 1656'
GDAL signalled an error: err_no=1, msg='Error occurred in C:\vcpkg\buildtrees\gdal\src\v3.9.3-e3a570b154.clean\ogr\ogrsf_frmts\openfilegdb\filegdbtable.cpp at line 1518'
```

These are **non-critical errors** from GDAL's OpenFileGDB driver when reading ESRI File Geodatabases. They typically occur during metadata reading but don't prevent elevation data access.

#### Error Suppression (Default: Enabled)
The service automatically suppresses these errors by default. You can control this behavior:

```env
# Suppress non-critical GDAL errors (recommended for production)
SUPPRESS_GDAL_ERRORS=true

# Set to false to see all GDAL messages (useful for debugging)
SUPPRESS_GDAL_ERRORS=false

# Control GDAL logging level
GDAL_LOG_LEVEL=ERROR
```

#### Testing Error Suppression
Run the test script to verify error suppression is working:
```bash
python test_error_suppression.py
```

#### Manual GDAL Configuration
You can also configure GDAL environment variables manually:
```bash
export CPL_LOG_ERRORS=OFF
export CPL_DEBUG=OFF
export GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR
```

### Common Issues 