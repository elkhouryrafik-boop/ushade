"""Run the 3 NEW infrared diagnostic layers for the demo site (AUTHORIZED paid run).

Beyond the baseline UTCI grid (run_daytime_infrared.py) this fetches the high-value
layers the project was leaving on the table:

  * direct-sun-hours  -> sun_hours_grid.json     (which cells bake in the sun all day)
  * solar-radiation   -> solar_radiation_grid.json (W/m^2 load per cell, shade ROI)
  * TCS heat-stress   -> heat_stress_grid.json    (fraction of day each cell heat-stressed)

All three share ONE fetched area (buildings + ground materials + vegetation + weather) and
snap to the SAME 6 m master lattice as utci_grid.json / the crowd field / the placer, so the
viewer can overlay them cell-for-cell.

PAID: spends real infrared budget. Run ONLY with explicit authorisation.
Run: PYTHONPATH=src python scripts/run_site_diagnostics.py
"""
from __future__ import annotations
import json, os
from pathlib import Path

for line in Path(".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line.startswith("INFRARED_API_KEY="):
        os.environ["INFRARED_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")

from climate.multi_analysis import run_site_diagnostics, DIAGNOSTIC_VALUE_KEYS, DAYTIME_BAND
from climate.lattice import grid_to_value_artifact

DATE = "2026-08-15"
OUT = Path("projects/primavera-aug2026")
OUT.mkdir(parents=True, exist_ok=True)
OUT_FILES = {
    "direct_sun_hours": "sun_hours_grid.json",
    "solar_radiation": "solar_radiation_grid.json",
    "tcs_heat_stress": "heat_stress_grid.json",
}

geo = json.loads(Path("viz/data/boundary_2026.geojson").read_text(encoding="utf-8"))
geom = geo["features"][0]["geometry"] if geo.get("type") == "FeatureCollection" else geo.get("geometry", geo)
ring = geom["coordinates"][0]
polygon = {"type": "Polygon", "coordinates": [ring]}
lon = sum(p[0] for p in ring) / len(ring)
lat = sum(p[1] for p in ring) / len(ring)

# Skip any layer already on disk (idempotent — no re-charge).
todo = [k for k in OUT_FILES if not (OUT / OUT_FILES[k]).exists()]
if not todo:
    print("All diagnostic layers already on disk — nothing to fetch.")
    raise SystemExit(0)

print(f"Fetching {todo} for {DATE} band {DAYTIME_BAND} (lat {lat:.4f}, lon {lon:.4f})...", flush=True)
grids = run_site_diagnostics(lat=lat, lon=lon, polygon=polygon, date=DATE, analyses=todo)

manifest = {"date": DATE, "site": "Parc del Forum", "band": list(DAYTIME_BAND),
            "tier": "GROUNDED (infrared.city)", "layers": {}}
for key, (grid, bounds) in grids.items():
    value_key = DIAGNOSTIC_VALUE_KEYS[key]
    art = grid_to_value_artifact(grid, bounds, value_key=value_key)
    art["_meta"] = {"date": DATE, "analysis": key, "band": list(DAYTIME_BAND), "tier": "GROUNDED"}
    fp = OUT / OUT_FILES[key]
    fp.write_text(json.dumps(art), encoding="utf-8")
    vals = [c[value_key] for c in art["cells"]]
    lat0 = art["lattice"]
    print(f"  {key:18s} -> {fp.name}  lattice {lat0['cols']}x{lat0['rows']}@{lat0['cell_size_m']}m  "
          f"{value_key} {min(vals):.2f}..{max(vals):.2f}  cells={len(vals)}", flush=True)
    manifest["layers"][key] = {"file": fp.name, "value_key": value_key,
                               "min": round(min(vals), 3), "max": round(max(vals), 3)}

(OUT / "diagnostics_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(f"\nDONE -> {OUT}. Manifest: {OUT/'diagnostics_manifest.json'}")
