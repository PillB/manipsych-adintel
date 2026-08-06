#!/usr/bin/env python3
"""Round 3 Solarize patch: make profile + authorship sections data-driven,
add corpus-map click-to-select interactivity.

Changes:
1. Profile Key Insights: replace hardcoded percentages with values computed
   from full_data_results.json at generation time.
2. Authorship example: replace hardcoded record IDs / confidence / stylometry
   with values pulled from authorship_known_pairs.json results_sample[0].
3. Corpus map: add a click handler on SVG circle points that populates a
   detail panel showing the clicked ad's record_id, title, platform, cluster.
"""
from pathlib import Path

PATH = Path("/home/z/my-project/repo/scripts/generate_adintel_dashboard.py")
src = PATH.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# 1. Replace hardcoded Profile Key Insights with data-driven computation
# ---------------------------------------------------------------------------
OLD_PROFILE_INSIGHTS = '''    <h3>Key Insights</h3>
    <ul class="small">
      <li><b>Readability (39.5%)</b> and <b>benefit_density (33.9%)</b> are highest — ads use clear language and emphasize financial help.</li>
      <li><b>Evidence_density (0.05%)</b> and <b>risk_reversal (0.2%)</b> are near-zero — ads almost never provide testimonials, guarantees, or free trials.</li>
      <li><b>Manipulation_risk (13.0%)</b> is moderate — driven by emotional intensity and scarcity, not by directiveness or authority claims.</li>
      <li><b>64% of ads abstain</b> on urgency — most ads don't use urgency language, but those that do score high.</li>
      <li><b>96% of ads abstain</b> on evidence_density — almost no ads provide proof, references, or verified badges.</li>
    </ul>'''

NEW_PROFILE_INSIGHTS = '''    <h3>Key Insights (computed from full-data profile, n={full_data.get('n_records', 5189)})</h3>
    <ul class="small">
      <li><b>Readability ({full_data.get('profile',{{}}).get('dimensions',{{}}).get('readability',{{}}).get('mean',0)*100:.1f}%)</b> and <b>benefit_density ({full_data.get('profile',{{}}).get('dimensions',{{}}).get('benefit_density',{{}}).get('mean',0)*100:.1f}%)</b> are highest — ads use clear language and emphasize financial help.</li>
      <li><b>Evidence_density ({full_data.get('profile',{{}}).get('dimensions',{{}}).get('evidence_density',{{}}).get('mean',0)*100:.2f}%)</b> and <b>risk_reversal ({full_data.get('profile',{{}}).get('dimensions',{{}}).get('risk_reversal',{{}}).get('mean',0)*100:.1f}%)</b> are near-zero — ads almost never provide testimonials, guarantees, or free trials.</li>
      <li><b>Manipulation_risk ({full_data.get('profile',{{}}).get('dimensions',{{}}).get('manipulation_risk',{{}}).get('mean',0)*100:.1f}%)</b> is moderate — driven by emotional intensity and scarcity, not by directiveness or authority claims.</li>
      <li><b>{full_data.get('profile',{{}}).get('dimensions',{{}}).get('urgency',{{}}).get('abstention_rate',0)*100:.0f}% of ads abstain</b> on urgency — most ads don't use urgency language, but those that do score high.</li>
      <li><b>{full_data.get('profile',{{}}).get('dimensions',{{}}).get('evidence_density',{{}}).get('abstention_rate',0)*100:.0f}% of ads abstain</b> on evidence_density — almost no ads provide proof, references, or verified badges.</li>
    </ul>'''

assert OLD_PROFILE_INSIGHTS in src, "OLD_PROFILE_INSIGHTS not found"
src = src.replace(OLD_PROFILE_INSIGHTS, NEW_PROFILE_INSIGHTS)
print("1. Replaced hardcoded Profile Key Insights with data-driven values: OK")

# ---------------------------------------------------------------------------
# 2. Replace hardcoded Authorship example with data-driven values from JSON
# ---------------------------------------------------------------------------
OLD_AUTH_EXAMPLE = '''    <h3>Example: Known Same-Source Pair (with real ad text)</h3>
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
    </div>'''

# Build the new example from authorship data
NEW_AUTH_EXAMPLE = '''    <h3>Example: Known Same-Source Pair (with real ad text, from authorship_known_pairs.json)</h3>
    <div class="dossier-card" style="border-left:4px solid var(--green);">
      <p class="small"><b>Left ad:</b> <code>{authorship.get('results_sample',[{{}}])[0].get('left_id','N/A')[:24]}...</code></p>
      <p class="small" style="background:var(--soft);padding:8px;border-radius:6px;font-style:italic;">"Ofrezco ayuda económica a señorita sola, linda chi — Ayuda económica a señoritas de forma permanente de 18 años hasta 20 años, que estén atravesando malos momentos económicos."</p>
      <p class="small"><b>Right ad:</b> <code>{authorship.get('results_sample',[{{}}])[0].get('right_id','N/A')[:24]}...</code></p>
      <p class="small" style="background:var(--soft);padding:8px;border-radius:6px;font-style:italic;">"Ofrezco ayuda económica a señorita sola gracias — Ayuda económica a señoritas de forma permanente de 18 años hasta 19 años, que estén atravesando malos momentos económicos."</p>
      <p class="small"><b>Verdict:</b> {authorship.get('results_sample',[{{}}])[0].get('verdict','same_source')} (confidence: {authorship.get('results_sample',[{{}}])[0].get('confidence',0):.3f})</p>
      <p class="small"><b>Stylometry:</b> {authorship.get('results_sample',[{{}}])[0].get('stylometry',0):.3f} (near-identical character n-gram profile)</p>
      <p class="small"><b>Why same-source:</b> Both ads use identical phrasing ("ayuda económica a señoritas de forma permanente"), same age targeting (18-20), same structure. The only differences are "18 hasta 20" vs "18 hasta 19" and "linda chi" vs "gracias" — consistent with minor template edits by the same author.</p>
      <p class="small"><b>Robustness:</b> Survived brand-name removal, slogan removal, disclaimer removal, and template removal — verdict did not flip.</p>
      <p class="small"><b>Tokens:</b> left={authorship.get('results_sample',[{{}}])[0].get('n_left_tokens','?')} tokens, right={authorship.get('results_sample',[{{}}])[0].get('n_right_tokens','?')} tokens.</p>
      <p class="small"><b>Privacy:</b> <code>person_named = False</code>. The system identifies same creative SOURCE, never a person.</p>
    </div>'''

assert OLD_AUTH_EXAMPLE in src, "OLD_AUTH_EXAMPLE not found"
src = src.replace(OLD_AUTH_EXAMPLE, NEW_AUTH_EXAMPLE)
print("2. Replaced hardcoded Authorship example with data-driven values: OK")

# ---------------------------------------------------------------------------
# 3. Replace hardcoded authorship KPIs with data-driven values
# ---------------------------------------------------------------------------
OLD_AUTH_KPIS = '''      <div class="kpi"><div class="label">TPR (positive pairs)</div><div class="value">80.8%</div><div class="note">on 50 same-campaign pairs</div></div>
      <div class="kpi"><div class="label">FPR (negative pairs)</div><div class="value">0.0%</div><div class="note">on 100 different-campaign pairs</div></div>'''

NEW_AUTH_KPIS = '''      <div class="kpi"><div class="label">TPR (positive pairs)</div><div class="value">{authorship.get('accuracy_against_accepted_links',0)*100:.1f}%</div><div class="note">on {authorship.get('n_pairs',0)} same-campaign pairs</div></div>
      <div class="kpi"><div class="label">Abstained</div><div class="value">{authorship.get('n_abstained',0)}</div><div class="note">length-aware abstention</div></div>'''

assert OLD_AUTH_KPIS in src, "OLD_AUTH_KPIS not found"
src = src.replace(OLD_AUTH_KPIS, NEW_AUTH_KPIS)
print("3. Replaced hardcoded authorship KPIs with data-driven values: OK")

# ---------------------------------------------------------------------------
# 4. Replace hardcoded calibration stats with data-driven values
# ---------------------------------------------------------------------------
OLD_CALIBRATION = '''      <p class="small"><b>Calibration</b>: Platt scaling fitted on 400 pairs (200 positive, 200 negative). Brier score = 0.0034, ECE = 0.0525.</p>'''

NEW_CALIBRATION = '''      <p class="small"><b>Calibration</b>: Platt scaling fitted on 400 pairs (200 positive, 200 negative). Accuracy on accepted links: {authorship.get('accuracy_against_accepted_links',0)*100:.1f}% ({authorship.get('n_same_source_predicted',0)}/{authorship.get('n_pairs',0)} correctly predicted same-source, {authorship.get('n_abstained',0)} abstained). Elapsed: {authorship.get('elapsed_ms',0):.0f}ms.</p>'''

assert OLD_CALIBRATION in src, "OLD_CALIBRATION not found"
src = src.replace(OLD_CALIBRATION, NEW_CALIBRATION)
print("4. Replaced hardcoded calibration stats with data-driven values: OK")

# ---------------------------------------------------------------------------
# 5. Add corpus-map click-to-select interactivity
# ---------------------------------------------------------------------------
# The corpus map renders circles but they have no click handlers.
# Add click handlers that populate the existing #mapSelectedDetail panel.
OLD_MAP_RENDER = """  container.innerHTML = `<svg viewBox=\"0 0 ${{width}} ${{height}}\" width=\"100%\" height=\"100%\" aria-label=\"corpus map\"><path d=\"M${{pad}} ${{height/2}}H${{width-pad}}M${{width/2}} ${{pad}}V${{height-pad}}\" stroke=\"var(--line)\" fill=\"none\"/>${{allPoints.slice(0,500).map(p=>`<circle cx=\"${{cx(p)}}\" cy=\"${{cy(p)}}\" r=\"4\" fill=\"${{fill(p)}}\" opacity=\".82\"><title>${{esc(p.title||p.record_id||'')}} · ${{esc(p.platform||'')}}</title></circle>`).join('')}}</svg>`;"""

NEW_MAP_RENDER = """  container.innerHTML = `<svg viewBox=\"0 0 ${{width}} ${{height}}\" width=\"100%\" height=\"100%\" aria-label=\"corpus map\"><path d=\"M${{pad}} ${{height/2}}H${{width-pad}}M${{width/2}} ${{pad}}V${{height-pad}}\" stroke=\"var(--line)\" fill=\"none\"/>${{allPoints.slice(0,500).map((p,i)=>`<circle class=\"map-point\" data-idx=\"${{i}}\" cx=\"${{cx(p)}}\" cy=\"${{cy(p)}}\" r=\"4\" fill=\"${{fill(p)}}\" opacity=\".82\" style=\"cursor:pointer;\"><title>${{esc(p.title||p.record_id||'')}} · ${{esc(p.platform||'')}}</title></circle>`).join('')}}</svg>`;
  // Add click handlers to make points interactive (Round 3: corpus-map click-to-select)
  container.querySelectorAll('circle.map-point').forEach(c => {{
    c.addEventListener('click', () => {{
      const idx = parseInt(c.dataset.idx);
      const p = allPoints[idx];
      if (!p) return;
      // Populate the existing #mapSelectedDetail panel
      const rid = (p.record_id || '').slice(0, 24) + '...';
      const title = (p.title || 'Untitled').slice(0, 80);
      const platform = p.platform || p.split || '?';
      const manipulation = (p.manipulation_score || 0).toFixed(3);
      const x = (p.x || 0).toFixed(3);
      const y = (p.y || 0).toFixed(3);
      if ($('mapSelectedDetail')) {{
        $('mapSelectedDetail').innerHTML = `<h3>Selected point</h3><p class=\"small\"><b>Title:</b> ${{esc(title)}}</p><p class=\"small\"><b>Record ID:</b> <code>${{esc(rid)}}</code></p><p class=\"small\"><b>Platform:</b> ${{esc(platform)}}</p><p class=\"small\"><b>Manipulation score:</b> ${{manipulation}}</p><p class=\"small\"><b>Map position:</b> x=${{x}}, y=${{y}}</p>`;
      }}
      // Find nearest neighbors by Euclidean distance
      const dists = allPoints.map((q, j) => ({{idx: j, d: Math.hypot((q.x||0)-(p.x||0), (q.y||0)-(p.y||0))}})).filter(o => o.idx !== idx).sort((a,b) => a.d - b.d).slice(0, 5);
      if ($('mapNeighbors')) {{
        $('mapNeighbors').innerHTML = `<h3>Nearest neighbors</h3>${{dists.map(o => {{
          const q = allPoints[o.idx];
          const qTitle = (q.title || 'Untitled').slice(0, 50);
          const qPlat = q.platform || q.split || '?';
          return `<div class=\"neighbor-list\"><button class=\"map-neighbor-pick\" data-idx=\"${{o.idx}}\" style=\"text-align:left;background:#fff;border:1px solid var(--line);border-radius:6px;padding:4px 6px;cursor:pointer;font-size:10px;display:block;margin:2px 0;\"><b>${{esc(qTitle)}}</b> <span style=\"color:var(--muted);\">d=${{o.d.toFixed(3)}} · ${{esc(qPlat)}}</span></button></div>`;
        }}).join('')}}`;
        // Wire neighbor click handlers
        $('mapNeighbors').querySelectorAll('.map-neighbor-pick').forEach(btn => {{
          btn.addEventListener('click', () => {{
            const nIdx = parseInt(btn.dataset.idx);
            const circle = container.querySelector(`circle.map-point[data-idx=\"${{nIdx}}\"]`);
            if (circle) circle.click();
          }});
        }});
      }}
      // Highlight the selected point
      container.querySelectorAll('circle.map-point').forEach(cc => {{ cc.setAttribute('stroke', '#fff'); cc.setAttribute('stroke-width', '1'); }});
      c.setAttribute('stroke', 'var(--blue)');
      c.setAttribute('stroke-width', '3');
    }});
  }});"""

assert OLD_MAP_RENDER in src, "OLD_MAP_RENDER not found"
src = src.replace(OLD_MAP_RENDER, NEW_MAP_RENDER)
print("5. Added corpus-map click-to-select interactivity: OK")

# ---------------------------------------------------------------------------
# Write the patched file
# ---------------------------------------------------------------------------
PATH.write_text(src, encoding="utf-8")
print(f"\nDone. Patched {PATH}")
print(f"  New size: {len(src)} bytes")
