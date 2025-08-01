# S3 Index Recovery Plan

## Problem Statement

**Issue**: Railway deployments failing to load S3 campaign index due to missing file
**Impact**: Loss of 54,000x Brisbane speedup, degraded to API-only operation
**Priority**: HIGH - Critical performance regression

## Root Cause Analysis

### Primary Issue
- S3 file `indexes/grouped_spatial_index.json` does not exist in bucket `road-engineering-elevation-data`
- SourceProvider correctly implements graceful degradation
- Service starts with API fallback but loses spatial indexing benefits

### Secondary Issues  
- Disconnect between expected index file name and actual S3 bucket contents
- No validation of S3 index existence during deployment pipeline
- Missing operational runbook for S3 index management

## Solution Architecture

### Phase 1: Immediate Fix (2 hours)
**Objective**: Restore S3 index functionality with proper file resolution

#### Task 1.1: S3 Bucket Audit (30 min)
- [ ] List all files in `s3://road-engineering-elevation-data/indexes/`
- [ ] Identify the correct campaign index file name
- [ ] Document current S3 bucket structure

#### Task 1.2: Index File Resolution (45 min)  
- [ ] Update `src/source_provider.py` to use correct index file name
- [ ] OR regenerate missing `grouped_spatial_index.json` if needed
- [ ] Validate index file structure matches expected format

#### Task 1.3: Configuration Update (30 min)
- [ ] Update `src/main.py` lifespan handler with correct index path
- [ ] Ensure Railway environment variables align with actual S3 structure
- [ ] Test configuration changes locally with Docker environment

#### Task 1.4: Deployment Validation (15 min)
- [ ] Deploy to Railway and verify S3 index loads successfully
- [ ] Confirm Brisbane coordinates return 54,000x speedup performance
- [ ] Validate health check passes within timeout

### Phase 2: Operational Resilience (1 hour)
**Objective**: Prevent future S3 index issues with proper validation

#### Task 2.1: S3 Index Validation (30 min)
- [ ] Add S3 index existence check to health check endpoint
- [ ] Create operational script to validate S3 index integrity
- [ ] Document S3 bucket maintenance procedures

#### Task 2.2: Enhanced Error Reporting (30 min)
- [ ] Improve SourceProvider error messages with specific S3 paths
- [ ] Add Railway deployment logs for S3 troubleshooting
- [ ] Create S3 index recovery documentation

### Phase 3: Long-term Prevention (30 min)
**Objective**: Systematic prevention of S3 index issues

#### Task 3.1: Documentation Update
- [ ] Update CLAUDE.md with correct S3 index file names
- [ ] Create S3 bucket structure documentation
- [ ] Add troubleshooting guide for S3 index issues

## Implementation Strategy

### Security Compliance
- ✅ No secrets in code (uses environment variables)
- ✅ Proper error sanitization (internal S3 paths not exposed)
- ✅ Input validation maintained for all configuration

### Quality Standards
- ✅ Changes under 50 lines per file
- ✅ Maintains existing graceful degradation logic
- ✅ Comprehensive logging for troubleshooting
- ✅ No breaking changes to existing API

### Performance Requirements
- ✅ Must restore 54,000x Brisbane speedup
- ✅ Startup time <500ms maintained
- ✅ Health check timeout <240s Railway requirement
- ✅ Memory usage optimization preserved

## Risk Assessment

### High Risk Items
1. **S3 Bucket Access**: Ensure credentials still valid
2. **Index File Format**: Validate structure matches SourceProvider expectations  
3. **Railway Timeout**: Changes must not increase startup time

### Mitigation Strategies
1. **Parallel Development**: Test locally before Railway deployment
2. **Rollback Plan**: Maintain graceful API fallback if S3 issues persist
3. **Monitoring**: Enhanced logging for S3 operations during fix deployment

## Success Criteria

### Functional Requirements
- [ ] Railway deployment completes successfully
- [ ] S3 campaign index loads without errors
- [ ] Brisbane coordinates return ~11.523m elevation with source attribution
- [ ] Health check passes within 240s timeout
- [ ] Service maintains 54,000x performance advantage

### Performance Benchmarks
- [ ] Startup time <500ms (current: target maintained)
- [ ] Brisbane query response <50ms (vs >2000ms API fallback) 
- [ ] Memory usage ~600MB (spatial indexes loaded)
- [ ] 1,153 S3 campaigns available (vs current 0)

### Operational Requirements
- [ ] Clear error messages for S3 troubleshooting
- [ ] Documentation updated with correct procedures
- [ ] Health check includes S3 index status
- [ ] Railway logs provide actionable debugging information

## Timeline

**Total Estimated Time**: 3.5 hours
- Phase 1 (Critical): 2 hours
- Phase 2 (Resilience): 1 hour  
- Phase 3 (Prevention): 30 minutes

**Priority**: Execute Phase 1 immediately, Phases 2-3 can follow after core functionality restored.

This plan follows the development protocol requirements for incremental implementation, comprehensive testing, and proper documentation while addressing the critical S3 index failure.