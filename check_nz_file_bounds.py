"""
Check NZ file bounds to understand the mismatch
"""
import json
import boto3
import os

# Auckland coordinate
lat, lon = -36.8485, 174.7633

# Load the NZ index from S3 with credentials
os.environ['AWS_ACCESS_KEY_ID'] = 'AKIA5SIDYET7N3U4JQ5H'
os.environ['AWS_SECRET_ACCESS_KEY'] = '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'
s3 = boto3.client('s3', region_name='ap-southeast-2')

response = s3.get_object(
    Bucket='road-engineering-elevation-data',
    Key='indexes/unified_spatial_index_v2_ideal.json'
)
index_data = json.loads(response['Body'].read())

# Find an Auckland collection
for collection in index_data['data_collections']:
    if collection.get('collection_type') == 'new_zealand_campaign' and 'auckland' in collection.get('region', '').lower():
        if 'auckland-north_2016-2018_dem' in collection.get('survey_name', ''):
            print(f"Collection: {collection['survey_name']}")
            print(f"Collection bounds: lat [{collection['coverage_bounds']['min_lat']:.2f}, {collection['coverage_bounds']['max_lat']:.2f}], "
                  f"lon [{collection['coverage_bounds']['min_lon']:.2f}, {collection['coverage_bounds']['max_lon']:.2f}]")
            print(f"Auckland ({lat}, {lon}) is in collection bounds: ✅")
            
            print(f"\nChecking first 10 files:")
            for i, file_entry in enumerate(collection['files'][:10]):
                file_bounds = file_entry['bounds']
                print(f"\nFile {i+1}: {file_entry['filename']}")
                print(f"  Bounds: lat [{file_bounds['min_lat']:.6f}, {file_bounds['max_lat']:.6f}], "
                      f"lon [{file_bounds['min_lon']:.6f}, {file_bounds['max_lon']:.6f}]")
                
                # Check if Auckland is in these bounds
                in_bounds = (file_bounds['min_lat'] <= lat <= file_bounds['max_lat'] and
                           file_bounds['min_lon'] <= lon <= file_bounds['max_lon'])
                print(f"  Auckland in bounds: {'✅' if in_bounds else '❌'}")
                
                # Check for suspicious bounds patterns
                if file_bounds['min_lat'] > 0 or file_bounds['max_lat'] > 0:
                    print(f"  ⚠️ WARNING: Positive latitude values! Likely UTM coordinates mistaken for WGS84!")
                if abs(file_bounds['min_lon']) > 180 or abs(file_bounds['max_lon']) > 180:
                    print(f"  ⚠️ WARNING: Longitude > 180! Likely UTM coordinates mistaken for WGS84!")
                    
            break