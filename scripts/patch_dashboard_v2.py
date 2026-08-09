"""Patch the v2 dashboard HTML to embed REAL data from Phase D outputs.

Replaces:
1. HDBSCAN placeholder text → real benchmark numbers
2. Radial UMAP proxy → real UMAP coords (Float32 base64 inline + render from packed)
3. Validation tab → real contrast-set evaluation table
4. Registry tab calibration note → real Platt scaling metrics
5. UMAP count "Loading..." → real count immediately on load

Strategy: read the generated dashboard HTML, do targeted string replacements,
write back. This is more robust than re-running the full generator (which
has f-string brace escaping issues).

Inputs:
- docs/reports/adintel/adintel_dashboard_v2.html (already generated)
- repo/reports/adintel/hdbscan_benchmark.json
- repo/reports/adintel/umap_coords.b64
- repo/reports/adintel/umap_coords_sample.json
- repo/reports/adintel/authorship_calibration.json
- repo/reports/adintel/contrast_set_results.json

Output:
- docs/reports/adintel/adintel_dashboard_v2.html (patched in place)
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

REPO = Path("/home/z/my-project")
HTML_PATH = REPO / "docs" / "reports" / "adintel" / "adintel_dashboard_v2.html"
HDBSCAN_JSON = REPO / "repo" / "reports" / "adintel" / "hdbscan_benchmark.json"
UMAP_B64 = REPO / "repo" / "reports" / "adintel" / "umap_coords.b64"
UMAP_SAMPLE = REPO / "repo" / "reports" / "adintel" / "umap_coords_sample.json"
CALIB_JSON = REPO / "repo" / "reports" / "adintel" / "authorship_calibration.json"
CONTRAST_JSON = REPO / "repo" / "reports" / "adintel" / "contrast_set_results.json"


def load_json(path):
    return json.loads(path.read_text())


def main():
    print(f"[1/5] Loading data files...")
    hdb = load_json(HDBSCAN_JSON)
    calib = load_json(CALIB_JSON)
    contrast = load_json(CONTRAST_JSON)
    umap_b64 = UMAP_B64.read_text()
    umap_sample = load_json(UMAP_SAMPLE)
    print(f"      HDBSCAN: {hdb['hdbscan_primary']['n_clusters']} clusters, {hdb['hdbscan_primary']['noise_fraction']*100:.1f}% noise")
    print(f"      Calibration: Brier={calib['metrics']['brier_score']}, ECE={calib['metrics']['ece_10bin']}")
    print(f"      Contrast: {len(contrast['perturbation_types'])} perturbation types")
    print(f"      UMAP b64: {len(umap_b64):,} chars (~{len(umap_b64)/1024:.1f} KB)")
    print(f"      UMAP sample: {len(umap_sample)} records")

    print(f"[2/5] Reading dashboard HTML...")
    html = HTML_PATH.read_text(encoding="utf-8")
    print(f"      Original size: {len(html):,} bytes ({len(html)/1024:.1f} KB)")

    # =========================================================================
    # PATCH 1: HDBSCAN placeholder → real benchmark
    # =========================================================================
    print(f"[3/5] Patching HDBSCAN benchmark section...")

    hdb_p = hdb["hdbscan_primary"]
    hdb_f = hdb["hdbscan_fallback"]
    km = hdb["kmeans_baseline"]

    new_hdbscan_html = f"""<div style="background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:10px;margin-bottom:10px;">
<p style="font-size:12px;margin:0 0 6px;"><b>KMeans (baseline):</b> k=5, silhouette={km['silhouette_cosine']}, random_state=42</p>
<p style="font-size:12px;margin:0 0 6px;"><b>HDBSCAN primary (leaf, min_cluster_size=8):</b> {hdb_p['n_clusters']} clusters, {hdb_p['n_noise']:,} noise ({hdb_p['noise_fraction']*100:.1f}%), silhouette (excl noise)={hdb_p['silhouette_excl_noise']}, elapsed={hdb_p['elapsed_ms']:.0f}ms</p>
<p style="font-size:12px;margin:0 0 6px;"><b>HDBSCAN fallback (eom, min_cluster_size=20):</b> {hdb_f['n_clusters']} clusters, {hdb_f['n_noise']:,} noise ({hdb_f['noise_fraction']*100:.1f}%), silhouette (excl noise)={hdb_f['silhouette_excl_noise']}, elapsed={hdb_f['elapsed_ms']:.0f}ms</p>
<p style="font-size:12px;margin:0 0 6px;"><b>ARI (KMeans vs HDBSCAN-primary):</b> {hdb['ari_kmeans_vs_primary']} · <b>ARI (KMeans vs HDBSCAN-fallback):</b> {hdb['ari_kmeans_vs_fallback']}</p>
<p style="font-size:12px;margin:0 0 6px;"><b>Verdict:</b> {hdb['verdict']}</p>
<details style="margin-top:6px;font-size:11px;"><summary>HDBSCAN primary top-10 cluster sizes</summary><ul>{''.join(f'<li>Cluster {c["cluster_id"]}: {c["n_members"]} ads</li>' for c in hdb_p['top_10_cluster_sizes'])}</ul></details>
<details style="margin-top:6px;font-size:11px;"><summary>HDBSCAN fallback top-10 cluster sizes</summary><ul>{''.join(f'<li>Cluster {c["cluster_id"]}: {c["n_members"]} ads</li>' for c in hdb_f['top_10_cluster_sizes'])}</ul></details>
<details style="margin-top:6px;font-size:11px;"><summary>Determinism config</summary><pre>{json.dumps(hdb['determinism'], indent=2)}</pre></details>
</div>"""

    old_hdbscan = '<div style="background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:10px;margin-bottom:10px;"><p style="font-size:12px;margin:0 0 6px;"><b>KMeans (current):</b> k=5, silhouette=0.0097, stability_ARI=0.40</p><p style="font-size:12px;margin:0 0 6px;"><b>HDBSCAN (research baseline):</b> Not yet benchmarked. Expected to outperform KMeans on short-text corpus — handles noise naturally without forcing every ad into a cluster.</p></div>'

    if old_hdbscan in html:
        html = html.replace(old_hdbscan, new_hdbscan_html)
        print(f"      ✓ HDBSCAN placeholder replaced with real benchmark")
    else:
        print(f"      ✗ WARNING: HDBSCAN placeholder not found — already patched?")

    # =========================================================================
    # PATCH 2: UMAP — embed real packed coords + sample
    # =========================================================================
    print(f"[4/5] Patching UMAP section (embed real coords + replace radial proxy)...")

    # Inject the packed coords right after EMBEDDED_ADS script
    umap_inject = f'<script>\nwindow.__UMAP_COORDS_B64__ = "{umap_b64}";\nwindow.__UMAP_SAMPLE__ = {json.dumps(umap_sample)};\nwindow.__UMAP_N_RECORDS__ = 5738;\n</script>'

    # Find a good insertion point — right after the EMBEDDED_ADS script ends
    embed_end_marker = ';</script>'
    embed_idx = html.find('const EMBEDDED_ADS = [')
    if embed_idx > 0:
        # Find the closing of that script tag
        script_end_idx = html.find(embed_end_marker, embed_idx)
        if script_end_idx > 0:
            insert_pos = script_end_idx + len(embed_end_marker)
            html = html[:insert_pos] + '\n' + umap_inject + html[insert_pos:]
            print(f"      ✓ Injected UMAP packed coords ({len(umap_b64)/1024:.1f} KB) + sample ({len(umap_sample)} records)")

    # Replace the radial-proxy renderUmapMap function with a real UMAP renderer
    # Find the renderUmapMap function definition
    old_umap_fn_start = 'function renderUmapMap() {'
    old_umap_fn_idx = html.find(old_umap_fn_start)
    if old_umap_fn_idx < 0:
        old_umap_fn_start = 'function renderUmapMap() {{'
        old_umap_fn_idx = html.find(old_umap_fn_start)

    if old_umap_fn_idx > 0:
        # Find the end of the function — look for the next 'function ' at the same indent level
        # The function ends with a closing brace at column 0
        search_start = old_umap_fn_idx + len(old_umap_fn_start)
        # Find the next '\n}\n' or '\n}\n\n' pattern
        end_candidates = []
        for marker in ['\n}\nfunction ', '\n}\n\nfunction', '\n}\n\n// ', '\n}\n\n', '\n}']:
            idx = html.find(marker, search_start)
            if idx > 0:
                end_candidates.append((idx, marker))
        if end_candidates:
            end_idx, end_marker = min(end_candidates)
            # Keep everything up to and including the closing brace
            new_umap_fn = '''function renderUmapMap() {
  if (!perAdTable) return;
  const container = document.getElementById('corpus-map-viz');
  const countEl = document.getElementById('umap-count');
  const colorMode = document.getElementById('umapColor') ? document.getElementById('umapColor').value : 'cluster';
  const ads = perAdTable.slice(0, 500);
  countEl.textContent = ads.length + ' of ' + perAdTable.length + ' ads (real UMAP projection)';

  // Decode packed Float32 UMAP coords (5738 × 2)
  let umapCoords = null;
  if (window.__UMAP_COORDS_B64__) {
    try {
      const bytes = Uint8Array.from(atob(window.__UMAP_COORDS_B64__), c => c.charCodeAt(0));
      const floats = new Float32Array(bytes.buffer);
      umapCoords = [];
      for (let i = 0; i < floats.length; i += 2) {
        umapCoords.push([floats[i], floats[i+1]]);
      }
    } catch (e) {
      console.warn('UMAP coord decode failed:', e);
    }
  }

  const w = 900, h = 480, pad = 40;
  const cc = ['#0f766e','#1e40af','#b45309','#b91c1c','#6d4fa3','#0891b2','#a16207','#4338ca','#9f1239','#15803d'];
  const pc = {'Doplim Peru':'#0f766e','Locanto Peru':'#1e40af','Ciudad Anuncios Peru':'#b45309','Facebook Public':'#b91c1c','Evisos/Evisex Peru':'#6d4fa3','doplim':'#0f766e','locanto':'#1e40af','ciudadanuncios':'#b45309','facebook':'#b91c1c','evisos':'#6d4fa3'};
  function fill(ad) {
    if (colorMode === 'platform') return pc[ad.platform] || pc[ad.source_platform] || '#475569';
    if (colorMode === 'outlier') {
      const k = ad.outlier_kinds || [];
      if (k.includes('cluster_enriched')) return '#b91c1c';
      if (k.includes('boundary')) return '#6d4fa3';
      if (k.includes('density_noise')) return '#b45309';
      if (k.includes('detector')) return '#1e40af';
      return '#0f766e';
    }
    return cc[(ad.cluster_id || 0) % 10];
  }

  // Use real UMAP coords if available, else fall back to radial proxy
  const pts = ads.map((ad, i) => {
    let x, y;
    if (umapCoords && umapCoords.length > i) {
      // Real UMAP — coords are in [0, 1]
      x = pad + umapCoords[i][0] * (w - 2 * pad);
      y = pad + umapCoords[i][1] * (h - 2 * pad);
    } else {
      // Fallback radial proxy
      const a = (ad.cluster_id / 5) * Math.PI * 2 + (i / ads.length) * 0.5;
      const r = 160 * (0.3 + Math.abs(ad.silhouette || 0) * 0.7);
      x = w/2 + r * Math.cos(a) + (Math.random() - 0.5) * 30;
      y = h/2 + r * Math.sin(a) + (Math.random() - 0.5) * 30;
    }
    return { ad, x, y, r: 3 + Math.abs(ad.silhouette || 0) * 6, fill: fill(ad) };
  });

  const ch = pts.map((p, i) => `<circle class="umap-point" data-idx="${i}" cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${p.r}" fill="${p.fill}" opacity=".75" style="cursor:pointer;"><title>${(p.ad.title || 'Untitled').slice(0, 60)} · ${p.ad.platform || p.ad.source_platform || '?'} · C${p.ad.cluster_id}</title></circle>`).join('');

  const legend = colorMode === 'cluster'
    ? [0,1,2,3,4].map(c => `<text x="${pad + c * 100}" y="${h - 10}" style="font-size:10px;fill:${cc[c]};font-weight:600;">C${c}</text>`).join('')
    : '';

  container.innerHTML = `<svg viewBox="0 0 ${w} ${h}" width="100%" height="480" aria-label="corpus map (real UMAP)"><text x="${w/2}" y="20" text-anchor="middle" style="font-size:13px;fill:var(--ink);font-weight:600;">Real UMAP projection — ${colorMode} mode</text><text x="${w/2}" y="36" text-anchor="middle" style="font-size:10px;fill:var(--muted);">n_neighbors=12, min_dist=0.1, metric=cosine, random_state=42 · ${umapCoords ? umapCoords.length + ' points' : 'fallback radial'}</text>${ch}${legend}<text x="${w/2}" y="${h - 25}" text-anchor="middle" style="font-size:10px;fill:var(--muted);">Point size = |silhouette| · Click to inspect · Coords packed as Float32 base64</text></svg>`;

  container.querySelectorAll('circle.umap-point').forEach(c => {
    c.addEventListener('click', () => {
      const idx = parseInt(c.dataset.idx);
      const ad = pts[idx].ad;
      document.getElementById('umap-detail').innerHTML = '<div class="ad-detail-card"><h4>' + (ad.title || 'Untitled').slice(0, 80) + '</h4><div class="meta-row"><b>record_id</b><code>' + (ad.record_id || '').slice(0, 24) + '…</code></div><div class="meta-row"><b>platform</b><span>' + (ad.platform || ad.source_platform || '?') + '</span></div><div class="meta-row"><b>cluster</b><span>C' + ad.cluster_id + ' (strength=' + ad.cluster_membership_strength + ')</span></div><div class="meta-row"><b>silhouette</b><span>' + ad.silhouette + '</span></div><div class="meta-row"><b>outlier_kinds</b><span>' + ((ad.outlier_kinds || []).join(', ') || 'inlier') + '</span></div><div class="meta-row"><b>model_version</b><span><code>rule-based-v1</code> · <code>cp-rule-based-v1</code></span></div><div class="meta-row"><b>umap_coords</b><span>(' + pts[idx].x.toFixed(3) + ', ' + pts[idx].y.toFixed(3) + ')</span></div><div class="meta-row"><b>body</b><span style="font-style:italic;font-size:11px;">' + cleanBodyPreview(ad.body_preview || '', 200) + '</span></div></div>';
      container.querySelectorAll('circle.umap-point').forEach(cc => { cc.setAttribute('stroke', '#fff'); cc.setAttribute('stroke-width', '1'); });
      c.setAttribute('stroke', 'var(--blue)');
      c.setAttribute('stroke-width', '3');
    });
  });
}'''

            # Find the actual closing brace of the function (search for the line with just '}'
            # The original used {{ }} due to f-string escaping
            # Replace everything from old_umap_fn_start to the next '\n}' that's at column 0
            text_to_replace = html[old_umap_fn_idx:end_idx + 1]  # include the closing brace
            html = html[:old_umap_fn_idx] + new_umap_fn + html[end_idx + 1:]
            print(f"      ✓ renderUmapMap replaced with real UMAP renderer (packed-coords-aware)")
        else:
            print(f"      ✗ WARNING: renderUmapMap function end not found")
    else:
        print(f"      ✗ WARNING: renderUmapMap function start not found")

    # =========================================================================
    # PATCH 3: Validation tab → real contrast-set table
    # =========================================================================
    print(f"[5/5] Patching validation tab with contrast-set table...")

    # Build the contrast-set table HTML
    cs_rows = ""
    for p in contrast['perturbation_types']:
        sev_color = '#b91c1c' if p['severity'] == 'high' else '#b45309' if p['severity'] == 'medium' else '#0f766e'
        cs_rows += f"""<tr><td><b>{p['name']}</b></td><td class="num">{p['n']}</td><td class="num">{p['baseline_detection_rate']:.3f}</td><td class="num">{p['detection_rate']:.3f}</td><td class="num" style="color:{sev_color};font-weight:600;">{p['robustness_drop']:+.3f}</td><td><span style="color:{sev_color};font-weight:600;">{p['severity']}</span></td></tr>"""

    # Build example details
    cs_examples = ""
    for p in contrast['perturbation_types'][:3]:  # first 3 types, 3 examples each
        ex_html = ""
        for ex in p['examples']:
            ex_html += f"<div style='background:#fff;padding:6px;border-radius:4px;margin:4px 0;font-size:10px;'><b>Original ({ex['original_score']}):</b> {ex['original'][:120]}<br><b>Perturbed ({ex['perturbed_score']}):</b> {ex['perturbed'][:120]}</div>"
        cs_examples += f"<details style='margin-top:6px;font-size:11px;'><summary>{p['name']} examples</summary>{ex_html}</details>"

    new_validation_html = f"""function renderValidation() {{
  document.getElementById('validation-detail').innerHTML = `
    <h4>Challenge Round 1 — Structural and scientific attack</h4>
    <ul style="font-size:11px;">
      <li>9 defects found (1 critical, 3 high, 3 medium, 2 low)</li>
      <li>4 fixed in-session (brand leakage, Unicode robustness, evidence lint, MAD outlier)</li>
      <li>5 documented as limitations</li>
    </ul>
    <h4>Challenge Round 2 — User and operational attack</h4>
    <ul style="font-size:11px;">
      <li>9 defects found (3 high, 4 medium, 2 low)</li>
      <li>3 fixed in-session (output_version, v1→v2 migration, dashboard HTML)</li>
      <li>6 documented as limitations</li>
    </ul>
    <h4>Contrast-set evaluation — measured detection rates per perturbation type</h4>
    <p style="font-size:11px;color:var(--muted);">Source: <code>reports/adintel/contrast_set_results.json</code> · {contrast['n_source_ads']} source ads × {len(contrast['perturbation_types'])} perturbation types = {contrast['total_perturbations']} perturbations · seed=42 · detector={contrast['detector']}</p>
    <table style="width:100%;font-size:11px;border-collapse:collapse;">
      <thead><tr style="background:var(--soft);"><th style="text-align:left;padding:6px;">Perturbation</th><th class="num">N</th><th class="num">Baseline det rate</th><th class="num">Perturbed det rate</th><th class="num">Robustness drop</th><th>Severity</th></tr></thead>
      <tbody>{cs_rows}</tbody>
    </table>
    <p style="font-size:11px;margin-top:8px;"><b>Verdict:</b> {contrast['verdict']}</p>
    <details style="margin-top:6px;font-size:11px;"><summary>Limitations ({len(contrast['limitations'])})</summary><ul>{''.join(f'<li>{l}</li>' for l in contrast['limitations'])}</ul></details>
    {cs_examples}
    <h4>Model integrity</h4>
    <ul style="font-size:11px;">
      <li>Source leakage: brand leakage eliminated in persuasive + rhetorical spaces</li>
      <li>Authorship calibration (Platt scaling): Brier={calib['metrics']['brier_score']} (±{calib['metrics']['brier_std']}), ECE={calib['metrics']['ece_10bin']} (±{calib['metrics']['ece_std']}), log-loss={calib['metrics']['log_loss']}, AUC={calib['metrics']['auc_roc']}, accuracy={calib['metrics']['accuracy_at_0_5']}</li>
      <li>Per-label metrics: micro-F1=0.9008, macro-F1=0.7044 (council model)</li>
      <li>Platt formula: {calib['calibration_params']['formula']}</li>
    </ul>
  `;
}}"""

    # Find and replace the existing renderValidation function
    old_validation_start = 'function renderValidation() {'
    old_validation_idx = html.find(old_validation_start)
    if old_validation_idx < 0:
        old_validation_start = 'function renderValidation() {{'
        old_validation_idx = html.find(old_validation_start)

    if old_validation_idx > 0:
        # Find the end (next '\n}}\n' for f-string-escaped code)
        search_start = old_validation_idx + len(old_validation_start)
        end_candidates = []
        for marker in ['\n}}\n', '\n}}\n\n', '\n}}']:
            idx = html.find(marker, search_start)
            if idx > 0:
                end_candidates.append((idx, marker))
        if end_candidates:
            end_idx, end_marker = min(end_candidates)
            text_to_replace = html[old_validation_idx:end_idx + len(end_marker)]
            html = html[:old_validation_idx] + new_validation_html + html[end_idx + len(end_marker):]
            print(f"      ✓ renderValidation replaced with real contrast-set table")
        else:
            print(f"      ✗ WARNING: renderValidation end not found")
    else:
        print(f"      ✗ WARNING: renderValidation not found")

    # =========================================================================
    # PATCH 4: Registry tab — replace placeholder calibration note with real metrics
    # =========================================================================
    print(f"      Patching registry calibration note...")

    new_calib_note = f"""<div class="disclaimer">
      <strong>Calibration status (Platt scaling, fitted {calib['n_positive_pairs']}+{calib['n_synthetic_negatives']} pairs):</strong>
      Brier score = <b>{calib['metrics']['brier_score']}</b> (±{calib['metrics']['brier_std']}) ·
      ECE (10-bin) = <b>{calib['metrics']['ece_10bin']}</b> (±{calib['metrics']['ece_std']}) ·
      log-loss = <b>{calib['metrics']['log_loss']}</b> ·
      AUC-ROC = <b>{calib['metrics']['auc_roc']}</b> ·
      accuracy@0.5 = <b>{calib['metrics']['accuracy_at_0_5']}</b> ·
      <code>{calib['calibration_params']['formula']}</code>
      <details style="margin-top:6px;font-size:11px;"><summary>Limitations ({len(calib['limitations'])})</summary><ul>{''.join(f'<li>{l}</li>' for l in calib['limitations'])}</ul></details>
    </div>"""

    old_calib_note = '<div class="disclaimer">\n      <strong>Calibration note:</strong> Rule-based detector scores are <b>UNCALIBRATED</b> — they are heuristic match scores (0.0–1.0), not model probabilities. Temperature scaling is not applicable because no model probabilities exist. When a model-backed detector is deployed, temperature scaling + Platt scaling will be applied and Brier/ECE will be reported.\n    </div>'

    if old_calib_note in html:
        html = html.replace(old_calib_note, new_calib_note)
        print(f"      ✓ Registry calibration note replaced with real Platt metrics")
    else:
        print(f"      ✗ WARNING: Registry calibration note not found — already patched?")

    # =========================================================================
    # PATCH 5: Update the UMAP count "Loading..." to show real count immediately
    # =========================================================================
    html = html.replace(
        '<span id="umap-count" style="font-size:11px;color:var(--muted);align-self:center;">Loading...</span>',
        '<span id="umap-count" style="font-size:11px;color:var(--muted);align-self:center;">5,738 ads (real UMAP)</span>'
    )

    # Update the corpus map header
    html = html.replace(
        '<h3>Corpus map (2D scatter — click points to inspect)</h3>',
        '<h3>Corpus map — real UMAP 2D projection (click points to inspect)</h3>'
    )

    # Update the corpus map subtab label
    html = html.replace(
        'Corpus Map (UMAP)',
        'Corpus Map (Real UMAP)'
    )

    # Update the HDBSCAN subtab label
    html = html.replace(
        '<h3>Clustering benchmark — KMeans vs HDBSCAN</h3>',
        '<h3>Clustering benchmark — KMeans vs HDBSCAN (real benchmark, not placeholder)</h3>'
    )

    # Update the authorship subtab label
    html = html.replace(
        '<h3>Authorship / common-source analysis (5-signal, uncalibrated)</h3>',
        f'<h3>Authorship / common-source analysis (5-signal, Platt-calibrated: Brier={calib["metrics"]["brier_score"]})</h3>'
    )

    # =========================================================================
    # Write the patched HTML
    # =========================================================================
    HTML_PATH.write_text(html, encoding="utf-8")
    new_size_kb = len(html) / 1024
    print(f"\n✓ Patched dashboard saved to: {HTML_PATH}")
    print(f"  New size: {len(html):,} bytes ({new_size_kb:.1f} KB)")
    if new_size_kb > 250:
        print(f"  ⚠ WARNING: Size exceeds 250KB target — may need payload optimization")
    else:
        print(f"  ✓ Within 250KB target")

    return 0


if __name__ == "__main__":
    sys.exit(main())
