import json
from pathlib import Path


def test_generated_council_report_has_advanced_explainability_sections():
    report = Path("reports/ad_manipulation_report.html")
    assert report.exists()
    content = report.read_text(encoding="utf-8")
    for section_id in [
        'id="explainability-atlas"',
        'id="term-network"',
        'id="corpus-map"',
        'id="facet-overview"',
        'id="explainabilityAtlas"',
        'id="termNetworkViz"',
        'id="corpusMapViz"',
        'id="networkLabelMode"',
        'id="mapLegend"',
        'id="mapQuadrants"',
        'id="mapSelectedDetail"',
        'id="mapNeighbors"',
        'id="deepClusterPanel"',
        'id="mapProjection"',
        'id="mapOverlay"',
        'id="mapClusterLayers"',
        'id="mapResetLayers"',
        'value="deep_separation"',
        'value="deep_bottleneck"',
        'value="legacy_svd"',
        'value="deep_cluster"',
        'value="isolation_slice"',
        'value="isolation_score"',
        'value="both"',
        'value="isolation"',
    ]:
        assert section_id in content
    for tutorial_text in [
        "How to read the KPI cards",
        "How to use this pipeline diagram",
        "Diagnostics tutorial",
        "How to read and interact with explainability",
        "How to read and interact with the network",
        "How to read and interact with the corpus map",
        "Smart labels intentionally hide lower-priority labels",
        "Deep neural projection axis",
        "Deep separated clusters",
        "Deep 2D bottleneck",
        "Legacy SVD diagnostic",
        "Deep Isolation Forest cut-slices",
        "Silhouette higher is better",
        "Davies–Bouldin lower is better",
        "Calinski–Harabasz higher is better",
        "Nearest neighbors",
        "Explainable deep clusters",
        "Reset cluster layers",
        "Highlight on map",
        "neural bottleneck",
        "How to use facets and taxonomy",
        "How to review individual ads",
        "How to read observability",
        "How to interpret the expert POC",
        "How to use the research notes",
    ]:
        assert tutorial_text in content
    embedded = content.split('<script id="report-data" type="application/json">', 1)[1].split("</script>", 1)[0]
    payload = json.loads(embedded)
    report_data = payload["report"]
    assert report_data["global_explainability"]["labels"]
    assert report_data["term_network"]["nodes"]
    assert report_data["term_network"]["edges"]
    assert report_data["corpus_map"]["points"]
    assert report_data["corpus_map"]["deep_clusters"]["clusters"]
    assert report_data["corpus_map"]["deep_clusters"]["default_projection"] == "deep_separation"
    assert "deep_separation" in report_data["corpus_map"]["deep_clusters"]["projection_modes"]
    assert "deep_bottleneck" in report_data["corpus_map"]["deep_clusters"]["projection_modes"]
    assert "legacy_svd" in report_data["corpus_map"]["deep_clusters"]["projection_modes"]
    assert all("deep_cluster" in point for point in report_data["corpus_map"]["points"])
    assert all("projections" in point and "deep_separation" in point["projections"] for point in report_data["corpus_map"]["points"])
    assert report_data["corpus_map"]["deep_clusters"]["deep_isolation"]["slices"]
    assert report_data["corpus_map"]["deep_clusters"]["deep_isolation"]["metrics"]["deep_isolation_bottleneck"]
    assert report_data["corpus_map"]["deep_clusters"]["deep_isolation"]["metrics"]["kmeans_bottleneck"]
    assert all("isolation_slice" in point for point in report_data["corpus_map"]["points"])
    assert all("isolation_anomaly_score" in point for point in report_data["corpus_map"]["points"])
    for cluster in report_data["corpus_map"]["deep_clusters"]["clusters"]:
        assert cluster["eli5_title"]
        assert cluster["eli5_description"].startswith("ELI5:")
        assert cluster["risk_characterization"]
        assert cluster["likely_pattern"]
        assert cluster["review_guidance"]
        assert cluster["confidence_note"]
    assert report_data["facet_overview"]["facets"]
    assert report_data["annotation_taxonomy_matrix"]
