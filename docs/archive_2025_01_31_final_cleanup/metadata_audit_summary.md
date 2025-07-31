# DEM Metadata Audit Summary Report

**Generated:** 2025-07-20T18:49:57.262612

## Overview

- **Total Files:** 631,556
- **Total Storage:** 3503.5 GB

## Naming Patterns

- **act_4ppm:** 740 files
- **standard_grid:** 79 files
- **generic_dem:** 544,849 files
- **clarence_grid:** 139 files
- **gosford_lid:** 775 files
- **sydney_lid:** 814 files
- **brisbane_sw:** 4,634 files
- **uncovered:** 79,526 files

## Resolution Distribution

- **1m:** 341,901 files
- **50cm:** 173,385 files
- **unknown:** 116,270 files

## Bounds Accuracy

- **precise:** 4,634 files (0.7%)
- **reasonable:** 4,502 files (0.7%)
- **regional:** 31,806 files (5.0%)
- **excessive:** 590,614 files (93.5%)

## Recommendations

### 1. Bounds Accuracy (HIGH Priority)

**Issue:** 590,614 files have excessive bounds (>5° range)

**Recommendation:** Implement enhanced UTM converter patterns to fix fallback bounds

**Impact:** Reduce Brisbane coverage from 31,809 to ~5906-11812 files

### 2. Pattern Coverage (MEDIUM Priority)

**Issue:** 79,526 files don't match known patterns

**Recommendation:** Add new regex patterns for uncovered filename formats

**Impact:** Improve coordinate extraction accuracy

