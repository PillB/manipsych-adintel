# Technique Decision: Per-label Metric Heatmap

## Research question
Which colour-mapping function and which HTML structure preserve the v1 dashboard's per-label F1/AUC/accuracy/support overview while (a) being perceptually uniform and colour-vision-deficiency friendly, (b) exposing the data as a real table to assistive technology, and (c) keeping the inline-SVG/inline-CSS self-contained constraint?

## Current behavior
The v1 dashboard renders the heatmap via `renderDiagnostics()` (line 318 of `ad_manipulation_report.html`). It takes the top 20 labels by support from `modelReport.metrics.test.per_label`, then emits a sequence of `<div class="heat-row">` elements (a CSS-grid fake table, not a real `<table>`). Each row has five cells: the label name, three `<span class="heat-cell" style="background:${heatColor(value)}">value</span>` cells for F1, AUC, and accuracy, and a bold support count. The `heatColor(value)` function (line 308) maps a 0-1 value to `hsl(${20 + v*115} 48% ${88 - v*34}%)` — an amber-to-green hue ramp (hue 20° → 135°) with lightness decreasing from 88% to 54%. Missing values (`null`/`undefined`/`NaN`) are coloured `#eee6d7` (a flat cream). There is no legend, no axis, and no `<table>`/`<thead>`/`<th>` structure. The cell text is the raw numeric value (e.g. `0.88`), so colour is *not* the sole encoding — WCAG 1.4.1 is satisfied by accident.

## Reference behavior
The unified dashboard reuses `heatColor` and the same `<div class="heat-row">` structure. No visual regression, but the same two latent issues are inherited: (1) the amber-to-green HSL ramp is **not perceptually uniform** and is **not safe for deuteranopia/protanopia** (red-green colour vision deficiency affects ~8% of men), because the hue passes through the exact region of the spectrum those viewers collapse; (2) the heatmap is a fake table built from `<div>`s, so screen-reader users cannot use table-navigation commands to jump label-by-label or metric-by-metric.

## Sources
- W3C, *Understanding Success Criterion 1.4.1: Use of Color* — https://www.w3.org/WAI/WCAG21/Understanding/use-of-color.html
- Fabio Crameri, *Scientific colour maps* — https://www.fabiocrameri.ch/colourmaps (perceptually uniform, CVD-friendly, citable)
- s-Ink, *Scientific colour maps overview* — https://s-ink.org/scientific-colour-maps
- D3, *d3-scale-chromatic* — https://d3js.org/d3-scale-chromatic (Brewer-derived sequential + diverging schemes; reference for the `interpolateViridis` family)
- Smith & van der Walt, *viridis colour maps* (R vignette) — https://cran.r-project.org/web/packages/viridis/vignettes/intro-to-viridis.html (the canonical argument for perceptually uniform, CVD-friendly, grayscale-safe defaults)
- HoloViz, *colorcet continuous colormaps* — https://colorcet.holoviz.org/user_guide/Continuous.html (notes that diverging maps have discontinuities around the central value — relevant because F1 is bounded 0-1 but centred at no natural midpoint)
- Square Engineering, *Accessible Colors for Data Visualization* — https://developer.squareup.com/blog/accessible-colors-for-data-visualization
- Minnesota IT, *Data visualization accessibility: Focus on color* (2025-12-17) — https://mn.gov/mnit/about-mnit/accessibility/news/?id=38-716215
- MDN, *ARIA: table role* — https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Roles/table_role (the guidance is: prefer native `<table>` over `role="table"`)
- W3C ARIA APG, *Table pattern* (the `aria-sort` precedent for sortable columns) — https://www.w3.org/WAI/ARIA/apg/patterns/table

## Comparable implementations
1. **D3 `d3-scale-chromatic` `interpolateViridis` / `interpolateCividis`** — https://d3js.org/d3-scale-chromatic — license: ISC. The de-facto standard perceptually-uniform, CVD-friendly sequential ramp. `interpolateCividis` is specifically designed for viewers with deuteranopia. Self-contained compatibility: vendoring the colour function (≈2 KB) is cheap, but vendoring all of `d3-scale-chromatic` is unnecessary.
2. **Crameri Scientific Colour Maps (`batlow`, `vik`, `roma`)** — https://www.fabiocrameri.ch/colourmaps — license: CC-BY 4.0 / MIT (the palette data). Perceptually uniform, CVD-friendly, and grayscale-safe. The `vik` diverging map is the recommended choice for signed deviations from a midpoint. Vendoring a 256-stop lookup table is ~4 KB.
3. **Carbon Design System Data Table** (IBM) — https://carbondesignsystem.com/components/data-table/usage/ — license: Apache-2.0. Uses a native `<table>` with `<th scope="col">`/`<th scope="row">`, conditional cell colouring, and `aria-sort` on sortable headers. This is the structural reference for the `<table>` rebuild (the colour ramp is independent).

## Candidate techniques
1. **Original (v1) amber-to-green HSL on a `<div>` fake-table** — `heatColor(v) = hsl(20+v*115, 48%, 88-v*34%)`. Already WCAG-1.4.1-safe by accident (the numeric value is always shown). Not CVD-safe; not a real table.
2. **Minimal restore: swap the colour ramp, keep the fake table** — replace `heatColor` with a vendored 256-stop `viridis` or `cividis` lookup table (a ~2 KB JS array literal). The `<div class="heat-row">` structure stays. Fixes the CVD issue but leaves the screen-reader table-navigation gap.
3. **Alternative: native `<table>` + vendored `viridis` ramp + `<caption>` + `aria-label` per cell** — rebuild as `<table class="heat"><caption>Per-label test metrics, top 20 by support</caption><thead>…</thead><tbody>…</tbody></table>`. Each cell is `<td style="background:viridis(f1)" data-label="F1">0.88</td>`. A legend row explains the colour ramp. The `heatColor` function is replaced with the vendored lookup table.

## Decision matrix

| Criterion (weight) | Original | Minimal restore (ramp only) | Alternative (table + viridis) |
|---|---|---|---|
| Original feature fidelity (25%) | 5/5 | 5/5 | 4/5 |
| Statistical/semantic accuracy (15%) | 2/5 | 5/5 | 5/5 |
| Accessibility (15%) | 2/5 | 3/5 | 5/5 |
| Task effectiveness (15%) | 4/5 | 4/5 | 5/5 |
| Performance at scale (10%) | 5/5 | 5/5 | 5/5 |
| Maintainability (10%) | 4/5 | 4/5 | 4/5 |
| Responsive (5%) | 4/5 | 4/5 | 4/5 |
| Self-contained (5%) | 5/5 | 5/5 | 5/5 |
| **Weighted total** | 73/100 | 88/100 | 95/100 |

## Chosen technique
**Alternative: native `<table>` + vendored `viridis` (or `cividis`) lookup table.** The 256-stop `viridis` colormap is inlined as a JS array literal of hex strings (≈4 KB) inside the generator; the heatmap is rebuilt as a real `<table>` with `<caption>`, `<thead>` with `<th scope="col">`, `<tbody>` with `<th scope="row">` for the label column, and `<td>` cells whose `background` is `viridisLookupTable[Math.round(value*255)]`. The numeric value remains the cell's text content (preserving the v1's accidental WCAG-1.4.1 compliance). A small legend row below the table shows the 0 → 1 ramp with tick labels. `cividis` is preferred over `viridis` if the audit reveals any deuteranopia tester in the stakeholder group; otherwise `viridis` is the safer default (broader familiarity, identical perceptual properties).

## Rejected techniques
- **Original amber-to-green HSL ramp**: rejected on two counts. (1) Statistical/semantic: the ramp is not perceptually uniform, so a 0.50 → 0.55 jump looks visually smaller than a 0.85 → 0.90 jump even though both are 0.05. (2) Accessibility: the hue path passes through the red-green region that deuteranopes and protanopes collapse to a single yellow, so the F1 ranking by colour is unreliable for ~8% of male viewers. The numeric text saves WCAG-1.4.1 compliance but does not save *glanceability*.
- **Minimal restore (ramp only, keep `<div>` fake table)**: rejected because it leaves the heatmap inaccessible to screen-reader table navigation. JAWS, NVDA, and VoiceOver all have dedicated table-navigation keystrokes (Ctrl+Alt+Arrow) that work on real `<table>` elements but not on `<div class="heat-row">`. The marginal cost of the table rebuild (one generator-side template swap) is far smaller than the marginal accessibility gain.

## Risks
- The `viridis` lookup table must be generated from the canonical 256-stop reference (matplotlib's `viridis` or the d3 `interpolateViridis` source). A hand-typed subset will not be perceptually uniform.
- The `<table>` rebuild changes the CSS selector surface (`.heat-row` → `tr`, `.heat-cell` → `td`). Any existing CSS that targets `.heat-cell` for print or responsive overrides must be updated in lockstep.
- The "empty AUC means no positive/negative support" convention (the v1 caveat text) must be preserved: cells with `null`/`undefined` AUC must render as `n/a` on the cream background, not as a viridis-mapped colour.
- The `slice(0,20)` cap on visible labels is a deliberate information-density choice; the rebuild must not silently expand or shrink it.

## Red tests
1. **Native table semantics**: the heatmap container is a `<table>` element with a `<caption>`, a `<thead>` containing `<th scope="col">` cells for F1/AUC/Accuracy/Support, and `<tbody>` rows whose first cell is `<th scope="row">`. Axe reports zero `table-fake-caption` / `td-headers-attr` violations.
2. **CVD-safe colour ramp**: every cell's `background` colour, when converted to sRGB and run through a deuteranopia-simulation matrix (e.g. Machado 2009), retains a perceptual-lightness ordering that matches the numeric value's ordering. Equivalently: for any two cells with values `v1 < v2`, the simulated-lightness of cell 1 is ≤ that of cell 2.
3. **Missing-value preservation**: a label whose AUC is `null` in the source JSON renders a cell containing the literal text `n/a` on the cream `#eee6d7` background, *not* a viridis-mapped colour.

## Prototype plan
Generate a `heatmap-prototype.html` with the vendored `viridis` array literal and a `<table>` of the top 20 labels from the real `report-data` JSON. Run a CVD simulation (the `colorblind` Python package or the online Coblis simulator) on a screenshot of both the v1 ramp and the viridis ramp side by side. If the viridis ramp retains its ordering under deuteranopia and the v1 ramp does not, the technique is approved.

## Rollback plan
The change is two generator-side edits: (1) the `heatColor` function template and (2) the `<div class="heat-row">` template in `renderDiagnostics()`. Both are string templates in `tools/generate_council_inferences_report.py` (and the adintel generator). The previous templates are kept as commented-out blocks for one release cycle. `git revert` the generator commit and rerun the generator to restore the v1 heatmap exactly.

## Freshness date
2026-08-04
