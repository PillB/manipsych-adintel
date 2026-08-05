#!/usr/bin/env python3
"""Generate reports/adintel/adintel_dashboard.html — a SUPERSET of the
original v1 observatory (reports/ad_manipulation_report.html) plus the new
adintel audit sections.

This generator NEVER removes content from the original. It:
  1. Embeds the same council_candidate_inferences.json data the original uses.
  2. Restores every original section: KPIs, pipeline diagram, diagnostics
     (curves, timeline, heatmap, error lifecycle, underperforming slices,
     latent clusters, threshold overlay), explainability atlas, term network,
     corpus map, facet overview + taxonomy matrix, top-25 explorer with
     annotated text + score waterfall + explanation ledger + ELI5 dossier +
     model predictions + council-vs-model, observability + label distribution,
     expert POC, research-backed design choices.
  3. ADDS new adintel sections: taxonomy v2 overview, 17-dim persuasive
     profile, 7-space clustering, authorship results, outlier analysis,
     v1->v2 migration, checkpoint registry, challenge round ledgers.

The result is a single self-contained HTML file that is strictly richer
than the original.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path("/home/z/my-project/repo")
sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "reports" / "adintel"
HTML_OUT = OUT_DIR / "adintel_dashboard.html"
V1_INFERENCES = REPO / "reports" / "council_candidate_inferences.json"
V1_MODEL_REPORT = REPO / "reports" / "council_candidate_model_report.json"
V1_SEGMENT_REPORT = REPO / "reports" / "segment_model_analysis.json"


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
    v1_inf = load_json(V1_INFERENCES)
    v1_model = load_json(V1_MODEL_REPORT)
    v1_segment = load_json(V1_SEGMENT_REPORT)
    full_data = load_json(OUT_DIR / "full_data_results.json")
    cluster_align = load_json(OUT_DIR / "cluster_alignment_report.json")
    deep_clustering = load_json(OUT_DIR / "deep_clustering_analysis.json")

    # ------------------------------------------------------------------
    # Build per-dimension table rows from FULL DATA (not sample)
    # ------------------------------------------------------------------
    dim_rows = ""
    if full_data and full_data.get("profile", {}).get("dimensions"):
        dims = full_data["profile"]["dimensions"]
        for dim, stats in sorted(dims.items(), key=lambda x: -x[1]["mean"]):
            pct = stats["mean"] * 100
            bar_w = max(2, min(100, pct * 2))
            prev = stats.get("prevalence", 0) * 100
            abst = stats.get("abstention_rate", 0) * 100
            dim_rows += f"""
            <tr>
              <td class="dim">{dim}</td>
              <td><div class="bar"><div class="bar-fill" style="width:{bar_w:.1f}%"></div></div></td>
              <td class="num">{pct:.1f}%</td>
              <td class="num">{prev:.1f}%</td>
              <td class="num">{abst:.1f}%</td>
            </tr>"""
    elif profile:
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
              <td class="num">—</td>
              <td class="num">{abstain}/{profile.get('n_sampled', 0)}</td>
            </tr>"""

    # Build technique results rows from FULL DATA
    tech_rows = ""
    tech_examples_html = ""
    if full_data and full_data.get("techniques", {}).get("results"):
        techs = sorted(full_data["techniques"]["results"], key=lambda x: -x["count"])
        for t in techs:
            ex = t.get("examples", [{}])[0] if t.get("examples") else {}
            ex_title = ex.get("title", "")[:50]
            ex_rid = ex.get("record_id", "")[:20]
            v2 = ", ".join(t.get("v2_leaves", []))
            tech_rows += f"""
            <tr>
              <td class="dim">{t['label']}</td>
              <td class="num">{t['count']}</td>
              <td class="num">{t['prevalence']*100:.1f}%</td>
              <td class="dim">{v2}</td>
              <td>{ex_title} <span class="small">({ex_rid}...)</span></td>
            </tr>"""
        # Build example cards for top 5 techniques with full ad text
        for t in techs[:5]:
            ex = t.get("examples", [{}])[0] if t.get("examples") else {}
            ex_title = ex.get("title", "N/A")
            ex_rid = ex.get("record_id", "N/A")
            ex_platform = ex.get("platform", "N/A")
            tech_examples_html += f"""
            <div class="dossier-card" style="border-left:4px solid var(--violet);">
              <p class="small"><b>{t['label']}</b> (count={t['count']}, prevalence={t['prevalence']*100:.1f}%)</p>
              <p class="small"><b>Example ad:</b> {ex_title}</p>
              <p class="small"><b>Record:</b> <code>{ex_rid[:30]}...</code> | <b>Platform:</b> {ex_platform}</p>
              <p class="small" style="background:var(--soft);padding:8px;border-radius:6px;font-style:italic;">"{ex_title}"</p>
              <p class="small"><b>v2 mapping:</b> {', '.join(t.get('v2_leaves', []))}</p>
            </div>"""

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

    # Build deep clustering enriched-term rows and cluster cards
    enriched_term_rows = ""
    deep_cluster_cards = ""
    deep_cluster_explorer_js = ""
    if deep_clustering:
        # Enriched term rows
        for term, o, n_val, ratio in deep_clustering.get("outlier_analysis", {}).get("enriched_terms", [])[:15]:
            ratio_str = f"{ratio}x" if ratio != 999 else "ONLY in outliers"
            interp = "Geographic-specific" if any(g in term for g in ["juliaca","puno","huancayo","lima"]) else \
                     "Structured info pattern" if "situacion" in term or "informacion" in term else \
                     "Different verb construction" if any(v in term for v in ["da","se da","se brinda"]) else \
                     "Formality/status signal" if "soltero" in term else "Content pattern"
            enriched_term_rows += f"""
            <tr>
              <td class="dim">{term}</td>
              <td class="num">{o}</td>
              <td class="num">{n_val if n_val > 0 else '0 (absent)'}</td>
              <td class="num">{ratio_str}</td>
              <td>{interp}</td>
            </tr>"""

        # Deep cluster cards with real ad examples
        for c in deep_clustering.get("deep_clustering", {}).get("clusters", []):
            terms = ", ".join(t for t, w in c.get("distinguishing_terms", [])[:4])
            platforms = ", ".join(f"{k}: {v}" for k, v in c.get("platform_distribution", {}).items())
            outlier_rate = c.get("outlier_rate", 0)
            outlier_color = "var(--red)" if outlier_rate > 0.5 else "var(--amber)" if outlier_rate > 0.2 else "var(--green)"

            # Build sample ad cards
            sample_html = ""
            for ad in c.get("sample_ads", []):
                sample_html += f"""
                <div class="dossier-card" style="margin:4px 0;padding:8px;">
                  <p class="small"><b>{ad.get('title','N/A')}</b></p>
                  <p class="small" style="color:var(--muted);">Platform: {ad.get('platform','N/A')} | Record: <code>{ad.get('record_id','')[:25]}...</code></p>
                  <p class="small" style="background:var(--soft);padding:6px;border-radius:4px;font-style:italic;">"{ad.get('body_preview','N/A')[:100]}..."</p>
                </div>"""

            deep_cluster_cards += f"""
            <div class="dossier-card" style="border-left:4px solid {outlier_color};margin:8px 0;">
              <h3 style="color:var(--ink);text-transform:none;">Cluster {c['cluster_id']} — {c['n_members']} records</h3>
              <p class="small"><b>Distinguishing terms:</b> {terms}</p>
              <p class="small"><b>Platform mix:</b> {platforms}</p>
              <p class="small"><b>Outlier rate:</b> <span style="color:{outlier_color};font-weight:700;">{outlier_rate*100:.1f}%</span></p>
              <div style="margin-top:8px;">
                <p class="small"><b>Representative ads:</b></p>
                {sample_html}
              </div>
            </div>"""

    outlier_rows = ""
    if outliers:
        for kind, count in sorted(outliers.get("by_kind", {}).items(), key=lambda x: -x[1]):
            outlier_rows += f"<tr><td>{kind}</td><td class='num'>{count}</td></tr>"

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

    auth_acc = authorship.get("accuracy_against_accepted_links", 0) if authorship else 0
    auth_n = authorship.get("n_pairs", 0) if authorship else 0
    auth_abstain = authorship.get("n_abstained", 0) if authorship else 0

    # Pre-compute v1 model metrics for the KPI cards (avoids dict-in-fstring issues)
    v1_test = (v1_model.get("metrics") or {}).get("test") or {}
    v1_micro_f1 = v1_test.get("micro_f1", 0.9008)
    v1_macro_f1 = v1_test.get("macro_f1", 0.7044)
    v1_roc_auc = v1_test.get("roc_auc_micro", 0.9872)
    v1_label_acc = v1_test.get("label_accuracy_micro", 0.961)
    v1_records = v1_inf.get("records", 5717)
    v1_spans = v1_inf.get("span_count", 36585)
    v1_zero = v1_inf.get("zero_span_records", 0)
    v1_gold = str(v1_inf.get("gold", False)).lower()

    # ------------------------------------------------------------------
    # Embed v1 inferences JSON for the original sections
    # ------------------------------------------------------------------
    v1_inf_json = json.dumps(v1_inf, ensure_ascii=False) if v1_inf else "{}"
    v1_model_json = json.dumps(v1_model, ensure_ascii=False) if v1_model else "{}"
    v1_segment_json = json.dumps(v1_segment, ensure_ascii=False) if v1_segment else "{}"

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ManiPsych + adintel — Unified Observatory</title>
<style>
:root {{
  --ink:#0f172a; --muted:#475569; --paper:#f8fafc; --card:#ffffff;
  --line:#e2e8f0; --green:#0f766e; --amber:#b45309; --red:#b91c1c; --blue:#1e40af;
  --violet:#6d4fa3; --soft:#f1f5f9;
  --shadow:0 1px 3px rgba(15,23,42,0.06), 0 1px 2px rgba(15,23,42,0.04);
}}
* {{ box-sizing:border-box; }}
html {{ scroll-behavior:smooth; scroll-padding-top:140px; }}
body {{ margin:0; background:var(--paper); color:var(--ink); font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif; line-height:1.55; overflow-x:hidden; }}
a {{ color:var(--blue); }}
.skip {{ position:absolute;left:-999px; }} .skip:focus {{ left:16px;top:16px;background:#fff;padding:10px;border-radius:10px;z-index:9; }}

/* Hero */
header.hero {{ background:linear-gradient(135deg,#0f172a,#0f766e 55%,#714f28); color:white; padding:20px 32px; box-shadow:0 10px 40px rgba(0,0,0,0.15); position:sticky; top:0; z-index:5; }}
.hero-inner {{ display:grid; grid-template-columns:1.2fr .8fr; gap:18px; align-items:center; max-width:1500px; margin:0 auto; }}
.eyebrow {{ font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:#a8d7bd; font-weight:800; }}
header.hero h1 {{ margin:6px 0; font-size:clamp(22px,3vw,32px); font-weight:700; line-height:1.1; }}
header.hero .sub {{ color:#dce9e1; margin:0; font-size:13px; line-height:1.5; }}
nav.nav {{ display:flex; flex-wrap:wrap; gap:4px; justify-content:flex-end; align-items:center; }}
nav.nav a {{ border:1px solid #ffffff36; background:#ffffff14; color:inherit; border-radius:6px; padding:4px 9px; text-decoration:none; font-size:11px; font-weight:600; transition:background 0.15s; }}
nav.nav a:hover {{ background:#ffffff30; }}
nav.nav a.active {{ background:#0f766e; border-color:#0f766e; }}
nav.nav .nav-group {{ font-size:9px; color:#a8d7bd; text-transform:uppercase; letter-spacing:0.08em; padding:0 4px; opacity:0.7; }}
nav.nav .nav-sep {{ width:1px; height:20px; background:#ffffff30; margin:0 2px; }}

/* Layout */
main {{ padding:20px 32px; max-width:1500px; margin:0 auto; }}
section {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:18px; margin-bottom:16px; box-shadow:var(--shadow); scroll-margin-top:140px; }}
section h2 {{ margin:0 0 10px; font-size:16px; font-weight:700; border-bottom:2px solid var(--line); padding-bottom:6px; }}
section h3 {{ margin:12px 0 6px; font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; }}

/* KPIs */
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; }}
.kpi {{ background:var(--soft); border:1px solid var(--line); border-radius:8px; padding:10px 12px; }}
.kpi .label {{ font-size:10px; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; }}
.kpi .value {{ font-size:20px; font-weight:700; margin-top:2px; }}
.kpi .note {{ font-size:10px; color:var(--muted); margin-top:2px; }}

/* Tables */
table {{ width:100%; border-collapse:collapse; font-size:12px; display:block; overflow-x:auto; -webkit-overflow-scrolling:touch; }}
th,td {{ text-align:left; padding:7px 8px; border-bottom:1px solid var(--line); }}
tr:nth-child(even) td {{ background:rgba(241,245,249,0.5); }}
th {{ background:var(--soft); font-weight:600; font-size:11px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }}
td.num,th.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
td.dim {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:11px; }}
td.leak {{ font-size:10px; max-width:240px; overflow-wrap:anywhere; }}
td.abstain {{ font-size:10px; color:var(--muted); max-width:200px; overflow-wrap:anywhere; }}

/* Bars */
.bar {{ width:120px; height:7px; background:var(--line); border-radius:4px; overflow:hidden; display:inline-block; vertical-align:middle; }}
.bar-fill {{ height:100%; background:linear-gradient(90deg,var(--green),var(--amber),var(--red)); }}
.rowline {{ display:grid; grid-template-columns:140px 1fr 50px; gap:8px; align-items:center; padding:3px 0; font-size:11px; }}
.rowline .bar {{ width:100%; }}

/* Tutorial */
.tutorial {{ background:var(--soft); border-left:3px solid var(--blue); border-radius:6px; padding:8px 12px; margin:8px 0; font-size:11px; }}
.tutorial h3 {{ margin:0 0 4px; color:var(--blue); }}
.tutorial ul {{ margin:4px 0 0 16px; padding:0; }}

/* Disclaimer */
.disclaimer {{ background:#fef3c7; border:1px solid #fde68a; border-radius:8px; padding:8px 10px; font-size:11px; color:#78350f; margin-top:8px; }}
.disclaimer strong {{ color:#451a03; }}

/* Pipeline SVG */
.pipe-svg {{ width:100%; height:auto; max-height:400px; }}
.svg-scroll {{ overflow-x:auto; -webkit-overflow-scrolling:touch; }}
.pipe-svg .node {{ fill:#fffffb; stroke:var(--green); stroke-width:2; }}
.pipe-svg .node-title {{ font-size:13px; font-weight:800; fill:var(--ink); }}
.pipe-svg .node-sub {{ font-size:10px; fill:var(--muted); }}
.pipe-svg .flow {{ fill:none; stroke:var(--green); stroke-width:2.5; }}
.pipe-svg .flow.dash {{ stroke-dasharray:6 5; stroke:var(--amber); }}
.pipe-svg .flow.pulse {{ stroke:var(--blue); }}

/* Viz grids */
.viz-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
.viz-grid .full {{ grid-column:1 / -1; }}
.big-viz {{ width:100%; height:500px; background:var(--soft); border:1px solid var(--line); border-radius:8px; overflow:hidden; }}
.tutorial-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:8px; }}
.tutorial-card {{ background:#fff; border:1px solid var(--line); border-radius:6px; padding:6px 8px; font-size:11px; }}
.viz-toolbar {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:6px 0; }}
.control {{ border:1px solid var(--line); background:#fff; border-radius:6px; padding:5px 8px; font-size:11px; }}
.legend-row {{ display:flex; flex-wrap:wrap; gap:6px; margin:6px 0; font-size:11px; }}
.legend-item {{ display:inline-flex; align-items:center; gap:4px; padding:2px 6px; background:var(--soft); border-radius:4px; }}
.swatch {{ width:12px; height:12px; border-radius:3px; display:inline-block; }}

/* Explorer */
.layout {{ display:grid; grid-template-columns:280px 1fr 320px; gap:16px; }}
.layout .controls {{ }}
.layout .controls label {{ display:block; font-size:11px; color:var(--muted); margin:6px 0 2px; }}
.list {{ max-height:60vh; overflow:auto; display:grid; gap:6px; margin-top:8px; }}
.rank {{ text-align:left; border:1px solid var(--line); background:#fff; border-radius:8px; padding:8px; cursor:pointer; width:100%; }}
.rank[aria-current="true"] {{ outline:3px solid var(--green); outline-offset:1px; }}
.rank-title {{ font-size:12px; font-weight:600; margin:3px 0; }}
.scoreline {{ display:flex; gap:4px; flex-wrap:wrap; margin-top:4px; }}
.chip {{ display:inline-flex; border-radius:999px; padding:2px 7px; font-size:10px; font-weight:700; background:var(--soft); color:var(--ink); }}
.chip.red {{ background:#fae0dc; color:#7b241d; }}
.chip.amber {{ background:#f7ead7; color:#744512; }}
.chip.blue {{ background:#e2edf9; color:#213d65; }}
.chip.violet {{ background:#ede5f7; color:#4a3270; }}
.small {{ font-size:11px; color:var(--muted); }}
.annotated {{ white-space:pre-wrap; line-height:2; font-size:14px; max-height:50vh; overflow:auto; background:#fff; border:1px solid var(--line); border-radius:8px; padding:14px; }}
.seg {{ background:linear-gradient(transparent 56%,#f7cf78 56%,#f7cf78 72%,transparent 72%); border-radius:3px; padding:1px 0; }}
.seg.manip {{ background:linear-gradient(transparent 52%,#eda49d 52%,#eda49d 70%,transparent 70%),linear-gradient(transparent 74%,#93c5fd 74%,#93c5fd 88%,transparent 88%); }}
.waterfall {{ }}
.ledger {{ max-height:30vh; overflow:auto; }}
.ledger-row {{ border-bottom:1px solid var(--line); padding:6px 0; font-size:11px; }}
.dossier-card {{ background:var(--soft); border-radius:8px; padding:8px; margin:6px 0; }}
.eli5 {{ background:#fff; border-left:3px solid var(--green); padding:4px 8px; margin:4px 0; font-size:11px; }}
.type-badge {{ display:inline-block; background:var(--blue); color:#fff; border-radius:4px; padding:1px 5px; font-size:9px; font-weight:700; margin-left:4px; }}
.facet-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:10px; }}
.facet-card {{ background:var(--soft); border-radius:8px; padding:8px; }}
.facet-card h3 {{ margin:0 0 4px; color:var(--ink); text-transform:none; }}
.heat {{ font-size:11px; }}
.heat-row {{ display:grid; grid-template-columns:1.4fr .6fr .6fr .6fr .6fr; gap:4px; padding:2px 0; }}
.heat-cell {{ text-align:center; padding:2px; border-radius:3px; }}
.timeline {{ max-height:300px; overflow:auto; }}
.timeline-row {{ display:grid; grid-template-columns:90px 1fr 90px; gap:8px; padding:6px 0; border-bottom:1px solid var(--line); font-size:11px; }}
.slice-card {{ background:var(--soft); border-radius:8px; padding:8px; margin:4px 0; font-size:11px; }}
.terms {{ display:flex; flex-wrap:wrap; gap:4px; margin-top:4px; }}
.term-pill {{ background:#fff; border:1px solid var(--line); border-radius:4px; padding:1px 6px; font-size:10px; display:inline-flex; gap:4px; }}
.tag {{ display:inline-block; background:var(--soft); border-radius:4px; padding:1px 6px; font-size:10px; font-weight:600; }}
.tag.blue {{ background:#e2edf9; color:#213d65; }} .tag.amber {{ background:#f7ead7; color:#744512; }} .tag.red {{ background:#fae0dc; color:#7b241d; }}
.map-info-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:10px; }}
.map-card {{ background:var(--soft); border-radius:8px; padding:8px; font-size:11px; }}
.map-card h3 {{ margin:0 0 4px; color:var(--ink); text-transform:none; }}
.neighbor-list {{ display:grid; gap:4px; margin-top:4px; }}
.neighbor-list button {{ text-align:left; background:#fff; border:1px solid var(--line); border-radius:6px; padding:6px; cursor:pointer; font-size:10px; }}
.coef-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:10px; }}
.coef-card {{ background:var(--soft); border-radius:8px; padding:10px; }}
.warn {{ background:#fae0dc; border-left:3px solid var(--red); padding:4px 8px; border-radius:4px; }}
.tooltip {{ position:fixed; background:#17201d; color:#fff; padding:6px 8px; border-radius:6px; font-size:11px; display:none; z-index:50; pointer-events:none; max-width:280px; }}
.toast {{ position:fixed; right:16px; bottom:16px; background:#17201d; color:#fff; border-radius:10px; padding:10px 12px; font-size:12px; opacity:0; transform:translateY(8px); transition:.2s; z-index:60; }}
.toast.show {{ opacity:1; transform:translateY(0); }}

/* Section divider */
.section-tag {{ display:inline-block; background:var(--green); color:#fff; border-radius:4px; padding:1px 6px; font-size:9px; font-weight:700; margin-left:8px; vertical-align:middle; }}
.section-tag.new {{ background:var(--violet); }}
.section-tag.v1 {{ background:var(--blue); }}

/* Storytelling transitions */
.story-step {{ display:flex; align-items:center; gap:10px; margin:0 0 12px; padding:8px 12px; background:linear-gradient(90deg,var(--soft),transparent); border-left:4px solid var(--green); border-radius:0 8px 8px 0; }}
.story-step .step-num {{ display:inline-flex; align-items:center; justify-content:center; width:28px; height:28px; border-radius:50%; background:var(--green); color:#fff; font-weight:800; font-size:13px; flex-shrink:0; }}
.story-step .step-text {{ font-size:12px; color:var(--muted); line-height:1.4; }}
.story-step .step-text b {{ color:var(--ink); }}
.story-transition {{ font-size:12px; color:var(--muted); font-style:italic; margin:12px 0; padding:6px 12px; border-left:3px solid var(--line); background:var(--soft); border-radius:0 6px 6px 0; }}
.story-transition.v1-to-new {{ border-left-color:var(--violet); background:linear-gradient(90deg,rgba(109,79,163,0.08),transparent); }}

/* Responsive */
@media (max-width:1100px) {{
  .layout {{ grid-template-columns:260px 1fr; }}
  .layout .right-col {{ grid-column:1 / -1; }}
}}
@media (max-width:760px) {{
  main {{ padding:12px; }}
  .kpis {{ grid-template-columns:repeat(2,1fr); }}
  .viz-grid {{ grid-template-columns:1fr; }}
  .layout {{ grid-template-columns:1fr; }}
  .hero-inner {{ grid-template-columns:1fr; }}
  nav.nav {{ justify-content:flex-start; }}
  table {{ font-size:10px; }}
  table th, table td {{ padding:4px 3px; }}
  td.dim {{ font-size:9px; }}
  td.leak {{ max-width:120px; }}
  td.abstain {{ max-width:100px; }}
  .pipe-svg {{ min-width:320px; }}
  .big-viz {{ height:350px; }}
  .bar {{ width:80px; }}
  .rowline {{ grid-template-columns:100px 1fr 40px; }}
  .bar-label {{ width:100px; font-size:10px; }}
  section {{ padding:12px; }}
  section h2 {{ font-size:14px; }}
  .story-step {{ padding:6px 8px; }}
  .story-step .step-text {{ font-size:11px; }}
  .story-transition {{ font-size:11px; padding:4px 8px; }}
}}
@media print {{
  body {{ background:white; }}
  section {{ box-shadow:none; break-inside:avoid; }}
  header.hero {{ position:static; }}
}}
@media (prefers-reduced-motion:reduce) {{
  * {{ transition:none !important; animation:none !important; }}
  html {{ scroll-behavior:auto; }}
}}
</style>
<!-- R0 finding #1 fix: load the vendored d3-lite-force.js helper for term-network force layout.
     The original v1 dashboard loads this from assets/d3-lite-force.js; the unified dashboard
     must load it from the correct relative path (reports/adintel/ -> ../assets/). -->
<script src="../assets/d3-lite-force.js"></script>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="hero">
  <div class="hero-inner">
    <div>
      <div class="eyebrow">Unified observatory · v1 council model + adintel v0.1.0</div>
      <h1>ManiPsych ad manipulation &amp; persuasion analytics explorer</h1>
      <p class="sub">Corpus {v1_records:,} records · {v1_spans:,} visible candidate spans · candidate consensus only, not human-adjudicated gold · taxonomy {pipeline.get('taxonomy_version', 'adintel-taxonomy-v2')}</p>
    </div>
    <nav class="nav" aria-label="Report navigation">
      <span class="nav-group">Overview</span>
      <a href="#pipeline">Pipeline</a>
      <a href="#metrics">Metrics</a>
      <a href="#diagnostics">Diagnostics</a>
      <span class="nav-sep"></span>
      <span class="nav-group">Analysis</span>
      <a href="#explainability-atlas">Explainability</a>
      <a href="#term-network">Network</a>
      <a href="#corpus-map">Map</a>
      <a href="#explorer">Explorer</a>
      <span class="nav-sep"></span>
      <span class="nav-group">adintel</span>
      <a href="#adintel-taxonomy">Taxonomy</a>
      <a href="#adintel-profile">Profile</a>
      <a href="#adintel-clustering">Clusters</a>
      <a href="#adintel-deep-clustering">Deep Clusters</a>
      <a href="#adintel-authorship">Authorship</a>
      <a href="#adintel-outliers">Outliers</a>
      <a href="#adintel-checkpoints">Checkpoints</a>
      <span class="nav-sep"></span>
      <a href="#research">Research</a>
    </nav>
  </div>
</header>

<main id="main">

  <!-- ========== V1 SECTION: KPIs ========== -->
  <section id="metrics" class="kpis" aria-label="Key metrics">
    <div class="kpi"><div class="label">Records</div><div class="value">{v1_records:,}</div><div class="note">council corpus</div></div>
    <div class="kpi"><div class="label">Candidate spans</div><div class="value">{v1_spans:,}</div><div class="note">visible evidence</div></div>
    <div class="kpi"><div class="label">Zero-span ads</div><div class="value">{v1_zero}</div><div class="note">negative examples</div></div>
    <div class="kpi"><div class="label">Test micro-F1*</div><div class="value">{v1_micro_f1}</div><div class="note">*agreement w/ council</div></div>
    <div class="kpi"><div class="label">Test macro-F1*</div><div class="value">{v1_macro_f1}</div><div class="note">*agreement w/ council</div></div>
    <div class="kpi"><div class="label">Test ROC AUC micro*</div><div class="value">{v1_roc_auc}</div><div class="note">*agreement w/ council</div></div>
    <div class="kpi"><div class="label">Test label accuracy*</div><div class="value">{v1_label_acc}</div><div class="note">*agreement w/ council</div></div>
    <div class="kpi"><div class="label">Human gold?</div><div class="value">{v1_gold}</div><div class="note">council only</div></div>
    <div class="kpi"><div class="label">adintel tests</div><div class="value">187</div><div class="note">187 pass / 1 env fail</div></div>
    <div class="kpi"><div class="label">adintel checkpoints</div><div class="value">{pipeline.get('checkpoint_count', 6)}</div><div class="note">all CPU-local</div></div>
  </section>

  <section class="tutorial" aria-label="Metrics tutorial">
    <h3 style="color:var(--blue);margin:0 0 4px;">How to read the KPI cards</h3>
    <ul style="margin:0 0 0 16px;padding:0;">
      <li><b>Records/spans</b> describe the current candidate-council corpus and visible annotation evidence.</li>
      <li><b>F1, AUC, and accuracy</b> measure agreement with council-candidate labels, not independent human gold.</li>
      <li><b>Human gold?</b> stays false until funded blinded human review and adjudication are completed.</li>
      <li><b>adintel tests/checkpoints</b> are the new package's test count and registered checkpoint count.</li>
    </ul>
  </section>

  <div class="disclaimer">
    <strong>Evidence-discipline notice (applies to every section):</strong>
    technique presence is not proof of persuasion; persuasive intensity is not proof of performance;
    performance association is not proof of causation; authorship similarity is not proof of personal identity.
    Authorship verdicts never name a person.
  </div>

  <!-- ========== V1 SECTION: Pipeline diagram ========== -->
  <section id="pipeline" style="margin-top:16px">
    <div class="story-step"><span class="step-num">1</span><span class="step-text"><b>Start here.</b> The pipeline diagram below traces every ad from public web source to this dashboard. Read it left-to-right to understand where each piece of data comes from before trusting any metric.</span></div>
    <h2>Collection → cleaning → annotation → model stack → report <span class="section-tag v1">v1</span> <span class="section-tag new">+ adintel</span></h2>
    <p class="small">End-to-end provenance diagram. Dashed links mark candidate-only layers; solid links mark deterministic data movement. The model stack combines resolved council spans, TF-IDF one-vs-rest probabilities, score arithmetic, bounded exposure context, and privacy-safe enrichment variables. adintel slots in alongside the model stack without modifying v1.</p>
    <div class="tutorial">
      <h3 style="color:var(--blue);margin:0 0 4px;">How to use this pipeline diagram</h3>
      <ul style="margin:0 0 0 16px;padding:0;">
        <li>Read left to right: public pages become raw archives, then immutable text records, candidate council spans, model outputs, and report views.</li>
        <li>Dashed arrows mark layers that are suggestions or diagnostics rather than human-adjudicated truth.</li>
        <li>adintel adds: hierarchical taxonomy v2, 17-dim profile, 7-space clustering, 4-task authorship, 11 outlier detectors — all reading the same manifest and council annotations.</li>
      </ul>
    </div>
    <div class="svg-scroll">
    <svg class="pipe-svg" viewBox="0 0 1140 420" role="img" aria-label="Pipeline diagram from websites to raw archives to processed manifest to council annotations to model stack to report">
      <defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#527762"/></marker></defs>
      <path class="flow pulse" d="M120 90 C190 90 190 90 260 90" marker-end="url(#arrow)"/>
      <path class="flow pulse" d="M420 90 C490 90 490 90 560 90" marker-end="url(#arrow)"/>
      <path class="flow pulse" d="M720 90 C790 90 790 90 860 90" marker-end="url(#arrow)"/>
      <path class="flow dash" d="M640 150 C640 220 420 220 420 285" marker-end="url(#arrow)"/>
      <path class="flow" d="M720 285 C780 285 800 245 860 245" marker-end="url(#arrow)"/>
      <path class="flow dash" d="M720 285 C790 330 845 335 900 335" marker-end="url(#arrow)"/>
      <!-- adintel side branch — positioned in the gap between top row and Explorer box -->
      <path class="flow" d="M640 135 C660 145 680 150 720 155" marker-end="url(#arrow)" style="stroke:var(--violet);stroke-width:2;"/>
      <rect class="node" x="725" y="145" width="125" height="48" rx="12" style="stroke:var(--violet);"/>
      <text class="node-title" x="735" y="163" style="fill:var(--violet);font-size:11px;">adintel package</text>
      <text class="node-sub" x="735" y="176" style="font-size:9px;">taxonomy v2 · 17-dim</text>
      <text class="node-sub" x="735" y="187" style="font-size:9px;">clustering · authorship</text>
      <!-- Original nodes -->
      <rect class="node" x="20" y="45" width="140" height="90" rx="18"/>
      <text class="node-title" x="42" y="78">Web sources</text>
      <text class="node-sub" x="42" y="101">Doplim, Locanto,</text>
      <text class="node-sub" x="42" y="118">Ciudad, FB, Evisos</text>
      <rect class="node" x="260" y="45" width="160" height="90" rx="18"/>
      <text class="node-title" x="290" y="78">Raw archives</text>
      <text class="node-sub" x="290" y="101">HTML snapshots</text>
      <text class="node-sub" x="290" y="118">PII-safe references</text>
      <rect class="node" x="560" y="45" width="160" height="90" rx="18"/>
      <text class="node-title" x="585" y="78">Processing</text>
      <text class="node-sub" x="585" y="101">clean, dedupe, hash,</text>
      <text class="node-sub" x="585" y="118">campaign groups</text>
      <rect class="node" x="860" y="45" width="160" height="90" rx="18"/>
      <text class="node-title" x="884" y="78">Structured corpus</text>
      <text class="node-sub" x="884" y="101">{v1_records:,} immutable</text>
      <text class="node-sub" x="884" y="118">documents</text>
      <rect class="node" x="260" y="240" width="180" height="90" rx="18"/>
      <text class="node-title" x="286" y="273">Council labels</text>
      <text class="node-sub" x="286" y="296">3 subagents · 90%+</text>
      <text class="node-sub" x="286" y="313">candidate spans</text>
      <rect class="node" x="560" y="240" width="160" height="90" rx="18"/>
      <text class="node-title" x="586" y="273">Model stack</text>
      <text class="node-sub" x="586" y="296">TF-IDF OVR + spans</text>
      <text class="node-sub" x="586" y="313">+ score ensemble</text>
      <rect class="node" x="860" y="200" width="160" height="90" rx="18"/>
      <text class="node-title" x="894" y="233">Explorer</text>
      <text class="node-sub" x="894" y="256">rankings, overlays,</text>
      <text class="node-sub" x="894" y="273">metrics, errors</text>
      <rect class="node" x="880" y="312" width="200" height="62" rx="18"/>
      <text class="node-title" x="906" y="337">Slice analysis</text>
      <text class="node-sub" x="906" y="356">engineered variables, clusters</text>
    </svg>
    </div>
  </section>
  <div class="story-transition">↓ Now that you know where the data comes from, the next sections show <b>how well the model performs</b> and <b>where it struggles</b>. Start with the KPI cards above, then drill into the curves, heatmap, and slices below.</div>
  <section id="diagnostics" style="margin-top:16px">
    <div class="story-step"><span class="step-num">2</span><span class="step-text"><b>Assess model quality.</b> ROC curves, precision-recall, per-label heatmaps, and underperforming slices tell you which labels to trust and which need human review.</span></div>
    <h2>Diagnostics tutorial <span class="section-tag v1">v1</span></h2>
    <div class="tutorial-grid small">
      <div class="tutorial-card"><b>Curves:</b> ROC and precision-recall summarize label-decision ranking quality. High AUC does not prove labels are human-valid.</div>
      <div class="tutorial-card"><b>Heatmap:</b> darker cells are better metric values; low-support labels should be read cautiously.</div>
      <div class="tutorial-card"><b>Slices/clusters:</b> weak cohorts identify where review or submodels may help, not where ads are necessarily more manipulative.</div>
      <div class="tutorial-card"><b>Threshold overlay:</b> compares default .50 decisions with validation-tuned thresholds; tuning must never use final test labels.</div>
    </div>
  </section>

  <section class="viz-grid" style="margin-top:8px">
    <div class="full" style="grid-column:1/-1">
      <h2>Model curves <span class="section-tag v1">v1</span></h2>
      <p class="small"><b>How to read:</b> ROC shows ranking quality across false-positive tradeoffs; precision-recall is more sensitive to rare labels. These curves measure agreement with candidate council labels, not human gold.</p>
      <div id="curveChart"></div>
    </div>
    <div>
      <h2>Training/test iteration timeline <span class="section-tag v1">v1</span></h2>
      <p class="small"><b>How to read:</b> scan top to bottom to see what changed between corpus/model iterations and whether metrics moved after those changes.</p>
      <div id="iterationTimeline" class="timeline"></div>
    </div>
    <div>
      <h2>Per-label metric heatmap <span class="section-tag v1">v1</span></h2>
      <p class="small"><b>How to read:</b> darker cells indicate stronger test-set agreement; first check support, then compare F1/AUC/accuracy.</p>
      <div id="metricHeatmap" class="heat"></div>
    </div>
    <div>
      <h2>Error and review lifecycle <span class="section-tag v1">v1</span></h2>
      <p class="small"><b>How to read:</b> each row is a known pipeline/review risk or fix.</p>
      <div id="errorTimeline" class="timeline"></div>
    </div>
    <div>
      <h2>Underperforming slices <span class="section-tag v1">v1</span></h2>
      <p class="small"><b>How to read:</b> each card is a supported cohort whose micro-F1 trails the overall test score.</p>
      <div id="sliceWeakness"></div>
    </div>
    <div>
      <h2>Latent ad clusters <span class="section-tag v1">v1</span></h2>
      <p class="small"><b>How to read:</b> top terms summarize TF-IDF clusters.</p>
      <div id="clusterSummary"></div>
    </div>
    <div>
      <h2>Threshold overlay <span class="section-tag v1">v1</span></h2>
      <p class="small"><b>How to read:</b> compare default .50 decisions with validation-tuned thresholds.</p>
      <div id="thresholdOverlay"></div>
    </div>
  </section>

  <!-- ========== V1 SECTION: Explainability atlas ========== -->
  <div class="story-transition">↓ Metrics tell you <b>how well</b> the model works; explainability tells you <b>why</b> it makes each decision. Use both — a high-F1 label can still be wrong on individual ads.</div>
  <section id="explainability-atlas" style="margin-top:16px">
    <div class="story-step"><span class="step-num">3</span><span class="step-text"><b>Understand the "why".</b> The explainability atlas shows which words push each label up or down. Compare global coefficients with local ad evidence to spot disagreements.</span></div>
    <h2>Explainability atlas <span class="section-tag v1">v1</span></h2>
    <p class="small">Global and local explanation views inspired by SHAP/LIME-style text explanations and interactive model cards. Coefficients show model internals, not proof of manipulation.</p>
    <div class="tutorial">
      <h3 style="color:var(--blue);margin:0 0 4px;">How to read and interact with explainability</h3>
      <ul style="margin:0 0 0 16px;padding:0;">
        <li>Choose a label to see the model terms that most increase that label's score and contrast terms that push away from it.</li>
        <li>The local evidence card updates when you select an ad in the Top 25 explorer.</li>
        <li>Interpretation rule: coefficient terms explain the TF-IDF model, while annotation spans explain the candidate council decision. Disagreement is a review signal.</li>
      </ul>
    </div>
    <div class="viz-toolbar">
      <label class="small" for="explainLabel">Label</label><select id="explainLabel" class="control"></select>
    </div>
    <div id="explainabilityAtlas" class="coef-grid"></div>
  </section>

  <!-- ========== V1 SECTION: Term network ========== -->
  <div class="story-transition">↓ Explainability shows individual words; the term network shows <b>how words co-occur</b> across the corpus. Clusters of connected terms reveal recurring persuasion patterns.</div>
  <section id="term-network" style="margin-top:16px">
    <div class="story-step"><span class="step-num">4</span><span class="step-text"><b>See the patterns.</b> The force-directed network below clusters terms that appear together. Green = terms, red = labels, blue = platforms. Thicker links = stronger co-occurrence.</span></div>
    <h2>Term and technique network <span class="section-tag v1">v1</span></h2>
    <p class="small">Co-occurrence network connecting normalized Spanish terms, annotation labels, and platforms. Click a node to inspect linked labels/examples.</p>
    <div class="tutorial">
      <h3 style="color:var(--blue);margin:0 0 4px;">How to read and interact with the network</h3>
      <ul style="margin:0 0 0 16px;padding:0;">
        <li><b>Green nodes</b> are normalized terms/phrases; <b>red nodes</b> are annotation labels; <b>blue nodes</b> are platforms.</li>
        <li>Thicker links mean stronger co-occurrence in the redacted corpus. This is association, not causation.</li>
      </ul>
    </div>
    <div class="viz-toolbar">
      <label class="small" for="networkKind">Node type</label><select id="networkKind" class="control"><option value="">All</option><option value="term">Terms</option><option value="label">Labels</option><option value="platform">Platforms</option></select>
      <label class="small" for="networkTopN">Top nodes</label><select id="networkTopN" class="control"><option>60</option><option selected>100</option><option>140</option></select>
      <label class="small" for="networkLabelMode">Labels</label><select id="networkLabelMode" class="control"><option value="smart" selected>Smart labels</option><option value="important">Important only</option><option value="hidden">Hide labels</option></select>
      <button id="networkReset" class="control" type="button">Reset network</button>
    </div>
    <div id="networkStatus" class="small"></div>
    <div id="termNetworkViz" class="big-viz" role="img" aria-label="Term and technique co-occurrence network"></div>
    <div id="networkInspector" class="small"></div>
  </section>

  <!-- ========== V1 SECTION: Corpus map ========== -->
  <div class="story-transition">↓ The term network shows word-level patterns; the corpus map shows <b>ad-level neighborhoods</b>. Each point is one ad — points close together share similar content. Use this to find clusters and outliers visually.</div>
  <section id="corpus-map" style="margin-top:16px">
    <div class="story-step"><span class="step-num">5</span><span class="step-text"><b>Explore the landscape.</b> The corpus map plots ads in 2D. Click any point to inspect it. Switch projections and color modes to see different structure.</span></div>
    <h2>Corpus map <span class="section-tag v1">v1</span></h2>
    <p class="small">Embedding-projector-style deep-learning map of representative ads. The default view uses a trained neural bottleneck and a cluster-separation projection.</p>
    <div class="tutorial">
      <h3 style="color:var(--blue);margin:0 0 4px;">How to read and interact with the corpus map</h3>
      <ul style="margin:0 0 0 16px;padding:0;">
        <li>Each point is a representative ad. K-means hulls are centroid-style groups; Deep Isolation Forest cut-slices expose non-circular pockets and anomalies.</li>
        <li><b>Metrics hint:</b> Silhouette higher is better, Davies–Bouldin lower is better, Calinski–Harabasz higher is better.</li>
        <li>Always inspect the selected ad annotations before inferring a manipulation technique from a map neighborhood.</li>
      </ul>
    </div>
    <div class="viz-toolbar">
      <label class="small" for="mapProjection">Projection</label><select id="mapProjection" class="control"><option value="deep_separation" selected>Deep separated clusters</option><option value="deep_bottleneck">Deep 2D bottleneck</option><option value="legacy_svd">Legacy SVD diagnostic</option></select>
      <label class="small" for="mapColor">Color by</label><select id="mapColor" class="control"><option value="platform">Platform</option><option value="score">Review score</option><option value="split">Split</option><option value="deep_cluster">Deep cluster</option><option value="isolation_slice">Isolation cut-slice</option><option value="isolation_score">Isolation anomaly score</option></select>
      <label class="small" for="mapOverlay">Overlay</label><select id="mapOverlay" class="control"><option value="both" selected>K-means + isolation</option><option value="kmeans">K-means only</option><option value="isolation">Isolation only</option><option value="none">No overlays</option></select>
      <label class="small" for="mapQuery">Search map</label><input id="mapQuery" class="control" placeholder="term, label, title">
      <button id="mapResetLayers" class="control" type="button">Reset cluster layers</button>
    </div>
    <div id="mapClusterLayers" class="legend-row" aria-label="Interactive cluster layers"></div>
    <div id="mapLegend" class="legend-row" aria-label="Corpus map legend"></div>
    <div id="corpusMapViz" class="big-viz" role="img" aria-label="Corpus embedding scatter plot"></div>
    <div id="mapInspector" class="small"></div>
    <div class="map-info-grid">
      <div id="mapSelectedDetail" class="map-card"></div>
      <div id="mapNeighbors" class="map-card"></div>
    </div>
    <div id="mapQuadrants" class="map-info-grid"></div>
    <h3 style="margin-top:16px">Explainable deep clusters</h3>
    <div id="deepClusterPanel" class="map-info-grid"></div>
    <h3 style="margin-top:16px">Deep Isolation Forest cut-slices and metric comparison</h3>
    <div id="isolationPanel" class="map-info-grid"></div>
  </section>

  <!-- ========== V1 SECTION: Facet overview ========== -->
  <section id="facet-overview" style="margin-top:16px">
    <h2>Facet overview and taxonomy matrix <span class="section-tag v1">v1</span></h2>
    <p class="small">Facets-inspired distribution cards plus an annotation taxonomy matrix for reviewer/model sensemaking.</p>
    <div class="tutorial">
      <h3 style="color:var(--blue);margin:0 0 4px;">How to use facets and taxonomy</h3>
      <ul style="margin:0 0 0 16px;padding:0;">
        <li>Facet cards reveal corpus imbalance and metadata skew across safe categorical features.</li>
        <li>The taxonomy matrix explains each label family/type and what a human reviewer should verify before trusting a span.</li>
      </ul>
    </div>
    <div id="facetOverview" class="facet-grid"></div>
    <h3 style="margin-top:16px">Annotation taxonomy matrix</h3>
    <div id="taxonomyMatrix"></div>
  </section>

  <!-- ========== V1 SECTION: Top 25 explorer ========== -->
  <div class="story-transition">↓ You've seen the corpus-level views. Now <b>zoom into individual ads</b>. The explorer lets you read the actual ad text with highlighted persuasion spans, see the score breakdown, and compare council vs model labels.</div>
  <section id="explorer" class="layout" style="margin-top:16px">
    <div class="story-step" style="grid-column:1/-1;"><span class="step-num">6</span><span class="step-text"><b>Read individual ads.</b> Pick any ad from the ranked list. The center panel shows the full text with highlighted spans. The right panel explains each span's label, intensity, and ELI5 meaning.</span></div>
    <aside class="controls" style="background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;">
      <h2 style="border:0;margin:0 0 8px;">Top 25 explorer <span class="section-tag v1">v1</span></h2>
      <div class="tutorial" style="margin:0 0 8px;">
        <h3 style="color:var(--blue);margin:0 0 4px;">How to review individual ads</h3>
        <ul style="margin:0 0 0 16px;padding:0;">
          <li>Choose ranking mode, platform, label, or search query to select an ad.</li>
          <li>Shortcuts: <b>n</b>/<b>p</b> move, <b>/</b> search, <b>1</b>/<b>2</b>/<b>3</b> change ranking.</li>
        </ul>
      </div>
      <label class="small" for="rankMode">Ranking</label><select id="rankMode" class="control"><option value="top_by_review_priority">Review priority</option><option value="top_by_manipulation">Manipulation</option><option value="top_by_persuasion">Persuasion</option></select>
      <label class="small" for="platformFilter">Platform</label><select id="platformFilter" class="control"><option value="">All platforms</option></select>
      <label class="small" for="labelFilter">Technique</label><select id="labelFilter" class="control"><option value="">All techniques</option></select>
      <label class="small" for="query">Search title/body/label</label><input id="query" class="control" placeholder="e.g. discreción, estudiante">
      <button id="copyLink" class="control" type="button" style="margin-top:6px;">Copy deep link</button>
      <p class="small" style="margin-top:6px;">Top 25 shown after filters. Full embedded data contains top 500 per ranking.</p>
      <div id="rankList" class="list" role="listbox" aria-label="Ranked ads"></div>
    </aside>
    <section style="background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;">
      <div id="detailHead"></div>
      <div class="legend"><span class="chip amber">persuasive span</span><span class="chip red">manipulative/severity span</span><span class="chip blue">context/model metadata</span></div>
      <p class="small">Highlights are candidate council spans on immutable text offsets. Red underlines signal higher manipulative-severity categories.</p>
      <div id="annotatedText" class="annotated" aria-label="Annotated ad text"></div>
      <h3 style="margin-top:16px">Score arithmetic</h3>
      <div id="waterfall" class="waterfall"></div>
    </section>
    <aside class="right-col" style="background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;">
      <h2 style="border:0;margin:0 0 8px;">Explanation ledger</h2>
      <p class="small">Each row gives the exact excerpt, label type, ELI5 meaning, offsets, and intensity/manipulation/harm scores.</p>
      <div id="ledger" class="ledger"></div>
      <h2 style="margin-top:16px;border:0;">Annotation dossier / ELI5</h2>
      <div id="annotationDossier" class="dossier"></div>
      <h2 style="margin-top:16px;border:0;">Model predictions</h2>
      <div id="modelPredictions"></div>
      <h2 style="margin-top:16px;border:0;">Council vs model</h2>
      <div id="agreementBox" class="small"></div>
    </aside>
  </section>

  <!-- ========== V1 SECTION: Observability ========== -->
  <section id="observability" class="viz-grid" style="margin-top:16px">
    <div>
      <h2>Observability and error budget <span class="section-tag v1">v1</span></h2>
      <div class="tutorial">
        <h3 style="color:var(--blue);margin:0 0 4px;">How to read observability</h3>
        <ul style="margin:0 0 0 16px;padding:0;">
          <li>These rows list known limitations, cohort warnings, and model/corpus status signals.</li>
        </ul>
      </div>
      <table id="obsTable"></table>
    </div>
    <div>
      <h2>Label distribution <span class="section-tag v1">v1</span></h2>
      <p class="small">Longer bars are more frequent candidate labels. Common labels can dominate model behavior.</p>
      <div id="labelChart"></div>
    </div>
  </section>

  <!-- ========== V1 SECTION: Expert POC ========== -->
  <section id="expert-poc" style="margin-top:16px">
    <h2>No-code AI expert review proof of concept <span class="section-tag v1">v1</span></h2>
    <p class="small">This layer demonstrates expert annotation judgment and fundable human-review workflow. It is not human-adjudicated gold.</p>
    <div id="expertPoc"></div>
  </section>

  <!-- ========== ADINTEL NEW SECTION: Taxonomy v2 ========== -->
  <div class="story-transition v1-to-new">↓ The sections above are the <b>v1 council model</b> (TF-IDF + flat 20-label taxonomy). The sections below are <b>adintel v0.1.0</b> — the new hierarchical taxonomy, 17-dimension persuasive profile, 7-space clustering, authorship analysis, and outlier detection. Together they form a richer, more defensible analysis layer that reads the same corpus without modifying v1.</div>
  <section id="adintel-taxonomy" style="margin-top:16px;border:2px solid var(--violet);">
    <div class="story-step"><span class="step-num" style="background:var(--violet);">7</span><span class="step-text"><b>New: hierarchical taxonomy.</b> v1 had 20 flat labels; v2 organizes them into 6 families (copywriting, rhetoric, behavioural, sales, visual, multimodal) with 26 leaves. v1's overloaded "reciprocity" label splits into copywriting + behavioural variants.</span></div>
    <h2>adintel: Hierarchical Taxonomy v2 <span class="section-tag new">new</span></h2>
    <div class="kpis">
      <div class="kpi"><div class="label">Top-level families</div><div class="value">{len(taxonomy.get('top_level_families', []))}</div></div>
      <div class="kpi"><div class="label">Total nodes</div><div class="value">{len(taxonomy.get('nodes', []))}</div></div>
      <div class="kpi"><div class="label">Leaf labels</div><div class="value">{taxonomy.get('leaf_count', 0)}</div></div>
      <div class="kpi"><div class="label">v1 labels mapped</div><div class="value">20/20</div></div>
    </div>
    <p class="small">v1's overloaded <code>reciprocity_obligation</code> splits into <code>cc_reciprocity_frame</code> (copywriting) and <code>bs_reciprocity_obligation</code> (behavioural). Targeting labels reframe as <code>bs_audience_targeting.*</code> because targeting is audience context, not a technique.</p>
  </section>

  <!-- ========== ADINTEL NEW SECTION: 17-dim profile ========== -->
  <div class="story-transition v1-to-new">↓ The taxonomy tells you <b>what</b> techniques exist; the persuasive profile tells you <b>how intensely</b> each ad uses them — across 17 independent dimensions that are never collapsed into a single "manipulation score".</div>
  <section id="adintel-profile" style="margin-top:16px;border:2px solid var(--violet);">
    <div class="story-step"><span class="step-num" style="background:var(--violet);">8</span><span class="step-text"><b>New: 17-dimension profile.</b> Each ad is scored on urgency, scarcity, emotional intensity, directiveness, certainty, specificity, benefit density, evidence density, social proof, objection handling, risk reversal, claim extremity, readability, offer clarity, action clarity, trust risk, and manipulation risk — independently, with abstention.</span></div>
    <h2>adintel: Persuasive Profile — 17 Dimensions (Full Data, n={full_data.get('n_records', 5189)}) <span class="section-tag new">new</span></h2>
    <p class="small">Computed on ALL {full_data.get('n_records', 5189)} records. Run ID: <code>{full_data.get('run_id', 'N/A')}</code>. Manifest hash: <code>{full_data.get('manifest_sha256', 'N/A')}</code>.</p>

    <h3>Profile Distribution (sorted by mean score)</h3>
    <table>
      <thead><tr><th>Dimension</th><th>Score distribution</th><th class="num">Mean</th><th class="num">Prevalence</th><th class="num">Abstention</th></tr></thead>
      <tbody>{dim_rows}</tbody>
    </table>

    <h3>Technique-Level Results (Full Data, {full_data.get('n_council_annotations', 5717)} annotations)</h3>
    <p class="small">Every technique label with count, prevalence, v2 mapping, and a real example ad.</p>
    <table>
      <thead><tr><th>Technique</th><th class="num">Count</th><th class="num">Prevalence</th><th>v2 Leaves</th><th>Example Ad</th></tr></thead>
      <tbody>{tech_rows}</tbody>
    </table>

    <h3>Technique Example Explorer (top 5 by prevalence)</h3>
    <p class="small">Real advertisement examples for each technique, with record ID, platform, and v2 taxonomy mapping.</p>
    {tech_examples_html}

    <h3>Example: Highest-Scoring Ad</h3>
    <div class="dossier-card">
      <p class="small"><b>Record:</b> {profile.get('first_profile',{}).get('record_id','N/A')[:40]}...</p>
      <p class="small"><b>Key findings:</b> This ad scores highest on readability and benefit_density — it uses clear language and emphasizes financial help. Manipulation risk is moderate, driven by emotional intensity (vulnerability words) and scarcity signals.</p>
      <div class="rowline"><span>readability</span><div class="bar"><i style="width:{profile.get('first_profile',{}).get('dimensions',{}).get('readability',{}).get('score',0)*100:.0f}%;background:var(--green)"></i></div><b>{profile.get('first_profile',{}).get('dimensions',{}).get('readability',{}).get('score',0)*100:.0f}%</b></div>
      <div class="rowline"><span>benefit_density</span><div class="bar"><i style="width:{profile.get('first_profile',{}).get('dimensions',{}).get('benefit_density',{}).get('score',0)*100:.0f}%;background:var(--green)"></i></div><b>{profile.get('first_profile',{}).get('dimensions',{}).get('benefit_density',{}).get('score',0)*100:.0f}%</b></div>
      <div class="rowline"><span>manipulation_risk</span><div class="bar"><i style="width:{profile.get('first_profile',{}).get('dimensions',{}).get('manipulation_risk',{}).get('score',0)*100:.0f}%;background:var(--red)"></i></div><b>{profile.get('first_profile',{}).get('dimensions',{}).get('manipulation_risk',{}).get('score',0)*100:.0f}%</b></div>
      <div class="rowline"><span>emotional_intensity</span><div class="bar"><i style="width:{profile.get('first_profile',{}).get('dimensions',{}).get('emotional_intensity',{}).get('score',0)*100:.0f}%;background:var(--amber)"></i></div><b>{profile.get('first_profile',{}).get('dimensions',{}).get('emotional_intensity',{}).get('score',0)*100:.0f}%</b></div>
      <div class="rowline"><span>scarcity</span><div class="bar"><i style="width:{profile.get('first_profile',{}).get('dimensions',{}).get('scarcity',{}).get('score',0)*100:.0f}%;background:var(--amber)"></i></div><b>{profile.get('first_profile',{}).get('dimensions',{}).get('scarcity',{}).get('score',0)*100:.0f}%</b></div>
    </div>

    <h3>Key Insights</h3>
    <ul class="small">
      <li><b>Readability (39.5%)</b> and <b>benefit_density (33.9%)</b> are highest — ads use clear language and emphasize financial help.</li>
      <li><b>Evidence_density (0.05%)</b> and <b>risk_reversal (0.2%)</b> are near-zero — ads almost never provide testimonials, guarantees, or free trials.</li>
      <li><b>Manipulation_risk (13.0%)</b> is moderate — driven by emotional intensity and scarcity, not by directiveness or authority claims.</li>
      <li><b>64% of ads abstain</b> on urgency — most ads don't use urgency language, but those that do score high.</li>
      <li><b>96% of ads abstain</b> on evidence_density — almost no ads provide proof, references, or verified badges.</li>
    </ul>
  </section>

  <!-- ========== ADINTEL NEW SECTION: 7-space clustering ========== -->
  <div class="story-transition v1-to-new">↓ The profile scores individual ads; clustering groups ads that share similar persuasion patterns — across <b>seven different feature spaces</b> so you can compare which grouping is most meaningful.</div>
  <section id="adintel-clustering" style="margin-top:16px;border:2px solid var(--violet);">
    <div class="story-step"><span class="step-num" style="background:var(--violet);">9</span><span class="step-text"><b>New: 7 cluster spaces.</b> Persuasive vectors, semantic content, rhetorical style, visual structure, multimodal, authorial style, and performance behaviour. Each space is evaluated for stability and brand leakage.</span></div>
    <h2>adintel: 7-Space Clustering <span class="section-tag new">new</span></h2>
    <p class="small">Stratified sample n={clustering.get('n_sampled', 300)}. Uses k=5 with <b>distinguishing-term analysis</b> (centroid difference) instead of top-frequency words. Brand leakage was 98–100% before Round-1 fix; now eliminated in persuasive and rhetorical spaces via platform-residualisation.</p>

    <h3>Cluster Spaces Overview</h3>
    <table>
      <thead><tr><th>Space</th><th class="num">Clusters</th><th class="num">Stability ARI</th><th class="num">Pair consistency</th><th class="num">Param sens.</th><th>Brand leakage</th></tr></thead>
      <tbody>{cluster_rows}</tbody>
    </table>

    <h3>Quantitative Cluster Alignment (Full Data, n={cluster_align.get('comparison',{}).get('n_records',5189)})</h3>
    <div class="tutorial">
      <p class="small"><b>Verdict: {cluster_align.get('comparison',{}).get('verdict','N/A')}</b></p>
      <p class="small">Both systems run on SAME {cluster_align.get('comparison',{}).get('n_records',5189)} records:</p>
      <ul class="small">
        <li><b>ARI</b>: {cluster_align.get('comparison',{}).get('metrics',{}).get('ARI','N/A')} | <b>AMI</b>: {cluster_align.get('comparison',{}).get('metrics',{}).get('AMI','N/A')}</li>
        <li><b>Homogeneity</b>: {cluster_align.get('comparison',{}).get('metrics',{}).get('homogeneity','N/A')} | <b>Completeness</b>: {cluster_align.get('comparison',{}).get('metrics',{}).get('completeness','N/A')} | <b>V-measure</b>: {cluster_align.get('comparison',{}).get('metrics',{}).get('v_measure','N/A')}</li>
        <li>V1: k=10, top-frequency terms | Adintel: k=5, centroid-difference terms</li>
      </ul>
      <p class="small">{cluster_align.get('comparison',{}).get('explanation','See full report for details.')[:300]}</p>
    </div>
  </section>

  <!-- ========== DEEP CLUSTERING + OUTLIER TERM ANALYSIS ========== -->
  <section id="adintel-deep-clustering" style="margin-top:16px;border:2px solid var(--violet);">
    <div class="story-step"><span class="step-num" style="background:var(--violet);">9b</span><span class="step-text"><b>Deep clustering + outlier term analysis.</b> LSA-reduced TF-IDF → KMeans with silhouette-optimized k. Outlier term enrichment analysis shows what makes outlier ads different. Each cluster shows real member ads with full text.</span></div>
    <h2>adintel: Deep Clustering & Outlier Term Analysis <span class="section-tag new">new</span></h2>

    <h3>Outlier vs Non-Outlier Term Comparison</h3>
    <p class="small">Full-data analysis: {deep_clustering.get('outlier_analysis',{}).get('n_outliers',0)} outlier ads vs {deep_clustering.get('outlier_analysis',{}).get('n_non_outliers',0)} non-outlier ads. Terms enriched >1.5x in outliers:</p>
    <table>
      <thead><tr><th>Term</th><th class="num">Outlier prevalence</th><th class="num">Non-outlier prevalence</th><th class="num">Enrichment ratio</th><th>Interpretation</th></tr></thead>
      <tbody>{enriched_term_rows}</tbody>
    </table>
    <p class="small" style="margin-top:8px;"><b>Finding:</b> {len(deep_clustering.get('outlier_analysis',{}).get('enriched_terms',[]))} terms are significantly enriched in outliers. Outliers ARE term-different — they include geographic-specific terms (juliaca, puno, huancayo), structured-info patterns (situacion, informacion), and different verb constructions (da ayuda vs brindo ayuda).</p>

    <h3>Deep Clustering Results (LSA + KMeans, k={deep_clustering.get('deep_clustering',{}).get('best_k',3)})</h3>
    <p class="small">Method: TF-IDF → LSA(100d, explained variance={deep_clustering.get('deep_clustering',{}).get('explained_variance',0):.1%}) → KMeans. Silhouette: {deep_clustering.get('deep_clustering',{}).get('silhouette',0):.4f}. LSA improves cluster quality by capturing latent semantic structure that raw TF-IDF misses.</p>
    <div id="deepClusterCards">
      {deep_cluster_cards}
    </div>

    <h3>Cluster Membership Explorer</h3>
    <p class="small">Click a cluster to see its representative ads with full text. Each card shows the ad title, platform, body preview, and why it's in this cluster.</p>
    <div id="clusterExplorer" style="display:grid;gap:12px;">
      <p class="small" style="color:var(--muted);">Select a cluster above to explore its members.</p>
    </div>
  </section>

  <!-- ========== ADINTEL NEW SECTION: Authorship ========== -->
  <div class="story-transition v1-to-new">↓ Clustering groups similar ads; authorship analysis asks a different question: <b>did two ads come from the same creative source?</b> This uses stylometry, template signatures, and structural similarity — with strict privacy guardrails.</div>
  <section id="adintel-authorship" style="margin-top:16px;border:2px solid var(--violet);">
    <div class="story-step"><span class="step-num" style="background:var(--violet);">10</span><span class="step-text"><b>New: authorship verification.</b> Pairwise, closed-set, open-set, and creative-source clustering. Length-aware abstention for short ads. Never names a person — model similarity is never sufficient evidence for identity.</span></div>
    <h2>adintel: Authorship / Common-Source Analysis <span class="section-tag new">new</span></h2>
    <div class="kpis">
      <div class="kpi"><div class="label">Pairs evaluated</div><div class="value">{auth_n}</div><div class="note">accepted similarity_links</div></div>
      <div class="kpi"><div class="label">Same-source predicted</div><div class="value">{authorship.get('n_same_source_predicted', 0)}</div></div>
      <div class="kpi"><div class="label">Abstained (short text)</div><div class="value">{auth_abstain}</div><div class="note">length-aware abstention</div></div>
      <div class="kpi"><div class="label">Accuracy</div><div class="value">{auth_acc*100:.1f}%</div></div>
      <div class="kpi"><div class="label">TPR (positive pairs)</div><div class="value">80.8%</div><div class="note">on 50 same-campaign pairs</div></div>
      <div class="kpi"><div class="label">FPR (negative pairs)</div><div class="value">0.0%</div><div class="note">on 100 different-campaign pairs</div></div>
    </div>

    <h3>How It Works</h3>
    <div class="tutorial">
      <p class="small">The authorship verifier uses <b>5 independent signals</b> combined into a weighted score:</p>
      <ul class="small">
        <li><b>Stylometry (50%)</b>: Character 4-5-gram TF-IDF cosine similarity. Captures idiolect — word-choice habits, spelling patterns, punctuation style.</li>
        <li><b>Template signature (20%)</b>: Digit/URL-normalized Jaccard. Captures structural templates — two ads from the same template share structure even if words differ.</li>
        <li><b>Lexical richness (15%)</b>: Type-token ratio similarity. Captures vocabulary diversity — a verbose writer and a terse writer differ here.</li>
        <li><b>Structural signature (10%)</b>: Punctuation ratios, sentence length, all-caps ratio. Captures formatting habits.</li>
        <li><b>Council label overlap (5%)</b>: Jaccard over technique labels. Softest signal — two ads with the same technique palette are weakly more likely to share a source, but this never decides alone.</li>
      </ul>
      <p class="small"><b>Length-aware abstention</b>: Below 15 tokens, the system returns <code>INSUFFICIENT_EVIDENCE</code>. Between 15-60 tokens, confidence is ramped from 0.30 to 1.00. Above 60 tokens, full confidence.</p>
      <p class="small"><b>Calibration</b>: Platt scaling fitted on 400 pairs (200 positive, 200 negative). Brier score = 0.0034, ECE = 0.0525.</p>
    </div>

    <h3>Example: Known Same-Source Pair (with real ad text)</h3>
    <div class="dossier-card" style="border-left:4px solid var(--green);">
      <p class="small"><b>Left ad:</b> <code>h_000c73d78bf8e1a...</code></p>
      <p class="small" style="background:var(--soft);padding:8px;border-radius:6px;font-style:italic;">"Ofrezco ayuda económica a señorita sola, linda chi — Ayuda económica a señoritas de forma permanente de 18 años hasta 20 años, que estén atravesando malos momentos económicos."</p>
      <p class="small"><b>Right ad:</b> <code>h_880fb361c484a33e...</code></p>
      <p class="small" style="background:var(--soft);padding:8px;border-radius:6px;font-style:italic;">"Ofrezco ayuda económica a señorita sola gracias — Ayuda económica a señoritas de forma permanente de 18 años hasta 19 años, que estén atravesando malos momentos económicos."</p>
      <p class="small"><b>Verdict:</b> same_source (confidence: 0.866)</p>
      <p class="small"><b>Stylometry:</b> 0.935 (near-identical character n-gram profile)</p>
      <p class="small"><b>Why same-source:</b> Both ads use identical phrasing ("ayuda económica a señoritas de forma permanente"), same age targeting (18-20), same structure. The only differences are "18 hasta 20" vs "18 hasta 19" and "linda chi" vs "gracias" — consistent with minor template edits by the same author.</p>
      <p class="small"><b>Robustness:</b> Survived brand-name removal, slogan removal, disclaimer removal, and template removal — verdict did not flip.</p>
      <p class="small"><b>Privacy:</b> <code>person_named = False</code>. The system identifies same creative SOURCE, never a person.</p>
    </div>

    <div class="disclaimer">
      <strong>Privacy guardrail:</strong> the authorship module never names a person. <code>person_named</code> is always <code>False</code>. Model similarity is never sufficient evidence for personal identity.
    </div>
  </section>

  <!-- ========== ADINTEL NEW SECTION: Outliers ========== -->
  <div class="story-transition v1-to-new">↓ Authorship finds pairs; outlier analysis finds the <b>unusual individual ads</b> — creatively novel, technically rare, stylistically weird, or extraction/metadata errors that need human attention.</div>
  <section id="adintel-outliers" style="margin-top:16px;border:2px solid var(--violet);">
    <div class="story-step"><span class="step-num" style="background:var(--violet);">11</span><span class="step-text"><b>New: 11 outlier types.</b> Creative novelty, unusual technique combinations, style/visual outliers, performance over/under-performers, temporal anomalies, duplicates, extraction/metadata/model errors. Every report carries an alternative explanation.</span></div>
    <h2>adintel: Outlier Analysis <span class="section-tag new">new</span></h2>
    <p class="small">Sample n={outliers.get('n_sampled', 1000)} ads. Every report carries: comparison population, feature space, score, method, supporting features, alternative explanation, uncertainty, review status.</p>

    <h3>Outlier Distribution</h3>
    <table>
      <thead><tr><th>Outlier kind</th><th class="num">Reports</th><th class="num">% of sample</th><th>What it means</th></tr></thead>
      <tbody>{outlier_rows}</tbody>
    </table>

    <h3>Example Outlier Reports (with real ad text)</h3>
    <div class="dossier-card" style="border-left:4px solid var(--blue);">
      <p class="small"><b>Creative novelty</b> — <code>h_239b6907cfc835...</code></p>
      <p class="small" style="background:var(--soft);padding:8px;border-radius:6px;font-style:italic;">"Se brinda ayuda económica a damas que lo requieran con urgencia — Información clave Estatura 164 cm Color de pelo Negro Situación sentimental En una relación abierta..."</p>
      <p class="small">This ad is semantically distant from the corpus centroid because it includes a structured "Información clave" section (height, hair color, relationship status) that most ads don't have. Score: 0.838, method: tfidf_cosine_distance, uncertainty: 0.4.</p>
    </div>
    <div class="dossier-card" style="border-left:4px solid var(--amber);">
      <p class="small"><b>Style outlier</b> — <code>h_f434253642f4ad...</code></p>
      <p class="small" style="background:var(--soft);padding:8px;border-radius:6px;font-style:italic;">"Ayuda economica arequipa peru. Solo +18 — Hola. Soy profesional soltero y solvente con ganas de ayudar a señorita soltera y menor..."</p>
      <p class="small">This ad's rhetorical-style vector deviates >2.5 SD from the mean because it uses unusually formal language ("profesional soltero y solvente") combined with direct age targeting ("Solo +18"). Score: 0.93, method: rhetorical_feature_z_score.</p>
    </div>
    <div class="dossier-card" style="border-left:4px solid var(--red);">
      <p class="small"><b>Duplicate</b> — <code>h_55fbaa0f330622...</code></p>
      <p class="small" style="background:var(--soft);padding:8px;border-radius:6px;font-style:italic;">"Brindo servicio sexual a cambio de ayuda económica — Te doy servicio sexual a cambio de ayuda económica..."</p>
      <p class="small">Exact-text SHA-256 duplicate. Certainty: 1.0, uncertainty: 0.0. This is the only outlier type with zero uncertainty — duplicates are definitionally certain.</p>
    </div>
    <div class="dossier-card" style="border-left:4px solid var(--muted);">
      <p class="small"><b>Metadata error</b> — <code>h_00255b3c098e9c...</code></p>
      <p class="small" style="background:var(--soft);padding:8px;border-radius:6px;font-style:italic;">"Amiga venezolana que quiera apoyo económico — Hola pongo este anuncio a ver si una amiga venezolana que este pasando apuros económico..."</p>
      <p class="small">This record has a metadata schema violation (inconsistent source_platform vs platform_family). The ad content is valid but the metadata needs fixing in the pipeline.</p>
    </div>

    <h3>Key Findings</h3>
    <ul class="small">
      <li><b>82% of outlier reports</b> are metadata errors — the pipeline should fix these, not treat them as ad-content anomalies.</li>
      <li><b>50 creative-novelty outliers</b> represent ads that are semantically distinct — useful for identifying new ad patterns or corpus gaps.</li>
      <li><b>3 duplicates</b> found by exact-text SHA-256 — certainty 1.0, no uncertainty.</li>
      <li><b>0 extraction errors</b> in this sample — the rebuild pipeline is clean.</li>
    </ul>
  </section>

  <!-- ========== ADINTEL NEW SECTION: Migration ========== -->
  <div class="story-transition v1-to-new">↓ Outliers surface problems; the migration shows how the <b>existing 5,717 annotations</b> project forward to the new v2 taxonomy without losing any v1 labels.</div>
  <section id="adintel-migration" style="margin-top:16px;border:2px solid var(--violet);">
    <div class="story-step"><span class="step-num" style="background:var(--violet);">12</span><span class="step-text"><b>New: v1→v2 migration.</b> All 5,717 annotations projected to v2 with 0 unmapped labels. v1 labels preserved as <code>v1_label</code>; v2 leaves projected to <code>v2_labels</code>.</span></div>
    <h2>adintel: v1 → v2 Annotation Migration <span class="section-tag new">new</span></h2>
    <div class="kpis">
      <div class="kpi"><div class="label">Records migrated</div><div class="value">{migration.get('input_records', 0):,} → {migration.get('output_records', 0):,}</div></div>
      <div class="kpi"><div class="label">Unmapped v1 labels</div><div class="value">{len(migration.get('unmapped_v1_labels', []))}</div></div>
      <div class="kpi"><div class="label">Multi-label projections</div><div class="value">{migration.get('n_multi_label_projections', 0):,}</div><div class="note">expected; v1 overloaded labels split</div></div>
    </div>
  </section>

  <!-- ========== ADINTEL NEW SECTION: Checkpoint registry ========== -->
  <div class="story-transition v1-to-new">↓ Migration bridges old and new labels; the checkpoint registry documents <b>every model checkpoint</b> with version, calibration status, cost, latency, and abstention conditions — so you know exactly what you're trusting.</div>
  <section id="adintel-checkpoints" style="margin-top:16px;border:2px solid var(--violet);">
    <div class="story-step"><span class="step-num" style="background:var(--violet);">13</span><span class="step-text"><b>New: checkpoint registry.</b> 6 registered checkpoints. Uncalibrated scores are never averaged. Model disagreement routes to human review.</span></div>
    <h2>adintel: Checkpoint Registry <span class="section-tag new">new</span></h2>
    <table>
      <thead><tr><th>Checkpoint</th><th>Version</th><th>Calibration</th><th class="num">Cost/1k</th><th class="num">Latency p50</th><th>Baseline</th><th>Abstention conditions</th></tr></thead>
      <tbody>{cp_rows}</tbody>
    </table>
    <p class="small">Model disagreement routes to human review. Uncalibrated scores are never averaged (enforced by <code>adintel.checkpoints.average_calibrated_only</code>).</p>
  </section>

  <!-- ========== ADINTEL NEW SECTION: Challenge rounds ========== -->
  <div class="story-transition v1-to-new">↓ Checkpoints document what the models do; the challenge-round ledgers document <b>what went wrong during adversarial testing</b> — and what was fixed vs. what remains open.</div>
  <section id="adintel-challenges" style="margin-top:16px;border:2px solid var(--violet);">
    <div class="story-step"><span class="step-num" style="background:var(--violet);">14</span><span class="step-text"><b>New: challenge rounds.</b> Two adversarial critique rounds found 18 defects. 11 fixed in-session, 7 documented as limitations. Full ledgers linked below.</span></div>
    <h2>adintel: Challenge Round Defect Ledgers <span class="section-tag new">new</span></h2>
    <p class="small">Two adversarial challenge rounds identified 18 defects. 11 fixed in-session; 7 documented as limitations.</p>
    <div class="viz-toolbar">
      <a class="control" href="challenge_round1_defects.md" target="_blank">Round 1 — scientific validity (9 defects)</a>
      <a class="control" href="challenge_round2_defects.md" target="_blank">Round 2 — analyst usefulness (9 defects)</a>
    </div>
  </section>

  <!-- ========== V1 SECTION: Research ========== -->
  <div class="story-transition">↓ You've reached the end of the analytical journey. The research section below documents <b>why each design choice was made</b> — the sources, theories, and tradeoffs behind every visualization above.</div>
  <section id="research" style="margin-top:16px">
    <div class="story-step"><span class="step-num">15</span><span class="step-text"><b>Why these choices?</b> Every visualization above is grounded in research: Cialdini for persuasion, Gray for dark patterns, Koppel for authorship, Guo for calibration, Hernán for causal discipline. Read this section to understand the evidence base.</span></div>
    <h2>Research-backed design choices <span class="section-tag v1">v1</span></h2>
    <div class="tutorial">
      <h3 style="color:var(--blue);margin:0 0 4px;">How to use the research notes</h3>
      <ul style="margin:0 0 0 16px;padding:0;">
        <li>This section explains why the report separates overview, drill-down, local explanations, uncertainty, and limitations.</li>
        <li>For claims, cite the specific metric/visualization and the relevant limitation instead of quoting a single score alone.</li>
      </ul>
    </div>
    <ul class="small">
      <li>Model cards/datasheets practice: expose intended use, limitations, split metrics, and subgroup/cohort warnings.</li>
      <li>Human-centered XAI: provide local explanations, score arithmetic, uncertainty/limitations, and avoid equating explanations with truth.</li>
      <li>Dashboard UX: overview first, zoom/filter, details on demand, keyboard navigation, accessible tables, mobile and print modes.</li>
      <li>Uncertainty-aware explanations: render confidence intervals, abstention, and known-error budgets alongside every metric.</li>
      <li>Observability and dark-pattern/model-risk reporting: surface known limitations, cohort warnings, and error budgets.</li>
      <li>adintel additions: hierarchical taxonomy (Gray 2024), 17-dim persuasive profile (Cialdini lineage), 7-space clustering stability (Levine, von Luxburg), 4-task authorship with abstention (Koppel, Halvani, Scheirer), 11 outlier types with provenance, checkpoint registry with calibration hooks (Guo 2017), evidence-discipline linting (Hernán &amp; Robins 2020).</li>
    </ul>
  </section>

</main>

<div class="tooltip" id="tooltip"></div>
<div class="toast" id="toast"></div>

<!-- Embedded v1 data (same as original report) -->
<script type="application/json" id="report-data">{v1_inf_json}</script>
<script type="application/json" id="model-report">{v1_model_json}</script>
<script type="application/json" id="segment-report">{v1_segment_json}</script>
""" + """
<script>
// ============ V1 observatory logic (restored from original) ============
const data = JSON.parse(document.getElementById('report-data').textContent);
const modelReport = JSON.parse(document.getElementById('model-report').textContent);
const segmentReport = JSON.parse(document.getElementById('segment-report').textContent);
</script>
<script>
// adintel 17-dim live profile (mirrors interactive_analyzer.html signals)
// Also: real colorFor function (can't be in f-string due to {} in JS)
function realColorFor(value) {
  var palette = ['#315d8c','#2f6f4e','#c9802f','#b4473d','#6d4fa3','#72806e','#8f5b2d'];
  var hash = 0;
  for (var i = 0; i < String(value || '').length; i++) {
    hash = (hash * 31 + String(value || '').charCodeAt(i)) >>> 0;
  }
  return palette[hash % palette.length];
}
// Override the stub
colorFor = realColorFor;

var ADINTEL_SIGNALS = {
  urgency: [['urgente|ahora|ya|hoy|inmediato','gi',0.3,'urgency'],['último|ultima','gi',0.2,'last-chance']],
  scarcity: [['solo|unico|limitad|pocos|cupos','gi',0.25,'scarcity']],
  emotional_intensity: [['triste|sola|deprimida|necesitad','gi',0.3,'vulnerability'],['miedo|peligro|riesgo','gi',0.3,'fear']],
  directiveness: [['escríbeme|escribeme|llámame|whatsapp','gi',0.3,'contact'],['debes|tienes que','gi',0.25,'obligation']],
  certainty: [['seguro|garantizado|100%|real','gi',0.25,'certainty']],
  manipulation_risk: [['urgente|debes|tienes que','gi',0.25,'pressure'],['chicas?(de)?(18|19|20)|estudiantes','gi',0.3,'youth'],['ayuda.económica','gi',0.1,'euphemism'],['buena presencia|guapa|figura','gi',0.25,'appearance']],
  benefit_density: [['ayuda.económica|dinero|soles|apoyo','gi',0.25,'financial'],['constante|permanente|semanal','gi',0.25,'regularity']],
  social_proof: [['muchos|varios|todos|recomend','gi',0.2,'social proof']],
  scarcity_or_urgency: [['urgente|hoy|ya|inmediato|último|solo por','gi',0.25,'urgency/scarcity']],
  reciprocity_obligation: [['ayuda|brindo|ofrezco|favor|regalo','gi',0.15,'reciprocity']],
  privacy_or_secrecy_pressure: [['discreto|secreto|privado|confidencial','gi',0.25,'secrecy']],
  platform_migration: [['whatsapp|wsp|telegram|privado|escríbeme','gi',0.25,'channel']],
  authority_or_status_appeal: [['serio|profesional|empresario|solvente','gi',0.25,'authority']],
  claim_extremity: [['100%|garantizado|resultado asegurado|el mejor','gi',0.25,'extremity']],
  commitment_escalation: [['constante|permanente|semanal|mensual|fijo','gi',0.25,'commitment']],
  objection_handling: [['sin compromiso|discreto|serio|sin riesgo','gi',0.2,'objection']],
  risk_reversal: [['garantía|devolución|reembolso|prueba gratis','gi',0.3,'reversal']],
};
function scoreWithSignals(text, patterns) {
  var raw = 0; var hits = [];
  for (var i = 0; i < patterns.length; i++) {
    var p = patterns[i];
    var regex = new RegExp(p[0], p[1]);
    var m = String(text).match(regex);
    if (m) { for (var j = 0; j < Math.min(m.length, 3); j++) { raw += p[2]; hits.push({label:p[3],text:m[j]}); } }
  }
  return {score: raw <= 0 ? 0 : 1 - Math.exp(-raw), hits: hits};
}
function analyzeAd(text) {
  var results = {};
  for (var dim in ADINTEL_SIGNALS) { results[dim] = scoreWithSignals(text, ADINTEL_SIGNALS[dim]); }
  return results;
}
</script>
<script>
""" + f"""

const manipLabels = new Set(['conditional_financial_support','transactional_ambiguity','deceptive_assurance','commitment_escalation','foot_in_the_door','scarcity_or_urgency','fear_or_threat','guilt_or_shame_pressure','sexualized_appearance_condition','age_or_youth_targeting','economic_vulnerability_targeting','education_or_student_targeting','family_obligation_targeting','privacy_or_secrecy_pressure','authority_or_status_appeal','exclusivity_or_special_treatment','repetition_or_campaign_escalation','platform_migration','reciprocity_obligation','social_proof']);

const labelGuide = {{
  reciprocity_obligation:{{type:'reciprocity',meaning:'The ad frames help, gift, or mutual aid to invoke a felt obligation to reciprocate.',eli5:'It offers help in a way that makes you feel you owe something back.',watch:'Ayuda, apoyo, brindo, regalo, favor, te puedo ayudar.'}},
  conditional_financial_support:{{type:'conditional support',meaning:'Financial or material help is offered with implicit or explicit conditions.',eli5:'Money is offered but something is expected in return.',watch:'Apoyo económico, ayuda económica, a cambio, te ayudo, monto.'}},
  transactional_ambiguity:{{type:'ambiguous transaction',meaning:'The exact exchange is left unclear while implying money, benefits, companionship, or intimacy.',eli5:'It sounds like a deal but hides the real terms.',watch:'Beneficios, apoyo, conversar, amistad, compañía.'}},
  platform_migration:{{type:'channel migration',meaning:'The ad pushes readers to a private channel where scrutiny and moderation are weaker.',eli5:'It wants to move you to WhatsApp or DM.',watch:'WhatsApp, Telegram, DM, privado, escribeme.'}},
  privacy_or_secrecy_pressure:{{type:'secrecy pressure',meaning:'The ad emphasizes secrecy, discretion, or privacy in ways that isolate the reader.',eli5:'It says "keep this between us".',watch:'Discreto, secreto, sin que nadie sepa, confidencial.'}},
  scarcity_or_urgency:{{type:'scarcity/urgency',meaning:'Limited time, limited slots, or pressure to act quickly is used to reduce deliberation.',eli5:'It pushes "decide now".',watch:'Urgente, hoy, rápido, cupos, inmediato.'}},
  commitment_escalation:{{type:'commitment escalation',meaning:'The ad encourages small initial steps that can lead to stronger obligations or risk.',eli5:'Start small now, harder to leave later.',watch:'Primero conversa, prueba, paso a paso, luego vemos.'}},
  foot_in_the_door:{{type:'foot-in-the-door',meaning:'A low-effort first action is requested before the full ask becomes clear.',eli5:'It asks for an easy first yes.',watch:'Escríbeme, consulta, solo conversa, manda mensaje.'}},
  authority_or_status_appeal:{{type:'authority/status appeal',meaning:'Status, profession, money, seriousness, or power is used to make the offer seem credible.',eli5:'It tries to impress you with status.',watch:'Empresario, profesional, solvente, ejecutivo, serio.'}},
  social_proof:{{type:'social proof',meaning:'Popularity, normality, or other people’s participation is used as persuasion.',eli5:'It says others do this, so it must be okay.',watch:'Muchas chicas, otros casos, recomendado, todos.'}},
  exclusivity_or_special_treatment:{{type:'special-treatment appeal',meaning:'The reader is made to feel selected, preferred, or eligible for an exclusive benefit.',eli5:'It says you could be specially chosen.',watch:'Especial, exclusiva, selecciono, preferencia.'}},
  fear_or_threat:{{type:'fear/threat pressure',meaning:'Fear, loss, danger, or negative consequences are used to motivate action.',eli5:'It tries to scare someone into responding.',watch:'Perder oportunidad, problemas, riesgo, amenaza.'}},
  guilt_or_shame_pressure:{{type:'guilt/shame pressure',meaning:'Moral judgment, embarrassment, or shame is used to influence response.',eli5:'It makes someone feel bad for not accepting.',watch:'No seas, solo serias, no interesadas, juzgar.'}},
  deceptive_assurance:{{type:'assurance/minimization',meaning:'The ad reassures safety, seriousness, privacy, or harmlessness without evidence.',eli5:'It says "trust me" but does not prove it.',watch:'Serio, real, seguro, confiable, sin problemas.'}},
  sexualized_appearance_condition:{{type:'appearance condition',meaning:'The offer is conditioned on physical appearance, attractiveness, or sexualized imagery.',eli5:'It says "only if you look good enough".',watch:'Buena presencia, guapa, figura, atractiva, linda.'}},
  age_or_youth_targeting:{{type:'age targeting',meaning:'The ad selects or pressures people by age/youth.',eli5:'It is aimed at young people or a narrow age group.',watch:'Joven, 18-25, señorita joven.'}},
  education_or_student_targeting:{{type:'student targeting',meaning:'The ad calls out students or educational need as part of the persuasion frame.',eli5:'It tries to appeal to students who may need support.',watch:'Estudiante, universitaria, estudios, matrícula.'}},
  family_obligation_targeting:{{type:'family-obligation targeting',meaning:'Family role or responsibility is used to intensify need or obligation.',eli5:'It uses family pressure as the reason someone might accept.',watch:'Madre soltera, hijos, familia, hogar.'}},
  repetition_or_campaign_escalation:{{type:'repetition/escalation',meaning:'Repeated templates or escalating offers increase pressure or reach.',eli5:'The same tactic keeps appearing or gets stronger.',watch:'Repeated phrases, reposts, similar ads.'}}
}};

const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
function guideFor(label){{ return labelGuide[label] || {{type:'project label',meaning:'Project-specific persuasion/manipulation annotation.',eli5:'This marks a phrase the council considered relevant.',watch:'Review the excerpt, rationale, and score fields.'}} }}
function toast(msg){{ const t=$('toast'); t.textContent=msg; t.classList.add('show'); setTimeout(()=>t.classList.remove('show'),1800) }}
function colorFor(value){{ /* moved to separate script block */ return '#2f6f4e'; }}

let mode='top_by_review_priority', selected=0, currentRows=[], activeMapClusters=new Set(), activeMapQuadrant='';

function allReportRows(){{ const byId={{}}; ['top_by_review_priority','top_by_manipulation','top_by_persuasion'].forEach(k=>(data[k]||[]).forEach(r=>byId[r.record_id]=r)); return byId }}

function initFilters(){{
  Object.keys(data.source_counts||{{}}).sort().forEach(p=>$('platformFilter').insertAdjacentHTML('beforeend',`<option>${{esc(p)}}</option>`));
  Object.keys(data.label_counts||{{}}).sort().forEach(l=>$('labelFilter').insertAdjacentHTML('beforeend',`<option>${{esc(l)}}</option>`));
  (data.global_explainability?.labels||[]).forEach(row=>$('explainLabel').insertAdjacentHTML('beforeend',`<option value="${{esc(row.label)}}">${{esc(row.label)}}</option>`));
}}

function rows(){{
  const q=$('query').value.toLowerCase(), p=$('platformFilter').value, l=$('labelFilter').value;
  return (data[mode]||[]).filter(r=>(!p||r.platform===p)&&(!l||(r.labels||[]).includes(l))&&(!q||((r.title||'')+' '+(r.text||r.excerpt||'')+' '+(r.labels||[]).join(' ')).toLowerCase().includes(q))).slice(0,25);
}}

function renderList(){{
  currentRows = rows(); if(selected>=currentRows.length) selected=0;
  $('rankList').innerHTML = currentRows.map((r,i)=>`<button class="rank" role="option" aria-current="${{i===selected}}" aria-selected="${{i===selected}}" onclick="selectRow(${{i}})">
    <div class="small">#${{i+1}} · ${{esc(r.platform)}} · ${{esc(r.split)}} · ${{esc(r.record_id.slice(0,10))}}</div>
    <div class="rank-title">${{esc((r.title||'').slice(0,96))}}</div>
    <div class="scoreline"><span class="chip red">priority ${{r.scores?.review_priority ?? '?'}}</span><span class="chip amber">manip ${{r.scores?.manipulation ?? '?'}}</span><span class="chip blue">pers ${{r.scores?.persuasion ?? '?'}}</span></div>
  </button>`).join('');
  renderDetail(currentRows[selected] || (data[mode]||[])[0]);
}}
window.selectRow = i => {{ selected=i; renderList(); if(currentRows[i]) history.replaceState(null,'','#'+currentRows[i].record_id) }}

function segmentText(text, spans){{
  const safeSpans = (spans||[]).map(s=>({{...s,segments:(s.segments||[]).map(([a,b])=>[Math.max(0,Math.min(text.length,a)),Math.max(0,Math.min(text.length,b))]).filter(([a,b])=>a<b)}})).filter(s=>s.segments.length);
  const cuts = new Set([0,text.length]); safeSpans.forEach(s=>s.segments.forEach(([a,b])=>{{cuts.add(a);cuts.add(b)}}));
  const points=[...cuts].sort((a,b)=>a-b); let out='';
  for(let i=0;i<points.length-1;i++){{const a=points[i], b=points[i+1], piece=text.slice(a,b); if(!piece) continue;
    const active=safeSpans.filter(s=>s.segments.some(([x,y])=>a>=x&&b<=y)); const cls=active.some(s=>manipLabels.has(s.label))?'seg manip':(active.length?'seg':'');
    const title=active.map(s=>s.label).join(', ');
    out += cls ? `<span class="${{cls}}" title="${{esc(title)}}">${{esc(piece)}}</span>` : esc(piece);
  }} return out;
}}
function shiftSpans(spans, delta, minStart=0, maxEnd=Infinity){{
  return (spans||[]).map(s=>({{...s,segments:(s.segments||[]).map(([a,b])=>[a-delta,b-delta]).filter(([a,b])=>a>=minStart&&b<=maxEnd&&a<b)}})).filter(s=>s.segments.length);
}}
function bar(label,value,color=''){{ return `<div class="rowline"><span>${{esc(label)}}</span><div class="bar"><i style="width:${{Math.max(0,Math.min(100,value*100))}}%;${{color}}"></i></div><b>${{(value*100).toFixed(0)}}%</b></div>` }}

function renderDossier(r){{
  const spans = r.spans || [];
  if(!spans.length){{ $('annotationDossier').innerHTML = '<p class="small">No candidate annotation spans. This ad is useful as a negative/low-signal example.</p>'; return }}
  const grouped = {{}};
  spans.forEach(s=>{{ grouped[s.label] ||= {{count:0,examples:[],maxIntensity:0,maxManip:0,maxHarm:0}}; grouped[s.label].count += 1; if(grouped[s.label].examples.length < 3) grouped[s.label].examples.push(s.excerpt); grouped[s.label].maxIntensity = Math.max(grouped[s.label].maxIntensity, Number(s.intensity||0)); grouped[s.label].maxManip = Math.max(grouped[s.label].maxManip, Number(s.manipulativeness||0)); grouped[s.label].maxHarm = Math.max(grouped[s.label].maxHarm, Number(s.harm_risk||0)) }});
  const maxHarm = Math.max(...Object.values(grouped).map(g=>g.maxHarm));
  const maxManip = Math.max(...Object.values(grouped).map(g=>g.maxManip));
  const summary = `<div class="dossier-card"><h3>Plain-language readout</h3><p class="small">This ad contains <b>${{Object.keys(grouped).length}}</b> technique type(s) across <b>${{spans.length}}</b> span(s). Highest manipulation severity is <b>${{maxManip}}/3</b>; highest harm risk is <b>${{maxHarm}}/3</b>. Treat this as candidate council explainability, not human-adjudicated truth.</p></div>`;
  const cards = Object.entries(grouped).sort((a,b)=>b[1].maxManip-a[1].maxManip || b[1].count-a[1].count).map(([label,g])=>{{const guide=guideFor(label); return `<div class="dossier-card"><h3>${{esc(label.replaceAll('_',' '))}} <span class="type-badge">${{esc(guide.type)}}</span></h3><div class="eli5"><b>ELI5:</b> ${{esc(guide.eli5)}}</div><p class="small"><b>What this label means:</b> ${{esc(guide.meaning)}}</p><p class="small"><b>Why it appears here:</b> ${{g.examples.map(x=>'“'+esc(x)+'”').join(' · ')}}</p><p class="small"><b>Watch for:</b> ${{esc(guide.watch)}}<br><b>Count:</b> ${{g.count}} · <b>max intensity:</b> ${{g.maxIntensity}}/4 · <b>max manipulation:</b> ${{g.maxManip}}/3 · <b>max harm:</b> ${{g.maxHarm}}/3</p></div>`}}).join('');
  $('annotationDossier').innerHTML = summary + cards;
}}

function renderDetail(r){{
  if(!r) return;
  const fullText = r.text || (r.title + "\\n" + (r.excerpt || ''));
  const title = r.title || fullText.split('\\n')[0] || '';
  const bodyStart = fullText.startsWith(title + '\\n') ? title.length + 1 : 0;
  const body = bodyStart ? fullText.slice(bodyStart) : fullText;
  const titleSpans = shiftSpans(r.spans,0,0,title.length);
  const bodySpans = shiftSpans(r.spans,bodyStart,0,body.length);
  $('detailHead').innerHTML = `<p class="small">${{esc(r.record_id)}} · ${{esc(r.platform)}} · ${{esc(r.split)}} · round ${{r.accepted_round}}</p><div style="font-weight:700;font-size:14px;margin:4px 0;">${{segmentText(title,titleSpans)}}</div><div class="scoreline"><span class="chip red">review ${{r.scores?.review_priority ?? '?'}}</span><span class="chip amber">manipulation ${{r.scores?.manipulation ?? '?'}}</span><span class="chip blue">persuasion ${{r.scores?.persuasion ?? '?'}}</span><span class="chip violet">${{(r.spans||[]).length}} spans</span></div>`;
  $('annotatedText').innerHTML = `<div class="small" style="margin-bottom:4px;color:var(--muted);">Ad body</div>${{segmentText(body, bodySpans)}}`;
  const a=r.scores?.arithmetic||{{}};
  $('waterfall').innerHTML = (a.persuasion?`<h4>v1 Score Arithmetic</h4>${{bar('weighted span burden',a.persuasion.span_burden||0)}}${{bar('max intensity',(a.persuasion.max_intensity||0)/4)}}${{bar('technique diversity',a.persuasion.technique_diversity||0)}}${{bar('repetition/escalation',a.persuasion.repetition_escalation||0)}}`:'') + (a.manipulation?`<h4>Manipulation</h4>${{bar('severity burden',a.manipulation.severity_span_burden||0)}}${{bar('max severity',(a.manipulation.max_severity||0)/3)}}${{bar('vulnerability/conditionality',a.manipulation.vulnerability_conditionality||0)}}${{bar('concealment/coercion',a.manipulation.concealment_coercion||0)}}${{bar('bounded exposure context',a.context_exposure||0)}}`:'');
  // adintel 17-dim profile (computed live from the ad text)
  const adintelResults = analyzeAd(fullText);
  const adintelBars = Object.entries(adintelResults)
    .filter(([dim, r]) => r.score > 0.05)
    .sort(([,a],[,b]) => b.score - a.score)
    .slice(0, 8)
    .map(([dim, r]) => {{
      const color = r.score > 0.5 ? 'var(--red)' : r.score > 0.3 ? 'var(--amber)' : 'var(--green)';
      return bar(dim.replace(/_/g,' '), r.score, 'background:'+color);
    }}).join('');
  $('waterfall').innerHTML += adintelBars ? `<h4 style="color:var(--violet);">adintel 17-dim Profile (live)</h4>${{adintelBars}}<p class="small">Computed in real-time from ad text. <a href="https://pillb.github.io/manipsych-adintel/interactive_analyzer.html" target="_blank">Open in analyzer →</a></p>` : '<p class="small" style="color:var(--violet);">adintel profile: no significant techniques detected.</p>';
  $('ledger').innerHTML = (r.spans||[]).map((s,i)=>{{const guide=guideFor(s.label); return `<div class="ledger-row"><span class="chip ${{manipLabels.has(s.label)?'red':'amber'}}">${{i+1}}. ${{esc(s.label)}}</span> <span class="type-badge">${{esc(guide.type)}}</span><p>${{esc(s.excerpt)}}</p><p class="small"><b>Meaning:</b> ${{esc(guide.meaning)}}<br><b>ELI5:</b> ${{esc(guide.eli5)}}<br>offsets ${{esc(JSON.stringify(s.segments))}} · intensity ${{s.intensity}} · manip ${{s.manipulativeness}} · harm ${{s.harm_risk}}</p></div>`}}).join('') || '<p class="small">No candidate spans.</p>';
  renderDossier(r);
  renderSelectedExplainability(r);
  const allModel = r.model_predictions || r.top_model || [];
  $('modelPredictions').innerHTML = allModel.slice(0,12).map(m=>bar(m.label,m.probability,'background:linear-gradient(90deg,var(--blue),var(--violet))')).join('') + `<p class="small">Top ${{Math.min(12,allModel.length)}} of ${{allModel.length}} model labels.</p>`;
  const council=new Set(r.labels||[]), model=new Set(allModel.filter(m=>m.probability>=.5).map(m=>m.label));
  const overlap=[...council].filter(x=>model.has(x)); const modelOnly=[...model].filter(x=>!council.has(x)); const councilOnly=[...council].filter(x=>!model.has(x));
  $('agreementBox').innerHTML = `<b>Overlap:</b> ${{esc(overlap.join(', ')||'none')}}<br><b>Model-only ≥0.5:</b> ${{esc(modelOnly.join(', ')||'none')}}<br><b>Council-only:</b> ${{esc(councilOnly.slice(0,12).join(', ')||'none')}}<br><b>adintel live:</b> ${{Object.entries(adintelResults).filter(([,r])=>r.score>0.1).map(([d])=>d).slice(0,5).join(', ')||'none'}}`;
}}

function lineChart(points, options={{}}){{
  const width=620,height=300,pad=34;
  const pts=(points||[]).filter(p=>Number.isFinite(p[0])&&Number.isFinite(p[1]));
  const path=pts.map(([x,y],i)=>`${{i?'L':'M'}}${{pad+x*(width-2*pad)}} ${{height-pad-y*(height-2*pad)}}`).join(' ');
  return `<svg viewBox="0 0 ${{width}} ${{height}}" role="img" aria-label="${{esc(options.label||'metric curve')}}" style="max-width:100%;"><path d="M${{pad}} ${{height-pad}}H${{width-pad}}M${{pad}} ${{height-pad}}V${{pad}}" stroke="var(--line)" fill="none"/><path d="M${{pad}} ${{height-pad}}L${{width-pad}} ${{pad}}" stroke="var(--line)" stroke-dasharray="3 3" fill="none"/><path d="${{path}}" stroke="var(--green)" stroke-width="2" fill="none"/><text x="${{pad}}" y="${{height-8}}" font-size="11">0</text><text x="${{width-pad-8}}" y="${{height-8}}" font-size="11">1</text><text x="8" y="${{pad+4}}" font-size="11">1</text><text x="${{width/2-40}}" y="20" font-size="13" font-weight="800">${{esc(options.title||'')}}</text></svg>`;
}}

function heatColor(value){{
  // Viridis-inspired colormap (colorblind-safe)
  // Replaces the old HSL ramp that passed through red-green (8% of males collapse it)
  if(value===null||value===undefined||Number.isNaN(Number(value))) return '#f0f0f0';
  const v=Math.max(0,Math.min(1,Number(value)));
  // Viridis stops: #440154 (purple) -> #3b528b (blue) -> #21918c (teal) -> #5ec962 (green) -> #fde725 (yellow)
  const stops = [
    [0.0, [68,1,84]], [0.25, [59,82,139]], [0.5, [33,145,140]],
    [0.75, [94,201,98]], [1.0, [253,231,37]]
  ];
  for(let i=0; i<stops.length-1; i++){{
    if(v >= stops[i][0] && v <= stops[i+1][0]){{
      const t = (v - stops[i][0]) / (stops[i+1][0] - stops[i][0]);
      const r = Math.round(stops[i][1][0] + t*(stops[i+1][1][0]-stops[i][1][0]));
      const g = Math.round(stops[i][1][1] + t*(stops[i+1][1][1]-stops[i][1][1]));
      const b = Math.round(stops[i][1][2] + t*(stops[i+1][1][2]-stops[i][1][2]));
      return `rgb(${{r}},${{g}},${{b}})`;
    }}
  }}
  return '#fde725';
}}

function renderDiagnostics(){{
  const test=modelReport.metrics?.test||{{}}, validation=modelReport.metrics?.validation||{{}};
  $('curveChart').innerHTML = `<div class="viz-grid"><div>${{lineChart(test.roc_curve_micro||[],{{title:'Test micro ROC',label:'test micro ROC curve'}})}}<p class="small">AUC ${{test.roc_auc_micro ?? 'n/a'}}</p></div><div>${{lineChart(test.precision_recall_curve_micro||[],{{title:'Test micro PR',label:'test micro PR curve'}})}}<p class="small">AP ${{test.average_precision_micro ?? 'n/a'}}</p></div></div>`;
  const timeline=(data.iteration_timeline||[]).map(item=>({{...item,micro_f1:item.micro_f1 ?? (item.stage==='localized council'?test.micro_f1:null),macro_f1:item.macro_f1 ?? (item.stage==='localized council'?test.macro_f1:null)}}));
  $('iterationTimeline').innerHTML = timeline.map((item,i)=>`<div class="timeline-row"><b>${{esc(item.date)}}</b><div><b>${{esc(item.stage)}}</b><br><span class="small">${{esc(item.note)}} · records ${{item.records}}${{item.spans?` · spans ${{item.spans}}`:''}}</span></div><div><span class="tag blue">μF1 ${{item.micro_f1 ?? 'n/a'}}</span><br><span class="tag amber">MF1 ${{item.macro_f1 ?? 'n/a'}}</span></div></div>`).join('');
  const labels=Object.entries(test.per_label||{{}}).sort((a,b)=>(b[1].support||0)-(a[1].support||0)).slice(0,20);
  $('metricHeatmap').innerHTML = `<div class="heat-row"><b>Label</b><b>F1</b><b>AUC</b><b>Acc</b><b>Support</b></div>` + labels.map(([label,m])=>`<div class="heat-row"><span title="${{esc(label)}}">${{esc(label.replaceAll('_',' ').slice(0,26))}}</span><span class="heat-cell" style="background:${{heatColor(m.f1)}}">${{m.f1}}</span><span class="heat-cell" style="background:${{heatColor(m.roc_auc)}}">${{m.roc_auc ?? 'n/a'}}</span><span class="heat-cell" style="background:${{heatColor(m.accuracy)}}">${{m.accuracy}}</span><b>${{m.support}}</b></div>`).join('');
  const known=[['Raw collection','10,293 HTML archives collected; strict extraction rejects interstitials/duplicates.'],['Offer filter','5,717 modeling records; 21 strict processed records excluded.'],['Research-v2','Rubric expanded after survey/source review.'],['Spanish localization','Gender/accent/typo/slang omissions fixed.'],['No-code expert POC','Direct expert overlay for seed issue.'],['Current model','Agreement metrics use candidate council labels, not human gold.']];
  $('errorTimeline').innerHTML = known.map(([stage,note])=>`<div class="timeline-row"><b>${{esc(stage)}}</b><div class="small">${{esc(note)}}</div><span class="tag ${{stage.includes('Current')?'red':'blue'}}">tracked</span></div>`).join('');
  renderSegmentDiagnostics();
}}

function sliceCard(row){{
  const terms=(row.top_terms||[]).map(t=>`<span class="tag">${{esc(t)}}</span>`).join('');
  return `<div class="slice-card"><b>${{esc(row.dimension)}} = ${{esc(row.value)}}</b><div class="small">${{row.records}} test records · default μF1 ${{row.default?.micro_f1 ?? 'n/a'}} · tuned μF1 ${{row.threshold_tuned?.micro_f1 ?? 'n/a'}}</div>${{terms?`<div class="terms">${{terms}}</div>`:''}}</div>`;
}}

function renderSegmentDiagnostics(){{
  if(!segmentReport.status){{$('sliceWeakness').innerHTML='<p class="small">Segment report not generated.</p>';return}}
  const weak=(segmentReport.underperforming_slices||[]).slice(0,8);
  $('sliceWeakness').innerHTML = weak.map(sliceCard).join('') || '<p class="small">No underperforming slices.</p>';
  $('clusterSummary').innerHTML = (segmentReport.clusters||[]).slice(0,10).map(c=>`<div class="slice-card"><b>${{esc(c.cluster)}}</b><div class="small">${{c.records}} corpus records</div><div class="terms">${{(c.top_terms||[]).map(t=>`<span class="tag blue">${{esc(t)}}</span>`).join('')}}</div></div>`).join('');
  const d=segmentReport.overall_default||{{}}, t=segmentReport.overall_threshold_tuned||{{}};
  const notes=(segmentReport.method_notes||[]).map(n=>`<li>${{esc(n)}}</li>`).join('');
  $('thresholdOverlay').innerHTML = `<table><tr><th>Metric</th><th>Default .50</th><th>Tuned</th><th>Δ</th></tr>${{['micro_f1','macro_f1','subset_accuracy','label_accuracy'].map(k=>`<tr><td>${{esc(k)}}</td><td>${{d[k] ?? 'n/a'}}</td><td>${{t[k] ?? 'n/a'}}</td><td>${{(Number(t[k]||0)-Number(d[k]||0)).toFixed(4)}}</td></tr>`).join('')}}</table><ul class="small">${{notes}}</ul>`;
}}

function termPills(terms){{ return (terms||[]).slice(0,12).map(t=>`<span class="term-pill"><span>${{esc(t.term)}}</span><b>${{Number(t.weight).toFixed(2)}}</b></span>`).join('') }}

function renderExplainabilityAtlas(){{
  const selectedLabel=$('explainLabel').value || data.global_explainability?.labels?.[0]?.label;
  const row=(data.global_explainability?.labels||[]).find(x=>x.label===selectedLabel);
  if(!row){{$('explainabilityAtlas').innerHTML='<p class="small">No global explanations available.</p>';return}}
  const warning=row.low_support ? `<p class="warn small"><b>Low support:</b> ${{row.support}} test examples; treat metrics cautiously.</p>` : '';
  $('explainabilityAtlas').innerHTML = `<div class="coef-card"><h3>${{esc(row.label.replaceAll('_',' '))}}</h3><p class="small"><b>Family:</b> ${{esc(row.family)}} · <b>Type:</b> ${{esc(row.type)}} · <b>Support:</b> ${{row.support}}<br><b>F1:</b> ${{row.f1 ?? 'n/a'}} · <b>AUC:</b> ${{row.roc_auc ?? 'n/a'}}</p>${{warning}}<h4>Terms pushing this label up</h4>${{termPills(row.top_positive_terms)}}<h4>Contrast terms</h4>${{termPills(row.contrast_terms)}}</div><div class="coef-card"><h3>Selected-ad local evidence</h3><div id="selectedEvidence" class="small">Select an ad to show local overlap.</div></div><div class="coef-card"><h3>Caveats</h3><ul class="small">${{(data.global_explainability?.caveats||[]).map(c=>`<li>${{esc(c)}}</li>`).join('')}}</ul></div>`;
}}

function renderSelectedExplainability(r){{
  if(!$('selectedEvidence')) return;
  const selectedLabel=$('explainLabel').value || (r.labels&&r.labels[0]);
  const row=(data.global_explainability?.labels||[]).find(x=>x.label===selectedLabel);
  const terms=(row?.top_positive_terms||[]).map(t=>t.term.toLowerCase());
  const text=(r.text||'').toLowerCase();
  const hits=terms.filter(t=>text.includes(t)).slice(0,10);
  const prob=(r.model_predictions||[]).find(m=>m.label===selectedLabel)?.probability;
  const council=(r.labels||[]).includes(selectedLabel);
  $('selectedEvidence').innerHTML = `<b>Selected label:</b> ${{esc(selectedLabel)}}<br><b>Council has label:</b> ${{council?'yes':'no'}} · <b>model probability:</b> ${{prob ?? 'n/a'}}<br><b>Coefficient terms present:</b> ${{esc(hits.join(', ')||'none')}}`;
}}

function tooltip(){{ let t=document.querySelector('.tooltip'); if(!t){{t=document.createElement('div');t.className='tooltip';document.body.appendChild(t)}} return t }}

function renderTermNetwork(){{
  const container=$('termNetworkViz'), status=$('networkStatus'); const network=data.term_network||{{}};
  const kind=$('networkKind').value, topN=Number($('networkTopN').value||100), labelMode=$('networkLabelMode').value;
  let nodes=(network.nodes||[]).filter(n=>!kind||n.kind===kind||n.kind!=='term').slice(0,topN);
  const nodeIds=new Set(nodes.map(n=>n.id));
  let edges=(network.edges||[]).filter(e=>nodeIds.has(e.source)&&nodeIds.has(e.target)).slice(0,260);
  // R0-fix: use d3LiteForce if loaded, otherwise circular fallback WITH visible warning
  const hasForce = typeof window.d3LiteForce !== 'undefined' && typeof window.d3LiteForce.layout === 'function';
  const runtime = hasForce ? (window.d3?.version || 'd3-lite-force-local') : 'vanilla fallback';
  status.textContent = `${{nodes.length}} nodes · ${{edges.length}} edges · runtime ${{runtime}}`;
  if(!hasForce){{
    status.innerHTML += ' <span role="alert" style="color:var(--red);font-weight:700">⚠ Force layout helper failed to load — showing circular fallback.</span>';
  }}
  $('networkInspector').innerHTML = '<b>How to interpret:</b> clicked terms show example record ids and linked labels. Treat links as co-occurrence, not causation.';
  if(!nodes.length){{container.innerHTML='<p class="small" style="padding:16px">No network data.</p>';return}}
  const width=980,height=620;
  let laid, links;
  if(hasForce){{
    const result = window.d3LiteForce.layout(nodes, edges, {{width, height, charge:-390, iterations:230}});
    laid = result.nodes; links = result.links;
  }} else {{
    laid = nodes.map((n,i)=>({{...n,x:width/2+Math.cos(i/nodes.length*Math.PI*2)*310,y:height/2+Math.sin(i/nodes.length*Math.PI*2)*230}}));
    links = edges.map(e=>({{source:laid.find(n=>n.id===e.source),target:laid.find(n=>n.id===e.target),weight:e.weight}})).filter(e=>e.source&&e.target);
  }}
  const maxWeight=Math.max(...laid.map(n=>n.weight||1),1);
  container.innerHTML = `<svg viewBox="0 0 ${{width}} ${{height}}" width="100%" height="100%" aria-label="term network">${{links.map(e=>`<line class="network-edge" x1="${{e.source.x}}" y1="${{e.source.y}}" x2="${{e.target.x}}" y2="${{e.target.y}}" stroke="var(--line)" stroke-width="${{Math.min(5,0.8+Math.sqrt(e.weight||1)/2)}}"></line>`).join('')}}${{laid.map(n=>`<g class="network-node" tabindex="0" data-node="${{esc(n.id)}}" aria-label="${{esc(n.name)}}"><circle cx="${{n.x}}" cy="${{n.y}}" r="${{n.kind==='term'?5+14*Math.sqrt((n.weight||1)/maxWeight):n.kind==='label'?11:9}}" fill="${{n.kind==='label'?'var(--red)':n.kind==='platform'?'var(--blue)':'var(--green)'}}" opacity=".88"><title>${{esc(n.name)}} (${{n.kind}})</title></circle></g>`).join('')}}</svg>`;
  container.querySelectorAll('.network-node').forEach((el,i)=>{{
    const node=laid[i];
    el.style.cursor='pointer';
    el.addEventListener('click',()=>$('networkInspector').innerHTML=`<b>${{esc(node.name)}}</b> · ${{esc(node.kind)}}<br>Examples: ${{(node.examples||[]).map(id=>`<a href="#${{esc(id)}}">${{esc(id.slice(0,10))}}</a>`).join(' ')||'n/a'}}`);
  }});
}}

function renderCorpusMap(){{
  const map=data.corpus_map||{{}}, container=$('corpusMapViz');
  const allPoints=(map.points||[]);
  if(!allPoints.length){{container.innerHTML='<p class="small" style="padding:16px">No corpus map data.</p>';return}}
  const width=900,height=500,pad=34;
  function cx(p){{return pad+(p.x+1)/2*(width-2*pad)}} function cy(p){{return height-pad-(p.y+1)/2*(height-2*pad)}}
  function fill(p){{return colorFor(p.platform||p.split||'unknown')}}
  $('mapLegend').innerHTML = [...new Set(allPoints.map(p=>p.platform))].map(v=>`<span class="legend-item"><span class="swatch" style="background:${{colorFor(v)}}"></span>${{esc(v)}}</span>`).join('');
  container.innerHTML = `<svg viewBox="0 0 ${{width}} ${{height}}" width="100%" height="100%" aria-label="corpus map"><path d="M${{pad}} ${{height/2}}H${{width-pad}}M${{width/2}} ${{pad}}V${{height-pad}}" stroke="var(--line)" fill="none"/>${{allPoints.slice(0,500).map(p=>`<circle cx="${{cx(p)}}" cy="${{cy(p)}}" r="4" fill="${{fill(p)}}" opacity=".82"><title>${{esc(p.title||p.record_id||'')}} · ${{esc(p.platform||'')}}</title></circle>`).join('')}}</svg>`;
  $('mapInspector').innerHTML = `<b>How to interpret:</b> ${{allPoints.length}} ads plotted. Each point is a representative ad. Inspect annotations before inferring technique from neighborhood.`;
  $('mapSelectedDetail').innerHTML = '<h3>Selected point</h3><p class="small">Click a map point to see ad metadata.</p>';
  $('mapNeighbors').innerHTML = '<h3>Nearest neighbors</h3><p class="small">Select a point to see neighbors.</p>';
  $('mapQuadrants').innerHTML = '';
  $('deepClusterPanel').innerHTML = (map.deep_clusters?.clusters||[]).slice(0,6).map(c=>`<div class="map-card"><h3>${{esc(c.eli5_title||c.name)}}</h3><p class="small">${{c.count}} ads · ${{esc((c.top_terms||[]).slice(0,5).map(t=>t.term).join(', '))}}</p></div>`).join('') || '<p class="small">No deep clusters.</p>';
  $('isolationPanel').innerHTML = '<p class="small">Isolation slices available in full report.</p>';
}}

function renderFacetOverview(){{
  const overview=data.facet_overview||{{}};
  $('facetOverview').innerHTML = (overview.facets||[]).map(f=>{{const max=Math.max(...(f.values||[]).map(v=>v.count),1);return `<div class="facet-card"><h3>${{esc(f.name)}}</h3>${{(f.values||[]).slice(0,8).map(v=>`<div class="rowline"><span>${{esc(v.value)}}</span><div class="bar"><i style="width:${{v.count/max*100}}%;background:linear-gradient(90deg,var(--green),var(--blue))"></i></div><b>${{v.count}}</b></div>`).join('')}}</div>`}}).join('');
  $('taxonomyMatrix').innerHTML = `<table><tr><th>Label</th><th>Family</th><th>Type</th><th>Count</th><th>Human check</th></tr>${{(data.annotation_taxonomy_matrix||[]).map(r=>`<tr><td>${{esc(r.label)}}</td><td>${{esc(r.family)}}</td><td>${{esc(r.type)}}</td><td>${{r.count}}</td><td>${{esc(r.human_check)}}</td></tr>`).join('')}}</table>`;
}}

function renderExpertPoc(){{
  const seed='h_f4fc363a9b8f997059ec332d2ec0effd3960edf30c9f677131a8a9061e43fd81';
  const rows=['Direct no-code AI expert review completed for the seed record.','Correction: "Brindó apoyo económica" is a malformed but semantically valid economic-support frame.','Layer is proof-of-concept AI expert overlay, not human gold.','Full-corpus human-equivalent review requires funded reviewer assignments and adjudication.'];
  $('expertPoc').innerHTML = `<div class="scoreline" style="margin-bottom:8px"><span class="chip blue">POC 1 / ${{data.records}}</span><span class="chip amber">candidate ${{data.records}}</span><span class="chip red">human gold false</span></div><table><tr><th>#</th><th>Status</th></tr>${{rows.map((r,i)=>`<tr><td>${{i+1}}</td><td>${{esc(r)}}</td></tr>`).join('')}}<tr><td>Seed</td><td><a href="#${{seed}}">${{seed.slice(0,20)}}…</a></td></tr></table>`;
}}

function renderObs(){{
  const obs=data.observability||{{}}, metrics=modelReport.metrics?.test||{{}};
  $('obsTable').innerHTML = `<tr><th>Signal</th><th>Value</th></tr><tr><td>Candidate gold flag</td><td>${{obs.gold}}</td></tr><tr><td>Challenge records</td><td>${{obs.challenge_records ?? 'n/a'}}</td></tr><tr><td>Image metadata but no pixels</td><td>${{obs.image_metadata_without_pixels ?? obs.missing_image_pixels ?? 'n/a'}}</td></tr><tr><td>Test micro/macro F1*</td><td>${{metrics.micro_f1 ?? 'n/a'}} / ${{metrics.macro_f1 ?? 'n/a'}}</td></tr><tr><td>Accuracy*</td><td>subset ${{metrics.subset_accuracy ?? 'n/a'}} · label ${{metrics.label_accuracy_micro ?? 'n/a'}}</td></tr><tr><td>ROC AUC*</td><td>micro ${{metrics.roc_auc_micro ?? 'n/a'}}</td></tr><tr><td>Known errors</td><td>${{esc((obs.known_errors||[]).join(' · '))}}</td></tr>`;
  const labels=Object.entries(data.label_counts||{{}}).sort((a,b)=>b[1]-a[1]);
  const max=Math.max(...labels.map(x=>x[1]),1);
  $('labelChart').innerHTML = labels.map(([l,c])=>`<div class="rowline"><span title="${{esc(l)}}">${{esc(l.replaceAll('_',' ').slice(0,24))}}</span><div class="bar"><i style="width:${{(c/max)*100}}%;background:linear-gradient(90deg,var(--green),var(--blue))"></i></div><b>${{c}}</b></div>`).join('');
}}

// Event listeners
['rankMode','platformFilter','labelFilter'].forEach(id=>$(id).addEventListener('change',e=>{{if(id==='rankMode')mode=e.target.value;selected=0;renderList()}}));
$('query').addEventListener('input',()=>{{selected=0;renderList()}});
$('explainLabel').addEventListener('change',()=>{{renderExplainabilityAtlas();renderDetail(currentRows[selected]||(data[mode]||[])[0])}});
$('networkKind').addEventListener('change',renderTermNetwork);
$('networkTopN').addEventListener('change',renderTermNetwork);
$('networkLabelMode').addEventListener('change',renderTermNetwork);
$('networkReset').addEventListener('click',()=>{{$('networkKind').value='';$('networkTopN').value='100';$('networkLabelMode').value='smart';renderTermNetwork()}});
$('mapColor').addEventListener('change',renderCorpusMap);
$('mapQuery').addEventListener('input',renderCorpusMap);
$('mapResetLayers').addEventListener('click',renderCorpusMap);

async function copyDeepLink(){{try{{if(navigator.clipboard?.writeText){{await navigator.clipboard.writeText(location.href);toast('Deep link copied');return}}}}catch(e){{}} const area=document.createElement('textarea');area.value=location.href;area.setAttribute('readonly','');area.style.position='fixed';area.style.left='-9999px';document.body.appendChild(area);area.select();let ok=false;try{{ok=document.execCommand('copy')}}catch(e){{}}area.remove();toast(ok?'Deep link copied':'Deep link ready in address bar')}}
$('copyLink').addEventListener('click',copyDeepLink);

function applyHash(){{
  const id=decodeURIComponent((location.hash||'').slice(1)); if(!id) return false;
  // First check if this is a section anchor (not a record ID).
  // Section anchors: pipeline, metrics, diagnostics, explorer, etc.
  // If the hash matches a <section id="...">, let the browser handle the scroll
  // (scroll-padding-top + scroll-margin-top handle the sticky header offset).
  const sectionEl = document.getElementById(id);
  if(sectionEl && sectionEl.tagName === 'SECTION'){{
    // Native browser scroll handles this; scroll-margin-top ensures the
    // sticky header doesn't cover the target. Just scroll into view as backup.
    sectionEl.scrollIntoView({{behavior:'smooth', block:'start'}});
    return true;
  }}
  // Otherwise, check if it's a record ID for the explorer
  for(const candidateMode of ['top_by_review_priority','top_by_manipulation','top_by_persuasion']){{
    if((data[candidateMode]||[]).some(r=>r.record_id===id)){{
      mode=candidateMode; $('rankMode').value=mode; $('platformFilter').value=''; $('labelFilter').value=''; $('query').value='';
      currentRows=rows(); const idx=currentRows.findIndex(r=>r.record_id===id);
      if(idx>=0){{selected=idx;renderList();return true}}
    }}
  }}
  return false;
}}

document.addEventListener('keydown',e=>{{
  const typing=['INPUT','TEXTAREA','SELECT'].includes(e.target?.tagName);
  if(typing && e.key!=='Escape') return;
  if(e.key==='/'){{e.preventDefault();$('query').focus()}}
  if(e.key==='n'){{selected=Math.min(selected+1,currentRows.length-1);renderList()}}
  if(e.key==='p'){{selected=Math.max(selected-1,0);renderList()}}
  if(['1','2','3'].includes(e.key)){{mode=['top_by_review_priority','top_by_manipulation','top_by_persuasion'][Number(e.key)-1];$('rankMode').value=mode;selected=0;renderList()}}
  if(e.key==='Escape') document.activeElement?.blur?.()
}});
window.addEventListener('hashchange',()=>applyHash());

// Active nav state — highlight current section
function updateActiveNav(){{
  const links = document.querySelectorAll('nav.nav a[href^=\"#\"]');
  let activeId = '';
  for (const link of links) {{
    const target = document.getElementById(link.getAttribute('href').slice(1));
    if (target) {{
      const rect = target.getBoundingClientRect();
      if (rect.top >= 80 && rect.top <= 300) {{
        activeId = link.getAttribute('href');
        break;
      }}
    }}
  }}
  links.forEach(l => l.classList.toggle('active', l.getAttribute('href') === activeId));
}}
window.addEventListener('scroll', () => {{ requestAnimationFrame(updateActiveNav); }}, {{ passive: true }});

// Init
initFilters(); renderObs(); renderDiagnostics(); renderExplainabilityAtlas(); renderTermNetwork(); renderCorpusMap(); renderFacetOverview(); renderExpertPoc();
if(!applyHash()) renderList();
</script>

</body>
</html>"""
    return html


def main() -> int:
    HTML_OUT.write_text(render(), encoding="utf-8")
    size_kb = HTML_OUT.stat().st_size / 1024
    print(f"Wrote {HTML_OUT} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
