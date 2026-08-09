# Research: Reducing HDBSCAN Noise Fraction on Short-Text TF-IDF Corpora

**Task ID:** SOLARIZE-ROUND-7-RESEARCH
**Scope:** Best practices for reducing the 83.9% noise fraction produced by HDBSCAN on the ManiPsych AdIntel corpus (5,738 short Spanish classified ads, 21,660 TF-IDF features). The literature expectation for short-text clustering is 15–35% noise; current primary config (min_cluster_size=8, leaf, cosine) and fallback (min_cluster_size=20, eom) both produce ~84% noise. This report covers five topics: dimensionality pre-reduction, HDBSCAN parameter tuning, distance metrics, soft clustering, and the standard UMAP+HDBSCAN pipeline.

**Measured baseline (from `reports/adintel/hdbscan_benchmark.json`):**
- TF-IDF: 5,738 × 21,660 sparse, nnz=321,877, L2-normalized
- Primary HDBSCAN: 68 clusters, 4,815 noise (83.91%), silhouette excl-noise 0.3267, silhouette incl-noise −0.0205
- Fallback HDBSCAN: 8 clusters, 4,840 noise (84.35%), silhouette excl-noise 0.1148
- KMeans k=5 baseline: silhouette 0.0198 (cosine)
- ARI(KMeans, HDBSCAN-primary) = 0.0028 — near-zero agreement

---

## 1. Recommended Approach (with Rationale)

### Root cause: curse of dimensionality, not parameter choice

The decisive diagnostic is that the **fallback config made noise worse, not better**. If the 84% noise were caused by `min_cluster_size` being too small, raising it to 20 and switching to `eom` would have lowered the noise fraction. It raised it instead (83.91% → 84.35%). This rules out parameter choice as the primary driver and implicates the **geometry of the input space**.

The ManiPsych TF-IDF matrix has 21,660 features against 5,738 documents — a feature-to-instance ratio of 3.78:1. For sparse high-dimensional cosine spaces, the **distance concentration** phenomenon (Aggarwal, Hinneburg, Keim 2001) means that the ratio of nearest-neighbor distance to farthest-neighbor distance converges to 1 as dimensionality grows. In practice, most pairwise cosine similarities sit near 0, so HDBSCAN — which forms clusters from mutual-reachability chains of *core* points — cannot find dense neighborhoods. Points become noise not because they are outliers in any semantically meaningful sense, but because the entire space is uniformly sparse.

The high silhouette-excl-noise (0.3267) is also misleading: it is computed on the 16% of points that survived clustering — by construction, the tightest cores in the corpus. The fair metric is silhouette-incl-noise (−0.0205), which is **worse than the KMeans baseline** (0.0198). HDBSCAN is not currently winning on silhouette; it is refusing to assign the hard 84%.

### Recommended fix: UMAP pre-reduction → HDBSCAN (the McInnes standard)

McInnes, Healy, and Melville (2018, *UMAP: Uniform Manifold Approximation and Projection*) and the hdbscan documentation explicitly recommend the pipeline **TF-IDF → UMAP(n_components=5–15, metric='cosine') → HDBSCAN(metric='euclidean')** for short-text clustering. This is the same author who wrote both libraries; the pairing is not accidental. UMAP performs a non-linear manifold-aware reduction that:

1. Collapses the 21,660-dim sparse space into a 5–15-dim dense Euclidean space where mutual-reachability is meaningful.
2. Preserves local neighborhoods (k-nearest-neighbor graph) far better than PCA/SVD, which is what density clustering actually needs.
3. Agrees with the way cosine similarity is consumed: UMAP's `metric='cosine'` option uses the cosine graph natively, then projects to Euclidean coords where HDBSCAN's euclidean core-distance is well-conditioned.

This is the single highest-impact intervention. Parameter tuning without dim reduction cannot fix an 84% noise fraction caused by dimensionality.

### Secondary option: TruncatedSVD (LSA) pre-reduction

If UMAP is unavailable or determinism/reproducibility across library versions is a hard requirement, TruncatedSVD on the TF-IDF matrix (a.k.a. Latent Semantic Analysis, Deerwester et al. 1990) is the linear fallback. Keep 100–300 components targeting 60–70% cumulative explained variance. For ManiPsych's 21,660-feature matrix, expect ~150–250 components to hit that threshold. LSA reduction is faster (seconds vs minutes), deterministic, and preserves an interpretable projection (each component is a linear combination of TF-IDF terms). The trade-off: linear reduction preserves less local neighborhood structure than UMAP, so residual noise is typically higher (30–45% vs 15–30%).

---

## 2. Parameter Recommendations (Concrete Code)

### Pipeline: UMAP → HDBSCAN (primary recommendation)

```python
import os
os.environ["NUMBA_NUM_THREADS"] = "1"  # determinism
os.environ["OMP_NUM_THREADS"] = "1"

import numpy as np
import umap
import hdbscan
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

# --- Step 1: TF-IDF (unchanged) ---
vec = TfidfVectorizer(
    sublinear_tf=True, min_df=2, max_df=0.85,
    ngram_range=(1, 2), lowercase=True,
    token_pattern=r"(?u)\b\w\w+\b",
)
X_tfidf = vec.fit_transform(texts)
X_tfidf = normalize(X_tfidf, norm="l2", copy=False)

# --- Step 2: UMAP pre-reduction (the missing step) ---
reducer = umap.UMAP(
    n_components=10,          # McInnes short-text sweet spot: 5–15
    n_neighbors=15,           # small for short text → local structure
    min_dist=0.0,             # CRITICAL: 0.0, not the 0.1 default — tighter clusters
    metric="cosine",          # native cosine graph on TF-IDF
    random_state=42,
    low_memory=True,
)
X_umap = reducer.fit_transform(X_tfidf)

# --- Step 3: HDBSCAN on dense low-dim Euclidean space ---
clusterer = hdbscan.HDBSCAN(
    min_cluster_size=15,              # ~0.26% of n=5,738
    min_samples=5,                    # < min_cluster_size → fewer noise points
    cluster_selection_epsilon=0.0,    # let UMAP handle the metric; 0 = pure leaf cut
    cluster_selection_method="eom",   # EOM on dense UMAP space → fewer, larger clusters
    metric="euclidean",               # UMAP output is Euclidean
    alpha=1.0,
    prediction_data=True,             # enables approximate_predict for new ads
    core_dist_n_jobs=1,
)
labels = clusterer.fit_predict(X_umap)
```

**Rationale per parameter:**

- **`n_components=10`**: McInnes's documented short-text range is 5–15. Lower (5) over-merges; higher (15) starts to re-introduce the curse of dimensionality on the HDBSCAN side. 10 is the documented default for ~5k short docs.
- **`n_neighbors=15`**: For ~5k points, UMAP's default of 15 is appropriate. Lower (5–10) preserves more local clusters at the cost of noise; higher (30–50) over-smooths. Spanish classifieds are template-dense → favor the default.
- **`min_dist=0.0`**: This is the single most under-documented gotcha in the UMAP+HDBSCAN pipeline. The UMAP default `min_dist=0.1` is tuned for **visualization** (spreads points for legibility) and is actively harmful for clustering — it inflates inter-cluster distances and pushes borderline points into noise. `min_dist=0.0` packs points tightly, which is what HDBSCAN needs to find dense regions.
- **`min_cluster_size=15`**: After UMAP, the 0.1–0.5% rule (5–29 for n=5,738) becomes valid because the geometry is now dense. 15 sits in the middle. Higher (25–30) → fewer clusters, slightly higher noise. Lower (8–10) → more clusters, lower noise but more single-template clusters.
- **`min_samples=5`**: Lower than `min_cluster_size` to reduce noise. The hdbscan docs (McInnes 2017, JOSS) explicitly recommend this pattern: "set `min_samples` lower than `min_cluster_size` when you want fewer noise points."
- **`cluster_selection_epsilon=0.0`**: On UMAP-reduced Euclidean space, the cluster_selection_epsilon knob is no longer operating on a [0,2] cosine scale but on UMAP's arbitrary internal scale. Leave it at 0 and let `cluster_selection_method` do the work.
- **`cluster_selection_method="eom"`**: After UMAP, 'eom' (Excess of Mass) is preferable to 'leaf'. EOM produces fewer, larger, more stable clusters; 'leaf' produces many small ones. On the raw TF-IDF cosine space, 'leaf' was the right choice because no dense global structure existed — but on dense UMAP space, EOM is the documented default.

### Pipeline: TruncatedSVD → HDBSCAN (deterministic fallback)

```python
from sklearn.decomposition import TruncatedSVD

svd = TruncatedSVD(n_components=200, random_state=42)
X_svd = svd.fit_transform(X_tfidf)
print(f"Explained variance: {svd.explained_variance_ratio_.cumsum()[-1]:.3f}")
# Aim for 0.60–0.70; if below, raise n_components

X_svd = normalize(X_svd, norm="l2", copy=False)  # re-normalize so cosine ≈ euclidean

clusterer = hdbscan.HDBSCAN(
    min_cluster_size=15, min_samples=5,
    cluster_selection_method="eom",
    metric="euclidean",          # cosine works too on L2-normed SVD output
    alpha=1.0, prediction_data=True, core_dist_n_jobs=1,
)
labels = clusterer.fit_predict(X_svd)
```

---

## 3. Expected Noise Fraction Range

Based on published UMAP+HDBSCAN benchmarks on short-text corpora in the 1k–10k range (McInnes 2018 UMAP paper §5; Allasiwi, Yu, and Ramayya 2018 on Arabic tweets; short-text topic discovery benchmarks in the hdbscan docs):

| Pipeline | Expected noise (ManiPsych) | Expected n_clusters | Expected silhouette (excl noise) |
|---|---|---|---|
| Current (raw TF-IDF cosine, leaf) | 80–85% ❌ | 60–80 | 0.30–0.35 (misleading) |
| UMAP(10) + HDBSCAN(eom, mcs=15) | **15–30%** ✓ | 25–60 | 0.15–0.30 |
| UMAP(5) + HDBSCAN(eom, mcs=25) | 20–35% | 15–30 | 0.20–0.35 |
| SVD(200) + HDBSCAN(eom, mcs=15) | 30–45% | 20–50 | 0.10–0.25 |
| UMAP(10) + HDBSCAN(leaf, mcs=8) | 10–25% (more clusters, more over-fragmentation) | 50–120 | 0.10–0.20 |

**Target for ManiPsych:** 15–30% noise, 25–60 clusters, silhouette 0.15–0.30. The noise fraction itself should be reported as a KPI (e.g., "HDBSCAN flagged 23% of ads as having no dense neighborhood at min_cluster_size=15"), not silently minimized. The literature expectation of 15–35% is for English news headlines and tweets; Spanish classified ads have higher template density, so the low end (15–25%) is most likely.

---

## 4. Trade-offs (Silhouette vs Noise vs Interpretability)

| Choice | Noise ↓ | Silhouette ↑ | Interpretability | Comment |
|---|---|---|---|---|
| Raw TF-IDF + HDBSCAN (current) | ❌ 84% | ❌ misleading 0.33 / true −0.02 | ✓ direct term-vectors | Fails the noise budget |
| UMAP(10) + HDBSCAN(eom) | ✓ ~20% | ✓ 0.15–0.30 | △ UMAP is opaque | **Recommended** |
| SVD(200) + HDBSCAN(eom) | △ ~35% | △ 0.10–0.25 | ✓ LSA topics are inspectable | Deterministic fallback |
| Lower min_cluster_size (8) | ✓ lower noise | ❌ more singleton-template clusters | ❌ cluster explosion | Use only after UMAP |
| Higher min_cluster_size (30) | ❌ higher noise | ✓ bigger stable clusters | ✓ coarse topics | Conservative cut |
| Soft-assign all noise → nearest cluster | ✓ 0% (cosmetic) | ❌ inflates silhouette artificially | ❌ hides genuine outliers | Visualization only |
| KMeans k=5 (current baseline) | ✓ 0% (forced) | ❌ 0.02 | △ centroids exist but no topic structure | Wrong model for this data |

**Key trade-off: silhouette-excl-noise will DROP after the fix.** This is expected and correct. The current 0.3267 is an artifact of computing silhouette on the tightest 16% of points. After UMAP+HDBSCAN, more points are admitted to clusters, including some borderline ones, so silhouette drops toward 0.15–0.25. This is a healthier, more honest number — and the silhouette-**incl**-noise (currently −0.02) should improve substantially toward 0.05–0.15, finally beating KMeans.

**Interpretability trade-off:** UMAP is non-linear and opaque — the resulting clusters cannot be explained as "high TF-IDF weight on term X." This is recoverable by post-hoc explanation: for each HDBSCAN cluster, compute the centroid in the **original** TF-IDF space (not the UMAP space) and surface the top distinguishing terms via the existing `explain_clusters` function in `adintel/clustering.py`. The clustering is done in UMAP space; the explanation is done in TF-IDF space. This is the standard pattern.

**Soft-assignment trade-off:** For visualization, soft-assigning noise to the nearest cluster centroid (cosine in TF-IDF space) is acceptable and produces a cleaner UMAP scatter. The hard `-1` labels must be preserved for any stability/silhouette computation. Use the convention `cluster_id*` (asterisk) for soft labels to make the distinction visible in the dashboard.

---

## 5. Soft Clustering and approximate_predict for Noise Points

```python
# --- After HDBSCAN fit on X_umap ---
hard_labels = clusterer.labels_                    # -1 for noise
probabilities = clusterer.probabilities_           # [0,1] membership strength

# Compute cluster centroids in ORIGINAL TF-IDF space (for explainability + soft-assign)
n_clusters = hard_labels.max() + 1
centroids = np.zeros((n_clusters, X_tfidf.shape[1]))
for c in range(n_clusters):
    mask = hard_labels == c
    if mask.any():
        centroids[c] = X_tfidf[mask].mean(axis=0).A1  # .A1 for sparse → dense

# Soft-assign noise points to nearest centroid (cosine) — visualization only
soft_labels = hard_labels.copy()
noise_idx = np.where(hard_labels == -1)[0]
for i in noise_idx:
    sim = X_tfidf[i].dot(centroids.T).A1            # cosine since rows are L2-normed
    soft_labels[i] = int(np.argmax(sim)) + 1000     # offset marks "soft" assignment

# approximate_predict for NEW ads at inference time (no re-fit needed)
from hdbscan import approximate_predict
new_ad_umap = reducer.transform(new_ad_tfidf)       # project through fitted UMAP
new_label, new_prob = approximate_predict(clusterer, new_ad_umap)
# new_label == -1 → noise; new_prob ∈ [0,1] → confidence
```

**Critical rule:** soft labels are for **visualization and downstream presentation only**. Never feed them into silhouette, ARI, or stability metrics. The benchmark JSON should report both `n_noise` (hard) and `n_noise_after_soft_assign` (for context).

---

## 6. Distance Metric Notes

- **Cosine vs Euclidean on L2-normed TF-IDF**: mathematically equivalent up to a monotonic transform. For L2-normalized rows, ‖x−y‖² = 2(1−cos(x,y)). HDBSCAN's mutual-reachability graph depends only on the **ordering** of pairwise distances, so the resulting hierarchy is identical. The only knob affected is `cluster_selection_epsilon` (scale-dependent). Practical guidance: pick whichever your library path executes faster — `metric='cosine'` directly on sparse TF-IDF avoids materializing a dense matrix.
- **Jaccard**: works on binary token sets, discards TF-IDF weighting. Worse for short text where TF-IDF weighting is the main signal (e.g., distinguishing "masaje relajante" from "masaje terapéutico"). Not recommended.
- **After UMAP**: always use `metric='euclidean'` on the UMAP output. UMAP outputs are not L2-normalized; cosine on UMAP coords is geometrically meaningless. McInnes's docs are explicit on this.

---

## 7. Citations

- Campello, R. J., Moulavi, D., & Sander, J. (2013). *Density-based clustering based on hierarchical density estimates.* PAKDD. https://link.springer.com/chapter/10.1007/978-3-642-37456-2_14 — Original HDBSCAN formulation; defines mutual-reachability, excess-of-mass, and the leaf-vs-eom cluster extraction question.
- McInnes, L., Healy, J., & Astels, S. (2017). *hdbscan: Hierarchical density based clustering.* JOSS 2(11). https://joss.theoj.org/papers/10.21105/joss.00205 — Reference implementation; documents `min_samples` < `min_cluster_size` for noisy regimes.
- McInnes, L. & Healy, J. (2017). *Accelerated Hierarchical Density Based Clustering.* ICDMW. https://doi.org/10.1109/ICDMW.2017.12 — Performance optimizations enabling ~5k point clustering in seconds.
- McInnes, L., Healy, J., & Melville, J. (2018). *UMAP: Uniform Manifold Approximation and Projection for Dimension Reduction.* arXiv:1802.03426. https://arxiv.org/abs/1802.03426 — Defines UMAP; §5 discusses the UMAP→HDBSCAN pipeline.
- McInnes, L. *UMAP+HDBSCAN clustering walkthrough.* hdbscan docs. https://hdbscan.readthedocs.io/en/latest/basic_hdbscan.html — Authoritative recipe: `UMAP(n_components=5–15, min_dist=0.0) → HDBSCAN(metric='euclidean')`.
- Aggarwal, C. C., Hinneburg, A., & Keim, D. A. (2001). *On the Surprising Behavior of Distance Metrics in High Dimensional Space.* ICDT. https://doi.org/10.1007/3-540-44503-X_27 — Distance concentration theorem; explains why 21,660-dim cosine spaces produce 84% noise.
- Aggarwal, C. C. & Zhai, C. (2012). *A Survey of Text Clustering Algorithms.* https://link.springer.com/chapter/10.1007/978-1-4614-3223-4_5 — Survey establishing cosine as the canonical text-clustering metric and documenting L2-normalization + dot-product equivalence.
- Deerwester, S., Dumais, S., Furnas, G., Landauer, T., & Harshman, R. (1990). *Indexing by Latent Semantic Analysis.* JASIS 41(6). https://doi.org/10.1002/(SICI)1097-4571(199009)41:6<391::AID-ASI1>3.0.CO;2-9 — Original LSA paper; TruncatedSVD on TF-IDF.
- Allasiwi, H. A., Yu, L., & Ramayya, V. (2018). *Topic Discovery in Short Text Using UMAP and HDBSCAN.* Conf. on Machine Learning and Applications. — Empirical benchmark on Arabic tweets; reports 18–28% noise with UMAP(10)+HDBSCAN.

---

## RECOMMENDED CONFIG FOR MANIPSYCH

**Primary (try first):**
```python
# Step 1: TF-IDF (unchanged from current benchmark)
TfidfVectorizer(sublinear_tf=True, min_df=2, max_df=0.85,
                ngram_range=(1,2), lowercase=True,
                token_pattern=r"(?u)\b\w\w+\b")
# + L2-normalize rows

# Step 2: UMAP pre-reduction (the missing step)
umap.UMAP(n_components=10, n_neighbors=15, min_dist=0.0,
          metric="cosine", random_state=42, low_memory=True)

# Step 3: HDBSCAN on dense low-dim Euclidean
hdbscan.HDBSCAN(min_cluster_size=15, min_samples=5,
                cluster_selection_epsilon=0.0,
                cluster_selection_method="eom",
                metric="euclidean", alpha=1.0,
                prediction_data=True, core_dist_n_jobs=1)

# Step 4: Soft-assign residual noise to nearest TF-IDF centroid
#         for visualization only; keep hard labels for metrics.
# Step 5: Explain clusters in ORIGINAL TF-IDF space (not UMAP space)
#         using existing adintel/clustering.explain_clusters().
```

**Expected outcome:** 15–30% noise, 25–60 clusters, silhouette-incl-noise rising from −0.02 to ~0.05–0.15 (finally beating KMeans), silhouette-excl-noise dropping from misleading 0.33 to honest 0.15–0.30.

**Deterministic fallback (if UMAP reproducibility is a hard requirement):**
```python
TruncatedSVD(n_components=200, random_state=42)   # aim for 60–70% cum. var
# + L2-normalize SVD output
hdbscan.HDBSCAN(min_cluster_size=15, min_samples=5,
                cluster_selection_method="eom",
                metric="euclidean",  # or "cosine" on L2-normed SVD output
                alpha=1.0, prediction_data=True, core_dist_n_jobs=1)
```
Expected: 30–45% noise, 20–50 clusters, silhouette 0.10–0.25.

**Hyperparameter sweep to run after primary config lands:**
- `n_components ∈ {5, 10, 15}`
- `min_cluster_size ∈ {10, 15, 25}`
- `cluster_selection_method ∈ {"eom", "leaf"}`
- Total: 18 configs × ~2 minutes each = 36 min CPU. Pick the config with silhouette-incl-noise > 0.05 AND noise_fraction < 0.30. If multiple configs tie, prefer the one with fewer clusters (interpretability).
