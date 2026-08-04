# Dashboard Restoration Research Plan

## Protocol

This plan governs all dashboard restoration work. No implementation may
begin until the research gate for each feature passes.

## Scope

Two HTML artifacts:
1. `reports/ad_manipulation_report.html` — v1 original (680 lines, 12.2 MB
   with embedded data)
2. `reports/adintel/adintel_dashboard.html` — unified superset (12.5 MB,
   v1 + adintel)

Plus the annotation studio at `annotation_app/index.html` (180 lines).

## Phase R0 — Library version manifest

**Status: COMPLETE.**

Artifact: `library-version-manifest.json`

Key finding: the dashboard is **fully self-contained** — no CDN, no external
scripts, no fetch/XHR. The only "library" is `reports/assets/d3-lite-force.js`,
an 89-line vendored mini-D3 force layout helper.

**Critical regression found**: the unified dashboard does NOT load
`d3-lite-force.js`, so the term network falls back to a circular layout.

## Phase R1 — Project memory and local prior art

**Status: COMPLETE.**

### Git history
- Only 2 commits touch the dashboard: initial commit + the superset restore.
- No prior merge attempts, no rejected library changes, no performance
  regression history (the repo was freshly initialized).

### Existing reusable helpers
- `tools/generate_council_inferences_report.py` (1810 lines) — the original
  dashboard generator. Contains all chart-rendering JS as string templates.
- `tools/render_html_report.py` (300 lines) — simpler HTML renderer.
- `tools/generate_annotation_gui.py` (356 lines) — annotation studio generator.
- `tools/audit_html_report_playwright.py` (528 lines) — established Playwright
  audit pattern with mouse + keyboard interaction tests.
- `tools/audit_annotation_gui_playwright.py` — annotation studio audit.

### Established test patterns
The existing Playwright audit script (`tools/audit_html_report_playwright.py`)
already implements:
- DOM metric collection via `page.evaluate()` (100+ metrics)
- Keyboard interaction tests (n/p/1/2/3/Escape slash)
- Mouse click tests on rank list, network nodes, map points
- Select/filter/change tests on dropdowns
- Duplicate-ID detection
- Unnamed-button detection
- Unlabelled-control detection
- Network label overlap detection
- Span offset validation
- Deep-link hash validation
- Mobile viewport overflow detection

**Decision**: the new Playwright tests must follow this same pattern and extend
it to cover the adintel sections.

## Phase R2 — Research questions

Each feature family has a precise research question in its technique-decision
record. See `technique-decisions/` directory.

## Phase R3 — Multi-perspective research fan-out

For each feature family, research from 8 perspectives:
1. Visualization theory
2. Domain/statistical correctness
3. Interaction/UX
4. Accessibility
5. Frontend architecture
6. Performance
7. Security/provenance
8. Maintainability/reproducibility

## Phase R4 — Source hierarchy

Sources consulted (in priority order):
1. W3C SVG 1.1 spec, WCAG 2.2, ARIA 1.3
2. MDN Web Docs (current)
3. Existing project code (primary source for established patterns)
4. D3.js official docs (for force layout theory, even though we use a lite version)
5. Playwright official docs (for testing patterns)

## Phase R5 — Comparable projects

See `comparable-projects.jsonl`.

## Phase R6 — Feature-specific research

Each feature family has a dedicated research record:
- `technique-decisions/kpi-cards.md`
- `technique-decisions/roc-pr-curves.md`
- `technique-decisions/metric-heatmap.md`
- `technique-decisions/timeline.md`
- `technique-decisions/term-network.md`
- `technique-decisions/corpus-map.md`
- `technique-decisions/explainability-atlas.md`
- `technique-decisions/top-explorer.md`
- `technique-decisions/pipeline-diagram.md`
- `technique-decisions/threshold-controls.md`
- `technique-decisions/observability-panel.md`
- `technique-decisions/adintel-profile.md`
- `technique-decisions/adintel-clustering.md`
- `technique-decisions/adintel-authorship.md`
- `technique-decisions/adintel-outliers.md`

## Phase R7 — Decision matrix

Each technique-decision record contains the weighted rubric:
- Original feature fidelity: 25%
- Statistical/semantic accuracy: 15%
- Accessibility: 15%
- Task effectiveness: 15%
- Performance at scale: 10%
- Maintainability: 10%
- Responsive: 5%
- Self-contained compatibility: 5%

## Phase R8 — Prototype and benchmark

The current unified dashboard IS the prototype. Playwright tests are the
benchmark. Results in `benchmark-results/`.

## Phase R9 — Research-to-Red contract

Each feature gets a JSON contract at `research-gates/<feature-id>.json`.

## Live server

A persistent HTTP server is running at `http://localhost:8765/` serving the
repo root. The dashboard is accessible at:
`http://localhost:8765/reports/adintel/adintel_dashboard.html`

This server stays alive for user testing and feedback.

## Playwright testing

Tests use ONLY mouse and keyboard emulation (no shell commands during test
execution). Test script: `scripts/playwright_dashboard_audit.py`.
