# Code Review Files for Gemini Analysis

## Key Issue Confirmed: Single S3 Client for Both Buckets

Looking at `unified_index_loader.py`, the exact issue Gemini predicted is confirmed:

### 1. UnifiedIndexLoader._get_s3_client() (lines 62-98)
```python
def _get_s3_client(self):
    """Lazy load S3 client with enhanced credential handling"""
    if not self.s3_client:
        # ... credential validation ...
        self.s3_client = boto3.client('s3', config=config)  # SINGLE CREDENTIALED CLIENT
        return self.s3_client
```

**Problem**: Single credentialed `boto3.client('s3')` used for ALL buckets.

### 2. _load_from_s3() uses hardcoded bucket (line 165)
```python
response = s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
```

**Issue**: `self.bucket_name` defaults to `"road-engineering-elevation-data"` (line 29).
**Result**: ALL index loading attempts use the private AU bucket name, not the NZ bucket!

### 3. Configuration Issue (lines 28-29)
```python
def __init__(self, bucket_name: str = None, environment: str = None):
    self.bucket_name = bucket_name or os.getenv("S3_INDEX_BUCKET", "road-engineering-elevation-data")
```

**Problem**: The loader assumes a SINGLE bucket for ALL indexes. But we need:
- AU indexes: `road-engineering-elevation-data` (private, needs credentials)  
- NZ indexes: `nz-elevation` (public, needs unsigned access)

### 4. Error Handling (lines 173-182)
```python
except ClientError as e:
    error_code = e.response['Error']['Code']
    if error_code == 'NoSuchKey':
        raise FileNotFoundError(f"S3 index not found: {self.bucket_name}/{s3_key}")
    else:
        raise RuntimeError(f"S3 error loading {s3_key}: {error_code} - {e.response['Error']['Message']}")
```

**Issue**: AccessDenied errors are caught and re-raised as RuntimeError, but the calling code likely catches this broadly.

## Root Cause Confirmed

1. **Wrong Bucket**: NZ index loading tries to access `road-engineering-elevation-data/indexes/nz_spatial_index.json` instead of `nz-elevation/indexes/nz_spatial_index.json`

2. **Wrong Client**: Even if bucket was correct, credentialed client would fail on public bucket without explicit IAM permissions

3. **Silent Failure**: The EnhancedSourceSelector catches exceptions during initialization and continues

This explains everything:
- ✅ AU indexes load (correct private bucket + credentials)
- ❌ NZ indexes fail (wrong bucket + wrong client type)  
- 🔇 Failure is silent (broad exception handling during startup)

## Solution Required

The UnifiedIndexLoader needs:
1. **Multi-bucket support**: Map index names to specific buckets
2. **Bucket-aware S3 clients**: Credentialed for private, unsigned for public
3. **Better error handling**: Critical startup failures should be visible

Example fix structure:
```python
BUCKET_CONFIG = {
    "au": {"bucket": "road-engineering-elevation-data", "access": "private"},
    "nz": {"bucket": "nz-elevation", "access": "public"}
}

def _get_s3_client(self, access_type: str):
    if access_type == "public":
        return boto3.client('s3', config=Config(signature_version=UNSIGNED))
    else:
        return boto3.client('s3', config=config)  # credentialed
```