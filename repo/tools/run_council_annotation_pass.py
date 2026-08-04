#!/usr/bin/env python3
"""Run a deterministic 3-profile council annotation pass.

This creates subagent suggestion annotations from the frozen annotation DB.
It is intentionally not a gold-label generator: accepted council outputs still
remain layer=subagent unless a human/adjudicator promotes them separately.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import unicodedata
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.annotation_store import save_annotation
from tools.council_consensus import actor_for_round, evaluate, export_queue

DEFAULT_DB = ROOT / "data/annotation/annotations.sqlite3"
DEFAULT_QUEUE = ROOT / "data/annotation/council_second_pass_queue.jsonl"
SPAN_MATCH_MODE = "accent_gender_typo_normalized_span_matching_v5"
ANNOTATION_METHOD = "automated_council_rules_v5_spanish_orthographic_semantic"

# Spanish classified-ad text is noisy: accents are omitted, gender agreement is
# inconsistent ("apoyo económica"), and common human-entry errors include
# duplicated syllables ("economomico") and digit substitutions ("ec0nomica").
# These fragments intentionally match the original surface form so saved spans
# keep exact immutable offsets rather than normalized text offsets.
ECON_WORD = r"econ(?:o|ó|0)m(?:om)?(?:i|í)[ck][oa]s?"
ECON_ADV = r"econ(?:o|ó|0)m(?:om)?(?:i|í)[ck]amente"
SUPPORT_NOUN = rf"(?:ayuda|alluda|apoyo|apoya|apollo|apoyos?|apoyito|gastos?|dinero|solvencia|compensaci(?:o|ó)n|pago|pagos?)"
SUPPORT_VERB = (
    r"(?:brindo|brind[oó]|brinda|brindar|doy|doi|ofrezco|ofresco|ofrese|ofrece|"
    r"apoyo|apoya|apollo|ayuda|ayudo|te\s+(?:apoyo|apoya|ayudo)|solvento|financio|mantengo|cubro)"
)


@dataclass(frozen=True)
class Cue:
    label: str
    pattern: str
    rationale: str
    intensity: int
    manipulativeness: int
    harm_risk: int
    explicitness: str = "explicit"
    vulnerability_target: str = ""
    profiles: tuple[str, ...] = ("a", "b", "c")


PROFILE_BY_SLOT = {0: "a", 1: "b", 2: "c"}


CUES: tuple[Cue, ...] = (
    Cue(
        "reciprocity_obligation",
        rf"\b{SUPPORT_VERB}\s+(?:\w+\s+){{0,5}}(?:{ECON_WORD}|{ECON_ADV}|{SUPPORT_NOUN}|soles?)\b|\b(?:{SUPPORT_NOUN}|ayudo)\s+(?:{ECON_WORD}|{ECON_ADV})\b|\b{SUPPORT_NOUN}\s+(?:mutu[oa]|mensual|semanal)\b",
        "frames the advertiser as providing help/support, creating reciprocity pressure",
        3,
        2,
        2,
    ),
    Cue(
        "conditional_financial_support",
        rf"\b(?:a\s*cambio\s*(?:de)?|x\s+(?:sexo|intimidad|relaciones?|encuentr(?:os?|it[oa]s?)|salid(?:as?|it[oa]s?)|citas?|compa(?:ñ|n)[ií]a)|si\s+aceptas|te\s+ayud[oa]\s+si|yo\s+te\s+apoy[oa]\s+si|beneficio\s+mutu[oa]|por\s+(?:sexo|intimidad|relaciones?|encuentr(?:os?|it[oa]s?)|salid(?:as?|it[oa]s?)|citas?|compa(?:ñ|n)[ií]a)|por\s+cada\s+(?:salida|encuentro|vez)|{SUPPORT_NOUN}\s+(?:regular\s+)?(?:de\s+)?(?:hasta\s+)?s/?\.?\s*\d+|la\s+cantidad\s+depende\s+de\s+c[oó]mo\s+seas)\b",
        "makes financial or material support conditional on an exchange",
        4,
        3,
        3,
    ),
    Cue(
        "transactional_ambiguity",
        r"\b(?:llegar\s+a\s+un\s+acuerdo|acuerdo\s+mutuo|mutuo\s+acuerdo|trato|tratos|arreglo|arreglito|convenio|sin\s+compromiso|disponibilidad|beneficio\s+mutuo|apoyo\s+mutuo)\b",
        "uses euphemistic or ambiguous transactional wording",
        3,
        2,
        2,
    ),
    Cue(
        "economic_vulnerability_targeting",
        rf"\b(?:apuros?|apurad[ao]s?|urgencias?|emergencias?|necesidad(?:es)?|necesit[ao]s?|nesecidad(?:es)?|nesecit[ao]s?|necesito|nesecito|malos?\s+momentos?|problemas?\s+{ECON_WORD}|situaci(?:o|ó)n\s+dif(?:i|í)cil|pasando\s+(?:por\s+)?(?:apuros?|necesidad(?:es)?|malos?\s+momentos?)|gastos?(?:\s+personales)?|solventar(?:te)?|alquiler(?:es)?|renta|vestimenta|manutenci(?:o|ó)n|dinero|deudas?|sin\s+trabajo|misio|misia)\b",
        "targets economic hardship or urgent need",
        4,
        3,
        3,
        vulnerability_target="economic",
    ),
    Cue(
        "privacy_or_secrecy_pressure",
        r"\b(?:discret[ao]s?|discretamente|discreci(?:o|ó)n|discrecion|discresi(?:o|ó)n|discrici(?:o|ó)n|discricion|discrisi(?:o|ó)n|reserva|reservad[ao]s?|confidencial|secreto|sin\s+que\s+nadie\s+sepa|privad[ao]|priv|pv|entre\s+nosotros|calladit[ao])\b",
        "requests secrecy, discretion, or privacy",
        3,
        2,
        2,
    ),
    Cue(
        "platform_migration",
        r"\b(?:whats?app|whasap|wsp|wasap|guasap|telegram|inbox|imbox|dm|buz(?:o|ó)n|privado|priv|pv|correo|email|e-?mail|mensaje|msje|msj|sms|nro|n[uú]mero|numero|escr[ií]beme|escribeme|ecrivir|ll[aá]mame|llamame|cont[aá]ctame|contactame|\[REDACTED_(?:PHONE|CONTACT|EMAIL)\])\b",
        "moves the interaction to direct/private contact",
        2,
        1,
        1,
        profiles=("a", "c"),
    ),
    Cue(
        "sexualized_appearance_condition",
        r"\b(?:lind[ao]s?|bonit[ao]s?|atractiv[ao]s?|guap[ao]s?|hermos[ao]s?|delgad[ao]s?|cuerp[oa]|figura|contextura|cari(?:ñ|n)os[ao]s?|sexy|sensual|femenina|femenino|mente\s+abierta|liberal|foto(?:s)?|fotitos?|con\s+foto|buena\s+presencia)\b",
        "conditions attention/support on appearance or sexualized traits",
        3,
        2,
        2,
        vulnerability_target="gendered_appearance",
    ),
    Cue(
        "age_or_youth_targeting",
        r"\b(?:18\s*(?:a|hasta|-)\s*(?:20|21|22|23|24|25)|2[0-5]\s+a(?:ñ|n)os?\s+(?:para\s+abajo|m[aá]ximo)|menores?\s+de\s+26|jovencitas?|j[oó]venes?|se(?:ñ|n)oritas?|srtas?|chicas?|xicas?|chibolas?|mujeres\s+j[oó]venes?|primerizas?)\b",
        "targets young women or specific youth age ranges",
        3,
        2,
        2,
        vulnerability_target="age_youth",
    ),
    Cue(
        "education_or_student_targeting",
        r"\b(?:estudiantes?|estudiant[eai]s?|universitari[ao]s?|univ\.?|univers?\.?|instituto|colegial[ao]s?|estudios|carrera|academia)\b",
        "targets students or educational dependency",
        3,
        2,
        2,
        vulnerability_target="student",
    ),
    Cue(
        "family_obligation_targeting",
        r"\b(?:madres?\s+solteras?|mam[áa]s?\s+solteras?|con\s+hijos?|hij[ao]s?|familia|mantener\s+a\s+tu\s+familia|para\s+tus?\s+hij[ao]s?)\b",
        "targets family-care obligations",
        3,
        2,
        2,
        vulnerability_target="family",
    ),
    Cue(
        "commitment_escalation",
        r"\b(?:permanente|mensual|semanal|quincenal|constante|estable|fij[oa]|regular|largo\s+plazo|cada\s+mes|cada\s+semana)\b",
        "offers recurring support that may create dependency",
        3,
        2,
        2,
        profiles=("a", "c"),
    ),
    Cue(
        "authority_or_status_appeal",
        r"\b(?:caballero\s+serio|hombre\s+serio|profesional|empresario|solvente|maduro|responsable|ejecutivo|ingeniero|doctor|respetuoso|educado|amable|tranquilo|sin\s+vicios|limpio|buen\s+f[ií]sico)\b",
        "uses status, solvency, or respectability as persuasion",
        2,
        1,
        1,
        profiles=("a",),
    ),
    Cue(
        "deceptive_assurance",
        r"\b(?:no\s+pido\s+nada|nada\s+a\s+cambio|solo\s+amistad|solo\s+conversar|sin\s+obligaci(?:o|ó)n|sin\s+compromiso|sin\s+riesgo|100\s*%\s*segur[ao]|no\s+te\s+arrepentir[aá]s|real\s+y\s+constante|seri[ao]\s+y\s+real|segur[ao]|con\s+(?:debido\s+)?respeto|nada\s+grosero|confianza|confiable)\b",
        "downplays obligation or risk while advertising support",
        3,
        2,
        2,
        profiles=("a", "b"),
    ),
    Cue(
        "foot_in_the_door",
        r"\b(?:primero\s+convers(?:a|e)mos|conocernos|conocer|tomar\s+un\s+caf[eé]|vernos\s+primero|solo\s+hablar)\b",
        "starts with a low-commitment step",
        2,
        1,
        1,
        profiles=("a",),
    ),
    Cue(
        "scarcity_or_urgency",
        r"\b(?:hoy|urgente|r[aá]pid[ao]|inmediata?|de\s+inmediato|ahora|esta\s+noche|por\s+poco\s+tiempo|solo\s+hoy|sin\s+complicaciones|dentro\s+del\s+mismo\s+d[ií]a)\b",
        "adds temporal pressure or urgency",
        2,
        1,
        1,
        profiles=("a", "c"),
    ),
    Cue(
        "exclusivity_or_special_treatment",
        r"\b(?:solo\s+para\s+ti|exclusiv[ao]|especial|preferencia|una\s+sola\s+chica|[uú]nica)\b",
        "promises special or exclusive treatment",
        2,
        1,
        1,
        profiles=("a", "c"),
    ),
    Cue(
        "social_proof",
        r"\b(?:otras?\s+(?:chicas?|personas?)|personas?\s+que\s+me\s+escrib(?:en|ieron)|varias?\s+(?:chicas?|personas?)|todos?\s+(?:dicen|saben)|recomendad[ao]|comprobado)\b",
        "uses other people's participation or endorsement as social proof",
        2,
        1,
        1,
        profiles=("a", "c"),
    ),
    Cue(
        "guilt_or_shame_pressure",
        r"\b(?:si\s+(?:est[aá]s|estas)\s+realmente\s+decidida|solo\s+chicas?\s+reales|abstenerse\s+(?:curiosas?|kines?|intermediarios?)|no\s+(?:me\s+)?hagas?\s+perder\s+el\s+tiempo|si\s+de\s+verdad|demuestra)\b",
        "uses gatekeeping, shame, or proof-of-seriousness pressure",
        3,
        2,
        2,
        profiles=("a", "b"),
    ),
    Cue(
        "fear_or_threat",
        r"\b(?:te\s+vas\s+a\s+arrepentir|pierdas?\s+la\s+oportunidad|sin\s+salida|no\s+tendr[aá]s\s+otra|amenaz[ao]|denunci[ao])\b",
        "uses fear, threat, or loss framing",
        3,
        3,
        3,
        profiles=("a", "c"),
    ),
    Cue(
        "repetition_or_campaign_escalation",
        r"\b(?:cada\s+(?:semana|mes|vez)|dos\s+hasta\s+tres\s+veces|varias\s+veces|nuevamente|otra\s+vez|repetid[ao]|frecuencia|constantemente)\b",
        "signals repeated contact, repost-like repetition, or campaign escalation",
        3,
        2,
        2,
        profiles=("a", "c"),
    ),
)


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def fold_with_index(value: str) -> tuple[str, list[int]]:
    """Return accent/case-folded text plus folded-index -> original-index map.

    The source ads contain informal Spanish with accent omissions, gender
    agreement mistakes, and typos. Matching against folded text improves recall
    while preserving exact original offsets for saved standoff annotations.
    """
    folded_chars: list[str] = []
    index_map: list[int] = []
    for original_index, char in enumerate(value):
        for folded_char in unicodedata.normalize("NFKD", char.casefold()):
            if unicodedata.combining(folded_char):
                continue
            folded_chars.append(folded_char)
            index_map.append(original_index)
    return "".join(folded_chars), index_map


def folded_span_to_original(index_map: list[int], start: int, end: int) -> tuple[int, int]:
    if start < 0 or end <= start or end > len(index_map):
        raise ValueError("invalid folded span")
    return index_map[start], index_map[end - 1] + 1


def sexual_exchange_present(text: str) -> bool:
    folded, _ = fold_with_index(text)
    return bool(
        re.search(
            r"\b(sexo|sexual|intimidad|intimo|relacion(?:es)?|encuentr(?:o|os|ito|itos)|placer|cama)\b",
            folded,
        )
    )


def overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def merge_same_label_overlaps(spans: list[dict]) -> list[dict]:
    ordered = sorted(spans, key=lambda span: (span["label"], span["segments"][0][0], span["segments"][0][1]))
    merged: list[dict] = []
    for span in ordered:
        if not merged or merged[-1]["label"] != span["label"]:
            merged.append(span)
            continue
        prev = merged[-1]
        prev_start, prev_end = prev["segments"][0]
        start, end = span["segments"][0]
        if start <= prev_end:
            new_start, new_end = min(prev_start, start), max(prev_end, end)
            prev["segments"] = [[new_start, new_end]]
            prev["exact_text"] = span["_text"][new_start:new_end]
            prev["intensity"] = max(prev.get("intensity") or 0, span.get("intensity") or 0)
            prev["manipulativeness"] = max(
                prev.get("manipulativeness") or 0, span.get("manipulativeness") or 0
            )
            prev["harm_risk"] = max(prev.get("harm_risk") or 0, span.get("harm_risk") or 0)
        else:
            merged.append(span)
    for span in merged:
        span.pop("_text", None)
    return merged


def profile_for_actor(actor_id: str) -> str:
    match = re.search(r"_([abc])$", actor_id)
    if not match:
        raise ValueError(f"unknown council actor profile: {actor_id}")
    return match.group(1)


def cue_allowed(cue: Cue, profile: str, round_number: int, deliberated_second_pass: bool) -> bool:
    if deliberated_second_pass and round_number > 1:
        return profile in ("a", "b", "c")
    return profile in cue.profiles


def annotate_text(
    text: str,
    context: dict,
    actor_id: str,
    round_number: int,
    deliberated_second_pass: bool = False,
) -> tuple[list[dict], dict]:
    profile = profile_for_actor(actor_id)
    folded_text, folded_index = fold_with_index(text)
    has_sexual_exchange = sexual_exchange_present(folded_text)
    spans: list[dict] = []
    occupied_by_label: dict[str, list[tuple[int, int]]] = {}
    for cue in CUES:
        if not cue_allowed(cue, profile, round_number, deliberated_second_pass):
            continue
        for match in re.finditer(cue.pattern, folded_text, flags=re.IGNORECASE):
            folded_start, folded_end = match.span()
            start, end = folded_span_to_original(folded_index, folded_start, folded_end)
            if start == end:
                continue
            label_ranges = occupied_by_label.setdefault(cue.label, [])
            if any(overlap((start, end), existing) for existing in label_ranges):
                continue
            intensity = cue.intensity
            manipulativeness = cue.manipulativeness
            harm_risk = cue.harm_risk
            if has_sexual_exchange and cue.label in {
                "conditional_financial_support",
                "reciprocity_obligation",
                "transactional_ambiguity",
                "economic_vulnerability_targeting",
            }:
                intensity = max(intensity, 4)
                manipulativeness = max(manipulativeness, 3)
                harm_risk = max(harm_risk, 3)
            if (
                not deliberated_second_pass
                and profile == "b"
                and cue.label in {"platform_migration", "authority_or_status_appeal"}
            ):
                continue
            span = {
                "label": cue.label,
                "segments": [[start, end]],
                "exact_text": text[start:end],
                "rationale": cue.rationale,
                "intensity": intensity,
                "manipulativeness": manipulativeness,
                "harm_risk": harm_risk,
                "explicitness": cue.explicitness,
                "vulnerability_target": cue.vulnerability_target,
                "_text": text,
            }
            spans.append(span)
            label_ranges.append((start, end))
    spans = merge_same_label_overlaps(spans)
    max_intensity = max((span.get("intensity") or 0 for span in spans), default=0)
    max_manip = max((span.get("manipulativeness") or 0 for span in spans), default=0)
    max_harm = max((span.get("harm_risk") or 0 for span in spans), default=0)
    vulnerability_targets = sorted(
        {
            span.get("vulnerability_target")
            for span in spans
            if span.get("vulnerability_target")
        }
    )
    document = {
        "adjudication_state": "reviewed",
        "annotation_method": ANNOTATION_METHOD,
        "span_match_mode": SPAN_MATCH_MODE,
        "council_round": round_number,
        "deliberated_second_pass": bool(deliberated_second_pass and round_number > 1),
        "explicitness": "explicit" if spans else "unclear",
        "harm_risk": max_harm,
        "image_available": bool(context.get("image_available")),
        "image_reviewed": False,
        "image_review_note": context.get("image_review_note", "No local image pixels archived."),
        "manipulativeness": max_manip,
        "negative_example": not spans,
        "persuasive_intensity": max_intensity,
        "span_count": len(spans),
        "vulnerability_target": ",".join(vulnerability_targets) if vulnerability_targets else "",
    }
    return spans, document


def pending_assignments(database: Path, round_number: int, reviewer_id: str | None, limit: int | None) -> list[dict]:
    db = sqlite3.connect(database)
    db.row_factory = sqlite3.Row
    params: list[object] = [round_number]
    reviewer_clause = ""
    if reviewer_id:
        reviewer_clause = "AND a.reviewer_id=?"
        params.append(reviewer_id)
    limit_clause = ""
    if limit is not None:
        limit_clause = "LIMIT ?"
        params.append(limit)
    rows = db.execute(
        f"""SELECT a.record_id,a.reviewer_id,a.round,d.text,d.context_json
            FROM assignments a
            JOIN documents d ON d.record_id=a.record_id
            LEFT JOIN annotation_sets s
              ON s.record_id=a.record_id
             AND s.actor_id=a.reviewer_id
             AND s.layer='subagent'
             AND s.round=a.round
            WHERE a.role='subagent'
              AND a.status='pending'
              AND a.round=?
              AND s.id IS NULL
              {reviewer_clause}
            ORDER BY a.record_id,a.reviewer_id
            {limit_clause}""",
        params,
    ).fetchall()
    db.close()
    return [dict(row) for row in rows]


def run_pass(
    database: Path,
    round_number: int,
    reviewer_id: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    deliberated_second_pass: bool = False,
) -> dict:
    rows = pending_assignments(database, round_number, reviewer_id, limit)
    counts = {"assignments": len(rows), "submitted": 0, "negative": 0, "spans": 0}
    labels: dict[str, int] = {}
    for row in rows:
        context = json.loads(row["context_json"])
        spans, document = annotate_text(
            row["text"],
            context,
            row["reviewer_id"],
            int(row["round"]),
            deliberated_second_pass=deliberated_second_pass,
        )
        counts["negative"] += int(not spans)
        counts["spans"] += len(spans)
        for span in spans:
            labels[span["label"]] = labels.get(span["label"], 0) + 1
        if not dry_run:
            save_annotation(
                database,
                row["record_id"],
                row["reviewer_id"],
                "subagent",
                "submitted",
                spans,
                document=document,
                round=int(row["round"]),
            )
            counts["submitted"] += 1
    counts["labels"] = dict(sorted(labels.items()))
    counts["round"] = round_number
    counts["dry_run"] = dry_run
    counts["deliberated_second_pass"] = deliberated_second_pass
    return counts


def run(
    database: Path,
    round_number: int = 1,
    actor_id: str | None = None,
    limit: int | None = None,
    rounds: int | None = None,
    queue_output: Path = DEFAULT_QUEUE,
) -> dict:
    """Compatibility wrapper used by tests and full council orchestration."""
    if rounds is None:
        result = run_pass(database, round_number, reviewer_id=actor_id, limit=limit)
        return {
            **result,
            "actor_id": actor_id or "all",
            "assignments_saved": result["submitted"],
            "spans_saved": result["spans"],
            "negative_annotations": result["negative"],
        }

    aggregate: dict[str, object] = {
        "actor_id": actor_id or "all",
        "assignments_saved": 0,
        "negative_annotations": 0,
        "spans_saved": 0,
        "rounds": [],
    }
    round_results: list[dict] = aggregate["rounds"]  # type: ignore[assignment]
    for current_round in range(round_number, round_number + rounds):
        pass_result = run_pass(
            database,
            current_round,
            reviewer_id=actor_id,
            limit=limit,
            deliberated_second_pass=current_round > 1,
        )
        consensus = evaluate(
            database,
            round_number=current_round,
            create_next_round=current_round < round_number + rounds - 1,
        )
        queued = export_queue(database, queue_output, round_number=current_round)
        aggregate["assignments_saved"] = int(aggregate["assignments_saved"]) + int(pass_result["submitted"])
        aggregate["negative_annotations"] = int(aggregate["negative_annotations"]) + int(pass_result["negative"])
        aggregate["spans_saved"] = int(aggregate["spans_saved"]) + int(pass_result["spans"])
        round_results.append({"annotation": pass_result, "consensus": consensus, "queue_records": queued})
        if consensus["decisions"].get("pending", 0) == 0 and consensus["decisions"].get("second_pass", 0) == 0:
            break
    return {
        **aggregate,
        "round": round_number,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--rounds", type=int, help="Run annotation plus consensus for N rounds.")
    parser.add_argument("--queue-output", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--reviewer-id")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--deliberated-second-pass",
        action="store_true",
        help="For round >1, use a shared stricter post-disagreement rubric.",
    )
    parser.add_argument(
        "--print-actors",
        action="store_true",
        help="Print expected council actor IDs for this round and exit.",
    )
    args = parser.parse_args()
    if args.print_actors:
        print(json.dumps({"round": args.round, "actors": [actor_for_round(args.round, i) for i in range(3)]}))
        return 0
    if args.rounds:
        print(
            json.dumps(
                run(
                    args.database,
                    round_number=args.round,
                    actor_id=args.reviewer_id,
                    limit=args.limit,
                    rounds=args.rounds,
                    queue_output=args.queue_output,
                ),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    result = run_pass(
        args.database,
        args.round,
        reviewer_id=args.reviewer_id,
        limit=args.limit,
        dry_run=args.dry_run,
        deliberated_second_pass=args.deliberated_second_pass,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
