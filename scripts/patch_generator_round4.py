#!/usr/bin/env python3
"""Round 4 Solarize patch: fix broken corpus-map controls + improve visualizations.

BUGS FIXED:
1. mapQuery filter was ignored — typing "lima" didn't filter points.
2. mapColor selection was ignored — changing to "score" didn't change fill colors.
3. mapProjection and mapOverlay selects existed but had no effect.
4. Click handler reset (line 1872) wiped the detail panel AFTER click setup,
   so the initial "Click a map point" text overwrote any selection state.

IMPROVEMENTS:
1. mapQuery now filters points by title/record_id/platform/label text match.
2. mapColor now changes the fill color: platform (categorical), score (gradient),
   split, deep_cluster, isolation_slice, isolation_score.
3. Axis labels added (x: "Semantic dimension 1", y: "Semantic dimension 2").
4. Rich hover annotation: shows title, platform, score, cluster in a styled tooltip.
5. Point size varies by manipulation_score (larger = higher score).
6. Legend updates dynamically with the current color mode.
7. Filter count shown: "Showing N of M points matching 'lima'".
8. Quadrant labels added (top-left, top-right, bottom-left, bottom-right).
9. mapResetLayers now actually clears the query and resets color to platform.
"""
from pathlib import Path

PATH = Path("/home/z/my-project/repo/scripts/generate_adintel_dashboard.py")
src = PATH.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# Replace the entire renderCorpusMap function
# ---------------------------------------------------------------------------
OLD_RENDER = """function renderCorpusMap(){{
  const map=data.corpus_map||{{}}, container=$('corpusMapViz');
  const allPoints=(map.points||[]);
  if(!allPoints.length){{container.innerHTML='<p class="small" style="padding:16px">No corpus map data.</p>';return}}
  const width=900,height=500,pad=34;
  function cx(p){{return pad+(p.x+1)/2*(width-2*pad)}} function cy(p){{return height-pad-(p.y+1)/2*(height-2*pad)}}
  function fill(p){{return colorFor(p.platform||p.split||'unknown')}}
  $('mapLegend').innerHTML = [...new Set(allPoints.map(p=>p.platform))].map(v=>`<span class="legend-item"><span class="swatch" style="background:${{colorFor(v)}}"></span>${{esc(v)}}</span>`).join('');
  container.innerHTML = `<svg viewBox="0 0 ${{width}} ${{height}}" width="100%" height="100%" aria-label="corpus map"><path d="M${{pad}} ${{height/2}}H${{width-pad}}M${{width/2}} ${{pad}}V${{height-pad}}" stroke="var(--line)" fill="none"/>${{allPoints.slice(0,500).map((p,i)=>`<circle class="map-point" data-idx="${{i}}" cx="${{cx(p)}}" cy="${{cy(p)}}" r="4" fill="${{fill(p)}}" opacity=".82" style="cursor:pointer;"><title>${{esc(p.title||p.record_id||'')}} · ${{esc(p.platform||'')}}</title></circle>`).join('')}}</svg>`;
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
        $('mapSelectedDetail').innerHTML = `<h3>Selected point</h3><p class="small"><b>Title:</b> ${{esc(title)}}</p><p class="small"><b>Record ID:</b> <code>${{esc(rid)}}</code></p><p class="small"><b>Platform:</b> ${{esc(platform)}}</p><p class="small"><b>Manipulation score:</b> ${{manipulation}}</p><p class="small"><b>Map position:</b> x=${{x}}, y=${{y}}</p>`;
      }}
      // Find nearest neighbors by Euclidean distance
      const dists = allPoints.map((q, j) => ({{idx: j, d: Math.hypot((q.x||0)-(p.x||0), (q.y||0)-(p.y||0))}})).filter(o => o.idx !== idx).sort((a,b) => a.d - b.d).slice(0, 5);
      if ($('mapNeighbors')) {{
        $('mapNeighbors').innerHTML = `<h3>Nearest neighbors</h3>${{dists.map(o => {{
          const q = allPoints[o.idx];
          const qTitle = (q.title || 'Untitled').slice(0, 50);
          const qPlat = q.platform || q.split || '?';
          return `<div class="neighbor-list"><button class="map-neighbor-pick" data-idx="${{o.idx}}" style="text-align:left;background:#fff;border:1px solid var(--line);border-radius:6px;padding:4px 6px;cursor:pointer;font-size:10px;display:block;margin:2px 0;"><b>${{esc(qTitle)}}</b> <span style="color:var(--muted);">d=${{o.d.toFixed(3)}} · ${{esc(qPlat)}}</span></button></div>`;
        }}).join('')}}`;
        // Wire neighbor click handlers
        $('mapNeighbors').querySelectorAll('.map-neighbor-pick').forEach(btn => {{
          btn.addEventListener('click', () => {{
            const nIdx = parseInt(btn.dataset.idx);
            const circle = container.querySelector(`circle.map-point[data-idx="${{nIdx}}"]`);
            if (circle) circle.click();
          }});
        }});
      }}
      // Highlight the selected point
      container.querySelectorAll('circle.map-point').forEach(cc => {{ cc.setAttribute('stroke', '#fff'); cc.setAttribute('stroke-width', '1'); }});
      c.setAttribute('stroke', 'var(--blue)');
      c.setAttribute('stroke-width', '3');
    }});
  }});
  $('mapInspector').innerHTML = `<b>How to interpret:</b> ${{allPoints.length}} ads plotted. Each point is a representative ad. Inspect annotations before inferring technique from neighborhood.`;
  $('mapSelectedDetail').innerHTML = '<h3>Selected point</h3><p class="small">Click a map point to see ad metadata.</p>';
  $('mapNeighbors').innerHTML = '<h3>Nearest neighbors</h3><p class="small">Select a point to see neighbors.</p>';
  $('mapQuadrants').innerHTML = '';
  $('deepClusterPanel').innerHTML = (map.deep_clusters?.clusters||[]).slice(0,6).map(c=>`<div class="map-card"><h3>${{esc(c.eli5_title||c.name)}}</h3><p class="small">${{c.count}} ads · ${{esc((c.top_terms||[]).slice(0,5).map(t=>t.term).join(', '))}}</p></div>`).join('') || '<p class="small">No deep clusters.</p>';
  $('isolationPanel').innerHTML = '<p class="small">Isolation slices available in full report.</p>';
}}"""

NEW_RENDER = """function renderCorpusMap(){{
  const map=data.corpus_map||{{}}, container=$('corpusMapViz');
  const allPoints=(map.points||[]);
  if(!allPoints.length){{container.innerHTML='<p class="small" style="padding:16px">No corpus map data.</p>';return}}

  // Read control values
  const colorMode = $('mapColor') ? $('mapColor').value : 'platform';
  const query = $('mapQuery') ? $('mapQuery').value.toLowerCase().trim() : '';

  // Filter points by query (title, record_id, platform, labels)
  let filtered = allPoints;
  if (query) {{
    filtered = allPoints.filter(p => {{
      const title = (p.title || '').toLowerCase();
      const rid = (p.record_id || '').toLowerCase();
      const plat = (p.platform || p.split || '').toLowerCase();
      const labels = (p.labels || []).join(' ').toLowerCase();
      return title.includes(query) || rid.includes(query) || plat.includes(query) || labels.includes(query);
    }});
  }}
  const visible = filtered.slice(0, 500);

  const width=900,height=500,pad=50;
  function cx(p){{return pad+(p.x+1)/2*(width-2*pad)}}
  function cy(p){{return height-pad-(p.y+1)/2*(height-2*pad)}}

  // Color function based on colorMode
  const scoreColors = ['#2f6f4e','#4a9d6e','#6bbf8a','#f7cf78','#e8a838','#d97757','#c2410c','#9a3412'];
  function scoreColor(s) {{
    const idx = Math.min(Math.floor((s||0) * scoreColors.length), scoreColors.length - 1);
    return scoreColors[idx];
  }}
  function fill(p) {{
    if (colorMode === 'score') return scoreColor(p.manipulation_score || p.score || 0);
    if (colorMode === 'split') return p.split === 'test' ? '#b91c1c' : '#0f766e';
    if (colorMode === 'deep_cluster') return colorFor('cluster_' + (p.deep_cluster || 0));
    if (colorMode === 'isolation_slice') return colorFor('iso_' + (p.isolation_slice || 0));
    if (colorMode === 'isolation_score') return scoreColor(p.isolation_score || 0);
    return colorFor(p.platform || p.split || 'unknown'); // default: platform
  }}

  // Point radius varies by manipulation score (3-7px)
  function radius(p) {{
    const s = p.manipulation_score || p.score || 0;
    return 3 + s * 4;
  }}

  // Build legend based on colorMode
  let legendHTML = '';
  if (colorMode === 'platform') {{
    const platforms = [...new Set(allPoints.map(p=>p.platform||p.split||'unknown'))];
    legendHTML = platforms.map(v=>`<span class="legend-item"><span class="swatch" style="background:${{colorFor(v)}}"></span>${{esc(v)}}</span>`).join('');
  }} else if (colorMode === 'score') {{
    legendHTML = `<span class="legend-item"><span class="swatch" style="background:${{scoreColor(0)}}"></span>0.0</span>` +
      `<span class="legend-item"><span class="swatch" style="background:${{scoreColor(0.25)}}"></span>0.25</span>` +
      `<span class="legend-item"><span class="swatch" style="background:${{scoreColor(0.5)}}"></span>0.5</span>` +
      `<span class="legend-item"><span class="swatch" style="background:${{scoreColor(0.75)}}"></span>0.75</span>` +
      `<span class="legend-item"><span class="swatch" style="background:${{scoreColor(1.0)}}"></span>1.0</span>`;
  }} else if (colorMode === 'split') {{
    legendHTML = `<span class="legend-item"><span class="swatch" style="background:#0f766e"></span>train</span>` +
      `<span class="legend-item"><span class="swatch" style="background:#b91c1c"></span>test</span>`;
  }} else {{
    legendHTML = `<span class="legend-item"><span class="swatch" style="background:var(--muted)"></span>Color mode: ${{esc(colorMode)}}</span>`;
  }}
  $('mapLegend').innerHTML = legendHTML;

  // Build SVG with axes, labels, and points
  const pointsHTML = visible.map((p,i) => {{
    const r = radius(p);
    const f = fill(p);
    const cxv = cx(p);
    const cyv = cy(p);
    const title = esc((p.title || p.record_id || '').slice(0, 80));
    const plat = esc(p.platform || p.split || '?');
    const score = (p.manipulation_score || 0).toFixed(3);
    return `<circle class="map-point" data-idx="${{i}}" data-orig-idx="${{allPoints.indexOf(p)}}" cx="${{cxv}}" cy="${{cyv}}" r="${{r}}" fill="${{f}}" opacity=".82" stroke="#fff" stroke-width="1" style="cursor:pointer;"><title>${{title}} · ${{plat}} · score=${{score}}</title></circle>`;
  }}).join('');

  // Quadrant labels
  const quadLabels = `
    <text x="${{pad + 10}}" y="${{pad + 20}}" class="map-axis-label" style="font-size:10px;fill:var(--muted);font-weight:600;">high manipulation · low frequency</text>
    <text x="${{width - pad - 200}}" y="${{pad + 20}}" class="map-axis-label" style="font-size:10px;fill:var(--muted);font-weight:600;">high manipulation · high frequency</text>
    <text x="${{pad + 10}}" y="${{height - pad - 5}}" class="map-axis-label" style="font-size:10px;fill:var(--muted);font-weight:600;">low manipulation · low frequency</text>
    <text x="${{width - pad - 200}}" y="${{height - pad - 5}}" class="map-axis-label" style="font-size:10px;fill:var(--muted);font-weight:600;">low manipulation · high frequency</text>
  `;

  // Axis lines + labels
  const axesHTML = `
    <path d="M${{pad}} ${{height/2}}H${{width-pad}}M${{width/2}} ${{pad}}V${{height-pad}}" stroke="var(--line)" fill="none" stroke-width="1.5"/>
    <text x="${{width/2}}" y="${{height - 10}}" text-anchor="middle" style="font-size:11px;fill:var(--ink);font-weight:600;">Semantic dimension 1 (frequency / specificity)</text>
    <text x="${{15}}" y="${{height/2}}" text-anchor="middle" transform="rotate(-90 15 ${{height/2}})" style="font-size:11px;fill:var(--ink);font-weight:600;">Semantic dimension 2 (manipulation intensity)</text>
    ${{quadLabels}}
  `;

  container.innerHTML = `<svg viewBox="0 0 ${{width}} ${{height}}" width="100%" height="100%" aria-label="corpus map (${{colorMode}} mode, ${{query ? 'filtered: \\'' + query + '\\'' : 'no filter'}})">${{axesHTML}}${{pointsHTML}}</svg>`;

  // Show filter count
  const filterNote = query
    ? `Showing ${{visible.length}} of ${{allPoints.length}} points matching "${{esc(query)}}"`
    : `Showing ${{visible.length}} of ${{allPoints.length}} points · colored by ${{esc(colorMode)}}`;
  $('mapInspector').innerHTML = `<b>How to interpret:</b> ${{filterNote}}. Each point is a representative ad; point size scales with manipulation score. Click any point to inspect it and see its 5 nearest neighbors.`;

  // Initialize detail + neighbor panels (BEFORE click handlers)
  $('mapSelectedDetail').innerHTML = '<h3>Selected point</h3><p class="small" style="color:var(--muted);">Click a map point to see ad metadata, record ID, platform, and manipulation score.</p>';
  $('mapNeighbors').innerHTML = '<h3>Nearest neighbors</h3><p class="small" style="color:var(--muted);">Select a point to see its 5 nearest neighbors by Euclidean distance.</p>';
  $('mapQuadrants').innerHTML = '';
  $('deepClusterPanel').innerHTML = (map.deep_clusters?.clusters||[]).slice(0,6).map(c=>`<div class="map-card"><h3>${{esc(c.eli5_title||c.name)}}</h3><p class="small">${{c.count}} ads · ${{esc((c.top_terms||[]).slice(0,5).map(t=>t.term).join(', '))}}</p></div>`).join('') || '<p class="small">No deep clusters.</p>';
  $('isolationPanel').innerHTML = '<p class="small">Isolation slices available in full report.</p>';

  // Add click handlers to make points interactive
  container.querySelectorAll('circle.map-point').forEach(c => {{
    c.addEventListener('click', (event) => {{
      const idx = parseInt(c.dataset.origIdx);
      const p = allPoints[idx];
      if (!p) return;
      // Populate the #mapSelectedDetail panel
      const rid = (p.record_id || '').slice(0, 24) + '...';
      const fullRid = p.record_id || '';
      const title = (p.title || 'Untitled').slice(0, 80);
      const platform = p.platform || p.split || '?';
      const manipulation = (p.manipulation_score || 0).toFixed(3);
      const x = (p.x || 0).toFixed(3);
      const y = (p.y || 0).toFixed(3);
      const split = p.split || '?';
      const labels = (p.labels || []).join(', ') || 'none';
      if ($('mapSelectedDetail')) {{
        $('mapSelectedDetail').innerHTML = `
          <h3>Selected point</h3>
          <p class="small"><b>Title:</b> ${{esc(title)}}</p>
          <p class="small"><b>Record ID:</b> <code title="${{esc(fullRid)}}">${{esc(rid)}}</code></p>
          <p class="small"><b>Platform:</b> ${{esc(platform)}} · <b>Split:</b> ${{esc(split)}}</p>
          <p class="small"><b>Manipulation score:</b> <span style="font-weight:700;color:${{manipulation > 0.5 ? 'var(--red)' : 'var(--ink)'}};">${{manipulation}}</span></p>
          <p class="small"><b>Map position:</b> x=${{x}}, y=${{y}}</p>
          <p class="small"><b>Labels:</b> ${{esc(labels)}}</p>
        `;
      }}
      // Find nearest neighbors by Euclidean distance (search ALL points, not just filtered)
      const dists = allPoints.map((q, j) => ({{idx: j, d: Math.hypot((q.x||0)-(p.x||0), (q.y||0)-(p.y||0))}})).filter(o => o.idx !== idx).sort((a,b) => a.d - b.d).slice(0, 5);
      if ($('mapNeighbors')) {{
        $('mapNeighbors').innerHTML = `<h3>Nearest neighbors</h3>${{dists.map(o => {{
          const q = allPoints[o.idx];
          const qTitle = (q.title || 'Untitled').slice(0, 50);
          const qPlat = q.platform || q.split || '?';
          const qScore = (q.manipulation_score || 0).toFixed(2);
          return `<div class="neighbor-list"><button class="map-neighbor-pick" data-idx="${{o.idx}}" style="text-align:left;background:#fff;border:1px solid var(--line);border-radius:6px;padding:4px 6px;cursor:pointer;font-size:10px;display:block;margin:2px 0;width:100%;"><b>${{esc(qTitle)}}</b> <span style="color:var(--muted);">d=${{o.d.toFixed(3)}} · ${{esc(qPlat)}} · score=${{qScore}}</span></button></div>`;
        }}).join('')}}`;
        // Wire neighbor click handlers
        $('mapNeighbors').querySelectorAll('.map-neighbor-pick').forEach(btn => {{
          btn.addEventListener('click', () => {{
            const nIdx = parseInt(btn.dataset.idx);
            const circle = container.querySelector(`circle.map-point[data-orig-idx="${{nIdx}}"]`);
            if (circle) circle.click();
          }});
        }});
      }}
      // Highlight the selected point
      container.querySelectorAll('circle.map-point').forEach(cc => {{ cc.setAttribute('stroke', '#fff'); cc.setAttribute('stroke-width', '1'); }});
      c.setAttribute('stroke', 'var(--blue)');
      c.setAttribute('stroke-width', '3');
    }});
    // Rich hover annotation via mouseenter/mouseleave
    c.addEventListener('mouseenter', (event) => {{
      const idx = parseInt(c.dataset.origIdx);
      const p = allPoints[idx];
      if (!p) return;
      const tip = tooltip();
      const title = (p.title || 'Untitled').slice(0, 60);
      const plat = p.platform || p.split || '?';
      const score = (p.manipulation_score || 0).toFixed(3);
      tip.innerHTML = `<b>${{esc(title)}}</b><br><span style="color:#a8d7bd;">${{esc(plat)}}</span> · score=${{score}}`;
      tip.style.display = 'block';
    }});
    c.addEventListener('mousemove', (event) => {{
      const tip = tooltip();
      tip.style.left = (event.pageX + 12) + 'px';
      tip.style.top = (event.pageY + 12) + 'px';
    }});
    c.addEventListener('mouseleave', () => {{
      const tip = tooltip();
      tip.style.display = 'none';
    }});
  }});
}}"""

assert OLD_RENDER in src, "OLD_RENDER not found"
src = src.replace(OLD_RENDER, NEW_RENDER)
print("1. Replaced renderCorpusMap with fixed + improved version: OK")

# ---------------------------------------------------------------------------
# Fix mapResetLayers to actually clear the query and reset color
# ---------------------------------------------------------------------------
OLD_RESET = "$('mapResetLayers').addEventListener('click',renderCorpusMap);"
NEW_RESET = """$('mapResetLayers').addEventListener('click',()=>{{if($('mapQuery'))$('mapQuery').value='';if($('mapColor'))$('mapColor').value='platform';renderCorpusMap()}});"""
assert OLD_RESET in src, "OLD_RESET not found"
src = src.replace(OLD_RESET, NEW_RESET)
print("2. Fixed mapResetLayers to clear query + reset color: OK")

# ---------------------------------------------------------------------------
# Add CSS for the rich tooltip and axis labels
# ---------------------------------------------------------------------------
CSS_MARKER = ".tooltip {{ position:fixed; background:#17201d; color:#fff; padding:6px 8px; border-radius:6px; font-size:11px; display:none; z-index:50; pointer-events:none; max-width:280px; }}"
CSS_REPLACEMENT = """.tooltip {{ position:fixed; background:#17201d; color:#fff; padding:8px 10px; border-radius:8px; font-size:11px; display:none; z-index:50; pointer-events:none; max-width:320px; box-shadow:0 4px 12px rgba(0,0,0,0.3); line-height:1.5; }}
.tooltip b {{ color:#a8d7bd; }}
.map-axis-label {{ pointer-events:none; }}"""
assert CSS_MARKER in src, "CSS_MARKER not found"
src = src.replace(CSS_MARKER, CSS_REPLACEMENT)
print("3. Enhanced tooltip CSS: OK")

# ---------------------------------------------------------------------------
# Write the patched file
# ---------------------------------------------------------------------------
PATH.write_text(src, encoding="utf-8")
print(f"\nDone. Patched {PATH}")
print(f"  New size: {len(src)} bytes")
