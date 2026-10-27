"""The single grid->contract transform of Phase 2a (the genuinely net-new code).

``grid_to_utci_artifact(merged_grid, bounds)`` converts the infrared SDK's
``result.merged_grid`` + ``result.bounds`` into a contract-valid ``utci_grid``
master-lattice artifact (CONTRACT-03). It is the master coordinate lattice every
downstream spatial artifact snaps to, and its per-cell values are the no-shade
baseline (CLIMATE-04 / CONTRACT-05) the Phase 5b gate measures dUTCI against.

Four responsibilities, in order (RESEARCH §Pattern 2, Pitfalls 1/2/8):

1. CROP to the non-NaN bbox BEFORE building the lattice (the SDK returns 512x512
   with data in one corner; NaN = outside the polygon).
2. PROJECT lon/lat -> EPSG:32631 metres **exactly once**, and ONLY via ``src/crs``
   (CONTRACT-01). There is no hand-rolled UTM math and no ETRS89 zone-31 leak
   in this module — the no-leak contract is guarded by ``tests/test_crs.py`` and the
   plan's acceptance greps (T-02a-04).
3. RESAMPLE the native ~1 m grid to the declared 6.0 m master lattice by
   mean-aggregating the native cells whose centres fall inside each 6 m cell. The
   origin is snapped DOWN to integer metres so 2b/3 can snap by integer index.
4. EMIT every non-NaN cell with ``baseline_utci_c == utci_c``. Thermally comfortable
   (sub-threshold) cells are **preserved** here — the comfort-threshold drop is a
   SCORE-time filter (Phase 3), never a write-time drop (RESEARCH Pitfall 2 /
   CLIMATE-04). Do not "fix" this by dropping cells: the Phase 5b gate needs the full
   baseline denominator.

Grid conventions (RESEARCH Pitfall 1, grid-conventions.md): row 0 = SOUTH edge,
col 0 = WEST edge, ``bounds = (min_lng, min_lat, max_lng, max_lat)`` WGS84.

This function is **pure**: no SDK import, no network, no file I/O, no manifest. The
orchestrator (Plan 03/04) validates-then-writes; this only shapes the artifact.

karpathy: one function + one constant. No class, no resampler abstraction.
"""

from __future__ import annotations

import math

import numpy as np

from crs.crs import assert_crs_roundtrip, to_utm31n

# ── DECLARED MASTER RESOLUTION (ASSUMED) ──────────────────────────────────────
# CONTRACT-03 master lattice cell size, in metres. ASSUMED constant (CONTEXT Q1):
# the native infrared pitch is ~1 m, but a ~1 m master lattice over a festival site
# is >100k cells (intractable for the 2b snap + Phase-3 greedy sort). 6.0 m is the
# human-scale shade granularity (~6 m structural bays) the master lattice is resampled
# to. Changeable ONLY before any accepted run — immutable once a run is accepted
# (it is the resolution every downstream spatial artifact snaps to).
CELL_SIZE_M: float = 6.0


def _resample_to_lattice(merged_grid, bounds):
    """Crop -> project once -> bin the native grid onto the 6 m master lattice.

    The analysis-agnostic spine shared by every grid->artifact shaper. Returns the
    lattice geometry plus the per-out-cell ``sums`` / ``counts`` so callers can emit
    cells with whatever value key their analysis needs (``utci_c``, ``sun_hours``,
    ``solar_wm2``, ``heat_stress_frac``, ...). Steps 1-3 of the original
    ``grid_to_utci_artifact`` verbatim — only the cell-emit step (4) is caller-specific.

    Returns:
        ``(origin_x_m, origin_y_m, out_rows, out_cols, sums, counts)``.

    Raises:
        ValueError: if the grid is not 2-D or is entirely NaN (no region to lattice).
    """
    grid = np.asarray(merged_grid, dtype=float)  # NaN = outside polygon
    if grid.ndim != 2:
        raise ValueError(f"merged_grid must be 2-D, got shape {grid.shape!r}")
    rows, cols = grid.shape

    # 1) CROP to the non-NaN bbox BEFORE building the lattice (512x512 corner gotcha).
    valid_rows = np.where(~np.isnan(grid).all(axis=1))[0]
    valid_cols = np.where(~np.isnan(grid).all(axis=0))[0]
    if valid_rows.size == 0 or valid_cols.size == 0:
        raise ValueError("merged_grid is entirely NaN — no valid region to lattice.")
    r0, r1 = int(valid_rows[0]), int(valid_rows[-1]) + 1
    c0, c1 = int(valid_cols[0]), int(valid_cols[-1]) + 1
    crop = grid[r0:r1, c0:c1]
    crop_rows, crop_cols = crop.shape

    min_lng, min_lat, max_lng, max_lat = (float(b) for b in bounds)

    # 2) Georeference the NATIVE cell centres. The full grid spans the bounds box;
    #    row 0 = SOUTH (lat increases with row index), col 0 = WEST (lon increases
    #    with col index). Each native cell centre sits at the (index + 0.5) fraction
    #    of its axis across the FULL grid extent.
    lng_step = (max_lng - min_lng) / cols
    lat_step = (max_lat - min_lat) / rows

    def native_centre_lonlat(row: int, col: int) -> tuple[float, float]:
        lon = min_lng + (col + 0.5) * lng_step
        lat = min_lat + (row + 0.5) * lat_step
        return lon, lat

    # Fail-closed CRS guard once, up front, on the crop centroid (T-02a-04 / Pitfall 5).
    centroid_lon, centroid_lat = native_centre_lonlat(
        r0 + crop_rows / 2.0 - 0.5, c0 + crop_cols / 2.0 - 0.5
    )
    assert_crs_roundtrip(centroid_lon, centroid_lat)

    # Project EVERY native cell centre of the crop to EPSG:32631 metres via src/crs
    # (the ONLY lon/lat -> metre conversion). Store (x_m, y_m, value) per native cell.
    native_x = np.empty((crop_rows, crop_cols), dtype=float)
    native_y = np.empty((crop_rows, crop_cols), dtype=float)
    for i in range(crop_rows):
        for j in range(crop_cols):
            lon, lat = native_centre_lonlat(r0 + i, c0 + j)
            x_m, y_m = to_utm31n(lon, lat)
            native_x[i, j] = x_m
            native_y[i, j] = y_m

    # 3) RESAMPLE to the declared 6.0 m lattice. The metric extent comes from the
    #    projected native-centre coordinates; snap the SW origin DOWN to integer metres.
    sw_x = float(np.min(native_x))
    sw_y = float(np.min(native_y))
    ne_x = float(np.max(native_x))
    ne_y = float(np.max(native_y))
    origin_x_m = float(math.floor(sw_x))
    origin_y_m = float(math.floor(sw_y))

    # Cover the full projected extent of the native centres with a regular 6 m grid.
    width_m = ne_x - origin_x_m
    height_m = ne_y - origin_y_m
    out_cols = max(1, math.ceil(width_m / CELL_SIZE_M) or 1)
    out_rows = max(1, math.ceil(height_m / CELL_SIZE_M) or 1)
    # Guarantee every native centre falls within [origin, origin + n*CELL_SIZE_M).
    if origin_x_m + out_cols * CELL_SIZE_M <= ne_x:
        out_cols += 1
    if origin_y_m + out_rows * CELL_SIZE_M <= ne_y:
        out_rows += 1

    # Bin each native cell into its 6 m lattice cell; mean-aggregate the contributors.
    # A 6 m cell with NO non-NaN native contributor is OUTSIDE the polygon -> skip it.
    sums = np.zeros((out_rows, out_cols), dtype=float)
    counts = np.zeros((out_rows, out_cols), dtype=float)
    for i in range(crop_rows):
        for j in range(crop_cols):
            value = crop[i, j]
            if math.isnan(value):
                continue  # NaN native cell = outside polygon, contributes nothing
            col_idx = int((native_x[i, j] - origin_x_m) // CELL_SIZE_M)
            row_idx = int((native_y[i, j] - origin_y_m) // CELL_SIZE_M)
            col_idx = min(max(col_idx, 0), out_cols - 1)
            row_idx = min(max(row_idx, 0), out_rows - 1)
            sums[row_idx, col_idx] += value
            counts[row_idx, col_idx] += 1.0

    return origin_x_m, origin_y_m, out_rows, out_cols, sums, counts


def grid_to_utci_artifact(merged_grid, bounds) -> dict:
    """Convert an infrared ``merged_grid`` + ``bounds`` into a ``utci_grid`` artifact.

    Args:
        merged_grid: 2-D array-like of degrees Celsius. NaN = outside the site
            polygon. Convention: row 0 = SOUTH edge, col 0 = WEST edge, native
            ~1 m pitch (RESEARCH Pitfall 1).
        bounds: ``(min_lng, min_lat, max_lng, max_lat)`` WGS84 — the true grid
            extent (``result.bounds``, SDK 0.4.4+). The full grid spans this box.

    Returns:
        A contract-shaped ``utci_grid`` dict (passes ``validate(d, "utci_grid")``):
        ``schema_version``, ``crs`` (EPSG:32631 / metre), ``lattice`` (6.0 m,
        integer origin), and ``cells`` (every retained cell, ``baseline_utci_c ==
        utci_c``). Not validated here — the caller validates-then-writes (Plan 03).

    Raises:
        ValueError: if the grid is entirely NaN (no valid region to build a lattice
            from — never emit an empty/holey artifact, T-02a-06).
    """
    origin_x_m, origin_y_m, out_rows, out_cols, sums, counts = _resample_to_lattice(
        merged_grid, bounds
    )

    # 4) EMIT cells[]: one cell per retained 6 m bin (>=1 native contributor).
    #    baseline_utci_c == utci_c at emit (CLIMATE-04). Sub-threshold (comfortable)
    #    cells are PRESERVED (the drop is Phase-3 score-time — RESEARCH Pitfall 2).
    cells: list[dict] = []
    for row in range(out_rows):
        for col in range(out_cols):
            if counts[row, col] == 0:
                continue  # no native contributor -> outside polygon, not emitted
            mean = sums[row, col] / counts[row, col]
            utci_c = round(float(mean), 4)
            x_m = origin_x_m + (col + 0.5) * CELL_SIZE_M
            y_m = origin_y_m + (row + 0.5) * CELL_SIZE_M
            cells.append(
                {
                    "x_m": x_m,
                    "y_m": y_m,
                    "utci_c": utci_c,
                    "baseline_utci_c": utci_c,  # EQUAL at emit (CLIMATE-04)
                }
            )

    if not cells:
        raise ValueError("No non-NaN cells survived resampling — refusing empty artifact.")

    return {
        "schema_version": "1.0.0",
        "crs": {"epsg": 32631, "units": "metre"},
        "lattice": {
            "origin_x_m": origin_x_m,
            "origin_y_m": origin_y_m,
            "cell_size_m": CELL_SIZE_M,
            "cols": out_cols,
            "rows": out_rows,
        },
        "cells": cells,
    }


def grid_to_value_artifact(merged_grid, bounds, *, value_key: str, round_to: int = 4) -> dict:
    """Generic sibling of ``grid_to_utci_artifact`` for any scalar analysis grid.

    Same crop -> project -> 6 m resample spine, but emits one value per cell under a
    caller-named key (``sun_hours``, ``solar_wm2``, ``heat_stress_frac``, ...) and does
    NOT add the UTCI-specific ``baseline_*`` twin. The lattice geometry is identical to
    the canonical ``utci_grid`` for the SAME ``bounds``, so every layer snaps to the one
    master lattice the crowd field and placer already use.

    Args:
        value_key: the per-cell value field name (e.g. ``"sun_hours"``).
        round_to: decimal places for the emitted value.

    Returns:
        A ``{schema_version, crs, lattice, cells}`` dict; each cell is
        ``{"x_m", "y_m", value_key}``. NOT contract-validated against ``utci_grid``
        (different value key); these are diagnostic overlays, not the baseline.
    """
    origin_x_m, origin_y_m, out_rows, out_cols, sums, counts = _resample_to_lattice(
        merged_grid, bounds
    )

    cells: list[dict] = []
    for row in range(out_rows):
        for col in range(out_cols):
            if counts[row, col] == 0:
                continue  # no native contributor -> outside polygon, not emitted
            mean = sums[row, col] / counts[row, col]
            x_m = origin_x_m + (col + 0.5) * CELL_SIZE_M
            y_m = origin_y_m + (row + 0.5) * CELL_SIZE_M
            cells.append(
                {"x_m": x_m, "y_m": y_m, value_key: round(float(mean), round_to)}
            )

    if not cells:
        raise ValueError("No non-NaN cells survived resampling — refusing empty artifact.")

    return {
        "schema_version": "1.0.0",
        "crs": {"epsg": 32631, "units": "metre"},
        "lattice": {
            "origin_x_m": origin_x_m,
            "origin_y_m": origin_y_m,
            "cell_size_m": CELL_SIZE_M,
            "cols": out_cols,
            "rows": out_rows,
        },
        "cells": cells,
    }
