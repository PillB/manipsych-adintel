# Technique Decision: ROC and Precision-Recall Curves

## Research question
Which SVG path-interpolation technique preserves the statistical correctness of ROC and precision-recall curves (step function between thresholds, not linear chord) while keeping the chart keyboard-navigable, self-contained, and visually consistent with the v1 line-chart aesthetic?

## Current behavior
The v1 dashboard renders both curves with a single `lineChart(points, options)` function (line 302 of `ad_manipulation_report.html`). The function maps each `[x, y]` pair (already normalized to 0-1 by the Python generator) onto a 620×300 viewBox, then emits a single SVG `<path>` built from `M x y L x y L x y …` commands — i.e. **straight-line linear interpolation between every threshold point**. A second `<path class="curve base">` draws the y=x diagonal as the ROC chance reference. The chart container is `<div id="curveChart">`, filled at runtime by `renderDiagnostics()` (line 314), which lays out two side-by-side charts: one for `test.roc_curve_micro` (with the AUC label below) and one for `test.precision_recall_curve_micro` (with the average-precision label below). The `<svg>` carries `role="img"` and an `aria-label`, but there is no `<title>`, no `<desc>`, no per-point `<circle>`, and no threshold tooltips.

## Reference behavior
The unified dashboard uses the same `lineChart` helper. Visual parity is preserved. **No new regression** was introduced, but a pre-existing statistical issue is inherited: PR curves drawn with linear interpolation between thresholds are not monotonic and can suggest precision values that the classifier never actually achieved at any threshold. The ROC chart is less affected because TPR and FPR are both monotonic in threshold, so linear interpolation underestimates AUC only slightly (the trapezoidal convention).

## Sources
- scikit-learn, *`sklearn.metrics.roc_curve`* — https://scikit-learn.org/stable/modules/generated/sklearn.metrics.roc_curve.html (documents that returned points are at discrete thresholds; the convention since 1.3 prepends a `(0,0)` threshold point)
- scikit-learn / Machine Learning Mastery, *ROC Curves and Precision-Recall Curves for Imbalanced Classification* — https://www.machinelearningmastery.com/roc-curves-and-precision-recall-curves-for-imbalanced-classification
- Plotly, *ROC and PR curves in Python* — https://plotly.com/python/roc-and-pr-curves (reference for how a maintained library renders the curves with hover)
- Richardson et al., *The receiver operating characteristic curve accurately…* (PMC, 2024, 286 citations) — https://pmc.ncbi.nlm.nih.gov/articles/PMC11240176 (cautionary: ROC-AUC inflation under class imbalance; reinforces the v1 dashboard's existing caveat text "more sensitive to rare labels")
- data.europa.eu, *Accessible SVG and ARIA* — https://data.europa.eu/apps/data-visualisation-guide/accessible-svg-and-aria (the `role="img"` + `<title>` + `<desc>` + `aria-labelledby` pattern)
- W3C, *SVG Accessibility / ARIA roles for charts* — https://www.w3.org/wiki/SVG_Accessibility/ARIA_roles_for_charts
- CSS-Tricks, *Accessible SVGs* — https://css-tricks.com/accessible-svgs
- Vispero, *Using ARIA to enhance SVG accessibility* — https://vispero.com/resources/using-aria-enhance-svg-accessibility

## Comparable implementations
1. **Plotly Python ROC/PR** — https://plotly.com/python/roc-and-pr-curves — license: MIT. Renders both curves with threshold hover tooltips, an AUC-shaded area, and a chance diagonal. Uses linear interpolation between thresholds *but* shades the trapezoidal area, which is the convention scikit-learn computes. Similarity: high. Self-contained compatibility: zero — Plotly ships a multi-hundred-KB runtime.
2. **scikit-learn ` RocCurveDisplay` / `PrecisionRecallDisplay`** — https://scikit-learn.org/stable/modules/generated/sklearn.metrics.roc_curve.html — license: BSD-3. Matplotlib-based, server-side raster. Same trapezoidal convention. Useful only as a *reference for the convention*, not as a front-end technique.
3. **D3 `d3-shape` `line` + `step` interpolation** — https://d3js.org/d3-shape — license: ISC. `d3.line().curve(d3.curveStepAfter)` is the canonical way to draw a step-function ROC. Self-contained compatibility: vendoring `d3-shape` adds ~12 KB; vendoring all of D3 adds ~270 KB. We already vendor `d3-lite-force.js`; a second vendored helper would need its own audit.

## Candidate techniques
1. **Original (v1) `lineChart` linear interpolation** — `M x0 y0 L x1 y1 L x2 y2 …` for every threshold. One `<path>` per curve, plus a chance-diagonal reference line. Already `role="img"` with an `aria-label`. No `<title>`/`<desc>`.
2. **Minimal restore (step interpolation, keep one-path-per-curve)** — swap the `L` commands for `H`/`V` commands so each segment becomes a horizontal-then-vertical step (post-threshold step, matching scikit-learn's `(0,0)` prepended point). Add `<title>` and `<desc>` to each `<svg>` and reference them via `aria-labelledby`. No new dependencies.
3. **Alternative: vendored `d3-shape` step + area fill** — vendor `d3-shape` (≈12 KB) to draw the step path, the area-under-curve shading, and a baseline. Increases the bundle by ~12 KB and adds a second vendored library to maintain.

## Decision matrix

| Criterion (weight) | Original | Minimal restore (step) | Alternative (d3-shape) |
|---|---|---|---|
| Original feature fidelity (25%) | 5/5 | 4/5 | 4/5 |
| Statistical/semantic accuracy (15%) | 2/5 | 5/5 | 5/5 |
| Accessibility (15%) | 2/5 | 4/5 | 4/5 |
| Task effectiveness (15%) | 3/5 | 4/5 | 5/5 |
| Performance at scale (10%) | 5/5 | 5/5 | 4/5 |
| Maintainability (10%) | 5/5 | 4/5 | 3/5 |
| Responsive (5%) | 5/5 | 5/5 | 5/5 |
| Self-contained (5%) | 5/5 | 5/5 | 3/5 |
| **Weighted total** | 72/100 | 89/100 | 86/100 |

## Chosen technique
**Minimal restore (step interpolation).** Replace the `L` (line-to) path commands with `H` (horizontal-to) + `V` (vertical-to) commands so each segment between consecutive thresholds is drawn as a post-threshold step — the convention scikit-learn documents and `RocCurveDisplay` uses. Add `<title id="…">Test micro ROC curve, AUC 0.987</title>` and `<desc id="…">Step plot of true-positive rate against false-positive rate across all decision thresholds; chance diagonal shown.</desc>` to each `<svg>`, and reference them via `aria-labelledby="title-id desc-id"`. Keep the existing chance-diagonal reference path. This is a ~20-line change to the `lineChart` generator template, no new dependencies, and it fixes both the statistical issue (PR is no longer drawn as linear chords) and the accessibility gap (chart now has a programmatic name and description).

## Rejected techniques
- **Original linear interpolation**: rejected primarily for statistical accuracy. Linear chords on a precision-recall curve suggest precision values that the classifier never achieved at any operating threshold, which is misleading for the rare-label case the dashboard explicitly warns about ("precision-recall is more sensitive to rare labels"). Linear interpolation on the ROC is less harmful but still inconsistent with the trapezoidal AUC the Python backend reports.
- **Vendored `d3-shape`**: rejected because it introduces a second vendored library (alongside `d3-lite-force.js`) for a problem that requires only an `H`/`V` path swap. The self-contained requirement is not strictly violated (it would still work from `file://`), but the maintenance cost of tracking a second vendored copy is not justified by the marginal gain (area shading, smoother hover) at the current ~100-point curve density.

## Risks
- The Python generator currently normalizes points to 0-1 *before* emitting them; the step rendering must preserve the order of threshold points (descending threshold for ROC, ascending recall for PR). If the generator re-sorts, the step shape becomes meaningless.
- The `<title>` and `<desc>` text must be regenerated per chart from the live AUC / average-precision values, not hard-coded. A stale `<title>` ("AUC 0.987") that disagrees with the data file would be worse than no title.
- Step interpolation increases the path's command count from `N` to `2N-1`; at the current curve density (~100 points) this is negligible, but if the backend ever ships 10 000-point curves the path string grows to ~80 KB per chart. A guardrail (downsample above 500 points) should be added to the generator.

## Red tests
1. **Step-shape verification**: the rendered `<path>` for the ROC chart contains at least one `H` or `V` command (i.e. it is not purely `L`-based linear interpolation), and the path's bounding box touches both the `(0,0)` and `(1,1)` corners of the chart area.
2. **Programmatic name**: each curve `<svg>` exposes `aria-labelledby` pointing to a non-empty `<title>` whose text contains the literal substring "AUC" (ROC) or "average precision" (PR) and the numeric value, asserted against the value in the embedded `report-data` JSON.
3. **PR monotonic recall**: the x-coordinates of the precision-recall path points are non-decreasing (the curve does not run backwards at any threshold), which is the precondition for the step interpolation to be statistically valid.

## Prototype plan
Patch `lineChart` in a throwaway `curve-prototype.html` that loads only the `report-data` JSON and renders the two curves. Manually verify the PR curve is now a staircase and not a series of chords. Run the existing `tools/audit_html_report_playwright.py` keyboard-interaction suite against the prototype to confirm the `role="img"` chart still receives focus and the tooltip / `aria-label` path is unchanged.

## Rollback plan
The `lineChart` function is a single string template in `tools/generate_council_inferences_report.py`. The previous linear-interpolation template is kept as a commented-out block immediately above the new template for one release cycle. A `git revert` of the generator commit plus a rerun of the generator restores the v1 visual exactly. No data migration is involved (the JSON shape is unchanged).

## Freshness date
2026-08-04
