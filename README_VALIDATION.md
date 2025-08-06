# Service Validation

## Quick Validation

**Before any deployment**, run this validation script:

```bash
python validate_service.py
```

**Expected output**:
```
🎉 ALL TESTS PASSED (3/3)
✅ Service is operational and ready for production
```

## Critical Endpoints

These endpoints **MUST** work for the service to be considered operational:

### Auckland, New Zealand
```bash
curl -s "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation?lat=-36.8485&lon=174.7633"
```
**Expected**: `elevation_m: 25.0` (±1.0m acceptable)

### Brisbane, Australia  
```bash
curl -s "https://re-dem-elevation-backend.up.railway.app/api/v1/elevation?lat=-27.4698&lon=153.0251"
```
**Expected**: `elevation_m: 10.87` (±1.0m acceptable)

### Health Check
```bash
curl -s "https://re-dem-elevation-backend.up.railway.app/api/v1/health"
```
**Expected**: `collection_count: 1582`, `provider_type: "unified"`

## Troubleshooting

If any tests fail, see [docs/CRITICAL_TROUBLESHOOTING.md](docs/CRITICAL_TROUBLESHOOTING.md) for systematic debugging.