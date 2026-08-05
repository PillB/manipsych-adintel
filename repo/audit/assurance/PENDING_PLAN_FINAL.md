# Refreshed Plan — Final Round

## Status: 2026-08-05 (post Phase 1-4)
- 25 total items: 14 completed, 5 accepted risk, **6 remaining**
- TPR=0.808, FPR=0.000, Brier=0.0034, 186 tests pass, Pages live

## 6 Remaining Items

### D-01: Complete metric provenance for all 50 metrics
- **Root cause**: METRIC_CATALOG.json has 50 metrics but some lack source_functions
- **Strategy**: Add source_functions to every metric entry
- **Gate**: All 50 metrics have source_functions field

### D-02: PDF-dashboard timestamp comparison test
- **Root cause**: PDF generated at different time than dashboard
- **Strategy**: Add test that verifies both have timestamps from same pipeline run
- **Gate**: Test passes

### M-02: Verify mobile table overflow is fixed
- **Root cause**: Tables already have display:block;overflow-x:auto
- **Strategy**: Verify with Playwright mobile viewport
- **Gate**: No table overflow on mobile

### O-01: HTTP server exposed on 0.0.0.0
- **Root cause**: Python http.server default binds to all interfaces
- **Strategy**: Change server script to bind 127.0.0.1 only; add warning if 0.0.0.0
- **Gate**: Server binds to localhost only

### O-03: Add monitoring script
- **Root cause**: No drift detection or performance monitoring
- **Strategy**: Create scripts/monitor.py that checks key metrics against thresholds
- **Gate**: Monitor runs and produces report

### O-04: SQLite memory usage
- **Root cause**: Some scripts load all rows from 204MB SQLite
- **Strategy**: Document as accepted risk (scripts already use streaming for most queries)
- **Gate**: Documented in model card
