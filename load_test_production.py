#!/usr/bin/env python3
"""
Production Load Testing for DEM Elevation Service
Tests SQLite R*Tree performance under concurrent load
"""

import asyncio
import httpx
import time
import random
from statistics import mean, median, stdev
from typing import List, Tuple
import json
import os
from datetime import datetime

# Configuration
PRODUCTION_URL = "https://re-dem-elevation-backend.up.railway.app"
API_KEY = os.environ.get("DEM_API_KEY", "test-api-key-2024")

# Test coordinates - mix of known cities and random points
TEST_CITIES = [
    (-27.4698, 153.0251, "Brisbane"),
    (-36.8485, 174.7633, "Auckland"),
    (-33.8688, 151.2093, "Sydney"),
    (-37.8136, 144.9631, "Melbourne"),
    (-31.9505, 115.8605, "Perth"),
    (-41.2865, 174.7762, "Wellington"),
    (-43.5321, 172.6362, "Christchurch"),
    (-34.9285, 138.6007, "Adelaide"),
]

# Bounding box for Australia/NZ region
LAT_RANGE = (-47, -10)
LON_RANGE = (113, 178)


async def test_endpoint(
    client: httpx.AsyncClient, lat: float, lon: float, location: str = None
) -> dict:
    """Test a single elevation endpoint"""
    start = time.time()
    
    try:
        response = await client.get(
            f"/api/v1/elevation",
            params={"lat": lat, "lon": lon},
            headers={"X-API-Key": API_KEY}
        )
        elapsed_ms = (time.time() - start) * 1000
        
        if response.status_code == 200:
            data = response.json()
            return {
                "success": True,
                "location": location or f"({lat:.4f}, {lon:.4f})",
                "lat": lat,
                "lon": lon,
                "elapsed_ms": elapsed_ms,
                "elevation": data.get("elevation"),
                "source": data.get("dem_source_used"),
                "status_code": response.status_code
            }
        else:
            return {
                "success": False,
                "location": location or f"({lat:.4f}, {lon:.4f})",
                "lat": lat,
                "lon": lon,
                "elapsed_ms": elapsed_ms,
                "status_code": response.status_code,
                "error": response.text[:200]
            }
    except Exception as e:
        return {
            "success": False,
            "location": location or f"({lat:.4f}, {lon:.4f})",
            "lat": lat,
            "lon": lon,
            "elapsed_ms": (time.time() - start) * 1000,
            "error": str(e)
        }


async def warmup_test(client: httpx.AsyncClient):
    """Warmup requests to ensure service is ready"""
    print("\n🔥 Warming up service...")
    
    warmup_tasks = []
    for lat, lon, city in TEST_CITIES[:4]:
        warmup_tasks.append(test_endpoint(client, lat, lon, city))
    
    results = await asyncio.gather(*warmup_tasks)
    
    for result in results:
        if result["success"]:
            print(f"  ✅ {result['location']}: {result['elapsed_ms']:.1f}ms")
        else:
            print(f"  ❌ {result['location']}: Failed")


async def sequential_test(client: httpx.AsyncClient):
    """Test sequential requests to measure baseline performance"""
    print("\n📊 Sequential Performance Test...")
    
    results = []
    for lat, lon, city in TEST_CITIES:
        result = await test_endpoint(client, lat, lon, city)
        results.append(result)
        if result["success"]:
            print(f"  {city}: {result['elapsed_ms']:.1f}ms - {result['elevation']:.1f}m ({result['source']})")
        else:
            print(f"  {city}: FAILED - {result.get('error', 'Unknown error')}")
    
    successful = [r for r in results if r["success"]]
    if successful:
        times = [r["elapsed_ms"] for r in successful]
        print(f"\n  Average: {mean(times):.1f}ms")
        print(f"  Median: {median(times):.1f}ms")
        print(f"  Min: {min(times):.1f}ms")
        print(f"  Max: {max(times):.1f}ms")


async def concurrent_test(client: httpx.AsyncClient, num_requests: int = 100):
    """Test concurrent requests to measure performance under load"""
    print(f"\n🚀 Concurrent Load Test ({num_requests} requests)...")
    
    tasks = []
    
    # Mix of known cities and random coordinates
    for i in range(num_requests):
        if i % 4 == 0:  # 25% known cities
            lat, lon, city = random.choice(TEST_CITIES)
            tasks.append(test_endpoint(client, lat, lon, city))
        else:  # 75% random coordinates
            lat = random.uniform(*LAT_RANGE)
            lon = random.uniform(*LON_RANGE)
            tasks.append(test_endpoint(client, lat, lon))
    
    start_time = time.time()
    results = await asyncio.gather(*tasks)
    total_time = time.time() - start_time
    
    # Analyze results
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    
    if successful:
        times = [r["elapsed_ms"] for r in successful]
        times_sorted = sorted(times)
        
        p50 = times_sorted[int(len(times_sorted) * 0.50)]
        p95 = times_sorted[int(len(times_sorted) * 0.95)]
        p99 = times_sorted[int(len(times_sorted) * 0.99)]
        
        print(f"\n  ✅ Success Rate: {len(successful)}/{num_requests} ({len(successful)*100/num_requests:.1f}%)")
        print(f"  ⏱️  Total Time: {total_time:.2f}s")
        print(f"  📈 Throughput: {num_requests/total_time:.1f} req/s")
        print(f"\n  Response Times:")
        print(f"    Average: {mean(times):.1f}ms")
        print(f"    Median (P50): {p50:.1f}ms")
        print(f"    P95: {p95:.1f}ms")
        print(f"    P99: {p99:.1f}ms")
        print(f"    Min: {min(times):.1f}ms")
        print(f"    Max: {max(times):.1f}ms")
        
        if times:
            print(f"    StdDev: {stdev(times):.1f}ms")
        
        # Source analysis
        sources = {}
        for r in successful:
            source = r.get("source", "unknown")
            sources[source] = sources.get(source, 0) + 1
        
        print(f"\n  Data Sources Used:")
        for source, count in sorted(sources.items(), key=lambda x: x[1], reverse=True):
            print(f"    {source}: {count} ({count*100/len(successful):.1f}%)")
    
    if failed:
        print(f"\n  ❌ Failed Requests: {len(failed)}")
        error_types = {}
        for r in failed:
            error = r.get("error", "Unknown")[:50]
            error_types[error] = error_types.get(error, 0) + 1
        for error, count in list(error_types.items())[:5]:
            print(f"    {error}: {count}")


async def stress_test(client: httpx.AsyncClient, duration_seconds: int = 30):
    """Continuous stress test for a specified duration"""
    print(f"\n💪 Stress Test ({duration_seconds}s duration)...")
    
    start_time = time.time()
    end_time = start_time + duration_seconds
    
    all_results = []
    batch_size = 50
    batch_num = 0
    
    while time.time() < end_time:
        batch_num += 1
        tasks = []
        
        for _ in range(batch_size):
            if random.random() < 0.3:  # 30% known cities
                lat, lon, city = random.choice(TEST_CITIES)
                tasks.append(test_endpoint(client, lat, lon, city))
            else:  # 70% random
                lat = random.uniform(*LAT_RANGE)
                lon = random.uniform(*LON_RANGE)
                tasks.append(test_endpoint(client, lat, lon))
        
        batch_results = await asyncio.gather(*tasks)
        all_results.extend(batch_results)
        
        # Progress update
        elapsed = time.time() - start_time
        successful_batch = sum(1 for r in batch_results if r["success"])
        print(f"  Batch {batch_num}: {successful_batch}/{batch_size} successful ({elapsed:.1f}s elapsed)")
    
    # Final analysis
    total_time = time.time() - start_time
    successful = [r for r in all_results if r["success"]]
    
    if successful:
        times = [r["elapsed_ms"] for r in successful]
        times_sorted = sorted(times)
        
        p50 = times_sorted[int(len(times_sorted) * 0.50)]
        p95 = times_sorted[int(len(times_sorted) * 0.95)]
        p99 = times_sorted[int(len(times_sorted) * 0.99)]
        
        print(f"\n  📊 Stress Test Results:")
        print(f"    Total Requests: {len(all_results)}")
        print(f"    Successful: {len(successful)} ({len(successful)*100/len(all_results):.1f}%)")
        print(f"    Duration: {total_time:.1f}s")
        print(f"    Throughput: {len(all_results)/total_time:.1f} req/s")
        print(f"\n    Response Times under stress:")
        print(f"      P50: {p50:.1f}ms")
        print(f"      P95: {p95:.1f}ms")
        print(f"      P99: {p99:.1f}ms")


async def main():
    """Main test runner"""
    print("=" * 60)
    print("DEM Elevation Service - Production Load Test")
    print(f"Target: {PRODUCTION_URL}")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)
    
    # Create HTTP client with appropriate timeout
    async with httpx.AsyncClient(
        base_url=PRODUCTION_URL,
        timeout=httpx.Timeout(30.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
    ) as client:
        
        # 1. Warmup
        await warmup_test(client)
        
        # 2. Sequential baseline
        await sequential_test(client)
        
        # 3. Concurrent load test
        await concurrent_test(client, num_requests=100)
        
        # 4. Higher concurrent load
        await concurrent_test(client, num_requests=500)
        
        # 5. Stress test
        # await stress_test(client, duration_seconds=30)
        
    print("\n" + "=" * 60)
    print("✅ Load Test Complete")
    print("=" * 60)


if __name__ == "__main__":
    # Check for API key
    if not API_KEY:
        print("⚠️  Warning: No DEM_API_KEY environment variable set")
        print("   Using default test key which may have limited access")
    
    # Run the tests
    asyncio.run(main())