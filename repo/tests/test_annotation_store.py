import json
import sqlite3

import pytest

from tools.annotation_store import save_annotation, visible_annotations
from tools.council_consensus import evaluate
from tools.export_council_packets import export_packets
from tools.export_resolved_council_annotations import export_resolved
from tools.prepare_annotation_campaign import prepare
from tools.run_council_annotation_pass import annotate_text, run_pass
from tools.validate_annotations import validate


def campaign(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "record_id": "r1",
                "source_platform": "doplim",
                "title": "Brindo ayuda",
                "body_redacted": "Texto discreto",
                "metadata": {"platform_family": "doplim"},
            }
        ) + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "annotation"
    prepare(manifest, out, 1, 2)
    return out / "annotations.sqlite3"


def test_save_submit_immutable_and_blinded(tmp_path):
    database = campaign(tmp_path)
    span = {
        "label": "privacy_or_secrecy_pressure",
        "segments": [[19, 27]],
        "exact_text": "discreto",
        "intensity": 2,
        "manipulativeness": 1,
        "harm_risk": 1,
    }
    save_annotation(database, "r1", "subagent_a", "subagent", "submitted", [span])
    assert visible_annotations(database, "r1", "reviewer_a") == []
    save_annotation(database, "r1", "reviewer_a", "human", "draft", [])
    assert all(row["actor_id"] == "reviewer_a" for row in visible_annotations(database, "r1", "reviewer_a"))
    save_annotation(database, "r1", "reviewer_a", "human", "submitted", [span])
    assert {row["actor_id"] for row in visible_annotations(database, "r1", "reviewer_a")} == {
        "reviewer_a", "subagent_a"
    }
    with pytest.raises(ValueError, match="immutable"):
        save_annotation(database, "r1", "reviewer_a", "human", "draft", [])


def test_rejects_stale_substring(tmp_path):
    database = campaign(tmp_path)
    with pytest.raises(ValueError, match="exact_text"):
        save_annotation(
            database, "r1", "reviewer_a", "human", "draft",
            [{"label": "x", "segments": [[0, 6]], "exact_text": "wrong"}],
        )


def test_validator_accepts_saved_span(tmp_path):
    database = campaign(tmp_path)
    save_annotation(
        database,
        "r1",
        "subagent_a",
        "subagent",
        "submitted",
        [{"label": "privacy_or_secrecy_pressure", "segments": [[19, 27]], "exact_text": "discreto"}],
    )
    assert validate(database) == []


def test_council_unanimous_accepts(tmp_path):
    database = campaign(tmp_path)
    span = {"label": "privacy_or_secrecy_pressure", "segments": [[19, 27]], "exact_text": "discreto"}
    for actor in ("subagent_a", "subagent_b", "subagent_c"):
        save_annotation(database, "r1", actor, "subagent", "submitted", [span])
    result = evaluate(database)
    assert result["decisions"] == {"accepted": 1}


def test_council_disagreement_creates_second_round(tmp_path):
    database = campaign(tmp_path)
    span = {"label": "privacy_or_secrecy_pressure", "segments": [[19, 27]], "exact_text": "discreto"}
    save_annotation(database, "r1", "subagent_a", "subagent", "submitted", [span])
    save_annotation(database, "r1", "subagent_b", "subagent", "submitted", [span])
    save_annotation(database, "r1", "subagent_c", "subagent", "submitted", [])
    result = evaluate(database, create_next_round=True)
    assert result["decisions"] == {"second_pass": 1}
    db = sqlite3.connect(database)
    assert db.execute("SELECT COUNT(*) FROM assignments WHERE role='subagent' AND round=2").fetchone()[0] == 3
    db.close()


def test_exports_council_packets_with_context_and_schema(tmp_path):
    database = campaign(tmp_path)
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({"labels": [{"id": "privacy_or_secrecy_pressure"}]}), encoding="utf-8")
    output = tmp_path / "packets.jsonl"
    assert export_packets(database, schema, output, reviewer_id="subagent_a") == 1
    packet = json.loads(output.read_text(encoding="utf-8"))
    assert packet["reviewer_id"] == "subagent_a"
    assert packet["title"] == "Brindo ayuda"
    assert packet["context"]["image_available"] is False
    assert packet["label_schema"]["labels"][0]["id"] == "privacy_or_secrecy_pressure"


def test_runs_council_annotation_pass(tmp_path):
    database = campaign(tmp_path)
    result = run_pass(database, 1)
    assert result["submitted"] == 3
    assert result["spans"] >= 3
    assert validate(database) == []
    consensus = evaluate(database)
    assert sum(consensus["decisions"].values()) == 1
    output = tmp_path / "resolved.jsonl"
    exported = export_resolved(database, output)
    assert exported["resolved"] == 1
    assert json.loads(output.read_text(encoding="utf-8"))["gold"] is False


def test_automated_council_annotation_offsets_and_labels():
    text = (
        "Ofrezco ayuda económica a señorita estudiante discreta\n"
        "Apoyo a chicas con urgencias económicas a cambio de intimidad."
    )
    spans, document = annotate_text(text, {"image_available": False}, "subagent_a", 1)
    labels = {span["label"] for span in spans}
    assert "conditional_financial_support" in labels
    assert "economic_vulnerability_targeting" in labels
    assert "reciprocity_obligation" in labels
    assert "privacy_or_secrecy_pressure" in labels
    assert document["harm_risk"] == 3
    for span in spans:
        start, end = span["segments"][0]
        assert text[start:end] == span["exact_text"]


def test_automated_council_handles_spanish_gender_typos_and_slang():
    text = (
        "Brindó apoyo económica a señorita por compañía a e\n"
        "Joven profesional brinda apoyo económico semanal a señorita estudiante de buen trato. "
        "Por compañía a lugares por elegir. Seguridad y discreción[REDACTED_CONTACT]"
    )
    spans, document = annotate_text(text, {"image_available": False}, "subagent_r4_a", 4, deliberated_second_pass=True)
    by_label = {}
    for span in spans:
        by_label.setdefault(span["label"], []).append(span["exact_text"])
        start, end = span["segments"][0]
        assert text[start:end] == span["exact_text"]

    assert any("apoyo económica" in value for value in by_label["reciprocity_obligation"])
    assert any("apoyo económico" in value for value in by_label["reciprocity_obligation"])
    assert "por compañía" in [value.lower() for value in by_label["conditional_financial_support"]]
    assert "discreción" in by_label["privacy_or_secrecy_pressure"]
    assert document["span_match_mode"] == "accent_gender_typo_normalized_span_matching_v5"
