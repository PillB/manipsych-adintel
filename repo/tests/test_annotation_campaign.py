import json
import sqlite3

from tools.prepare_annotation_campaign import prepare
from tools.validate_annotations import validate


def test_campaign_is_reproducible_and_group_safe(tmp_path):
    records = []
    for index, source in enumerate(["doplim"] * 7 + ["locanto"] * 3 + ["facebook"]):
        records.append(
            {
                "record_id": f"r{index}",
                "source_platform": source,
                "title": f"distinct title token number {index}",
                "body_redacted": f"distinct body content marker {index}",
                "metadata": {"platform_family": source, "account_hash": "same" if index < 2 else ""},
            }
        )
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    out = tmp_path / "annotation"
    meta = prepare(manifest, out, pilot_size=4, batch_size=3)
    assert meta["records"] == 11
    assert meta["pilot_records"] == 4
    db = sqlite3.connect(out / "annotations.sqlite3")
    assert db.execute("SELECT COUNT(*) FROM assignments").fetchone()[0] == 55
    assert db.execute("SELECT COUNT(*) FROM assignments WHERE role='subagent'").fetchone()[0] == 33
    linked_splits = {
        r[0] for r in db.execute(
            "SELECT split_name FROM documents WHERE record_id IN ('r0','r1')"
        )
    }
    assert len(linked_splits) == 1
    assert db.execute("SELECT split_name FROM documents WHERE platform='facebook'").fetchone()[0] == "challenge"
    db.close()
    assert validate(out / "annotations.sqlite3") == []


def test_near_templates_share_campaign_group(tmp_path):
    base = "Brindo ayuda economica a señorita universitaria responsable y discreta en Lima"
    records = [
        {
            "record_id": "a",
            "source_platform": "doplim",
            "title": base,
            "body_redacted": "Escribeme al [REDACTED_PHONE] para conversar con respeto.",
            "metadata": {"platform_family": "doplim"},
        },
        {
            "record_id": "b",
            "source_platform": "locanto",
            "title": base.replace("Lima", "Cusco"),
            "body_redacted": "Escribeme al [REDACTED_PHONE] para conversar con respeto.",
            "metadata": {"platform_family": "locanto"},
        },
    ]
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    out = tmp_path / "annotation"
    meta = prepare(manifest, out, pilot_size=1, batch_size=2)
    assert meta["campaign_groups"] == 1
    db = sqlite3.connect(out / "annotations.sqlite3")
    assert db.execute("SELECT COUNT(DISTINCT campaign_group) FROM documents").fetchone()[0] == 1
    db.close()
