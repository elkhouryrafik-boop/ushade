"""Infrared UTCI cost PREVIEW only — no paid run. Estimates tiles/time/tokens for one area run.

Run: PYTHONPATH=src python scripts/infrared_cost_preview.py
"""
from __future__ import annotations
import json, os
from pathlib import Path

# load INFRARED_API_KEY from .env into the env (never printed)
for line in Path(".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line.startswith("INFRARED_API_KEY="):
        os.environ["INFRARED_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")

from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import AnalysesName

geo = json.loads(Path("viz/data/boundary_2026.geojson").read_text(encoding="utf-8"))
geom = geo["features"][0]["geometry"] if geo.get("type") == "FeatureCollection" else geo.get("geometry", geo)
polygon = {"type": "Polygon", "coordinates": [geom["coordinates"][0]]}  # exterior ring only (no holes)

N_RUNS = 6
with InfraredClient() as c:
    p = c.preview_area(polygon, analysis_type=AnalysesName.thermal_comfort_index)
    print("=== UTCI area cost preview (Parc del Forum) ===")
    print(f"  tiles/run        : {p.tile_count}")
    print(f"  est time/run     : {p.estimated_time_s} s ({p.estimated_time_s/60:.1f} min)")
    print(f"  est tokens/run   : {p.estimated_cost_tokens}")
    print(f"  --- x{N_RUNS} runs ---")
    print(f"  total tokens     : {p.estimated_cost_tokens * N_RUNS}")
    print(f"  total est time   : {p.estimated_time_s * N_RUNS / 60:.1f} min (runs are sequential here)")
