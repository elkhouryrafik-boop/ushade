"""GEOM-06 — deterministic offline shadow-projection coverage of the footprint at peak sun.

RESEARCH (§GEOM-06): "offline geometric shadow projection from the tilted roof mesh is computable
deterministically." This module does exactly that with shapely (a BASE dependency, no geom extra):

  1. take the roof geometry as a ground-plane-projectable polygon (or polygons) in metres;
  2. parallel-project it onto the ground (z=0) ALONG the sun vector — each roof vertex at height z
     casts to ``(x - z*sx/sz, y - z*sy/sz)`` (the ray from the vertex toward the ground in the sun
     direction); a flat roof at z=0 projects to itself;
  3. union the projected shadow polygons;
  4. intersect with the footprint and return ``shadow ∩ footprint / footprint_area``.

It is pure geometry — no randomness, no I/O — so the coverage is byte-deterministic for a fixed
roof + footprint + sun vector. The demo must confirm ``>= 0.80`` at peak sun (the Phase-5b coverage
criterion input). ``coverage_pct`` is recorded in ``gh_meta.json`` (DERIVED) by the stage spine.
"""

from __future__ import annotations

from typing import Any

from shapely.geometry import Polygon  # BASE dep — NOT lazy
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union


def _footprint_polygon(footprint: Any) -> BaseGeometry:
    """Union the footprint rings into a single shapely geometry (clone reference_generator)."""
    if isinstance(footprint, dict):
        rings = footprint.get("polygons", [])
    else:
        rings = footprint
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
    # MJ-05: return the union DIRECTLY (MultiPolygon-safe). The old `convex_hull` fallback for a
    # disjoint footprint inflated the denominator to the venue-scale hull (the c72dc3d bug class,
    # ~48x the real 5,976 m^2 shade area), which would falsely fail the 80% gate the moment a real
    # roof shape is projected. Shapely's .area/.intersection need no single-Polygon guarantee.
    return unary_union(polys)


def _roof_polygons(roof: Any) -> list[list[tuple[float, float, float]]]:
    """Normalize the roof geometry to a list of vertex rings ``[(x, y, z), ...]``.

    Accepts a single ring (``[(x,y)|(x,y,z), ...]``) or a list of rings. A 2D point is treated as
    z=0 (a flat roof at ground level — the PREVIEW mesh shape).
    """
    def _is_ring(obj) -> bool:
        return obj and isinstance(obj[0], (list, tuple)) and isinstance(obj[0][0], (int, float))

    rings = [roof] if _is_ring(roof) else list(roof)
    out: list[list[tuple[float, float, float]]] = []
    for ring in rings:
        verts = []
        for p in ring:
            x, y = float(p[0]), float(p[1])
            z = float(p[2]) if len(p) > 2 else 0.0
            verts.append((x, y, z))
        if len(verts) >= 3:
            out.append(verts)
    return out


def _project(ring: list[tuple[float, float, float]], sun: Any) -> Polygon:
    """Parallel-project a roof ring onto the ground (z=0) along the sun vector."""
    sx, sy, sz = float(sun[0]), float(sun[1]), float(sun[2])
    # Sun below/at the horizon -> no usable shadow; fall back to the vertical drop (z removed).
    safe_sz = sz if abs(sz) > 1e-6 else 1.0
    ground = [(x - z * sx / safe_sz, y - z * sy / safe_sz) for (x, y, z) in ring]
    return Polygon(ground)


def shadow_coverage(roof: Any, footprint: Any, sun: Any) -> float:
    """Fraction of the footprint shaded by the roof at the given sun vector (GEOM-06).

    Args:
        roof: the roof geometry — a single ring or a list of rings of ``(x,y)`` or ``(x,y,z)`` verts
            (metres, origin-translated). A flat PREVIEW roof at z=0 projects to its own footprint.
        footprint: the ``footprint.json`` dict or a list of rings (metres, origin-translated to the
            SAME min-corner as the decoded roof, so they overlap).
        sun: the 3D sun unit vector ``[x, y, z]`` (z>0 above the horizon).

    Returns:
        ``shadow ∩ footprint / footprint_area`` in ``[0, 1]``.
    """
    fp = _footprint_polygon(footprint)
    fp_area = fp.area
    if fp_area <= 0:
        return 0.0

    # Origin-translate the footprint to its own min-corner so it shares the decoded roof's
    # near-origin frame (the decode step origin-translates the mesh to the footprint min-corner;
    # the PREVIEW roof rectangle is built at (0,0)). Without this the absolute EPSG-coord footprint
    # (~434000 m) and the near-origin roof never overlap and coverage reads a false 0.
    minx, miny, _maxx, _maxy = fp.bounds
    from shapely.affinity import translate as _translate  # noqa: PLC0415 (lazy, shapely is base)

    fp = _translate(fp, xoff=-minx, yoff=-miny)

    shadows = [_project(ring, sun) for ring in _roof_polygons(roof)]
    shadows = [s for s in shadows if s.is_valid and s.area > 0]
    if not shadows:
        return 0.0
    shadow = unary_union(shadows)

    covered = shadow.intersection(fp).area
    return max(0.0, min(1.0, covered / fp_area))
