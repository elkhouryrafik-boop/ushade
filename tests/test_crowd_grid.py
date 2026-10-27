"""RED scaffold for the PURE crowd grid transform (CROWD-02/03/04) — Wave 0.

``crowd.grid.build_crowd_grid(trajectory, lattice)`` is the net-new pure transform Plan 03
ships (the analogue of Phase-2a ``lattice.py``): trajectory → lattice-snapped density +
dwell_zones (DBSCAN) + flow_vectors. It has NO torch/SB3 dependency, so these tests belong
to the BASE suite (NOT marked ``crowd``) once Plan 03 lands — they run torch-free against the
``conftest_crowd`` synthetic trajectory.

RED mechanism (deviation from the literal "fail at import", documented in the SUMMARY):
``grid.py`` does not exist yet, so a bare top-level ``from crowd.grid import ...`` would make
this whole module ERROR at collection and turn the base ``-m "not crowd"`` suite RED. To keep
the base regression green while STILL collecting the 4 named tests (the Task-3 acceptance
grep) and staying honestly RED, each test is ``skipif``-guarded on the absence of ``crowd.grid``
and does the import lazily inside the body. When Plan 03 ships ``grid.py``, ``find_spec`` finds
it, the skips lift, and these tests execute for real — locking the contract every later plan
is verified against. They are NOT marked ``crowd`` (grid.py is torch-free).

The synthetic trajectory has a KNOWN dwell cluster + 2 flow groups (see ``conftest_crowd``),
so each assertion has a ground truth.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

from conftest_crowd import synthetic_trajectory, tiny_lattice

# Lifts automatically once Plan 03 ships src/crowd/grid.py (honest RED-until-then).
_GRID_AVAILABLE = importlib.util.find_spec("crowd.grid") is not None
_needs_grid = pytest.mark.skipif(
    not _GRID_AVAILABLE, reason="src/crowd/grid.py lands in Plan 03 (RED scaffold)"
)


@_needs_grid
def test_dwell_zones_from_still_agents():
    """CROWD-02: DBSCAN over >10-consecutive-still agents yields ≥1 dwell zone (≥3-pt polygon)."""
    from crowd.grid import build_crowd_grid

    grid = build_crowd_grid(synthetic_trajectory(), tiny_lattice())
    zones = grid.get("dwell_zones", [])
    assert zones, "the known still-agent cluster must produce at least one dwell zone"
    for z in zones:
        assert len(z["polygon"]) >= 3, "dwell-zone polygon needs ≥3 points (contract)"


@_needs_grid
def test_flow_vectors_major_groups():
    """CROWD-03: the 2 known major groups yield ≥2 origin→destination flow vectors."""
    from crowd.grid import build_crowd_grid

    grid = build_crowd_grid(synthetic_trajectory(), tiny_lattice())
    flows = grid.get("flow_vectors", [])
    assert len(flows) >= 2, "the 2 known flow groups must produce ≥2 flow vectors"
    for f in flows:
        assert {"x_m", "y_m"} == set(f["origin"]), "flow origin must be a point_m"
        assert {"x_m", "y_m"} == set(f["destination"]), "flow destination must be a point_m"


@_needs_grid
def test_lattice_equals_utci():
    """CROWD-04: emitted crowd_grid.lattice is byte-equal to the lattice read in (alignment contract)."""
    from crowd.grid import build_crowd_grid

    lattice = tiny_lattice()
    grid = build_crowd_grid(synthetic_trajectory(), lattice)
    assert grid["lattice"] == lattice, "crowd_grid.lattice must equal the utci_grid lattice read in"


@_needs_grid
def test_density_snapped_by_integer_index():
    """CROWD-04: density cells snap by integer index onto the lattice (cell centres on the grid)."""
    from crowd.grid import build_crowd_grid

    lattice = tiny_lattice()
    grid = build_crowd_grid(synthetic_trajectory(), lattice)
    cells = grid["cells"]
    assert cells, "a populated trajectory must snap to ≥1 occupied cell"
    s = lattice["cell_size_m"]
    ox, oy = lattice["origin_x_m"], lattice["origin_y_m"]
    for c in cells:
        # Cell centre lies at origin + (int_index + 0.5) * cell_size (integer-index snap).
        col = (c["x_m"] - ox) / s - 0.5
        row = (c["y_m"] - oy) / s - 0.5
        assert abs(col - round(col)) < 1e-9, "x_m not on an integer-index cell centre"
        assert abs(row - round(row)) < 1e-9, "y_m not on an integer-index cell centre"
        assert c["crowd_density_agents_per_cell"] >= 0


@_needs_grid
def test_density_lands_in_expected_cell():
    """CROWD-04: an agent at a KNOWN (x_m, y_m) lands in the expected integer-index cell.

    Mirrors lattice.py's convention: an agent at (37, 49) on a 6 m lattice from origin
    (0,0) belongs to col = int(37//6) = 6, row = int(49//6) = 8, whose CENTRE is
    (6.5*6, 8.5*6) = (39.0, 51.0). The synthetic dwell cluster (parked ~(30,30)) lands in
    col=row=5 (centre 33.0,33.0).
    """
    from crowd.grid import snap_to_lattice

    lattice = tiny_lattice()
    cells = snap_to_lattice([(37.0, 49.0)], lattice)
    assert len(cells) == 1
    assert cells[0]["x_m"] == 39.0 and cells[0]["y_m"] == 51.0
    assert cells[0]["crowd_density_agents_per_cell"] == 1.0


@_needs_grid
def test_off_lattice_agents_dropped():
    """T-02b-09: agents outside the lattice extent are dropped, never emitted off-grid."""
    from crowd.grid import snap_to_lattice

    lattice = tiny_lattice()  # 20x20 cells of 6 m -> extent [0, 120) m
    cells = snap_to_lattice([(-10.0, 5.0), (5.0, 5.0), (1000.0, 1000.0)], lattice)
    # Only the in-bounds (5,5) agent survives.
    assert len(cells) == 1
    assert 0.0 <= cells[0]["x_m"] < 120.0 and 0.0 <= cells[0]["y_m"] < 120.0


def test_grid_module_is_torch_free():
    """T-02b-10: grid.py is statically + dynamically free of the heavy ML backends.

    Two guards mirroring Phase-2a's SDK quarantine: (1) STATIC — the source file contains
    none of the three forbidden tokens (the same grep the plan's acceptance runs); (2)
    DYNAMIC — importing crowd.grid pulls none of them into sys.modules. This test is NOT
    skipif-guarded (it must run even before/without grid.py) and is NOT ``crowd``-marked.
    """
    src = pathlib.Path(__file__).resolve().parents[1] / "src" / "crowd" / "grid.py"
    text = src.read_text(encoding="utf-8")
    for forbidden in ("torch", "stable_baselines3", "gymnasium"):
        assert forbidden not in text, f"grid.py must not reference {forbidden!r} (base-suite purity)"

    # Drop any pre-imported heavy modules, then import grid.py and assert it added none.
    for mod in ("torch", "stable_baselines3", "gymnasium"):
        sys.modules.pop(mod, None)
    importlib.import_module("crowd.grid")
    for mod in ("torch", "stable_baselines3", "gymnasium"):
        assert mod not in sys.modules, f"importing crowd.grid must not import {mod!r}"
