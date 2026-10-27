"""Pure site-geometry loader — committed geojson → UTM31N env geometry + blocked cells.

This module PROMOTES the DemoEnv prototype's site loading + walkability rasterisation
(``viz/run_demo_sim.py``: ``build_blocked_cells``, ``_polygon_rings_to_utm``, ``load_layout``)
INTO ``src/crowd`` as proper pipeline code (RESEARCH §Architectural Responsibility Map row 3,
§Don't Hand-Roll). It turns the three committed layer files —

* ``viz/data/festival_map_2026.geojson`` — 19 user-placed stages + 2 entrances (A general,
  B VIP), indicative ±30 m;
* ``viz/data/boundary_2026.geojson`` — the revised site boundary polygon;
* ``viz/data/walkable_nogo_2026.geojson`` — the 13 impassable blocker polygons —

into env geometry: stage goals + capacity-class goal weights (UTM31N), the two ordered
entrances, and the **impassable blocked-cell set** on the READ utci lattice (the PRD
"Obstacles flagged as impassable" honoured literally — RESEARCH must-have truth 2).

PURITY CONTRACT — this module is PURE pipeline: ``json`` + ``shapely`` + the canonical ``crs``
module. It imports NONE of the heavy crowd-extra ML stack (the deep-RL framework, its policy
backend, or the env/gym API). A static guard in ``tests/test_site.py`` greps this file's text
for those forbidden tokens and fails if any appears — prose included — so the forbidden-token
list is kept in the TEST, not here. The flow field is deterministic global routing; this loader
is deterministic geometry. Neither learns anything.

DON'T-HAND-ROLL (RESEARCH): polygon containment uses **shapely prepared geometry** (already in
the ``crowd`` extra); we never hand-roll a point-in-polygon test. The CRS transform is the
canonical ``crs.to_utm31n`` (CONTRACT-01) — never reproduced here.

LATTICE CONVENTION: blocked cells are ``(col, row)`` integer indices (cols-major), matching
``env.py``'s ``(pos - origin) // cell_size_m`` mapping — the same convention the flow field
(``flowfield.py``) and the demo's blocked-revert use. ``PYTHONUTF8=1`` matters for the geojson
``read_text`` (accented stage names).
"""

from __future__ import annotations

import json
from pathlib import Path

from crowd.constants import GOAL_WEIGHT_BY_CLASS, GOAL_WEIGHT_DEFAULT
from crs.crs import to_utm31n

# Repo-root-relative default paths for the committed layer files (INPUTS, 259d3fb).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_VIZ_DATA = _REPO_ROOT / "viz" / "data"
DEFAULT_FESTIVAL_PATH = _VIZ_DATA / "festival_map_2026.geojson"
DEFAULT_BOUNDARY_PATH = _VIZ_DATA / "boundary_2026.geojson"
DEFAULT_NOGO_PATH = _VIZ_DATA / "walkable_nogo_2026.geojson"


def _load_geojson(arg, default_path: Path) -> dict:
    """Resolve a geojson arg to a dict.

    Accepts: a dict (already-loaded geojson — for testability), a path (str/Path), or ``None``
    (→ the committed default). ``PYTHONUTF8=1`` matters for the accented stage names.
    """
    if isinstance(arg, dict):
        return arg
    path = Path(arg) if arg is not None else default_path
    return json.loads(path.read_text(encoding="utf-8"))


def _polygon_rings_to_utm(geom: dict) -> list[list[tuple[float, float]]]:
    """Return the list of exterior rings (UTM31N metre tuples) for a Polygon/MultiPolygon.

    Promoted verbatim from ``viz/run_demo_sim.py``. Non-polygon geometries return ``[]``.
    """
    rings: list[list[tuple[float, float]]] = []
    if geom["type"] == "Polygon":
        polys = [geom["coordinates"]]
    elif geom["type"] == "MultiPolygon":
        polys = geom["coordinates"]
    else:
        return rings
    for poly in polys:
        ext = poly[0]  # exterior ring
        rings.append([to_utm31n(lon, lat) for lon, lat in ext])
    return rings


def build_blocked_cells(lattice: dict, boundary_geo: dict, nogo_geo: dict) -> set[tuple[int, int]]:
    """Rasterise blocker polygons AND outside-boundary area to blocked ``(col, row)`` cells.

    A cell-centre test on the READ utci lattice using shapely PREPARED geometries (RESEARCH
    §Don't-Hand-Roll — robust containment, no hand-rolled point-in-polygon). A cell ``(col,row)``
    is blocked when its centre is **outside the site boundary** OR **inside any blocker polygon**
    — the PRD "Obstacles flagged as impassable" honoured literally (RESEARCH must-have truth 2).

    Args:
        lattice: master-lattice descriptor (``origin_x_m``, ``origin_y_m``, ``cell_size_m``,
            ``cols``, ``rows``) — the READ utci lattice (CONTRACT-03).
        boundary_geo: the site-boundary geojson FeatureCollection (Polygon/MultiPolygon).
        nogo_geo: the blocker geojson FeatureCollection (the 13 impassable polygons).

    Returns:
        A ``set[(col, row)]`` of impassable cells (cols-major, matching ``env.py``).
    """
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    from shapely.prepared import prep

    ox, oy = lattice["origin_x_m"], lattice["origin_y_m"]
    s = lattice["cell_size_m"]
    cols, rows = lattice["cols"], lattice["rows"]

    # Site boundary polygon (union of all boundary features, projected to UTM31N).
    bpolys = []
    for f in boundary_geo["features"]:
        for ring in _polygon_rings_to_utm(f["geometry"]):
            bpolys.append(Polygon(ring))
    boundary = unary_union(bpolys)
    boundary_prep = prep(boundary)

    # Blocker polygons (buildings/bridges) — agents may NOT enter.
    blockers = []
    for f in nogo_geo["features"]:
        for ring in _polygon_rings_to_utm(f["geometry"]):
            blockers.append(Polygon(ring))
    blockers_union = unary_union(blockers)
    blockers_prep = prep(blockers_union)

    blocked: set[tuple[int, int]] = set()
    for col in range(cols):
        cx = ox + (col + 0.5) * s
        for row in range(rows):
            cy = oy + (row + 0.5) * s
            pt = Point(cx, cy)
            if (not boundary_prep.contains(pt)) or blockers_prep.intersects(pt):
                blocked.add((col, row))
    return blocked


def load_site_geometry(festival_geo=None, boundary_geo=None, nogo_geo=None, lattice=None) -> dict:
    """Load the committed geojson → UTM31N env geometry + the blocked-cell set.

    Promotes ``viz/run_demo_sim.py::load_layout`` into pipeline code. Each geojson arg accepts a
    dict (already-loaded — for testability), a path (str/Path), or ``None`` (→ committed default).

    Args:
        festival_geo: festival-map geojson (19 stages + 2 entrances). Default: the committed file.
        boundary_geo: site-boundary geojson. Default: the committed file.
        nogo_geo: blocker geojson (13 impassable polygons). Default: the committed file.
        lattice: master-lattice descriptor (the READ utci lattice). REQUIRED — the blocked-cell
            rasterisation needs the lattice; pass the descriptor read from ``utci_grid.json``.

    Returns:
        A dict with:
          * ``stages_utm`` — list of 19 ``(x_m, y_m)`` stage centres (UTM31N).
          * ``stage_meta`` — list of ``{name, class, lon, lat}`` (one per stage, same order).
          * ``goal_weights`` — list of capacity-class FLOOR weights
            (``GOAL_WEIGHT_BY_CLASS.get(class, GOAL_WEIGHT_DEFAULT)``), same order as stages.
          * ``entrances_utm`` — ``[A_utm, B_utm]`` (general, then VIP) UTM31N tuples.
          * ``entrances_ll`` — ``{"A": (lon, lat), "B": (lon, lat)}`` (general, then VIP).
          * ``blocked_cells`` — ``set[(col, row)]`` impassable cells (or empty if ``lattice`` is
            ``None`` — geometry-only mode).
    """
    festival = _load_geojson(festival_geo, DEFAULT_FESTIVAL_PATH)
    boundary = _load_geojson(boundary_geo, DEFAULT_BOUNDARY_PATH)
    nogo = _load_geojson(nogo_geo, DEFAULT_NOGO_PATH)

    stages_utm: list[tuple[float, float]] = []
    stage_meta: list[dict] = []
    goal_weights: list[int] = []
    for f in festival["features"]:
        if f["properties"].get("layer") != "stage":
            continue
        lon, lat = f["geometry"]["coordinates"]
        x, y = to_utm31n(lon, lat)
        stages_utm.append((x, y))
        cls = f["properties"].get("capacity_class", "")
        goal_weights.append(GOAL_WEIGHT_BY_CLASS.get(cls, GOAL_WEIGHT_DEFAULT))
        stage_meta.append({"name": f["properties"]["name"], "class": cls, "lon": lon, "lat": lat})

    # Entrances: A = "(general)" gate, B = "(VIP" gate. Both kind == "entrance".
    ents: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {}
    for f in festival["features"]:
        if f["properties"].get("kind") == "entrance":
            lon, lat = f["geometry"]["coordinates"]
            ents[f["properties"]["name"]] = (to_utm31n(lon, lat), (lon, lat))
    # Order [A, B] independent of geojson feature order: A = general, B = VIP.
    a = next(v for k, v in ents.items() if "general" in k.lower())
    b = next(v for k, v in ents.items() if "vip" in k.lower())
    entrances_utm = [a[0], b[0]]
    entrances_ll = {"A": a[1], "B": b[1]}

    blocked_cells: set[tuple[int, int]] = (
        build_blocked_cells(lattice, boundary, nogo) if lattice is not None else set()
    )

    return {
        "stages_utm": stages_utm,
        "stage_meta": stage_meta,
        "goal_weights": goal_weights,
        "entrances_utm": entrances_utm,
        "entrances_ll": entrances_ll,
        "blocked_cells": blocked_cells,
    }
