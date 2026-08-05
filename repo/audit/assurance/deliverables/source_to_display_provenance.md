# Source-to-Display Provenance

## Data Flow
```
data/processed/ad_manifest.jsonl (5738 records, sha256=609f0a5f)
  → scripts/run_full_data_pipeline.py
    → reports/adintel/full_data_results.json (run_id=full-data-1785938320)
      → scripts/generate_adintel_dashboard.py
        → reports/adintel/adintel_dashboard.html
          → docs/reports/adintel/adintel_dashboard.html (GitHub Pages copy)
            → https://pillb.github.io/manipsych-adintel/reports/adintel/adintel_dashboard.html
```

## Provenance Chain
| Stage | Input | Output | Hash/ID |
|-------|-------|--------|---------|
| Source | ad_manifest.jsonl | 5738 records | sha256=609f0a5f |
| Pipeline | manifest + council | full_data_results.json | run_id=full-data-1785938320 |
| Dashboard | full_data_results.json | adintel_dashboard.html | contains run_id |
| Deployed | dashboard HTML | GitHub Pages | curl confirms 5738 + run_id |

## Verification
- Local file contains "5738": YES
- Deployed file contains "5738": YES (verified via curl)
- Local file contains "Technique-Level": YES
- Deployed file contains "Technique-Level": YES
- Local file contains "PARTIALLY_ALIGNED": YES
- Deployed file contains "PARTIALLY_ALIGNED": YES

Generated: 2026-08-05T21:20:37.331001+00:00
