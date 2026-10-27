"""Pluggable coverage-model interface for the MCLP placer (post-pivot PLACE-02).

A *coverage model* answers ONE question: given a candidate structure site, which demand cells
does a structure placed there actually shade? Different models answer it differently, so the
placer (``core.placement``) never hard-codes the geometry — it takes a coverage model and calls
``covered_keys`` only. Swap the model, the placer is unchanged.

Two models live here:

* ``RadiusCoverage`` — cells within radius R of the site. SIMPLE but WRONG as the real model:
  Barcelona's low late-afternoon sun means a canopy's shade lands OFFSET (east of the structure),
  so a radius-R disc best matches the SUNLIT ground, not the shaded ground. Kept only as the
  swappable baseline / sanity alternative.
* ``OffsetShadowCoverage`` — the REAL model. The structure's footprint polygon, translated by the
  sun-driven shadow offset, IS the shaded region; covered cells are those whose centre falls in it.
  Reuses the same projected-shadow logic as ``acceptance.coverage`` (Pitfall 12 — shade is the
  PROJECTED shadow, never the raw footprint).

Determinism: every model returns a ``frozenset`` of ``(row, col)`` lattice keys — set-membership
only, no float accumulation, no ordering dependence. shapely is the ONLY heavy import (base tier;
no torch / rhino3dm / infrared).
"""

from __future__ import annotations

import math
from typing import Protocol

from shapely.affinity import translate
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union


class CoverageModel(Protocol):
    """The contract the placer relies on. A model maps a site → covered demand keys + area.

    ``name`` is a stable label emitted into the placement provenance (which model produced the
    coverage). ``covered_keys`` is the only method the greedy/ILP loop calls.
    """

    name: str

    def covered_keys(
        self, site_xy: tuple[float, float], demand: dict
    ) -> frozenset[tuple[int, int]]:
        """Demand keys whose cell centre is shaded by a structure placed at ``site_xy``.

        ``demand`` is ``core.placement.build_demand``'s output: ``{(row,col): {x_m, y_m, weight}}``.
        Returns a subset of ``demand``'s keys (a model NEVER invents keys not in the demand field).
        """
        ...

    def area_m2(self) -> float:
        """The structure's plan footprint area (m²) — reported per zone, never used for selection."""
        ...


def square_canopy_ring(half_span_m: float) -> list[tuple[float, float]]:
    """A square canopy footprint of side ``2·half_span_m`` centred on the origin (closed ring).

    Origin-centred so ``OffsetShadowCoverage`` can translate it to any site by (site + sun_offset).
    """
    if half_span_m <= 0:
        raise ValueError("half_span_m must be > 0")
    h = float(half_span_m)
    return [(-h, -h), (h, -h), (h, h), (-h, h), (-h, -h)]


def shadow_offset_from_sun(
    sun_vector: tuple[float, float, float], canopy_height_m: float
) -> tuple[float, float]:
    """Horizontal shadow displacement (dx, dy) of a canopy at ``canopy_height_m``.

    ``sun_vector`` points TOWARD the sun (the Phase-4 ``gh_meta`` / ``utci_grid`` convention).
    A point at height h casts its shadow at ``-h · (sun_x, sun_y) / sun_z`` — opposite the sun,
    longer as the sun drops (small ``sun_z``). Raises if the sun is at/below the horizon
    (``sun_z <= 0`` — no daytime shadow to project).
    """
    sx, sy, sz = (float(v) for v in sun_vector)
    if sz <= 0:
        raise ValueError("sun at/below horizon (sun_z <= 0) — no projected shadow")
    return (-canopy_height_m * sx / sz, -canopy_height_m * sy / sz)


class RadiusCoverage:
    """Cells within ``radius_m`` of the site centre. Baseline only — see module docstring."""

    name = "radius"

    def __init__(self, radius_m: float) -> None:
        if radius_m <= 0:
            raise ValueError("radius_m must be > 0")
        self.radius_m = float(radius_m)

    def covered_keys(
        self, site_xy: tuple[float, float], demand: dict
    ) -> frozenset[tuple[int, int]]:
        sx, sy = site_xy
        r2 = self.radius_m * self.radius_m  # compare squared distance — no sqrt, exact-ish, fast
        return frozenset(
            key
            for key, c in demand.items()
            if (c["x_m"] - sx) ** 2 + (c["y_m"] - sy) ** 2 <= r2
        )

    def area_m2(self) -> float:
        return math.pi * self.radius_m * self.radius_m


class OffsetShadowCoverage:
    """The REAL coverage model: sun-offset projected shadow of a canopy footprint.

    ``canopy_ring_m`` is the structure footprint as an origin-centred closed ring (use
    ``square_canopy_ring``); ``sun_offset_m`` is the (dx, dy) shadow displacement (use
    ``shadow_offset_from_sun``). A structure at ``site_xy`` shades the polygon
    ``canopy translated by (site_xy + sun_offset)``; a demand cell is covered iff its centre
    ``.intersects`` that shadow (interior + boundary — a boundary cell IS credited, mirrors
    ``acceptance.coverage``).
    """

    name = "offset_shadow"

    def __init__(
        self,
        canopy_ring_m: list[tuple[float, float]],
        sun_offset_m: tuple[float, float],
    ) -> None:
        self._canopy = Polygon(canopy_ring_m)
        if not self._canopy.is_valid or self._canopy.is_empty:
            raise ValueError("canopy_ring_m is not a valid non-empty polygon")
        self.sun_offset_m = (float(sun_offset_m[0]), float(sun_offset_m[1]))
        self._area = float(self._canopy.area)

    def covered_keys(
        self, site_xy: tuple[float, float], demand: dict
    ) -> frozenset[tuple[int, int]]:
        sx, sy = site_xy
        dx, dy = self.sun_offset_m
        # Shadow = canopy translated to the site, then by the sun offset (off-zenith displacement).
        shadow = translate(self._canopy, xoff=sx + dx, yoff=sy + dy)
        return frozenset(
            key
            for key, c in demand.items()
            if shadow.intersects(Point(c["x_m"], c["y_m"]))
        )

    def area_m2(self) -> float:
        return self._area


class PersistedShadowCoverage:
    """The WHOLE-SITE persisted-shadow model — a FIXED shaded region, site-independent.

    Two distinct coverage questions exist, answered by two distinct models:

    * "Which cells does ONE candidate structure shade?" — the per-candidate RANKING question.
      Answered by ``OffsetShadowCoverage`` (a canopy translated to each site + sun offset), which
      VARIES per candidate and is therefore the DEMO default the placer ranks zones with.
    * "Is the whole site shaded?" — answered HERE. This model treats the persisted Phase-4 roof-mesh
      projection (``gh_meta.shadow_polygon_m``) as ONE fixed shaded ground region; ``site_xy`` is
      accepted for ``CoverageModel`` Protocol conformance but does NOT move the shadow. It is
      reserved for the LATER acceptance gate, where the placer and the gate must share ONE shadow
      representation — NOT for per-candidate ranking (a fixed region credits every candidate with the
      SAME cells → no ranking).

    Re-uses the EXACT projected-shadow parse + ``-min_corner_m`` frame translate as
    ``acceptance.coverage`` (``_shadow_geometry`` / ``priority_shadow_coverage``) so the placer's
    whole-site model and the acceptance gate are a single shared representation (Pitfall 8 — the
    demand centres are absolute UTM, the polygon is origin-translated to its ``min_corner_m``, so a
    non-empty shadow never reads a false 0 %). Pitfall 12: shade is the PROJECTED shadow, never the
    raw footprint. shapely only (base tier).
    """

    name = "persisted_shadow"

    def __init__(self, shadow_polygon_m: dict) -> None:
        rings = shadow_polygon_m["polygons_xy_m"]
        polys = [
            Polygon([(float(p[0]), float(p[1])) for p in ring])
            for ring in rings
            if len(ring) >= 3
        ]
        if not polys:
            raise ValueError("shadow_polygon_m carries no valid polygon ring")
        self._shadow = unary_union(polys)
        min_corner = shadow_polygon_m.get("min_corner_m", [0.0, 0.0])
        self._min_corner = (float(min_corner[0]), float(min_corner[1]))
        self._area = float(self._shadow.area)

    def covered_keys(
        self, site_xy: tuple[float, float], demand: dict
    ) -> frozenset[tuple[int, int]]:
        # FIXED whole-site shadow: site_xy does NOT move it (Protocol conformance only). Translate
        # each demand centre by -min_corner_m into the shadow's near-origin frame before .intersects.
        ox, oy = self._min_corner
        return frozenset(
            key
            for key, c in demand.items()
            if self._shadow.intersects(Point(c["x_m"] - ox, c["y_m"] - oy))
        )

    def area_m2(self) -> float:
        return self._area
