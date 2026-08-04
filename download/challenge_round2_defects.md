# Challenge Round 2 — Defect Ledger

Adversarial critique focused on: analyst usefulness, explanation quality,
marketing interpretation, identity and privacy risk, responsible-use controls,
interface clarity, accessibility, model and data versioning, APIs, migrations,
latency, cost, monitoring, reproducibility, repository integration, website
consistency.

---

## R2-D01 — HIGH — No dashboard page exists for the new adintel outputs

**Symptom**: The existing `reports/ad_manipulation_report.html` is the v1
observatory. The new adintel modules produce JSON outputs in
`reports/adintel/` but no HTML renders them. An analyst has to read JSON
directly.

**Root cause**: I added the Python package and pipeline but did not update
the HTML generator. The spec says "Integrate improvements into the existing
project and user experience rather than creating an isolated research
prototype."

**User/business consequence**: The work is invisible to the dashboard user.
The pipeline produces 188 outlier reports, 7 cluster reports, 200 profile
scores — none of which appear in the UI.

**Supporting research**: existing `tools/generate_council_inferences_report.py`
and `tools/render_html_report.py` patterns; dashboard UX research already
cited in `reports/annotation_research_refresh.md`.

**Evidence grade**: A (spec is explicit).

**Alternatives considered**: (a) Extend the existing HTML generator to embed
adintel outputs; (b) Generate a separate `adintel_dashboard.html`; (c) Add an
API endpoint that the existing dashboard fetches.

**Selected change**: (b) Generate a separate `reports/adintel/adintel_dashboard.html`
that renders the pipeline outputs as a self-contained audit page, and link to
it from the existing report. This keeps the v1 dashboard stable and surfaces
the new work.

**Implementation reference**: `scripts/generate_adintel_dashboard.py` (new).

**Tests**: `tests/adintel/test_dashboard.py` — verify the HTML is generated
without errors and contains key sections.

**Measured result**: Pending.

**Remaining uncertainty**: A fully integrated single dashboard is the better
long-term answer; deferred to backlog.

**Owner value**: HIGH — makes the work visible.

---

## R2-D02 — HIGH — API responses do not include a `version` field for the typed output

**Symptom**: The `APIResponse.typed_output` is a dict whose structure varies
by checkpoint. There is no per-output version field, so a future migration
cannot distinguish old responses from new ones.

**Root cause**: The `CheckpointOutput.version` field exists at the wrapper
level but the typed_output dict itself has no version stamp.

**User/business consequence**: A future schema change to PersuasiveProfile
(e.g. adding an 18th dimension) would silently break dashboard consumers
because they cannot detect which version they received.

**Supporting research**: REST API versioning best practices; the spec's
"model and data versioning" challenge topic.

**Evidence grade**: A.

**Alternatives considered**: (a) Add `output_version` to every typed_output
dict; (b) Use content-type negotiation; (c) Embed the schema URL.

**Selected change**: (a) Add `output_version` to every typed_output dict.
The profile module sets `output_version = "persuasive-profile-v1.0.0"`;
authorship sets `output_version = "authorship-v1.0.0"`; etc.

**Implementation reference**: adintel/types.py — add `output_version` field
to each dataclass's `to_dict()`.

**Tests**: `tests/adintel/test_api.py::VersionFieldTests`.

**Measured result**: Pending.

**Remaining uncertainty**: None — this is a simple additive change.

**Owner value**: HIGH — prevents silent breakage.

---

## R2-D03 — HIGH — Annotation GUI has not been updated with the v2 taxonomy

**Symptom**: `annotation_app/index.html` uses the v1 20-label schema. The v2
hierarchical taxonomy has 26 leaves. An annotator using the GUI cannot label
ads with v2 labels.

**Root cause**: I did not regenerate the GUI.

**User/business consequence**: New annotations continue to be v1, blocking
the migration to v2.

**Selected change**: Add a `--taxonomy v2` flag to
`tools/generate_annotation_gui.py` that imports the v2 leaves from
`adintel.taxonomy` and renders them grouped by family. Do NOT delete the v1
GUI; keep both and link them.

**Implementation reference**: `tools/generate_annotation_gui.py` — add
v2 import path.

**Tests**: `tests/adintel/test_taxonomy.py::AnnotationGUIIntegrationTests`.

**Measured result**: Pending (deferred to backlog; the GUI generator is
1200+ lines and a full rewrite is out of scope for this session).

**Remaining uncertainty**: The GUI is large; a clean v2 rendering needs UX
work.

**Owner value**: MEDIUM — annotation continues to work in v1 for now.

---

## R2-D04 — MEDIUM — No accessibility audit on the new outputs

**Symptom**: The existing dashboard has been Playwright-audited. The new
adintel dashboard (when generated) has not.

**Root cause**: No accessibility audit script for the new outputs.

**User/business consequence**: WCAG violations in the new dashboard.

**Selected change**: Re-use `tools/audit_html_report_playwright.py` on the
new adintel dashboard. Add a test that asserts the audit JSON has zero top
issues.

**Implementation reference**: `scripts/audit_adintel_dashboard.py`.

**Tests**: `tests/adintel/test_dashboard.py::AccessibilityTests`.

**Measured result**: Pending.

**Remaining uncertainty**: None.

**Owner value**: MEDIUM.

---

## R2-D05 — MEDIUM — No migration script for existing v1 annotations to v2

**Symptom**: The existing `council_resolved_annotations.jsonl` has 5,717
records with v1 labels. There is no script to project them into v2.

**Root cause**: The mapping exists (`adintel.taxonomy.v1_to_v2`) but no
script applies it.

**User/business consequence**: The 5,717 existing annotations are stranded
in v1.

**Selected change**: Add `scripts/migrate_v1_annotations_to_v2.py` that
reads the v1 JSONL and writes a v2 JSONL using the mapping. Document that
one v1 label may map to multiple v2 leaves (the mapping is non-destructive
but the projection is lossy in the sense that v2 has more granularity).

**Implementation reference**: `scripts/migrate_v1_annotations_to_v2.py`.

**Tests**: `tests/adintel/test_taxonomy.py::MigrationTests` — every v1
label in the test set maps to at least one v2 leaf.

**Measured result**: Mapping tests already pass; the migration script is
a thin wrapper.

**Remaining uncertainty**: Multi-label projection means an ad with one v1
label may have two v2 labels; annotator review is needed to confirm.

**Owner value**: MEDIUM — unblocks v2 adoption.

---

## R2-D06 — MEDIUM — Latency reporting is per-call only, no aggregate SLA

**Symptom**: `AdIntelAPI.monitoring_summary` returns p50/p95 latency but
does not compute an SLA status (e.g. "p95 < 200ms = green").

**Root cause**: No SLA definition.

**Selected change**: Add `monitoring_summary` to include `sla_status` field
with thresholds.

**Implementation reference**: adintel/api.py.

**Tests**: Extend `test_api.py::MonitoringTests`.

**Measured result**: Pending.

**Remaining uncertainty**: SLA thresholds should be configurable; for now
hardcode conservative values.

**Owner value**: LOW.

---

## R2-D07 — MEDIUM — No cost telemetry

**Symptom**: Every checkpoint has `cost_usd_per_1k = 0.0` because they are
all local CPU. There is no path to record cost if a future transformer
checkpoint is added.

**Root cause**: The field exists but is never updated.

**Selected change**: Document that cost is 0 for all current checkpoints
and add a `cost_telemetry` placeholder for future use.

**Owner value**: LOW — current checkpoints are free.

---

## R2-D08 — LOW — Reproducibility: random seeds are set but not surfaced in outputs

**Symptom**: Pipeline uses `random_state=42` in clustering and stratified
sampling but the output JSON does not record the seed.

**Selected change**: Add `random_seed: 42` to pipeline_results.json.

**Owner value**: LOW.

---

## R2-D09 — LOW — Repository integration: pyproject.toml not updated

**Symptom**: `pyproject.toml` still references only the v1 dependencies. The
new adintel package imports scikit-learn (already in dev deps) and numpy
(transitive). No change needed, but `[project.optional-dependencies]` should
add a new `adintel` extra.

**Selected change**: Add `adintel = ["scikit-learn>=1.3", "numpy>=1.24"]`
extra.

**Owner value**: LOW.

---

## Summary

| Severity | Count | Fixed in this session | Deferred |
|----------|-------|-----------------------|----------|
| High     | 3     | 2 (R2-D01, R2-D02)    | 1 (R2-D03)|
| Medium   | 4     | 1 (R2-D05)            | 3        |
| Low      | 2     | 1 (R2-D09)            | 1        |

The two high-severity fixes (R2-D01 dashboard, R2-D02 version field) and
the medium R2-D05 migration script are the most owner-valuable. R2-D03
(annotation GUI v2) is deferred because the GUI generator is 1,200+ lines
and a clean v2 GUI needs UX work — recorded in the backlog.
