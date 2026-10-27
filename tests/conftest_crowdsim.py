"""Torch-free / jupedsim-free test scaffolding for the Phase-15 crowdsim suite.

Like ``conftest_crowd.py``, this module is imported EXPLICITLY by the crowdsim tests — it is
NOT auto-loaded (pytest only auto-loads ``conftest.py``). It provides the two seams the Wave-0
RED scaffold needs WITHOUT pulling jupedsim (which is not installed until Wave 4):

* :func:`crowdsim_real_site_project` — seeds a project dir under ``tmp_path`` with the committed
  ``projects/primavera-demo`` real-site inputs (``parsed_brief.json`` shaped with
  ``capacity = PRIMAVERA_DAILY_CAPACITY`` and the committed ``utci_grid.json`` lattice/cells), so
  a real-site ``run_crowd_stage`` rolls the JuPedSim engine over the ~800 m Parc del Fòrum
  geometry (the BLOCKING DoD gate's geometry source). Mirrors
  ``conftest_crowd.build_real_site_env``'s read of the committed ``utci_grid.json`` (the lattice is
  READ, never re-derived — CONTRACT-03).

* :func:`fake_sim_factory` — a torch/jupedsim-free injectable ``sim_factory`` returning a callable
  ``(*, lattice, utci_cells, n_agents, seed) -> (steps×agents×4) numpy array`` built from
  ``conftest_crowd.synthetic_trajectory`` (sliced to ``n_agents``). The base-tier provenance/purity
  tests inject this so they assert the shell's provenance/purity WITHOUT jupedsim — the same
  injected-fake discipline ``test_crowd.py`` uses with ``env_factory``.

DoD far-region helper (15-04 Task 1): ``_far_stage_waiting_regions`` (and its flat-union convenience
``_far_stage_waiting_cells``) derive the BLOCKING DoD gate's far-stage waiting regions — the farthest
gate-A-reachable stages by ``flowfield.bfs_distance`` and each one's ``REACH_RADIUS_M`` disc of
finite-bfs lattice cells. This promotes the Plan-01 inline derivation into the shared seam, with the
honest D-03 ``bfs_distance == inf`` exclusions (stage- AND cell-level) applied inside. The gate
asserts each far-stage REGION receives density (D-01), not every individual disc pixel.

karpathy: plain stdlib + numpy; any heavy import is lazy so this module imports clean with NO
crowdsim/crowd extra installed.
"""

from __future__ import annotations

import json
from pathlib import Path

# synthetic_trajectory is the torch-free (steps×agents×4) ground truth reused as the fake sim
# output — imported from the sibling crowd conftest (NOT auto-loaded; explicit like this module).
from conftest_crowd import synthetic_trajectory
from crowd.constants import PRIMAVERA_DAILY_CAPACITY

_REPO_ROOT_CROWDSIM = Path(__file__).resolve().parent.parent
#: The committed REAL-site inputs (the same lattice + cells the V2 harness reads). The DoD reach /
#: contract / determinism tests seed a project dir from these so the JuPedSim path runs on the
#: real ~800 m Parc del Fòrum geometry.
_PRIMAVERA_DEMO = _REPO_ROOT_CROWDSIM / "projects" / "primavera-demo"
_UTCI_GRID_PATH = _PRIMAVERA_DEMO / "utci_grid.json"


def crowdsim_real_site_project(
    projects_root: Path, project_id: str = "forum-real", *, capacity: int = PRIMAVERA_DAILY_CAPACITY
) -> Path:
    """Seed ``<projects_root>/<project_id>/`` with the committed real-site crowd inputs.

    Writes the two files ``run_crowd_stage`` reads: a ``parsed_brief.json`` carrying ``capacity``
    (default the documented Primavera daily capacity → N = capacity // AGENT_DIVISOR agents) and a
    copy of the committed ``projects/primavera-demo/utci_grid.json`` (the READ master lattice +
    cells — CONTRACT-03). Returns the seeded project dir.

    Mirrors ``conftest_crowd.build_real_site_env``'s committed-input read (lines 340-341) so the DoD
    gate measures the JuPedSim path on exactly the geometry the runtime stage uses.
    """
    pdir = Path(projects_root) / project_id
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "parsed_brief.json").write_text(
        json.dumps({"capacity": int(capacity)}), encoding="utf-8"
    )
    # Copy the committed real-site utci_grid.json verbatim (lattice READ, never re-derived).
    utci = json.loads(_UTCI_GRID_PATH.read_text(encoding="utf-8"))
    (pdir / "utci_grid.json").write_text(json.dumps(utci), encoding="utf-8")
    return pdir


def load_committed_utci() -> dict:
    """Return the committed real-site ``utci_grid.json`` dict (lattice + cells), READ verbatim."""
    return json.loads(_UTCI_GRID_PATH.read_text(encoding="utf-8"))


def fake_sim_factory(counter: list[int] | None = None):
    """Return a torch/jupedsim-free ``sim_factory`` yielding a synthetic ``(steps×agents×4)`` array.

    The returned callable has the EXACT injection signature the Wave-2 shell will call —
    ``(*, lattice, utci_cells, n_agents, seed) -> np.ndarray`` — so the base-tier provenance/purity
    tests drive ``run_crowd_stage`` with NO jupedsim installed (mirror of ``test_crowd.py``'s
    injected ``env_factory``). If ``counter`` is given it bumps once per call (a rollout proxy for a
    cache-hit assertion).
    """

    def _factory(*, lattice=None, utci_cells=None, n_agents=1, seed=0):  # noqa: ARG001
        if counter is not None:
            counter[0] += 1
        traj = synthetic_trajectory()  # (steps × 19 × 4) known-structure ground truth
        return traj[:, : int(n_agents), :]

    return _factory


def _cell_index(x_m: float, y_m: float, lattice: dict) -> tuple[int, int]:
    """Map a UTM31N (x, y) to its ``(col, row)`` lattice index (grid.snap_to_lattice convention)."""
    ox = lattice["origin_x_m"]
    oy = lattice["origin_y_m"]
    s = lattice["cell_size_m"]
    return int((x_m - ox) // s), int((y_m - oy) // s)


def _far_stage_waiting_regions(lattice: dict) -> list[dict]:
    """The DoD gate's far-stage waiting REGIONS, one per farthest-reachable stage (15-04).

    Promotes the Plan-01 inline derivation into a shared, per-stage form. Picks the farthest REACHABLE
    stages by gate-A geodesic (``flowfield.bfs_distance``, the SAME field the router follows) and, for
    each, returns its ``REACH_RADIUS_M`` waiting-set REGION = the finite-bfs lattice cells inside the
    disc the dwell positions snap to. Returns a list of
    ``{"stage_index", "name", "bfs_distance", "centre_cell", "cells"}`` dicts (the per-stage grouping
    the D-01 region gate needs; the flat union is :func:`_far_stage_waiting_cells`).

    Two HONEST D-03 exclusions (geometric unreachability — never papering over a wiring bug; each
    documented in the 15-04 SUMMARY with its ``bfs_distance == inf`` proof):

    1. **Stage-level:** a stage whose gate-A ``bfs_distance`` is ``inf`` is genuinely unreachable (its
       centre cell sits inside a blocker footprint) — EXCLUDED from the far-stage cohort entirely.
    2. **Cell-level:** an individual disc cell whose ``bfs_distance`` is ``inf`` (inside a blocker /
       outside the walkable area) can NEVER receive density — no agent can stand on a blocked cell —
       so it is EXCLUDED from a region's asserted cells. This is the SAME D-03 honest relaxation at
       cell granularity; it does NOT relax any reachable (finite-bfs) cell, so a far stage whose
       ENTIRE region reads zero (the old ~0% failure) still FAILS the gate (a real mis-wire — fixed,
       never relaxed).

    ``REACH_RADIUS_M`` is read from ``crowd.constants`` (never an inline literal — anti-tuning).
    """
    import math

    from crowd.constants import REACH_RADIUS_M
    from crowd.flowfield import bfs_distance
    from crowd.site import load_site_geometry

    geo = load_site_geometry(lattice=lattice)
    stages_utm = geo["stages_utm"]
    stage_meta = geo.get("stage_meta", [{} for _ in stages_utm])
    blocked = geo["blocked_cells"]
    cols, rows = lattice["cols"], lattice["rows"]

    # Gate A (general entrance) cell — the wavefront SOURCE the router uses.
    gate_a_x, gate_a_y = geo["entrances_utm"][0]
    gate_cell = _cell_index(gate_a_x, gate_a_y, lattice)
    dist = bfs_distance(blocked, cols, rows, gate_cell)

    def _finite_bfs(col: int, row: int) -> bool:
        return 0 <= col < cols and 0 <= row < rows and math.isfinite(float(dist[col, row]))

    # Geodesic gate-A distance to each stage (∞ for genuinely unreachable stages → excluded, D-03 #1).
    reachable: list[tuple[float, int, tuple[float, float]]] = []
    for i, (sx, sy) in enumerate(stages_utm):
        scol, srow = _cell_index(sx, sy, lattice)
        if _finite_bfs(scol, srow):
            reachable.append((float(dist[scol, srow]), i, (sx, sy)))

    assert reachable, "no reachable stage found from gate A — real-site geometry is mis-loaded"
    reachable.sort(key=lambda t: t[0], reverse=True)
    # The farthest ~third of reachable stages (the cohort a too-short horizon starves first).
    n_far = max(1, len(reachable) // 3)
    far = reachable[:n_far]

    # Each far stage's waiting REGION = the finite-bfs lattice cells inside its REACH_RADIUS_M disc
    # the dwell positions snap to (D-03 #2: a blocked/∞ disc cell can never get density → dropped).
    s = lattice["cell_size_m"]
    n_ring = max(4, int(round(2 * math.pi * REACH_RADIUS_M / s)))
    regions: list[dict] = []
    for d, idx, (sx, sy) in far:
        cells: set[tuple[int, int]] = set()
        centre = _cell_index(sx, sy, lattice)
        if _finite_bfs(*centre):
            cells.add(centre)
        for k in range(n_ring):
            theta = 2 * math.pi * k / n_ring
            cell = _cell_index(sx + REACH_RADIUS_M * math.cos(theta), sy + REACH_RADIUS_M * math.sin(theta), lattice)
            if _finite_bfs(*cell):
                cells.add(cell)
        regions.append(
            {
                "stage_index": idx,
                "name": stage_meta[idx].get("name", f"stage-{idx}") if idx < len(stage_meta) else f"stage-{idx}",
                "bfs_distance": d,
                "centre_cell": centre,
                "cells": cells,
            }
        )
    return regions


def _far_stage_waiting_cells(lattice: dict) -> set[tuple[int, int]]:
    """Flat union of all far-stage waiting REGION cells (the per-stage grouping is
    :func:`_far_stage_waiting_regions`). Same honest D-03 stage- and cell-level ``bfs_distance == inf``
    exclusions; ``REACH_RADIUS_M`` read from ``crowd.constants`` (never inline)."""
    cells: set[tuple[int, int]] = set()
    for region in _far_stage_waiting_regions(lattice):
        cells |= region["cells"]
    return cells
