"""Create a compact record_id -> UMAP coord map for the dashboard.

Problem: umap_coords.b64 has 5738 coords in manifest order, but
EMBEDDED_ADS and solarize_per_ad.jsonl have different subsets/orderings.
The dashboard matches by positional index, which is WRONG.

Fix: Create umap_coord_map.json — a compact {record_id: [x, y]} map.
Coords are in [0,1] so we pack as uint16 (0-65535) to save space.
5738 records x ~70 char id x 2 x 5 digit coords = ~800KB as JSON.
With uint16 packing: 5738 x 70 + 5738 x 4 = ~430KB. Still too big.

Better approach: Create a compact JSONL where each line is:
{"r":"h_abc...","x":0.123,"y":0.456}
Gzipped by GitHub Pages to ~150KB.

Even better: Create a lookup index. The umap_coords.b64 already has
coords in manifest order. If we also save the manifest record_ids in
order, the dashboard can build the map client-side.

Best approach for 150KB budget:
1. Keep umap_coords.b64 (60KB, packed Float32, manifest order)
2. Create umap_record_order.json — just the 5738 record_ids in order
   (packed as array of short hashes: first 16 chars of each record_id)
   5738 x 18 chars = ~100KB. Gzipped ~40KB.
3. Dashboard fetches both, builds record_id -> index -> [x,y] map
"""
import json
import os
from pathlib import Path

REPO = Path("/home/z/my-project/repo")
MANIFEST = REPO / "data" / "processed" / "ad_manifest.jsonl"
OUT = Path("/home/z/my-project/docs/reports/adintel/umap_record_order.json")

# Read manifest in order (same order as umap_coords.b64)
record_ids = []
with open(MANIFEST) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            rid = rec.get("record_id", "")
            if rid:
                # Use first 16 chars as short key (enough for uniqueness)
                record_ids.append(rid[:16])
        except:
            continue

print(f"Loaded {len(record_ids)} record_ids from manifest")

# Save as compact JSON array
data = {"n": len(record_ids), "ids": record_ids}
OUT.write_text(json.dumps(data, separators=(",", ":")))
print(f"Saved {OUT} ({OUT.stat().st_size / 1024:.1f} KB)")

# Also verify the umap_coords.b64 has the same number of coords
import base64
import numpy as np
b64 = (REPO / "reports" / "adintel" / "umap_coords.b64").read_text()
packed = base64.b64decode(b64)
floats = np.frombuffer(packed, dtype=np.float32)
n_coords = len(floats) // 2
print(f"umap_coords.b64 has {n_coords} coordinate pairs")
print(f"Match: {n_coords == len(record_ids)}")
