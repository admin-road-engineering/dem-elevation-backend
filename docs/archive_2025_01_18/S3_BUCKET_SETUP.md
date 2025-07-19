# S3 Bucket Setup for Higher Resolution DEM Data

## Requirements from Elevation Team

### Step 1: Create S3 Bucket
1. Create a new bucket in your AWS account
2. **Region**: Sydney (`ap-southeast-2`) - **REQUIRED**
3. **Suggested name**: `dem-high-res-data-2024` (or similar)

### Step 2: Configure Bucket Policy
Replace `<your_bucket_name>` with your chosen bucket name:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "DelegateS3Access",
            "Effect": "Allow",
            "Principal": {
                "AWS": "arn:aws:iam::337340849400:user/ELEVATION_BULK_DATA_DISTRIBUTOR"
            },
            "Action": [
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::<your_bucket_name>",
                "arn:aws:s3:::<your_bucket_name>/*"
            ]
        },
        {
            "Sid": "GrantOwnerFullControl",
            "Action": [
                "s3:PutObject",
                "s3:PutObjectAcl"
            ],
            "Effect": "Allow",
            "Resource": "arn:aws:s3:::<your_bucket_name>/*",
            "Condition": {
                "StringEquals": {
                    "s3:x-amz-acl": "bucket-owner-full-control"
                }
            },
            "Principal": {
                "AWS": [
                    "arn:aws:iam::337340849400:user/ELEVATION_BULK_DATA_DISTRIBUTOR"
                ]
            }
        }
    ]
}
```

### Step 3: Notify Elevation Team
Send them your bucket name to add to their user policy.

## Integration with Your Backend

### Recommended Bucket Structure
```
s3://your-high-res-bucket/
├── queensland/
│   ├── 50cm/
│   │   ├── QLD_50cm_DEM_Region1.tif
│   │   ├── QLD_50cm_DEM_Region2.tif
│   │   └── ...
│   └── 1m/
│       ├── QLD_1m_DEM_Region1.tif
│       └── ...
├── tasmania/
│   ├── 50cm/
│   │   ├── TAS_50cm_DEM_Region1.tif
│   │   └── ...
│   └── 1m/
│       └── ...
└── metadata/
    ├── coverage_index.json
    └── source_catalog.json
```

### Backend Configuration
You'll need to update your `.env` file to include both buckets:
- **Existing bucket**: `roadengineer-dem-files` (keep current data)
- **New bucket**: `your-high-res-bucket` (new high-resolution data) 