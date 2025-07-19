# Frontend Integration Guide - S3 → GPXZ → Google Fallback Chain

## Overview

The DEM Backend now operates with a **S3 → GPXZ → Google fallback chain** architecture, providing reliable elevation data with global coverage. This guide covers frontend integration for React applications.

## Architecture Benefits

### Fallback Chain Reliability
- **Priority 1**: S3 Sources (High-resolution regional data)
- **Priority 2**: GPXZ.io API (Global coverage)
- **Priority 3**: Google Elevation API (Final fallback)

### Direct Frontend Access
- **CORS enabled** for direct frontend calls
- **No proxy required** for basic elevation requests
- **Consistent response format** across all sources

## Core Integration

### Base Configuration

```javascript
// config/elevation.js
export const ELEVATION_CONFIG = {
  BASE_URL: process.env.NODE_ENV === 'production' 
    ? 'https://dem-api.road.engineering' 
    : 'http://localhost:8001',
  
  // Fallback chain provides automatic reliability
  TIMEOUT: 10000, // 10 seconds (includes fallback time)
  RETRY_ATTEMPTS: 1, // Service handles internal retries
  
  // Rate limiting awareness
  RATE_LIMIT_BUFFER: 0.9 // Use 90% of available quota
};
```

### Single Point Elevation

```javascript
// utils/elevation.js
export async function getElevation(latitude, longitude) {
  try {
    const response = await fetch(`${ELEVATION_CONFIG.BASE_URL}/api/v1/elevation/point`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ latitude, longitude }),
      signal: AbortSignal.timeout(ELEVATION_CONFIG.TIMEOUT)
    });
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const data = await response.json();
    
    // Response format with fallback chain info
    return {
      elevation: data.elevation_m,
      source: data.dem_source_used, // "s3_sources", "gpxz_api", or "google_api"
      coordinates: { latitude: data.latitude, longitude: data.longitude },
      success: data.elevation_m !== null,
      message: data.message
    };
    
  } catch (error) {
    console.error('Elevation request failed:', error);
    return { elevation: null, success: false, error: error.message };
  }
}
```

### Batch Elevation Requests

```javascript
// utils/elevation.js
export async function getBatchElevation(points) {
  try {
    const response = await fetch(`${ELEVATION_CONFIG.BASE_URL}/api/v1/elevation/points`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ points }),
      signal: AbortSignal.timeout(ELEVATION_CONFIG.TIMEOUT)
    });
    
    const data = await response.json();
    
    // Process batch results
    return data.map(point => ({
      elevation: point.elevation_m,
      source: point.dem_source_used,
      coordinates: { latitude: point.latitude, longitude: point.longitude },
      success: point.elevation_m !== null
    }));
    
  } catch (error) {
    console.error('Batch elevation request failed:', error);
    return points.map(() => ({ elevation: null, success: false }));
  }
}
```

## React Hook Integration

### useElevation Hook

```javascript
// hooks/useElevation.js
import { useState, useCallback } from 'react';
import { getElevation, getBatchElevation } from '../utils/elevation';

export function useElevation() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastSource, setLastSource] = useState(null);
  
  const fetchElevation = useCallback(async (latitude, longitude) => {
    setLoading(true);
    setError(null);
    
    try {
      const result = await getElevation(latitude, longitude);
      setLastSource(result.source);
      
      if (!result.success) {
        setError(result.message || 'No elevation data available');
        return null;
      }
      
      return result.elevation;
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);
  
  const fetchBatchElevation = useCallback(async (points) => {
    setLoading(true);
    setError(null);
    
    try {
      const results = await getBatchElevation(points);
      const sources = [...new Set(results.map(r => r.source))];
      setLastSource(sources.length === 1 ? sources[0] : `Mixed: ${sources.join(', ')}`);
      
      return results;
    } catch (err) {
      setError(err.message);
      return [];
    } finally {
      setLoading(false);
    }
  }, []);
  
  return {
    fetchElevation,
    fetchBatchElevation,
    loading,
    error,
    lastSource // Shows which fallback source was used
  };
}
```

### Component Usage

```javascript
// components/ElevationDisplay.jsx
import React, { useState } from 'react';
import { useElevation } from '../hooks/useElevation';

export function ElevationDisplay({ latitude, longitude }) {
  const { fetchElevation, loading, error, lastSource } = useElevation();
  const [elevation, setElevation] = useState(null);
  
  const handleFetchElevation = async () => {
    const result = await fetchElevation(latitude, longitude);
    setElevation(result);
  };
  
  const getSourceBadge = (source) => {
    const sourceConfig = {
      's3_sources': { label: 'S3', color: 'green', description: 'High-resolution' },
      'gpxz_api': { label: 'GPXZ', color: 'blue', description: 'Global API' },
      'google_api': { label: 'Google', color: 'orange', description: 'Fallback' }
    };
    
    const config = sourceConfig[source] || { label: source, color: 'gray' };
    
    return (
      <span 
        className={`px-2 py-1 rounded text-sm bg-${config.color}-100 text-${config.color}-800`}
        title={config.description}
      >
        {config.label}
      </span>
    );
  };
  
  return (
    <div className="p-4 border rounded">
      <h3 className="font-semibold mb-2">Elevation Data</h3>
      
      <div className="space-y-2">
        <p>Location: {latitude.toFixed(6)}, {longitude.toFixed(6)}</p>
        
        {elevation !== null && (
          <div className="flex items-center gap-2">
            <p>Elevation: {elevation.toFixed(2)}m</p>
            {lastSource && getSourceBadge(lastSource)}
          </div>
        )}
        
        {error && (
          <p className="text-red-600">Error: {error}</p>
        )}
        
        <button
          onClick={handleFetchElevation}
          disabled={loading}
          className="px-4 py-2 bg-blue-500 text-white rounded disabled:opacity-50"
        >
          {loading ? 'Loading...' : 'Get Elevation'}
        </button>
      </div>
    </div>
  );
}
```

## Contour Data Integration

### Grid-based Contour Generation

```javascript
// utils/contours.js
export async function getContourData(bounds, resolution = 10) {
  try {
    const response = await fetch(`${ELEVATION_CONFIG.BASE_URL}/api/v1/elevation/contour-data`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        area_bounds: {
          polygon_coordinates: bounds.polygon_coordinates
        },
        grid_resolution_m: resolution
      }),
      signal: AbortSignal.timeout(ELEVATION_CONFIG.TIMEOUT)
    });
    
    const data = await response.json();
    
    return {
      gridData: data.grid_data,
      bounds: data.bounds,
      gridSize: data.grid_size,
      resolution: data.resolution_m,
      source: data.source_used,
      success: true
    };
    
  } catch (error) {
    console.error('Contour data request failed:', error);
    return { success: false, error: error.message };
  }
}
```

### Contour Visualization

```javascript
// components/ContourMap.jsx
import React, { useState, useEffect } from 'react';
import { getContourData } from '../utils/contours';

export function ContourMap({ bounds, resolution = 10 }) {
  const [contourData, setContourData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  useEffect(() => {
    if (!bounds) return;
    
    const fetchContours = async () => {
      setLoading(true);
      setError(null);
      
      try {
        const result = await getContourData(bounds, resolution);
        
        if (result.success) {
          setContourData(result);
        } else {
          setError(result.error);
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    
    fetchContours();
  }, [bounds, resolution]);
  
  if (loading) {
    return <div className="flex items-center justify-center p-8">Loading contours...</div>;
  }
  
  if (error) {
    return <div className="text-red-600 p-4">Error: {error}</div>;
  }
  
  return (
    <div className="contour-map">
      {contourData && (
        <div className="mb-4 text-sm text-gray-600">
          Generated {contourData.gridData.length} elevation points 
          using {contourData.source} at {contourData.resolution}m resolution
        </div>
      )}
      
      {/* Integrate with your mapping library (Leaflet, Mapbox, etc.) */}
      <div id="contour-map-container" className="w-full h-96">
        {/* Your map implementation here */}
      </div>
    </div>
  );
}
```

## Error Handling & Fallback Awareness

### Source Status Component

```javascript
// components/ElevationStatus.jsx
import React, { useState, useEffect } from 'react';

export function ElevationStatus() {
  const [status, setStatus] = useState(null);
  
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await fetch(`${ELEVATION_CONFIG.BASE_URL}/api/v1/health`);
        const data = await response.json();
        setStatus(data);
      } catch (error) {
        console.error('Failed to fetch service status:', error);
      }
    };
    
    fetchStatus();
    const interval = setInterval(fetchStatus, 60000); // Update every minute
    
    return () => clearInterval(interval);
  }, []);
  
  if (!status) return null;
  
  return (
    <div className="bg-gray-50 p-3 rounded text-sm">
      <h4 className="font-semibold mb-2">Elevation Service Status</h4>
      
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${
            status.fallback_chain?.s3_sources === 'available' ? 'bg-green-500' : 'bg-red-500'
          }`}></span>
          <span>S3 Sources: {status.fallback_chain?.s3_sources || 'unknown'}</span>
        </div>
        
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${
            status.fallback_chain?.gpxz_api === 'available' ? 'bg-green-500' : 'bg-red-500'
          }`}></span>
          <span>GPXZ API: {status.fallback_chain?.gpxz_api || 'unknown'}</span>
          {status.rate_limits?.gpxz_requests_remaining && (
            <span className="text-gray-500">
              ({status.rate_limits.gpxz_requests_remaining} remaining)
            </span>
          )}
        </div>
        
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${
            status.fallback_chain?.google_api === 'available' ? 'bg-green-500' : 'bg-red-500'
          }`}></span>
          <span>Google API: {status.fallback_chain?.google_api || 'unknown'}</span>
          {status.rate_limits?.google_requests_remaining && (
            <span className="text-gray-500">
              ({status.rate_limits.google_requests_remaining} remaining)
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
```

### Graceful Degradation

```javascript
// utils/elevationWithFallback.js
export async function getElevationWithFallback(latitude, longitude) {
  try {
    // Try DEM backend first
    const result = await getElevation(latitude, longitude);
    
    if (result.success) {
      return {
        elevation: result.elevation,
        source: result.source,
        method: 'dem_backend'
      };
    }
    
    // If DEM backend fails entirely, could implement local fallback
    // For now, return the error from DEM backend
    return {
      elevation: null,
      source: 'none',
      method: 'failed',
      error: result.message
    };
    
  } catch (error) {
    console.error('All elevation methods failed:', error);
    return {
      elevation: null,
      source: 'none',
      method: 'failed',
      error: error.message
    };
  }
}
```

## Performance Optimization

### Request Batching

```javascript
// utils/elevationBatcher.js
class ElevationBatcher {
  constructor() {
    this.queue = [];
    this.batchSize = 50;
    this.batchDelay = 100; // ms
    this.timeout = null;
  }
  
  async addRequest(latitude, longitude) {
    return new Promise((resolve) => {
      this.queue.push({ latitude, longitude, resolve });
      
      if (this.queue.length >= this.batchSize) {
        this.processBatch();
      } else {
        this.scheduleProcessing();
      }
    });
  }
  
  scheduleProcessing() {
    if (this.timeout) return;
    
    this.timeout = setTimeout(() => {
      this.processBatch();
    }, this.batchDelay);
  }
  
  async processBatch() {
    if (this.timeout) {
      clearTimeout(this.timeout);
      this.timeout = null;
    }
    
    if (this.queue.length === 0) return;
    
    const batch = this.queue.splice(0, this.batchSize);
    const points = batch.map(item => ({
      latitude: item.latitude,
      longitude: item.longitude
    }));
    
    try {
      const results = await getBatchElevation(points);
      
      batch.forEach((item, index) => {
        const result = results[index];
        item.resolve(result);
      });
    } catch (error) {
      batch.forEach(item => {
        item.resolve({ elevation: null, success: false, error: error.message });
      });
    }
  }
}

export const elevationBatcher = new ElevationBatcher();
```

## Testing Integration

### Service Testing

```javascript
// tests/elevation.test.js
import { getElevation, getBatchElevation } from '../utils/elevation';

describe('Elevation Service', () => {
  test('should get elevation for valid coordinates', async () => {
    const result = await getElevation(-27.4698, 153.0251);
    
    expect(result.success).toBe(true);
    expect(result.elevation).toBeNumber();
    expect(['s3_sources', 'gpxz_api', 'google_api']).toContain(result.source);
  });
  
  test('should handle batch requests', async () => {
    const points = [
      { latitude: -27.4698, longitude: 153.0251 },
      { latitude: -27.4705, longitude: 153.0258 }
    ];
    
    const results = await getBatchElevation(points);
    
    expect(results).toHaveLength(2);
    expect(results[0].success).toBe(true);
    expect(results[1].success).toBe(true);
  });
  
  test('should handle service failures gracefully', async () => {
    // Mock service failure
    jest.spyOn(global, 'fetch').mockRejectedValue(new Error('Service unavailable'));
    
    const result = await getElevation(-27.4698, 153.0251);
    
    expect(result.success).toBe(false);
    expect(result.error).toBeDefined();
  });
});
```

## Production Considerations

### Environment Configuration

```javascript
// config/production.js
export const PRODUCTION_CONFIG = {
  BASE_URL: 'https://dem-api.road.engineering',
  
  // Rate limiting for production
  RATE_LIMITS: {
    GPXZ_DAILY: 10000, // Upgraded subscription
    GOOGLE_DAILY: 25000, // Paid tier
    REQUESTS_PER_MINUTE: 100
  },
  
  // Error tracking
  ERROR_REPORTING: {
    ENABLED: true,
    ENDPOINT: '/api/errors',
    SAMPLE_RATE: 0.1
  },
  
  // Performance monitoring
  PERFORMANCE: {
    TRACK_FALLBACK_USAGE: true,
    TRACK_RESPONSE_TIMES: true,
    ALERT_ON_FALLBACK_OVERUSE: true
  }
};
```

### Monitoring Integration

```javascript
// utils/monitoring.js
export function trackElevationRequest(source, responseTime, success) {
  if (PRODUCTION_CONFIG.PERFORMANCE.TRACK_FALLBACK_USAGE) {
    // Track which fallback sources are being used
    analytics.track('elevation_request', {
      source,
      responseTime,
      success,
      timestamp: new Date().toISOString()
    });
    
    // Alert if too many fallback requests
    if (source === 'google_api' && PRODUCTION_CONFIG.PERFORMANCE.ALERT_ON_FALLBACK_OVERUSE) {
      console.warn('Using Google API fallback - check S3 and GPXZ status');
    }
  }
}
```

This integration guide provides a complete frontend implementation for the S3 → GPXZ → Google fallback chain, ensuring reliable elevation data access with proper error handling and performance optimization.