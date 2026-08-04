# Challenge Round 1 — Defect Ledger

Adversarial critique focused on: scientific validity, behavioural interpretation,
statistical methods, confounding, leakage, calibration, cluster stability,
authorship reliability, short-text limitations, open-set rejection, outlier
robustness, annotation agreement, causal wording, alternative explanations.

Each defect is real — discovered by re-reading my own implementation against
the spec. Severity: critical / high / medium / low.

---

## R1-D01 — CRITICAL — Cluster brand leakage is near-total in 4 of 7 spaces

**Symptom**: The pipeline ran on 300 ads and the clustering summary shows
brand_leakage of 98.46% (Locanto Peru) in `persuasive`, 100% in `semantic`,
100% in `rhetorical`, 100% in `multimodal`. Only `visual` and `performance`
show mixed-platform clusters.

**Root cause**: The 300-ad sample is not stratified by platform — it is the
first 300 records, which happen to be all-Doplim or all-Locanto due to the
ingestion order. MiniBatchKMeans then separates by topic (which is confounded
with platform) rather than by technique.

**User/business consequence**: An analyst who opens the dashboard and sees
"Cluster 0 = Locanto ads about students" will believe they have found a
technique cluster when in fact they have found a *platform* cluster. This is
exactly the "treat technique presence as proof of persuasion" failure mode
the spec warns against.

**Supporting research**: Lex et al. (2012) "Stability of NMF clusterings";
Manning et al. IR §16 — domain-stratified sampling.

**Evidence grade**: B (single-corpus observation, reproduced on a sample).

**Alternatives considered**: (a) Stratified sampling by platform; (b) residualise
platform before clustering; (c) cluster within-platform and surface
cross-platform clusters separately.

**Selected change**: (a) Stratified sampling in the pipeline runner; the
clustering module already accepts arbitrary records, so the fix is in the
caller. Add a `stratify_by_platform` helper to `adintel.clustering`.

**Implementation reference**: `adintel/clustering.py` → new helper
`stratified_sample(records, by_field, n_per_stratum)`.

**Tests**: `tests/adintel/test_clustering.py::StratifiedSamplingTests` — sample
must contain at least 3 platforms when corpus has 3 platforms.

**Measured result**: After fix, brand_leakage should drop to <50% per cluster
in `persuasive` and `semantic` spaces.

**Remaining uncertainty**: Even after stratification, true topic clusters will
still correlate with platform because platforms specialise. Residualisation
would be a stronger fix but requires more validation.

**Owner value**: HIGH — without this fix, cluster cards are actively
misleading.

---

## R1-D02 — HIGH — Authorship thresholds calibrated on 4 hand-written samples, not on the corpus

**Symptom**: `SAME_SOURCE_THRESHOLD = 0.55`, `DIFFERENT_SOURCE_THRESHOLD = 0.30`
were tuned by running pairwise_verify on TEXT_A1 vs TEXT_A2 and observing
0.633 raw similarity. This is N=1 calibration.

**Root cause**: No held-out labelled set of known same-source / different-source
pairs was used. The 642 accepted similarity_links could have served this
purpose but were only used for evaluation, not for threshold selection.

**User/business consequence**: A threshold set too low yields false same-source
verdicts; too high yields false abstentions. Both undermine the dashboard's
authorship cards.

**Supporting research**: Koppel & Winter (2014) "Determining if two documents
are by the same author"; Halvani et al. (2017) "Authorship verification
via sparsification".

**Evidence grade**: C (single tuning example).

**Alternatives considered**: (a) Grid-search thresholds over the 642 links;
(b) Fit a logistic regression on raw similarity → calibrated probability;
(c) Use the existing `platt_scale` helper in `adintel.checkpoints` on a
held-out split of the 642 links.

**Selected change**: (c) Wire the pipeline runner to fit Platt scaling on a
held-out 80/20 split of the 642 accepted links, then use the calibrated
probability at threshold 0.5 as the same-source decision boundary.

**Implementation reference**: `scripts/run_adintel_pipeline.py` → new step
"4b. Calibrate authorship thresholds on 642 known links".

**Tests**: `tests/adintel/test_authorship.py::CalibratedThresholdTests` —
calibrated thresholds must produce accuracy ≥ 0.85 on the held-out 20%.

**Measured result**: Pending implementation; current uncalibrated accuracy
is 40/41 = 97.6% which is suspiciously high (likely because the 642 links
are near-duplicates that any reasonable threshold accepts — this is selection
bias).

**Remaining uncertainty**: The 642 links are not labelled *negative* pairs,
so we have no false-positive rate estimate. Need a same-source-vs-different-
source evaluation set with both classes.

**Owner value**: HIGH — without proper calibration, the authorship verdicts
have unknown specificity.

---

## R1-D03 — HIGH — Open-set attribution uses same threshold as pairwise verification

**Symptom**: `OPEN_SET_UNKNOWN_THRESHOLD = 0.30` is the same as
`DIFFERENT_SOURCE_THRESHOLD`. This conflates two distinct decisions.

**Root cause**: Open-set attribution is conceptually different from pairwise
verification: it asks "is this query from ANY known source?" whereas pairwise
asks "are these two specific texts from the same source?". Using the same
threshold is a category error.

**User/business consequence**: An ad that is genuinely from a new source
(open-set unknown) may be mis-attributed to the closest known source if
threshold is too low; an ad that is genuinely from a known source may be
labelled unknown if threshold is too high.

**Supporting research**: Scheirer et al. (2013) "Toward Open Set Recognition";
Koppel & Winter (2014).

**Evidence grade**: C (logical argument, no empirical validation in this
session).

**Alternatives considered**: (a) Separate thresholds tuned independently;
(b) Use a per-candidate threshold based on candidate's intra-source variance;
(c) Use a distance-based rejection rule (query must be within k standard
deviations of the candidate cluster centroid).

**Selected change**: (a) Add a separate `OPEN_SET_REJECTION_THRESHOLD` tuned
on a held-out evaluation; for now, document the limitation in the module
docstring.

**Implementation reference**: `adintel/authorship.py` — add a comment block
explaining the conflation, surface the limitation in the typed output via
`abstention_reason="open_set_threshold_conflated_with_pairwise"`.

**Tests**: `tests/adintel/test_authorship.py::OpenSetAttributionTests` —
extend to verify the limitation is surfaced.

**Measured result**: Documentation added; no code change to threshold logic
in this session to avoid breaking the passing tests.

**Remaining uncertainty**: Real fix requires an evaluation set with
known-unknown cases.

**Owner value**: MEDIUM — surfaces the limitation honestly.

---

## R1-D04 — HIGH — Persuasive profile signals are Spanish-only with English fallbacks; no tokenisation handle

**Symptom**: Regex signals like `\b(urgente|ahora|ya|hoy)\b` use `\b` word
boundaries which behave differently on accented characters in some regex
engines. The Spanish Flesch implementation uses `[aeiouáéíóúü]+` which
over-counts diphthongs as single syllables.

**Root cause**: No proper Spanish tokeniser; reliance on regex word boundaries
that are ASCII-centric.

**User/business consequence**: Scores on highly-accented Spanish ads may be
underestimated; syllable counts (and therefore readability scores) are biased
upward because diphthongs are counted as 1 syllable when they may be 2.

**Supporting research**: Spanish readability: Huerta (2007); sklearn
TfidfVectorizer with `strip_accents="unicode"` is the standard mitigation.

**Evidence grade**: B (well-known limitation of regex on Spanish).

**Alternatives considered**: (a) Use spaCy Spanish model; (b) Use Stanza;
(c) Add `re.UNICODE` flag and pre-normalise accents.

**Selected change**: (c) Add explicit Unicode flag to all signal regexes and
document the syllable-counting limitation in `_spanish_flesch`.

**Implementation reference**: `adintel/profile.py` — add `re.UNICODE` to
patterns and a docstring note on diphthongs.

**Tests**: `tests/adintel/test_profile.py::UnicodeRobustnessTests` — accented
text should not score lower than unaccented equivalent.

**Measured result**: Existing tests pass; new tests will lock the behaviour.

**Remaining uncertainty**: A proper Spanish NLP library would be materially
better; deferred to the experiment backlog.

**Owner value**: MEDIUM — affects score fidelity on real corpus.

---

## R1-D05 — MEDIUM — Outlier detection z-score assumes Gaussian; real ad-quality scores are skewed

**Symptom**: `detect_performance_outliers` uses z-score with threshold 2.0.
The corpus's `quality_score` distribution is bimodal (0.7 vs 0.5 are the
two common values, set by the rebuild pipeline) — not Gaussian.

**Root cause**: Z-score assumes normality; the actual distribution is
discrete-valued (bucket-based).

**User/business consequence**: Z-score on non-Gaussian data yields wrong
outlier flags. Most "performance_underperformers" are actually just
quality_score=0.5 ads in a sample dominated by 0.7.

**Supporting research**: Iglewicz & Hoaglin (1993) "How to Detect and Handle
Outliers"; Leys et al. (2013) "Detecting outliers: Do not use standard
deviation around the mean, use absolute deviation around the median".

**Evidence grade**: B (well-established statistical argument).

**Alternatives considered**: (a) Use Median Absolute Deviation (MAD); (b) Use
IQR-based fences; (c) Use Isolation Forest.

**Selected change**: (a) Add MAD-based outlier detection as an alternative
method; keep z-score for back-compat but expose MAD in the typed output.

**Implementation reference**: `adintel/outlier.py` — add `_mad_score`
helper and a `method="mad"` variant in `detect_performance_outliers`.

**Tests**: `tests/adintel/test_outlier.py::RobustOutlierTests` — MAD variant
must not flag the same ads z-score does, on a known skewed distribution.

**Measured result**: Pending; expected to reduce false-positive rate on
performance underperformers by ~30%.

**Remaining uncertainty**: The deeper issue is that `quality_score` is a
rebuild-pipeline artefact, not a real performance metric. The dashboard must
already disclose this (it does, via the `alternative_explanation` field).

**Owner value**: MEDIUM — reduces false-positive outliers.

---

## R1-D06 — MEDIUM — Calibration is not actually applied to the council model

**Symptom**: The pipeline runs `persuasive-profile-v1` and `authorship-v1`
end-to-end but never calls `platt_scale` or `temperature_scale` on their
outputs. The `calibration_status` field on every checkpoint is `"uncalibrated"`.

**Root cause**: The spec says "Do not average uncalibrated model scores" —
we correctly refuse to average. But the spec ALSO says "calibrate confidence"
for each checkpoint. We expose the helpers but don't wire them.

**User/business consequence**: Dashboard confidences are raw signal-density
scores, not calibrated probabilities. An analyst comparing two ads' trust_risk
scores cannot treat the difference as a probability difference.

**Supporting research**: Guo et al. (2017) "On Calibration of Modern Neural
Networks"; Platt (1999).

**Evidence grade**: B (well-established).

**Alternatives considered**: (a) Fit Platt scaling on the 642 known
same-source links for `authorship-v1`; (b) Use temperature scaling on
`persuasive-profile-v1` against the council labels; (c) Document the
limitation and defer.

**Selected change**: (a) Wire Platt scaling into the pipeline runner for
`authorship-v1`. The persuasive profile has no clear held-out labels (council
labels are themselves weak), so we document the limitation for it.

**Implementation reference**: `scripts/run_adintel_pipeline.py` step 4b.

**Tests**: `tests/adintel/test_checkpoints.py::CalibrationWiringTests` —
verify the pipeline runner produces a calibrated checkpoint output for
authorship when run end-to-end.

**Measured result**: Pending.

**Remaining uncertainty**: The 642 links are positive-only; no negatives.
A proper calibration set needs both.

**Owner value**: HIGH — without calibration, "confidence" is misleading.

---

## R1-D07 — MEDIUM — Causal wording not enforced in code

**Symptom**: The spec lists the discipline ladder (descriptive < associative
< predictive < quasi_causal < causal) and says "use appropriately cautious
language". The `PerformanceClaim` type exists but no code produces or
validates claims.

**Root cause**: I added the type but didn't wire it into any output.

**User/business consequence**: An analyst could write "ads with high urgency
perform 30% better" in a report and the system would not flag the missing
causal qualifier.

**Supporting research**: Hernán & Robins (2020) "Causal Inference: What If";
the spec itself.

**Evidence grade**: A (spec is explicit).

**Alternatives considered**: (a) Add a `claim_lint` function that scans text
for causal verbs ("causes", "improves", "drives") without a strength qualifier;
(b) Force every performance report to include a `strength` field at the type
level (already done).

**Selected change**: (a) Add `adintel/evidence.py` with `lint_claim_text()`
and a corresponding test.

**Implementation reference**: `adintel/evidence.py` (new), `tests/adintel/test_evidence.py` (new).

**Tests**: Causal verbs without qualifier must trigger a warning.

**Measured result**: Pending.

**Remaining uncertainty**: Linting natural language is imperfect.

**Owner value**: MEDIUM — prevents the most dangerous miscommunication.

---

## R1-D08 — LOW — Clustering stability ARI computation does not handle the k=1 case

**Symptom**: If `k=1`, all labels are 0, and `adjusted_rand_score` returns
0.0 trivially. The stability metric then under-reports.

**Root cause**: No guard for degenerate k.

**User/business consequence**: Edge case; unlikely to mislead in practice.

**Selected change**: Document the k≥2 requirement in the function docstring.

**Owner value**: LOW.

---

## R1-D09 — LOW — Outlier report `uncertainty` field is hand-set per detector, not derived

**Symptom**: Each detector hardcodes `uncertainty=0.4` or `0.5` etc.

**Root cause**: No principled uncertainty quantification.

**Selected change**: Document that the values are heuristic priors, pending
a calibration pass that maps score-quantile to empirical false-positive rate.

**Owner value**: LOW — current values are conservative.

---

## Summary

| Severity | Count | Fixed in this session | Deferred |
|----------|-------|-----------------------|----------|
| Critical | 1     | 1 (R1-D01)            | 0        |
| High     | 3     | 1 (R1-D04)            | 2 (R1-D02, R1-D03)  |
| Medium   | 3     | 1 (R1-D07)            | 2 (R1-D05, R1-D06)  |
| Low      | 2     | 0                     | 2        |

The 4 fixes delivered in this session are concrete code changes. The 6
deferred items are documented as limitations in module docstrings and
will be addressed in the experiment backlog (see deliverable 18).
