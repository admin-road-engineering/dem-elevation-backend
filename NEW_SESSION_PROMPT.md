# New Session: DEM Backend Recovery Implementation

## Immediate Context
You are continuing work on a DEM elevation microservice that is in a **recovery phase** due to over-engineering. Both primary coordinates (Brisbane AU and Auckland NZ) worked individually before but are now broken after multiple optimization attempts.

## Critical Background
- **Service**: Railway deployment healthy, 1,582 collections loaded
- **Problem**: Both Brisbane (-27.4698, 153.0251) and Auckland (-36.8485, 174.7633) return null elevations
- **Root Cause**: Over-engineered solutions broke working functionality
- **Lesson Learned**: "Make it work, then make it better" - NOT the other way around

## What Happened
1. **Brisbane (AU)**: Previously returned 10.872m → Now GDAL opens files but `_gdal_array` import fails → rasterio fallback fails with boto3 session errors
2. **Auckland (NZ)**: Previously returned ~25m → Now finds 73 collections but 0 files in each (bounds/CRS issue)

## Your Mission
Implement **Gemini's validated recovery plan** from `IMPLEMENTATION_PLAN.md` with **test-driven approach**:

### Phase 1: Build Integration Test First (Step 2.5)
**CRITICAL**: Before any fixes, create integration test that asserts:
- Brisbane (-27.4698, 153.0251) returns 10-12m elevation in <2s
- Auckland (-36.8485, 174.7633) returns 20-30m elevation in <2s
- Tests will initially FAIL - that's expected and correct

### Phase 2: Minimal Fixes Only
**Step 1**: Fix Brisbane with simplest possible approach:
- Remove complex boto3 session management
- Use basic environment variables for AU private bucket
- Focus on getting GDAL or simple rasterio working

**Step 2**: Fix Auckland file discovery:
- Check if `nz_spatial_index.json` has WGS84 vs UTM bounds mismatch (like AU had)
- Ensure intersection logic works for WGS84 input coordinates

### Phase 3: Test and Stop
Recovery complete when integration tests pass consistently. NO optimizations until then.

## Key Files to Reference
- `IMPLEMENTATION_PLAN.md` - Detailed recovery strategy
- `RECOVERY_PLAN.md` - Original plan validated by Gemini  
- `CLAUDE.md` - Updated with over-engineering lessons
- `Gemini.md` - Crisis learning documentation
- `src/data_sources/unified_s3_source.py` - Main file needing fixes

## What NOT to Do
- ❌ Complex session management patterns
- ❌ Sophisticated error handling  
- ❌ Bucket detection strategies
- ❌ "Architectural improvements"
- ❌ Multiple context managers

## What TO Do  
- ✅ Build integration test first
- ✅ Simple environment variable approach
- ✅ Minimal changes to restore function
- ✅ Test-driven validation
- ✅ Stop when both coordinates work

## Success Criteria
Integration tests pass showing both Brisbane and Auckland return expected elevations in <2s. That's it. Nothing more until that baseline works reliably.

## Starting Command
```bash
# First, create and run the integration test to establish baseline
# Then implement minimal fixes to make tests pass
# Focus on working functionality over elegant architecture
```

Remember: **Technical excellence is working code that solves real problems, not sophisticated patterns that don't work.**