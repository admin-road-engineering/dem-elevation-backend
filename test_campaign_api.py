"""Simple test script for campaign API endpoints."""

import asyncio
import json
import sys
import os
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.services.campaign_service import campaign_service
from src.models.campaign_models import CampaignQuery, CampaignFilters, Bounds, DataType


async def test_campaign_service():
    """Test the campaign service functionality."""
    print("Testing Campaign Service...")
    
    try:
        # Initialize service
        print("1. Initializing campaign service...")
        await campaign_service.initialize()
        
        if not campaign_service._campaigns_list:
            print("[ERROR] No campaigns loaded")
            return False
        
        print(f"[OK] Loaded {len(campaign_service._campaigns_list)} campaigns")
        
        # Test basic query
        print("\n2. Testing basic campaign query...")
        query = CampaignQuery(page=1, page_size=5)
        response = await campaign_service.get_campaigns(query)
        
        print(f"[OK] Retrieved {len(response.campaigns)} campaigns (page 1)")
        print(f"   Total available: {response.total_count}")
        
        # Test campaign by ID
        if response.campaigns:
            print("\n3. Testing campaign by ID...")
            first_campaign = response.campaigns[0]
            campaign_detail = await campaign_service.get_campaign_by_id(
                first_campaign.id, 
                include_geometry=True
            )
            
            if campaign_detail:
                print(f"[OK] Retrieved campaign: {campaign_detail.name}")
                print(f"   ID: {campaign_detail.id}")
                print(f"   Type: {campaign_detail.data_type}")
                print(f"   Resolution: {campaign_detail.resolution_m}m")
                print(f"   Files: {campaign_detail.file_count}")
                if campaign_detail.geometry:
                    print(f"   Geometry: {campaign_detail.geometry.type}")
            else:
                print("[ERROR] Failed to retrieve campaign details")
                return False
        
        # Test spatial query
        print("\n4. Testing spatial bounds query...")
        # Brisbane area bounds
        brisbane_bounds = Bounds(
            min_lat=-27.6,
            max_lat=-27.3,
            min_lon=152.9,
            max_lon=153.3
        )
        
        campaigns_in_bounds = await campaign_service.get_campaigns_in_bounds(brisbane_bounds)
        print(f"[OK] Found {len(campaigns_in_bounds)} campaigns in Brisbane area")
        
        # Test filtering
        print("\n5. Testing data type filtering...")
        filters = CampaignFilters(data_types=[DataType.LIDAR])
        filter_query = CampaignQuery(filters=filters, page=1, page_size=10)
        filtered_response = await campaign_service.get_campaigns(filter_query)
        
        print(f"[OK] Found {filtered_response.total_count} LiDAR campaigns")
        
        # Test clustering
        print("\n6. Testing campaign clustering...")
        australia_bounds = Bounds(
            min_lat=-45.0,
            max_lat=-10.0,
            min_lon=110.0,
            max_lon=155.0
        )
        
        clusters = await campaign_service.get_campaign_clusters(australia_bounds, zoom_level=6)
        print(f"[OK] Generated {len(clusters.clusters)} clusters for zoom level 6")
        print(f"   Total campaigns: {clusters.total_campaigns}")
        
        print("\n[SUCCESS] All campaign service tests passed!")
        return True
        
    except Exception as e:
        print(f"[ERROR] Campaign service test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_data_statistics():
    """Test data statistics and summary information."""
    print("\n" + "="*50)
    print("Campaign Data Statistics")
    print("="*50)
    
    try:
        campaigns = campaign_service._campaigns_list
        if not campaigns:
            print("No campaigns loaded for statistics")
            return
        
        # Basic stats
        total_campaigns = len(campaigns)
        total_files = sum(c.file_count for c in campaigns)
        
        print(f"Total Campaigns: {total_campaigns}")
        print(f"Total Files: {total_files:,}")
        
        # Data type breakdown
        data_types = {}
        for campaign in campaigns:
            dt = campaign.data_type.value
            data_types[dt] = data_types.get(dt, 0) + 1
        
        print(f"\nData Types:")
        for dt, count in sorted(data_types.items()):
            print(f"  {dt}: {count} campaigns")
        
        # Provider breakdown
        providers = {}
        for campaign in campaigns:
            provider = campaign.provider.value
            providers[provider] = providers.get(provider, 0) + 1
        
        print(f"\nProviders:")
        for provider, count in sorted(providers.items()):
            print(f"  {provider}: {count} campaigns")
        
        # Resolution breakdown
        resolutions = {}
        for campaign in campaigns:
            res = f"{campaign.resolution_m}m"
            resolutions[res] = resolutions.get(res, 0) + 1
        
        print(f"\nResolutions:")
        for res, count in sorted(resolutions.items(), key=lambda x: float(x[0][:-1])):
            print(f"  {res}: {count} campaigns")
        
        # Geographic coverage
        if campaigns:
            min_lat = min(c.bounds.min_lat for c in campaigns)
            max_lat = max(c.bounds.max_lat for c in campaigns)
            min_lon = min(c.bounds.min_lon for c in campaigns)
            max_lon = max(c.bounds.max_lon for c in campaigns)
            
            print(f"\nGeographic Coverage:")
            print(f"  Latitude: {min_lat:.2f} to {max_lat:.2f}")
            print(f"  Longitude: {min_lon:.2f} to {max_lon:.2f}")
        
        # Sample campaigns
        print(f"\nSample Campaigns:")
        for i, campaign in enumerate(campaigns[:3]):
            print(f"  {i+1}. {campaign.name}")
            print(f"     Type: {campaign.data_type.value}, Resolution: {campaign.resolution_m}m")
            print(f"     Files: {campaign.file_count}, Region: {campaign.geographic_region}")
        
    except Exception as e:
        print(f"Failed to generate statistics: {e}")


if __name__ == "__main__":
    async def main():
        success = await test_campaign_service()
        
        if success:
            await test_data_statistics()
        
        return success
    
    # Run the test
    result = asyncio.run(main())
    
    if result:
        print("\n[SUCCESS] Campaign API implementation completed successfully!")
        print("\nNext steps:")
        print("1. Start DEM Backend: uvicorn src.main:app --reload --port 8001")
        print("2. Test API endpoints:")
        print("   - GET http://localhost:8001/api/v1/campaigns")
        print("   - GET http://localhost:8001/api/v1/campaigns/health")
        print("   - GET http://localhost:8001/api/v1/campaigns/stats/summary")
    else:
        print("\n[ERROR] Campaign API implementation needs attention")
        sys.exit(1)