"""Crowd-validation Step A — build the REAL Lyon festival reference (CROWD DERIVED gate).

Reads the MADRAS Fête-des-Lumières open dataset (Zenodo 10.5281/zenodo.13830435, CC-BY 4.0)
and produces two grounded artifacts the JuPedSim density gate validates against:

  1. ``lyon_walkable.wkt``      — the walkable polygon (people-hull minus real obstacles),
                                  EPSG:2154 metres, for the JuPedSim Lyon scene.
  2. ``lyon_observed_density.json`` — the MEASURED per-cell crowd density (people/m²) from the
                                  4,081-person single-frame LargeView snapshot, binned on a
                                  fixed grid; the empirical target for the density comparison.

This is REAL measured festival crowd data — the thing that lets crowd_density move past
ASSUMED for the density-MAGNITUDE/physics sub-claim (NOT the site-specific spatial allocation,
which has no open data; that stays ASSUMED — see MODEL_CARD).

Run: python scripts/crowd_validation/build_lyon_reference.py
Pure numpy + shapely (no pedpy → no numpy-2 pin break; grid density matches our crowd_grid
representation, which is apples-to-apples with U-Shade's own field).
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
from shapely import wkt as shapely_wkt
from shapely.geometry import MultiPoint, Polygon
from shapely.ops import unary_union

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_ZIP = _REPO / "data" / "validation" / "madras" / "Data_Madras.zip"
_OUT = _REPO / "data" / "validation" / "madras"

CELL_M = 2.0  # density grid cell (m); 2 m ≈ a person's personal-space scale (Fruin/Voronoi-ish)
# Obstacle classes that are NOT walkable (subtracted from the hull). Buildings bound the square.
_OBSTACLE_TYPES = {"Fountain", "Stairs", "Prohibited area", "Buren column",
                   "Square bollard", "Round bollard", "Buildings"}


def _read_zip_text(member_suffix: str) -> str:
    z = zipfile.ZipFile(_ZIP)
    name = [n for n in z.namelist() if n.endswith(member_suffix)][0]
    return z.read(name).decode("utf-8", "replace")


def load_geometry() -> dict[str, list[Polygon]]:
    """Parse Geometry.csv (WKT, EPSG:2154) → {type: [polygons]}. Drops Z to 2D."""
    text = _read_zip_text("Geometry.csv")
    by_type: dict[str, list[Polygon]] = {}
    for line in text.splitlines()[1:]:  # skip header Type,WKT
        if not line.strip():
            continue
        typ, _, wkt_str = line.partition(",")
        wkt_str = wkt_str.strip().strip('"')
        try:
            geom = shapely_wkt.loads(wkt_str)
        except Exception:
            continue
        # POLYGON Z → 2D
        geom2d = Polygon([(x, y) for x, y, *_ in geom.exterior.coords]) if geom.geom_type == "Polygon" else None
        if geom2d is not None and geom2d.is_valid:
            by_type.setdefault(typ, []).append(geom2d)
    return by_type


def load_observed_points() -> np.ndarray:
    """The 4,081-person LargeView single-frame snapshot → (N,2) EPSG:2154 metres (x_RGF,y_RGF)."""
    text = _read_zip_text("LargeView_density.txt")
    pts = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        f = line.split()
        # cols: id frame x/m y/m z/m t/s x_RGF y_RGF  → use the RGF ground coords (last two)
        pts.append((float(f[6]), float(f[7])))
    return np.asarray(pts, dtype=float)


def build_walkable(points: np.ndarray, geom: dict[str, list[Polygon]]) -> Polygon:
    """Walkable = convex hull of the observed crowd (where people actually are) minus the real
    obstacle polygons. People define the walkable extent; obstacles punch holes. Valid for JuPedSim."""
    hull = MultiPoint([tuple(p) for p in points]).convex_hull.buffer(1.0)  # +1 m margin
    obstacles = [p for t in _OBSTACLE_TYPES for p in geom.get(t, [])]
    walkable = hull.difference(unary_union(obstacles)) if obstacles else hull
    # keep the largest piece if difference fragmented it
    if walkable.geom_type == "MultiPolygon":
        walkable = max(walkable.geoms, key=lambda g: g.area)
    return walkable


def observed_density_grid(points: np.ndarray) -> dict:
    """Bin the snapshot into a fixed CELL_M grid → MEASURED people/m² per cell + summary stats."""
    x0, y0 = points.min(axis=0)
    x1, y1 = points.max(axis=0)
    nx = int(np.ceil((x1 - x0) / CELL_M))
    ny = int(np.ceil((y1 - y0) / CELL_M))
    ix = np.clip(((points[:, 0] - x0) / CELL_M).astype(int), 0, nx - 1)
    iy = np.clip(((points[:, 1] - y0) / CELL_M).astype(int), 0, ny - 1)
    counts = np.zeros((ny, nx), dtype=float)
    np.add.at(counts, (iy, ix), 1.0)
    density = counts / (CELL_M * CELL_M)  # people/m²
    occupied = density[counts > 0]
    return {
        "cell_m": CELL_M,
        "nx": nx, "ny": ny,
        "origin_xy": [float(x0), float(y0)],
        "n_people": int(len(points)),
        "occupied_cells": int((counts > 0).sum()),
        "density_people_per_m2": {
            "mean_occupied": float(occupied.mean()),
            "p50": float(np.percentile(occupied, 50)),
            "p90": float(np.percentile(occupied, 90)),
            "p99": float(np.percentile(occupied, 99)),
            "max": float(occupied.max()),
        },
        "counts": counts.tolist(),
    }


def main() -> None:
    geom = load_geometry()
    points = load_observed_points()
    walkable = build_walkable(points, geom)
    dens = observed_density_grid(points)

    (_OUT / "lyon_walkable.wkt").write_text(walkable.wkt, encoding="utf-8")
    (_OUT / "lyon_observed_density.json").write_text(json.dumps(dens, indent=2), encoding="utf-8")

    print("geometry types:", {t: len(v) for t, v in geom.items()})
    print(f"observed people: {dens['n_people']}  extent grid: {dens['nx']}x{dens['ny']} @ {CELL_M} m")
    print(f"walkable area: {walkable.area:.0f} m²  valid={walkable.is_valid}")
    d = dens["density_people_per_m2"]
    print(f"MEASURED density people/m²: mean_occ {d['mean_occupied']:.2f}  p90 {d['p90']:.2f}  "
          f"p99 {d['p99']:.2f}  max {d['max']:.2f}")
    print("wrote lyon_walkable.wkt + lyon_observed_density.json")


if __name__ == "__main__":
    main()
