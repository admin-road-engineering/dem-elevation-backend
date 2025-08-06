"""
Check what type of bounds NZ files have in the index
"""
import json
import boto3
import os

# Load the NZ index from S3 with credentials
os.environ['AWS_ACCESS_KEY_ID'] = 'AKIA5SIDYET7N3U4JQ5H'
os.environ['AWS_SECRET_ACCESS_KEY'] = '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'
s3 = boto3.client('s3', region_name='ap-southeast-2')

response = s3.get_object(
    Bucket='road-engineering-elevation-data',
    Key='indexes/unified_spatial_index_v2_ideal.json'
)
index_data = json.loads(response['Body'].read())

# Check a specific Auckland collection
for collection in index_data['data_collections']:
    if collection.get('survey_name') == 'auckland-north_2016-2018_dem_1m':
        print(f"Collection: {collection['survey_name']}")
        print(f"Collection type: {collection.get('collection_type')}")
        
        # Check the file that contains Auckland
        for file_entry in collection['files']:
            if file_entry['filename'] == 'BA32_10000_0401.tiff':
                print(f"\nFile: {file_entry['filename']}")
                print(f"Bounds structure: {file_entry['bounds']}")
                
                bounds = file_entry['bounds']
                print(f"\nBounds keys: {list(bounds.keys())}")
                
                # Check if it has WGS84 keys
                has_wgs84 = all(k in bounds for k in ['min_lat', 'max_lat', 'min_lon', 'max_lon'])
                has_utm = all(k in bounds for k in ['min_x', 'max_x', 'min_y', 'max_y'])
                
                print(f"Has WGS84 keys (min_lat, max_lat, min_lon, max_lon): {has_wgs84}")
                print(f"Has UTM keys (min_x, max_x, min_y, max_y): {has_utm}")
                
                if has_wgs84:
                    print(f"\n✅ File has WGS84 bounds as expected")
                    print(f"  lat: [{bounds['min_lat']:.4f}, {bounds['max_lat']:.4f}]")
                    print(f"  lon: [{bounds['min_lon']:.4f}, {bounds['max_lon']:.4f}]")
                    
                    # Check if Auckland is in bounds
                    lat, lon = -36.8485, 174.7633
                    in_bounds = (bounds['min_lat'] <= lat <= bounds['max_lat'] and
                               bounds['min_lon'] <= lon <= bounds['max_lon'])
                    print(f"\n  Auckland ({lat}, {lon}) in bounds: {'✅' if in_bounds else '❌'}")
                
                break
        break