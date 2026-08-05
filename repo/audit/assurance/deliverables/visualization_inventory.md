# Visualization Inventory

| Section | Visualization | Data Source | Interactive |
|---------|--------------|-------------|-------------|
| KPI Metrics | 10 KPI cards | pipeline_results.json + v1_model_report | No |
| Pipeline | SVG diagram | Static | No |
| Diagnostics | ROC + PR curves | v1 model report | No |
| Heatmap | Per-label F1/AUC (viridis) | v1 model report | No |
| Explainability | Coefficient terms | v1 inferences | Dropdown |
| Term Network | Force-directed graph | v1 inferences + d3-lite-force | Filter, click |
| Corpus Map | 2D scatter | v1 inferences | Color, overlay, click |
| Explorer | Ranked list + annotated text | v1 inferences | Search, filter, keyboard |
| Profile | 17-dim bars + technique table | full_data_results.json | No |
| Clustering | 7-space table + alignment | clustering_summary + cluster_alignment | No |
| Authorship | KPIs + how-it-works + example | authorship + calibration | No |
| Outliers | Table + example cards | full_data_results.json | No |
| Checkpoints | Table | checkpoint_registry.json | No |
| Interactive Analyzer | Live tagging + GAN | Client-side JS | Full |
