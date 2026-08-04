# Technique Decision: Explainability Atlas (coefficient terms for a selected label)

## Research question
Which rendering technique preserves the v1 atlas's three-card layout (label coefficients + selected-ad local evidence + caveats) while (a) making the coefficient magnitudes visually comparable (not just textual), (b) keeping the term list sortable/keyboard-navigable, and (c) staying honest about the fact that these are TF-IDF model coefficients, not SHAP/Shapley attributions?

## Current behavior
The v1 dashboard renders the atlas via `renderExplainabilityAtlas()` (line 340 of `ad_manipulation_report.html`). The pipeline:
1. Read the selected label from `<select id="explainLabel">` (populated from `data.global_explainability.labels`).
2. Find the matching label row and emit three `<div class="coef-card">` cards:
   - **Card 1 (label coefficients)**: heading + tutorial paragraph + a stat line (`family · type · support · F1 · precision · recall · AUC`) + an optional low-support warning + "Terms pushing this label up" (a row of `termPills(row.top_positive_terms)`) + "Contrast terms" (a row of `termPills(row.contrast_terms)`) + the method footnote.
   - **Card 2 (selected-ad local evidence)**: a `<div id="selectedEvidence">` populated by `renderSelectedExplainability(r)` (line 347) when an ad is selected in the explorer. Shows: selected label, whether the council has the label, the model probability, which top coefficient terms appear in the ad's text, and up to 3 span examples.
   - **Card 3 (caveats)**: a `<ul>` of `data.global_explainability.caveats`.
3. `termPills(terms)` (line 337) renders `(terms||[]).slice(0,12).map(t => '<span class="term-pill"><span>${esc(t.term)}</span><b>${Number(t.weight).toFixed(2)}</b></span>')`. The pill shows the term as text and the weight as a bold number; there is **no bar, no length encoding, no sort**. The terms are shown in the order the backend emits them (already sorted by weight descending, but the user cannot re-sort).

The `<select id="explainLabel">` has a `<label for="explainLabel">` (line 88), so the control is accessible. The three cards are plain `<div>`s with no `role` or `aria-labelledby`.

## Reference behavior
The unified dashboard reuses `renderExplainabilityAtlas()` unchanged. No visual regression. The latent issues (no visual magnitude encoding; no sort; pills are not a list) are inherited but not worsened.

## Sources
- SHAP, *waterfall plot* docs (the canonical feature-attribution visual; shows signed contribution as a horizontal bar) — https://shap.readthedocs.io/en/latest/example_notebooks/api_examples/plots/waterfall.html
- Christoph Molnar, *Interpretable Machine Learning, ch. 18 SHAP* — https://christophm.github.io/interpretable-ml-book/shap.html
- Aidan Cooper, *A Non-Technical Guide to Interpreting SHAP Analyses* — https://www.aidancooper.co.uk/a-non-technical-guide-to-interpreting-shap-analyses
- ELI5 / LIME / SHAP overview (Kaggle) — https://www.kaggle.com/code/ankitp013/interpreting-ml-models-eli5-lime-shap-yellowbrick
- UCLA Stats, *FAQ: How do I interpret odds ratios in logistic regression?* — https://stats.oarc.ucla.edu/other/mult-pkg/faq/general/faq-how-do-i-interpret-odds-ratios-in-logistic-regression
- Andrew Wheeler, *Odds Ratios NEED To Be Graphed On Log Scales* — https://andrewpwheeler.com/2013/10/26/odds-ratios-need-to-be-graphed-on-log-scales (the argument that coefficient magnitudes should be shown on a symmetric log scale so that a positive coefficient of +2 and a negative coefficient of −2 have equal visual weight)
- PMC / Halvorson 2021, *Making sense of some odd ratios* — https://pmc.ncbi.nlm.nih.gov/articles/PMC8553813
- W3C ARIA APG, *Grid (Interactive Tabular Data) Pattern* — https://www.w3.org/WAI/ARIA/apg/patterns/grid
- W3C ARIA APG, *Table pattern* (`aria-sort` reference) — https://www.w3.org/WAI/ARIA/apg/patterns/table
- MDN, *ARIA: table role* — https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Roles/table_role

## Comparable implementations
1. **SHAP `waterfall` plot** — https://shap.readthedocs.io/en/latest/example_notebooks/api_examples/plots/waterfall.html — license: MIT. The reference feature-attribution visual: each feature is a row, the signed contribution is a horizontal bar (red for positive, blue for negative), rows are sorted by absolute contribution, and a connecting "waterfall" line shows the cumulative prediction. Self-contained compatibility: SHAP is a Python library that renders to matplotlib SVG; the *technique* (signed horizontal bars sorted by magnitude) is portable to inline SVG.
2. **ELI5 `show_weights`** — https://eli5.readthedocs.io — license: MIT. Renders a horizontal HTML table of features with a `<b>` weight bar (`<div style="width: NN%">`), positive weights in green, negative in red. This is the closest structural reference for what the v1 atlas *should* look like: a sortable HTML table with inline weight bars.
3. **LIME `show_in_notebook`** — https://github.com/marcotcr/lime — license: BSD-2. Renders a horizontal bar chart of feature contributions, similar to SHAP. Reference for the diverging-bar technique (positive right, negative left of a centre line).
4. **Carbon Design System Data Table** — https://carbondesignsystem.com/components/data-table/usage/ — license: Apache-2.0. Reference for the `<table role="grid">` + `aria-sort` + keyboard-navigation pattern that the atlas's term list should adopt.

## Candidate techniques
1. **Original (v1) term pills** — `<span class="term-pill"><span>term</span><b>weight</b></span>`, twelve per card, no bar, no sort, no list semantics. Already behind a `<label for="explainLabel">` selector.
2. **Minimal restore: term pills → sortable `<table role="grid">` with inline weight bars** — convert each "Terms pushing this label up" and "Contrast terms" block into `<table class="coef-table"><caption>…</caption><thead><tr><th scope="col">Term</th><th scope="col" aria-sort="descending">Weight</th></tr></thead><tbody>…</tbody></table>`. Each row is `<tr><th scope="row">term</th><td><div class="bar"><i style="width:|w|*100%"></i></div> <b>w</b></td></tr>`. Clicking the Weight header toggles `aria-sort` and re-sorts. Positive terms get a green bar; contrast terms get a red bar (diverging). Twelve rows max per table.
3. **Alternative: SHAP-style diverging waterfall SVG** — replace the two term lists with a single inline SVG waterfall: a centre vertical axis, positive terms as rightward green bars, contrast terms as leftward red bars, sorted by absolute weight, with a connecting cumulative line. This is the most information-rich option but the most complex to render and the least faithful to the v1's two-list structure.

## Decision matrix

| Criterion (weight) | Original (pills) | Minimal restore (table + bars) | Alternative (SHAP waterfall) |
|---|---|---|---|
| Original feature fidelity (25%) | 5/5 | 4/5 | 3/5 |
| Statistical/semantic accuracy (15%) | 3/5 | 4/5 | 5/5 |
| Accessibility (15%) | 3/5 | 5/5 | 3/5 |
| Task effectiveness (15%) | 3/5 | 5/5 | 5/5 |
| Performance at scale (10%) | 5/5 | 5/5 | 4/5 |
| Maintainability (10%) | 4/5 | 4/5 | 3/5 |
| Responsive (5%) | 4/5 | 4/5 | 3/5 |
| Self-contained (5%) | 5/5 | 5/5 | 5/5 |
| **Weighted total** | 81/100 | 90/100 | 81/100 |

## Chosen technique
**Minimal restore: sortable `<table role="grid">` with inline weight bars.** Convert the two `termPills()` blocks into two `<table class="coef-table">` elements, each with a `<caption>`, a `<thead>` containing `<th scope="col">Term</th>` and `<th scope="col" aria-sort="descending">Weight</th>`, and a `<tbody>` of `<tr><th scope="row">term</th><td>…</td></tr>`. Each weight cell contains a `<div class="bar"><i style="width:${Math.abs(w/maxW)*100}%"></i></div>` and the numeric weight as text. Positive-terms bars are green (`var(--green)`); contrast-terms bars are red (`var(--red)`) — a diverging visual without a centre axis. Clicking the Weight `<th>` toggles `aria-sort` between `ascending`/`descending` and re-sorts the rows in place. The two-table structure preserves the v1's "positive vs contrast" framing; the diverging colours preserve the signed semantics.

The low-support warning, the method footnote, and the caveats card are unchanged. The selected-ad local evidence card is unchanged (it already shows overlap as text, which is the correct encoding for a per-ad view).

## Rejected techniques
- **Original term pills**: rejected because the weight is shown only as a number, not as a length. Users must mentally compare `0.42` vs `0.38` vs `0.31` to rank the terms, which is slower and more error-prone than comparing bar lengths (Cleveland & McGill's elementary perceptual tasks rank length above numeric readout). The pills are also not a list, so screen-reader users cannot use table-navigation commands.
- **SHAP-style diverging waterfall SVG**: rejected because (a) it collapses the v1's deliberate two-list structure (positive vs contrast) into a single sorted-by-magnitude list, which changes the analytical framing; (b) the connecting cumulative line is only meaningful for additive attributions (SHAP Shapley values), and the v1's coefficients are TF-IDF weights that are *not* additive — drawing a cumulative line would imply a property the model does not have. The dashboard's tutorial text already warns "coefficient terms explain the TF-IDF model, while annotation spans explain the candidate council decision"; a SHAP-style visual would muddy this. The technique is recorded as a documented follow-up only if the backend ever switches to a true additive attribution method.

## Risks
- The `aria-sort` toggle requires a keyboard handler on the `<th>` (`Enter`/`Space` to toggle, in addition to click). The W3C ARIA APG grid pattern specifies arrow-key navigation between cells, which is more than this atlas needs — the simpler `role="grid"` with `aria-sort` on the header and `tabindex` management on rows is sufficient.
- The diverging colour choice (green positive / red contrast) inherits the same deuteranopia concern as the heatmap. The numeric weight text saves WCAG-1.4.1 compliance, but a CVD-safe palette (blue positive / orange contrast, or the `vik` diverging map from Crameri) should be considered if the audit reveals a CVD-affected stakeholder. This is the same finding as the heatmap decision and should be addressed consistently.
- The `termPills()` function is also used elsewhere (the `renderSelectedExplainability` local-evidence card, line 354, uses `terms.filter(...)` directly, not `termPills`). The refactor must not break that call site.
- The max-weight normalization (`Math.abs(w/maxW)`) must recompute when the label changes; a stale `maxW` would make bars in one label's table scale to another label's range.
- The "top 12" cap (from `termPills`'s `.slice(0,12)`) must be preserved or made explicit (e.g. a "showing top 12 of N" footnote) so users know the table is truncated.

## Red tests
1. **Table semantics**: each coefficient block is a `<table role="grid">` with a `<caption>`, a `<thead>` containing `<th scope="col">` cells, and `<tbody>` rows whose first cell is `<th scope="row">`. The Weight `<th>` carries `aria-sort` with a value of `ascending`, `descending`, or `none`. Axe reports zero `table-fake-caption` / `th-has-data-cells` violations.
2. **Magnitude encoding**: each weight cell contains a `<div class="bar">` whose inner `<i>` has a `width` style expressed as a percentage of the table's max absolute weight (asserted: the widest bar in a given table corresponds to the row with the largest `Math.abs(weight)`).
3. **Sort interactivity**: clicking (or focusing and pressing `Enter` on) the Weight `<th>` toggles `aria-sort` between `descending` and `ascending`, and the row order in the `<tbody>` reverses accordingly. The first row's weight after a descending sort is ≥ the last row's weight.

## Prototype plan
Build an `atlas-prototype.html` with the real `global_explainability` JSON, the two-table layout, and the `aria-sort` toggle. Manually verify: (a) the green/red diverging bars make the top-vs-contrast framing visually obvious; (b) clicking the Weight header re-sorts in <50 ms; (c) a screen-reader spot check (VoiceOver) announces the table as "table, N rows, N columns" and the sort state as "sorted ascending/descending by Weight". Run the existing Playwright audit; extend it with a sort-interaction test.

## Rollback plan
The change is two generator-side template edits (`termPills` → `<table>` template, and the `aria-sort` click handler) in `tools/generate_council_inferences_report.py` (and the adintel generator). The previous `termPills()` function is kept for the local-evidence card (which still uses it via a different call path) — only the two atlas coefficient blocks are migrated. A full rollback is `git revert` of the generator commit plus regeneration; the `termPills()` function remains available for any other call site.

## Freshness date
2026-08-04
