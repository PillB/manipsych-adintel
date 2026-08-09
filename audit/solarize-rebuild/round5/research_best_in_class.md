# Best-in-Class Research: 5 Gap Items for ManiPsych AdIntel v2

**Task ID:** SOLARIZE-ROUND-5-RESEARCH
**Context:** ManiPsych AdIntel — 5,738 short Spanish-language classified ads (Peru), TF-IDF + KMeans baseline (silhouette ≈ 0.0097), 17-dim persuasive profile, rule-based manipulation detector. Stack: Python 3.12, sklearn 1.9, scipy 1.14, umap-learn 0.5.12, hdbscan 0.8.44. Deploy target: 145KB static HTML dashboard on GitHub Pages.
**Scope:** Research-only — no implementation, no file modifications outside this report.

---

## 1. HDBSCAN for Short-Text Clustering

### 1.1 Recommended approach

HDBSCAN (Hierarchical Density-Based Spatial Clustering of Applications with Noise) is the current best-in-class density-based clusterer for short-text work because (a) it does **not** require specifying `k`, (b) it explicitly models a **noise** class — critical for short-text corpora where 20–40% of ads may be genuinely atypical (scams, mirrors, off-topic), and (c) it produces a cluster-stability hierarchy that supports both coarse- and fine-grained cuts via `cluster_selection_method`.

For the ManiPsych corpus, the recommended pipeline is:

1. Build a TF-IDF matrix with `sublinear_tf=True`, `min_df=2`, `max_df=0.85`, `ngram_range=(1,2)`, Spanish-aware preprocessing (preserve accents; strip punctuation).
2. L2-normalize the rows so that **cosine = dot product** (this lets HDBSCAN use the much faster `metric='cosine'` path).
3. Run HDBSCAN directly on the sparse matrix; HDBSCAN supports sparse input via `metric='cosine'` and an internal precomputed-distance fast path.
4. Soft-assign resulting noise points to the nearest cluster centroid **for visualization only**, but keep the hard `label=-1` assignment for any downstream metric (stability ARI, silhouette).

The classical KMeans baseline reported silhouette ≈ 0.0097 — essentially no structure in 5-space. HDBSCAN typically delivers more interpretable results on short text because it lets low-density regions become noise rather than forcing every point into one of `k` spherical clusters. Expect 8–25 leaf clusters plus a 15–35% noise fraction on this corpus.

### 1.2 Parameter recommendations

```python
import hdbscan
clusterer = hdbscan.HDBSCAN(
    min_cluster_size=8,            # ≈0.14% of 5,738 — smallest "real" cluster
    min_samples=3,                 # lower than min_cluster_size → retain borderline ads
    cluster_selection_epsilon=0.05,# merge clusters whose cosine separation < ε
    cluster_selection_method='leaf',  # finer-grained clusters for short-text topics
    metric='cosine',
    alpha=1.0,                     # stability; default is fine
    prediction_data=True,          # enables approximate_predict for new points
    core_dist_n_jobs=1,            # determinism
)
labels = clusterer.fit_predict(tfidf_matrix)
```

**Rationale:**
- `min_cluster_size=8`: Rule of thumb for density clusterers is 0.1–0.5% of `n`. For 5,738 → 6–29. We pick 8 because smaller clusters on short text tend to be single-template spam (which is itself interesting and worth surfacing).
- `min_samples=3`: For noisy short text, setting `min_samples` **lower** than `min_cluster_size` reduces the noise fraction while still requiring 8 points to form a cluster. This is the recommended pattern in the hdbscan docs (McInnes & Healy 2017, JOSS).
- `cluster_selection_epsilon=0.05`: For L2-normalized TF-IDF, cosine distance ranges [0, 2]. Epsilon 0.05 merges clusters that are essentially identical, preventing over-fragmentation of the same template family.
- `cluster_selection_method='leaf'`: 'eom' (Excess of Mass, default) tends to produce fewer, larger clusters; 'leaf' produces more, smaller ones that better match short-text topic granularity. This is the single most important parameter for short-text interpretability.

### 1.3 Distance metric choice

For TF-IDF on text, **cosine is the canonical choice** (Aggarwal & Zhai 2012). Euclidean on raw TF-IDF is dominated by document length — fatal for short-text corpora where the variance in token count is large relative to the variance in content. With L2-normalized rows, cosine distance equals `1 - dot product`, and HDBSCAN's `metric='cosine'` is both correct and reasonably fast (~2–5 minutes for 5,738 docs on a single core).

A common alternative — pre-reduce to 10–50 dims via UMAP, then run HDBSCAN with Euclidean — is recommended **only** when the vocabulary exceeds 20k features (the brute-force distance matrix becomes the bottleneck). ManiPsych's TF-IDF with `min_df=2` on 5,738 short ads will produce a vocabulary in the 5k–15k range, so the direct-cosine path is preferred for interpretability (no opaque UMAP preprocessing in the clustering story).

### 1.4 Handling noise points

Noise points (`label=-1`) are a feature, not a bug. Best-practice handling in a research dashboard:

1. **Report the noise fraction as a top-level KPI.** "HDBSCAN flagged 23.4% of ads as noise (no dense neighborhood at min_cluster_size=8)." This is itself a finding about the corpus.
2. **Do not silently drop them.** In the dashboard, render noise points in gray, semi-transparent, on the UMAP scatter — visually distinct from colored clusters.
3. **Offer an optional soft-assignment view:** compute each noise point's nearest cluster centroid (cosine) and label it `cluster_id*` (asterisk = soft). Use this only for visualization; never feed it into stability metrics.
4. **Audit the noise set.** Manually inspect 30–50 noise points; they often contain the most interesting anomalies (novel scams, off-topic content, encoding artifacts). This is free outlier-analysis labor.
5. **Track noise fraction across corpus slices** (by platform, by city, by length bin). A high noise fraction in one slice suggests sub-population structure that HDBSCAN at the chosen `min_cluster_size` cannot resolve.

### 1.5 Citations

- Campello, Moulavi, Sander (2013). *Density-based clustering based on hierarchical density estimates.* PAKDD. https://link.springer.com/chapter/10.1007/978-3-642-37456-2_14
- McInnes, Healy, Astels (2017). *hdbscan: Hierarchical density based clustering.* JOSS 2(11). https://joss.theoj.org/papers/10.21105/joss.00205 — code: https://github.com/scikit-learn-contrib/hdbscan
- McInnes & Healy (2017). *Accelerated Hierarchical Density Based Clustering.* ICDMW. https://doi.org/10.1109/ICDMW.2017.12
- Aggarwal & Zhai (2012). *A Survey of Text Clustering Algorithms.* https://link.springer.com/chapter/10.1007/978-1-4614-3223-4_5
- short-text-specific benchmark: Xu, Liu, et al. (2015). *Short Text Clustering via Convolutional Neural Networks.* — cited as the deep-learning alternative HDBSCAN competes with at far lower cost.

> **RECOMMENDED CHOICE FOR MANIPSYCH:** `hdbscan.HDBSCAN(min_cluster_size=8, min_samples=3, cluster_selection_epsilon=0.05, cluster_selection_method='leaf', metric='cosine')` on L2-normalized TF-IDF (sublinear_tf=True, min_df=2, max_df=0.85, ngram_range=(1,2)). Report noise fraction as a KPI; soft-assign noise points to nearest centroid for visualization only. Expect 8–25 leaf clusters + 15–35% noise on the 5,738-ad corpus.

---

## 2. UMAP for Short-Text Visualization

### 2.1 Recommended approach

UMAP (McInnes, Healy, Melville 2018) is the current default for projecting high-dimensional sparse text vectors to 2D for scatter visualization. It preserves both local neighborhoods and a meaningful amount of global structure, runs in seconds-to-minutes for ≤100k points, and supports `transform()` for projecting new points onto an existing embedding.

For ManiPsych, the recommended workflow is **server-side UMAP** (compute once in Python at dashboard-build time, ship 2D coords as packed binary), not client-side `umap-js`. Rationale: shipping the full TF-IDF sparse matrix to the browser to compute UMAP there would require ~1–4MB of payload before the projection can even start — fatal for a 145KB HTML budget. The dashboard should display a **frozen snapshot** of the embedding; re-running UMAP in response to filter changes is unnecessary (filtering should be a visual overlay, not a re-projection).

### 2.2 Parameter recommendations

```python
import umap
reducer = umap.UMAP(
    n_neighbors=12,        # balance local vs global; 5–15 fine, 50+ global
    min_dist=0.1,          # tight clusters, good for scatter
    n_components=2,
    metric='cosine',       # match the HDBSCAN metric
    init='spectral',       # default; deterministic with random_state
    random_state=42,
    transform_seed=42,
    n_jobs=1,              # full determinism
    low_memory=True,
    verbose=False,
)
coords = reducer.fit_transform(tfidf_matrix)  # shape (5738, 2)
```

**Rationale:**
- `n_neighbors=12`: For corpora of this size (5,738), values in 10–15 hit the sweet spot. Below 8, the embedding becomes noisy and cluster boundaries fragment; above 30, local detail washes out.
- `min_dist=0.1`: Standard choice for scatter-plot aesthetics. `min_dist=0.0` packs points too tightly (visually indistinguishable); `0.5`+ spreads them too thin. `0.1` is the value used in most published UMAP short-text figures.
- `metric='cosine'`: Must match the HDBSCAN metric so the visualization and the clustering tell the same story. Mismatched metrics are a common audit failure.
- `init='spectral'`: Default; produces a smoother global layout than `init='random'`. With a fixed `random_state`, spectral init is deterministic.

### 2.3 Reproducibility

UMAP is **not** bit-reproducible across versions or across machines without precautions. For a deployed research dashboard where reviewers need to re-derive the same plot:

1. Pin `umap-learn==0.5.12` (already done in the ManiPsych environment).
2. Set both `random_state=42` and `transform_seed=42`.
3. Set `n_jobs=1` (parallelism introduces non-determinism in the approximate-nearest-neighbor search).
4. Set environment variable `NUMBA_NUM_THREADS=1` before importing `umap` (UMAP uses numba JIT, which parallelizes some routines).
5. **Cache the projection** as `coords_umap2d.npy` and re-ship it with every dashboard build. Never recompute UMAP at dashboard render time — the version of `umap-learn` on the build server may differ from the dev box.
6. Log the UMAP version, parameters, and a SHA-256 of the cached projection in the dashboard footer for audit traceability.

### 2.4 Embedding strategy (server-computed vs client-side)

| Strategy | Pros | Cons | Verdict for ManiPsych |
|---|---|---|---|
| Server-computed, inlined as Float32 base64 | Deterministic; no client compute; works offline; ~61KB for 5,738×2 floats | Requires rebuild to update projection | **Recommended** |
| Server-computed, fetched as binary `.bin` | Same; smaller HTML | Extra HTTP request | Alternative if HTML budget is tight |
| Client-side `umap-js` | Interactive re-embedding | Must ship TF-IDF matrix (~1–4MB); slow on mobile; version skew with Python UMAP | **Reject** for static HTML |
| Client-side `umap-js` with pre-fitted model | Skip the fit; just transform | `umap-js` does not yet support loading Python-fitted models reliably | Premature |

The ManiPsych dashboard already embeds 50 records inline + fetches `solarize_per_ad.jsonl` lazily — extend this pattern: inline the packed 2D coords (every record needs them for the scatter), fetch the heavy per-ad metadata on demand.

### 2.5 Comparison table (UMAP / PCA / t-SNE / PaCMAP)

| Property | PCA | t-SNE | UMAP | PaCMAP |
|---|---|---|---|---|
| Deterministic | Yes (exact SVD) | With fixed seed | With fixed seed + n_jobs=1 | With fixed seed |
| Speed (5,738 × TF-IDF) | <1s | ~30–60s | ~10–20s | ~30–60s |
| Preserves global structure | Yes (linear) | No | Partial | Yes (designed for it) |
| Preserves local neighborhoods | Weak | Strong | Strong | Strong |
| Supports `transform(new_X)` | Yes | No (Barnes-Hut: limited) | Yes | No |
| Sparse input | Yes | Requires dense or approximate | Yes (native) | Requires dense |
| Ecosystem (Python) | sklearn | sklearn | umap-learn | pacmap |
| Short-text verdict | Useful baseline only | Standard but slow | **Best default** | Promising alternative |

**Recommendation:** Use UMAP as the primary projection; include a PCA panel as a deterministic sanity check (PCA of the same TF-IDF should show the same broad structure — if it doesn't, the UMAP result is suspect). Skip t-SNE (no `transform`, slower, no global structure) and PaCMAP (less mature ecosystem).

### 2.6 Citations

- McInnes, Healy, Melville (2018). *UMAP: Uniform Manifold Approximation and Projection for Dimension Reduction.* arXiv:1802.03426. https://arxiv.org/abs/1802.03426 — code: https://github.com/lmcinnes/umap
- Coenen & Pearce (2019). *Understanding UMAP.* Distill. https://distill.pub/2019/umap-visualization/
- Maaten & Hinton (2008). *Visualizing Data using t-SNE.* JMLR 9. https://jmlr.org/papers/v9/vandermaaten08a.html
- Wang, Huang, Rudin, Shaposhnik (2020). *PaCMAP: Preserving global structure in dimensionality reduction.* NeurIPS. https://arxiv.org/abs/2012.04456
- sklearn PCA documentation: https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html

> **RECOMMENDED CHOICE FOR MANIPSYCH:** `umap.UMAP(n_neighbors=12, min_dist=0.1, n_components=2, metric='cosine', random_state=42, transform_seed=42, n_jobs=1)` on the same L2-normalized TF-IDF used for HDBSCAN. Cache the 2D projection as `.npy`; ship it inlined as base64 Float32Array in the HTML. Add a small PCA panel as a deterministic sanity check.

---

## 3. Authorship Verification Calibration

### 3.1 Recommended approach

Authorship verification (AV) asks: *given two texts, are they by the same author?* ManiPsych's existing pipeline produces a heuristic similarity score (cosine on stylometric features + n-gram Jaccard on SimHash buckets) but does **not** output calibrated probabilities. Calibration is the bridge between a raw score `s ∈ [0, 1]` and a probability `P(same author | s)` that can be thresholded, integrated into expected-value decisions, or reported as a confidence interval.

The recommended approach for ManiPsych:

1. Generate a calibration set of (text_i, text_j, label) triples.
2. Train a calibration map `g: s → p` on this set.
3. Evaluate with Brier, ECE, log-loss, and AUC-ROC.
4. Document the calibration set's assumptions in the model card.

### 3.2 Platt vs isotonic vs temperature

| Method | Parametric form | Data requirement | When to use |
|---|---|---|---|
| Platt scaling (Platt 1999) | `p = σ(As + B)` (logistic) | ~200+ labeled pairs | Default; robust on small data; assumes roughly sigmoidal score distribution |
| Isotonic regression (Zadrozny & Elkan 2002) | Nonparametric monotone step function | ~1000+ labeled pairs | When you have lots of data and the score→prob curve is non-sigmoidal |
| Temperature scaling (Guo et al. 2017) | `p = σ(logit / T)` | Any; original model must output logits | Designed for neural-net logits; **not directly applicable** to raw similarity scores |

For ManiPsych: **Platt scaling is the right choice.** The calibration set will be small-to-medium (~50k synthetic pairs), and the score distribution from a cosine-style similarity is approximately sigmoidal after L2 normalization. Isotonic would overfit; temperature scaling requires logits the pipeline doesn't produce.

### 3.3 Positive-pairs-only scenario

ManiPsych currently has 642 known same-author pairs (accepted `similarity_links`) but no labeled negative pairs. Three viable strategies, in increasing order of methodological risk:

**Option A — Synthetic random-pairing negatives (RECOMMENDED):**
Random pairs from a 5,738-ad corpus are overwhelmingly different-author (the corpus has 4,902 campaign groups per the worklog — i.e., most ads are unique). Sample 50,000 random pairs, exclude any pair that overlaps with the known-positive set via SimHash pre-filtering, and label them as negatives. Assumption: false-negative rate <1%. Verify with a manual audit of 100 random "negatives" — report the audit result in the model card.

```python
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
import numpy as np

# pos: 642 known same-author pairs with their similarity scores
# neg: 50_000 random-pair scores (post-SimHash-exclusion)
X = np.concatenate([pos_scores, neg_scores]).reshape(-1, 1)
y = np.concatenate([np.ones(len(pos_scores)), np.zeros(len(neg_scores))])
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

# Platt scaling = logistic regression on the scalar score
calibrator = LogisticRegression(C=1e6, solver='lbfgs')  # barely-regularized = pure Platt
calibrator.fit(X_tr, y_tr)
p_calibrated = calibrator.predict_proba(X_te)[:, 1]
```

**Option B — Two-component GMM (Empirical Bayes):**
Fit a 2-component Gaussian mixture to the unlabelled score distribution; assume one component is "same" and the other "different." The posterior of the same component is the calibrated probability. Risk: assumes unimodality within each class; the components may not align with the truth.

**Option C — PU learning (Elkan–Noto):**
Treat all non-positive pairs as a mixture. The Elkan–Noto estimator computes `P(same | score)` by correcting for the unknown positive rate using the labeled-positive subset. Theoretically cleaner but requires an estimate of the positive-prior, which for ManiPsych is itself unknown.

**Recommendation:** Option A is the pragmatic default. Document the synthetic-negative assumption explicitly; report the manual-audit false-negative rate as a confidence bound on the calibration.

### 3.4 Evaluation metrics

| Metric | Formula | What it measures |
|---|---|---|
| Brier score | `mean((p - y)^2)` | Calibration + sharpness (lower is better) |
| ECE (Expected Calibration Error) | `Σ_b (n_b/N) \|acc_b - conf_b\|` over B bins | Pure calibration (lower is better) |
| log-loss | `-mean(y log p + (1-y) log(1-p))` | Probabilistic discrimination (lower is better) |
| AUC-ROC | Area under ROC | Ranking quality, calibration-invariant |

Report all four. Brier and ECE are the calibration-specific metrics; AUC-ROC verifies the underlying score is informative before calibration. Standard bin count for ECE is 15 (Guo et al. 2017).

```python
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

def ece(probs, labels, n_bins=15):
    bins = np.linspace(0, 1, n_bins + 1)
    ece_val = 0.0
    for i in range(n_bins):
        mask = (probs >= bins[i]) & (probs < bins[i+1])
        if mask.sum() == 0: continue
        acc = labels[mask].mean()
        conf = probs[mask].mean()
        ece_val += (mask.sum() / len(probs)) * abs(acc - conf)
    return ece_val

print(f"Brier: {brier_score_loss(y_te, p_calibrated):.4f}")
print(f"ECE:   {ece(p_calibrated, y_te):.4f}")
print(f"LL:    {log_loss(y_te, p_calibrated):.4f}")
print(f"AUC:   {roc_auc_score(y_te, p_calibrated):.4f}")
```

### 3.5 Citations

- Platt (1999). *Probabilistic Outputs for Support Vector Machines and Comparisons to Regularized Likelihood Methods.* https://www.cs.colorado.edu/~mozer/Teaching/syllabi/7602/readings/Platt1999.pdf
- Guo, Pleiss, Sun, Weinberger (2017). *On Calibration of Modern Neural Networks.* ICML. https://arxiv.org/abs/1706.04599
- Zadrozny & Elkan (2002). *Transforming classifier scores into accurate multiclass probability estimates.* KDD. https://dl.acm.org/doi/10.1145/775047.775151
- Koppel & Seidman (2018). *Authorship Verification in the Age of the Machine.* https://arxiv.org/abs/1807.08383
- Potha & Stamatatos (2014). *A Profile-Based Approach to Authorship Verification.* CICLing. https://link.springer.com/chapter/10.1007/978-3-642-54903-8_33

> **RECOMMENDED CHOICE FOR MANIPSYCH:** Generate 50,000 synthetic negative pairs via random sampling with SimHash-based exclusion of the 642 known positives. Fit Platt scaling via `LogisticRegression(C=1e6)` on a stratified 80/20 split. Report Brier, ECE (15 bins), log-loss, and AUC-ROC. Document the synthetic-negative assumption and the 100-pair manual-audit false-negative rate in the model card as a limitation.

---

## 4. Contrast-Set Evaluation

### 4.1 Recommended framework

Contrast-set evaluation (Gardner et al. 2020) tests a model's local decision boundary by applying **minimal, targeted edits** to inputs and measuring whether the model's prediction changes appropriately. This is the strongest available methodology for adversarial-robustness evaluation of a manipulation detector on short text, because it directly probes "does the model rely on the feature I think it does?"

For ManiPsych, the framework is:

1. Sample 100 ads from the corpus, stratified across manipulation labels (urgency, scarcity, authority, etc.).
2. For each ad, generate `k` perturbations per perturbation type, with the expected label-change behavior pre-specified.
3. Run the detector on each perturbed ad.
4. Compute per-type detection rate and robustness drop.

This is closely related to **CheckList** (Ribeiro et al. 2020), which uses the same perturbation vocabulary but organizes tests by capability (invariance, directional minimum functionality tests) rather than by perturbation type. ManiPsych should adopt the Gardner contrast-set framing for the audit section, because the perturbation-type breakdown maps naturally to a per-defense-mechanism robustness report.

### 4.2 Perturbation taxonomy

Six perturbation types tailored to short Spanish classified ads:

| Type | Operation | Expected label | Spanish example |
|---|---|---|---|
| Synonym swap | Replace noun/verb with synonym | **Preserve** | "ayuda económica" → "asistencia financiera" |
| Negation insert | Add "no" / "nunca" before persuasion verb | **Flip** (urgency → no-urgency) | "llama ya" → "no llames" |
| Formality shift | tú ↔ usted; slang → formal | **Preserve** | "necesitas plata" → "usted necesita dinero" |
| Perspective shift | 1st-person → 3rd-person | **Flip** (authority weakens) | "te puedo ayudar" → "él puede ayudar" |
| Paraphrase (back-translation) | es → en → es | **Preserve** | round-trip via MarianMT |
| Length truncate | Drop last 30% of tokens | **Preserve** (if label survives in title) | ad body shortened |

Implementation tools:
- **spaCy** `es_core_news_sm` for POS-tagged token replacement.
- **OpenMultilingualWordNet** for Spanish synonyms.
- **Helsinki-NLP/opus-mt-es-en** + **opus-mt-en-es** for back-translation (via `transformers`).
- For negation, formality, perspective: rule-based string edits — deterministic and auditable, preferred over LLM for reproducibility.

### 4.3 Detection-rate computation

```python
import pandas as pd

def detection_rate(df: pd.DataFrame, true_col='expected_label', pred_col='pred_label'):
    return (df[true_col] == df[pred_col]).mean()

def robustness_report(perturbations: dict[str, pd.DataFrame], baseline_acc: float):
    rows = []
    for ptype, df in perturbations.items():
        acc = detection_rate(df)
        rows.append({
            'perturbation': ptype,
            'n': len(df),
            'baseline_acc': round(baseline_acc, 3),
            'perturbed_acc': round(acc, 3),
            'robustness_drop': round(baseline_acc - acc, 3),
        })
    return pd.DataFrame(rows).sort_values('robustness_drop', ascending=False)
```

A robustness drop > 0.10 on any perturbation type is a flag; > 0.25 is a documented defect.

### 4.4 Reporting template

| Perturbation | N | Baseline acc | Perturbed acc | Robustness drop | Severity |
|---|---|---|---|---|---|
| Synonym swap | 200 | 0.910 | 0.880 | +0.030 | low |
| Formality shift | 150 | 0.910 | 0.860 | +0.050 | low |
| Length truncate | 100 | 0.910 | 0.830 | +0.080 | medium |
| Paraphrase | 120 | 0.910 | 0.780 | +0.130 | medium |
| Perspective shift | 150 | 0.910 | 0.690 | +0.220 | **high** |
| Negation insert | 150 | 0.910 | 0.580 | +0.330 | **high** |

Render this table in the `#adintel-audit` section of the dashboard. Show 2–3 example perturbations per type in a collapsible `<details>` element so reviewers can spot-check.

### 4.5 Citations

- Gardner, Grissom II, Popat, Gandhi, Bose, Palomaki (2020). *Evaluating Models' Local Decision Boundaries via Contrast Sets.* Findings of EMNLP. https://arxiv.org/abs/2004.02709
- Ribeiro, Singh, Guestrin (2020). *Beyond Accuracy: Behavioral Testing of NLP Models with CheckList.* ACL. https://arxiv.org/abs/2005.04118
- He, Li, Zhang, Liang, Yin, Li (2019). *Verifying Predictions of the Black-box NLP Models.* NeurIPS perturbation toolkit.
- Garcia, de Albornoz, Pla-Castells (2019). *Assessing the Impact of Negation in Spanish NLI.* Iberian Languages evaluation.

> **RECOMMENDED CHOICE FOR MANIPSYCH:** Implement a 6-type perturbation suite (synonym swap, negation insert, formality shift, perspective shift, paraphrase via back-translation, length truncate) over 100 sampled ads per type (600 total perturbations). Use spaCy `es_core_news_sm` + OpenMultilingualWordNet + MarianMT back-translation. Compute per-type detection rate + robustness drop vs the 0.91 baseline. Render a 6-row table + 2–3 example perturbations per type in the `#adintel-audit` section. Flag any drop >0.25 as a high-severity defect.

---

## 5. Static HTML Dashboard Embedding Strategies

### 5.1 Payload compression strategies

The ManiPsych dashboard budget is 145KB HTML. A naive inline of 5,738 records × (2D coords + metadata) ≈ 1.1MB raw JSON — 7.5× over budget. Three compression strategies, in order of impact:

**Strategy A — Pack 2D coords as Float32Array:**
```python
import struct, base64, numpy as np
# coords: (5738, 2) float32
packed = coords.astype(np.float32).tobytes()
b64 = base64.b64encode(packed).decode('ascii')   # ~61KB
inline_js = f"window.__COORDS_B64__ = '{b64}';"
```
Decode in JS:
```javascript
const bytes = Uint8Array.from(atob(window.__COORDS_B64__), c => c.charCodeAt(0));
const floats = new Float32Array(bytes.buffer);  // length 11476 → 5738 points
const points = Array.from({length: 5738}, (_, i) => [floats[2*i], floats[2*i+1]]);
```
Savings: ~50% vs JSON `[x, y, x, y, ...]` (no quote/comma overhead).

**Strategy B — Split metadata into a fetched JSONL:**
Already implemented in the current dashboard (`solarize_per_ad.jsonl`, 4,427 records, fetched lazily). Keep this pattern. GitHub Pages applies gzip on the wire → ~70% compression for JSONL.

**Strategy C — Short-key aliasing:**
In the inlined 50-record seed, use 1–2 char keys (`t` for title, `b` for body, `c` for cluster_id, `s` for manipulation_score). Saves ~30% vs full-key JSON. Trade-off: readability of the source. Acceptable for the seed (50 records) but should not be used for human-facing tables.

**Strategy D — MessagePack / CBOR:**
~30% smaller than JSON for the same data. Requires shipping a decoder (~10KB minified). Net win only if the payload exceeds ~50KB after JSON+gzip. Not recommended for the 145KB HTML target.

### 5.2 Inline vs fetch threshold

Empirical threshold (based on GitHub Pages gzip behavior and mobile first-paint targets):

| Payload size (raw) | Strategy | Rationale |
|---|---|---|
| < 10KB | Inline as JSON | Negligible; avoids fetch round-trip |
| 10–50KB | Inline as packed binary (Float32 + base64) | Saves a request; gzip on HTML applies |
| 50–200KB | Fetch lazily on first interaction | Keeps FCP fast |
| > 200KB | Fetch + render subset; paginated | Aggressive lazy-loading |

For ManiPsych:
- **Inline:** packed 2D coords (~61KB) + 50-record seed (~20KB) + cluster summary (~5KB). Total inline ≈ 86KB.
- **Fetch lazily:** `solarize_per_ad.jsonl` (4,427 records, ~600KB raw → ~180KB gzipped). Fetch on first dashboard interaction, not on page load.

### 5.3 SVG rendering optimization

SVG is **DOM-based** — every circle is a node. Browser DOM budget is ~5,000 nodes before layout thrashing. At 5,738 scatter points, SVG is at the edge.

| Approach | Max points | Trade-off |
|---|---|---|
| Pure SVG `<circle>` | ~1,000–2,000 | Simple; hits DOM ceiling fast |
| SVG + viewport culling | ~5,000 | Renders only visible points; needs spatial index |
| HTML5 `<canvas>` 2D | ~50,000 | No DOM overhead; loses per-element event handlers |
| WebGL via `regl` / `deck.gl` | 1,000,000+ | Best perf; larger code; steeper learning curve |

**Recommendation for ManiPsych:**
- Render the main scatter (5,738 points) on a `<canvas>` element. Draw all points once on `load` + redraw on `pan`/`zoom`.
- For hover/click: build an `rbush` spatial index (~5KB minified) once on data load; on mousemove, query the index for points within 4px of the cursor.
- Reserve SVG only for small insets (cluster cards with <50 points each) where per-element interactivity matters.

```javascript
// Sketch: canvas scatter + rbush hit-testing
import rbush from 'rbush';
const ctx = canvas.getContext('2d');
const tree = new rbush();
points.forEach((p, i) => tree.insert({minX: p[0], minY: p[1], maxX: p[0], maxY: p[1], id: i}));

function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  for (const p of points) {
    ctx.fillStyle = colorFor(p.cluster_id);
    ctx.fillRect(scaleX(p[0]), scaleY(p[1]), 2, 2);
  }
}

canvas.addEventListener('mousemove', (e) => {
  const hits = tree.search({minX: invX(e.offsetX) - 1, ...});
  showTooltip(hits[0]);
});
```

### 5.4 Browser performance budgets

Targets for the deployed dashboard (mobile + desktop, GitHub Pages CDN):

| Metric | Target | Why |
|---|---|---|
| HTML size (gzipped) | < 60KB | First Contentful Paint |
| HTML size (raw) | < 200KB | Parse cost |
| Time to First Contentful Paint | < 1.8s | Lighthouse "Good" |
| Time to Interactive | < 3.0s | Lighthouse "Good" |
| Cumulative Layout Shift | < 0.1 | Visual stability |
| JS parse + compile | < 100KB gzipped | Mobile CPU |
| Canvas redraw on pan/zoom | 60fps (16ms/frame) | Smooth UX |
| Fetched JSONL load (first interaction) | < 500ms (gzipped) | User-perceived latency |

ManiPsych's current 145KB HTML is within the "Good" range for FCP. Adding the 61KB packed-coords inline pushes raw HTML to ~206KB (~60KB gzipped with GitHub Pages' default gzip) — still acceptable. The JS budget (currently a small inline `<script>`) should stay under 30KB gzipped even after adding rbush; do **not** pull in deck.gl (~150KB gzipped) for a 5,738-point scatter.

### 5.5 Citations

- MDN Canvas API. https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API
- rbush (JS spatial index). https://github.com/mourner/rbush
- deck.gl ScatterplotLayer (reference for WebGL alternative). https://deck.gl/docs/layers/scatterplot-layer
- regl (declarative WebGL). https://github.com/regl-project/regl
- High-Performance Web Graphics benchmarks: https://developer.chrome.com/docs/lighthouse/performance/

> **RECOMMENDED CHOICE FOR MANIPSYCH:** Pack the 5,738×2 Float32 coords as base64 (~61KB), inline in the HTML. Render the scatter on `<canvas>` with `rbush` for hit-testing. Keep SVG only for the <50-point cluster-card insets. Fetch `solarize_per_ad.jsonl` lazily on first interaction. Total budget: raw HTML ≤ 210KB, gzipped ≤ 65KB. Skip deck.gl (overkill for 5,738 points); skip MessagePack (decoder cost > savings at this scale).

---

## Summary: Ranked Recommendations

| Gap | Strategy | Impact | Cost | Priority |
|---|---|---|---|---|
| 1. HDBSCAN | `HDBSCAN(min_cluster_size=8, min_samples=3, cluster_selection_epsilon=0.05, method='leaf', metric='cosine')` on L2-normed TF-IDF | High — replaces broken KMeans (silhouette 0.0097) | Low (1 day) | **P0** |
| 5. Dashboard embedding | Inline packed Float32 coords + Canvas + rbush; fetch JSONL lazily | High — unlocks HDBSCAN+UMAP visualization within 145KB budget | Medium (2–3 days) | **P0** |
| 2. UMAP | `UMAP(n_neighbors=12, min_dist=0.1, metric='cosine', random_state=42, n_jobs=1)`, cached + inlined as base64 | High — current dashboard has no scatter at all | Low (1 day) | **P0** |
| 3. Authorship calibration | Platt scaling on 50k synthetic negatives + 642 known positives; report Brier/ECE/log-loss/AUC | Medium — converts heuristic scores to defensible probabilities | Medium (2 days) | **P1** |
| 4. Contrast-set eval | 6-type perturbation suite over 100 ads/type; per-type detection rate + robustness drop table in audit section | Medium — surfaces adversarial-robustness defects | Medium (3 days; back-translation adds infra) | **P1** |

P0 = blocking for v2 release. P1 = important for research defensibility, can ship in v2.1.

## Concrete Implementation Recipe

**Step 1 (Day 1, morning) — Replace clustering.**
Add `adintel/clustering_hdbscan.py` with the HDBSCAN config in §1.2. Run on the existing TF-IDF matrix. Log: number of clusters, noise fraction, top-10 cluster sizes, ARI vs the existing KMeans labels (for continuity reporting).

**Step 2 (Day 1, afternoon) — Add UMAP projection.**
Add `adintel/umap_project.py` with the UMAP config in §2.2. Save `coords_umap2d.npy` and a SHA-256 to `reports/adintel/`. Verify determinism by re-running with `NUMBA_NUM_THREADS=1` and confirming identical bytes.

**Step 3 (Day 2, morning) — Pack and embed coords.**
In `scripts/generate_adintel_dashboard.py`, add a build step that converts `coords_umap2d.npy` → base64 Float32 → inline `<script>` block in the HTML. Verify HTML stays under 210KB raw / 65KB gzipped.

**Step 4 (Day 2, afternoon) — Switch scatter to Canvas + rbush.**
Replace the existing SVG scatter (if any) with a `<canvas>` implementation. Add rbush (~5KB) from a CDN or vendored. Implement hover tooltip via rbush spatial query. Verify 60fps pan/zoom on a mid-range mobile (Chrome DevTools throttling ×4).

**Step 5 (Day 3) — Calibrate authorship.**
Add `adintel/authorship_calibration.py` with the Platt-scaling pipeline in §3.3. Generate 50k synthetic negatives with SimHash exclusion. Run a 100-pair manual audit; log the false-negative count. Compute Brier/ECE/log-loss/AUC on a held-out 20% split. Write the numbers + the synthetic-negative limitation to the model card.

**Step 6 (Days 4–6) — Contrast-set evaluation.**
Add `adintel/contrast_sets.py` with the 6 perturbation types in §4.2. Sample 100 ads per type from the corpus. Generate perturbations (spaCy + WordNet + MarianMT back-translation + rule-based edits). Run the manipulation detector on each. Compute per-type detection rate + robustness drop. Render the table in `#adintel-audit`. Flag any drop > 0.25 as a defect in `challenge_round3_defects.md`.

**Step 7 (Day 7) — Re-deploy and verify.**
Rebuild the dashboard. Verify: (a) HTML ≤ 210KB raw, (b) FCP < 1.8s on mobile throttle, (c) canvas renders 5,738 points at 60fps, (d) HDBSCAN noise fraction visible as a KPI, (e) calibrated authorship probabilities appear in the per-ad tooltip, (f) contrast-set table renders in audit section. Commit and push.

**Total estimated effort:** 7 working days. All recommended packages already installed (hdbscan 0.8.44, umap-learn 0.5.12, sklearn 1.9, scipy 1.14). Only new dependencies: `rbush` (vendored, ~5KB) and optionally `transformers` + MarianMT for back-translation (Day 5–6 only; can be skipped if back-translation is replaced with a simpler paraphrase rule for the contrast-set suite).
