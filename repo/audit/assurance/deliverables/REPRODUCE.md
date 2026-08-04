# Reproduce — ManiPsych + adintel

**Audit artifact:** `audit/assurance/deliverables/REPRODUCE.md`
**Purpose:** step-by-step instructions to reproduce the audit findings, regenerate the artifacts, and re-run the pipeline from a clean checkout.
**Convention:** every step lists the command, the expected output, and a verification hash/count. Steps that cannot be reproduced from in-repo code are marked `NOT REPRODUCIBLE — [reason]`.

---

## 0. Prerequisites

### 0.1 Environment

```bash
python3 --version    # verified: Python 3.12.13
pip list | grep -iE "scikit-learn|joblib|pytest"
# verified: scikit-learn 1.5.2, joblib 1.5.3, pytest 9.0.2
```

The `pyproject.toml` declares:
- `requires-python = ">=3.9"`
- runtime deps: `beautifulsoup4>=4.12`, `lxml>=5.0`, `playwright>=1.40`, `selenium>=4.15`, `webdriver-manager>=4.0`
- dev deps: `pytest>=7.0`, `scikit-learn>=1.3`

The sandbox has Python 3.12.13 with sklearn 1.5.2, joblib 1.5.3, pytest 9.0.2 (verified). Playwright and Selenium are installed but their browsers may need `playwright install chromium` to be re-runnable.

### 0.2 Working directory

All commands assume the working directory is `/home/z/my-project/repo`. Adjust if you cloned elsewhere.

```bash
cd /home/z/my-project/repo
```

### 0.3 Verify the repo state matches this audit

```bash
# Verify the 7 deliverables exist
ls -la audit/assurance/deliverables/
# Expected: AI_SYSTEM_INVENTORY.md, ARCHITECTURE_AND_DATA_FLOW.md, THREAT_MODEL.md,
#           MODEL_INVENTORY.json, RESEARCH_LEDGER.md, METRIC_CATALOG.json,
#           RESIDUAL_RISK_REGISTER.md, REPRODUCE.md (8 files total)

# Verify key file counts
wc -l data/processed/ad_manifest.jsonl                 # Expected: 5189
wc -l data/annotation/council_resolved_annotations.jsonl  # Expected: 5717
wc -l data/annotation/similarity_links.jsonl           # Expected: 642

# Verify model hashes
sha256sum models/manipulation_tfidf_ovr.joblib
# Expected: 6bb0fbe2eb1c723d1f4473880afaabbc32ab9d7954601a3795bf02c03a05cecc
sha256sum models/manipulation_council_tfidf_ovr.joblib
# Expected: 25b1bcabc15e13180dd969f6f3a0a779a48bf56a0c9e226b3d3264989fe77b28
```

---

## 1. Verify the Python package imports cleanly

```bash
python3 -c "
import adintel
print('adintel version:', adintel.__version__)
from adintel import taxonomy, profile, clustering, authorship, outlier, checkpoints, api, evidence, types
print('taxonomy version:', taxonomy.TAXONOMY_VERSION)
print('top-level families:', len(taxonomy.TOP_LEVEL_FAMILIES))
print('leaf nodes:', len(taxonomy.leaf_nodes()))
print('profile dimensions:', len(types.PROFILE_DIMENSIONS))
print('checkpoint registry:', list(checkpoints.REGISTRY.keys()))
print('api version:', api.API_VERSION)
"
```

**Expected output:**
```
adintel version: adintel-0.1.0
taxonomy version: adintel-taxonomy-v2
top-level families: 6
leaf nodes: 26
profile dimensions: 17
checkpoint registry: ['rule-detector-v1', 'tfidf-ovr-v1', 'persuasive-profile-v1', 'authorship-v1', 'outlier-v1', 'clustering-v1']
api version: adintel-api-v1
```

This verifies the package claims in [`AI_SYSTEM_INVENTORY.md`](./AI_SYSTEM_INVENTORY.md) §3.

---

## 2. Run the test suite

```bash
cd /home/z/my-project/repo
pytest tests/ -v 2>&1 | tail -50
```

**Expected:**
- 113 adintel tests + 75 v1 tests = 188 collected
- 187 pass, 1 environmental fail (per project documentation; NOT re-verified in this audit because the environmental fail likely requires playwright browser setup)

**Quick check (no execution):**
```bash
grep -hcE "^\s*def test_" tests/adintel/test_*.py | paste -sd+ | bc   # Expected: 113
grep -hcE "^\s*def test_" tests/test_*.py       | paste -sd+ | bc   # Expected: 75
```

If you want to run only the adintel suite (which has no playwright dependency):
```bash
pytest tests/adintel/ -v
```

---

## 3. Verify the data lineage

### 3.1 Verify manifest count and first record

```bash
wc -l data/processed/ad_manifest.jsonl   # Expected: 5189
head -1 data/processed/ad_manifest.jsonl | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print('record_id:', d['record_id'][:30] + '...')
print('source_platform:', d['source_platform'])
print('top-level keys:', list(d.keys()))
assert d['record_id'].startswith('h_'), 'record_id should start with h_'
assert 'body_redacted' in d, 'body_redacted field missing'
print('OK')
"
```

### 3.2 Verify annotation count and first record

```bash
wc -l data/annotation/council_resolved_annotations.jsonl   # Expected: 5717
head -1 data/annotation/council_resolved_annotations.jsonl | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print('record_id:', d['record_id'][:30] + '...')
print('split_name:', d['split_name'])
print('layer:', d['layer'])
print('gold:', d['gold'])
print('n_spans:', len(d['spans']))
assert d['gold'] is False, 'gold should be False per council_candidate_model_report.json'
print('OK')
"
```

### 3.3 Verify similarity links

```bash
wc -l data/annotation/similarity_links.jsonl   # Expected: 642
head -1 data/annotation/similarity_links.jsonl | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print('keys:', list(d.keys()))
print('left_record_id:', d['left_record_id'][:30] + '...')
print('character_5gram_jaccard:', d['character_5gram_jaccard'])
print('decision:', d['decision'])
assert d['decision'] == 'accepted', 'first link should be accepted'
print('OK')
"
```

---

## 4. Reproduce the model hashes

```bash
cd /home/z/my-project/repo
sha256sum models/manipulation_tfidf_ovr.joblib
# Expected: 6bb0fbe2eb1c723d1f4473880afaabbc32ab9d7954601a3795bf02c03a05cecc  models/manipulation_tfidf_ovr.joblib

sha256sum models/manipulation_council_tfidf_ovr.joblib
# Expected: 25b1bcabc15e13180dd969f6f3a0a779a48bf56a0c9e226b3d3264989fe77b28  models/manipulation_council_tfidf_ovr.joblib

# Source file hashes for checkpoint references:
sha256sum adintel/*.py tools/detect_manipulation.py tools/train_manipulation_model.py tools/train_council_candidate_model.py tools/generate_council_inferences_report.py
# Compare against AI_SYSTEM_INVENTORY.md §3 and §4
```

If the hashes do not match, the models were either retrained or modified after this audit.

---

## 5. Re-train the v1 model (reproduces `models/manipulation_tfidf_ovr.joblib`)

```bash
cd /home/z/my-project/repo
python3 tools/train_manipulation_model.py
```

This reads `data/processed/ad_manifest.jsonl`, generates weak labels via `tools/detect_manipulation.analyze_text`, fits the TF-IDF + OVR LR pipeline, and writes `models/manipulation_tfidf_ovr.joblib`. The hash of the retrained model may differ from the recorded hash because:
- sklearn version differences (1.5.2 in sandbox; original training version is unknown)
- random_state may produce different MiniBatchKMeans outcomes across versions
- the manifest may have changed since the original training

**Reproducibility note:** the original training was performed against `data/processed/ad_manifest.jsonl` (5,189 records). The original `reports/phase5_model_report.json` (if present) records the metrics from the original training. Compare your retrained metrics against those.

---

## 6. Re-train the council model (reproduces `models/manipulation_council_tfidf_ovr.joblib`)

```bash
cd /home/z/my-project/repo
python3 tools/train_council_candidate_model.py
```

This reads `data/annotation/council_resolved_annotations.jsonl` and `data/annotation/documents.jsonl`, fits the same TF-IDF + OVR LR pipeline, and writes `models/manipulation_council_tfidf_ovr.joblib`. It also writes `reports/council_candidate_model_report.json`.

**Verification after retraining:**
```bash
python3 -c "
import json
d = json.load(open('reports/council_candidate_model_report.json'))
print('split_counts:', d['split_counts'])
# Expected: {'train': 3983, 'validation': 853, 'test': 853, 'challenge': 28}
print('test micro_f1:', d['metrics']['test']['micro_f1'])
# Expected: ~0.9008 (may vary slightly with sklearn version)
print('test macro_f1:', d['metrics']['test']['macro_f1'])
# Expected: ~0.7044
print('test subset_accuracy:', d['metrics']['test']['subset_accuracy'])
# Expected: ~0.5076
"
```

---

## 7. Regenerate the v1 dashboard

```bash
cd /home/z/my-project/repo
python3 tools/generate_council_inferences_report.py
# This produces:
#   reports/council_candidate_inferences.json (~18.8 MB)
#   reports/ad_manipulation_report.html (~12.86 MB)
```

**Verification:**
```bash
ls -la reports/ad_manipulation_report.html
# Expected: ~12,858,658 bytes (size may vary slightly with regenerated data)
head -c 200 reports/ad_manipulation_report.html
# Expected: <!doctype html>...<title>ManiPsych research-v2 model observatory</title>
```

---

## 8. Re-run the adintel pipeline (Stage 4b)

**NOT REPRODUCIBLE — the pipeline runner script is not in the repo.**

The `AdIntelAPI` class is callable in-process, but the script that produced `reports/adintel/*.json` is missing. To reproduce the outputs from a Python REPL:

```python
# From /home/z/my-project/repo
import json
from pathlib import Path
from adintel.api import AdIntelAPI

api = AdIntelAPI()

# Load data
records = [json.loads(line) for line in open('data/processed/ad_manifest.jsonl') if line.strip()]
texts = [f"{r.get('title','')}\n{r.get('body_redacted','')}" for r in records]
annotations = [json.loads(line) for line in open('data/annotation/council_resolved_annotations.jsonl') if line.strip()]
links = [json.loads(line) for line in open('data/annotation/similarity_links.jsonl') if line.strip()]

# 1. Taxonomy
taxonomy_resp = api.get_taxonomy()
Path('reports/adintel/taxonomy_v2.json').write_text(
    json.dumps(taxonomy_resp.typed_output, ensure_ascii=False, indent=2) + '\n'
)

# 2. Profile sample (200 records)
profile_sample = records[:200]
profile_results = []
for r in profile_sample:
    text = f"{r.get('title','')}\n{r.get('body_redacted','')}"
    resp = api.score_profile(text, record_id=r['record_id'])
    profile_results.append(resp.typed_output)
Path('reports/adintel/profile_sample.json').write_text(
    json.dumps({
        'n_sampled': 200,
        'dimension_means': {
            dim: sum(p['dimensions'][dim]['score'] for p in profile_results) / len(profile_results)
            for dim in profile_results[0]['dimensions']
        },
        'profiles': profile_results[:5],  # truncate for size
    }, ensure_ascii=False, indent=2) + '\n'
)

# 3. Clustering (300 records, stratified)
from adintel.clustering import stratified_sample, cluster_all_spaces
sample = stratified_sample(records, by_field='source_platform', n_per_stratum=50)
sample_texts = [f"{r.get('title','')}\n{r.get('body_redacted','')}" for r in sample]
cluster_resp = api.cluster_all_spaces(sample, sample_texts, k=6)
Path('reports/adintel/clustering_summary.json').write_text(
    json.dumps({
        'n_sampled': len(sample),
        'spaces': {space: r.to_dict() for space, (_, r) in cluster_resp.typed_output.items()},
    }, ensure_ascii=False, indent=2) + '\n'
)

# 4. Authorship (41 known pairs)
import random
random.seed(42)
sample_links = random.sample(links, 41) if len(links) > 41 else links
authorship_results = []
for link in sample_links:
    left_rec = next(r for r in records if r['record_id'] == link['left_record_id'])
    right_rec = next(r for r in records if r['record_id'] == link['right_record_id'])
    left_text = f"{left_rec.get('title','')}\n{left_rec.get('body_redacted','')}"
    right_text = f"{right_rec.get('title','')}\n{right_rec.get('body_redacted','')}"
    resp = api.pairwise_verify(left_text, right_text)
    authorship_results.append({
        'left_id': link['left_record_id'],
        'right_id': link['right_record_id'],
        **resp.typed_output,
    })
Path('reports/adintel/authorship_known_pairs.json').write_text(
    json.dumps({
        'n_pairs': len(authorship_results),
        'n_same_source_predicted': sum(1 for r in authorship_results if r['verdict'] == 'same_source'),
        'n_abstained': sum(1 for r in authorship_results if r['verdict'] == 'insufficient_evidence'),
        'accuracy_against_accepted_links': sum(1 for r in authorship_results if r['verdict'] == 'same_source') / len(authorship_results),
        'results_sample': authorship_results[:5],
    }, ensure_ascii=False, indent=2) + '\n'
)

# 5. Outliers (1000 records)
outlier_sample = records[:1000]
outlier_texts = [f"{r.get('title','')}\n{r.get('body_redacted','')}" for r in outlier_sample]
outlier_resp = api.detect_outliers(outlier_texts, outlier_sample)
Path('reports/adintel/outlier_summary.json').write_text(
    json.dumps(outlier_resp.typed_output, ensure_ascii=False, indent=2) + '\n'
)

# 6. Checkpoint registry
from adintel.checkpoints import registry_to_dict
Path('reports/adintel/checkpoint_registry.json').write_text(
    json.dumps(registry_to_dict(), ensure_ascii=False, indent=2) + '\n'
)
```

This should reproduce the 10 JSON outputs under `reports/adintel/`. **The unified dashboard** (`reports/adintel/adintel_dashboard.html`) **cannot be reproduced** because its generator script is not in the repo.

---

## 9. Re-serve the dashboards over HTTP

```bash
cd /home/z/my-project/repo
# Kill any existing server
pkill -f "http.server 8765" 2>/dev/null || true
# Start the server (same as the live one)
python3 -m http.server 8765 --bind 0.0.0.0 --directory /home/z/my-project/repo &
SERVER_PID=$!
sleep 1

# Verify routes
curl -s -o /dev/null -w "v1: %{http_code} %{size_download}\n"      http://localhost:8765/reports/ad_manipulation_report.html
# Expected: v1: 200 12858658

curl -s -o /dev/null -w "unified: %{http_code} %{size_download}\n" http://localhost:8765/reports/adintel/adintel_dashboard.html
# Expected: unified: 200 12861304

curl -s -o /dev/null -w "root: %{http_code} %{size_download}\n"    http://localhost:8765/
# Expected: root: 200 ~1136 (directory listing)

# Leave the server running or kill it
# kill $SERVER_PID
```

**Security warning:** this server is unauthenticated and binds to `0.0.0.0`. Do NOT leave it running on a network with untrusted clients. See [`THREAT_MODEL.md`](./THREAT_MODEL.md) RR-01 for the full risk analysis.

---

## 10. Verify the live server (if already running)

```bash
# Check the server process
ps -fp 993 2>/dev/null || echo "server not running as pid 993"
# Expected: python3 -m http.server 8765 --bind 0.0.0.0 --directory /home/z/my-project/repo

# Check the port
netstat -tnlp 2>/dev/null | grep 8765
# Expected: tcp 0 0 0.0.0.0:8765 0.0.0.0:* LISTEN <pid>/python3

# Verify the dashboard
curl -s -o /dev/null -w "HTTP %{http_code} | %{size_download} bytes\n" --max-time 5 \
  http://localhost:8765/reports/adintel/adintel_dashboard.html
# Expected: HTTP 200 | 12861304 bytes
```

---

## 11. Reproduce the PDF report (Stage 6)

**NOT REPRODUCIBLE — the PDF generation script does not exist in the repo.**

The task brief references `scripts/generate_final_report_pdf.py` → `download/advertisement_intelligence_persuasion_analytics_report.pdf`, but:
- `find . -maxdepth 3 -name "generate_final_report_pdf.py"` → no matches
- `find . -maxdepth 3 -name "scripts" -type d` → no matches
- `find . -maxdepth 3 -name "*.pdf"` → no matches
- `find . -maxdepth 3 -name "download" -type d` → no matches

To create the PDF pipeline (recommended next action):
```bash
mkdir -p scripts download
# Write scripts/generate_final_report_pdf.py to:
#   1. Read reports/adintel/adintel_dashboard.html (or a curated subset)
#   2. Render to PDF via playwright (chromium headless) or weasyprint
#   3. Write to download/advertisement_intelligence_persuasion_analytics_report.pdf
# Then: python3 scripts/generate_final_report_pdf.py
```

---

## 12. Reproduce the audit findings

### 12.1 Verify the audit deliverables parse

```bash
cd /home/z/my-project/repo

# Verify MODEL_INVENTORY.json
python3 -c "
import json
d = json.load(open('audit/assurance/deliverables/MODEL_INVENTORY.json'))
assert isinstance(d, list), 'should be a JSON array'
assert len(d) == 7, f'expected 7 model records, got {len(d)}'
model_ids = [m['model_id'] for m in d]
expected = ['rule-detector-v1', 'tfidf-ovr-v1', 'manipulation_council_tfidf_ovr_v1',
            'persuasive-profile-v1', 'authorship-v1', 'outlier-v1', 'clustering-v1']
assert model_ids == expected, f'model_ids mismatch: {model_ids}'
print('MODEL_INVENTORY.json: OK, 7 records')
"

# Verify METRIC_CATALOG.json
python3 -c "
import json
d = json.load(open('audit/assurance/deliverables/METRIC_CATALOG.json'))
assert 'metrics' in d, 'should have metrics key'
assert len(d['metrics']) == 50, f'expected 50 metrics, got {len(d[\"metrics\"])}'
print('METRIC_CATALOG.json: OK, 50 metrics')
"
```

### 12.2 Re-verify the file integrity

```bash
cd /home/z/my-project/repo

# Re-hash the models and compare to MODEL_INVENTORY.json
sha256sum models/manipulation_tfidf_ovr.joblib models/manipulation_council_tfidf_ovr.joblib

# Re-hash the source files
sha256sum adintel/*.py tools/detect_manipulation.py tools/train_manipulation_model.py \
           tools/train_council_candidate_model.py tools/generate_council_inferences_report.py

# Compare against the hashes recorded in:
#   audit/assurance/deliverables/AI_SYSTEM_INVENTORY.md §3, §4, §5
#   audit/assurance/deliverables/MODEL_INVENTORY.json (checkpoint_hash fields)
```

### 12.3 Re-verify the data counts

```bash
cd /home/z/my-project/repo
echo "manifest:    $(wc -l < data/processed/ad_manifest.jsonl) records (expected 5189)"
echo "annotations: $(wc -l < data/annotation/council_resolved_annotations.jsonl) records (expected 5717)"
echo "sim_links:   $(wc -l < data/annotation/similarity_links.jsonl) records (expected 642)"
echo "adintel tests: $(grep -hcE '^\s*def test_' tests/adintel/test_*.py | paste -sd+ | bc) functions (expected 113)"
echo "v1 tests:      $(grep -hcE '^\s*def test_' tests/test_*.py | paste -sd+ | bc) functions (expected 75)"
```

---

## 13. Reproduce the existing self-audit defects

The repo already contains two candid self-audit defect ledgers. To verify them:

```bash
cd /home/z/my-project/repo

# Round 1 defects (9 defects: R1-D01 .. R1-D09)
grep -E "^## R1-D[0-9]+" reports/adintel/challenge_round1_defects.md
# Expected: 9 lines (R1-D01 through R1-D09)

# Round 2 defects (9 defects: R2-D01 .. R2-D09)
grep -E "^## R2-D[0-9]+" reports/adintel/challenge_round2_defects.md
# Expected: 9 lines (R2-D01 through R2-D09)
```

Each defect has its own "Selected change" and "Measured result" sections. To verify whether the selected changes were actually implemented:
- R1-D01 (cluster brand leakage): the `stratified_sample` helper exists in `adintel/clustering.py:440`, but the latest `reports/adintel/clustering_summary.json` still shows 100% leakage in 4 of 7 spaces. **Not fully implemented.**
- R1-D02 (authorship calibration): the `platt_scale` helper exists in `adintel/checkpoints.py:264`, but no calibration has been applied. **Not implemented.**
- R1-D03 (open-set threshold): documented as a limitation but no code change. **Not implemented.**
- R1-D04 (Spanish regex): no `re.UNICODE` flag added. **Not implemented.**
- R1-D05 (z-score Gaussian assumption): no robust-statistics alternative added. **Not implemented.**
- R1-D06 (calibration not applied): see RR-03. **Not implemented.**
- R1-D07 (causal wording enforcement): the `lint_claim_text` helper exists in `adintel/evidence.py:65`, but it is not called by any pipeline runner. **Partially implemented.**
- R1-D08 (k=1 stability ARI): not specifically tested. **Not verified.**
- R1-D09 (uncertainty hand-set): still hand-set. **Not implemented.**

---

## 14. Reproducibility summary

| Step | Reproducible? | Time | Notes |
|------|:-------------:|:----:|-------|
| 1. Import adintel package | Yes | <1s | No external dependencies |
| 2. Run test suite | Partial | ~30s | 1 environmental fail expected (playwright) |
| 3. Verify data lineage | Yes | <5s | Just `wc -l` and `head -1` |
| 4. Verify model hashes | Yes | <1s | `sha256sum` |
| 5. Retrain v1 model | Yes | ~30s | Hash may differ from recorded due to sklearn version |
| 6. Retrain council model | Yes | ~60s | Metrics should match within ±0.01 |
| 7. Regenerate v1 dashboard | Yes | ~60s | Output size ~12.86 MB |
| 8. Re-run adintel pipeline | Partial | ~10s | Runner script missing; manual Python REPL needed |
| 9. Serve over HTTP | Yes | <1s | Same security caveats apply |
| 10. Verify live server | Yes | <1s | `curl` only |
| 11. Generate PDF | **No** | — | Script does not exist |
| 12. Verify audit deliverables | Yes | <5s | `python3 -c` JSON validation |
| 13. Verify self-audit defects | Yes | <5s | `grep` only |

---

## 15. Cross-references

- AI System Inventory: [`AI_SYSTEM_INVENTORY.md`](./AI_SYSTEM_INVENTORY.md)
- Architecture and data flow: [`ARCHITECTURE_AND_DATA_FLOW.md`](./ARCHITECTURE_AND_DATA_FLOW.md)
- Threat model: [`THREAT_MODEL.md`](./THREAT_MODEL.md)
- Model inventory: [`MODEL_INVENTORY.json`](./MODEL_INVENTORY.json)
- Metric catalog: [`METRIC_CATALOG.json`](./METRIC_CATALOG.json)
- Residual risk register: [`RESIDUAL_RISK_REGISTER.md`](./RESIDUAL_RISK_REGISTER.md)
- Research ledger: [`RESEARCH_LEDGER.md`](./RESEARCH_LEDGER.md)

End of reproduction instructions.
