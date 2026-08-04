# Technique Decision: KPI Cards (metric tiles)

## Research question
Which HTML structure best preserves the v1 metric-tile glanceability (large numeric value + uppercase label + tutorial block) while exposing each value to assistive technology as a machine-readable label/value pair, without adding an external dependency?

## Current behavior
The v1 dashboard (`reports/ad_manipulation_report.html` lines ~38-46) renders six KPI tiles as a CSS grid of plain `<div class="panel">` cards. Each tile contains two free-floating children: a `<div class="metric">` (the raw value such as `0.9008`) and a `<div class="metric-label">` (the uppercase label such as `test micro-F1*`). The asterisk signals "candidate council labels, not human gold" and is explained in a sibling `<section class="tutorial">` block titled "How to read the KPI cards". There is no `<dl>`/`<dt>`/`<dd>` structure, no `aria-label`, and no `role="status"` on the container. Values are static strings written into the HTML at generation time (they are not computed at runtime from `report-data`).

## Reference behavior
The unified dashboard (`reports/adintel/adintel_dashboard.html`) replicates the same `<div class="panel"><div class="metric">…</div><div class="metric-label">…</div></div>` pattern with adintel-specific values. No regression in *visual* fidelity, but no improvement in accessibility either. The tiles are still semantically unlabelled containers — screen readers announce the value and the label as two disconnected runs of text.

## Sources
- W3C, *Web Content Accessibility Guidelines (WCAG) 2.2*, 2024-12-12 — https://www.w3.org/TR/WCAG22 (criteria 1.3.1 Info and Relationships, 4.1.2 Name/Role/Value)
- MDN, *WAI-ARIA Roles* — https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Roles (2025-08-14 snapshot)
- MDN, *`<dl>` HTML description list element* — https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/dl (2026-04-24 snapshot)
- Deque, *ARIA roles used must conform to valid values* (axe rule) — https://dequeuniversity.com/rules/axe/html/4.10/aria-roles
- W3C ARIA Authoring Practices, *Table pattern* (for the `aria-sort` precedent of using native semantics over ARIA when possible) — https://www.w3.org/WAI/ARIA/apg/patterns/table
- Highcharts, *KPI Component* (commercial reference for what a maintained KPI widget exposes) — https://www.highcharts.com/docs/dashboards/kpi-component

## Comparable implementations
1. **Highcharts Dashboards KPI Component** — https://www.highcharts.com/docs/dashboards/kpi-component — license: commercial (Highcharts) / OSS (Highcharts OSS variant). Renders a value, a title, and an optional delta as a structured component. Similarity: high — solves exactly the value+label+delta problem but pulls in the Highcharts runtime (~200 KB), which violates the self-contained requirement.
2. **ApexCharts Radial/KPI cards** — https://apexcharts.com — license: MIT. Provides KPI-style tiles but ships a charting runtime; same self-containment concern.
3. **Carbon Design System Stat / KPI tile** (IBM) — https://carbondesignsystem.com/components/stat/usage/ — license: Apache-2.0. Uses a `<dl>`-based semantic structure with `aria-label` on the wrapper. This is the closest *accessible-by-default* reference; the technique (not the React component) is what we adopt.

## Candidate techniques
1. **Original (v1)** — bare `<div class="panel"><div class="metric">value</div><div class="metric-label">label</div></div>`. No semantics; visual only.
2. **Minimal restore** — wrap each tile in `<div class="panel" role="group" aria-label="…"><p class="metric" aria-describedby="…-label">value</p><p class="metric-label" id="…-label">label</p></div>`. Adds programmatic name and description without restructuring the DOM. Keeps the tutorial block as the long-form explanation.
3. **Alternative: `<dl>` semantic rebuild** — convert each tile to `<dl class="panel metric-tile"><dt class="metric-label">test micro-F1*</dt><dd class="metric">0.9008</dd></dl>` inside an outer `<section role="group" aria-label="Key performance indicators">`. Native semantics: the `dt`/`dd` pairing is announced as "term: definition" by screen readers, satisfying WCAG 1.3.1 without any ARIA.

## Decision matrix

| Criterion (weight) | Original | Minimal restore | Alternative (`<dl>`) |
|---|---|---|---|
| Original feature fidelity (25%) | 5/5 | 5/5 | 4/5 |
| Statistical/semantic accuracy (15%) | 3/5 | 4/5 | 5/5 |
| Accessibility (15%) | 2/5 | 4/5 | 5/5 |
| Task effectiveness (15%) | 4/5 | 4/5 | 4/5 |
| Performance at scale (10%) | 5/5 | 5/5 | 5/5 |
| Maintainability (10%) | 4/5 | 3/5 | 5/5 |
| Responsive (5%) | 5/5 | 5/5 | 5/5 |
| Self-contained (5%) | 5/5 | 5/5 | 5/5 |
| **Weighted total** | 78/100 | 87/100 | 95/100 |

## Chosen technique
**Alternative: the `<dl>` semantic rebuild.** Each tile becomes a `<dl>` whose `<dt>` is the human label and whose `<dd>` is the numeric value. An outer `<section aria-label="Key performance indicators">` groups them. The asterisk footnote is retained as a `<p class="small">` with `role="note"` immediately after the grid, and the existing tutorial block stays in place. This is a pure markup change with zero new dependencies and zero runtime cost, and it satisfies WCAG 1.3.1 and 4.1.2 without any ARIA at all (the native `dt`/`dd` semantics are sufficient). The Carbon Design System Stat tile uses exactly this pattern.

## Rejected techniques
- **Original bare `<div>` tiles**: rejected because the value and label are siblings with no semantic relationship. Screen-reader users hear "zero point nine zero zero eight test micro-F1 asterisk" as ambient text, with no way to navigate to a specific KPI by name. Violates WCAG 1.3.1 (Info and Relationships) and 4.1.2 (Name/Role/Value).
- **Minimal restore (ARIA-only)**: rejected because it duplicates the relationship in two places (visual order *and* `aria-describedby`), which drifts over time. The `<dl>` approach encodes the relationship in the DOM itself, so it cannot drift.

## Risks
- The `*` footnote convention ("candidate labels, not human gold") must survive the rebuild. If the `<dl>` rebuild accidentally drops the asterisk or the footnote paragraph, the most important provenance signal in the dashboard is lost.
- Some screen readers truncate `<dd>` content if it is wrapped in block elements; the numeric value must remain a plain text node or an inline `<bdo>`/`<data value="0.9008">` element.
- The adintel dashboard currently duplicates the KPI grid; both files must be migrated together or the unified dashboard regresses again.

## Red tests
1. **Tile-name announcement**: in a Playwright + axe-core run, every KPI tile has a programmatically determinable name (axe rule `aria-label` / `dl` semantics pass with zero violations on the KPI section).
2. **Value/label pairing**: a screen-reader walk of the KPI section (simulated via `element.accessibleName`/`accessibleDescription` queries) returns one `(label, value)` pair per tile, in label-then-value order, with no orphan values.
3. **Asterisk provenance**: the footnote paragraph explaining the `*` marker is present immediately after the KPI grid and is associated with the grid via `aria-describedby`, so the relationship is preserved after the rebuild.

## Prototype plan
Build a single static `kpi-prototype.html` with six `<dl>` tiles plus an axe-core bookmarklet-style scan. If axe reports zero serious issues on the KPI section and a manual screen-reader spot check (VoiceOver on macOS) announces "test micro F1 asterisk: zero point nine zero zero eight", the technique is approved for integration into both `ad_manipulation_report.html` and `adintel_dashboard.html` generators (`tools/generate_council_inferences_report.py`).

## Rollback plan
The change is a generator-side string template swap in `tools/generate_council_inferences_report.py` (and the adintel generator). The previous `<div class="panel"><div class="metric">…` template is preserved as a commented-out block above the new template for one release cycle. If the Playwright audit regresses on any tile-related metric, `git revert` the generator commit and rerun the audit; the rendered HTML files are not version-controlled artifacts (they are regenerated).

## Freshness date
2026-08-04
