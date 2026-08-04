"""17-dimension persuasive-language profile.

The spec lists 17 dimensions explicitly and forbids collapsing them into an
unexplained universal score. This module scores each dimension independently
with a transparent signal inventory, returns both raw and normalised scores,
abstains when signal is insufficient, and exposes a calibration hook.

Dimensions (spec order, do not reorder — dashboards depend on this):
  urgency, scarcity, emotional_intensity, directiveness, certainty,
  specificity, benefit_density, evidence_density, social_proof,
  objection_handling, risk_reversal, claim_extremity, readability,
  offer_clarity, action_clarity, trust_risk, manipulation_risk.

`trust_risk` and `manipulation_risk` are *meta*-dimensions: they score the
risk that the ad is untrustworthy or manipulative, respectively. They are
NOT a sum of the other 15.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable

from adintel.types import (
    PROFILE_DIMENSIONS,
    EvidenceRef,
    PersuasiveProfile,
    ProfileScore,
)
from adintel import taxonomy as tx

PROFILE_TAXONOMY_VERSION = tx.TAXONOMY_VERSION
PROFILE_CHECKPOINT_ID = "persuasive-profile-v1"


# ---------------------------------------------------------------------------
# Signal inventories
# ---------------------------------------------------------------------------
# Each dimension is scored from a list of (regex, weight) signals. Weights are
# transparent and audit-friendly. Scoring is additive with a saturating
# transform; this is a deliberate choice over a learned model because (a) the
# spec demands explainability, (b) labels are weak, (c) the dashboard must be
# able to defend each score with a signal list.

# Spanish-leaning signals because the corpus is Peruvian Spanish; English
# signals are included as fallbacks for cross-lingual robustness tests.

_URGENCY_SIGNALS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\b(urgente|ahora|ya|hoy|inmediato|rápidito|rapidito|ya mismo)\b", re.I), 0.30, "urgency word"),
    (re.compile(r"\b(solo por (hoy|esta noche|esta semana))\b", re.I), 0.25, "limited-time urgency"),
    (re.compile(r"\b(último|última|ultima|ultimos|últimos)\b", re.I), 0.20, "last-chance word"),
    (re.compile(r"\b(no (esperes|tardes|dejes))\b", re.I), 0.20, "imperative urgency"),
    (re.compile(r"\b(today|now|tonight only|last chance|hurry)\b", re.I), 0.20, "english urgency"),
]

_Scarcity_SIGNALS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\b(solo|único|única|unico|unica|limitad|pocos|pocas|un cupo|un lugar)\b", re.I), 0.25, "scarcity word"),
    (re.compile(r"\b(pocas? (vacantes|opciones|chicas?|cupo))\b", re.I), 0.30, "specific scarcity"),
    (re.compile(r"\b(solo\s+\d+)\b", re.I), 0.30, "numeric scarcity"),
    (re.compile(r"\b(limited|only \d+|while (supplies|slots) last)\b", re.I), 0.25, "english scarcity"),
]

_EMOTION_SIGNALS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\b(amor|cariño|cariño|afecto|corazon|corazón|amistad|sincero|sincera)\b", re.I), 0.15, "warmth word"),
    (re.compile(r"\b(triste|sola|solo|deprimida|abandonada|abandonado|necesitad)\b", re.I), 0.30, "vulnerability word"),
    (re.compile(r"\b(miedo|peligro|riesgo|amenaza|inseguridad)\b", re.I), 0.30, "fear word"),
    (re.compile(r"\b(esperanza|sueña|sueño|futuro|mejorar|salir adelante)\b", re.I), 0.20, "hope word"),
    (re.compile(r"\b(verguenza|vergüenza|humillad|culpable|deberías|deberias)\b", re.I), 0.30, "shame word"),
]

_DIRECTIVENESS_SIGNALS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\b(escribeme|escríbeme|escribeme ya|mandame| mándame|llamame|llámame|enviame|envíame)\b", re.I), 0.30, "imperative contact"),
    (re.compile(r"\b(hazlo|hazlo ya|no (esperes|dudes|tardes))\b", re.I), 0.25, "imperative action"),
    (re.compile(r"\b(debes|tienes que|tenés que|no (dejes|pierdas))\b", re.I), 0.25, "obligation modal"),
    (re.compile(r"\b(whatsapp|wsp|telegram|inbox|dm|privado)\b", re.I), 0.20, "channel directive"),
]

_CERTAINTY_SIGNALS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\b(seguro|segura|garantizado|garantizada|100%|cien por ciento|real|verdadero|seguridad)\b", re.I), 0.25, "certainty word"),
    (re.compile(r"\b(comprobado|verificado|avalado|respaldado)\b", re.I), 0.25, "verified claim"),
    (re.compile(r"\b(sin riesgo|sin peligros|confiable|confiable)\b", re.I), 0.20, "no-risk claim"),
    (re.compile(r"\b(tal vez|quizás|quizas|puede ser|a lo mejor|no sé|no se)\b", re.I), -0.15, "hedging (reduces certainty)"),
]

_SPECIFICITY_SIGNALS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\b(\d+)\s*(años|anos|soles|s/|usd|\$)\b", re.I), 0.25, "numeric specificity"),
    (re.compile(r"\b(de\s+\d+\s+a\s+\d+\s+años)\b", re.I), 0.30, "age range"),
    (re.compile(r"\b(lima|arequipa|cusco|trujillo|piura|chiclayo|huancayo|ica|callao)\b", re.I), 0.15, "city named"),
    (re.compile(r"\b(universidad|instituto|colegio|ciclo|semestre)\b", re.I), 0.20, "education-specific"),
]

_BENEFIT_SIGNALS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\b(ayuda economic|ayuda económica|apoyo economic|apoyo económico|dinero|soles|ingreso|ingresos)\b", re.I), 0.25, "financial benefit"),
    (re.compile(r"\b(constante|permanente|semanal|quincenal|mensual|fijo)\b", re.I), 0.25, "regularity benefit"),
    (re.compile(r"\b(libre de deudas|deudas|alquiler|renta|gastos|colegio)\b", re.I), 0.20, "need-coverage benefit"),
    (re.compile(r"\b(regalo|obsequio|gratis|sin costo|de balde)\b", re.I), 0.20, "free-frame benefit"),
]

_EVIDENCE_SIGNALS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\b(referencias|referencia|testimonio|testimonios|reseña|reseñas)\b", re.I), 0.30, "testimonials"),
    (re.compile(r"\b(fotos? (reales|verificadas)|video real|live photo)\b", re.I), 0.25, "verification media"),
    (re.compile(r"\b(cuenta verificada|perfil verificado|badge)\b", re.I), 0.20, "verified badge"),
    (re.compile(r"\b(con\s+\d+\s+(clientes|anos|años|referencias))\b", re.I), 0.25, "track record"),
]

_SOCIAL_PROOF_SIGNALS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\b(muchos|muchas|varios|varias|todos|todas|la mayoría|mayoria)\b", re.I), 0.20, "majority claim"),
    (re.compile(r"\b(recomendad|recomendad[oa]s?|popular|top|favorit[oa])\b", re.I), 0.25, "popularity claim"),
    (re.compile(r"\b(\d+\s+(clientes|chicas|personas|usuarias))\b", re.I), 0.30, "numeric popularity"),
    (re.compile(r"\b(me\s+recomiendan|me\s+recomiendan|ya\s+confían|confian)\b", re.I), 0.25, "trust-by-others"),
]

_OBJECTION_HANDLING_SIGNALS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\b(sin compromiso|sin obligación|sin obligacion|libre de compromisos)\b", re.I), 0.30, "no-commitment"),
    (re.compile(r"\b(discreto|discreta|privado|privada|confidencial|reservad[oa])\b", re.I), 0.20, "discretion-handling"),
    (re.compile(r"\b(no\s+es\s+(estafa|engaño|prostitución)|serio|seria|formal)\b", re.I), 0.30, "anti-scam disclaimer"),
    (re.compile(r"\b(seguro|segura|sin riesgo|confiable|de confianza)\b", re.I), 0.20, "safety-handling"),
]

_RISK_REVERSAL_SIGNALS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\b(garantía|garantia|devolución|devolucion|reembolso|satisfacción|satisfaccion)\b", re.I), 0.30, "guarantee"),
    (re.compile(r"\b(sin riesgo|cero riesgo|100% seguro|100% segura)\b", re.I), 0.25, "no-risk claim"),
    (re.compile(r"\b(prueba gratis|primera vez gratis|sin cobrar|no pagas)\b", re.I), 0.30, "free-trial"),
    (re.compile(r"\b(si no te gusta|si no funciona|si no te convence)\b", re.I), 0.25, "conditional refund"),
]

_CLAIM_EXTREMITY_SIGNALS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\b(el mejor|la mejor|los mejores|las mejores|número 1|numero 1|#1|top 1)\b", re.I), 0.30, "superlative"),
    (re.compile(r"\b(único|única|unico|unica|exclusivo|exclusiva|sin igual|increíble|increible)\b", re.I), 0.20, "exclusivity claim"),
    (re.compile(r"\b(100%|cien por ciento|total|absoluto|absoluta|perfecto|perfecta)\b", re.I), 0.25, "absolute claim"),
    (re.compile(r"\b(siempre|nunca|jamás|jamas|todos|todas|nadie)\b", re.I), 0.20, "universal quantifier"),
    (re.compile(r"\b(resultado asegurado|resultado garantizado|éxito garantizado|exito garantizado)\b", re.I), 0.30, "guaranteed-result claim"),
    (re.compile(r"\b(garantizado|garantizada|asegurado|asegurada|comprobado|verificado)\b", re.I), 0.20, "guarantee adjective"),
]

# Readability is computed differently (Flesch-style Spanish approximation),
# not from keyword signals. We still expose a signal inventory for audit.
_READABILITY_NOTE = "Spanish-adapted Flesch reading-ease; lower score = harder text. Normalised so 1.0 = easiest."


# Offer clarity and action clarity also use structural signals rather than
# keywords. We compute them from sentence / imperative / contact-cue density.

_ACTION_SIGNALS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\b(escribeme|escríbeme|llamame|llámame|enviame|envíame|mandame| mándame|whatsapp|wsp|telegram)\b", re.I), 0.25, "explicit contact verb"),
    (re.compile(r"\b(telefono|teléfono|celular|móvil|movil|numero|número)\b", re.I), 0.15, "contact noun"),
    (re.compile(r"\b(click|enlace|link|url|visita|visitar)\b", re.I), 0.20, "click action"),
]

_OFFER_SIGNALS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\b(ayuda economic|ayuda económica|apoyo economic|apoyo económico|ofrezco|brindo)\b", re.I), 0.25, "offer verb"),
    (re.compile(r"\b(dinero|soles|s/|usd|\$)\b", re.I), 0.15, "currency/amount"),
    (re.compile(r"\b(constante|permanente|semanal|quincenal|mensual|fijo)\b", re.I), 0.20, "regularity term"),
    (re.compile(r"\b(una\s+vez|ocasional|esporádico|esporadico)\b", re.I), 0.15, "frequency term"),
]

# Trust risk and manipulation risk are computed from a weighted combination
# of the other dimensions plus their own red-flag signals. They are NEVER a
# simple sum (per spec).

_TRUST_RISK_REDFLAGS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\b(inversión|inversion|registro|pago previo|pago por adelantado|depósito|deposito)\b", re.I), 0.30, "advance-payment ask"),
    (re.compile(r"\b(no\s+es\s+estafa|serio|seria|100% real|verdadeiro)\b", re.I), 0.20, "defensive 'not a scam' disclaimer"),
    (re.compile(r"\b(whatsapp|wsp|telegram|privado|inbox)\b", re.I), 0.10, "off-platform migration"),
]

_MANIPULATION_RISK_REDFLAGS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\b(necesitad|urgente|no tienes|debes|tienes que|por tu familia|si de verdad)\b", re.I), 0.25, "pressure + vulnerability combo"),
    (re.compile(r"\b(chicas?\s+(de\s+)?(18|19|20)|estudiantes?|alumnas?)\b", re.I), 0.30, "youth targeting cue"),
    (re.compile(r"\b(ayuda\s+económica|ayuda economica)\b", re.I), 0.10, "transactional euphemism"),
    (re.compile(r"\b(buena presencia|guapa|figura|cuerpo|attractive)\b", re.I), 0.25, "appearance condition"),
]


# ---------------------------------------------------------------------------
# Scoring primitives
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SignalHit:
    signal_name: str
    weight: float
    span: tuple[int, int]
    surface: str


def _find_signals(text: str, signals: list[tuple[re.Pattern[str], float, str]]) -> list[_SignalHit]:
    hits: list[_SignalHit] = []
    for pat, weight, name in signals:
        for m in pat.finditer(text):
            hits.append(_SignalHit(name, weight, (m.start(), m.end()), m.group(0)))
    return hits


def _saturate(raw: float, ceiling: float = 1.0) -> float:
    """Saturating transform: f(x) = 1 - exp(-x). Caps at ceiling."""
    if raw <= 0:
        return max(0.0, min(ceiling, raw))
    return ceiling * (1.0 - math.exp(-raw))


def _normalise(score: float, lo: float = 0.0, hi: float = 1.0) -> float:
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (score - lo) / (hi - lo)))


# ---------------------------------------------------------------------------
# Spanish Flesch reading ease
# ---------------------------------------------------------------------------

_VOWELS = re.compile(r"[aeiouáéíóúüAEIOUÁÉÍÓÚÜ]", re.I)
_SENTENCE_SPLIT = re.compile(r"[\.!\?;]+")
_SYLLABLE_APPROX = re.compile(r"[aeiouáéíóúü]+", re.I)


def _spanish_flesch(text: str) -> float:
    """Approximate Spanish Flesch reading ease.

    Huerta's Spanish adaptation:
      F = 206.84 - 62.3 * (syllables/words) - 1.015 * (words/sentences)
    Returns a number typically in [0, 100]; we normalise to [0,1] for the
    profile (higher = easier).
    """
    words = re.findall(r"\b\w+\b", text)
    if not words:
        return 0.0
    n_words = len(words)
    syllables = sum(len(_SYLLABLE_APPROX.findall(w)) or 1 for w in words)
    sentences = max(1, len([s for s in _SENTENCE_SPLIT.split(text) if s.strip()]))
    raw = 206.84 - 62.3 * (syllables / n_words) - 1.015 * (n_words / sentences)
    return raw  # in ~[0, 100]


# ---------------------------------------------------------------------------
# Per-dimension scorers
# ---------------------------------------------------------------------------


def _score_with_signals(
    text: str,
    signals: list[tuple[re.Pattern[str], float, str]],
    abstain_threshold: float = 0.0,
    max_hits_per_signal: int = 3,
) -> tuple[float, list[str], list[EvidenceRef], bool, str | None]:
    """Score text using signal inventory.

    Anti-gaming fix: each unique signal name counts at most `max_hits_per_signal`
    times. This prevents keyword-stuffing attacks where repeating the same word
    100 times would inflate the score to 1.0. The cap is set to 3 so that
    legitimate repetition (e.g. 'urgente' appearing 3 times in a real ad)
    still contributes, but stuffing (100 repetitions) does not.

    Evidence spans are still collected for ALL hits (for audit), but only the
    first `max_hits_per_signal` contribute to the raw score.
    """
    hits = _find_signals(text, signals)
    # Cap hits per signal name for scoring (anti-gaming)
    hits_by_signal: dict[str, list[_SignalHit]] = {}
    for h in hits:
        hits_by_signal.setdefault(h.signal_name, []).append(h)
    scoring_hits: list[_SignalHit] = []
    for name, name_hits in hits_by_signal.items():
        scoring_hits.extend(name_hits[:max_hits_per_signal])
    raw = sum(h.weight for h in scoring_hits)
    score = _saturate(raw)
    signal_names = sorted({h.signal_name for h in hits})
    evidence = [
        EvidenceRef(
            kind="text_span",
            modality="text",
            start=h.span[0],
            end=h.span[1],
            surface=h.surface,
        )
        for h in hits  # keep all hits for evidence/audit
    ]
    abstained = raw <= abstain_threshold and not hits
    reason = "no_signal" if abstained else None
    return score, signal_names, evidence, abstained, reason


def score_urgency(text: str) -> ProfileScore:
    s, names, ev, abst, reason = _score_with_signals(text, _URGENCY_SIGNALS)
    return ProfileScore(
        dimension="urgency",
        score=s,
        raw_score=s,
        signals=names,
        supporting_evidence=ev,
        abstained=abst,
        abstention_reason=reason,
        confidence=0.6,
    )


def score_scarcity(text: str) -> ProfileScore:
    s, names, ev, abst, reason = _score_with_signals(text, _Scarcity_SIGNALS)
    return ProfileScore(
        dimension="scarcity",
        score=s,
        raw_score=s,
        signals=names,
        supporting_evidence=ev,
        abstained=abst,
        abstention_reason=reason,
        confidence=0.6,
    )


def score_emotional_intensity(text: str) -> ProfileScore:
    s, names, ev, abst, reason = _score_with_signals(text, _EMOTION_SIGNALS)
    return ProfileScore(
        dimension="emotional_intensity",
        score=s,
        raw_score=s,
        signals=names,
        supporting_evidence=ev,
        abstained=abst,
        abstention_reason=reason,
        confidence=0.55,
    )


def score_directiveness(text: str) -> ProfileScore:
    s, names, ev, abst, reason = _score_with_signals(text, _DIRECTIVENESS_SIGNALS)
    return ProfileScore(
        dimension="directiveness",
        score=s,
        raw_score=s,
        signals=names,
        supporting_evidence=ev,
        abstained=abst,
        abstention_reason=reason,
        confidence=0.65,
    )


def score_certainty(text: str) -> ProfileScore:
    s, names, ev, abst, reason = _score_with_signals(text, _CERTAINTY_SIGNALS)
    return ProfileScore(
        dimension="certainty",
        score=max(0.0, s),  # hedging can drive negative raw
        raw_score=s,
        signals=names,
        supporting_evidence=ev,
        abstained=abst,
        abstention_reason=reason,
        confidence=0.55,
    )


def score_specificity(text: str) -> ProfileScore:
    s, names, ev, abst, reason = _score_with_signals(text, _SPECIFICITY_SIGNALS)
    return ProfileScore(
        dimension="specificity",
        score=s,
        raw_score=s,
        signals=names,
        supporting_evidence=ev,
        abstained=abst,
        abstention_reason=reason,
        confidence=0.6,
    )


def score_benefit_density(text: str) -> ProfileScore:
    hits = _find_signals(text, _BENEFIT_SIGNALS)
    words = max(1, len(re.findall(r"\b\w+\b", text)))
    raw = sum(h.weight for h in hits) / (words / 50.0)  # density per 50 words
    score = _saturate(raw)
    names = sorted({h.signal_name for h in hits})
    evidence = [
        EvidenceRef(kind="text_span", modality="text", start=h.span[0], end=h.span[1], surface=h.surface)
        for h in hits
    ]
    return ProfileScore(
        dimension="benefit_density",
        score=score,
        raw_score=raw,
        signals=names,
        supporting_evidence=evidence,
        abstained=not hits,
        abstention_reason="no_signal" if not hits else None,
        confidence=0.55,
    )


def score_evidence_density(text: str) -> ProfileScore:
    hits = _find_signals(text, _EVIDENCE_SIGNALS)
    words = max(1, len(re.findall(r"\b\w+\b", text)))
    raw = sum(h.weight for h in hits) / (words / 50.0)
    score = _saturate(raw)
    names = sorted({h.signal_name for h in hits})
    evidence = [
        EvidenceRef(kind="text_span", modality="text", start=h.span[0], end=h.span[1], surface=h.surface)
        for h in hits
    ]
    return ProfileScore(
        dimension="evidence_density",
        score=score,
        raw_score=raw,
        signals=names,
        supporting_evidence=evidence,
        abstained=not hits,
        abstention_reason="no_signal" if not hits else None,
        confidence=0.5,
    )


def score_social_proof(text: str) -> ProfileScore:
    s, names, ev, abst, reason = _score_with_signals(text, _SOCIAL_PROOF_SIGNALS)
    return ProfileScore(
        dimension="social_proof",
        score=s,
        raw_score=s,
        signals=names,
        supporting_evidence=ev,
        abstained=abst,
        abstention_reason=reason,
        confidence=0.55,
    )


def score_objection_handling(text: str) -> ProfileScore:
    s, names, ev, abst, reason = _score_with_signals(text, _OBJECTION_HANDLING_SIGNALS)
    return ProfileScore(
        dimension="objection_handling",
        score=s,
        raw_score=s,
        signals=names,
        supporting_evidence=ev,
        abstained=abst,
        abstention_reason=reason,
        confidence=0.6,
    )


def score_risk_reversal(text: str) -> ProfileScore:
    s, names, ev, abst, reason = _score_with_signals(text, _RISK_REVERSAL_SIGNALS)
    return ProfileScore(
        dimension="risk_reversal",
        score=s,
        raw_score=s,
        signals=names,
        supporting_evidence=ev,
        abstained=abst,
        abstention_reason=reason,
        confidence=0.6,
    )


def score_claim_extremity(text: str) -> ProfileScore:
    s, names, ev, abst, reason = _score_with_signals(text, _CLAIM_EXTREMITY_SIGNALS)
    return ProfileScore(
        dimension="claim_extremity",
        score=s,
        raw_score=s,
        signals=names,
        supporting_evidence=ev,
        abstained=abst,
        abstention_reason=reason,
        confidence=0.55,
    )


def score_readability(text: str) -> ProfileScore:
    flesch = _spanish_flesch(text)
    # Normalise: 60+ = easy (1.0), <30 = hard (0.0)
    score = _normalise(flesch, lo=20.0, hi=70.0)
    abstained = len(re.findall(r"\b\w+\b", text)) < 5
    return ProfileScore(
        dimension="readability",
        score=score,
        raw_score=flesch,
        signals=[_READABILITY_NOTE] if not abstained else [],
        supporting_evidence=[],
        abstained=abstained,
        abstention_reason="too_short" if abstained else None,
        confidence=0.5,
    )


def score_offer_clarity(text: str) -> ProfileScore:
    s, names, ev, abst, reason = _score_with_signals(text, _OFFER_SIGNALS)
    return ProfileScore(
        dimension="offer_clarity",
        score=s,
        raw_score=s,
        signals=names,
        supporting_evidence=ev,
        abstained=abst,
        abstention_reason=reason,
        confidence=0.55,
    )


def score_action_clarity(text: str) -> ProfileScore:
    s, names, ev, abst, reason = _score_with_signals(text, _ACTION_SIGNALS)
    return ProfileScore(
        dimension="action_clarity",
        score=s,
        raw_score=s,
        signals=names,
        supporting_evidence=ev,
        abstained=abst,
        abstention_reason=reason,
        confidence=0.6,
    )


def score_trust_risk(text: str, profile_so_far: dict[str, ProfileScore] | None = None) -> ProfileScore:
    """Trust risk combines red-flag signals with elevated directiveness and
    platform-migration cues. Never a simple sum."""
    redflag_hits = _find_signals(text, _TRUST_RISK_REDFLAGS)
    redflag_raw = sum(h.weight for h in redflag_hits)
    direct = profile_so_far.get("directiveness").score if profile_so_far and "directiveness" in profile_so_far else 0.0
    combo = _saturate(redflag_raw) * 0.7 + direct * 0.3
    names = sorted({h.signal_name for h in redflag_hits})
    evidence = [
        EvidenceRef(kind="text_span", modality="text", start=h.span[0], end=h.span[1], surface=h.surface)
        for h in redflag_hits
    ]
    abstained = not redflag_hits and direct < 0.05
    return ProfileScore(
        dimension="trust_risk",
        score=combo,
        raw_score=redflag_raw,
        signals=names,
        supporting_evidence=evidence,
        abstained=abstained,
        abstention_reason="no_signal" if abstained else None,
        confidence=0.5,
    )


def score_manipulation_risk(text: str, profile_so_far: dict[str, ProfileScore] | None = None) -> ProfileScore:
    """Manipulation risk combines red-flag signals with elevated urgency,
    emotional intensity, and audience-targeting cues. NEVER a simple sum of
    the other 15 dimensions, and never presented as 'this ad is manipulative'
    — it is a risk indicator that requires human review."""
    redflag_hits = _find_signals(text, _MANIPULATION_RISK_REDFLAGS)
    redflag_raw = sum(h.weight for h in redflag_hits)
    p = profile_so_far or {}
    urgency = p.get("urgency").score if "urgency" in p else 0.0
    emotional = p.get("emotional_intensity").score if "emotional_intensity" in p else 0.0
    direct = p.get("directiveness").score if "directiveness" in p else 0.0
    # Weighted combination with explicit coefficients (audit-friendly)
    combo = (
        _saturate(redflag_raw) * 0.45
        + urgency * 0.20
        + emotional * 0.20
        + direct * 0.15
    )
    names = sorted({h.signal_name for h in redflag_hits})
    evidence = [
        EvidenceRef(kind="text_span", modality="text", start=h.span[0], end=h.span[1], surface=h.surface)
        for h in redflag_hits
    ]
    abstained = not redflag_hits and combo < 0.05
    return ProfileScore(
        dimension="manipulation_risk",
        score=combo,
        raw_score=redflag_raw,
        signals=names,
        supporting_evidence=evidence,
        abstained=abstained,
        abstention_reason="no_signal" if abstained else None,
        confidence=0.5,
    )


# ---------------------------------------------------------------------------
# Full profile
# ---------------------------------------------------------------------------


def score_profile(text: str, record_id: str = "unknown") -> PersuasiveProfile:
    """Score all 17 dimensions for one ad.

    Order matters: trust_risk and manipulation_risk are scored AFTER the
    other 15 because they consume those scores as inputs.
    """
    partial: dict[str, ProfileScore] = {
        "urgency": score_urgency(text),
        "scarcity": score_scarcity(text),
        "emotional_intensity": score_emotional_intensity(text),
        "directiveness": score_directiveness(text),
        "certainty": score_certainty(text),
        "specificity": score_specificity(text),
        "benefit_density": score_benefit_density(text),
        "evidence_density": score_evidence_density(text),
        "social_proof": score_social_proof(text),
        "objection_handling": score_objection_handling(text),
        "risk_reversal": score_risk_reversal(text),
        "claim_extremity": score_claim_extremity(text),
        "readability": score_readability(text),
        "offer_clarity": score_offer_clarity(text),
        "action_clarity": score_action_clarity(text),
    }
    partial["trust_risk"] = score_trust_risk(text, partial)
    partial["manipulation_risk"] = score_manipulation_risk(text, partial)

    # Sanity: exactly 17 dimensions in spec order
    assert tuple(partial.keys()) == PROFILE_DIMENSIONS, "Profile dimension order drifted"

    composite = {
        "max_dimension": max(partial[d].score for d in PROFILE_DIMENSIONS),
        "mean_dimension": sum(partial[d].score for d in PROFILE_DIMENSIONS) / len(PROFILE_DIMENSIONS),
        "n_abstained": sum(1 for d in PROFILE_DIMENSIONS if partial[d].abstained),
        "high_risk_dimensions": [d for d in PROFILE_DIMENSIONS if partial[d].score >= 0.5],
    }

    return PersuasiveProfile(
        record_id=record_id,
        taxonomy_version=PROFILE_TAXONOMY_VERSION,
        checkpoint_id=PROFILE_CHECKPOINT_ID,
        dimensions=partial,
        composite_summary=composite,
        review_status="unreviewed",
    )


def profile_dimensions() -> tuple[str, ...]:
    """Public accessor for the 17 dimensions, in spec order."""
    return PROFILE_DIMENSIONS
