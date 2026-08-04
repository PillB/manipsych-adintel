# Dataset Manifest

## Current Dataset Status

- Raw archive path: `data/raw/ads/`
- Processed manifest: `data/processed/ad_manifest.jsonl`
- Raw HTML files scanned in latest rebuild: 2,372
- Current processed record count: 1,589 strict-valid records
- Current platform mix: 1,364 Locanto Peru records, 199 Doplim Peru records, and 26 Facebook public records
- Uniqueness: 1,589 unique `record_id` values and 1,589 unique `raw_archive_ref` values
- Rebuild summary: `reports/raw_rebuild_summary.json`
- Completion mode: sufficient for the current baseline modeling pass; still below the original 10,000-record ambition
- Exhaustion evidence: `reports/phase4_exhaustion.md`

## Data Handling Rules

- Raw public pages stay local under `data/raw/`.
- Raw data is excluded from git by `.gitignore`.
- Processed records store hashes for source identifiers and canonical URLs.
- Processed records redact phone numbers, emails, WhatsApp labels, and direct contact details.
- Login-gated, private group, CAPTCHA-protected, or access-restricted sources are excluded.
- Facebook processed metadata stores aggregate counts only; profile names and profile URLs are not stored in the manifest.

## Required Record Shape

Each JSONL record includes:

- `record_id`
- `source_platform`
- `source_url_hash`
- `collected_at`
- `title`
- `body_redacted`
- `raw_archive_ref`
- `metadata`

## Context Metadata

The latest rebuild adds aggregate non-PII metadata where recoverable:

- `platform_family`
- `quality_score`
- `is_paid_or_premium_marker`
- `is_featured_marker`
- `followers_count`
- `image_count`
- `facebook_reactions_approx`
- `facebook_comments_approx`
- `facebook_group_present`

## Validation

Run:

```bash
python3 tools/phase_gate.py --phase 4
```

The rebuilt manifest passes required-field, deduplication, source-metadata, raw-coherence, interstitial-rejection, UI-boilerplate, and PII-redaction checks.
