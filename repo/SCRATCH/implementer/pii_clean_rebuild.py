#!/usr/bin/env python3
import json, hashlib, time, re, sys
from pathlib import Path
from bs4 import BeautifulSoup
sys.path.insert(0, ".")
from tools.redact_pii import redact_text
from tools.phase_gate import _contains_contact_like_pii

REAL_SCR = Path("/var/folders/46/hqp40jys76g696ycvflt54mc0000gn/T/grok-goal-dce7e267cef8/implementer")
ROOT = Path(".")
MAN = ROOT / "data/processed/ad_manifest.jsonl"
RAWDIR = ROOT / "data/raw/ads"

ts = int(time.time())
bak = MAN.with_name(MAN.name + f".pii_rebuild_{ts}")
if MAN.exists():
    MAN.rename(bak)
    print("backup:", bak)

existing = set()
clean = []
TARGETS = ("ayuda economica", "apoyo economico", "doy ayuda", "brindo ayuda", "brindo apoyo")
MALE = ("brindo", "doy", "ofrezco", "soy ", "hombre", "señoritas", "universitarias")

src = bak if bak.exists() else MAN
for ln in src.read_text(errors="ignore").splitlines():
    if not ln.strip(): continue
    try:
        r = json.loads(ln)
    except:
        continue
    ref = r.get("raw_archive_ref")
    if not ref: continue
    rp = ROOT / ref
    if not rp.exists(): continue
    html = rp.read_text(errors="ignore")
    soup = BeautifulSoup(html, "lxml")
    title = ""
    for t in soup.find_all(["h1", "title"]):
        title = re.sub(r"\s+", " ", t.get_text()).strip()[:280]
        if title: break
    body = ""
    for sel in [".description", "article", ".ad_text", "main", "section"]:
        el = soup.select_one(sel)
        if el and len(el.get_text(strip=True)) > 60:
            body = re.sub(r"\s+", " ", el.get_text()).strip()[:9500]
            break
    if not body:
        body = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))[:6000]
    hay = (title + " " + body).lower()
    if not any(t in hay for t in TARGETS) or not any(m in hay for m in MALE):
        continue
    rt = redact_text(title)[:480]
    rb = redact_text(body)[:9500]
    if _contains_contact_like_pii(rt + " " + rb):
        continue
    rid = r.get("record_id") or hashlib.sha256(str(r.get("metadata",{}).get("original_url","") or ref).encode()).hexdigest()
    if rid in existing: continue
    rec = dict(r)
    rec["record_id"] = rid
    rec["title"] = rt
    rec["body_redacted"] = rb
    rec["raw_archive_ref"] = str(rp.relative_to(ROOT))
    clean.append(json.dumps(rec, ensure_ascii=False))
    existing.add(rid)

MAN.parent.mkdir(parents=True, exist_ok=True)
with open(MAN, "w", encoding="utf-8") as f:
    for c in clean:
        f.write(c + "\n")
print(f"Rebuilt: {len(clean)} good records")
with open(REAL_SCR / f"pii_rebuild_report_{ts}.txt", "w") as f:
    f.write(f"clean={len(clean)}\nbackup={bak}\n")
print("Saved report to real SCRATCH")