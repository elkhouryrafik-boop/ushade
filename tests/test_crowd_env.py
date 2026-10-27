"""Phase 2b env + constants contract (CROWD-01) — the contracts-first wave.

Two test tiers, by import cost:

* ``test_constants_are_prd_exact`` runs in the BASE (torch-free) suite — it imports ONLY
  ``crowd.constants`` (pure ints/floats, no gymnasium/torch). This is the acceptance guard
  for the immutable PRD integers (T-02b-01): any inline-magic drift fails CI here.
* ``test_obs_action_spaces`` + ``test_reset_is_seeded_reproducible`` construct ``FestivalEnv``,
  which imports ``gymnasium`` (a ``crowd``-extra dep), so they are marked ``@pytest.mark.crowd``
  and the gymnasium-touching import is done INSIDE the test (never at module top-level) so
  the base ``-m "not crowd"`` suite still COLLECTS this module green without the extra.

These env tests are EXPECTED RED until the crowd extra is installed — that is correct and is
excluded from the base suite by ``-m "not crowd"``.
"""

from __future__ import annotations

import pytest

# constants.py is pure (no crowd extra) → safe to import at module top-level.
from crowd.constants import (
    AGENT_DIVISOR,
    BENCH_TOL,
    DWELL_MIN_STEPS,
    P_COLLISION,
    P_DEST,
    P_HEAT,
    SIM_STEPS,
)


def _tiny_lattice() -> dict:
    """A small master-lattice descriptor (the env derives its site bbox from this)."""
    return {
        "origin_x_m": 0.0,
        "origin_y_m": 0.0,
        "cell_size_m": 6.0,
        "cols": 10,
        "rows": 10,
    }


def test_constants_are_prd_exact():
    """The 5 PRD integers are exact and named (T-02b-01) — runs torch-free in the base suite.

    AGENT_DIVISOR=100, SIM_STEPS=200, DWELL_MIN_STEPS=10, reward +10/−5/−2. BENCH_TOL=0.20
    (ASSUMED) is asserted too so its documented value can't silently drift to "pass" a gate.
    """
    assert AGENT_DIVISOR == 100
    assert SIM_STEPS == 200
    assert DWELL_MIN_STEPS == 10
    assert P_DEST == 10
    assert P_HEAT == 5
    assert P_COLLISION == 2
    assert BENCH_TOL == 0.20
    # PRD integers must be ints, not accidentally floats/strings.
    assert all(
        isinstance(v, int) for v in (AGENT_DIVISOR, SIM_STEPS, DWELL_MIN_STEPS, P_DEST, P_HEAT, P_COLLISION)
    )


@pytest.mark.crowd
def test_obs_action_spaces():
    """obs is a 6-float Box, action a 2-float Box clipped to ±V_MAX (CROWD-01 env contract)."""
    from crowd.constants import V_MAX
    from crowd.env import ACT_DIM, OBS_DIM, FestivalEnv

    env = FestivalEnv(lattice=_tiny_lattice(), utci_cells=[], n_agents=4)
    assert env.observation_space.shape == (OBS_DIM,)
    assert env.action_space.shape == (ACT_DIM,)
    # action Box is symmetric ±V_MAX.
    assert float(env.action_space.high[0]) == pytest.approx(V_MAX)
    assert float(env.action_space.low[0]) == pytest.approx(-V_MAX)
    obs, info = env.reset(seed=SIM_STEPS)
    assert obs.shape == (OBS_DIM,)
    assert env.observation_space.contains(obs)


@pytest.mark.crowd
def test_reset_is_seeded_reproducible():
    """Two resets with the SAME seed produce an identical first observation (CROWD-01 determinism)."""
    import numpy as np

    from crowd.constants import SEED
    from crowd.env import FestivalEnv

    env_a = FestivalEnv(lattice=_tiny_lattice(), utci_cells=[], n_agents=8)
    env_b = FestivalEnv(lattice=_tiny_lattice(), utci_cells=[], n_agents=8)
    obs_a, _ = env_a.reset(seed=SEED)
    obs_b, _ = env_b.reset(seed=SEED)
    assert np.array_equal(obs_a, obs_b)
    # A different seed should (almost surely) differ — guards against a constant-obs bug.
    obs_c, _ = env_a.reset(seed=SEED + 1)
    assert not np.array_equal(obs_a, obs_c)


@pytest.mark.crowd
def test_heat_penalty_applied_from_utci_cells():
    """An agent on a UTCI>26 cell incurs −P_HEAT — the env reads the passed-in utci cells."""
    from crowd.env import FestivalEnv

    lattice = _tiny_lattice()
    # Mark every cell hot so any agent position triggers −P_HEAT regardless of spawn.
    hot_cells = [
        {"x_m": (c + 0.5) * 6.0, "y_m": (r + 0.5) * 6.0, "utci_c": 40.0}
        for c in range(lattice["cols"])
        for r in range(lattice["rows"])
    ]
    env = FestivalEnv(lattice=lattice, utci_cells=hot_cells, n_agents=3)
    env.reset(seed=SIM_STEPS)
    _, reward, _, _, _ = env.step([0.0, 0.0])
    # 3 agents, all on hot cells, none at a goal, none colliding at spawn jitter → reward ≤ −P_HEAT.
    assert reward <= -P_HEAT
