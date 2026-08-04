#!/usr/bin/env python3
"""Generate reports/adintel/adintel_dashboard.html from pipeline outputs.

Self-contained HTML (no external CDN), keyboard-accessible, reduced-motion
safe, print-friendly. Surfaces:
  - taxonomy v2 overview
  - 17-dimension persuasive-profile sample means
  - 7 cluster spaces with stability + leakage
  - authorship verification results on 41 known same-source pairs
  - 10 outlier types summary
  - checkpoint registry table
  - challenge round defect ledgers (linked)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path("/home/z/my-project/repo")
sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "reports" / "adintel"
HTML_OUT = OUT_DIR / "adintel_dashboard.html"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def render() -> str:
    pipeline = load_json(OUT_DIR / "pipeline_results.json")
    taxonomy = load_json(OUT_DIR / "taxonomy_v2.json")
    profile = load_json(OUT_DIR / "profile_sample.json")
    clustering = load_json(OUT_DIR / "clustering_summary.json")
    authorship = load_json(OUT_DIR / "authorship_known_pairs.json")
    outliers = load_json(OUT_DIR / "outlier_summary.json")
    registry = load_json(OUT_DIR / "checkpoint_registry.json")
    migration = load_json(OUT_DIR / "v1_to_v2_migration_report.json")

    # Build per-dimension table rows
    dim_rows = ""
    if profile:
        means = profile.get("profile_dimension_means", profile.get("dimension_means", {}))
        abstains = profile.get("dimension_abstain_counts", {})
        for dim, mean in sorted(means.items(), key=lambda x: -x[1]):
            abstain = abstains.get(dim, 0)
            pct = mean * 100
            bar_w = max(2, min(100, pct * 2))
            dim_rows += f"""
            <tr>
              <td class="dim">{dim}</td>
              <td><div class="bar"><div class="bar-fill" style="width:{bar_w:.1f}%"></div></div></td>
              <td class="num">{pct:.1f}%</td>
              <td class="num">{abstain}/{profile.get('n_sampled', 0)}</td>
            </tr>"""

    # Cluster spaces rows
    cluster_rows = ""
    if clustering:
        for space, info in clustering.get("spaces", {}).items():
            leakage = info.get("brand_leakage", {})
            leak_str = ", ".join(f"{k}: {v*100:.0f}%" for k, v in leakage.items()) or "none"
            cluster_rows += f"""
            <tr>
              <td class="dim">{space}</td>
              <td class="num">{info.get('n_clusters', 0)}</td>
              <td class="num">{info.get('stability_ari', 0):.3f}</td>
              <td class="num">{info.get('resampling_consistency', 0):.3f}</td>
              <td class="num">{info.get('parameter_sensitivity', 0):.3f}</td>
              <td class="leak">{leak_str}</td>
            </tr>"""

    # Outlier kinds
    outlier_rows = ""
    if outliers:
        for kind, count in sorted(outliers.get("by_kind", {}).items(), key=lambda x: -x[1]):
            outlier_rows += f"<tr><td>{kind}</td><td class='num'>{count}</td></tr>"

    # Checkpoint registry
    cp_rows = ""
    if registry:
        for cid, spec in registry.items():
            cp_rows += f"""
            <tr>
              <td class="dim">{cid}</td>
              <td>{spec.get('version', '')}</td>
              <td>{spec.get('calibration_status', '')}</td>
              <td class="num">${spec.get('cost_usd_per_1k', 0):.3f}</td>
              <td class="num">{spec.get('latency_ms_p50', 0):.1f}ms</td>
              <td>{spec.get('baseline_checkpoint_id') or '—'}</td>
              <td class="abstain">{', '.join(spec.get('abstention_conditions', []))}</td>
            </tr>"""

    # Authorship summary card
    auth_acc = authorship.get("accuracy_against_accepted_links", 0) if authorship else 0
    auth_n = authorship.get("n_pairs", 0) if authorship else 0
    auth_abstain = authorship.get("n_abstained", 0) if authorship else 0

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Advertisement Intelligence and Persuasion Analytics — Audit Dashboard</title>
<style>
:root {{
  --ink:#0f172a; --muted:#475569; --paper:#f8fafc; --card:#ffffff;
  --line:#e2e8f0; --green:#0f766e; --amber:#b45309; --red:#b91c1c; --blue:#1e40af;
  --shadow:0 1px 3px rgba(15,23,42,0.06), 0 1px 2px rgba(15,23,42,0.04);
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--paper); color:var(--ink); font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif; line-height:1.55; }}
a {{ color:var(--blue); }}
header.top {{ background:linear-gradient(135deg,#0f172a,#0f766e); color:white; padding:24px 32px; }}
header.top h1 {{ margin:0 0 4px; font-size:clamp(20px,3vw,28px); font-weight:700; }}
header.top .sub {{ opacity:.88; font-size:14px; }}
main {{ padding:24px 32px; max-width:1400px; margin:0 auto; }}
section {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:20px; margin-bottom:20px; box-shadow:var(--shadow); }}
section h2 {{ margin:0 0 12px; font-size:18px; font-weight:700; border-bottom:2px solid var(--line); padding-bottom:8px; }}
section h3 {{ margin:16px 0 8px; font-size:14px; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin-bottom:8px; }}
.kpi {{ background:var(--paper); border:1px solid var(--line); border-radius:8px; padding:12px 14px; }}
.kpi .label {{ font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; }}
.kpi .value {{ font-size:22px; font-weight:700; margin-top:2px; }}
.kpi .note {{ font-size:11px; color:var(--muted); margin-top:2px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th,td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); }}
th {{ background:var(--paper); font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }}
td.num,th.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
td.dim {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; }}
td.leak {{ font-size:11px; max-width:280px; overflow-wrap:anywhere; }}
td.abstain {{ font-size:11px; color:var(--muted); max-width:240px; overflow-wrap:anywhere; }}
.bar {{ width:140px; height:8px; background:var(--line); border-radius:4px; overflow:hidden; }}
.bar-fill {{ height:100%; background:linear-gradient(90deg,var(--green),var(--amber),var(--red)); }}
.ledger-links {{ display:flex; gap:12px; flex-wrap:wrap; }}
.ledgel-link {{ padding:6px 12px; border:1px solid var(--line); border-radius:999px; font-size:12px; background:var(--paper); }}
.disclaimer {{ background:#fef3c7; border:1px solid #fde68a; border-radius:8px; padding:10px 12px; font-size:12px; color:#78350f; margin-top:12px; }}
.disclaimer strong {{ color:#451a03; }}
footer {{ padding:16px 32px; color:var(--muted); font-size:12px; text-align:center; }}
@media (max-width:760px) {{
  main {{ padding:16px; }}
  .kpis {{ grid-template-columns:repeat(2,1fr); }}
}}
@media print {{
  body {{ background:white; }}
  section {{ box-shadow:none; break-inside:avoid; }}
}}
@media (prefers-reduced-motion:reduce) {{
  * {{ transition:none !important; animation:none !important; }}
}}
</style>
</head>
<body>
<header class="top">
  <h1>Advertisement Intelligence &amp; Persuasion Analytics — Audit Dashboard</h1>
  <div class="sub">adintel v0.1.0 · taxonomy {taxonomy.get('taxonomy_version', 'adintel-taxonomy-v2')} · ran {pipeline.get('ran_at', 'n/a')}</div>
</header>

<main>
  <section>
    <h2>1. Executive KPIs</h2>
    <div class="kpis">
      <div class="kpi"><div class="label">Records in corpus</div><div class="value">{pipeline.get('n_records_total', 0):,}</div><div class="note">from data/processed/ad_manifest.jsonl</div></div>
      <div class="kpi"><div class="label">Council annotations</div><div class="value">{pipeline.get('n_council_annotations', 0):,}</div><div class="note">v1; migrated to v2 (see §7)</div></div>
      <div class="kpi"><div class="label">Authorship accuracy</div><div class="value">{auth_acc*100:.1f}%</div><div class="note">{auth_n} known same-source pairs, {auth_abstain} abstained</div></div>
      <div class="kpi"><div class="label">Outlier reports</div><div class="value">{outliers.get('n_reports', 0):,}</div><div class="note">on {outliers.get('n_sampled', 0)}-ad sample</div></div>
      <div class="kpi"><div class="label">Checkpoints registered</div><div class="value">{pipeline.get('checkpoint_count', 0)}</div><div class="note">all CPU-local; cost $0/1k</div></div>
      <div class="kpi"><div class="label">Pipeline runtime</div><div class="value">{pipeline.get('elapsed_s', 0):.1f}s</div><div class="note">end-to-end on real corpus</div></div>
    </div>
    <div class="disclaimer">
      <strong>Evidence-discipline notice:</strong> technique presence is not proof of persuasion;
      persuasive intensity is not proof of performance; performance association is not proof of
      causation; authorship similarity is not proof of personal identity. Authorship verdicts
      never name a person. See §8 for causal-language linting.
    </div>
  </section>

  <section>
    <h2>2. Hierarchical Taxonomy v2</h2>
    <div class="kpis">
      <div class="kpi"><div class="label">Top-level families</div><div class="value">{len(taxonomy.get('top_level_families', []))}</div></div>
      <div class="kpi"><div class="label">Total nodes</div><div class="value">{len(taxonomy.get('nodes', []))}</div></div>
      <div class="kpi"><div class="label">Leaf labels</div><div class="value">{taxonomy.get('leaf_count', 0)}</div></div>
    </div>
    <h3>v1 → v2 mapping coverage</h3>
    <p style="font-size:13px;">Every v1 leaf label maps to at least one v2 leaf (verified by test). v1's overloaded
    <code>reciprocity_obligation</code> splits into <code>cc_reciprocity_frame</code> (copywriting) and
    <code>bs_reciprocity_obligation</code> (behavioural). Targeting labels (age, education, economic,
    family, gendered-appearance) are reframed as <code>bs_audience_targeting.*</code> because targeting
    is audience context, not a persuasion technique per se.</p>
  </section>

  <section>
    <h2>3. Persuasive Profile — 17 Dimensions (sample means, n={profile.get('n_sampled', 0)})</h2>
    <p style="font-size:13px;">The 17 dimensions are NEVER collapsed into a single universal score (verified by test).
    Each dimension carries its own signal inventory and abstention rule.</p>
    <table>
      <thead><tr><th>Dimension</th><th>Score distribution</th><th class="num">Mean</th><th class="num">Abstained</th></tr></thead>
      <tbody>{dim_rows}</tbody>
    </table>
  </section>

  <section>
    <h2>4. Clustering — 7 Spaces (stratified sample, n={clustering.get('n_sampled', 0)})</h2>
    <p style="font-size:13px;">Brand leakage was 98–100% before Round-1 fix (stratified sampling); now empty for
    persuasive and rhetorical spaces. Residual leakage is sample-size artefact on small strata (Facebook n=26).</p>
    <table>
      <thead><tr><th>Space</th><th class="num">Clusters</th><th class="num">Stability (ARI)</th><th class="num">Pair consistency</th><th class="num">Param sensitivity</th><th>Brand leakage</th></tr></thead>
      <tbody>{cluster_rows}</tbody>
    </table>
  </section>

  <section>
    <h2>5. Authorship / Common-Source Analysis</h2>
    <div class="kpis">
      <div class="kpi"><div class="label">Pairs evaluated</div><div class="value">{auth_n}</div><div class="note">accepted similarity_links</div></div>
      <div class="kpi"><div class="label">Same-source predicted</div><div class="value">{authorship.get('n_same_source_predicted', 0)}</div></div>
      <div class="kpi"><div class="label">Abstained (short text)</div><div class="value">{auth_abstain}</div><div class="note">length-aware abstention</div></div>
      <div class="kpi"><div class="label">Accuracy</div><div class="value">{auth_acc*100:.1f}%</div></div>
    </div>
    <div class="disclaimer">
      <strong>Privacy guardrail:</strong> the authorship module never names a person. <code>person_named</code>
      is always <code>False</code>. Multi-signal scoring (stylometry, lexical richness, template signature,
      structural signature, council overlap) is the maximum the system will assert; person-level attribution
      requires human review and external evidence.
    </div>
  </section>

  <section>
    <h2>6. Outlier Analysis (sample n={outliers.get('n_sampled', 0)})</h2>
    <table>
      <thead><tr><th>Outlier kind</th><th class="num">Reports</th></tr></thead>
      <tbody>{outlier_rows}</tbody>
    </table>
    <p style="font-size:13px;">Every outlier report carries: comparison population, feature space, score, method,
    supporting features, alternative explanation, uncertainty, and review status. Performance outliers use a
    <strong>proxy</strong> (quality_score) because the corpus has no real spend/impressions/CTR — disclosed in
    each report's <code>alternative_explanation</code>.</p>
  </section>

  <section>
    <h2>7. v1 → v2 Annotation Migration</h2>
    <div class="kpis">
      <div class="kpi"><div class="label">Records migrated</div><div class="value">{migration.get('input_records', 0):,} → {migration.get('output_records', 0):,}</div></div>
      <div class="kpi"><div class="label">Unmapped v1 labels</div><div class="value">{len(migration.get('unmapped_v1_labels', []))}</div></div>
      <div class="kpi"><div class="label">Multi-label projections</div><div class="value">{migration.get('n_multi_label_projections', 0):,}</div><div class="note">expected; v1 overloaded labels split</div></div>
    </div>
    <p style="font-size:13px;">Output: <code>data/annotation/council_resolved_annotations_v2.jsonl</code>.
    Each span retains its <code>v1_label</code> and gains <code>v2_labels</code> (list of leaves). Multi-label
    projections require human review before being treated as gold.</p>
  </section>

  <section>
    <h2>8. Checkpoint Registry</h2>
    <table>
      <thead><tr><th>Checkpoint</th><th>Version</th><th>Calibration</th><th class="num">Cost/1k</th><th class="num">Latency p50</th><th>Baseline</th><th>Abstention conditions</th></tr></thead>
      <tbody>{cp_rows}</tbody>
    </table>
    <p style="font-size:13px;">Model disagreement routes to human review (verified by test). Uncalibrated scores
    are never averaged (verified by test). Calibration helpers (Platt, temperature) are available but not yet
    wired for every checkpoint — see Challenge Round 1 defect R1-D06.</p>
  </section>

  <section>
    <h2>9. Challenge Round Defect Ledgers</h2>
    <div class="ledger-links">
      <a class="ledgel-link" href="challenge_round1_defects.md">Round 1 — scientific validity (9 defects)</a>
      <a class="ledgel-link" href="challenge_round2_defects.md">Round 2 — analyst usefulness (9 defects)</a>
    </div>
    <p style="font-size:13px; margin-top:12px;">Round 1 found 1 critical and 3 high-severity defects; 4 fixed
    in-session (stratified sampling, Unicode robustness, evidence-discipline lint, MAD outlier hook). Round 2
    found 3 high-severity defects; 2 fixed in-session (output_version field, dashboard) and 1 deferred
    (annotation GUI v2). See ledger files for full details.</p>
  </section>
</main>

<footer>
  Generated by <code>scripts/generate_adintel_dashboard.py</code> from <code>reports/adintel/*.json</code>.
  All scores are signals, not proofs. Read the evidence-discipline notice in §1 before citing any number.
</footer>
</body>
</html>
"""
    return html


def main() -> int:
    HTML_OUT.write_text(render(), encoding="utf-8")
    print(f"Wrote {HTML_OUT} ({HTML_OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
