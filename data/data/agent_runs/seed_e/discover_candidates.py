#!/usr/bin/env python3
import html
import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[3]
OUT_DATA = ROOT / "data/agent_runs/seed_e/candidate_seeds.jsonl"
OUT_SUMMARY = ROOT / "reports/agent_runs/seed_e/summary.json"

SEARCH_QUERIES_USED = [
    'site:doplim.com.pe inurl:.html "ayuda economica" "brindo" Peru',
    'site:doplim.com.pe inurl:.html "apoyo economico" "ofrezco" Peru',
    'site:facebook.com/groups "ayuda economica" "brindo" "Peru"',
    'site:facebook.com/groups "apoyo economico" "caballero" "Peru"',
    '"Brindo Ayuda Económica" "Doplim" "Peru"',
    '"doy ayuda economica" "Doplim" "Peru"',
    '"ayuda económica" "doplim.com.pe" "hombre"',
    '"se brinda ayuda economica" "Doplim"',
    '"brindo ayuda economica" "facebook.com/groups"',
    '"doy ayuda economica" "facebook.com/groups"',
    '"apoyo economico" "facebook.com/groups" "sugar daddy"',
    '"ayuda económica" "facebook.com/groups" "caballero"',
]

URL_RE = re.compile(r"https?://[^\s\"'<>\\]+", re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
OG_TITLE_RE = re.compile(
    r"<meta[^>]+(?:property|name)=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)[\"']",
    re.I | re.S,
)
OG_DESC_RE = re.compile(
    r"<meta[^>]+(?:property|name)=[\"']og:description[\"'][^>]+content=[\"']([^\"']+)[\"']",
    re.I | re.S,
)

ECON_RE = re.compile(
    r"ayuda\s+econ[oó]mica|apoyo\s+econ[oó]mico|ayudo\s+econ[oó]micamente|brindo\s+apoyo|doy\s+apoyo|doy\s+ayuda",
    re.I,
)
MALE_RE = re.compile(
    r"\b(brindo|brinda|doy|ofrezco|se\s+brinda|caballero|empresario|sugar\s+daddy|hombre|maduro)\b",
    re.I,
)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?51[\s.-]*)?(?:9[\s.-]*)?\d(?:[\s.-]*\d){7,10}(?!\d)")
LONG_NUMBER_RE = re.compile(r"(?<!\d)\d{8,}(?!\d)")


def norm_url(url):
    url = html.unescape(url).replace("\\/", "/")
    url = url.rstrip(").,;]}'\"")
    url = url.replace("&amp;", "&")
    parsed = urlparse(url)
    if parsed.netloc.lower().endswith("doplim.com.pe") and parsed.path.lower().endswith(".html"):
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    if "facebook.com" in parsed.netloc.lower():
        keep = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            if key in {"story_fbid", "id"}:
                keep.append((key, value))
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", urlencode(keep), ""))
    return url


def strip_tags(value):
    value = re.sub(r"<script\b.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def redact(value):
    value = URL_RE.sub("[REDACTED_URL]", value)
    value = EMAIL_RE.sub("[REDACTED_EMAIL]", value)
    value = PHONE_RE.sub("[REDACTED_PHONE]", value)
    value = LONG_NUMBER_RE.sub("[REDACTED_NUMBER]", value)
    return value


def title_from_blob(blob):
    for pat in (OG_TITLE_RE, TITLE_RE):
        m = pat.search(blob)
        if m:
            return strip_tags(m.group(1))[:240]
    return ""


def desc_from_blob(blob):
    m = OG_DESC_RE.search(blob)
    if m:
        return strip_tags(m.group(1))[:1000]
    return ""


def context_for(blob, url):
    idx = blob.find(url)
    if idx < 0:
        idx = blob.find(url.replace("/", "\\/"))
    if idx < 0:
        return strip_tags(blob[:1600])[:1000]
    return strip_tags(blob[max(0, idx - 900) : idx + len(url) + 1300])[:1000]


def excluded_urls():
    blocked = set()
    manifest = ROOT / "data/processed/ad_manifest.jsonl"
    if manifest.exists():
        for line in manifest.read_text(errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            meta = row.get("metadata") or {}
            if meta.get("original_url"):
                blocked.add(norm_url(str(meta["original_url"])))
            raw = json.dumps(row, ensure_ascii=False)
            for url in URL_RE.findall(raw):
                blocked.add(norm_url(url))
    rejected = ROOT / "data/sources/rejected_seed_urls.json"
    if rejected.exists():
        try:
            obj = json.loads(rejected.read_text(errors="ignore"))
            for url in obj.get("urls", []):
                blocked.add(norm_url(url))
        except json.JSONDecodeError:
            pass
    return blocked


def platform_hint(url):
    host = urlparse(url).netloc.lower()
    path = urlparse(url).path.lower()
    if host.endswith("doplim.com.pe"):
        return "doplim_peru_direct_html"
    if "facebook.com" in host and ("/groups/" in path or "/posts/" in path or "permalink.php" in path):
        return "facebook_public_group_or_post"
    return ""


def qualifies(url, text):
    hint = platform_hint(url)
    if not hint:
        return False
    if hint == "doplim_peru_direct_html" and not urlparse(url).path.lower().endswith(".html"):
        return False
    haystack = f"{url} {text}"
    return bool(ECON_RE.search(haystack) and MALE_RE.search(haystack))


def add_candidate(candidates, url, title, text, source):
    url = norm_url(url)
    text = redact(strip_tags(text))
    title = redact(strip_tags(title))
    if not qualifies(url, f"{title} {text}"):
        return
    if url not in candidates:
        candidates[url] = {
            "url": url,
            "title": title[:240] or url.rsplit("/", 1)[-1].replace("-", " ")[:240],
            "text": text[:1000],
            "source": source,
            "platform_hint": platform_hint(url),
        }


def scan_structured_seed_files(candidates):
    for path in sorted((ROOT / "data/agent_runs").glob("*/*.jsonl")):
        if path.is_relative_to(ROOT / "data/agent_runs/seed_e"):
            continue
        for line in path.read_text(errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            url = row.get("url")
            if not url:
                continue
            title = row.get("title", "")
            text = row.get("text") or row.get("snippet") or title
            add_candidate(candidates, url, title, text, str(path.relative_to(ROOT)))


def scan_local_artifacts(candidates):
    roots = [ROOT / "data/raw/ads", ROOT / "data/sources", ROOT / "reports"]
    for base in roots:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".html", ".json", ".jsonl", ".txt", ".md"}:
                continue
            blob = path.read_text(errors="ignore")
            normalized_blob = html.unescape(blob).replace("\\/", "/")
            page_title = title_from_blob(normalized_blob)
            page_desc = desc_from_blob(normalized_blob)
            for raw_url in URL_RE.findall(normalized_blob):
                url = norm_url(raw_url)
                text = " ".join(x for x in [page_desc, context_for(normalized_blob, url)] if x)
                add_candidate(candidates, url, page_title, text, str(path.relative_to(ROOT)))


def main():
    blocked = excluded_urls()
    candidates = {}
    scan_structured_seed_files(candidates)
    scan_local_artifacts(candidates)
    for url in list(candidates):
        if url in blocked:
            candidates.pop(url)

    rows = sorted(candidates.values(), key=lambda r: (r["platform_hint"], r["url"]))
    OUT_DATA.parent.mkdir(parents=True, exist_ok=True)
    OUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    OUT_DATA.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))

    counts = {}
    for row in rows:
        counts[row["platform_hint"]] = counts.get(row["platform_hint"], 0) + 1
    summary = {
        "candidate_count": len(rows),
        "counts_by_platform_hint": counts,
        "excluded_known_or_rejected_url_count": len(blocked),
        "search_queries_used": SEARCH_QUERIES_USED,
        "method": "No ad detail pages fetched. Candidates mined from existing local artifacts plus public search-result queries attempted through the web search tool.",
    }
    OUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
