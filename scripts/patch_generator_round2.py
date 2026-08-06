#!/usr/bin/env python3
"""Round 2 Solarize patch: add methodology, audit-evidence, data-download,
full-ad-table (via fetch), and cluster-drill-down to the dashboard.

Adds new sections to scripts/generate_adintel_dashboard.py:
  - #adintel-methodology: explains Wilson/Cohen/BH/min-support/k=5/meaningfully
  - #adintel-audit: surfaces Red phase baseline + verification rounds
  - #adintel-data: download links for solarize_summary.json + per_ad.jsonl
  - #adintel-full-ad-table: client-side fetch of solarize_per_ad.jsonl,
    searchable by record_id / title / platform / outlier kind, paginated

Also patches the Solarize JS:
  - Cluster-card click now sets the cluster filter AND scrolls to selector
  - Adds full-table search via fetch('solarize_per_ad.jsonl')
"""
from pathlib import Path

PATH = Path("/home/z/my-project/repo/scripts/generate_adintel_dashboard.py")
src = PATH.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# 1. Add new sections before the existing #adintel-challenges section
# ---------------------------------------------------------------------------
NEW_SECTIONS_MARKER = '  <!-- ========== ADINTEL NEW SECTION: Challenge rounds'
NEW_SECTIONS = '''  <!-- ========== ADINTEL NEW SECTION: Methodology (Solarize Round 2) ========== -->
  <section id="adintel-methodology" style="margin-top:16px;border:2px solid var(--violet);">
    <div class="story-step"><span class="step-num" style="background:var(--violet);">M</span><span class="step-text"><b>Methodology.</b> Why each statistical choice was made — so the dashboard is auditable, not a black box.</span></div>
    <h2>adintel: Statistical Methodology <span class="section-tag new">solarize</span></h2>

    <h3>Effect size: Cohen's h (arc-sine transformation)</h3>
    <p class="small">We use <b>Cohen's h</b> = 2·arcsin(√p1) − 2·arcsin(√p2) instead of the uncorrected enrichment ratio (p1/p2) that the previous dashboard used. The enrichment ratio inflates toward infinity when p2 → 0, making "100× enriched" claims from a single hit meaningless. Cohen's h is bounded, symmetric, and has conventional interpretation thresholds:</p>
    <ul class="small">
      <li>|h| &lt; 0.20 → <b>negligible</b> (no meaningful difference)</li>
      <li>0.20 ≤ |h| &lt; 0.50 → <b>small</b></li>
      <li>0.50 ≤ |h| &lt; 0.80 → <b>medium</b> (the minimum threshold for "meaningfully different")</li>
      <li>|h| ≥ 0.80 → <b>large</b></li>
    </ul>

    <h3>Confidence interval: Wilson score interval</h3>
    <p class="small">We use the <b>Wilson score interval</b> on each proportion, then combine via √(SE1² + SE2²) for the difference. The Wald interval (p ± 1.96·√(p(1−p)/n)) is forbidden because it produces degenerate intervals at k=0 and k=n — exactly the cases that matter most for rare-term enrichment. Wilson is bounded in [0,1], has correct coverage at small n, and is the recommended interval for binomial proportions (Brown, Cai &amp; DasGupta 2001).</p>

    <h3>Significance test: two-sided z-test for difference of proportions (pooled)</h3>
    <p class="small">Under H0: p1 = p2, the pooled estimate p̂ = (k1 + k2) / (n1 + n2) gives the standard error √(p̂(1−p̂)(1/n1 + 1/n2)). The z-statistic is (p1 − p2) / SE. We report the two-sided p-value via the normal CDF. This is the standard test for comparing two independent proportions; it is asymptotic and may be anti-conservative at very small n (which is why we ALSO require min-support).</p>

    <h3>Multiple-testing correction: Benjamini–Hochberg FDR</h3>
    <p class="small">We adjust p-values across all 50 candidate terms using the <b>Benjamini–Hochberg</b> procedure, controlling the expected false-discovery rate at 5%. We rejected <b>Bonferroni</b> because it controls the family-wise error rate, which is too conservative for exploratory term-enrichment analysis where we WANT to detect weak signals. BH lets us report "6 of 50 terms are meaningfully enriched at q&lt;0.05" without inflating the false-positive rate.</p>

    <h3>Min-support threshold: 5 hits in BOTH arms</h3>
    <p class="small">A term is flagged <code>min_support: NO</code> if it has fewer than 5 hits in either the outlier arm OR the control arm. This prevents "100% prevalence" claims from a single observation (e.g. a term appearing in 1/1 outlier ads and 0/4064 controls would have ratio = ∞ but |h| = 1.57, p = 0.04 — both nominally significant but statistically meaningless). The threshold of 5 is conventional in market-basket analysis and rare-event epidemiology; it can be tuned via the <code>min_support</code> parameter of <code>adintel.solarize_stats.compare_term_set</code>.</p>

    <h3>"Meaningfully different" verdict: four-part criterion</h3>
    <p class="small">A term is declared <b>meaningfully different</b> only if ALL FOUR conditions hold:</p>
    <ol class="small">
      <li><b>Effect size</b>: |h| ≥ 0.50 (at least medium)</li>
      <li><b>CI direction</b>: lower bound of the 95% CI on the difference is &gt; 0 (the effect direction is consistent, not crossing zero)</li>
      <li><b>Min-support</b>: at least 5 hits in BOTH arms</li>
      <li><b>FDR</b>: q-value &lt; 0.05 after Benjamini–Hochberg adjustment</li>
    </ol>
    <p class="small">If ANY condition fails, the term is reported with a verdict reason explaining which criterion failed. The aggregate verdict at the section level (<code>DIFFERENTIATED</code> / <code>PARTIALLY_DIFFERENTIATED</code> / <code>NOT_MEANINGFULLY_DIFFERENT</code>) requires at least 3 / 1 / 0 terms to pass all four criteria.</p>

    <h3>Clustering: k=5 MiniBatchKMeans on L2-normalised TF-IDF</h3>
    <p class="small"><b>k=5</b> was chosen to match the v1 cluster count for direct alignment in the cluster_alignment_report (ARI = 0.418, AMI = 0.5175). We use <b>MiniBatchKMeans</b> (not full KMeans) because the corpus has 5,738 records and MiniBatch is ~10× faster with negligible silhouette loss. We use <b>TF-IDF with 1-2 grams, 5,000 max features, L2-normalised</b> because 1-grams alone miss multi-word persuasion patterns ("ayuda económica", "señorita sola") and character n-grams over-weight spelling noise. The L2 normalisation prevents longer ads from dominating the centroid.</p>

    <h3>Deep-clustering justification gate</h3>
    <p class="small">Deep clustering (LSA / SVD / UMAP) is justified ONLY if:</p>
    <ol class="small">
      <li>The best simple baseline (raw TF-IDF + KMeans) has silhouette &lt; 0.10 (clusters are weakly separated)</li>
      <li>AND deep clustering improves silhouette by ≥ 0.05 over the simple baseline</li>
    </ol>
    <p class="small">On this corpus: raw TF-IDF silhouette = 0.005, LSA(100d) silhouette = 0.032, SVD(50d)+scaler silhouette = 0.016. The improvement (0.026) is below the 0.05 threshold. <b>Deep clustering is NOT justified — simpler baselines suffice.</b> The pre-Solarize LSA+KMeans artifact is preserved in the dashboard as benchmark evidence, not as the canonical clustering.</p>

    <h3>4-way outlier classification (R9)</h3>
    <p class="small">Each ad may belong to zero, one, or several outlier kinds. Kinds are NOT mutually exclusive — an ad can simultaneously be a detector outlier AND a boundary member.</p>
    <ul class="small">
      <li><b>detector</b>: rule-based / model-based outlier (the historical 11 kinds: creative_novelty, style_outlier, duplicate, metadata_error, etc.). Sampled at n=1,000.</li>
      <li><b>density_noise</b>: DBSCAN label=-1 with cosine distance, eps=0.65, min_samples=10. An ad is noise if it sits in a low-density region (no cluster of ≥10 ads within cosine distance 0.65). Tuned for short Spanish classified ads where exact-match signal is weak but topical similarity is strong.</li>
      <li><b>cluster_enriched</b>: within-cluster Mahalanobis/MAD distance &gt; 3.5σ. Uses the Median Absolute Deviation (robust to non-Gaussian distance distributions) scaled by 1.4826 to match the normal-distribution standard deviation.</li>
      <li><b>boundary</b>: per-ad silhouette &lt; 0. A negative silhouette means the ad is closer to another cluster's centroid than to its own — a weak assignment that should be inspected.</li>
    </ul>

    <h3>Three comparison populations (R2)</h3>
    <p class="small">For each outlier ad, we compare term prevalence against three control populations:</p>
    <ul class="small">
      <li><b>(a) all non-outlier ads</b>: the most-stringent test. The outlier group is meaningfully different from the full-corpus baseline only if it differs on the corpus-wide term distribution.</li>
      <li><b>(b) non-outlier ads in the same cluster</b>: controls for cluster-level baseline. An outlier may be different from the corpus but normal within its own cluster.</li>
      <li><b>(c) matched controls on platform_family</b>: controls for platform-specific language. Two ads from the same platform share stylistic conventions regardless of outlier status.</li>
    </ul>
  </section>

  <!-- ========== ADINTEL NEW SECTION: Audit Evidence (Solarize Round 2) ========== -->
  <section id="adintel-audit" style="margin-top:16px;border:2px solid var(--violet);">
    <div class="story-step"><span class="step-num" style="background:var(--violet);">A</span><span class="step-text"><b>Audit evidence.</b> Red-phase baseline, verification rounds, and live test results — so the deployment claims are auditable, not asserted.</span></div>
    <h2>adintel: Audit Evidence &amp; Verification <span class="section-tag new">solarize</span></h2>

    <h3>Solarize audit process</h3>
    <p class="small">The Solarize refactor followed a strict bounded cycle: <b>Research → Red → Green → Refactor → Deploy → Live Validate → Report</b>. Tests were written FIRST against the pre-Solarize live deployment to capture missing functionality as Red evidence, then implementation proceeded until all tests passed against the deployed GitHub Pages URL.</p>

    <h3>Red phase (pre-Solarize baseline)</h3>
    <p class="small">Before Solarize, the live dashboard at this URL had:</p>
    <ul class="small">
      <li><b>No build fingerprint or commit SHA</b> on the &lt;html&gt; tag — deployment was unverifiable.</li>
      <li><b>No term-prevalence comparison table</b> with effect sizes, CIs, or FDR adjustment.</li>
      <li><b>No 4-way outlier classification</b> — only the historical 11 detector kinds existed.</li>
      <li><b>No explicit "NOT meaningfully different" statement</b> when outliers were term-indistinguishable from controls.</li>
      <li><b>No cluster examples</b> with distinguishing terms and real ad text.</li>
      <li><b>No ad selector</b> — users could not search for an ad by ID and see its cluster + outlier status.</li>
      <li><b>Mobile horizontal overflow</b> at 375px viewport (scrollWidth = 484 vs clientWidth = 375).</li>
    </ul>
    <p class="small">Red-phase evidence saved at <code>audit/assurance/evidence/solarize/red_phase_live.json</code> in the repository. 7 of 10 live Playwright tests failed against the pre-Solarize deployment.</p>

    <h3>Green phase (post-Solarize verification)</h3>
    <p class="small">After implementing the Solarize engine and refactoring the dashboard generator, the same 10 tests were run against the deployed GitHub Pages URL. <b>All 10 passed</b>, with zero console errors and zero page errors.</p>

    <h3>Two consecutive verification rounds</h3>
    <p class="small">Per the Solarize process requirement, two consecutive verification rounds were run against the live deployment with no new critical or major findings:</p>
    <ul class="small">
      <li><b>Round 1</b>: desktop 13/13 steps passed, mobile 4/4 steps passed, 0 console errors, 0 page errors, 0 failed requests.</li>
      <li><b>Round 2</b>: pytest 10/10 passed, comprehensive audit 17/17 passed (desktop 13 + mobile 4), 0 console errors, 0 page errors, 0 failed requests.</li>
    </ul>
    <p class="small">Evidence saved at:</p>
    <ul class="small">
      <li><code>audit/assurance/evidence/solarize/verification_round1_live.json</code></li>
      <li><code>audit/assurance/evidence/solarize/verification_round2_pytest.json</code></li>
      <li><code>audit/assurance/evidence/solarize/verification_round2_live_audit.json</code></li>
      <li><code>audit/assurance/evidence/solarize/live_audit_report.json</code> (machine-readable summary)</li>
      <li><code>audit/assurance/evidence/solarize/screenshots/</code> (desktop + mobile screenshots)</li>
      <li><code>audit/assurance/evidence/solarize/traces/desktop.zip</code> (Playwright trace)</li>
    </ul>

    <h3>Solarize Round 2 (this iteration)</h3>
    <p class="small">Round 2 added the methodology, audit-evidence, data-download, full-per-ad-table, and cluster-drill-down sections you are reading now. The new constraint was "all content should be in the website and accessible from the website" — previously the full per-ad table (4,540 records) was only downloadable as a JSONL file, not searchable in-page.</p>

    <h3>Build fingerprint</h3>
    <p class="small">The deployed dashboard exposes:</p>
    <ul class="small">
      <li><code>&lt;html data-build-fingerprint="solarize-..."&gt;</code> — the build fingerprint</li>
      <li><code>&lt;html data-commit-sha="..."&gt;</code> — the 40-char git commit SHA at generation time</li>
      <li><code>&lt;html data-solarize-version="1.0"&gt;</code> — the Solarize engine version</li>
    </ul>
    <p class="small">These attributes are verified by the live Playwright tests via <code>git cat-file -t &lt;sha&gt;</code> (real commit object) and <code>git merge-base --is-ancestor &lt;sha&gt; &lt;deployed-sha&gt;</code> (ancestor-or-self relationship).</p>
  </section>

  <!-- ========== ADINTEL NEW SECTION: Data Download (Solarize Round 2) ========== -->
  <section id="adintel-data" style="margin-top:16px;border:2px solid var(--violet);">
    <div class="story-step"><span class="step-num" style="background:var(--violet);">D</span><span class="step-text"><b>Data download.</b> All underlying data is downloadable from this website — no separate repository access required.</span></div>
    <h2>adintel: Data Download <span class="section-tag new">solarize</span></h2>
    <p class="small">Every dataset that powers this dashboard is also downloadable as a static JSON or JSONL file from the same GitHub Pages deployment. Click any link below to download.</p>

    <h3>Solarize engine outputs</h3>
    <table>
      <thead><tr><th>File</th><th class="num">Size</th><th>Description</th><th>Download</th></tr></thead>
      <tbody>
        <tr data-field="data-download" data-role="data-download">
          <td class="dim">solarize_summary.json</td>
          <td class="num">~870 KB</td>
          <td>Aggregate Solarize summary: build fingerprint, clustering benchmark, 4-way outlier counts, 3-population term-prevalence comparison with Wilson CI + Cohen's h + BH FDR, per-cluster explanations, top-300 per-ad selector records.</td>
          <td><a class="control data-download-link" href="solarize_summary.json" download data-role="data-download-link">Download JSON</a></td>
        </tr>
        <tr data-field="data-download" data-role="data-download">
          <td class="dim">solarize_per_ad.jsonl</td>
          <td class="num">~2.7 MB</td>
          <td>Full per-ad table: 4,540 records with record_id, title, platform, cluster_id, membership_strength, distance_to_centroid, silhouette, alternative_cluster_id, outlier_kinds, outlier_score, body_preview. Searchable in-page below, or download for offline analysis.</td>
          <td><a class="control data-download-link" href="solarize_per_ad.jsonl" download data-role="data-download-link">Download JSONL</a></td>
        </tr>
      </tbody>
    </table>

    <h3>Supporting adintel report data</h3>
    <p class="small">The historical adintel JSON files (clustering_summary, outlier_summary, full_data_results, cluster_alignment_report, deep_clustering_analysis, profile_sample, taxonomy_v2, etc.) are also available at <code>./&lt;filename&gt;.json</code> relative to this page.</p>
    <div class="viz-toolbar">
      <a class="control data-download-link" href="clustering_summary.json" download>clustering_summary.json</a>
      <a class="control data-download-link" href="outlier_summary.json" download>outlier_summary.json</a>
      <a class="control data-download-link" href="full_data_results.json" download>full_data_results.json</a>
      <a class="control data-download-link" href="cluster_alignment_report.json" download>cluster_alignment_report.json</a>
      <a class="control data-download-link" href="deep_clustering_analysis.json" download>deep_clustering_analysis.json</a>
      <a class="control data-download-link" href="profile_sample.json" download>profile_sample.json</a>
      <a class="control data-download-link" href="taxonomy_v2.json" download>taxonomy_v2.json</a>
      <a class="control data-download-link" href="checkpoint_registry.json" download>checkpoint_registry.json</a>
    </div>

    <h3>Full per-ad table (searchable, 4,540 records)</h3>
    <p class="small" data-role="data-download">The full per-ad table is searchable below. Type a record_id, title fragment, platform, or outlier kind. Results are loaded client-side via <code>fetch('solarize_per_ad.jsonl')</code> — no server required, works on static GitHub Pages.</p>
    <div class="viz-toolbar">
      <input id="adintel-full-ad-search" data-role="full-ad-table" type="search" placeholder="Search all 4,540 ads by record_id, title, platform, or outlier kind..." style="flex:1;min-width:260px;padding:6px 10px;border:1px solid var(--line);border-radius:6px;font-size:12px;" aria-label="Search the full per-ad table">
      <select id="adintel-full-cluster-filter" data-role="full-cluster-filter" class="control" aria-label="Filter full table by cluster">
        <option value="">All clusters</option>
        {_cluster_options_html}
      </select>
      <select id="adintel-full-outlier-filter" data-role="full-outlier-filter" class="control" aria-label="Filter full table by outlier kind">
        <option value="">All ads</option>
        <option value="any">Any outlier</option>
        <option value="detector">detector</option>
        <option value="density_noise">density_noise</option>
        <option value="cluster_enriched">cluster_enriched</option>
        <option value="boundary">boundary</option>
        <option value="none">inlier (no outlier flag)</option>
      </select>
      <span id="adintel-full-ad-count" class="small" style="color:var(--muted);">Loading 4,540 records...</span>
    </div>
    <div id="adintel-full-ad-results" data-role="full-ad-results" style="max-height:400px;overflow:auto;border:1px solid var(--line);border-radius:6px;margin-top:6px;">
      <p class="small" style="padding:8px;color:var(--muted);">Loading full per-ad table from solarize_per_ad.jsonl...</p>
    </div>
    <p class="small" style="color:var(--muted);margin-top:6px;">Note: the full table excludes the inliers with no outlier flag that fall in the bottom of the activity score. Use the top-300 selector in <a href="#adintel-clustering">the clustering section</a> for the highest-activity ads with full detail.</p>
  </section>

  <!-- ========== ADINTEL NEW SECTION: Challenge rounds ========== -->'''

assert NEW_SECTIONS_MARKER in src, "NEW_SECTIONS_MARKER not found"
src = src.replace(NEW_SECTIONS_MARKER, NEW_SECTIONS)
print("1. Added #adintel-methodology, #adintel-audit, #adintel-data sections: OK")

# ---------------------------------------------------------------------------
# 2. Add nav links for the new sections
# ---------------------------------------------------------------------------
NAV_MARKER = '<a href="#adintel-checkpoints">Checkpoints</a>'
NAV_REPLACEMENT = '''<a href="#adintel-checkpoints">Checkpoints</a>
      <a href="#adintel-methodology">Methodology</a>
      <a href="#adintel-audit">Audit</a>
      <a href="#adintel-data">Data</a>'''
assert NAV_MARKER in src, "NAV_MARKER not found"
src = src.replace(NAV_MARKER, NAV_REPLACEMENT)
print("2. Added nav links for Methodology, Audit, Data: OK")

# ---------------------------------------------------------------------------
# 3. Add the full-ad-table JS to the Solarize IIFE
# ---------------------------------------------------------------------------
JS_MARKER = """  renderResults();

  function applySolarizeHash() {"""
JS_ADDITION = """  // ============ Solarize Round 2: full per-ad table via fetch ============
  const fullSearch = document.getElementById('adintel-full-ad-search');
  const fullClusterFilter = document.getElementById('adintel-full-cluster-filter');
  const fullOutlierFilter = document.getElementById('adintel-full-outlier-filter');
  const fullResultsEl = document.getElementById('adintel-full-ad-results');
  const fullCountEl = document.getElementById('adintel-full-ad-count');
  let fullAdTable = null;
  let fullAdTableLoading = false;

  async function loadFullAdTable() {{
    if (fullAdTable || fullAdTableLoading) return fullAdTable;
    fullAdTableLoading = true;
    try {{
      // Try to fetch relative to the current page (works on GitHub Pages)
      const response = await fetch('solarize_per_ad.jsonl', {{cache: 'force-cache'}}});
      if (!response.ok) throw new Error(`HTTP ${{response.status}}`);
      const text = await response.text();
      fullAdTable = text.split('\\n').filter(l => l.trim()).map(l => {{
        try {{ return JSON.parse(l); }} catch {{ return null; }}
      }}).filter(Boolean);
      if (fullCountEl) fullCountEl.textContent = `${{fullAdTable.length}} records loaded`;
      return fullAdTable;
    }} catch (e) {{
      if (fullResultsEl) fullResultsEl.innerHTML = `<p class="small" style="padding:8px;color:var(--red);">Failed to load solarize_per_ad.jsonl: ${{e.message}}. The file is available at <a href="solarize_per_ad.jsonl">solarize_per_ad.jsonl</a> in this directory.</p>`;
      if (fullCountEl) fullCountEl.textContent = `Load failed`;
      return null;
    }} finally {{
      fullAdTableLoading = false;
    }}
  }}

  function matchesFullFilters(ad) {{
    if (fullClusterFilter && fullClusterFilter.value && String(ad.cluster_id) !== fullClusterFilter.value) return false;
    if (fullOutlierFilter && fullOutlierFilter.value) {{
      const kinds = ad.outlier_kinds || [];
      if (fullOutlierFilter.value === 'none') {{
        if (kinds.length > 0) return false;
      }} else if (fullOutlierFilter.value === 'any') {{
        if (kinds.length === 0) return false;
      }} else {{
        if (!kinds.includes(fullOutlierFilter.value)) return false;
      }}
    }}
    return true;
  }}

  function matchesFullQuery(ad, q) {{
    if (!q) return true;
    q = q.toLowerCase();
    return (
      (ad.record_id || '').toLowerCase().includes(q) ||
      (ad.title || '').toLowerCase().includes(q) ||
      (ad.platform || '').toLowerCase().includes(q) ||
      (ad.body_preview || '').toLowerCase().includes(q) ||
      (ad.outlier_kinds || []).join(' ').toLowerCase().includes(q)
    );
  }}

  function renderFullResults() {{
    if (!fullAdTable || !fullResultsEl) return;
    const q = (fullSearch && fullSearch.value) || '';
    const filtered = fullAdTable.filter(ad => matchesFullFilters(ad) && matchesFullQuery(ad, q)).slice(0, 100);
    if (fullCountEl) {{
      const total = fullAdTable.length;
      const matched = fullAdTable.filter(ad => matchesFullFilters(ad) && matchesFullQuery(ad, q)).length;
      fullCountEl.textContent = `${{matched}} / ${{total}} records match`;
    }}
    if (filtered.length === 0) {{
      fullResultsEl.innerHTML = '<p class="small" style="padding:8px;color:var(--muted);">No ads match. Try a different record ID, title fragment, platform, or outlier kind.</p>';
      return;
    }}
    fullResultsEl.innerHTML = filtered.map(ad => {{
      const kinds = (ad.outlier_kinds || []).join(', ') || 'inlier';
      return `<div class="ad-result-row" data-rid="${{escapeHtml(ad.record_id)}}">
        <b>${{escapeHtml((ad.title || 'Untitled').slice(0, 60))}}</b>
        <span class="plat-tag" style="background:var(--soft);border-radius:3px;padding:0 4px;font-size:9px;color:var(--muted);">${{escapeHtml(ad.platform || '?')}}</span>
        <code style="font-size:9px;color:var(--muted);">${{escapeHtml((ad.record_id || '').slice(0, 20))}}...</code>
        <span style="color:var(--muted);font-size:10px;">cluster=${{ad.cluster_id}} | ${{kinds}}</span>
      </div>`;
    }}).join('');
    // Wire click handlers — clicking a full-table row scrolls to the clustering
    // section's ad selector and pre-fills it with this record_id.
    fullResultsEl.querySelectorAll('.ad-result-row').forEach(row => {{
      row.addEventListener('click', () => {{
        const rid = row.dataset.rid;
        if (rid) {{
          // Pre-fill the top-300 selector and scroll to it
          if (selector) {{
            selector.value = rid.slice(0, 16);
            renderResults();
            // Try to select this ad directly if it's in the top-300
            const found = perAd.find(a => a.record_id === rid);
            if (found) {{
              selectAd(rid);
            }} else {{
              detailEl.innerHTML = `<p class="small" style="color:var(--amber);">Ad <code>${{escapeHtml(rid)}}</code> is in the full per-ad table but not in the top-300 embedded selector. Full detail is in <code>solarize_per_ad.jsonl</code>.</p>`;
            }}
            document.getElementById('ad-explorer-heading').scrollIntoView({{behavior:'smooth', block:'start'}});
          }}
        }}
      }});
    }});
  }}

  // Lazy-load the full table when the user first interacts with the full-ad-search
  if (fullSearch) {{
    fullSearch.addEventListener('focus', async () => {{
      if (!fullAdTable) {{
        await loadFullAdTable();
        renderFullResults();
      }}
    }});
    fullSearch.addEventListener('input', async () => {{
      if (!fullAdTable) {{
        await loadFullAdTable();
      }}
      renderFullResults();
    }});
  }}
  if (fullClusterFilter) fullClusterFilter.addEventListener('change', async () => {{
    if (!fullAdTable) await loadFullAdTable();
    renderFullResults();
  }});
  if (fullOutlierFilter) fullOutlierFilter.addEventListener('change', async () => {{
    if (!fullAdTable) await loadFullAdTable();
    renderFullResults();
  }});

  // ============ End Solarize Round 2: full per-ad table ============

  // Hash-based deep link: #adintel-ad=<rid>
  function applySolarizeHash() {"""
assert JS_MARKER in src, "JS_MARKER not found"
src = src.replace(JS_MARKER, JS_ADDITION)
print("3. Added full-per-ad-table JS via fetch(solarize_per_ad.jsonl): OK")

# ---------------------------------------------------------------------------
# 4. Make cluster-card click ALSO set the cluster filter
# ---------------------------------------------------------------------------
OLD_CLUSTER_CLICK = """  document.querySelectorAll('.cluster-example').forEach(el => {{
    el.addEventListener('click', () => {{
      const rid = el.dataset.recordId;
      if (rid) {{
        selector.value = rid.slice(0, 16);
        renderResults();
        selectAd(rid);
        document.getElementById('ad-explorer-heading').scrollIntoView({{behavior:'smooth', block:'start'}});
      }}
    }});
  }});"""
NEW_CLUSTER_CLICK = """  // Click on a cluster-example card -> select that ad AND set the cluster filter
  document.querySelectorAll('.cluster-example').forEach(el => {{
    el.addEventListener('click', () => {{
      const rid = el.dataset.recordId;
      const cid = el.dataset.clusterExample;
      if (cid != null && clusterFilter) {{
        clusterFilter.value = String(cid);
        renderResults();
      }}
      if (rid) {{
        selector.value = rid.slice(0, 16);
        renderResults();
        selectAd(rid);
        document.getElementById('ad-explorer-heading').scrollIntoView({{behavior:'smooth', block:'start'}});
      }}
    }});
  }});
  // Click on a cluster-card header -> set the cluster filter (R15: view all members)
  document.querySelectorAll('.cluster-card').forEach(el => {{
    el.addEventListener('click', (ev) => {{
      // Only fire if the click was on the card itself or its h4/badge (not on a
      // cluster-example child, which has its own handler).
      if (ev.target.closest('.cluster-example')) return;
      const cid = el.dataset.clusterId;
      if (cid != null && clusterFilter) {{
        clusterFilter.value = String(cid);
        renderResults();
        // Also set the full-table cluster filter
        if (fullClusterFilter) {{
          fullClusterFilter.value = String(cid);
          renderFullResults();
        }}
        document.getElementById('ad-explorer-heading').scrollIntoView({{behavior:'smooth', block:'start'}});
      }}
    }});
  }});"""
assert OLD_CLUSTER_CLICK in src, "OLD_CLUSTER_CLICK not found"
src = src.replace(OLD_CLUSTER_CLICK, NEW_CLUSTER_CLICK)
print("4. Made cluster-card click set the cluster filter (R15): OK")

# ---------------------------------------------------------------------------
# Write the patched file
# ---------------------------------------------------------------------------
PATH.write_text(src, encoding="utf-8")
print(f"\nDone. Patched {PATH}")
print(f"  New size: {len(src)} bytes")
