#!/usr/bin/env python3
"""Freeze the modeling corpus and prepare a deterministic annotation campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data/processed/modeling_manifest.jsonl"
DEFAULT_DIR = ROOT / "data/annotation"
DEFAULT_MODEL = ROOT / "models/manipulation_tfidf_ovr.joblib"
SPLIT_TARGETS = {"train": 0.70, "validation": 0.15, "test": 0.15}
PRIMARY = {"doplim", "locanto", "ciudadanuncios"}
COUNCIL_SIZE = 3
COUNCIL_AGREEMENT_THRESHOLD = 0.90


def canonical_text(record: dict) -> str:
    return f"{record.get('title', '')}\n{record.get('body_redacted', '')}"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def platform(record: dict) -> str:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    value = str(metadata.get("platform_family") or record.get("source_platform") or "other").lower()
    if "evis" in value:
        return "evisos"
    return next((p for p in ("doplim", "locanto", "ciudadanuncios", "facebook") if p in value), value)


def group_keys(record: dict, text_hash: str) -> list[str]:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    account = str(metadata.get("account_hash") or "").strip()
    repost = str(metadata.get("repost_group") or metadata.get("campaign_id") or "").strip()
    keys = [f"text:{text_hash}"]
    if account:
        keys.append(f"account:{account}")
    if repost:
        keys.append(f"repost:{repost}")
    return keys


class UnionFind:
    def __init__(self, size: int):
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        left, right = self.find(left), self.find(right)
        if left != right:
            self.parent[max(left, right)] = min(left, right)


def similarity_text(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.lower())
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"\[redacted_[^\]]+\]|\d+", " _ ", value)
    return re.sub(r"[^a-z_]+", " ", value).strip()


def shingles(text: str, width: int) -> set[str]:
    tokens = text.split()
    if len(tokens) < width:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[index:index + width]) for index in range(len(tokens) - width + 1)}


def char_ngrams(text: str, width: int = 5) -> set[str]:
    compact = re.sub(r"\s+", " ", text)
    return {compact[i:i + width] for i in range(max(1, len(compact) - width + 1))}


def jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / max(1, len(left | right))


def simhash(features: set[str]) -> int:
    weights = [0] * 64
    for feature in features:
        value = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "big")
        for bit in range(64):
            weights[bit] += 1 if value & (1 << bit) else -1
    return sum((1 << bit) for bit, weight in enumerate(weights) if weight >= 0)


def build_campaign_groups(rows: list[dict]) -> tuple[int, list[dict]]:
    """Link explicit identifiers and conservative near-template candidates."""
    union = UnionFind(len(rows))
    explicit: dict[str, int] = {}
    normalized: list[str] = []
    token_sets: list[set[str]] = []
    char_sets: list[set[str]] = []
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        for key in row.pop("_group_keys"):
            if key in explicit:
                union.union(index, explicit[key])
            else:
                explicit[key] = index
        norm = similarity_text(row["text"])
        tokens = shingles(norm, 3)
        chars = char_ngrams(norm)
        normalized.append(norm)
        token_sets.append(tokens)
        char_sets.append(chars)
        signature = simhash(tokens or chars)
        for band in range(8):
            buckets[(band, (signature >> (band * 8)) & 0xFF)].append(index)

    candidates: set[tuple[int, int]] = set()
    for members in buckets.values():
        # Very large buckets are generic and unsuitable as near-template evidence.
        if len(members) > 250:
            continue
        for offset, left in enumerate(members):
            for right in members[offset + 1:]:
                candidates.add((left, right))
    accepted: list[dict] = []
    for left, right in sorted(candidates):
        length_ratio = min(len(normalized[left]), len(normalized[right])) / max(
            1, len(normalized[left]), len(normalized[right])
        )
        if length_ratio < 0.72:
            continue
        token_score = jaccard(token_sets[left], token_sets[right])
        char_score = jaccard(char_sets[left], char_sets[right])
        if token_score >= 0.86 or (token_score >= 0.68 and char_score >= 0.84):
            union.union(left, right)
            accepted.append(
                {
                    "left_record_id": rows[left]["record_id"],
                    "right_record_id": rows[right]["record_id"],
                    "length_ratio": round(length_ratio, 4),
                    "token_trigram_jaccard": round(token_score, 4),
                    "character_5gram_jaccard": round(char_score, 4),
                    "decision": "accepted",
                }
            )

    members_by_root: dict[int, list[str]] = defaultdict(list)
    for index, row in enumerate(rows):
        members_by_root[union.find(index)].append(row["record_id"])
    for index, row in enumerate(rows):
        members = sorted(members_by_root[union.find(index)])
        row["campaign_group"] = "campaign:" + digest("\n".join(members).encode())[:20]
    return len(members_by_root), accepted


def assign_splits(rows: list[dict]) -> dict[str, str]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["campaign_group"]].append(row)
    counts = {name: Counter() for name in SPLIT_TARGETS}
    totals = Counter(row["platform"] for row in rows if row["platform"] in PRIMARY)
    result: dict[str, str] = {}
    ordered = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    for key, members in ordered:
        platforms = {member["platform"] for member in members}
        cohort = members[0]["platform"]
        if not platforms <= PRIMARY:
            chosen = "challenge"
        else:
            size = len(members)
            chosen = min(
                SPLIT_TARGETS,
                key=lambda split: (
                    (counts[split][cohort] + size) / max(1, totals[cohort]) - SPLIT_TARGETS[split],
                    sum(counts[split].values()),
                    split,
                ),
            )
            counts[chosen][cohort] += size
        result[key] = chosen
    return result


def select_pilot(rows: list[dict], size: int) -> set[str]:
    by_source: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_source[row["platform"]].append(row)
    selected: set[str] = set()
    sources = sorted(by_source)
    quotas = {source: size * len(items) // len(rows) for source, items in by_source.items()}
    for source in sorted(sources, key=lambda s: (-len(by_source[s]), s)):
        for row in sorted(by_source[source], key=lambda r: r["record_id"])[: quotas[source]]:
            selected.add(row["record_id"])
    for row in sorted(rows, key=lambda r: digest(r["record_id"].encode())):
        if len(selected) >= min(size, len(rows)):
            break
        selected.add(row["record_id"])
    return selected


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def create_db(path: Path, rows: list[dict], metadata: dict, pilot: set[str], batch_size: int) -> None:
    if path.exists():
        path.unlink()
    db = sqlite3.connect(path)
    db.executescript(
        """
        PRAGMA foreign_keys=ON;
        CREATE TABLE campaign_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE documents(
          record_id TEXT PRIMARY KEY, corpus_version TEXT NOT NULL, platform TEXT NOT NULL,
          split_name TEXT NOT NULL, campaign_group TEXT NOT NULL, text TEXT NOT NULL,
          text_hash TEXT NOT NULL, context_json TEXT NOT NULL, is_pilot INTEGER NOT NULL,
          batch_id TEXT NOT NULL
        );
        CREATE TABLE assignments(
          record_id TEXT NOT NULL REFERENCES documents(record_id), reviewer_id TEXT NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('human','subagent','adjudicator')),
          status TEXT NOT NULL DEFAULT 'pending', round INTEGER NOT NULL DEFAULT 1,
          PRIMARY KEY(record_id, reviewer_id, role, round)
        );
        CREATE TABLE annotation_sets(
          id INTEGER PRIMARY KEY, record_id TEXT NOT NULL REFERENCES documents(record_id),
          actor_id TEXT NOT NULL, layer TEXT NOT NULL
            CHECK(layer IN ('human','subagent','adjudicated')),
          state TEXT NOT NULL CHECK(state IN ('draft','submitted','adjudicated')),
          round INTEGER NOT NULL DEFAULT 1, text_hash TEXT NOT NULL, document_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          UNIQUE(record_id, actor_id, layer, round)
        );
        CREATE TABLE spans(
          id INTEGER PRIMARY KEY, annotation_set_id INTEGER NOT NULL REFERENCES annotation_sets(id),
          label TEXT NOT NULL, segments_json TEXT NOT NULL, exact_text TEXT NOT NULL,
          rationale TEXT NOT NULL DEFAULT '', intensity INTEGER CHECK(intensity BETWEEN 0 AND 4),
          manipulativeness INTEGER CHECK(manipulativeness BETWEEN 0 AND 3),
          harm_risk INTEGER CHECK(harm_risk BETWEEN 0 AND 3), explicitness TEXT,
          vulnerability_target TEXT, provenance TEXT NOT NULL
        );
        CREATE INDEX documents_group_idx ON documents(campaign_group);
        CREATE INDEX annotation_record_idx ON annotation_sets(record_id);
        CREATE TABLE council_consensus(
          record_id TEXT NOT NULL REFERENCES documents(record_id),
          round INTEGER NOT NULL,
          council_size INTEGER NOT NULL,
          submitted_count INTEGER NOT NULL,
          agreement REAL NOT NULL,
          decision TEXT NOT NULL CHECK(decision IN ('pending','accepted','second_pass')),
          consensus_signature TEXT,
          accepted_actor_id TEXT,
          updated_at TEXT NOT NULL,
          PRIMARY KEY(record_id, round)
        );
        """
    )
    db.executemany(
        "INSERT INTO campaign_metadata VALUES (?, ?)",
        [(key, json.dumps(value, ensure_ascii=False, sort_keys=True)) for key, value in metadata.items()],
    )
    ordered = sorted(rows, key=lambda r: (not (r["record_id"] in pilot), r["platform"], r["record_id"]))
    for index, row in enumerate(ordered):
        batch = f"{'pilot' if row['record_id'] in pilot else 'main'}-{index // batch_size + 1:03d}"
        db.execute(
            "INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                row["record_id"], metadata["corpus_version"], row["platform"], row["split"],
                row["campaign_group"], row["text"], row["text_hash"],
                json.dumps(row["context"], ensure_ascii=False, sort_keys=True),
                int(row["record_id"] in pilot), batch,
            ),
        )
        for reviewer in ("reviewer_a", "reviewer_b"):
            db.execute(
                "INSERT INTO assignments(record_id,reviewer_id,role) VALUES (?,?,?)",
                (row["record_id"], reviewer, "human"),
            )
        for agent in ("subagent_a", "subagent_b", "subagent_c"):
            db.execute(
                "INSERT INTO assignments(record_id,reviewer_id,role) VALUES (?,?,?)",
                (row["record_id"], agent, "subagent"),
            )
    db.commit()
    db.close()


def prepare(
    manifest: Path, output_dir: Path, pilot_size: int, batch_size: int, model: Path | None = None
) -> dict:
    raw = manifest.read_bytes()
    records = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    rows = []
    for record in records:
        text = canonical_text(record)
        text_hash = digest(text.encode("utf-8"))
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        image_count = metadata.get("image_count")
        context = {
            key: metadata.get(key)
            for key in (
                "is_paid_or_premium_marker", "is_featured_marker", "followers_count",
                "facebook_reactions_approx", "facebook_comments_approx", "image_count",
                "quality_score", "raw_size_bucket", "account_hash", "posting_hash",
                "normalized_text_hash",
            )
            if metadata.get(key) is not None
        }
        context.update(
            {
                "source_platform": record.get("source_platform"),
                "source_url_hash": record.get("source_url_hash"),
                "raw_archive_ref": record.get("raw_archive_ref"),
                "collected_at": record.get("collected_at"),
                "image_available": bool(image_count and int(image_count or 0) > 0),
                "image_review_note": (
                    "Image count is available from the archived page metadata; local image pixels are not archived."
                ),
            }
        )
        rows.append(
            {
                "record_id": str(record["record_id"]),
                "platform": platform(record),
                "text": text,
                "text_hash": text_hash,
                "_group_keys": group_keys(record, text_hash),
                "context": {key: value for key, value in context.items() if value is not None},
            }
        )
    group_count, similarity_links = build_campaign_groups(rows)
    manifest_hash = digest(raw)
    corpus_version = f"manipsych-{len(rows)}-{manifest_hash[:12]}"
    splits = assign_splits(rows)
    for row in rows:
        row["split"] = splits[row["campaign_group"]]
    pilot = select_pilot(rows, pilot_size)
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    split_counts = Counter(row["split"] for row in rows)
    source_counts = Counter(row["platform"] for row in rows)
    metadata = {
        "corpus_version": corpus_version,
        "manifest_sha256": manifest_hash,
        "model_sha256": digest(model.read_bytes()) if model and model.exists() else None,
        "records": len(rows),
        "source_counts": dict(sorted(source_counts.items())),
        "split_counts": dict(sorted(split_counts.items())),
        "campaign_groups": group_count,
        "near_template_links_accepted": len(similarity_links),
        "similarity_method": {
            "normalization": "NFKD lowercase; digits and redaction tokens masked",
            "candidate_generation": "eight 8-bit SimHash bands over token trigrams",
            "acceptance": "length_ratio>=0.72 and (token_jaccard>=0.86 or token_jaccard>=0.68 and char5_jaccard>=0.84)",
        },
        "pilot_records": len(pilot),
        "generated_at": generated,
        "text_definition": "title + newline + body_redacted; UTF-8; offsets are Python/Unicode code points",
        "offset_convention": "zero-based, end-exclusive",
        "gold_policy": "Only layer=adjudicated and state=adjudicated is gold.",
        "subagent_council": {
            "round_1_reviewers": ["subagent_a", "subagent_b", "subagent_c"],
            "council_size": COUNCIL_SIZE,
            "agreement_threshold": COUNCIL_AGREEMENT_THRESHOLD,
            "pass_rule": "3 of 3 exact normalized subagent annotation signatures must agree; otherwise queue round+1.",
            "candidate_policy": "Council output is suggestion data unless separately adjudicated.",
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "corpus_snapshot.json", metadata)
    with (output_dir / "documents.jsonl").open("w", encoding="utf-8") as handle:
        for row in sorted(rows, key=lambda r: r["record_id"]):
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    with (output_dir / "similarity_links.jsonl").open("w", encoding="utf-8") as handle:
        for link in sorted(similarity_links, key=lambda item: (item["left_record_id"], item["right_record_id"])):
            handle.write(json.dumps(link, ensure_ascii=False, sort_keys=True) + "\n")
    create_db(output_dir / "annotations.sqlite3", rows, metadata, pilot, batch_size)
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--pilot-size", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    args = parser.parse_args()
    result = prepare(args.manifest, args.output_dir, args.pilot_size, args.batch_size, args.model)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
