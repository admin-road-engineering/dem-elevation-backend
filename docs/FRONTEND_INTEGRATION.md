# Frontend Integration - GeoJSON Contours

## Overview
The DEM backend now generates GeoJSON contour lines server-side, eliminating browser memory crashes and d3-contour dependency.

## API Changes

### Endpoint (Same URL)
```
POST /api/v1/elevation/contour-data
```

### Request (Unchanged)
```javascript
{
  "area_bounds": {
    "polygon_coordinates": [
      {"latitude": -28.0, "longitude": 153.4},
      {"latitude": -27.99, "longitude": 153.4},
      {"latitude": -27.99, "longitude": 153.41},
      {"latitude": -28.0, "longitude": 153.41},
      {"latitude": -28.0, "longitude": 153.4}
    ]
  },
  "max_points": 50000,
  "sampling_interval_m": 10.0
}
```

### New Response Format
```javascript
{
  "success": true,
  "contours": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "geometry": {
          "type": "LineString", 
          "coordinates": [[lng, lat], [lng, lat], ...]
        },
        "properties": {
          "elevation": 10.0,
          "elevation_units": "meters"
        }
      }
    ]
  },
  "statistics": {
    "total_points": 7553,
    "min_elevation": 1.2,
    "max_elevation": 45.8,
    "contour_count": 25,
    "elevation_intervals": [5, 10, 15, 20, 25, 30, 35, 40, 45]
  }
}
```

## Frontend Migration

### 1. Remove d3-contour
```bash
npm uninstall d3-contour
```

### 2. Update API Call (Same endpoint, new response handling)
```javascript
async function generateContours(polygonCoords) {
  const response = await fetch('/api/v1/elevation/contour-data', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      area_bounds: {
        polygon_coordinates: polygonCoords.map(coord => ({
          latitude: coord.lat,
          longitude: coord.lng
        }))
      },
      max_points: 50000,
      sampling_interval_m: 10.0
    })
  });
  
  const data = await response.json();
  
  if (!data.success) {
    throw new Error(data.message || 'Failed to generate contours');
  }
  
  return data;
}
```

### 3. Display Contours (Replace d3-contour code)
```javascript
// OLD: Complex d3-contour processing
// const contours = d3.contours()
//   .size([width, height])
//   .thresholds(levels)(elevationMatrix);

// NEW: Direct GeoJSON rendering
function displayContours(contourData) {
  // Clear existing contours
  if (contourLayer) {
    map.removeLayer(contourLayer);
  }
  
  // Add GeoJSON contours directly to map
  contourLayer = L.geoJSON(contourData.contours, {
    style: function(feature) {
      const elevation = feature.properties.elevation;
      return {
        color: getElevationColor(elevation),
        weight: elevation % 10 === 0 ? 3 : 2, // Thicker for major contours
        opacity: 0.8
      };
    },
    onEachFeature: function(feature, layer) {
      layer.bindPopup(`Elevation: ${feature.properties.elevation}m`);
    }
  }).addTo(map);
  
  // Display statistics
  displayStats(contourData.statistics);
}
```

### 4. Color Styling Function
```javascript
function getElevationColor(elevation) {
  if (elevation < 0) return '#0066cc';      // Blue (below sea level)
  if (elevation < 10) return '#00cc66';     // Green (0-10m)
  if (elevation < 50) return '#ffcc00';     // Yellow (10-50m)
  if (elevation < 100) return '#ff6600';    // Orange (50-100m)
  return '#cc0000';                         // Red (100m+)
}
```

### 5. Statistics Display
```javascript
function displayStats(stats) {
  document.getElementById('contour-info').innerHTML = `
    <div>
      <strong>Contours:</strong> ${stats.contour_count} lines<br>
      <strong>Elevation Range:</strong> ${stats.min_elevation.toFixed(1)}m - ${stats.max_elevation.toFixed(1)}m<br>
      <strong>Data Points:</strong> ${stats.total_points.toLocaleString()}<br>
      <strong>Intervals:</strong> ${stats.elevation_intervals.join(', ')}m
    </div>
  `;
}
```

## Error Handling
```javascript
try {
  const contourData = await generateContours(polygonCoords);
  displayContours(contourData);
} catch (error) {
  console.error('Contour generation failed:', error);
  showError(`Failed to generate contours: ${error.message}`);
}
```

## Benefits
- ✅ **No browser crashes** - Server handles all processing
- ✅ **Faster rendering** - Direct GeoJSON display
- ✅ **Smaller payload** - GeoJSON more compact than raw matrices
- ✅ **Simpler code** - No complex d3-contour logic needed
- ✅ **Better performance** - Server-side generation more efficient

## Backward Compatibility
Legacy endpoint available at `/api/v1/elevation/contour-data/legacy` for gradual migration if needed. 