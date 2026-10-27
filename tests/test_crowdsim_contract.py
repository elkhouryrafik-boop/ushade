"""Contract conformance + XFN-04 lattice firewall on the JuPedSim path (CROWD-08).

The JuPedSim-produced ``crowd_grid`` must validate against the FROZEN
``contracts/crowd_grid.schema.json`` (the single-source ``validate(artifact, "crowd_grid")`` the
runtime + Node use — never a hand-rolled shape check), AND its ``lattice`` must be byte-equal to
the ``utci_grid.lattice`` it READ (XFN-04 / CONTRACT-03 — the lattice is read, never re-derived).
Because ``build_crowd_grid`` is FROZEN and re-emits the SAME lattice object, this holds BY
CONSTRUCTION once the JuPedSim path feeds it the ``(steps×agents×4)`` array — so a RED here means
the new code re-derived the lattice or built a parallel snap (Pitfall 4.4). Cells carry the lattice
CELL-CENTRE x/y (a join, never a positional zip).

``@pytest.mark.crowdsim``: runs the real JuPedSim path. DESIGNED-RED at Wave 0 (no engine yet);
GREEN at Wave 3. Collects cleanly today.
"""

from __future__ import annotations

import json

import pytest

# conftest_crowdsim is imported EXPLICITLY (not auto-loaded).
from conftest_crowdsim import crowdsim_real_site_project, load_committed_utci
from crowd.crowd import run_crowd_stage
from validate.validate import validate

pytestmark = pytest.mark.crowdsim


def test_crowd_grid_valid_and_lattice_byte_equal(tmp_path):
    """The JuPedSim crowd_grid is schema-valid AND its lattice is byte-equal to utci_grid.lattice.

    Validates against the frozen ``crowd_grid`` contract (no raise) and asserts XFN-04: the emitted
    ``lattice`` is byte-equal to the READ ``utci_grid.lattice`` (CONTRACT-03 — lattice READ, never
    re-derived). Both the in-memory return AND the persisted artifact carry the same lattice.
    """
    pdir = crowdsim_real_site_project(tmp_path, "contract-real", capacity=800)
    utci = load_committed_utci()

    artifact = run_crowd_stage("contract-real", projects_root=tmp_path)

    validate(artifact, "crowd_grid")  # raises ValidationError on any contract violation

    assert artifact["lattice"] == utci["lattice"], (
        "XFN-04: crowd_grid.lattice must be byte-equal to utci_grid.lattice (lattice READ, never "
        "re-derived — CONTRACT-03). A diff here means the JuPedSim path re-derived the lattice."
    )
    persisted = json.loads((pdir / "crowd_grid.json").read_text(encoding="utf-8"))
    assert persisted["lattice"] == utci["lattice"], "the lattice seam must hold on disk too"


def test_cells_are_cell_centre_join_not_zip(tmp_path):
    """Every crowd cell carries lattice CELL-CENTRE x/y (a (row,col) join — never a positional zip).

    Guards Pitfall 4.4: each emitted cell's (x_m, y_m) must sit on a lattice cell centre
    (``origin + (idx + 0.5) * cell_size_m``), proving the density was JOINED onto the lattice by
    index, not positionally zipped against the UTCI cell list.
    """
    crowdsim_real_site_project(tmp_path, "join-real", capacity=800)
    lattice = load_committed_utci()["lattice"]
    ox, oy, s = lattice["origin_x_m"], lattice["origin_y_m"], lattice["cell_size_m"]

    artifact = run_crowd_stage("join-real", projects_root=tmp_path)

    assert artifact["cells"], "a populated real-site run must snap to >=1 cell"
    for cell in artifact["cells"]:
        assert set(cell) == {"x_m", "y_m", "crowd_density_agents_per_cell"}
        col = (cell["x_m"] - ox) / s - 0.5
        row = (cell["y_m"] - oy) / s - 0.5
        assert abs(col - round(col)) < 1e-6 and abs(row - round(row)) < 1e-6, (
            f"cell ({cell['x_m']}, {cell['y_m']}) is not on a lattice cell centre — the density "
            f"was positionally zipped, not (row,col)-joined onto the master lattice (Pitfall 4.4)."
        )
