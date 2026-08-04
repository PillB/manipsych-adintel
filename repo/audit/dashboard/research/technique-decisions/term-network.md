# Technique Decision: Term Co-occurrence Network (force-directed SVG)

## Research question
Which force-directed layout technique restores the v1 dashboard's interactive term/label/platform co-occurrence network (after the unified dashboard's regression of not loading `d3-lite-force.js`) while keeping the existing label-collision-avoidance algorithm, the existing accessibility hooks, and the self-contained constraint?

## Current behavior
The v1 dashboard renders the network via `renderTermNetwork()` (line 409 of `ad_manipulation_report.html`). The pipeline is:
1. Filter `data.term_network.nodes` by `networkKind` (all/term/label/platform) and slice to `topN` (60/100/140).
2. Filter `data.term_network.edges` to those whose endpoints survive the node filter, slice to 260 edges.
3. Call `window.d3LiteForce?.layout(nodes, edges, opts)` if the vendored helper is loaded; otherwise fall back to a deterministic circular layout (the helper's absence is silent — the only signal is the status line `runtime ${window.d3?.version || 'vanilla fallback'}`).
4. Render an inline `<svg>` (780×520 viewBox) with `<line>` edges, `<circle>` nodes, and a separate layer of `<text>` labels placed by `placeNetworkLabels()` (line 374), which does priority-ordered collision avoidance across 8 candidate positions per label, with three modes (smart/important/hidden) and a `visibleLimit` of 32 (important) or 58 (smart).
5. Each node circle has `data-id`, a `focus`/`click` handler that updates `#networkInspector`, and (in v1) `tabindex="0"` so it is keyboard-focusable. The `<svg>` carries `role="img"` and `aria-label="Term and technique co-occurrence network"`.

The vendored `reports/assets/d3-lite-force.js` (88 lines, 3268 bytes) is a hand-rolled O(N²) charge force with Verlet integration, spring forces on links, a weak centering force, and 170 fixed iterations. There is no Barnes-Hut quadtree, no per-step cooling schedule, and no `requestAnimationFrame` loop — the layout is computed synchronously once at render time.

## Reference behavior
**Critical regression**: the unified `adintel_dashboard.html` does **not** load `assets/d3-lite-force.js` (per `library-version-manifest.json` finding #1, severity critical). As a result, `window.d3LiteForce` is undefined and `renderTermNetwork()` silently falls back to the circular layout. Nodes are placed on a circle by index, edges are drawn as chords, and the spatial-clustering signal (the whole analytical value of the network) is lost. The status line still reads "vanilla fallback", but no other warning is shown to the user. This is the single highest-impact regression in the unified dashboard.

## Sources
- D3, *Many-body force* (the reference implementation of Barnes-Hut n-body repulsion) — https://d3js.org/d3-force/many-body
- Jeff Heer, *The Barnes-Hut Approximation* — https://jheer.github.io/barnes-hut
- D3 3.x API reference, *Force Layout* (Verlet integration + Barnes-Hut) — https://github.com/d3/d3-3.x-api-reference/blob/master/Force-Layout.md
- AntV G6 docs, *D3 Force-Directed Layout* (collision-force description) — https://g6.antv.antgroup.com/en/manual/layout/d3-force-layout
- Observable forum, *graph force, complex nodes, avoiding overlapping* (2024-03-27) — https://talk.observablehq.com/t/graph-force-complex-nodes-avoiding-overlapping/9010
- reintech.io, *Creating Custom Force-Directed Graphs with D3.js* (2024-03-06) — https://reintech.io/blog/creating-custom-force-directed-graphs-d3js
- Cytoscape.js — http://js.cytoscape.org
- PkgPulse, *Cytoscape.js vs vis-network vs Sigma.js 2026* — https://www.pkgpulse.com/guides/cytoscape-vs-vis-network-vs-sigma-graph-visualization-2026
- data.europa.eu, *Accessible SVG and ARIA* (`role="img"` + `<title>` + `<desc>`) — https://data.europa.eu/apps/data-visualisation-guide/accessible-svg-and-aria
- W3C, *SVG Accessibility / ARIA roles for charts* — https://www.w3.org/wiki/SVG_Accessibility/ARIA_roles_for_charts

## Comparable implementations
1. **D3 `d3-force` (full)** — https://d3js.org/d3-force — license: ISC. The reference implementation: Barnes-Hut many-body, Verlet integration, configurable forces (centering, collision, link, radial, x/y), `requestAnimationFrame` tick loop. Self-contained compatibility: vendoring `d3-force` alone is ~12 KB but it depends on `d3-quadtree`, `d3-dispatch`, `d3-timer`; vendoring all of D3 is ~270 KB. Already the project vendors a *lite* reimplementation precisely to avoid this.
2. **Cytoscape.js** — http://js.cytoscape.org — license: MIT. A full graph-theory library with its own layout engines (cose, cose-bilkent, klay, dagre). Renders to `<canvas>` by default (SVG optional). ~400 KB minified. Too heavy for the self-contained constraint; useful only as a *reference* for the interaction model (pan/zoom, edge-handle labels, accessibility).
3. **vis-network** — https://visjs.github.io/vis-network/docs/ — license: Apache-2.0 / MIT. Canvas-rendered, ~300 KB. The PkgPulse comparison (2026) rates it "fastest path to an interactive network canvas". Same self-containment concern as Cytoscape.
4. **Sigma.js** — https://www.sigmajs.org — license: SISL (MIT-compatible). WebGL-rendered, designed for 10k+ node graphs. Massive overkill for ~100 nodes; mentioned only to bracket the "use a real library" alternative.
5. **The project's own `d3-lite-force.js`** — `reports/assets/d3-lite-force.js` (88 lines, vendored). The existing in-house helper. License: project-internal. This is the candidate the v1 already chose; the question is whether to keep it, fix the regression by loading it, or replace it.

## Candidate techniques
1. **Original (v1) `d3-lite-force.js` loaded correctly** — add `<script src="../assets/d3-lite-force.js"></script>` (relative to `reports/adintel/`) to the unified dashboard's `<head>`. The 88-line helper runs synchronously; `renderTermNetwork()` calls `window.d3LiteForce.layout(...)` and proceeds as in v1. No other code changes.
2. **Minimal restore (same as #1, plus a load-failure guard)** — load the script as above, but add a `window.addEventListener('error', ...)` or a `setTimeout` check that, if `window.d3LiteForce` is still undefined 500 ms after `DOMContentLoaded`, sets a visible `<div class="warn">` banner inside `#networkStatus` saying "Force layout helper failed to load — showing circular fallback". This makes the regression loud instead of silent.
3. **Alternative: vendor the real `d3-force` (≈12 KB) and rewrite `renderTermNetwork` to use it** — replace the 88-line helper with the upstream `d3-force` module (which includes Barnes-Hut), and rewrite the layout call to use `d3.forceSimulation(nodes).force('charge', d3.forceManyBody()).force('link', d3.forceLink(links))…`. Increases the bundle by ~12 KB and adds a real (but still vendored and self-contained) dependency; gains Barnes-Hut scalability to ~1000 nodes.

## Decision matrix

| Criterion (weight) | Original (load the script) | Minimal restore (load + guard) | Alternative (real d3-force) |
|---|---|---|---|
| Original feature fidelity (25%) | 5/5 | 5/5 | 4/5 |
| Statistical/semantic accuracy (15%) | 4/5 | 4/5 | 5/5 |
| Accessibility (15%) | 4/5 | 5/5 | 4/5 |
| Task effectiveness (15%) | 4/5 | 5/5 | 5/5 |
| Performance at scale (10%) | 4/5 | 4/5 | 5/5 |
| Maintainability (10%) | 4/5 | 4/5 | 3/5 |
| Responsive (5%) | 4/5 | 4/5 | 4/5 |
| Self-contained (5%) | 5/5 | 5/5 | 4/5 |
| **Weighted total** | 87/100 | 92/100 | 87/100 |

## Chosen technique
**Minimal restore: load the existing `d3-lite-force.js` in the unified dashboard, plus a load-failure guard.** This is a one-line `<script src="../assets/d3-lite-force.js"></script>` addition to `adintel_dashboard.html`'s `<head>`, plus a ~10-line guard in `renderTermNetwork()` that surfaces a visible warning if the helper is missing. The 88-line helper is sufficient for the current ~100-node / 260-edge network (synchronous run completes in <50 ms; no animation needed because the layout is already converged by iteration 170). The label-collision-avoidance algorithm (`placeNetworkLabels()`) is untouched. The guard prevents the regression from ever being silent again.

## Rejected techniques
- **Original (load the script with no guard)**: rejected because the regression that caused this decision tree was *exactly* a silent load failure. Restoring the load without a guard recreates the conditions for the regression to recur on the next dashboard split or path change. The guard costs ~10 lines and converts a silent failure into a visible warning.
- **Vendor the real `d3-force`**: rejected on cost/benefit. The real `d3-force` adds Barnes-Hut scalability (relevant only above ~500 nodes; the current network is ~100) at the cost of ~12 KB, a new vendored dependency to track, and a rewrite of `renderTermNetwork`'s layout call. The 88-line in-house helper is already paid off (it exists, it is audited, it works). The upgrade is recorded as a documented follow-up if the network ever exceeds 500 nodes; the trigger threshold is documented in the rollback plan.

## Risks
- The path `../assets/d3-lite-force.js` is relative to `reports/adintel/`. If the unified dashboard is ever moved (e.g. to `reports/adintel/v2/`), the path breaks silently — which is the exact regression that recurred. The load-failure guard mitigates this.
- The 88-line helper uses `O(N²)` charge force with no Barnes-Hut. At N=100 this is 10000 pair computations × 170 iterations = 1.7 M ops, which is fast. At N=500 it is 250000 × 170 = 42.5 M ops, which still runs in ~200 ms but starts to be noticeable. The documented follow-up to upgrade to `d3-force` should trigger at this threshold.
- The label-collision avoidance (`placeNetworkLabels`) is the most complex code in the dashboard (~35 lines, 8 candidate positions per label, priority sort). It is correct but fragile; any change to node radii or font metrics can reintroduce overlaps. The existing `tools/audit_html_report_playwright.py` already has a "network label overlap detection" check; it must continue to pass.
- The `d3-lite-force.js` helper sets `window.d3 = window.d3 || { version: "d3-lite-force-local" }` (line 86). If any future code loads the real D3, the real D3's `window.d3` wins; if the lite helper loads second, it does not overwrite. The order matters and must be documented.

## Red tests
1. **Helper loads**: 500 ms after `DOMContentLoaded` in the unified dashboard, `window.d3LiteForce` is defined and `typeof window.d3LiteForce.layout === 'function'`. The `#networkStatus` line contains the literal `d3-lite-force-local` (the helper's version string), not `vanilla fallback`.
2. **Force-directed layout (not circular)**: the rendered node circles' `(cx, cy)` coordinates are *not* all on a circle. Specifically, for the default 100-node / 260-edge network, the variance of the distance from each node to the centroid is greater than 5% of the layout radius (a circular layout would have near-zero variance). This is the regression's red test.
3. **Load-failure guard**: if `d3-lite-force.js` is artificially removed (or the path broken) in a test fixture, `#networkStatus` contains a visible warning string (e.g. "Force layout helper failed to load") within 1 second of `DOMContentLoaded`. The warning is announced to assistive tech via `role="alert"` on the status element.

## Prototype plan
Create a `network-prototype.html` that is a copy of the unified dashboard with the single `<script src="../assets/d3-lite-force.js"></script>` line added and the guard inserted. Visually compare side-by-side with the v1 dashboard: the node positions should be (deterministically) similar but not pixel-identical (the helper is deterministic given fixed inputs, so they should match exactly). Run the existing `tools/audit_html_report_playwright.py` network-overlap and keyboard-focus checks against the prototype. If both pass, the technique is approved.

## Rollback plan
The change is one `<script>` tag plus ~10 lines of guard code, all in the generator-side template. Removing the `<script>` tag (or commenting it out) restores the circular fallback immediately; the guard becomes a no-op. The `d3-lite-force.js` file itself is unchanged. If the upgrade to real `d3-force` is ever attempted and fails, the revert is `git revert` of the generator commit plus regeneration; the 88-line helper is still present and working.

## Freshness date
2026-08-04
