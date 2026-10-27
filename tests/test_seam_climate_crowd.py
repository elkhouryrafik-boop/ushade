"""XFN-04 climate x crowd lattice-alignment SEAM (the cross-phase contract).

The single most load-bearing cross-phase guarantee in Phase 2b: the crowd field snaps to
the climate master lattice and emits the SAME lattice object — so ``crowd_grid["lattice"]``
deep-equals ``utci_grid["lattice"]``. Re-deriving the lattice from bounds would reintroduce
the float-origin drift Phase 2a deliberately eliminated (T-02b-08). This mirrors
``tests/test_lattice_alignment.py`` but drives a REAL ``build_crowd_grid`` over the climate
side's lattice, proving the producer (not just a hand-built fixture) honours the seam.

Reuses ``tests/conftest.py``'s ``master_lattice`` / ``valid_utci_grid`` fixtures (the 3x3
master lattice + its matching UTCI grid). Torch-free (no ``crowd`` marker) — base suite.
"""

from __future__ import annotations

import numpy as np

from crowd.grid import build_crowd_grid
from validate.validate import validate


def _traj_on_lattice(lattice, *, steps: int = 30, agents: int = 6) -> np.ndarray:
    """A small still trajectory whose agents sit inside the given lattice extent.

    Parks all agents in the lattice's centre cell with |v| = 0 for the whole rollout, so the
    snap + dwell paths exercise on the REAL climate lattice (the point of the seam test is
    lattice EQUALITY, not the density field's shape).
    """
    cx = lattice["origin_x_m"] + lattice["cols"] * lattice["cell_size_m"] / 2.0
    cy = lattice["origin_y_m"] + lattice["rows"] * lattice["cell_size_m"] / 2.0
    traj = np.zeros((steps, agents, 4), dtype=np.float64)
    traj[:, :, 0] = cx
    traj[:, :, 1] = cy
    return traj  # velocities all 0 -> still agents inside the centre cell


def test_crowd_grid_lattice_equals_utci_lattice(valid_utci_grid):
    """XFN-04 POSITIVE: build_crowd_grid over utci_grid.lattice emits a byte-equal lattice."""
    lattice_in = valid_utci_grid["lattice"]
    crowd_grid = build_crowd_grid(_traj_on_lattice(lattice_in), lattice_in)
    # Deep-equality is THE alignment contract (mirrors test_lattice_alignment.py).
    assert crowd_grid["lattice"] == valid_utci_grid["lattice"]
    # And it is literally the SAME object read in (no copy, no re-derive).
    assert crowd_grid["lattice"] is lattice_in


def test_seam_artifact_validates_against_contract(valid_utci_grid):
    """The crowd_grid built on the climate lattice is itself contract-valid."""
    lattice_in = valid_utci_grid["lattice"]
    crowd_grid = build_crowd_grid(_traj_on_lattice(lattice_in), lattice_in)
    validate(crowd_grid, "crowd_grid")
    validate(valid_utci_grid, "utci_grid")  # the climate side is valid too


def test_seam_detects_lattice_drift(valid_utci_grid, master_lattice):
    """XFN-04 NEGATIVE: a drifted lattice is NOT equal — the seam catches drift.

    Feeding a cell_size-drifted lattice into the producer yields a crowd_grid whose lattice
    does NOT equal the utci_grid lattice — proving the equality assertion discriminates
    (guards the same Pitfall as test_lattice_alignment.test_mismatched_crowd_lattice_detected).
    """
    drifted = dict(master_lattice)
    drifted["cell_size_m"] = master_lattice["cell_size_m"] + 2.0
    crowd_grid = build_crowd_grid(_traj_on_lattice(drifted), drifted)
    assert crowd_grid["lattice"] != valid_utci_grid["lattice"]
