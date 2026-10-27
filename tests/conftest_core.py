"""Hand-computable tiny-lattice fixtures for the Phase-3 greedy-core Wave-0 RED scaffold.

Like ``conftest_crowd.py`` / ``conftest_climate.py``, this module is imported EXPLICITLY by
the Phase-3 tests — it is NOT auto-loaded (pytest only auto-loads ``conftest.py``). It exists
so the pure transforms (``core.score.score_and_allocate``, ``core.footprint.build_footprint``,
Plan 02) and the orchestrator (``core.core.run_core_stage``, Plan 03) can be unit-tested with
KNOWN-by-hand score orderings and EXACT budget stop points — no real run, no randomness.

Everything here is on a tiny 3x3 master lattice (``cell_size_m = 6.0``, integer origin) so the
score = ``crowd_density * max(utci_c - 26, 0)`` ordering and the greedy budget stop are
hand-verifiable (the determinism proof that backs CORE-05's byte-identical-rerun test).

THE TINY GRID (row-major; row 0 is the bottom row of the lattice — cell centres are
``origin + (col+0.5)*cell``, ``origin + (row+0.5)*cell``):

    utci_c:                 crowd_density_agents_per_cell:
      row0 [25.0 28.0 30.0]   row0 [5.0 0.0 2.0]
      row1 [27.0 28.0 32.0]   row1 [3.0 4.0 1.0]
      row2 [29.0 26.0 31.0]   row2 [2.0 9.0 1.0]

    score = density * max(utci - 26, 0), sorted by (-score, row, col):

      score   (row,col)   note
      ------  ---------   ------------------------------------------------
       8.00   (0, 2)      tie with (1,1) — (row,col) tiebreak puts (0,2) FIRST
       8.00   (1, 1)
       6.00   (1, 2)      tie with (2,0) — (row,col) tiebreak puts (1,2) FIRST
       6.00   (2, 0)
       5.00   (2, 2)
       3.00   (1, 0)
       0.00   (0, 0)      SUB-26 (utci 25.0) -> excess 0 -> score 0 even at density 5.0  (CORE-06)
       0.00   (0, 1)      ZERO-DENSITY (density 0.0) -> score 0 even at utci 28.0          (CORE-06)
       0.00   (2, 1)      utci == 26.0 EXACTLY -> excess clamped to 0 -> score 0           (CORE-06)

So exactly 6 cells score > 0, in the fixed order
``[(0,2), (1,1), (1,2), (2,0), (2,2), (1,0)]``; the two pairs of ties exercise the (row,col)
tiebreak; the three zero-score cells (one sub-26, one zero-density, one == threshold) are the
explicit guardrail targets.

Per-cell shade cost = ``ASSUMED_COST_PER_M2 (25.0) * CELL_AREA_M2 (36.0) = 900.0`` €.

karpathy: plain dicts, no fixture-factory framework; no torch/shapely import at module top
(shapely is exercised only inside the transforms the orchestrator calls).
"""

from __future__ import annotations

import copy
import json

import pytest

from core.constants import ASSUMED_COST_PER_M2, CELL_AREA_M2

# ── lattice + hand-built grids ──────────────────────────────────────────────
_CELL = 6.0
_ORIGIN_X = 0.0
_ORIGIN_Y = 0.0
_CRS = {"epsg": 32631, "units": "metre"}

# row-major: index [row][col]
_UTCI_C = [
    [25.0, 28.0, 30.0],
    [27.0, 28.0, 32.0],
    [29.0, 26.0, 31.0],
]
_DENSITY = [
    [5.0, 0.0, 2.0],
    [3.0, 4.0, 1.0],
    [2.0, 9.0, 1.0],
]

#: Per-cell shade cost (€) — the SAME product the transform/orchestrator use. Named here (never
#: an inline literal) so the budget fixtures below stay in lock-step with the constants module.
COST_PER_CELL: float = ASSUMED_COST_PER_M2 * CELL_AREA_M2  # 25.0 * 36.0 = 900.0

#: The hand-computed (row, col) order of the cells that score > 0, descending by score with the
#: (row, col) tiebreak. The RED tests assert the transform reproduces THIS exact ordering.
EXPECTED_POSITIVE_ORDER: list[tuple[int, int]] = [
    (0, 2),  # score 8.00 (tie head)
    (1, 1),  # score 8.00
    (1, 2),  # score 6.00 (tie head)
    (2, 0),  # score 6.00
    (2, 2),  # score 5.00
    (1, 0),  # score 3.00
]


def _cell_centre(col: int, row: int) -> tuple[float, float]:
    return (_ORIGIN_X + (col + 0.5) * _CELL, _ORIGIN_Y + (row + 0.5) * _CELL)


def _lattice() -> dict:
    return {
        "origin_x_m": _ORIGIN_X,
        "origin_y_m": _ORIGIN_Y,
        "cell_size_m": _CELL,
        "cols": 3,
        "rows": 3,
    }


def _utci_grid() -> dict:
    cells = []
    for row in range(3):
        for col in range(3):
            x_m, y_m = _cell_centre(col, row)
            utci_c = _UTCI_C[row][col]
            cells.append(
                {
                    "x_m": x_m,
                    "y_m": y_m,
                    "utci_c": utci_c,
                    "baseline_utci_c": utci_c + 0.5,
                }
            )
    return {
        "schema_version": "1.0.0",
        "crs": dict(_CRS),
        "lattice": _lattice(),
        "cells": cells,
    }


def _crowd_grid(lattice: dict) -> dict:
    cells = []
    for row in range(3):
        for col in range(3):
            x_m, y_m = _cell_centre(col, row)
            cells.append(
                {
                    "x_m": x_m,
                    "y_m": y_m,
                    "crowd_density_agents_per_cell": _DENSITY[row][col],
                }
            )
    return {
        "schema_version": "1.0.0",
        "crs": dict(_CRS),
        "lattice": copy.deepcopy(lattice),  # SAME lattice values (the XFN-04 seam holds)
        "cells": cells,
    }


def _build_inputs(*, budget: float) -> dict:
    """A dict bundle {utci, crowd, budget, lattice, expected_order, cost_per_cell}."""
    utci = _utci_grid()
    crowd = _crowd_grid(utci["lattice"])
    return {
        "utci": utci,
        "crowd": crowd,
        "budget": budget,
        "lattice": utci["lattice"],
        "expected_order": list(EXPECTED_POSITIVE_ORDER),
        "cost_per_cell": COST_PER_CELL,
    }


# ── fixtures (the four hand-computable scenarios) ───────────────────────────
@pytest.fixture
def tiny_score_inputs() -> dict:
    """3x3 grids with a KNOWN descending score order, two ties, a sub-26 cell, a zero-density
    cell, and an exactly-26 cell. Budget large enough to reach the first score==0 cell so the
    ordering/guardrail tests see the full positive set. (score==0 stop, not budget stop.)"""
    return _build_inputs(budget=1_000_000.0)


@pytest.fixture
def budget_exhaust_inputs() -> dict:
    """Budget = 2 * COST_PER_CELL (1800 €) -> funds EXACTLY 2 cells, then ``spent >= budget``
    fires on the 3rd iteration (CORE-03 budget stop). Marked = [(0,2), (1,1)]."""
    return _build_inputs(budget=2.0 * COST_PER_CELL)


@pytest.fixture
def score_zero_stop_inputs() -> dict:
    """Budget large enough that the greedy loop reaches the FIRST score==0 cell and stops there
    (CORE-03 zero-score stop) — exactly the 6 positive cells are funded, the 3 zero cells never."""
    return _build_inputs(budget=1_000_000.0)


@pytest.fixture
def infeasible_inputs() -> dict:
    """Budget below the cost of a single cell (450 € < COST_PER_CELL 900 €) -> no cell affordable
    -> the stage must emit an infeasibility report and an EMPTY footprint (CORE-04 / Pitfall 5,
    min-viable = cost of one cell)."""
    return _build_inputs(budget=COST_PER_CELL / 2.0)


# ── seeding helper (adapt test_crowd.py::_seed_inputs, lines 91-97) ─────────
def _seed_inputs(pdir, *, utci: dict, crowd: dict, budget) -> None:
    """Write parsed_brief.json + utci_grid.json + crowd_grid.json into ``pdir`` (the three
    inputs ``run_core_stage`` reads). ``parsed_brief`` carries ``budget`` (Phase 3 reads
    ``brief["budget"]``, NOT capacity — parsed_brief.schema.json)."""
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "parsed_brief.json").write_text(json.dumps({"budget": budget}), encoding="utf-8")
    (pdir / "utci_grid.json").write_text(json.dumps(utci), encoding="utf-8")
    (pdir / "crowd_grid.json").write_text(json.dumps(crowd), encoding="utf-8")


#: Default whole-site shadow polygon enclosing the full tiny 3x3 grid (centres at 3/9/15 m, so the
#: grid spans 0..18 m), origin-keyed min-corner. For the OPTIONAL ``PersistedShadowCoverage``
#: whole-site path — the DEMO per-candidate ranking path (``OffsetShadowCoverage``) needs NO gh_meta.
TINY_SHADOW_POLYGON_M: dict = {
    "min_corner_m": [0.0, 0.0],
    "polygons_xy_m": [[[0.0, 0.0], [18.0, 0.0], [18.0, 18.0], [0.0, 18.0], [0.0, 0.0]]],
}


def _seed_inputs_with_gh_meta(
    pdir, *, utci: dict, crowd: dict, budget, shadow_polygon_m: dict | None = None
) -> None:
    """``_seed_inputs`` PLUS a ``gh_meta.json`` carrying ``shadow_polygon_m`` (whole-site path).

    Sibling of ``_seed_inputs`` for the OPTIONAL ``PersistedShadowCoverage`` (whole-site) model.
    Defaults to ``TINY_SHADOW_POLYGON_M`` (the full-grid ring). The demo per-candidate canopy model
    does not require gh_meta — this helper exists only for the whole-site shadow representation.
    """
    _seed_inputs(pdir, utci=utci, crowd=crowd, budget=budget)
    poly = TINY_SHADOW_POLYGON_M if shadow_polygon_m is None else shadow_polygon_m
    (pdir / "gh_meta.json").write_text(
        json.dumps({"shadow_polygon_m": poly}), encoding="utf-8"
    )
