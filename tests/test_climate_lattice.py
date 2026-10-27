"""Unit tests for the Phase 2a grid->contract transform (``climate.lattice``).

These exercise the single load-bearing new function of the phase,
``grid_to_utci_artifact``, in full isolation (it is pure — no SDK, no network).
They lock CONTRACT-03 (master lattice), CLIMATE-02 (sub-threshold cell preserved),
and CLIMATE-04 (per-cell no-shade baseline == utci at emit), plus the no-lat/lon-leak
and no-empty-artifact threat mitigations (T-02a-04 / T-02a-05 / T-02a-06).

The recorded Plan-01 fixture (``utci_response_small.json``: 8x8 grid, NaN border,
a known 24.5 C interior cell) is the primary input; tiny explicit grids cover the
crop and all-NaN edge cases. The fake-SDK / fixture loaders live in
``tests/conftest_climate.py`` (imported explicitly — pytest only auto-loads
``conftest.py``).
"""

from __future__ import annotations

from math import floor, isnan, nan

import pytest

from climate.lattice import CELL_SIZE_M, grid_to_utci_artifact
from conftest_climate import load_recorded_utci_response
from validate.validate import validate


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _grid_with_nan(grid: list[list]) -> list[list[float]]:
    """JSON ``null`` -> ``float('nan')`` (NaN = outside the polygon)."""
    return [[float("nan") if c is None else float(c) for c in row] for row in grid]


def _artifact_from_fixture() -> dict:
    """Build the artifact from the recorded Plan-01 UTCI response."""
    resp = load_recorded_utci_response()
    grid = _grid_with_nan(resp["merged_grid"])
    return grid_to_utci_artifact(grid, resp["bounds"])


# Bounds reused for the tiny inline grids (the real Parc del Forum box, WGS84).
_BOUNDS = (2.2200, 41.4100, 2.2210, 41.4112)


# --------------------------------------------------------------------------- #
# Contract shape (CLIMATE-01 / CONTRACT-02)
# --------------------------------------------------------------------------- #
def test_artifact_validates():
    """The emitted dict passes the utci_grid contract validator."""
    art = _artifact_from_fixture()
    # Raises jsonschema.ValidationError on any contract violation.
    validate(art, "utci_grid")


# --------------------------------------------------------------------------- #
# Crop to non-NaN bbox (RESEARCH Pattern 2 / Pitfall 1)
# --------------------------------------------------------------------------- #
def test_nan_border_cropped():
    """An all-NaN border is cropped: cells[] count == the interior non-NaN count,
    never the full grid (the 512x512 corner gotcha)."""
    # 4x4 grid with a 1-cell all-NaN border -> 2x2 = 4 interior non-NaN cells.
    grid = [
        [nan, nan, nan, nan],
        [nan, 30.0, 31.0, nan],
        [nan, 28.0, 24.0, nan],
        [nan, nan, nan, nan],
    ]
    art = grid_to_utci_artifact(grid, _BOUNDS)
    assert len(art["cells"]) == 4  # interior, not the full 16


# --------------------------------------------------------------------------- #
# Sub-threshold preservation (CLIMATE-02 / RESEARCH Pitfall 2 / T-02a-05)
# --------------------------------------------------------------------------- #
def test_sub26_cell_present_in_artifact():
    """The known <26 C fixture cell (24.5 at [3][3]) is REPRESENTED among cells[]
    utci_c values — preserved at write time; the <26 drop is score-time (Phase 3)."""
    art = _artifact_from_fixture()
    utci_values = [c["utci_c"] for c in art["cells"]]
    # The 24.5 C cell maps to its own 6 m bin (distinct native centres bin 1:1 here),
    # so the value survives unchanged.
    assert any(abs(v - 24.5) < 1e-6 for v in utci_values)
    # And at least one emitted cell is below the 26 C comfort threshold (not dropped).
    assert any(v < 26.0 for v in utci_values)


# --------------------------------------------------------------------------- #
# Baseline semantics (CLIMATE-04 / CONTRACT-05)
# --------------------------------------------------------------------------- #
def test_baseline_equals_utci_at_emit():
    """Every cell carries baseline_utci_c == utci_c at emit (the frozen no-shade
    denominator equals the current field before any intervention exists)."""
    art = _artifact_from_fixture()
    assert art["cells"], "expected a non-empty artifact"
    for cell in art["cells"]:
        assert cell["baseline_utci_c"] == cell["utci_c"]


# --------------------------------------------------------------------------- #
# Declared master resolution (CONTRACT-03 / Pitfall 8)
# --------------------------------------------------------------------------- #
def test_cell_size_is_6m():
    """The lattice declares the 6.0 m master resolution, == the module constant."""
    art = _artifact_from_fixture()
    assert CELL_SIZE_M == 6.0
    assert art["lattice"]["cell_size_m"] == CELL_SIZE_M == 6.0


def test_origin_snapped_integer_metres():
    """origin_x_m / origin_y_m are whole metres (snapped DOWN to floor) so 2b/3 can
    snap by integer index."""
    art = _artifact_from_fixture()
    ox = art["lattice"]["origin_x_m"]
    oy = art["lattice"]["origin_y_m"]
    assert ox == floor(ox)
    assert oy == floor(oy)


# --------------------------------------------------------------------------- #
# No lat/lon leak (RESEARCH Pitfall 1 / T-02a-04)
# --------------------------------------------------------------------------- #
def test_coords_are_projected_metres():
    """At least one cell easting > 180 (a UTM magnitude, never a degree), and the
    CRS is exactly EPSG:32631 / metre — the single lon/lat -> metre conversion ran."""
    art = _artifact_from_fixture()
    assert art["crs"] == {"epsg": 32631, "units": "metre"}
    assert any(abs(c["x_m"]) > 180.0 for c in art["cells"])


# --------------------------------------------------------------------------- #
# Lattice descriptor consistency (CONTRACT-03)
# --------------------------------------------------------------------------- #
def test_lattice_descriptor_consistent():
    """All 5 lattice keys present, cols/rows >= 1, and rows*cols >= len(cells)
    (a regular grid descriptor consistent with the emitted cells)."""
    art = _artifact_from_fixture()
    lattice = art["lattice"]
    for key in ("origin_x_m", "origin_y_m", "cell_size_m", "cols", "rows"):
        assert key in lattice
    assert lattice["cols"] >= 1
    assert lattice["rows"] >= 1
    assert lattice["rows"] * lattice["cols"] >= len(art["cells"])


# --------------------------------------------------------------------------- #
# No empty / holey artifact (T-02a-06)
# --------------------------------------------------------------------------- #
def test_all_nan_grid_raises():
    """An entirely-NaN grid raises ValueError — never an empty/holey artifact."""
    grid = [[nan, nan], [nan, nan]]
    with pytest.raises(ValueError):
        grid_to_utci_artifact(grid, _BOUNDS)
