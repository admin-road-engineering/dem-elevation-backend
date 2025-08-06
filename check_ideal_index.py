#!/usr/bin/env python3
"""Check the ideal index that Railway is using"""

import json
import boto3

s3 = boto3.client('s3',
    aws_access_key_id='AKIA5SIDYET7N3U4JQ5H',
    aws_secret_access_key='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',
    region_name='ap-southeast-2'
)

# Check the IDEAL index that Railway is using
response = s3.get_object(Bucket='road-engineering-elevation-data', Key='indexes/unified_spatial_index_v2_ideal.json')
data = json.loads(response['Body'].read())

# Check NZ collections in the ideal index
nz_colls = [c for c in data['data_collections'] if c.get('country') == 'NZ']
print(f'Total NZ collections in IDEAL index: {len(nz_colls)}')

if nz_colls:
    # Check first NZ collection
    c = nz_colls[0]
    print(f'\nFirst NZ collection:')
    print(f'  id: {c["id"][:8]}...')
    print(f'  collection_type: {c.get("collection_type")}')
    print(f'  country: {c.get("country")}')
    
    # Check if any are mistyped
    wrong_type = [c for c in nz_colls if c.get('collection_type') != 'new_zealand_campaign']
    print(f'\nNZ collections with wrong type: {len(wrong_type)}')
    
    if wrong_type:
        print('Examples of wrong ones:')
        for w in wrong_type[:3]:
            print(f'  id: {w["id"][:8]}... type: {w.get("collection_type")}')