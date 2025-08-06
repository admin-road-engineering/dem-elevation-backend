# Root Cause Hypothesis: NZ File Bounds Structure Mismatch

## Hypothesis
**The NZ file bounds in the unified index are NOT stored with WGS84 keys (min_lat, max_lat, min_lon, max_lon) but likely use different key names or structure, causing the bounds checking logic to fail.**

## Evidence Supporting This Hypothesis

1. **Collections ARE found**: 25 NZ collections pass bounds check (collection-level bounds work)
2. **Files are NOT found**: 0 files found in those collections (file-level bounds fail)
3. **Known working file**: BA32_10000_0401.tiff with bounds lat[-36.8783, -36.8126] lon[174.7489, 174.8043] contains Auckland
4. **Code checks specific keys**: The find_files_for_coordinate method checks:
   - Attribute access: `hasattr(bounds, 'min_lat')` 
   - Dict access: `'min_lat' in bounds`
5. **Gemini analysis confirms**: File bounds might use different keys like min_x/max_x/min_y/max_y or other structure

## Most Likely Scenarios

### Scenario 1: Wrong Key Names
NZ file bounds use geographic keys but with different names:
- `min_x`/`max_x` instead of `min_lon`/`max_lon`
- `min_y`/`max_y` instead of `min_lat`/`max_lat`

### Scenario 2: Nested Structure
NZ file bounds might be nested differently:
- `bounds.wgs84.min_lat` instead of `bounds.min_lat`
- `bounds.geographic.min_lat` instead of direct access

### Scenario 3: String vs Float Type Issue
The bounds values might be strings instead of floats, causing comparison failures

## Test to Confirm
The debug logging added will reveal:
- `Bounds type: {type(bounds)}`
- `Has min_lat attr: {hasattr(bounds, 'min_lat')}`
- `Bounds keys: {list(bounds.keys())}`

When this logs for an NZ collection, we'll see exactly what structure the bounds have.