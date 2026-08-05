# Split/Merge Analysis

## Contingency Matrix (v1 rows × adintel cols)
Based on cluster_alignment_report.json, n=5189 records.

## Key Findings
- v1 cluster 1 (100 records) → adintel cluster 1 (100 records): 100% match (one-to-one)
- v1 cluster 3 (878 records) → adintel cluster 2 (1265 records): 98.7% (merge with v1_9)
- v1 cluster 0 (684 records) → adintel cluster 4 (1249 records): 79.8% (merge with v1_5, v1_7)
- v1 clusters 4+8 (467+422=889 records) → adintel cluster 3 (954 records): merged
- v1 cluster 2 (1046 records) → adintel cluster 0 (1621 records): 85.9% (merge with v1_6, v1_9)

## Pattern
V1 splits on synonym variations ('apoyo' vs 'ayuda', 'brindo' vs 'doy').
Adintel merges these into meaningful groups and splits on actual semantic content.

Generated: 2026-08-05T21:20:37.331001+00:00
