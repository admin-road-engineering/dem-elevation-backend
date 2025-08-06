# Auckland Elevation Bug Reproduction

## Bug Description
- **Expected behavior**: Auckland coordinate (-36.8485, 174.7633) should return ~25m elevation
- **Actual behavior**: Returns null with message "No elevation found in available files"
- **Brisbane status**: WORKING - returns 10.872m elevation correctly

## Reproduction Steps
1. Deploy service with ENABLE_NZ_SOURCES=true
2. Call API: GET /api/v1/elevation?lat=-36.8485&lon=174.7633
3. Observe null elevation despite 17 files existing with correct bounds

## Environment
- Railway production deployment
- Unified architecture with 1,582 collections (1,394 AU + 188 NZ)
- NZ data from public S3 bucket (nz-elevation)

## Current Evidence
From production logs:
- ✅ 25 NZ collections pass bounds check for Auckland
- ❌ 0 files found in those collections for the coordinate
- Known file BA32_10000_0401.tiff contains Auckland with bounds:
  - lat: [-36.8783, -36.8126]
  - lon: [174.7489, 174.8043]
  - Auckland (-36.8485, 174.7633) IS within these bounds