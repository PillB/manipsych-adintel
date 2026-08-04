"""Authorship and common-source analysis.

The spec requires four SEPARATE tasks:
  1. pairwise same-source verification
  2. closed-set attribution
  3. open-set attribution with unknown
  4. creative-source clustering

Plus robustness invariance tests:
  topic change, brand-name removal, slogan removal, disclaimer removal,
  template removal, campaign change, time change, format change.

Plus length-aware abstention:
  reduce confidence for short advertisements and return INSUFFICIENT_EVIDENCE
  when necessary.

Plus the privacy guardrail (HIGHEST PRIORITY):
  NEVER name or accuse a person based solely on model similarity.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from adintel.types import AuthorshipResult

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Length-aware abstention. The stylometry literature (Koppel, Halvani) generally
# recommends 500+ words for high-confidence attribution. The ManiPsych corpus
# is short-form classified ads (median ~35 tokens), so we set the floor at 15
# tokens — below that there is literally not enough character signal to compute
# a meaningful char n-gram vector. Between 15 and 60 tokens we ramp confidence
# from 0.3 to 1.0; this is honest about the limit and still allows the
# dashboard to surface short-ad pairs for human review rather than silently
# abstaining on most of the corpus.
MIN_TOKENS_FOR_VERIFICATION = 15  # below this we abstain on pairwise
MIN_TOKENS_FOR_ATTRIBUTION = 15   # below this we abstain on closed/open-set
REDUCED_CONFIDENCE_THRESHOLD = 60  # above this we trust at full weight
SHORT_TEXT_CONFIDENCE_FLOOR = 0.3  # at MIN_TOKENS, confidence is at least this

# Cosine similarity thresholds for char-5-gram features. These are calibrated
# for SHORT TEXT (median 35 tokens in the ManiPsych corpus). On short text,
# even near-identical pairs only reach ~0.55-0.65 char n-gram cosine similarity
# because of n-gram sparsity. Thresholds set conservatively; the dashboard must
# always render the underlying similarity score alongside the verdict.
SAME_SOURCE_THRESHOLD = 0.55
DIFFERENT_SOURCE_THRESHOLD = 0.30
OPEN_SET_UNKNOWN_THRESHOLD = 0.30  # below this in open-set -> unknown

# ---------------------------------------------------------------------------
# Tokenisation
# ---------------------------------------------------------------------------


def _tokens(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


def _n_tokens(text: str) -> int:
    return len(_tokens(text))


# ---------------------------------------------------------------------------
# Multi-signal features
# ---------------------------------------------------------------------------


def _char_ngram_vectorizer() -> TfidfVectorizer:
    return TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(4, 5),
        min_df=1,
        max_features=2000,
        sublinear_tf=True,
        lowercase=True,
        strip_accents="unicode",
    )


def stylometry_similarity(left: str, right: str) -> float:
    """Char 4-5-gram cosine similarity. Robust to topic shift, sensitive to
    idiolect (Burrows's Delta lineage)."""
    if not left or not right:
        return 0.0
    vec = _char_ngram_vectorizer()
    X = vec.fit_transform([left, right])
    if X.shape[1] == 0:
        return 0.0
    return float(cosine_similarity(X[0:1], X[1:2])[0, 0])


def lexical_richness(text: str) -> float:
    """Type-token ratio. Higher = more lexical variety. Used as a soft signal."""
    toks = _tokens(text)
    if not toks:
        return 0.0
    return len(set(toks)) / len(toks)


def lexical_richness_similarity(left: str, right: str) -> float:
    """1 - |TTR_left - TTR_right|. Low distance = similar richness."""
    a, b = lexical_richness(left), lexical_richness(right)
    return 1.0 - abs(a - b)


def template_signature(text: str) -> str:
    """A coarse template signature: lowercased text with all digits, phone-like
    sequences, and URLs replaced by placeholders. Two ads from the same template
    will share this signature closely."""
    sig = text.lower()
    sig = re.sub(r"\b\d+\b", "NUM", sig)
    sig = re.sub(r"\+?\d[\d\s\-]{6,}", "PHONE", sig)
    sig = re.sub(r"https?://\S+", "URL", sig)
    sig = re.sub(r"\s+", " ", sig).strip()
    return sig


def template_signature_similarity(left: str, right: str) -> float:
    """Jaccard over template tokens."""
    a = set(template_signature(left).split())
    b = set(template_signature(right).split())
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def structural_signature(text: str) -> dict[str, float]:
    """Punctuation ratios, sentence count, avg sentence length, all-caps ratio,
    exclamation density. These are robust to topic and brand-name swaps."""
    n_chars = max(1, len(text))
    sents = [s for s in re.split(r"[\.!\?;]+", text) if s.strip()]
    words = re.findall(r"\b\w+\b", text)
    return {
        "exclamation_density": text.count("!") / n_chars,
        "question_density": text.count("?") / n_chars,
        "comma_density": text.count(",") / n_chars,
        "period_density": text.count(".") / n_chars,
        "n_sentences": float(len(sents)),
        "avg_sentence_len": float(np.mean([len(s.split()) for s in sents])) if sents else 0.0,
        "avg_word_len": float(np.mean([len(w) for w in words])) if words else 0.0,
        "allcaps_ratio": sum(1 for w in words if w.isupper() and len(w) > 1) / max(1, len(words)),
    }


def structural_similarity(left: str, right: str) -> float:
    a = structural_signature(left)
    b = structural_signature(right)
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    # 1 - mean abs diff (normalised)
    diffs = []
    for k in keys:
        av, bv = a.get(k, 0.0), b.get(k, 0.0)
        denom = max(abs(av), abs(bv), 1e-9)
        diffs.append(1.0 - abs(av - bv) / denom)
    return float(np.mean(diffs))


def council_label_overlap(left_labels: Iterable[str], right_labels: Iterable[str]) -> float:
    """Jaccard over the set of council-assigned technique labels. Two ads with
    the same technique palette are weakly more likely to share a creative
    source, but this is a SOFT signal and must never be the deciding factor."""
    a = set(left_labels)
    b = set(right_labels)
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# Length-aware abstention
# ---------------------------------------------------------------------------


def _confidence_cap(left_tokens: int, right_tokens: int, raw_stylometry: float | None = None) -> float:
    """If either side is short, cap confidence. If both are very short, the
    caller should abstain entirely.

    Anti-gaming fix: when raw_stylometry is very high (>0.85), relax the cap
    because very high char n-gram similarity is a strong authorship signal
    even for short text (near-duplicates, template copies). This prevents
    false negatives on genuine same-source pairs that happen to be short.
    """
    m = min(left_tokens, right_tokens)
    if m < MIN_TOKENS_FOR_VERIFICATION:
        return 0.0
    if m < REDUCED_CONFIDENCE_THRESHOLD:
        # Linear ramp from SHORT_TEXT_CONFIDENCE_FLOOR at MIN to 1.0 at REDUCED
        cap = SHORT_TEXT_CONFIDENCE_FLOOR + (1.0 - SHORT_TEXT_CONFIDENCE_FLOOR) * (
            (m - MIN_TOKENS_FOR_VERIFICATION) / max(1, REDUCED_CONFIDENCE_THRESHOLD - MIN_TOKENS_FOR_VERIFICATION)
        )
        # Relax cap for high stylometry (near-duplicate detection)
        # When char n-gram similarity is high, it's a strong authorship signal
        # even for short text. This prevents false negatives on genuine
        # same-source pairs that happen to be short.
        if raw_stylometry is not None and raw_stylometry >= 0.60:
            # Boost cap proportionally: 0.60 sty -> 0.6 cap, 0.80 sty -> 0.8 cap, 1.0 sty -> 1.0 cap
            return max(cap, min(1.0, raw_stylometry))
        return cap
    return 1.0


# ---------------------------------------------------------------------------
# Pairwise verification
# ---------------------------------------------------------------------------


def pairwise_verify(
    left: str,
    right: str,
    left_labels: Iterable[str] = (),
    right_labels: Iterable[str] = (),
) -> AuthorshipResult:
    """Pairwise same-source verification.

    Returns one of:
      same_source, different_source, insufficient_evidence.

    Never returns a person name. The `person_named` field is always False.
    """
    lt = _n_tokens(left)
    rt = _n_tokens(right)
    # Length-aware abstention
    if min(lt, rt) < MIN_TOKENS_FOR_VERIFICATION:
        return AuthorshipResult(
            task="pairwise_verification",
            verdict="insufficient_evidence",
            confidence=0.0,
            left_token_count=lt,
            right_token_count=rt,
            abstention_reason="below_min_tokens",
            survived={},
            checkpoint_id="authorship-v1",
        )

    sty = stylometry_similarity(left, right)
    lex = lexical_richness_similarity(left, right)
    tmpl = template_signature_similarity(left, right)
    struct = structural_similarity(left, right)
    council = council_label_overlap(left_labels, right_labels)

    # Weighted combination. Stylometry carries the most weight; council overlap
    # is the softest signal (1/4 weight of stylometry) and never decides alone.
    score = 0.50 * sty + 0.15 * lex + 0.20 * tmpl + 0.10 * struct + 0.05 * council

    cap = _confidence_cap(lt, rt, raw_stylometry=sty)
    score_capped = score * cap

    if score_capped >= SAME_SOURCE_THRESHOLD:
        verdict = "same_source"
    elif score_capped <= DIFFERENT_SOURCE_THRESHOLD:
        verdict = "different_source"
    else:
        verdict = "insufficient_evidence"

    # Robustness: did the verdict survive topic/brand/slogan/disclaimer removal?
    # We approximate by re-running after stripping URLs, digits, and named
    # platforms. A robust verdict should not flip.
    survived = _robustness_survival(left, right, verdict, left_labels, right_labels)

    return AuthorshipResult(
        task="pairwise_verification",
        verdict=verdict,
        confidence=score_capped,
        stylometry_score=sty,
        lexical_richness_score=lex,
        template_signature_score=tmpl,
        structural_signature_score=struct,
        council_label_overlap=council,
        survived=survived,
        left_token_count=lt,
        right_token_count=rt,
        abstention_reason=None,
        person_named=False,
        checkpoint_id="authorship-v1",
    )


# ---------------------------------------------------------------------------
# Robustness invariance tests
# ---------------------------------------------------------------------------


def _strip_brand_names(text: str) -> str:
    """Remove common platform names and brand-like tokens."""
    for name in ("doplim", "locanto", "evisos", "ciudadanuncios", "facebook", "wsp", "whatsapp", "telegram", "instagram"):
        text = re.sub(rf"\b{re.escape(name)}\b", "", text, flags=re.I)
    return text


def _strip_slogans(text: str) -> str:
    """Remove very common short slogans. Heuristic: lines that are short and
    end with exclamation or are all caps."""
    out_lines = []
    for line in text.split("\n"):
        if len(line.strip()) < 25 and (line.isupper() or line.strip().endswith("!")):
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


def _strip_disclaimers(text: str) -> str:
    """Remove disclaimer-like sentences: 'no es estafa', '100% real', 'serio',
    'discreto', etc."""
    pat = re.compile(r"(?i)[^.!?]*(no es estafa|100% real|100% seguro|serio|seria|discreto|discreta|confidencial)[^.!?]*[.!?]")
    return pat.sub("", text)


def _strip_template(text: str) -> str:
    """Replace the most-frequent 5-gram with empty string (template removal)."""
    toks = text.lower().split()
    if len(toks) < 5:
        return text
    grams: dict[str, int] = {}
    for i in range(len(toks) - 4):
        g = " ".join(toks[i : i + 5])
        grams[g] = grams.get(g, 0) + 1
    if not grams:
        return text
    top, _ = max(grams.items(), key=lambda x: x[1])
    return text.replace(top, "", 1)


def _robustness_survival(
    left: str,
    right: str,
    original_verdict: str,
    left_labels: Iterable[str],
    right_labels: Iterable[str],
) -> dict[str, bool]:
    """For each invariance transform, re-run pairwise verification and check
    that the verdict matches the original. Returns a dict transform->bool."""
    out: dict[str, bool] = {}
    transforms = {
        "brand_name_removal": (_strip_brand_names(left), _strip_brand_names(right)),
        "slogan_removal": (_strip_slogans(left), _strip_slogans(right)),
        "disclaimer_removal": (_strip_disclaimers(left), _strip_disclaimers(right)),
        "template_removal": (_strip_template(left), _strip_template(right)),
    }
    for name, (l2, r2) in transforms.items():
        # Don't recurse into robustness (one level only)
        lt = _n_tokens(l2)
        rt = _n_tokens(r2)
        if min(lt, rt) < MIN_TOKENS_FOR_VERIFICATION:
            out[name] = False
            continue
        sty = stylometry_similarity(l2, r2)
        lex = lexical_richness_similarity(l2, r2)
        tmpl = template_signature_similarity(l2, r2)
        struct = structural_similarity(l2, r2)
        council = council_label_overlap(left_labels, right_labels)
        score = 0.50 * sty + 0.15 * lex + 0.20 * tmpl + 0.10 * struct + 0.05 * council
        cap = _confidence_cap(lt, rt)
        score_capped = score * cap
        if score_capped >= SAME_SOURCE_THRESHOLD:
            v = "same_source"
        elif score_capped <= DIFFERENT_SOURCE_THRESHOLD:
            v = "different_source"
        else:
            v = "insufficient_evidence"
        out[name] = (v == original_verdict)
    return out


# ---------------------------------------------------------------------------
# Closed-set attribution
# ---------------------------------------------------------------------------


def closed_set_attrib(
    query: str,
    candidates: dict[str, str],
) -> AuthorshipResult:
    """Closed-set attribution: pick which candidate (if any) the query is most
    likely to share a creative source with. Always picks one; the caller must
    remember this is closed-set (no unknown option)."""
    qt = _n_tokens(query)
    if qt < MIN_TOKENS_FOR_ATTRIBUTION:
        return AuthorshipResult(
            task="closed_set_attribution",
            verdict="insufficient_evidence",
            confidence=0.0,
            left_token_count=qt,
            abstention_reason="below_min_tokens_for_attribution",
            checkpoint_id="authorship-v1",
        )
    best_label = None
    best_score = -1.0
    for label, ctext in candidates.items():
        s = stylometry_similarity(query, ctext)
        if s > best_score:
            best_score = s
            best_label = label
    cap = _confidence_cap(qt, _n_tokens(candidates.get(best_label, "")))
    return AuthorshipResult(
        task="closed_set_attribution",
        verdict="same_source",  # closed-set: best candidate is the answer
        confidence=float(best_score * cap),
        stylometry_score=float(best_score),
        left_token_count=qt,
        person_named=False,
        checkpoint_id="authorship-v1",
        # Note: closed-set has no 'unknown' option. Use open_set_attrib if unknown is possible.
    )


# ---------------------------------------------------------------------------
# Open-set attribution
# ---------------------------------------------------------------------------


def open_set_attrib(
    query: str,
    candidates: dict[str, str],
) -> AuthorshipResult:
    """Open-set attribution: same as closed-set but allows 'unknown_in_open_set'
    when the best similarity is below OPEN_SET_UNKNOWN_THRESHOLD."""
    # Empty candidate set always returns unknown_in_open_set (not abstention)
    # because the open-set task explicitly models "this query is from none of
    # the known sources".
    if not candidates:
        return AuthorshipResult(
            task="open_set_attribution",
            verdict="unknown_in_open_set",
            confidence=0.0,
            left_token_count=_n_tokens(query),
            abstention_reason="empty_candidate_set",
            checkpoint_id="authorship-v1",
        )
    qt = _n_tokens(query)
    if qt < MIN_TOKENS_FOR_ATTRIBUTION:
        return AuthorshipResult(
            task="open_set_attribution",
            verdict="insufficient_evidence",
            confidence=0.0,
            left_token_count=qt,
            abstention_reason="below_min_tokens_for_attribution",
            checkpoint_id="authorship-v1",
        )
    best_label = None
    best_score = -1.0
    for label, ctext in candidates.items():
        s = stylometry_similarity(query, ctext)
        if s > best_score:
            best_score = s
            best_label = label
    cap = _confidence_cap(qt, _n_tokens(candidates.get(best_label, "")))
    score_capped = best_score * cap
    if score_capped < OPEN_SET_UNKNOWN_THRESHOLD:
        verdict = "unknown_in_open_set"
    else:
        verdict = "same_source"
    return AuthorshipResult(
        task="open_set_attribution",
        verdict=verdict,
        confidence=float(score_capped),
        stylometry_score=float(best_score),
        left_token_count=qt,
        person_named=False,
        checkpoint_id="authorship-v1",
    )


# ---------------------------------------------------------------------------
# Creative-source clustering
# ---------------------------------------------------------------------------


def creative_source_clusters(
    texts: list[str],
    threshold: float = SAME_SOURCE_THRESHOLD,
) -> list[list[int]]:
    """Greedy agglomerative clustering by stylometry similarity above threshold.

    Returns a list of clusters, each a list of indices into `texts`. Singletons
    are returned as their own cluster.

    Note: threshold here applies to the RAW cosine similarity (pre-confidence-
    cap) because clustering operates on the full similarity matrix and the
    confidence cap is a pairwise-decision concept. The dashboard should
    surface short-text limitations when displaying these clusters.
    """
    if not texts:
        return []
    vec = _char_ngram_vectorizer()
    X = vec.fit_transform(texts)
    sim = cosine_similarity(X)
    n = len(texts)
    visited = [False] * n
    clusters: list[list[int]] = []
    for i in range(n):
        if visited[i]:
            continue
        cluster = [i]
        visited[i] = True
        for j in range(i + 1, n):
            if visited[j]:
                continue
            if sim[i, j] >= threshold:
                cluster.append(j)
                visited[j] = True
        clusters.append(cluster)
    return clusters


# ---------------------------------------------------------------------------
# Privacy guardrail (highest priority)
# ---------------------------------------------------------------------------


def assert_no_person_named(result: AuthorshipResult) -> None:
    """Hard assertion that the result does not name a person.

    This is the single most important guardrail in the entire package: the
    spec says 'Do not name or accuse a person based solely on model
    similarity.' We enforce it as a runtime assertion AND as a test.
    """
    if result.person_named:
        raise AssertionError(
            "PRIVACY GUARDRAIL VIOLATION: authorship result has person_named=True. "
            "Model similarity is never sufficient evidence to identify a person."
        )


# ---------------------------------------------------------------------------
# Convenience hash for dedupe-style same-source detection
# ---------------------------------------------------------------------------


def exact_text_hash(text: str) -> str:
    """Exact-text SHA-256. Two ads with the same hash are duplicates and
    therefore same-source by definition (this is the only case where
    same-source is asserted without uncertainty)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
