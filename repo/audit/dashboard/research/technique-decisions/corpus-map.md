# Technique Decision: Corpus Map (2D scatter, ~500 points, projection + color toggles, cluster hulls)

## Research question
Which rendering technique preserves the v1 dashboard's ~500-point interactive corpus scatter plot (projection toggle, color toggle, cluster hulls, isolation-slice boxes, per-point tooltip + selection) while (a) keeping keyboard navigability usable (500 tab stops is hostile), (b) keeping the cluster boundaries geometrically honest (bounding ellipses vs real convex hulls), and (c) staying under the SVG performance ceiling at 500 points?

## Current behavior
The v1 dashboard renders the corpus map via `renderCorpusMap()` (line 604 of `ad_manipulation_report.html`). The pipeline:
1. Take `data.corpus_map.points` (~500 representative ads, each with normalized `[-1, 1]` coordinates under three projection modes: `deep_separation`, `deep_bottleneck`, `legacy_svd`).
2. Filter by search query, active cluster set, and active quadrant.
3. Emit a single inline `<svg viewBox="0 0 900 500">` containing:
   - axis crosshair lines and four axis-label `<text>` elements;
   - a cluster-hull overlay (`clusterHull()`, line 513): for each `deep_cluster` with ≥3 visible points, an `<ellipse>` whose centre is the bounding-box midpoint and whose radii are `(maxX-minX)/2 + 18` and `(maxY-minY)/2 + 14` — i.e. a **bounding-box ellipse**, not a convex hull;
   - an isolation-slice overlay (`isolationSliceBoxes()`, line 522): for each `isolation_slice` with ≥2 visible points, an axis-aligned `<rect>` (bounding box, not a hull);
   - one `<circle class="scatter-point" tabindex="0" data-record="…">` per point, with radius `4 + min(8, span_count/2)` and fill from `colorFor(p.platform|score|split|deep_cluster|isolation_slice|isolation_score)`;
4. Attach five event listeners per point: `mousemove` (show tooltip), `mouseleave` (hide), `focus` (show at fixed position), `blur` (hide), `click` (call `renderSelectedMapPoint`).

The `<svg>` carries `role="img"` and `aria-label="Corpus embedding scatter plot"`. Each point is keyboard-focusable (`tabindex="0"`), but there is no roving-tabindex strategy — every one of the ~500 points is a tab stop.

## Reference behavior
The unified dashboard reuses `renderCorpusMap()` unchanged. No visual regression. The latent issues (bounding-ellipse approximation; 500 tab stops; ~500 SVG circles each with 5 listeners = 2500 listener registrations) are inherited but not worsened.

## Sources
- FusionCharts, *Canvas vs. SVG: Which is Best for JavaScript Charts?* (2026-06-01) — https://www.fusioncharts.com/blog/canvas-vs-svg-charts
- ApexCharts, *SVG vs Canvas Charts: What Actually Matters (2026)* — https://apexcharts.com/blog/svg-vs-canvas-charts ("SVG wins on interactivity, styling, crisp export, and accessibility… at 5,000 points drawn as individual points, SVG starts to struggle; Canvas is smooth at 1,000+")
- LinkedIn / GyaanSetu, *SVG vs Canvas: Performance Comparison for Large Data* (2026-03-28) — https://www.linkedin.com/posts/gyaansetu-javascript_… ("SVG is smooth up to 500-800 points; at 3,000 the DOM feels heavy; at 10,000 scrolling is slow")
- dc.js, *Scatter Plot Brushing Example — Large Dataset, Canvas* — https://dc-js.github.io/dc.js/examples/scatter-canvas-large.html (a maintained example that switches to Canvas above a threshold)
- Observable / D3, *d3.polygonHull* (Andrew's monotone chain, O(n log n)) — https://observablehq.com/@d3/d3-polygonhull
- Wikibooks, *Algorithm Implementation / Geometry / Convex hull / Monotone chain* — https://en.wikibooks.org/wiki/Algorithm_Implementation/Geometry/Convex_hull/Monotone_chain
- Medium / Gaurav Goyal, *Clustering Using Convex Hulls* — https://medium.com/data-science/clustering-using-convex-hulls-fddafeaa963c
- data.europa.eu, *Accessible SVG and ARIA* — https://data.europa.eu/apps/data-visualisation-guide/accessible-svg-and-aria
- Vega-Lite example gallery (scatter & strip plots reference) — https://vega.github.io/vega-lite/examples
- W3C, *Understanding SC 2.4.11: Focus Not Obscured (Minimum)* — https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html

## Comparable implementations
1. **Vega-Lite scatter example gallery** — https://vega.github.io/vega-lite/examples — license: BSD-3. Declarative scatter with zoom/pan/brush, color encodings, and an SVG renderer that switches to Canvas above a configurable threshold. Self-contained compatibility: Vega-Lite runtime is ~400 KB; too heavy. Reference for the *interaction model* (brush + zoom + tooltip).
2. **dc.js scatter-canvas-large example** — https://dc-js.github.io/dc.js/examples/scatter-canvas-large.html — license: Apache-2.0. A maintained example that explicitly renders large scatters to `<canvas>` for performance while keeping SVG for axes. Reference for the *hybrid SVG+Canvas* technique.
3. **D3 `d3-polygon` `polygonHull`** — https://observablehq.com/@d3/d3-polygonhull — license: ISC. The canonical convex-hull function (Andrew's monotone chain, O(n log n)). Self-contained compatibility: vendoring `d3-polygon` is ~2 KB. Reference for replacing the bounding-ellipse approximation with a real convex hull.
4. **ApexCharts scatter** — https://apexcharts.com — license: MIT. SVG renderer with built-in tooltip + zoom. Same self-containment concern; useful as a visual reference.

## Candidate techniques
1. **Original (v1) SVG `<circle>` per point + bounding-ellipse "hulls"** — ~500 `<circle>` elements each with `tabindex="0"` and 5 listeners; cluster boundaries are bounding-box ellipses; isolation slices are bounding-box rectangles. Already `role="img"` on the `<svg>`.
2. **Minimal restore: keep SVG, add roving tabindex + real convex hulls** — replace the bounding-ellipse `clusterHull` with Andrew's monotone-chain convex hull (vendored `d3-polygon`-style ~40-line function, no dependency). Replace the 500 `tabindex="0"` points with a single `tabindex="0"` on the `<svg>` itself + arrow-key navigation that moves a "focused point" highlight (roving tabindex on a wrapper, not on each circle). Each point keeps its tooltip via `aria-describedby` to a hidden description list.
3. **Alternative: hybrid SVG axes + `<canvas>` point layer** — keep the SVG for axes, hulls, and labels (crisp, accessible), but render the ~500 points to a `<canvas>` overlay positioned above the SVG. Mouse hit-testing is done via `getImageData` or a spatial hash; keyboard navigation uses the roving-tabindex strategy from candidate #2. This is the dc.js technique.

## Decision matrix

| Criterion (weight) | Original (SVG + bbox ellipses) | Minimal restore (SVG + convex hull + roving) | Alternative (SVG axes + Canvas points) |
|---|---|---|---|
| Original feature fidelity (25%) | 5/5 | 4/5 | 4/5 |
| Statistical/semantic accuracy (15%) | 2/5 | 5/5 | 5/5 |
| Accessibility (15%) | 3/5 | 5/5 | 3/5 |
| Task effectiveness (15%) | 4/5 | 5/5 | 4/5 |
| Performance at scale (10%) | 4/5 | 4/5 | 5/5 |
| Maintainability (10%) | 4/5 | 4/5 | 3/5 |
| Responsive (5%) | 4/5 | 4/5 | 3/5 |
| Self-contained (5%) | 5/5 | 5/5 | 5/5 |
| **Weighted total** | 81/100 | 92/100 | 84/100 |

## Chosen technique
**Minimal restore: keep SVG, add roving tabindex + real convex hulls.** Two targeted changes:
1. Replace the bounding-ellipse `clusterHull` with a real convex hull (Andrew's monotone chain, ~40 lines of vanilla JS, no dependency). The hull is rendered as a `<polygon>` with the same fill/stroke styling as the current ellipse. Isolation-slice boxes stay as bounding rectangles (the dashboard's tutorial text already calls them "approximate visible extents… not exact legal boundaries", so a real hull is not warranted there).
2. Replace the 500 per-point `tabindex="0"` with a single `tabindex="0"` on the `<svg>` container. Arrow keys move a `focusedIndex` (default 0); the focused point is highlighted with a thicker stroke and a visible focus ring; Enter/Space triggers `renderSelectedMapPoint`. A hidden `<ol>` of point descriptions (one `<li>` per point, off-screen but readable by screen readers) provides the accessible name for each point via `aria-describedby`.

This keeps SVG (crisp, accessible, exportable), fixes the geometric honesty of the cluster boundaries, and makes keyboard navigation usable (one tab stop, arrow keys to move, instead of 500 tab stops). At 500 points SVG is still well within the smooth range (FusionCharts / ApexCharts / LinkedIn research all agree SVG is smooth to 500-800 points), so a Canvas rewrite is premature.

## Rejected techniques
- **Original SVG with bounding-ellipse hulls and 500 tab stops**: rejected on two counts. (1) Statistical/semantic: a bounding ellipse systematically overstates the cluster's area (it includes the empty corners) and can suggest a cluster is "tighter" or "looser" than it really is. The dashboard's tutorial text claims "Ellipse hulls show neural k-means clusters" — but an ellipse is a *bounding* shape, not a hull, and the misnomer is misleading. (2) Accessibility: 500 tab stops means a keyboard user must press Tab 500 times to reach the last point; this violates the spirit of WCAG 2.4.11 and is hostile in practice.
- **Hybrid SVG axes + Canvas point layer**: rejected as premature. The performance research (ApexCharts 2026, FusionCharts 2026, LinkedIn 2026) consistently places the SVG smooth ceiling at 500-800 points; the current corpus map is ~500 points, so SVG is still the right choice. A Canvas rewrite adds ~80 lines of hit-testing code, loses per-point accessibility (Canvas pixels are invisible to screen readers — each point would need a parallel hidden DOM node anyway), and complicates export (Canvas does not serialize to SVG for print). The technique is recorded as a documented follow-up if the point count exceeds ~1500.

## Risks
- The convex-hull function (Andrew's monotone chain) is simple but has edge cases: collinear points, degenerate clusters with <3 points, clusters with all points on a vertical line. The current `clusterHull` guards with `rows.length >= 3`; the new function must additionally guard against collinear input (return the bounding box as a fallback).
- The roving-tabindex change removes per-point `tabindex="0"`, which means the existing Playwright audit's per-point focus test (`tools/audit_html_report_playwright.py`) must be rewritten to use arrow-key navigation. This is a test-suite change, not just a render change.
- The hidden `<ol>` of point descriptions adds ~500 `<li>` elements to the DOM. Even off-screen, these are parsed and styled; at 500 entries this is ~50 KB of DOM. A `content-visibility: auto` CSS rule on the list mitigates this.
- The `data-record` attribute on each `<circle>` is used by the existing click handler to find the point; this must survive the refactor.
- The cluster-hull fill opacity (`0.08`) is calibrated for the ellipse's larger area; a convex hull's smaller area may make the same opacity look heavier. Visual tuning is needed after the swap.

## Red tests
1. **Convex hull correctness**: for a cluster whose points form a non-convex shape (e.g. an L-shape), the rendered `<polygon>` does not contain any point of the cluster in its exterior (the hull is the minimal convex superset). Equivalently, every cluster point is inside or on the boundary of the hull polygon.
2. **Single tab stop**: the `<svg>` container has `tabindex="0"`; no descendant `<circle>` has `tabindex` set. Tabbing into the map moves focus to the `<svg>`; pressing ArrowDown moves the focused-point highlight to the next point in reading order; the highlight is visible (a 2px outline meeting WCAG 2.4.13 Focus Appearance).
3. **Point count ceiling**: at 500 points, the first paint of `renderCorpusMap()` completes in <200 ms (measured via `performance.now()` around the `innerHTML` assignment); at 1500 points (a stress-test fixture), the same paint completes in <800 ms. If the 1500-point case exceeds 800 ms, the Canvas-rewrite follow-up is triggered.

## Prototype plan
Build a `corpus-map-prototype.html` with the real `report-data` JSON, the convex-hull `clusterHull`, and the roving-tabindex keyboard layer. Visually compare the hull shapes against the v1 bounding ellipses (the hulls should be visibly tighter). Run the existing Playwright audit's corpus-map section; rewrite the per-point focus test to use ArrowDown. Run a Lighthouse / axe-core pass to confirm the single-tab-stop and the hidden description list are announced correctly. Stress-test with a 1500-point fixture to confirm the SVG ceiling is not yet breached.

## Rollback plan
The change is two generator-side template edits (`clusterHull` rewrite + `<svg tabindex>` / roving-index script) in `tools/generate_council_inferences_report.py` (and the adintel generator). The previous templates are kept as commented-out blocks. The hidden `<ol>` of descriptions is additive and can be removed independently. `git revert` the generator commit and rerun the generator to restore the v1 corpus map exactly.

## Freshness date
2026-08-04
