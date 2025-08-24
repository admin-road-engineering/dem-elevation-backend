"""
Find files that actually contain Auckland harbor coordinate
"""
import json
import boto3
import os

# Auckland harbor coordinate
lat, lon = -36.8485, 174.7633

# Load the NZ index from S3 with credentials from environment
if not os.environ.get('AWS_ACCESS_KEY_ID'):
    print("⚠️ ERROR: AWS_ACCESS_KEY_ID not set in environment")
    exit(1)
if not os.environ.get('AWS_SECRET_ACCESS_KEY'):
    print("⚠️ ERROR: AWS_SECRET_ACCESS_KEY not set in environment")
    exit(1)
s3 = boto3.client('s3', region_name='ap-southeast-2')

response = s3.get_object(
    Bucket='road-engineering-elevation-data',
    Key='indexes/unified_spatial_index_v2_ideal.json'
)
index_data = json.loads(response['Body'].read())

print(f"Searching for files containing Auckland harbor: ({lat}, {lon})")
print("="*60)

files_found = []
collections_checked = 0

# Check all NZ collections
for collection in index_data['data_collections']:
    if collection.get('collection_type') == 'new_zealand_campaign':
        collections_checked += 1
        
        # Check each file in the collection
        for file_entry in collection['files']:
            file_bounds = file_entry['bounds']
            
            # Check if Auckland harbor is in these bounds
            if (file_bounds['min_lat'] <= lat <= file_bounds['max_lat'] and
                file_bounds['min_lon'] <= lon <= file_bounds['max_lon']):
                
                files_found.append({
                    'collection': collection['survey_name'],
                    'region': collection['region'],
                    'file': file_entry['filename'],
                    'bounds': file_bounds,
                    'path': file_entry['file']
                })

print(f"Collections checked: {collections_checked}")
print(f"Files found containing Auckland harbor: {len(files_found)}")

if files_found:
    print("\n✅ Files containing Auckland harbor:")
    for f in files_found[:5]:  # Show first 5
        print(f"\n  Collection: {f['collection']}")
        print(f"  Region: {f['region']}")
        print(f"  File: {f['file']}")
        print(f"  Bounds: lat [{f['bounds']['min_lat']:.4f}, {f['bounds']['max_lat']:.4f}], "
              f"lon [{f['bounds']['min_lon']:.4f}, {f['bounds']['max_lon']:.4f}]")
        print(f"  Path: {f['path']}")
else:
    print("\n❌ NO FILES FOUND containing Auckland harbor coordinate!")
    print("\nThis explains why Auckland returns null elevation.")
    print("\nPossible issues:")
    print("1. File bounds were not extracted correctly during index generation")
    print("2. Auckland harbor area is missing from the NZ elevation data")
    print("3. The bounds extraction used wrong coordinate system")
    
    # Find closest file to Auckland
    print("\nFinding closest file to Auckland harbor...")
    min_dist = float('inf')
    closest = None
    
    for collection in index_data['data_collections']:
        if collection.get('collection_type') == 'new_zealand_campaign' and 'auckland' in collection.get('region', '').lower():
            for file_entry in collection['files']:
                bounds = file_entry['bounds']
                # Distance to bounds center
                center_lat = (bounds['min_lat'] + bounds['max_lat']) / 2
                center_lon = (bounds['min_lon'] + bounds['max_lon']) / 2
                dist = ((lat - center_lat)**2 + (lon - center_lon)**2)**0.5
                
                if dist < min_dist:
                    min_dist = dist
                    closest = {
                        'collection': collection['survey_name'],
                        'file': file_entry['filename'],
                        'bounds': bounds,
                        'center': (center_lat, center_lon),
                        'distance': dist
                    }
    
    if closest:
        print(f"\nClosest file: {closest['file']}")
        print(f"  Collection: {closest['collection']}")
        print(f"  Bounds: lat [{closest['bounds']['min_lat']:.4f}, {closest['bounds']['max_lat']:.4f}], "
              f"lon [{closest['bounds']['min_lon']:.4f}, {closest['bounds']['max_lon']:.4f}]")
        print(f"  Center: ({closest['center'][0]:.4f}, {closest['center'][1]:.4f})")
        print(f"  Distance from Auckland: {closest['distance']:.4f} degrees")