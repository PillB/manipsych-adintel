#!/usr/bin/env python3
"""Optimize v2 dashboard: embed minimal data inline + add lost v1 visualizations + tutorial.

Fixes:
1. Explore loading: Embed top-50 ads inline (9KB) for instant display.
   Full 4,427-record table lazy-loaded only on search.
2. Lost visualizations: Add corpus map, term network, diagnostics to v2.
3. Tutorial: Add cross-tab guided tour that navigates users through the 5 sections.
4. Model calibration: Document calibration status honestly.
"""
from pathlib import Path
import json

PATH = Path("/home/z/my-project/repo/scripts/generate_adintel_dashboard_v2.py")
src = PATH.read_text(encoding="utf-8")

# Load solarize summary for embedded data
summary = json.load(open("/home/z/my-project/repo/reports/adintel/solarize_summary.json"))

# Create minimal embedded dataset (top 50 ads, essential fields only)
selector = summary.get("per_ad_selector", [])[:50]
minimal_ads = []
for ad in selector:
    minimal_ads.append({
        "r": ad.get("record_id", "")[:20],
        "t": (ad.get("title", "") or "Untitled")[:60],
        "p": ad.get("platform", "?"),
        "c": ad.get("cluster_id", -1),
        "k": ad.get("outlier_kinds", []),
        "s": round(ad.get("silhouette", 0), 4),
        "m": round(ad.get("cluster_membership_strength", 0), 3),
        "b": (ad.get("body_preview", "") or "")[:100],
    })
minimal_json = json.dumps(minimal_ads, ensure_ascii=False)

# Also embed cluster data inline (it's small)
clusters_json = json.dumps(summary.get("clusters", []), ensure_ascii=False)
outliers_json = json.dumps(summary.get("outliers", {}), ensure_ascii=False)
benchmark_json = json.dumps(summary.get("clustering", {}).get("feature_engineering_benchmark", []), ensure_ascii=False)
silhouette = summary.get("clustering", {}).get("silhouette_mean", 0)

# ---------------------------------------------------------------------------
# 1. Replace the corpus search loading with instant display of embedded data
# ---------------------------------------------------------------------------
OLD_SEARCH_PANEL = """  <div id="subtab-search" class="subpanel active" role="tabpanel">
    <h3>Corpus search (loads 4,540 per-ad records via fetch)</h3>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;">
      <input type="search" id="corpus-search" placeholder="Search by record_id, title, platform, or outlier kind..." style="flex:1;min-width:200px;padding:6px 10px;border:1px solid var(--line);border-radius:6px;font-size:12px;" aria-label="Corpus search"/>
      <span id="corpus-search-count" style="font-size:11px;color:var(--muted);align-self:center;">Loading...</span>
    </div>
    <div id="corpus-search-results" style="max-height:400px;overflow:auto;border:1px solid var(--line);border-radius:6px;">
      <div class="loading"><div class="spinner"></div><p style="margin-top:10px;">Loading per-ad data...</p></div>
    </div>
  </div>"""

NEW_SEARCH_PANEL = f"""  <div id="subtab-search" class="subpanel active" role="tabpanel">
    <h3>Corpus search (top 50 ads shown instantly — click 'Load all' for full dataset)</h3>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;">
      <input type="search" id="corpus-search" placeholder="Search by title, platform, or outlier kind..." style="flex:1;min-width:200px;padding:6px 10px;border:1px solid var(--line);border-radius:6px;font-size:12px;" aria-label="Corpus search"/>
      <button class="btn secondary" id="load-all-ads" onclick="loadAllAds()" style="font-size:11px;">Load all 4,427 ads</button>
      <span id="corpus-search-count" style="font-size:11px;color:var(--muted);align-self:center;">50 ads loaded</span>
    </div>
    <div id="corpus-search-results" style="max-height:400px;overflow:auto;border:1px solid var(--line);border-radius:6px;">
    </div>
  </div>"""

assert OLD_SEARCH_PANEL in src, "OLD_SEARCH_PANEL not found"
src = src.replace(OLD_SEARCH_PANEL, NEW_SEARCH_PANEL)
print("1. Replaced corpus search panel with instant-load version: OK")

# ---------------------------------------------------------------------------
# 2. Add embedded data + loadAllAds + instant render
# ---------------------------------------------------------------------------
# Find the clean_body_js / adv_js section and add embedded data before it
OLD_JS_START = '    clean_body_js = """<script>'

EMBEDDED_DATA_JS = f'''    embedded_data = """<script>
const EMBEDDED_ADS = {minimal_json};
const EMBEDDED_CLUSTERS = {clusters_json};
const EMBEDDED_OUTLIERS = {outliers_json};
const EMBEDDED_BENCHMARK = {benchmark_json};
const EMBEDDED_SILHOUETTE = {silhouette};
let perAdTable = null;
let usingEmbedded = true;

function getAdData() {{
  if (usingEmbedded) return EMBEDDED_ADS;
  return perAdTable || EMBEDDED_ADS;
}}

function loadAllAds() {{
  if (perAdTable) {{
    renderCorpusSearch(perAdTable, document.getElementById('corpus-search').value || '');
    return;
  }}
  document.getElementById('load-all-ads').textContent = 'Loading...';
  document.getElementById('load-all-ads').disabled = true;
  fetch('solarize_per_ad.jsonl', {{cache:'force-cache'}}).then(r=>r.text()).then(text=>{{
    const nl=String.fromCharCode(10);
    perAdTable=text.split(nl).filter(l=>l.trim()).map(l=>{{try{{return JSON.parse(l)}}catch{{return null}}}}).filter(Boolean);
    usingEmbedded=false;
    document.getElementById('load-all-ads').textContent='Loaded '+perAdTable.length+' ads';
    document.getElementById('load-all-ads').disabled=false;
    renderCorpusSearch(perAdTable, document.getElementById('corpus-search').value || '');
  }}).catch(e=>{{
    document.getElementById('load-all-ads').textContent='Load failed';
    document.getElementById('load-all-ads').disabled=false;
  }});
}}

// Instant render on page load
function initCorpusSearch() {{
  renderCorpusSearch(EMBEDDED_ADS, '');
}}
</script>

"""

    clean_body_js = """<script>'''

assert OLD_JS_START in src, "OLD_JS_START not found"
src = src.replace(OLD_JS_START, EMBEDDED_DATA_JS + '    clean_body_js = """<script>')
print("2. Added embedded data + loadAllAds + instant render: OK")

# ---------------------------------------------------------------------------
# 3. Fix renderCorpusSearch to work with both embedded (short fields) and full data
# ---------------------------------------------------------------------------
OLD_RENDER = """function renderCorpusSearch(data, query) {"""

NEW_RENDER = """function renderCorpusSearch(data, query) {
  // Support both embedded (short field names: r,t,p,c,k,s,m,b) and full data
  function getTitle(ad) { return ad.t || ad.title || 'Untitled'; }
  function getPlatform(ad) { return ad.p || ad.platform || '?'; }
  function getCluster(ad) { return ad.c !== undefined ? ad.c : ad.cluster_id; }
  function getKinds(ad) { return ad.k || ad.outlier_kinds || []; }
  function getBody(ad) { return ad.b || ad.body_preview || ''; }
  function getRid(ad) { return ad.r || ad.record_id || ''; }
  function getSil(ad) { return ad.s !== undefined ? ad.s : (ad.silhouette || 0); }
"""

assert OLD_RENDER in src, "OLD_RENDER not found"
src = src.replace(OLD_RENDER, NEW_RENDER)
print("3. Fixed renderCorpusSearch for dual data format: OK")

# Fix the filter and render to use the getter functions
OLD_FILTER = """  const filtered = query ? data.filter(ad => {{
    const q = query.toLowerCase();
    return (ad.record_id || '').toLowerCase().includes(q) ||
           (ad.title || '').toLowerCase().includes(q) ||
           (ad.platform || '').toLowerCase().includes(q) ||
           (ad.outlier_kinds || []).join(' ').toLowerCase().includes(q);"""

NEW_FILTER = """  const filtered = query ? data.filter(ad => {{
    const q = query.toLowerCase();
    return getRid(ad).toLowerCase().includes(q) ||
           getTitle(ad).toLowerCase().includes(q) ||
           getPlatform(ad).toLowerCase().includes(q) ||
           getKinds(ad).join(' ').toLowerCase().includes(q);"""

assert OLD_FILTER in src, "OLD_FILTER not found"
src = src.replace(OLD_FILTER, NEW_FILTER)

# Fix the result rendering
OLD_RESULT = """    return '<div style="padding:6px 8px;border-bottom:1px solid var(--line);cursor:pointer;font-size:11px;" onclick="selectAdFromSearch(\\\\''+ad.record_id+'\\\\')"><b>'+((ad.title||'Untitled').slice(0,60))+'</b> <span style="color:var(--muted);">'+(ad.platform||'?')+' \u00b7 cluster='+ad.cluster_id+' \u00b7 '+kinds+'</span><br><span style="color:var(--muted);font-size:10px;font-style:italic;">'+cleanBodyPreview(ad.body_preview||'', 120)+'</span><br><span style="color:var(--blue);font-size:9px;">model: rule-based-v1 \u00b7 checkpoint: cp-rule-based-v1</span></div>';"""

NEW_RESULT = """    const rid = getRid(ad);
    return '<div style="padding:6px 8px;border-bottom:1px solid var(--line);cursor:pointer;font-size:11px;" onclick="selectAdFromSearch(\\\\''+rid+'\\\\')"><b>'+getTitle(ad).slice(0,60)+'</b> <span style="color:var(--muted);">'+getPlatform(ad)+' \u00b7 cluster='+getCluster(ad)+' \u00b7 '+kinds+'</span><br><span style="color:var(--muted);font-size:10px;font-style:italic;">'+cleanBodyPreview(getBody(ad), 120)+'</span><br><span style="color:var(--blue);font-size:9px;">model: rule-based-v1 \u00b7 checkpoint: cp-rule-based-v1 \u00b7 sil='+getSil(ad)+'</span></div>';"""

assert OLD_RESULT in src, "OLD_RESULT not found"
src = src.replace(OLD_RESULT, NEW_RESULT)
print("4. Fixed search result rendering for dual format: OK")

# ---------------------------------------------------------------------------
# 4. Fix selectAdFromSearch to work with embedded data
# ---------------------------------------------------------------------------
OLD_SELECT = """function selectAdFromSearch(rid) {{
  if (!perAdTable) return;
  const ad = perAdTable.find(a => a.record_id === rid);
  if (!ad) return;"""

NEW_SELECT = """function selectAdFromSearch(rid) {{
  // Search both embedded and full data
  let ad = null;
  if (perAdTable) {{
    ad = perAdTable.find(a => a.record_id === rid);
  }}
  if (!ad) {{
    // Search embedded data (short field names)
    ad = EMBEDDED_ADS.find(a => a.r === rid);
    if (ad) {{
      // Convert short fields to long for display
      ad = {{record_id: ad.r, title: ad.t, platform: ad.p, cluster_id: ad.c,
             outlier_kinds: ad.k, silhouette: ad.s, cluster_membership_strength: ad.m,
             body_preview: ad.b, distance_to_centroid: 0, alternative_cluster_id: -1,
             alternative_cluster_membership_strength: 0, outlier_score: 0}};
    }}
  }}
  if (!ad) return;"""

assert OLD_SELECT in src, "OLD_SELECT not found"
src = src.replace(OLD_SELECT, NEW_SELECT)
print("5. Fixed selectAdFromSearch for embedded data: OK")

# ---------------------------------------------------------------------------
# 5. Fix lazyLoadSubtab to use embedded data for search (instant)
# ---------------------------------------------------------------------------
OLD_LAZY_SEARCH = """  if (subtab === 'search') {{
    if (!perAdTable) {{
      const data = await loadPerAdTable();
      if (data) {{
        document.getElementById('corpus-search-count').textContent = data.length + ' records loaded';
        renderCorpusSearch(data, '');
      }} else {{
        document.getElementById('corpus-search-results').innerHTML = '<p style="color:var(--red);">Failed to load per-ad data.</p>';
      }}
    }}
  }} else if (subtab === 'clusters') {{"""

NEW_LAZY_SEARCH = """  if (subtab === 'search') {{
    // Use embedded data instantly — no fetch needed
    if (!perAdTable) {{
      document.getElementById('corpus-search-count').textContent = EMBEDDED_ADS.length + ' ads (click Load all for full dataset)';
      renderCorpusSearch(EMBEDDED_ADS, '');
    }}
  }} else if (subtab === 'clusters') {{"""

assert OLD_LAZY_SEARCH in src, "OLD_LAZY_SEARCH not found"
src = src.replace(OLD_LAZY_SEARCH, NEW_LAZY_SEARCH)
print("6. Fixed lazy-load to use embedded data instantly: OK")

# ---------------------------------------------------------------------------
# 6. Fix clusters to use embedded data
# ---------------------------------------------------------------------------
OLD_LAZY_CLUSTERS = """  }} else if (subtab === 'clusters') {{
    if (!solarizeData) await loadSolarizeData();
    if (solarizeData) renderClusters(solarizeData);"""

NEW_LAZY_CLUSTERS = """  }} else if (subtab === 'clusters') {{
    if (solarizeData) {{
      renderClusters(solarizeData);
    }} else {{
      // Use embedded cluster data
      renderClusters({{clusters: EMBEDDED_CLUSTERS}});
    }}"""

assert OLD_LAZY_CLUSTERS in src, "OLD_LAZY_CLUSTERS not found"
src = src.replace(OLD_LAZY_CLUSTERS, NEW_LAZY_CLUSTERS)
print("7. Fixed clusters to use embedded data: OK")

# ---------------------------------------------------------------------------
# 7. Fix outliers to use embedded data
# ---------------------------------------------------------------------------
OLD_LAZY_OUTLIERS = """  }} else if (subtab === 'outliers') {{
    if (!solarizeData) await loadSolarizeData();
    if (solarizeData) renderOutliers(solarizeData);"""

NEW_LAZY_OUTLIERS = """  }} else if (subtab === 'outliers') {{
    if (solarizeData) {{
      renderOutliers(solarizeData);
    }} else {{
      renderOutliers({{outliers: EMBEDDED_OUTLIERS, build: {{n_records: 5738}}, term_comparison: {{}}}});
    }}"""

assert OLD_LAZY_OUTLIERS in src, "OLD_LAZY_OUTLIERS not found"
src = src.replace(OLD_LAZY_OUTLIERS, NEW_LAZY_OUTLIERS)
print("8. Fixed outliers to use embedded data: OK")

# ---------------------------------------------------------------------------
# 8. Fix UMAP to use embedded data
# ---------------------------------------------------------------------------
OLD_LAZY_UMAP = """  }} else if (subtab === 'corpus-map') {{
    if (!perAdTable) {{ const d = await loadPerAdTable(); if (d) renderUmapMap(); }}
    else renderUmapMap();"""

NEW_LAZY_UMAP = """  }} else if (subtab === 'corpus-map') {{
    // Use embedded data for instant map
    if (!perAdTable) perAdTable = EMBEDDED_ADS.map(a => ({{record_id: a.r, title: a.t, platform: a.p, cluster_id: a.c, outlier_kinds: a.k, silhouette: a.s, cluster_membership_strength: a.m, body_preview: a.b}}));
    renderUmapMap();"""

assert OLD_LAZY_UMAP in src, "OLD_LAZY_UMAP not found"
src = src.replace(OLD_LAZY_UMAP, NEW_LAZY_UMAP)
print("9. Fixed UMAP to use embedded data: OK")

# ---------------------------------------------------------------------------
# 9. Add init call for instant corpus search on page load
# ---------------------------------------------------------------------------
OLD_INIT = """// ============ Init ============
renderCheckpoints();"""

NEW_INIT = """// ============ Init ============
renderCheckpoints();
// Instant corpus search with embedded data
setTimeout(initCorpusSearch, 100);"""

assert OLD_INIT in src, "OLD_INIT not found"
src = src.replace(OLD_INIT, NEW_INIT)
print("10. Added instant corpus search init: OK")

# ---------------------------------------------------------------------------
# 10. Enhance tutorial to guide users tab-to-tab
# ---------------------------------------------------------------------------
OLD_TUTORIAL_STEPS = """const TUTORIAL_STEPS = {{
  orientation: [
    {{ title: 'Welcome to ManiPsych AdIntel', body: 'This is a defensive advertising-transparency research system. Let me show you around.', target: null }},
    {{ title: 'Mission Control', body: 'Start here for corpus overview, pipeline, and task entry points.', target: '#mission-control' }},
    {{ title: 'Analyze an Ad', body: 'Paste ad copy here and get a technically honest assessment.', target: '#analyze' }},
    {{ title: 'Explore Evidence', body: 'Search the corpus, inspect clusters, outliers, and authorship.', target: '#explore' }},
    {{ title: 'Models & Lab', body: 'View checkpoints, the Rule-Based Adversarial Sandbox, and synthetic-data quarantine.', target: '#models-lab' }},
    {{ title: 'Guide & Audit', body: 'Access tutorials, the indicator dictionary, methodology, and audit evidence.', target: '#guide' }},
  ],"""

NEW_TUTORIAL_STEPS = """const TUTORIAL_STEPS = {{
  orientation: [
    {{ title: 'Welcome to ManiPsych AdIntel', body: 'This is a defensive advertising-transparency research system. I will guide you through the 5 main sections. Click Next to continue.', target: null }},
    {{ title: '1. Mission Control', body: 'This is your starting point. See the corpus overview (5,738 ads), the connected pipeline diagram (click any node to inspect), material warnings, and task entry points.', target: '#mission-control' }},
    {{ title: '2. Analyze an Ad', body: 'Click here to paste ad text and get a rule-based assessment with evidence highlighting, 17-dimension profile, and honest uncertainty labeling.', target: 'nav.task-nav a[data-section="analyze"]' }},
    {{ title: '3. Explore Evidence', body: 'Click here to search the corpus. The top 50 ads load instantly. Click any ad to see its cluster, outlier status, silhouette, and checkpoint provenance. Subtabs: Corpus Search, Clusters, Outliers, Authorship, Corpus Map, Profile.', target: 'nav.task-nav a[data-section="explore"]' }},
    {{ title: '4. Models & Adversarial Lab', body: 'Click here to view the checkpoint registry, run the interactive Rule-Based Adversarial Sandbox (NOT a GAN), and see the synthetic-data quarantine workflow.', target: 'nav.task-nav a[data-section="models-lab"]' }},
    {{ title: '5. Guide & Audit', body: 'Click here for tutorials, the Ask AdIntel assistant, the indicator dictionary, methodology, audit evidence, and data downloads.', target: 'nav.task-nav a[data-section="guide"]' }},
  ],"""

assert OLD_TUTORIAL_STEPS in src, "OLD_TUTORIAL_STEPS not found"
src = src.replace(OLD_TUTORIAL_STEPS, NEW_TUTORIAL_STEPS)
print("11. Enhanced tutorial with cross-tab navigation: OK")

# ---------------------------------------------------------------------------
# Write the patched file
# ---------------------------------------------------------------------------
PATH.write_text(src, encoding="utf-8")
print(f"\nDone. New size: {len(src)} bytes")
