"""GATE-01 — projected-shadow coverage over the funded priority cells (D-02, Pitfall 12).

Coverage is the count ratio

    coverage_pct = 100 · |{ priority cell : centre ∈ projected_shadow }| / |priority cells|

over the funded high-priority (hottest×busiest) dwell cells, using the REAL Phase-4
**projected shadow** (the ``gh_meta.shadow_polygon_m`` plain-coords sidecar, Q1) — NOT the
raw footprint area and NOT the ``gh_meta.shadow_coverage_pct`` scalar (that is a
footprint-area fraction; reusing it is the Pitfall-12 trap). A cell whose centre is under the
FOOTPRINT but OUTSIDE the projected SHADOW is NOT credited: once the sun is off-zenith a tall
thin canopy footprints a cell yet casts shade elsewhere.

Frame discipline (Pitfall 8): the persisted shadow polygon is origin-translated to the
footprint min-corner (``shadow_polygon_m.min_corner_m``), so this module translates the
priority-cell centres by the SAME ``-min_corner_m`` before the point-in-polygon test — both
sets share the near-origin frame, so a non-empty shadow never reads a false 0 %. This mirrors
``geom.shadow_sim`` which origin-translates the footprint to its own min-corner.

BASE TIER — NON-NEGOTIABLE: shapely only. NO rhino3dm / torch / infrared import.
"""

from __future__ import annotations

from shapely.affinity import translate
from shapely.geometry import Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union


def _shadow_geometry(shadow_polygon_m: dict) -> tuple[BaseGeometry, tuple[float, float]]:
    """Build the (Multi)Polygon shadow + its ``min_corner_m`` from the Q1 sidecar field.

    ``shadow_polygon_m`` carries plain coords already origin-translated to the footprint
    min-corner: ``{"min_corner_m": [minx, miny], "polygons_xy_m": [[[x,y],...], ...]}``.
    Per-disjoint-polygon exteriors are preserved (never hull-collapsed) so disjoint shade
    stays disjoint. Returns the unioned geometry and the ``(minx, miny)`` offset the caller
    translates the cell centres by.
    """
    rings = shadow_polygon_m["polygons_xy_m"]
    polys: list[Polygon] = []
    for ring in rings:
        coords = [(float(p[0]), float(p[1])) for p in ring]
        if len(coords) >= 3:
            polys.append(Polygon(coords))
    if not polys:
        raise ValueError("shadow_polygon_m carries no valid polygon ring")
    geom = unary_union(polys)

    min_corner = shadow_polygon_m.get("min_corner_m", [0.0, 0.0])
    offset = (float(min_corner[0]), float(min_corner[1]))
    return geom, offset


def _footprint_polygon(footprint: dict) -> BaseGeometry:
    """Union the ``footprint.json`` rings into one shapely geometry (the funded-cell polys)."""
    rings = footprint.get("polygons", []) if isinstance(footprint, dict) else footprint
    polys: list[Polygon] = []
    for ring in rings:
        coords = []
        for pt in ring:
            if isinstance(pt, dict):
                coords.append((pt["x_m"], pt["y_m"]))
            else:
                coords.append((pt[0], pt[1]))
        if len(coords) >= 3:
            polys.append(Polygon(coords))
    if not polys:
        raise ValueError("footprint has no valid polygon ring")
    return unary_union(polys)


def priority_cells(
    score_grid: dict,
    footprint: dict,
    marked_cells: list | None = None,
) -> list[dict]:
    """The funded high-priority dwell cells (Q2 dual path).

    Orchestrator path: if ``marked_cells`` is given, use it directly (the greedy marked set
    the placement stage funded). Standalone path: intersect the ``score_grid`` cell centres
    with the ``footprint.json`` polygons — ``footprint.json`` IS the persisted record of which
    cells were funded — and keep those whose centre lies inside a funded polygon.

    Returns cells as ``{"x_m", "y_m"}`` (carrying ``score``/``baseline_utci_c`` when present).
    Defends CORE-06: only ``score > 0`` cells are funded (the demo already guarantees this);
    a non-positive-score cell is never credited as priority.
    """
    if marked_cells is not None:
        return [dict(c) for c in marked_cells]

    funded = _footprint_polygon(footprint)
    cells = score_grid.get("cells", []) if isinstance(score_grid, dict) else score_grid
    priority: list[dict] = []
    for c in cells:
        if c.get("score", 1.0) <= 0:
            continue  # CORE-06: a sub-26 / zero-density cell is never funded
        if funded.intersects(Point(c["x_m"], c["y_m"])):
            priority.append(dict(c))
    return priority


def coverage_pct(priority: list[dict], shadow_polygon_m: dict) -> float:
    """Percent of priority cells whose centre lies inside the PROJECTED shadow (frame-aware).

    Translates each priority centre by ``-min_corner_m`` (the same offset the shadow was
    origin-translated by) so both sets share the near-origin frame (Pitfall 8 — never a false
    0 %). Returns ``100 · shaded / |priority|``. An empty priority set returns ``0.0`` — a 0/0
    is disclosed via ``priority_shadow_coverage`` (``priority_count == 0``) so it can never
    silently read as a PASS. NEVER reuses ``gh_meta.shadow_coverage_pct`` (Pitfall 12).
    """
    return priority_shadow_coverage(priority, shadow_polygon_m)["coverage_pct"]


def priority_shadow_coverage(priority: list[dict], shadow_polygon_m: dict) -> dict:
    """GATE-01 result: ``{coverage_pct, shaded_count, priority_count}`` (frame-consistent).

    The single load-bearing transform the GATE-01 tests drive directly. ``shaded`` counts only
    priority cells the PROJECTED shadow ``.intersects`` after both are put in one frame — never a
    footprint-area credit (Pitfall 12) and never a frame-blind false 0 % (Pitfall 8).
    """
    shadow, (ox, oy) = _shadow_geometry(shadow_polygon_m)

    priority_count = len(priority)
    shaded_count = 0
    for c in priority:
        # Same frame as the shadow: translate the centre by -min_corner_m.
        pt = translate(Point(c["x_m"], c["y_m"]), xoff=-ox, yoff=-oy)
        # intersects() subsumes contains() for a Point (interior + boundary); the disjunction was
        # redundant (NT-01) — a boundary-centre cell is still credited.
        if shadow.intersects(pt):
            shaded_count += 1

    pct = 100.0 * shaded_count / priority_count if priority_count else 0.0
    return {
        "coverage_pct": pct,
        "shaded_count": shaded_count,
        "priority_count": priority_count,
    }
