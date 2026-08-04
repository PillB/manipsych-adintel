"""Hierarchical multi-label technique taxonomy (adintel-taxonomy-v2).

The existing ManiPsych taxonomy (manipsych-span-v1) is a flat list of 20 leaf
labels. The new spec requires a *hierarchical multi-label* taxonomy, with
explicit parent categories and a mapping from copywriting/composition,
persuasive rhetoric, behavioural science, and sales/objection-handling
families down to leaves. We also add visual-persuasion and multimodal leaves
that were missing from v1.

This module is the single source of truth for the taxonomy. Schemas, models,
and the dashboard all import from here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

TAXONOMY_VERSION = "adintel-taxonomy-v2"

# ---------------------------------------------------------------------------
# Hierarchy definition
# ---------------------------------------------------------------------------

# Four top-level families required by the spec, plus two cross-cutting
# families (visual persuasion, multimodal combinations) that the spec calls
# out separately.
TOP_LEVEL_FAMILIES: tuple[str, ...] = (
    "copywriting_composition",
    "persuasive_rhetoric",
    "behavioural_science",
    "sales_objection_handling",
    "visual_persuasion",
    "multimodal_combination",
)


@dataclass(frozen=True)
class TaxonNode:
    """One node in the hierarchical taxonomy."""

    id: str  # machine label, snake_case
    name: str  # human-readable name
    family: str  # top-level family
    parent: str | None  # parent label id, or None for family roots
    level: int  # 0 = family, 1 = sub-category, 2 = leaf
    definition: str
    mechanism: str  # psychological / rhetorical mechanism
    hard_negatives: tuple[str, ...] = ()  # short examples that should NOT fire this label
    language_patterns: tuple[str, ...] = ()
    visual_patterns: tuple[str, ...] = ()
    v1_equivalents: tuple[str, ...] = ()  # which manipsych-span-v1 leaves map here

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "family": self.family,
            "parent": self.parent,
            "level": self.level,
            "definition": self.definition,
            "mechanism": self.mechanism,
            "hard_negatives": list(self.hard_negatives),
            "language_patterns": list(self.language_patterns),
            "visual_patterns": list(self.visual_patterns),
            "v1_equivalents": list(self.v1_equivalents),
        }


# ---------------------------------------------------------------------------
# Taxonomy contents
# ---------------------------------------------------------------------------

# Notes on mapping v1 -> v2:
# - v1's `reciprocity_obligation` was overloaded; it split into
#   `behavioural_reciprocity` (behavioural_science family) and
#   `copywriting_reciprocity_frame` (copywriting_composition family).
# - v1's `platform_migration` is a copywriting-composition technique
#   (call-to-action design), not a persuasion technique per se.
# - v1's targeting labels (age/youth, education, economic, family, sexualised
#   appearance) are reframed as `behavioural_science.audience_targeting.*`
#   because targeting is not itself a technique — it is who a technique is
#   aimed at. This is an important re-framing: the spec says "do not equate
#   technique presence with persuasion", and conflating targeting with
#   technique was a v1 weakness.
# - New visual-persuasion leaves are added with `v1_equivalents=()` because
#   the v1 corpus had no image-pixel features.

NODES: tuple[TaxonNode, ...] = (
    # --- copywriting_composition family ------------------------------
    TaxonNode(
        id="copywriting_composition",
        name="Copywriting and composition techniques",
        family="copywriting_composition",
        parent=None,
        level=0,
        definition="Techniques of ad craft: how the copy is structured, sequenced, and presented.",
        mechanism="Composition choices shape attention, comprehension, and action without necessarily persuading.",
    ),
    TaxonNode(
        id="cc_headline_hook",
        name="Headline hook",
        family="copywriting_composition",
        parent="copywriting_composition",
        level=1,
        definition="A headline engineered to arrest attention (curiosity gap, startling claim, direct address).",
        mechanism="Orienting response + curiosity gap.",
        language_patterns=("curiosity gap", "direct address 'tú/usted'", "startling claim"),
        v1_equivalents=(),
    ),
    TaxonNode(
        id="cc_offer_stack",
        name="Offer stack",
        family="copywriting_composition",
        parent="copywriting_composition",
        level=1,
        definition="Itemised list of benefits or components presented as a stack with anchors.",
        mechanism="Anchoring on component value; transactional utility framing.",
        v1_equivalents=("conditional_financial_support",),
    ),
    TaxonNode(
        id="cc_call_to_action",
        name="Call-to-action design",
        family="copywriting_composition",
        parent="copywriting_composition",
        level=1,
        definition="Explicit instruction on how to respond, including channel migration cues.",
        mechanism="Reduces friction; specifies the next action.",
        language_patterns=("escribeme", "whatsapp", "dm", "inbox", "privado"),
        v1_equivalents=("platform_migration",),
    ),
    TaxonNode(
        id="cc_disclaimer_overlay",
        name="Disclaimer / compliance overlay",
        family="copywriting_composition",
        parent="copywriting_composition",
        level=1,
        definition="Compliance-style language added to lend legitimacy or to limit liability.",
        mechanism="Authority laundering through formal-sounding disclaimers.",
        v1_equivalents=("deceptive_assurance",),
    ),
    TaxonNode(
        id="cc_reciprocity_frame",
        name="Reciprocity framing in copy",
        family="copywriting_composition",
        parent="copywriting_composition",
        level=1,
        definition="Copy that frames the offer as help, gift, or mutual aid.",
        mechanism="Reciprocity heuristic (Cialdini).",
        v1_equivalents=("reciprocity_obligation",),
    ),

    # --- persuasive_rhetoric family ----------------------------------
    TaxonNode(
        id="persuasive_rhetoric",
        name="Persuasive rhetorical techniques",
        family="persuasive_rhetoric",
        parent=None,
        level=0,
        definition="Classical rhetorical moves (ethos, pathos, logos) and their modern ad variants.",
        mechanism="Rhetorical figures shape perceived credibility, emotion, and logic.",
    ),
    TaxonNode(
        id="pr_scarcity_urgency",
        name="Scarcity and urgency rhetoric",
        family="persuasive_rhetoric",
        parent="persuasive_rhetoric",
        level=1,
        definition="Rhetoric that implies limited time, limited supply, or limited access.",
        mechanism="Loss aversion; time pressure reduces deliberation.",
        language_patterns=("hoy", "urgente", "último", "solo por", "limited"),
        v1_equivalents=("scarcity_or_urgency",),
    ),
    TaxonNode(
        id="pr_social_proof",
        name="Social proof rhetoric",
        family="persuasive_rhetoric",
        parent="persuasive_rhetoric",
        level=1,
        definition="Claims of popularity, testimonials, or majority behaviour.",
        mechanism="Conformity heuristic.",
        v1_equivalents=("social_proof",),
    ),
    TaxonNode(
        id="pr_authority_appeal",
        name="Authority appeal",
        family="persuasive_rhetoric",
        parent="persuasive_rhetoric",
        level=1,
        definition="Citing titles, credentials, or institutional-sounding signals.",
        mechanism="Authority heuristic (Milgram lineage).",
        v1_equivalents=("authority_or_status_appeal",),
    ),
    TaxonNode(
        id="pr_exclusivity",
        name="Exclusivity / special treatment",
        family="persuasive_rhetoric",
        parent="persuasive_rhetoric",
        level=1,
        definition="Rhetoric that frames the offer as available only to a select few.",
        mechanism="In-group favouritism + scarcity.",
        v1_equivalents=("exclusivity_or_special_treatment",),
    ),
    TaxonNode(
        id="pr_emotional_appeal",
        name="Emotional appeal",
        family="persuasive_rhetoric",
        parent="persuasive_rhetoric",
        level=1,
        definition="Pathos-driven framing: fear, hope, shame, pride, belonging.",
        mechanism="Affect heuristic.",
        v1_equivalents=("fear_or_threat", "guilt_or_shame_pressure"),
    ),

    # --- behavioural_science family ----------------------------------
    TaxonNode(
        id="behavioural_science",
        name="Behavioural-science techniques",
        family="behavioural_science",
        parent=None,
        level=0,
        definition="Behavioural-economics levers (defaults, commitment, foot-in-the-door, etc.).",
        mechanism="Bounded rationality; System 1 levers.",
    ),
    TaxonNode(
        id="bs_commitment_consistency",
        name="Commitment and consistency / foot-in-the-door",
        family="behavioural_science",
        parent="behavioural_science",
        level=1,
        definition="Sequential asks that lock in commitment through consistency pressure.",
        mechanism="Commitment-consistency (Cialdini); foot-in-the-door.",
        v1_equivalents=("commitment_escalation", "foot_in_the_door"),
    ),
    TaxonNode(
        id="bs_reciprocity_obligation",
        name="Reciprocity obligation",
        family="behavioural_science",
        parent="behavioural_science",
        level=1,
        definition="Behavioural lever: invoking a felt obligation to reciprocate.",
        mechanism="Reciprocity heuristic.",
        v1_equivalents=("reciprocity_obligation",),
    ),
    TaxonNode(
        id="bs_repetition_campaign_escalation",
        name="Repetition and campaign escalation",
        family="behavioural_science",
        parent="behavioural_science",
        level=1,
        definition="Repeat exposure and escalation across placements or time.",
        mechanism="Mere exposure; availability cascade.",
        v1_equivalents=("repetition_or_campaign_escalation",),
    ),
    TaxonNode(
        id="bs_privacy_secrecy_pressure",
        name="Privacy / secrecy pressure",
        family="behavioural_science",
        parent="behavioural_science",
        level=1,
        definition="Pressure to keep the exchange private or secret from others.",
        mechanism="Information control; isolation of the target.",
        language_patterns=("discreto", "secreto", "sin que nadie", "confidencial"),
        v1_equivalents=("privacy_or_secrecy_pressure",),
    ),
    TaxonNode(
        id="bs_audience_targeting",
        name="Audience targeting (behavioural context, not a technique per se)",
        family="behavioural_science",
        parent="behavioural_science",
        level=1,
        definition="WHO the ad addresses; targeting is context, not a persuasion technique. Recorded separately so it is not collapsed with technique presence.",
        mechanism="Vulnerability amplifiers operate on targeted audiences.",
        v1_equivalents=(),
    ),
    TaxonNode(
        id="bs_audience_targeting.age_youth",
        name="Age / youth targeting",
        family="behavioural_science",
        parent="bs_audience_targeting",
        level=2,
        definition="Ad addresses or implies young-adult audience.",
        mechanism="Asymmetric power; developmental vulnerability.",
        v1_equivalents=("age_or_youth_targeting",),
    ),
    TaxonNode(
        id="bs_audience_targeting.education_student",
        name="Education / student targeting",
        family="behavioural_science",
        parent="bs_audience_targeting",
        level=2,
        definition="Ad addresses students or appeals to education-related financial pressure.",
        mechanism="Income asymmetry; aspiration leverage.",
        v1_equivalents=("education_or_student_targeting",),
    ),
    TaxonNode(
        id="bs_audience_targeting.economic_vulnerability",
        name="Economic-vulnerability targeting",
        family="behavioural_science",
        parent="bs_audience_targeting",
        level=2,
        definition="Ad explicitly frames the recipient as in financial distress.",
        mechanism="Leverage over material need.",
        v1_equivalents=("economic_vulnerability_targeting",),
    ),
    TaxonNode(
        id="bs_audience_targeting.family_obligation",
        name="Family-obligation targeting",
        family="behavioural_science",
        parent="bs_audience_targeting",
        level=2,
        definition="Ad invokes family care obligations as leverage.",
        mechanism="Normative obligation pressure.",
        v1_equivalents=("family_obligation_targeting",),
    ),
    TaxonNode(
        id="bs_audience_targeting.gendered_appearance",
        name="Gendered-appearance condition",
        family="behavioural_science",
        parent="bs_audience_targeting",
        level=2,
        definition="Ad conditions the offer on gendered appearance.",
        mechanism="Objectification; gendered power asymmetry.",
        v1_equivalents=("sexualized_appearance_condition",),
    ),

    # --- sales_objection_handling family -----------------------------
    TaxonNode(
        id="sales_objection_handling",
        name="Sales and objection-handling techniques",
        family="sales_objection_handling",
        parent=None,
        level=0,
        definition="Direct-response sales techniques: risk reversal, guarantee, FAQ-as-objection-handling, transactional ambiguity.",
        mechanism="Reduces perceived transactional risk; defers critical scrutiny.",
    ),
    TaxonNode(
        id="so_risk_reversal",
        name="Risk reversal / guarantee",
        family="sales_objection_handling",
        parent="sales_objection_handling",
        level=1,
        definition="Money-back, satisfaction, or safety guarantees.",
        mechanism="Loss-aversion offset.",
        v1_equivalents=("deceptive_assurance",),
    ),
    TaxonNode(
        id="so_transactional_ambiguity",
        name="Transactional ambiguity",
        family="sales_objection_handling",
        parent="sales_objection_handling",
        level=1,
        definition="Deliberate vagueness about what is being exchanged for what.",
        mechanism="Plausible deniability; deferred critical scrutiny.",
        v1_equivalents=("transactional_ambiguity",),
    ),
    TaxonNode(
        id="so_conditional_support",
        name="Conditional support framing",
        family="sales_objection_handling",
        parent="sales_objection_handling",
        level=1,
        definition="Framing the offer as conditional help with unstated conditions.",
        mechanism="Conceals the quid pro quo.",
        v1_equivalents=("conditional_financial_support",),
    ),

    # --- visual_persuasion family ------------------------------------
    TaxonNode(
        id="visual_persuasion",
        name="Visual persuasion techniques",
        family="visual_persuasion",
        parent=None,
        level=0,
        definition="Image- and layout-level persuasion. v1 corpus had no image pixels; these leaves are scaffolded for future image modelling.",
        mechanism="Visual salience, composition, and affective imagery.",
    ),
    TaxonNode(
        id="vp_gaze_direction",
        name="Gaze direction",
        family="visual_persuasion",
        parent="visual_persuasion",
        level=1,
        definition="Subject gaze directed at viewer or at CTA.",
        mechanism="Eye contact elevates attention and compliance.",
        visual_patterns=("subject looking at camera", "subject looking at CTA"),
    ),
    TaxonNode(
        id="vp_luxury_aesthetic",
        name="Luxury / status aesthetic",
        family="visual_persuasion",
        parent="visual_persuasion",
        level=1,
        definition="Visual cues of wealth, exclusivity, or status.",
        mechanism="Status-transfer heuristic.",
        visual_patterns=("gold accents", "branded props", "upscale interiors"),
    ),
    TaxonNode(
        id="vp_sexualised_imagery",
        name="Sexualised imagery",
        family="visual_persuasion",
        parent="visual_persuasion",
        level=1,
        definition="Sexualised depiction of subjects, especially conditioning the offer.",
        mechanism="Affective arousal; objectification.",
        visual_patterns=("revealing clothing", "suggestive pose", "body-part cropping"),
    ),

    # --- multimodal_combination family -------------------------------
    TaxonNode(
        id="multimodal_combination",
        name="Multimodal technique combinations",
        family="multimodal_combination",
        parent=None,
        level=0,
        definition="Cross-modal reinforcement or contradiction between text, image, audio, video.",
        mechanism="Multimodal coherence increases perceived credibility; contradiction can signal deception.",
    ),
    TaxonNode(
        id="mm_text_image_reinforcement",
        name="Text-image reinforcement",
        family="multimodal_combination",
        parent="multimodal_combination",
        level=1,
        definition="Image amplifies the same claim as the text.",
        mechanism="Dual coding; redundancy gains.",
    ),
    TaxonNode(
        id="mm_text_image_contradiction",
        name="Text-image contradiction",
        family="multimodal_combination",
        parent="multimodal_combination",
        level=1,
        definition="Image contradicts the literal text claim (e.g. text says 'help', image says otherwise).",
        mechanism="May signal deceptive framing; needs human review.",
    ),
)


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

_BY_ID: dict[str, TaxonNode] = {n.id: n for n in NODES}


def all_nodes() -> tuple[TaxonNode, ...]:
    return NODES


def leaf_nodes() -> tuple[TaxonNode, ...]:
    """Nodes with no children — the labels that predictions actually emit."""
    parent_ids = {n.parent for n in NODES if n.parent is not None}
    return tuple(n for n in NODES if n.id not in parent_ids)


def family_roots() -> tuple[TaxonNode, ...]:
    return tuple(n for n in NODES if n.level == 0)


def children(parent_id: str) -> tuple[TaxonNode, ...]:
    return tuple(n for n in NODES if n.parent == parent_id)


def get(node_id: str) -> TaxonNode:
    if node_id not in _BY_ID:
        raise KeyError(f"Unknown taxonomy node: {node_id}")
    return _BY_ID[node_id]


def ancestors(node_id: str) -> tuple[str, ...]:
    """Walk up to the family root. Returns ids from immediate parent up."""
    out: list[str] = []
    cur = _BY_ID.get(node_id)
    while cur and cur.parent is not None:
        out.append(cur.parent)
        cur = _BY_ID.get(cur.parent)
    return tuple(out)


def family_of(node_id: str) -> str:
    return get(node_id).family


def is_leaf(node_id: str) -> bool:
    return node_id in {n.id for n in leaf_nodes()}


# ---------------------------------------------------------------------------
# v1 -> v2 mapping
# ---------------------------------------------------------------------------

_V1_TO_V2: dict[str, list[str]] = {}  # populated below


def _build_v1_to_v2() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for node in NODES:
        for v1 in node.v1_equivalents:
            out.setdefault(v1, []).append(node.id)
    return out


_V1_TO_V2 = _build_v1_to_v2()


def v1_to_v2(v1_label: str) -> list[str]:
    """Return all v2 leaves that the given v1 label maps to.

    A v1 label may map to multiple v2 leaves (e.g. `reciprocity_obligation`
    maps to both `cc_reciprocity_frame` and `bs_reciprocity_obligation`).
    Records that used the v1 label should be re-labelled with all v2 leaves.
    """
    return list(_V1_TO_V2.get(v1_label, []))


def v2_to_v1(v2_label: str) -> list[str]:
    """Reverse mapping: which v1 labels map onto this v2 leaf."""
    return list(get(v2_label).v1_equivalents)


def unmapped_v1_labels(v1_labels: Iterable[str]) -> list[str]:
    """Return v1 labels that have no v2 equivalent (should be empty)."""
    return [v for v in v1_labels if not _V1_TO_V2.get(v)]


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def to_dict() -> dict:
    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "top_level_families": list(TOP_LEVEL_FAMILIES),
        "nodes": [n.to_dict() for n in NODES],
        "leaf_count": len(leaf_nodes()),
        "v1_to_v2": _V1_TO_V2,
    }


def to_json(path: str | Path) -> None:
    Path(path).write_text(json.dumps(to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
