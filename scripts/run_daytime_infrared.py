"""Run 6 real per-hour UTCI grids for a hot mid-August day at Parc del Forum (AUTHORIZED paid run).

Reuses the project's budgeted fetch_utci + grid_to_utci_artifact (same 6 m lattice shaping the crowd
uses). Writes projects/primavera-aug2026/utci_HH.json (+ a canonical utci_grid.json + parsed_brief)
so the crowd sim can re-run on the SAME lattice and the viewer can overlay heat x crowd.

Run: PYTHONPATH=src python scripts/run_daytime_infrared.py
"""
from __future__ import annotations
import json, os, shutil
from pathlib import Path

for line in Path(".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line.startswith("INFRARED_API_KEY="):
        os.environ["INFRARED_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")

import climate.infrared_client as ic
from climate.infrared_client import fetch_utci, LiveCallBudget
from climate.lattice import grid_to_utci_artifact

DATE = "2026-08-15"
HOURS = list(range(9, 21))                 # ALL 12 real hours 09:00..20:00 (no interpolation — accurate)
CANONICAL_HOUR = 14                         # the grid the crowd sim runs its lattice on (peak)
SRC_PROJECT = Path("projects/primavera-demo")
OUT = Path("projects/primavera-aug2026")
OUT.mkdir(parents=True, exist_ok=True)

geo = json.loads(Path("viz/data/boundary_2026.geojson").read_text(encoding="utf-8"))
geom = geo["features"][0]["geometry"] if geo.get("type") == "FeatureCollection" else geo.get("geometry", geo)
ring = geom["coordinates"][0]               # exterior ring, [lon,lat]
polygon = {"type": "Polygon", "coordinates": [ring]}
lon = sum(p[0] for p in ring) / len(ring)   # centroid (drives sun position)
lat = sum(p[1] for p in ring) / len(ring)

budget = LiveCallBudget(cap=6 * len(HOURS))   # generous call-count guard (preview+run+weather per hour); token cost stays 6x40=240
print(f"Running {len(HOURS)} UTCI anchors for {DATE} (lat {lat:.4f}, lon {lon:.4f})...", flush=True)

manifest = {"date": DATE, "site": "Parc del Forum", "centroid": [lon, lat], "hours": {}, "tier": "GROUNDED (infrared.city UTCI)"}
for h in HOURS:
    fp = OUT / f"utci_{h:02d}.json"
    if fp.exists():                          # already paid in a prior run — skip (idempotent, no re-charge)
        art = json.loads(fp.read_text(encoding="utf-8"))
        temps = [c["utci_c"] for c in art["cells"]]
        manifest["hours"][f"{h:02d}:00"] = {"file": fp.name, "utci_min": round(min(temps), 2),
                                            "utci_max": round(max(temps), 2),
                                            "weather_source": art.get("_meta", {}).get("weather_source", "cached")}
        print(f"  {h:02d}:00  SKIP (already on disk)", flush=True)
        continue
    ic.PEAK_HEAT_HOUR_BAND = (h, h + 1)     # per-hour band (build_time_period reads this module global)
    grid, bounds, src = fetch_utci(lat=lat, lon=lon, polygon=polygon, date=DATE, budget=budget)
    art = grid_to_utci_artifact(grid, bounds)
    art["_meta"] = {"date": DATE, "hour": f"{h:02d}:00", "weather_source": src, "tier": "GROUNDED"}
    fp = OUT / f"utci_{h:02d}.json"
    fp.write_text(json.dumps(art), encoding="utf-8")
    temps = [c["utci_c"] for c in art["cells"]]
    lat0 = art["lattice"]
    print(f"  {h:02d}:00  src={src}  lattice {lat0['cols']}x{lat0['rows']}@{lat0['cell_size_m']}m  "
          f"UTCI {min(temps):.1f}..{max(temps):.1f}C  cells={len(temps)}", flush=True)
    manifest["hours"][f"{h:02d}:00"] = {"file": fp.name, "utci_min": round(min(temps), 2),
                                        "utci_max": round(max(temps), 2), "weather_source": src}

# canonical utci_grid.json (lattice authority for the crowd sim) + brief
shutil.copy(OUT / f"utci_{CANONICAL_HOUR:02d}.json", OUT / "utci_grid.json")
shutil.copy(SRC_PROJECT / "parsed_brief.json", OUT / "parsed_brief.json")
(OUT / "utci_daytime_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(f"\nDONE. {len(HOURS)} grids -> {OUT}. Spent {budget.spent if hasattr(budget,'spent') else '?'} calls.")
print(f"Canonical (crowd-sim lattice) = {CANONICAL_HOUR:02d}:00. Manifest: {OUT/'utci_daytime_manifest.json'}")
