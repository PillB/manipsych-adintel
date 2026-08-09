# Round 9: Deep Diagnostic + Interactive Cluster Visualization

## ROOT CAUSE ANALYSIS

### Issue: "Images of the feed still has issues and fallbacks that turn to the sandbox"

**Root cause: UMAP coordinate positional mismatch**

The corpus map has a critical data integrity bug:

1. `umap_coords.b64` contains 5,738 Float32 (x,y) pairs computed in manifest order (ad 0, 1, 2, ... 5737)
2. `EMBEDDED_ADS` (50 ads) is a **stratified sample** — NOT the first 50 ads in the manifest
3. `solarize_per_ad.jsonl` (4,427 ads) is **another subset** with different ordering
4. The code matches coords to ads by positional index `i`: `umapCoords[i]` -> `perAdTable[i]`

**This means every point on the corpus map is at the WRONG position for its ad.**
- Ad #0 in EMBEDDED_ADS gets UMAP coord #0 from the manifest (a different ad)
- When you click a point, you see ad A's metadata at ad B's UMAP position
- The "fallback to radial" mode is actually MORE honest (uses cluster_id correctly)

### Secondary issues:
- No bidirectional cluster interaction (can't click cluster -> see member ads)
- No ad-to-map highlight (can't select ad from search -> see it on map)
- No cluster membership explanation (no distinguishing terms shown per ad)
- No representative/boundary ads per cluster

## 6-ITERATION PLAN

1. Fix UMAP coord mismatch (match by record_id)
2. Interactive cluster selection (click cluster card -> highlight points)
3. Ad-to-map bidirectional (select ad from search -> highlight on map)
4. Cluster membership explanation (distinguishing terms + representative/boundary ads)
5. VLM screenshot analysis
6. Playwright tests + final polish

## SUCCESS CRITERIA
- UMAP coords match ads by record_id
- Click cluster card -> member points highlight
- Click ad in search -> point pulses on map
- Cluster cards show distinguishing terms + representative/boundary ads
- HTML under 150KB, all 48 Red tests pass
