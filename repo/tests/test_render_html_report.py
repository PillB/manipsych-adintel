import json
from pathlib import Path

from tools.render_html_report import render_html_report


def test_render_html_report_contains_interactive_audit(tmp_path: Path):
    row = {
        "record_id": "h_test",
        "source_platform": "Locanto Peru",
        "title": "Ayuda economica urgente",
        "excerpt": "Ayuda urgente por privado",
        "overall_score": 0.88,
        "rule_score": 0.7,
        "quality_score": 0.6,
        "rule_findings": [{"tag": "scarcity_urgency_pressure", "rationale": "Urgency", "evidence": ["urgente"], "weight": 0.25}],
        "top_model_labels": [{"label": "scarcity_urgency_pressure", "probability": 0.9}],
        "context_model_labels": [{"label": "social_engagement_signal", "probability": 0.6}],
        "metadata_signals": {"followers_count": 10},
    }
    ranking = {"total_records_scored": 1, "top_records": [row] * 25}
    model = {"evaluation_metrics": {"macro_f1": 0.73, "micro_f1": 0.87, "accuracy": 0.35}, "training_data": {}}
    rebuild = {"raw_files_scanned": 30, "records_written": 25, "platform_counts": {"locanto": 25}, "reject_counts": {"duplicate": 5}}
    output = tmp_path / "report.html"

    render_html_report(ranking, model, rebuild, output)
    content = output.read_text(encoding="utf-8")

    assert "<!doctype html>" in content
    assert "tailwindcss.com" in content
    assert 'id="pipeline"' in content
    assert 'id="rankings"' in content
    assert 'id="detailDialog"' in content
    assert "prefers-reduced-motion" in content
    assert "Weak labels" in content
    embedded = content.split('<script id="reportData" type="application/json">', 1)[1].split("</script>", 1)[0]
    assert len(json.loads(embedded)["rows"]) == 25
