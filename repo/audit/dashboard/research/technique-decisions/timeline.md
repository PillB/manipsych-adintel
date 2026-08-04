# Technique Decision: Training/Test Iteration Timeline

## Research question
Which list structure preserves the v1 dashboard's vertical chronological scan (date → stage → metric tags) while (a) exposing the rows as an ordered list to assistive technology, (b) keeping keyboard focus visible and unobscured (WCAG 2.4.11 / 2.4.13), and (c) scaling gracefully if the iteration count grows from the current ~6 entries to several hundred?

## Current behavior
The v1 dashboard renders two parallel timelines inside `renderDiagnostics()` (lines 315-320 of `ad_manipulation_report.html`):
1. **Training/test iteration timeline** (`#iterationTimeline`) — data-driven from `data.iteration_timeline`. Each entry is emitted as `<div class="timeline-row"><b>date</b><div><b>stage</b><br><span class="small">note · records N · spans M</span></div><div><span class="tag blue">μF1 …</span><br><span class="tag amber">MF1 …</span></div></div>`. A CSS grid lays the three columns side by side.
2. **Error and review lifecycle** (`#errorTimeline`) — hardcoded as a JS array `known` of `[stage, note]` tuples inside `renderDiagnostics()` (line 319), then mapped to the same `<div class="timeline-row">` shape with a `fixed`/`tracked` status tag.

Neither timeline is a real list: the container `<div class="timeline">` has no `role="list"`, the rows are `<div>` not `<li>`, and there is no `aria-current` on the most-recent entry. The container is scrollable (`.ledger{max-height:34vh;overflow:auto}` is the closest match; `.timeline` shares the pattern), but there is no programmatic scroll-into-view on focus, so a keyboard user who tabs past the bottom of a long timeline can lose their place.

## Reference behavior
The unified dashboard reuses both timelines verbatim. The error-lifecycle `known` array is still hardcoded in the JS, which means adding a new known error requires editing the generator and regenerating — a maintainability smell, but not a regression. No new visual regression.

## Sources
- W3C, *Understanding SC 2.4.11: Focus Not Obscured (Minimum)* — https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html (the keyboard-focused row must remain at least partially visible inside the scroll container)
- W3C, *Understanding SC 2.4.13: Focus Appearance* — https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html (the focus indicator must meet a minimum size and contrast)
- W3C ARIA APG, *Table pattern* (for the `aria-sort` precedent of using native semantics over ARIA) — https://www.w3.org/WAI/ARIA/apg/patterns/table
- MDN, *WAI-ARIA Roles* (`role="list"` / `role="listitem"` — note: MDN recommends using native `<ol>`/`<ul>`/`<li>` instead) — https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Roles
- stackfull.dev, *Implementing virtual scroll for web from scratch, in less than 150 lines of code* (2025-04-24) — https://stackfull.dev/implementing-virtual-scroll-for-web-from-scratch-in-less-than-150-lines-of-code
- Sergi Mansilla, *Virtual list in vanilla JavaScript* — https://sergimansilla.com/blog/virtual-scrolling
- dev.to / Zeeshan Ali, *Frontend System Design: Virtualization & Handling Large Data Sets* (2026-03-15) — https://dev.to/zeeshanali0704/frontend-system-design-virtualization-handling-large-data-sets-29nf (the "below ~200 items the browser handles rendering efficiently; 200-5K needs simple pagination; 5K+ needs virtualization" rule of thumb)
- Density Labs, *Infinite Scroll with Intersection Observer* — https://densitylabs.io/blog/infinite-scroll-with-intersection-observer
- FrontendAtlas, *Infinite Scroll List Frontend System Design* (2026-07-27) — https://frontendatlas.com/system-design/infinite-scroll-list

## Comparable implementations
1. **Carbon Design System Timeline** (IBM) — https://carbondesignsystem.com/components/timeline/usage/ — license: Apache-2.0. Uses an `<ol class="cds--timeline">` with `<li>` items, each carrying `aria-current="date"` on the active step. Closest accessible-by-default reference for the visual pattern.
2. **GitHub commit history timeline** — https://github.com (web app, not a library). Uses a semantic `<ol>` of commits with keyboard-navigable rows and `aria-current` on the selected commit. Reference for the keyboard interaction model (j/k or arrow keys to move between rows, Enter to inspect).
3. **Sergi Mansilla's vanilla virtual list** — https://sergimansilla.com/blog/virtual-scrolling — license: public-domain blog post. A ~100-line vanilla-JS virtual list that renders only the visible window. Reference for the *technique* if the timeline ever needs to scale beyond ~200 entries (it does not today, but the adintel roadmap mentions "per-iteration audit log" growth).

## Candidate techniques
1. **Original (v1) `<div class="timeline-row">` fake list** — three-column CSS grid of `<div>`s inside a scrollable `<div class="timeline">`. No list semantics, no `aria-current`, no programmatic scroll-into-view.
2. **Minimal restore: native `<ol>` + `<li>` + `aria-current` on the latest entry** — convert the container to `<ol class="timeline">` and each row to `<li class="timeline-row" aria-current="step" id="iter-N">`. Add `tabindex="0"` to each `<li>` so it enters the tab order, and call `el.scrollIntoView({block:'nearest'})` on focus. No virtualization; the current ~6 entries render in full.
3. **Alternative: virtualized `<ol>` via IntersectionObserver** — keep the `<ol>`/`<li>` semantics, but render only the visible window plus a sentinel at each end; an `IntersectionObserver` appends/prepends rows as the user scrolls. Necessary only if the iteration count exceeds ~500; today it is 6.

## Decision matrix

| Criterion (weight) | Original | Minimal restore (`<ol>`) | Alternative (virtualized) |
|---|---|---|---|
| Original feature fidelity (25%) | 5/5 | 5/5 | 4/5 |
| Statistical/semantic accuracy (15%) | 4/5 | 5/5 | 5/5 |
| Accessibility (15%) | 2/5 | 5/5 | 4/5 |
| Task effectiveness (15%) | 4/5 | 5/5 | 4/5 |
| Performance at scale (10%) | 4/5 | 4/5 | 5/5 |
| Maintainability (10%) | 3/5 | 5/5 | 3/5 |
| Responsive (5%) | 4/5 | 4/5 | 4/5 |
| Self-contained (5%) | 5/5 | 5/5 | 5/5 |
| **Weighted total** | 76/100 | 92/100 | 82/100 |

## Chosen technique
**Minimal restore: native `<ol>` + `<li>` + `aria-current`.** Convert both timelines (iteration + error lifecycle) from `<div class="timeline-row">` to `<ol class="timeline"><li class="timeline-row" tabindex="0" aria-current="step">…</li></ol>`. The latest entry in each timeline gets `aria-current="step"` (the most recent iteration / the most recent tracked error). Each `<li>` is focusable; on `focus`, call `scrollIntoView({block:'nearest'})` so WCAG 2.4.11 is satisfied. The error-lifecycle `known` array is moved out of the JS into the embedded `report-data` JSON under a new `error_lifecycle` key, so adding an entry no longer requires editing the generator — this fixes the maintainability smell without changing the visual. Virtualization is explicitly **not** adopted today (the entry count is 6); the technique is documented as a known follow-up if the count exceeds 500.

## Rejected techniques
- **Original `<div>` fake list**: rejected because the rows are not exposed as list items to assistive technology. Screen-reader users cannot use list-navigation commands (e.g. VoiceOver's "list navigation" rotor) to jump between iterations, and the most-recent entry has no programmatic signal of recency.
- **Virtualized `<ol>` via IntersectionObserver**: rejected as premature. Virtualization adds ~80 lines of scroll-management code, a `ResizeObserver`, and a sentinel-rewriting routine that complicates the focus management (the focused `<li>` can be unmounted by the virtualizer if the scroll handler fires during a focus event). At 6 entries this complexity is unjustified. The technique is recorded as a documented follow-up with a clear trigger threshold (500 entries).

## Risks
- The error-lifecycle migration from JS-hardcoded array to JSON key changes the `report-data` schema. Any downstream consumer of that JSON (the audit Playwright scripts, the annotation app) must tolerate the new key; a schema-version bump in the JSON is advisable.
- Adding `tabindex="0"` to every `<li>` increases the tab-order length by N. For N=6 this is acceptable; for N>50 it becomes hostile. The follow-up virtualization plan must also include a roving-tabindex strategy.
- `aria-current="step"` is a relatively new value; older screen readers (NVDA < 2021) may not announce it. The fallback (`aria-label="most recent"` on the same element) covers this.
- The `scrollIntoView({block:'nearest'})` call on focus can fight with the page's sticky header if the timeline is near the top of the viewport; the call must use `block:'nearest'`, not `block:'center'`.

## Red tests
1. **List semantics**: the iteration timeline container is an `<ol>` element containing only `<li>` children; axe reports zero `list` / `listitem` role mismatches.
2. **Focus visibility (WCAG 2.4.11)**: when the last `<li>` in the iteration timeline receives focus via keyboard, at least 50% of its bounding box is inside the scroll container's viewport (asserted via `getBoundingClientRect` intersection).
3. **Recency signal**: the most recent iteration entry (the last `<li>` in DOM order, or the entry with the latest `date` field) carries `aria-current="step"`, and the error-lifecycle timeline's most-recently-tracked entry carries the same attribute.

## Prototype plan
Patch `renderDiagnostics()` in a throwaway `timeline-prototype.html` that loads the real `report-data` JSON plus the new `error_lifecycle` key. Verify with the keyboard: Tab into the timeline, arrow-down through the entries, confirm each focused entry is visible and announced as "step N of M" by a screen-reader spot check (VoiceOver). Run the existing `tools/audit_html_report_playwright.py` keyboard suite to confirm the n/p/1/2/3/Escape shortcuts still work and no new focus-trap is introduced.

## Rollback plan
The change is two generator-side template edits (the `<div class="timeline-row">` templates for both timelines) plus one JSON-schema addition (the `error_lifecycle` key). The previous templates are kept as commented-out blocks. The JSON key is purely additive, so a partial rollback (templates reverted, JSON key retained) is safe. A full rollback is `git revert` of the generator commit plus regeneration.

## Freshness date
2026-08-04
