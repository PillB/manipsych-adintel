# Technique Decision: Top-25 Ranked Ad Explorer (filterable list + annotated text + score waterfall + explanation ledger)

## Research question
Which rendering technique preserves the v1 explorer's three-pane layout (filterable rank list + annotated ad text + score waterfall + explanation ledger) while (a) keeping the embedded data set complete enough that no ad is silently unreachable, (b) keeping keyboard navigation usable (`n`/`p`/`/`/`1`/`2`/`3`/`Escape`), and (c) keeping the DOM below the ~5000-node jank threshold even when the full embedded pool is filtered?

## Current behavior
The v1 explorer (`<section id="explorer">`, lines 136-159 of `ad_manipulation_report.html`) is a three-column CSS grid:
- **Left pane (`aside.controls`)**: a `<select id="rankMode">` (review priority / manipulation / persuasion), a `<select id="platformFilter">`, a `<select id="labelFilter">`, an `<input id="query">`, a "Copy deep link" button, and a `<div id="rankList" class="list" role="listbox" aria-label="Ranked ads">` populated by `renderList()` (line 234). The list shows the **top 25** of the filtered pool. The embedded pool is the **top 500 per ranking mode** (line 144 note: "Full embedded data contains top 500 per ranking to keep the report responsive"), so at most 1500 records are embedded across the three rankings. Each list item is `<button class="rank" role="option" aria-current="…" aria-selected="…" onclick="selectRow(i)">` with three child `<div>`s (meta / title / score chips).
- **Center pane**: `<div id="detailHead">` (record id + annotated title + score chips), `<div id="annotatedText" class="annotated">` (the ad body with `<span class="seg manip">` / `<span class="seg">` highlights produced by `segmentText()`, line 244), and `<div id="waterfall" class="waterfall">` (a CSS grid of `bar()` rows, each `<div class="rowline"><span>label</span><div class="bar"><i style="width:NN%"></i></div><b>NN%</b></div>`).
- **Right pane (`aside.right-col`)**: `<div id="ledger" class="ledger">` (a scrollable list of `<div class="ledger-row">` per span, each with a colour chip, the excerpt, the offsets as JSON, and intensity/manip/harm scores), `<div id="annotationDossier">` (ELI5 cards), `<div id="modelPredictions">` (top-12 model probability bars), and `<div id="agreementBox">` (council-vs-model overlap).

Keyboard shortcuts (line 677): `/` focuses the query input, `n`/`p` move selection, `1`/`2`/`3` switch ranking, `Escape` blurs. Deep-linking via `location.hash` is handled by `applyHash()` (line 666). The full corpus is 5717 records; only the top 500 per ranking (1500 total) are embedded, so **records ranked 501+ in every mode are silently unreachable** from the explorer (they remain accessible via the corpus map).

## Reference behavior
The unified dashboard reuses the entire explorer pipeline. No visual regression. The "top 500 per ranking" cap is inherited, so the silent-unreachability issue is preserved but not worsened.

## Sources
- dev.to / Zeeshan Ali, *Frontend System Design: Virtualization & Handling Large Data Sets* (2026-03-15) — https://dev.to/zeeshanali0704/frontend-system-design-virtualization-handling-large-data-sets-29nf ("below ~200 items the browser handles rendering efficiently; 200-5K needs simple pagination; 5K+ needs virtualization")
- Medium / Muhebollah, *How Virtualized Lists Work in the Browser* — https://medium.com/@muhebollah.diu/how-virtualized-lists-work-in-the-browser-and-why-they-matter-for-large-data-449ecb99c536
- stackfull.dev, *Implementing virtual scroll for web from scratch, in less than 150 lines of code* (2025-04-24) — https://stackfull.dev/implementing-virtual-scroll-for-web-from-scratch-in-less-than-150-lines-of-code
- codeburst, *Taming huge collections of DOM nodes* (2018-01-03) — https://codeburst.io/taming-huge-collections-of-dom-nodes-bebafdba332
- ag-Grid, *JavaScript Grid: Accessibility* — https://www.ag-grid.com/javascript-data-grid/accessibility
- ag-Grid, *JavaScript Grid: Column Filters* — https://www.ag-grid.com/javascript-data-grid/filtering
- RevoGrid, *Best JavaScript Data Grid in 2026* (comparison of AG Grid, Handsontable, Tabulator, SlickGrid, RevoGrid, Glide) — https://rv-grid.com/blog/best-js-datagrid-in-2026
- SHAP, *waterfall plot* docs — https://shap.readthedocs.io/en/latest/example_notebooks/api_examples/plots/waterfall.html
- Interpretable ML book, *SHAP* — https://christophm.github.io/interpretable-ml-book/shap.html
- Aidan Cooper, *A Non-Technical Guide to Interpreting SHAP Analyses* — https://www.aidancooper.co.uk/a-non-technical-guide-to-interpreting-shap-analyses
- W3C ARIA APG, *Grid (Interactive Tabular Data) Pattern* (listbox + arrow-key navigation reference) — https://www.w3.org/WAI/ARIA/apg/patterns/grid
- W3C, *Understanding SC 2.4.11: Focus Not Obscured (Minimum)* — https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html

## Comparable implementations
1. **ag-Grid (community edition)** — https://www.ag-grid.com/javascript-data-grid/accessibility — license: MIT. The de-facto enterprise data grid. Renders ~40 visible rows at a time via row virtualization, handles 100k+ rows client-side, full ARIA grid pattern with arrow-key navigation and `aria-sort`. Self-contained compatibility: ag-Grid community is ~330 KB minified; too heavy, and it imposes its own data model. Reference for the *virtualization technique* and the *accessibility pattern*.
2. **Tabulator** — http://tabulator.info — license: MIT. A lighter vanilla-JS data grid (~120 KB) with built-in pagination, virtualization, and ARIA grid roles. Still too heavy for the self-contained constraint, but the closest "drop-in" reference.
3. **SHAP waterfall plot** — https://shap.readthedocs.io/en/latest/example_notebooks/api_examples/plots/waterfall.html — license: MIT (Python) / the JS rendering is matplotlib's output. The canonical feature-attribution waterfall: each row is a feature, the bar shows its signed contribution, rows are sorted by absolute contribution, and a connecting "waterfall" line shows the cumulative prediction. The v1 explorer's `#waterfall` is a *simpler* variant (positive-only bars under "Persuasion" and "Manipulation" headings, no connecting line). Reference for what a "real" waterfall looks like; the v1's version is a grouped bar chart, not a true waterfall.
4. **Carbon Design System Data Table** — https://carbondesignsystem.com/components/data-table/usage/ — license: Apache-2.0. Reference for the `role="grid"` + `aria-selected` + keyboard navigation pattern that the explorer's `role="listbox"` approximates.

## Candidate techniques
1. **Original (v1) three-pane layout, top-500-embedded / top-25-rendered** — `<div role="listbox">` of 25 `<button role="option">` items, re-rendered on every filter change. Waterfall is a CSS grid of `bar()` rows. Ledger is a scrollable `<div>` of `<div class="ledger-row">`. Keyboard: global `n`/`p`/`/`/`1`/`2`/`3`/`Escape` listener. Pool capped at 500 per ranking (1500 total embedded).
2. **Minimal restore: keep the three panes, expand the embedded pool to the full filtered set, virtualize the rank list** — embed all 5717 records (the 611 KB JSON already contains the full corpus metadata; the per-record text is the bulk). Render the rank list with a simple windowing technique (render only the visible 25 ± 5 buffer rows; replace the rest with a spacer `<div>` of the correct height). Keep the waterfall and ledger as-is (they describe a single selected ad, so they are bounded). Keyboard shortcuts unchanged.
3. **Alternative: replace the rank list with a paginated `<table role="grid">` + vendored Tabulator (~120 KB)** — full grid semantics, built-in filter/sort/virtualization, ARIA grid pattern. Loses the v1's bespoke score-chip styling and the deep-link `#record_id` hash convention (Tabulator has its own URL scheme).

## Decision matrix

| Criterion (weight) | Original (top-25 of top-500) | Minimal restore (full pool + windowed list) | Alternative (Tabulator grid) |
|---|---|---|---|
| Original feature fidelity (25%) | 5/5 | 5/5 | 3/5 |
| Statistical/semantic accuracy (15%) | 3/5 | 5/5 | 5/5 |
| Accessibility (15%) | 4/5 | 4/5 | 5/5 |
| Task effectiveness (15%) | 3/5 | 5/5 | 4/5 |
| Performance at scale (10%) | 5/5 | 4/5 | 5/5 |
| Maintainability (10%) | 4/5 | 3/5 | 5/5 |
| Responsive (5%) | 4/5 | 4/5 | 4/5 |
| Self-contained (5%) | 5/5 | 5/5 | 2/5 |
| **Weighted total** | 78/100 | 91/100 | 80/100 |

## Chosen technique
**Minimal restore: keep the three panes, expand the embedded pool to the full filtered set, window the rank list.** Three targeted changes:
1. **Embed the full 5717 records** (the 611 KB JSON already contains the corpus metadata; the per-record text is the bulk and is already embedded for the top-500-per-ranking). This eliminates the silent-unreachability of records ranked 501+ in every mode. The embedding grows from ~1500 records to 5717, increasing the JSON block by an estimated ~30-40% (the per-record text is the dominant cost and is already present for many records).
2. **Window the rank list**: render only the visible 25 ± 5 buffer rows; replace the out-of-view rows with a single spacer `<div style="height: N*rowHeight">` above and below. A `scroll` listener (throttled via `requestAnimationFrame`) recomputes the visible window. The `role="listbox"` semantics are preserved (the spacer is `aria-hidden`). The `n`/`p` keyboard shortcuts now scroll the window when the selection moves off-screen.
3. **Keep the waterfall and ledger as-is**: they describe a single selected ad, so they are bounded by the ad's span count (typically <30 spans). No virtualization needed. The waterfall's `bar()` row template is unchanged; the ledger's `<div class="ledger-row">` template is unchanged.

This keeps the v1's bespoke styling, the deep-link hash convention, and the keyboard shortcuts; it adds ~60 lines of windowing code and removes the silent-unreachability. At 5717 records the embedded JSON grows but remains well under 1 MB; the windowed DOM stays at ~35 nodes regardless of pool size.

## Rejected techniques
- **Original top-500-embedded / top-25-rendered**: rejected because records ranked 501+ in every mode are silently unreachable from the explorer. The dashboard's tutorial text claims the explorer shows "Top 25" but does not warn that records below rank 500 are absent — this is a data-completeness bug masquerading as a performance optimization. The 611 KB JSON already contains the full corpus; the cap is artificial.
- **Vendored Tabulator**: rejected because it violates the self-contained requirement's spirit (120 KB of vendored code for a problem that ~60 lines of vanilla windowing solves), and because it imposes Tabulator's URL scheme on the deep-link convention (the existing `#record_id` hash would need a compatibility shim). The accessibility gain (full ARIA grid) is real but not worth the cost; the v1's `role="listbox"` + `role="option"` pattern is already screen-reader-navigable.

## Risks
- The embedded JSON grows from ~611 KB to an estimated ~800-900 KB (the per-record text is the dominant cost). The dashboard is loaded from `file://` so there is no network cost, but the `JSON.parse` time grows roughly linearly. A guardrail: if parse time exceeds 500 ms on a mid-range laptop, the embed should be split into a separate `<script type="application/json">` block per ranking mode and parsed lazily on first mode switch.
- The windowing `scroll` listener must be throttled (`requestAnimationFrame` or a 16 ms debounce) or it will jank on fast scroll. The existing `tools/audit_html_report_playwright.py` mobile-viewport overflow check must be extended to verify the windowed list does not collapse to zero height on a 360 px viewport.
- The `n`/`p` keyboard shortcuts currently rely on `currentRows[selected]` being a live array of all filtered rows. With windowing, `currentRows` is still the full filtered array (only the *rendered* subset is windowed), so the shortcut logic is unchanged — but the `renderList()` call must scroll the window to keep `selected` visible.
- The deep-link `applyHash()` (line 666) scans all three ranking modes for the target `record_id`. With the full pool embedded, this scan is over 5717 records × 3 modes = ~17 k comparisons, which is fast (<5 ms) but must not be moved inside the windowed render path.
- The waterfall's `bar()` template uses `width:${value*100}%` with no guard against `value > 1` or `value < 0`. A malformed score in the embedded data could overflow the bar. The template should clamp `value` to `[0, 1]` (it already does via `Math.max(0, Math.min(100, value*100))` at line 257, so this is safe — but the guard must survive the refactor).

## Red tests
1. **Full pool reachability**: for every `record_id` present in the embedded `report-data` JSON, applying `location.hash = '#' + record_id` and waiting 200 ms results in that record being the selected row in `#rankList` (the `aria-selected="true"` item's `data-record` matches). This is the silent-unreachability red test.
2. **Windowed DOM size**: with a 5717-record pool and a filter that matches all of them, the `#rankList` element has at most 40 child `<button class="rank">` elements (25 visible ± 5 buffer above and below) plus 2 spacer `<div aria-hidden="true">` elements. The total descendant node count of `#rankList` is <200 regardless of pool size.
3. **Keyboard scroll-into-view**: pressing `n` repeatedly (50 times) moves the selection from row 0 to row 49; at each step, the selected `<button>` is at least 50% visible inside `#rankList`'s scroll viewport (asserted via `getBoundingClientRect` intersection). This is the WCAG 2.4.11 red test for the windowed list.

## Prototype plan
Build an `explorer-prototype.html` with the full 5717-record embed and the windowed `renderList()`. Manually verify: (a) a deep link to a record ranked 600 in review-priority mode now resolves (it did not in v1); (b) fast scrolling through the full list does not jank (>55 fps via DevTools Performance); (c) the `n`/`p`/`/`/`1`/`2`/`3`/`Escape` shortcuts still work. Run the existing Playwright audit's explorer section; extend the rank-list focus test to verify the windowed buffer.

## Rollback plan
The change is three generator-side edits in `tools/generate_council_inferences_report.py` (and the adintel generator): (1) the embed loop (raise the 500-per-ranking cap), (2) the `renderList()` template (add windowing), (3) the `scroll` listener attachment. The previous templates are kept as commented-out blocks. If the embedded JSON grows too large (parse > 500 ms), the embed cap can be restored to 500-per-ranking independently of the windowing change — the two are separable. A full rollback is `git revert` of the generator commit plus regeneration.

## Freshness date
2026-08-04
