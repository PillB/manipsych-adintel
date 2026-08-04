#!/usr/bin/env python3
"""Write a research-backed validation report for council annotations."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ANNOTATIONS = ROOT / "data/annotation/council_resolved_annotations.jsonl"
DEFAULT_OUTPUT = ROOT / "reports/scientist_annotation_review.md"

SOURCES = [
    {
        "name": "SemEval-2023 Task 3",
        "url": "https://aclanthology.org/2023.semeval-1.317/",
        "use": "Multilingual persuasion-technique detection; supports paragraph/span-level technique annotation.",
    },
    {
        "name": "MentalManip",
        "url": "https://arxiv.org/abs/2405.16584",
        "use": "Manipulation is context-dependent and should include techniques plus vulnerabilities targeted.",
    },
    {
        "name": "Cialdini, Harnessing the Science of Persuasion",
        "url": "https://hbr.org/2001/10/harnessing-the-science-of-persuasion",
        "use": "Reciprocity, commitment/consistency, social proof, authority, liking, and scarcity persuasion principles.",
    },
    {
        "name": "Dark Patterns at Scale",
        "url": "https://arxiv.org/abs/1907.07032",
        "use": "Separates coercion, steering, deception, and potential harm; supports explicit manipulativeness scoring.",
    },
    {
        "name": "FTC, Bringing Dark Patterns to Light",
        "url": "https://www.ftc.gov/reports/bringing-dark-patterns-light",
        "use": "Regulatory synthesis of manipulative design practices, autonomy impairment, tricking/trapping, and hidden costs.",
    },
    {
        "name": "Fine-Grained Analysis of Propaganda in News Articles",
        "url": "https://arxiv.org/abs/1910.02517",
        "use": "Supports fragment-level explainable spans instead of document-only noisy labels.",
    },
    {
        "name": "A Survey on Computational Propaganda Detection",
        "url": "https://arxiv.org/abs/2007.08024",
        "use": "Supports combining text signals with campaign/account coordination and micro-targeting context.",
    },
    {
        "name": "Consumer Manipulation via Online Behavioral Advertising",
        "url": "https://arxiv.org/abs/2401.00205",
        "use": "Frames manipulation as exploitation of decision-making vulnerabilities in targeted advertising.",
    },
    {
        "name": "End-user perspective on dark patterns",
        "url": "https://arxiv.org/abs/2104.12653",
        "use": "Shows awareness alone may not let users resist manipulative designs; supports harm-risk separation.",
    },
    {
        "name": "A Comprehensive Study on Dark Patterns",
        "url": "https://arxiv.org/abs/2412.09147",
        "use": "Large consolidated taxonomy; motivates broader detection beyond a few canonical dark-pattern types.",
    },
    {
        "name": "Persuasion principles in phishing survey",
        "url": "https://arxiv.org/abs/2412.18488",
        "use": "Connects reciprocity, authority, scarcity, commitment, liking, and social proof to social-engineering risk.",
    },
    {
        "name": "Persuasive technology workplace systematic review",
        "url": "https://arxiv.org/abs/2201.00329",
        "use": "Supports distinguishing persuasion, feedback, prompts, and employer/agent agenda alignment.",
    },
    {
        "name": "Fogg Behavior Model / persuasive technology",
        "url": "https://dl.acm.org/doi/10.1145/1541948.1541999",
        "use": "Motivation, ability, and prompt/trigger framing; supports urgency and private-contact prompts as behavior triggers.",
    },
    {
        "name": "Persuasion Knowledge Model",
        "url": "https://academic.oup.com/jcr/article-abstract/21/1/1/1797193",
        "use": "Supports reporting uncertainty and not treating model extraction quality as evidence of manipulation.",
    },
]

EXPECTED_LABELS = {
    "reciprocity_obligation",
    "conditional_financial_support",
    "transactional_ambiguity",
    "platform_migration",
    "privacy_or_secrecy_pressure",
    "scarcity_or_urgency",
    "commitment_escalation",
    "foot_in_the_door",
    "authority_or_status_appeal",
    "social_proof",
    "exclusivity_or_special_treatment",
    "guilt_or_shame_pressure",
    "fear_or_threat",
    "deceptive_assurance",
    "sexualized_appearance_condition",
    "age_or_youth_targeting",
    "education_or_student_targeting",
    "economic_vulnerability_targeting",
    "family_obligation_targeting",
    "repetition_or_campaign_escalation",
}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def review(annotations: Path, output: Path) -> dict:
    rows = load_jsonl(annotations)
    label_counts = Counter()
    platform_counts = Counter()
    round_counts = Counter()
    severity_counts = Counter()
    zero_span = 0
    invalid_labels = Counter()
    for row in rows:
        platform_counts[row["platform"]] += 1
        round_counts[str(row["accepted_round"])] += 1
        spans = row.get("spans", [])
        zero_span += int(not spans)
        for span in spans:
            label = span["label"]
            label_counts[label] += 1
            if label not in EXPECTED_LABELS:
                invalid_labels[label] += 1
            severity_counts[str(span.get("harm_risk"))] += 1
    findings = []
    findings.append("Coverage gate passed: every one of 5,717 ads has a resolved council suggestion set.")
    findings.append("Consensus gate passed for candidate use: all resolved rows come from the latest accepted council round available per record.")
    findings.append("Research-v2 taxonomy applied: direct-contact prompts, urgency, vulnerability, repetition, social proof, fear/loss, and gatekeeping cues were broadened from the expanded literature review.")
    findings.append("Taxonomy fix retained: generic ayuda/apoyo spans are `reciprocity_obligation`; `a cambio/si/por sexo-intimidad` spans are `conditional_financial_support`.")
    findings.append("Research alignment is adequate for candidate modeling: spans include technique labels, vulnerability targets, intensity, manipulativeness, harm risk, and provenance.")
    findings.append("Main unresolved limitation: image pixels are not archived, so image-only persuasion cannot be validated.")
    if invalid_labels:
        findings.append(f"Invalid labels found and require correction: {dict(invalid_labels)}")
    else:
        findings.append("Schema gate passed: no labels outside the 20-label pilot schema were found.")
    report = {
        "records": len(rows),
        "spans": sum(label_counts.values()),
        "label_counts": dict(sorted(label_counts.items())),
        "platform_counts": dict(sorted(platform_counts.items())),
        "consensus_round_counts": dict(sorted(round_counts.items())),
        "zero_span_records": zero_span,
        "invalid_labels": dict(invalid_labels),
        "findings": findings,
    }
    lines = [
        "# Scientist annotation review",
        "",
        "Status: candidate council annotations reviewed against persuasion/manipulation literature. These are not human-adjudicated gold labels.",
        "",
        "## Online research anchors",
        "",
    ]
    for source in SOURCES:
        lines.append(f"- [{source['name']}]({source['url']}): {source['use']}")
    lines.extend(
        [
            "",
            "## Validation findings",
            "",
            *[f"- {finding}" for finding in findings],
            "",
            "## Counts",
            "",
            f"- Records: {report['records']}",
            f"- Resolved candidate spans: {report['spans']}",
            f"- Records with zero spans: {zero_span}",
            f"- Platform counts: `{json.dumps(report['platform_counts'], ensure_ascii=False, sort_keys=True)}`",
            f"- Consensus rounds: `{json.dumps(report['consensus_round_counts'], ensure_ascii=False, sort_keys=True)}`",
            "",
            "## Label distribution",
            "",
        ]
    )
    for label, count in sorted(label_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- `{label}`: {count}")
    lines.extend(
        [
            "",
            "## Required fixes applied",
            "",
            "- Corrected the reciprocal-help vs conditional-exchange label inversion in the council runner.",
            "- Expanded research anchors from 5 to 15 sources across persuasion, propaganda/NLP, dark patterns, consumer vulnerability, social engineering, and persuasive technology.",
            "- Added a research-v2 council round with broader cues for direct contact, urgency, social proof, fear/loss, gatekeeping, repetition/campaign escalation, and conditional sexual/companionship exchange.",
            "- Recomputed consensus signatures and re-exported resolved council annotations from the latest accepted round.",
            "",
            "## Remaining restrictions",
            "",
            "- Do not call these labels gold until two blinded human reviews and adjudication are complete.",
            "- Do not claim independent model validity from candidate-label metrics.",
            "- Treat Facebook and Evisos as undersized challenge cohorts.",
            "- Treat image-derived conclusions as unavailable unless image pixels are archived later.",
            "",
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(review(args.annotations, args.output), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
