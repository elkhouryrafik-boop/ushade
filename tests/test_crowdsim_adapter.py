"""Unit tests for the pure-numpy crowdsim adapter + the jupedsim-free festival mapping (15-02).

These are BASE-tier tests (NOT ``crowdsim``-marked): the adapter is pure numpy and the mapping
imports no jupedsim wheel, so both are unit-testable WITHOUT the engine installed (the lazy-import
discipline — jupedsim only enters on ``simulation.py``'s factory path). They assert the two Task-1
contracts:

* :func:`crowdsim.adapter.to_trajectory` finite-differences per-step (x,y) positions into the
  FROZEN ``(steps × agents × 4)`` array ``[x, y, vx, vy]`` ``build_crowd_grid`` consumes, dividing
  the position delta by ``STEP_DT_JPS_S`` and zeroing the terminal/first-frame velocity.
* :func:`crowdsim.mapping.build_primitive_spec` reuses the FROZEN festival layer verbatim
  (``load_site_geometry`` + ``goal_weights_for_slice``) and emits a plain-data spec dict with NO
  jupedsim import (``crowdsim.mapping`` never enters ``sys.modules['jupedsim']``).
"""

from __future__ import annotations

import sys

import numpy as np

from crowd.constants import REACH_RADIUS_M, SPAWN_FRAC_GATE_A, STEP_DT_JPS_S


def test_to_trajectory_shape_and_zero_first_velocity():
    """A (steps, agents, 2) positions block → (steps, agents, 4); first-frame velocity is 0."""
    from crowdsim.adapter import to_trajectory

    out = to_trajectory(np.zeros((3, 2, 2)))
    assert out.shape == (3, 2, 4)
    assert (out[0, :, 2:] == 0).all()


def test_to_trajectory_finite_diff_divides_by_step_dt():
    """vx,vy = (pos[t] - pos[t-1]) / STEP_DT_JPS_S — a known ramp gives a constant velocity."""
    from crowdsim.adapter import to_trajectory

    # one agent walking +3 m in x and +4 m in y each step.
    pos = np.array(
        [[[0.0, 0.0]], [[3.0, 4.0]], [[6.0, 8.0]]],
        dtype=float,
    )  # (3 steps, 1 agent, 2)
    out = to_trajectory(pos)
    assert out.shape == (3, 1, 4)
    # positions carried through verbatim
    assert np.allclose(out[:, :, :2], pos)
    # first-frame velocity zero
    assert np.allclose(out[0, 0, 2:], [0.0, 0.0])
    # subsequent frames: delta / STEP_DT_JPS_S
    assert np.allclose(out[1, 0, 2:], np.array([3.0, 4.0]) / STEP_DT_JPS_S)
    assert np.allclose(out[2, 0, 2:], np.array([3.0, 4.0]) / STEP_DT_JPS_S)


def test_to_trajectory_parked_agent_keeps_zero_velocity():
    """An agent that stops moving (parked at a stage front) holds velocity 0 (A2)."""
    from crowdsim.adapter import to_trajectory

    pos = np.array(
        [[[10.0, 10.0]], [[10.0, 10.0]], [[10.0, 10.0]]],
        dtype=float,
    )
    out = to_trajectory(pos)
    assert (out[:, :, 2:] == 0).all()


def test_adapter_imports_no_jupedsim():
    """Importing the adapter pulls NO jupedsim wheel (pure numpy — base tier safe)."""
    sys.modules.pop("jupedsim", None)
    import crowdsim.adapter  # noqa: F401

    assert "jupedsim" not in sys.modules


def test_build_primitive_spec_reuses_frozen_festival_layer():
    """build_primitive_spec(lattice=...) emits a plain-data spec from the FROZEN geo dict."""
    from conftest_crowdsim import load_committed_utci

    from crowdsim.mapping import build_primitive_spec

    lattice = load_committed_utci()["lattice"]
    spec = build_primitive_spec(lattice=lattice)

    # plain-data contract — keys the simulation builder consumes
    for key in (
        "boundary_rings",
        "blocker_rings",
        "sources",
        "stages_utm",
        "goal_weights",
        "reach_radius_m",
    ):
        assert key in spec, f"spec missing {key!r}"

    # reach radius is the NAMED constant, never inline
    assert spec["reach_radius_m"] == REACH_RADIUS_M

    # 19 real stages carried through with one goal-weight each (demand-weighted slice)
    assert len(spec["stages_utm"]) == len(spec["goal_weights"]) == 19
    assert all(w > 0 for w in spec["goal_weights"])

    # two gate sources (A general, B VIP); their agent split honours SPAWN_FRAC_GATE_A for a known n
    assert len(spec["sources"]) == 2
    n = 1000
    spec_n = build_primitive_spec(lattice=lattice, n_agents=n)
    counts = [c for (_poly, c) in spec_n["sources"]]
    assert counts[0] == round(n * SPAWN_FRAC_GATE_A)
    assert sum(counts) == n

    # walkable polygon rings are coordinate lists (UTM metre tuples), not shapely objects
    assert isinstance(spec["boundary_rings"], list) and len(spec["boundary_rings"]) >= 1
    assert len(spec["boundary_rings"][0]) >= 3  # a ring has at least 3 vertices
    assert isinstance(spec["blocker_rings"], list)


def test_build_primitive_spec_imports_no_jupedsim():
    """build_primitive_spec is jupedsim-free — the mapping is unit-testable without the wheel."""
    from conftest_crowdsim import load_committed_utci

    from crowdsim.mapping import build_primitive_spec

    sys.modules.pop("jupedsim", None)
    build_primitive_spec(lattice=load_committed_utci()["lattice"])
    assert "jupedsim" not in sys.modules
