#!/usr/bin/env python3
"""Rebuild the processed ad manifest from locally archived raw HTML."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.redact_pii import redact_text
from tools.scrape_ads import is_access_interstitial, text_from_html


DEFAULT_RAW_DIR = ROOT / "data" / "raw" / "ads"
DEFAULT_MANIFEST = ROOT / "data" / "processed" / "ad_manifest.jsonl"
DEFAULT_SUMMARY = ROOT / "reports" / "raw_rebuild_summary.json"

TARGET_RE = re.compile(
    r"ayuda\s*econ[oó]mica|apoyo\s*econ[oó]mico|ayudo\s*econ[oó]micamente|"
    r"brindo\s+(?:ayuda|apoyo)|doy\s+(?:ayuda|apoyo)|ofrezco\s+(?:ayuda|apoyo)",
    re.I,
)
OFFER_RE = re.compile(
    r"\b(brindo|doy|ofrezco|se brinda|brinda apoyo|le ayudo|te brindo|"
    r"hombre maduro|caballero|profesional)\b",
    re.I,
)
BAD_SEEKER_RE = re.compile(
    r"busco\s+(ayuda|apoyo|chica|universitaria|estudiante|señorita|senorita)",
    re.I,
)
# Off-target ads that still mention ayuda/apoyo económico (charity, jobs, pets, bandas)
OFFTOPIC_RE = re.compile(
    r"\b(ong|perros?\s+de\s+la\s+calle|animales?\s+desprotej|refugio\s+de\s+anim|"
    r"vivienda\s*,?\s*comida|cuidar\s+se[nñ]ora\s+mayor|baterista|vocalista|"
    r"formar\s+banda|grupo\s+covers|aluzinc|drywall|shih\s*tzu|cachorro|"
    r"ofertas?\s+de\s+trabajo|asistente\s+administrativo|clases?\s+de\s+matem|"
    r"refuerzo\s+escolar|apoyo\s+escolar|apoyo\s+acad[eé]mico|apoyo\s+legal)\b",
    re.I,
)
CONTACT_RE = re.compile(
    r"\b\+?51\s?\d{3}\s?\d{3}\s?\d{3}\b|\b9\d{8}\b|"
    r"[\w.+-]+@[\w-]+\.[\w.-]+|\b9(?:[\s.-]*\d){7,}\b",
    re.I,
)


@dataclass(frozen=True)
class RebuildCandidate:
    raw_path: Path
    platform_family: str
    canonical: str
    title: str
    body: str
    metadata: dict[str, object]


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_token(value: str) -> str:
    return "h_" + hash_text(value)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def safe_int(value: str) -> int | None:
    digits = re.sub(r"[^\d]", "", value or "")
    return int(digits) if digits else None


def meta_content(soup: BeautifulSoup, selector: str) -> str:
    node = soup.select_one(selector)
    return normalize_space(node.get("content", "")) if node else ""


def canonical_url(soup: BeautifulSoup) -> str:
    node = soup.select_one('link[rel="canonical"]')
    if node and node.get("href"):
        return normalize_space(node["href"])
    node = soup.select_one('meta[property="og:url"]')
    if node and node.get("content"):
        return normalize_space(node["content"])
    return ""


def platform_family_for(path: Path, soup: BeautifulSoup, html: str, canonical: str) -> str:
    lowered_name = path.name.lower()
    host = urlparse(canonical).netloc.lower() if canonical else ""
    html_head = html[:250000].lower()
    if "locanto.com.pe" in host or "yalwa.v." in html or "posting_listing" in html_head:
        return "locanto"
    if "doplim.com.pe" in host or "doplim" in lowered_name or "cnt-list_ads" in html_head:
        return "doplim"
    if (
        "facebook.com" in host
        or lowered_name.startswith(("facebook_", "fb_", "mani_facebook", "facebook_public", "facebook_group"))
    ):
        return "facebook"
    if "ciudadanuncios" in host or "ciudadanuncios" in lowered_name:
        return "ciudadanuncios"
    if "evisex" in host or "evisex" in lowered_name:
        return "evisos"  # same family / strict gates
    if "evisos" in host or lowered_name.startswith(("evisos_", "evisos")):
        return "evisos"
    return "other"


def source_platform(platform_family: str, canonical: str, raw_name: str) -> str:
    if platform_family == "locanto":
        return "Locanto Peru"
    if platform_family == "doplim":
        return "Doplim Peru"
    if platform_family == "facebook":
        return "Facebook Public"
    if platform_family == "ciudadanuncios":
        return "Ciudad Anuncios Peru"
    if platform_family == "evisos":
        return "Evisos/Evisex Peru"
    return f"Other Public ({raw_name.split('_', 1)[0]})"


def first_text(soup: BeautifulSoup, selectors: list[str]) -> str:
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            text = normalize_space(node.get_text(" ", strip=True))
            if text:
                return text
    return ""


def longest_text(soup: BeautifulSoup, selectors: list[str]) -> str:
    texts: list[str] = []
    for selector in selectors:
        for node in soup.select(selector):
            text = normalize_space(node.get_text(" ", strip=True))
            if text:
                texts.append(text)
    return max(texts, key=len) if texts else ""


def extract_title(soup: BeautifulSoup, platform_family: str) -> str:
    if platform_family == "facebook":
        title = meta_content(soup, 'meta[property="og:title"]')
        if title:
            return title
    title = first_text(soup, ["h1", ".posting_title", ".cnt-title", ".bp_ad_title"])
    if title:
        return title
    if soup.title:
        return normalize_space(soup.title.get_text(" ", strip=True))
    return ""


def extract_body(soup: BeautifulSoup, html: str, platform_family: str) -> str:
    if platform_family == "locanto":
        body = longest_text(
            soup,
            [
                ".simple__description",
                ".js-simple_vapposting_description .simple__first",
                ".organism__item--vapposting",
            ],
        )
        if body:
            return body
    if platform_family == "doplim":
        body = longest_text(soup, [".descripcion", ".description", ".cnt_description", ".text-desc"])
        if body:
            return body
    if platform_family == "facebook":
        body = meta_content(soup, 'meta[property="og:description"]')
        if body:
            return body
        body = longest_text(soup, [".userContent", "[data-ad-preview='message']", "div[data-ad-preview]"])
        if body:
            return body
    if platform_family == "ciudadanuncios":
        # Prefer main listing block; strip related-ad sidebars that pollute TARGET gates
        full = text_from_html(html)
        m = re.search(
            r"Detalles del Anuncio(.*?)(Anuncios relacionados|Reportar el anuncio|Publicar|Iniciar sesión|$)",
            full,
            re.I | re.S,
        )
        if m and len(normalize_space(m.group(1))) > 40:
            return normalize_space(m.group(1))[:10000]
        body = longest_text(soup, [".description", ".ad-description", "#description", "article", ".content"])
        if body:
            return body
    if platform_family == "evisos":
        body = longest_text(
            soup,
            [
                ".description",
                "#description",
                ".ad-description",
                ".detail-description",
                "div[itemprop='description']",
            ],
        )
        if body:
            return body
    body = meta_content(soup, 'meta[property="og:description"]') or meta_content(soup, 'meta[name="description"]')
    if body:
        return body
    return text_from_html(html)


def locanto_metadata(soup: BeautifulSoup, html: str) -> dict[str, object]:
    metadata: dict[str, object] = {}
    posting = re.search(r"yalwa\.v\.posting_id\s*=\s*'(\d+)'", html)
    user = re.search(r"yalwa\.v\.userID_viewed\s*=\s*'(\d+)'", html)
    if posting:
        metadata["posting_hash"] = hash_token(posting.group(1))
    if user:
        metadata["account_hash"] = hash_token(user.group(1))
    metadata["is_paid_or_premium_marker"] = bool(re.search(r"yalwa\.v\.pf_posting\s*=\s*true", html, re.I))
    follower_text = first_text(soup, [".js-followers_counter", ".userprofile__sublabel"])
    follower_match = re.search(r"(\d[\d,. ]*)\s*Seguidores", follower_text, re.I)
    if follower_match:
        metadata["followers_count"] = safe_int(follower_match.group(1))
    image_counts = [safe_int(value) for value in re.findall(r"posting_listing__counter[^>]*>\s*(\d+)\s*<", html)]
    image_counts = [value for value in image_counts if value is not None]
    if image_counts:
        metadata["image_count"] = max(image_counts)
    city = first_text(soup, [".location", ".vap_address", ".breadcrumbs"])
    if city:
        metadata["location_hint_hash"] = hash_token(city[:120].lower())
    return metadata


def doplim_metadata(soup: BeautifulSoup, html: str, body: str) -> dict[str, object]:
    metadata: dict[str, object] = {
        "is_paid_or_premium_marker": bool(re.search(r"cnt_user_premium|getUserPremium|user_premium", html, re.I)),
        "is_featured_marker": bool(re.search(r"ads_featured|Destacar Anuncio|\bfeatured\b", html, re.I)),
    }
    follower_match = re.search(r"(\d[\d,. ]*)\s*Seguidores", body, re.I)
    if follower_match:
        metadata["followers_count"] = safe_int(follower_match.group(1))
    return metadata


def facebook_metadata(soup: BeautifulSoup, body: str) -> dict[str, object]:
    metadata: dict[str, object] = {}
    reactions = re.search(r"(\d[\d,. ]*)\s*(me gusta|reaccion(?:es|aron)?|likes?|reactions?)", body, re.I)
    comments = re.search(r"(\d[\d,. ]*)\s*(comentarios?|comments?)", body, re.I)
    if reactions:
        metadata["facebook_reactions_approx"] = safe_int(reactions.group(1))
    if comments:
        metadata["facebook_comments_approx"] = safe_int(comments.group(1))
    group = ""
    canonical = meta_content(soup, 'meta[property="og:url"]')
    if "/groups/" in canonical:
        group = canonical.split("/groups/", 1)[1].split("/", 1)[0]
    if group:
        metadata["facebook_group_hash"] = hash_token(group)
        metadata["facebook_group_present"] = True
    return metadata


def quality_score(metadata: dict[str, object]) -> float:
    score = 0.5
    if metadata.get("is_paid_or_premium_marker"):
        score += 0.1
    if metadata.get("is_featured_marker"):
        score += 0.1
    if int(metadata.get("followers_count") or 0) > 0:
        score += 0.1
    if int(metadata.get("image_count") or 0) > 1:
        score += 0.05
    if int(metadata.get("facebook_reactions_approx") or 0) > 0:
        score += 0.1
    if int(metadata.get("facebook_comments_approx") or 0) > 0:
        score += 0.1
    return min(round(score, 2), 1.0)


def size_bucket(byte_count: int) -> str:
    if byte_count < 2_000:
        return "lt_2kb"
    if byte_count < 10_000:
        return "2kb_10kb"
    if byte_count < 50_000:
        return "10kb_50kb"
    if byte_count < 100_000:
        return "50kb_100kb"
    if byte_count < 500_000:
        return "100kb_500kb"
    return "gt_500kb"


def should_reject_text(title: str, body: str) -> str | None:
    joined = f"{title}\n{body}"
    if len(normalize_space(body)) < 30:
        return "low_body_text"
    if not TARGET_RE.search(joined):
        return "no_target_terms"
    if OFFTOPIC_RE.search(joined) and not re.search(
        r"\b(brindo|doy|ofrezco)\s+(ayuda|apoyo)\b|"
        r"se\s+brinda\s+(ayuda|apoyo)|caballero|señoritas?\s+(universit|estudi)",
        joined,
        re.I,
    ):
        # Charity/job/pet/band noise that only incidentally mentions apoyo económico
        return "offtopic_context"
    if BAD_SEEKER_RE.search(joined) and not OFFER_RE.search(joined):
        return "seeker_only"
    return None


def build_candidate(path: Path) -> tuple[RebuildCandidate | None, str | None]:
    html = path.read_text(encoding="utf-8", errors="ignore")
    if len(html) < 500:
        return None, "tiny_or_corrupt"
    title_probe = ""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if title_match:
        title_probe = normalize_space(title_match.group(1)).lower()
    if is_access_interstitial(html) or ("un momento" in title_probe and re.search(r"captcha|verificando|cloudflare", html[:5000], re.I)):
        return None, "access_interstitial"

    soup = BeautifulSoup(html, "lxml")
    canonical = canonical_url(soup)
    platform_family = platform_family_for(path, soup, html, canonical)
    title = extract_title(soup, platform_family)
    body = extract_body(soup, html, platform_family)
    reject = should_reject_text(title, body)
    if reject:
        return None, reject

    metadata: dict[str, object] = {}
    if platform_family == "locanto":
        metadata.update(locanto_metadata(soup, html))
    elif platform_family == "doplim":
        metadata.update(doplim_metadata(soup, html, body))
    elif platform_family == "facebook":
        metadata.update(facebook_metadata(soup, body))
    metadata["platform_family"] = platform_family
    metadata["raw_size_bucket"] = size_bucket(path.stat().st_size)
    metadata["raw_rebuild"] = "raw_v1"
    metadata["quality_score"] = quality_score(metadata)
    if canonical:
        metadata["canonical_url_hash"] = hash_token(canonical)

    return RebuildCandidate(
        raw_path=path,
        platform_family=platform_family,
        canonical=canonical,
        title=title,
        body=body,
        metadata=metadata,
    ), None


def record_from_candidate(candidate: RebuildCandidate, root: Path) -> tuple[dict[str, object] | None, str | None]:
    canonical_or_raw = candidate.canonical or candidate.raw_path.stem
    normalized_text = normalize_space(f"{candidate.title}\n{candidate.body}").lower()
    title = redact_text(candidate.title)[:500]
    body = redact_text(candidate.body)[:10000]
    raw_ref = str(candidate.raw_path.relative_to(root))
    metadata = dict(candidate.metadata)
    metadata["normalized_text_hash"] = hash_token(normalized_text[:4000])
    metadata["collector"] = "tools/rebuild_manifest_from_raw.py"
    record = {
        "record_id": hash_token(canonical_or_raw),
        "source_platform": source_platform(candidate.platform_family, candidate.canonical, candidate.raw_path.name),
        "source_url_hash": hash_token(canonical_or_raw),
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "title": title,
        "body_redacted": body,
        "raw_archive_ref": raw_ref,
        "metadata": metadata,
    }
    if CONTACT_RE.search(json.dumps(record, ensure_ascii=False)):
        return None, "residual_contact_pii"
    return record, None


def rebuild_manifest(raw_dir: Path, manifest: Path, summary_path: Path, backup: bool = True, root: Path = ROOT) -> dict[str, object]:
    raw_paths = sorted(raw_dir.glob("*.html"))
    records: list[dict[str, object]] = []
    reject_counts: Counter[str] = Counter()
    platform_counts: Counter[str] = Counter()
    signal_counts: Counter[str] = Counter()
    seen_ids: set[str] = set()
    seen_raw_refs: set[str] = set()
    seen_text_hashes: set[str] = set()

    for raw_path in raw_paths:
        candidate, reason = build_candidate(raw_path)
        if reason:
            reject_counts[reason] += 1
            continue
        assert candidate is not None
        record, reason = record_from_candidate(candidate, root)
        if reason:
            reject_counts[reason] += 1
            continue
        assert record is not None
        text_hash = str(record["metadata"]["normalized_text_hash"])
        if record["record_id"] in seen_ids:
            reject_counts["duplicate_record_id"] += 1
            continue
        if record["raw_archive_ref"] in seen_raw_refs:
            reject_counts["duplicate_raw_ref"] += 1
            continue
        if text_hash in seen_text_hashes:
            reject_counts["duplicate_normalized_text"] += 1
            continue
        seen_ids.add(str(record["record_id"]))
        seen_raw_refs.add(str(record["raw_archive_ref"]))
        seen_text_hashes.add(text_hash)
        records.append(record)
        platform_counts[str(record["metadata"].get("platform_family", "other"))] += 1
        for key in (
            "is_paid_or_premium_marker",
            "is_featured_marker",
            "followers_count",
            "image_count",
            "facebook_reactions_approx",
            "facebook_comments_approx",
            "facebook_group_present",
        ):
            if record["metadata"].get(key):
                signal_counts[key] += 1

    manifest.parent.mkdir(parents=True, exist_ok=True)
    if backup and manifest.exists():
        backup_path = manifest.with_name(f"{manifest.name}.raw_rebuild_bak_{int(time.time())}")
        shutil.copy2(manifest, backup_path)
    manifest.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")

    summary = {
        "raw_files_scanned": len(raw_paths),
        "records_written": len(records),
        "platform_counts": dict(platform_counts),
        "quality_signal_counts": dict(signal_counts),
        "reject_counts": dict(reject_counts),
        "manifest": str(manifest.relative_to(root)) if manifest.is_relative_to(root) else str(manifest),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()
    summary = rebuild_manifest(args.raw_dir, args.manifest, args.summary, backup=not args.no_backup)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
