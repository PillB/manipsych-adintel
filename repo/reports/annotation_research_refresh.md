# Annotation research refresh and GUI implementation notes

Generated: 2026-07-09

## Sources rechecked

- SemEval-2023 Task 3, ACL Anthology: multilingual category/framing/persuasion-technique detection; paragraph-level taxonomy of 23 persuasion techniques; Spanish included in surprise languages.
- Azure Machine Learning data labeling documentation: project-specific instructions before tasks, work queue, number-key label selection, correction before submit, text NER workflow, and warning that ML prelabels can be wrong.
- Label Studio documentation: hotkeys, labeling guide, configurable workflows, imports/exports, and review-oriented annotation management.
- doccano documentation: simple text annotation project orientation for sequence labeling/classification/translation.
- LabelAId paper: just-in-time interventions can improve human labeling precision and domain knowledge without replacing human judgment.
- Computational persuasion survey: persuasion is context-dependent; AI can act as persuader, persuadee, or judge; model-as-judge outputs require caution.

## Design decisions encoded

1. The app opens with training by default and stores a primer hash in localStorage when completed.
2. Label suggestions stay hidden for a record until the current reviewer submits an independent human review.
3. The queue, annotation text, and controls are visible in one working view to reduce context switching.
4. Number-key label shortcuts mirror Azure/Label Studio-style fast labeling, while `/`, `n`, `p`, `s`, `Enter`, and `?` cover search, navigation, draft, submit, and help.
5. Span validation uses the immutable displayed text and stores exact selected text with zero-based, end-exclusive offsets.
6. Overlapping spans are allowed and rendered as atomic segments.
7. Promotion, image availability, platform, and raw archive metadata are displayed as context, not label evidence.
8. Drafts and submissions are local-only until exported as deterministic JSONL.
9. Undo/redo and negative-example controls are first-class because those are frequent annotation operations.
10. Mobile overflow, accessible control names, and first-run tutorial behavior are covered by Playwright audit.

## Generated artifacts

- Primer: `docs/ANNOTATOR_PRIMER.md`
- GUI generator: `tools/generate_annotation_gui.py`
- GUI: `annotation_app/index.html`
- GUI audit: `tools/audit_annotation_gui_playwright.py`
- Audit result: `reports/annotation_gui_playwright_audit.json`
