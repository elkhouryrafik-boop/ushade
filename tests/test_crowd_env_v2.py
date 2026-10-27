"""Phase 2.1 V2 env contract — OBS_DIM 6→7 scale-free obs + real-site path (CROWD-01/03/05).

This module is the acceptance guard for the V2 observation redesign (RESEARCH §Q1) and the
site-geometry path (gates/stages/blockers + flow field + seeded staggered arrivals).

Two test tiers, by import cost (mirrors ``test_crowd_env.py``):

* The V2 env tests construct ``FestivalEnv``, which imports ``gymnasium`` (a ``crowd``-extra
  dep), so the gymnasium-touching import is done INSIDE each test (never at module top-level)
  and the whole module is marked ``@pytest.mark.crowd`` — the base ``-m "not crowd"`` suite
  still COLLECTS this module green without the extra installed.
* Every test here is TORCH-FREE: env construction + ``observe_all`` + the reactive neighbour
  model only. NO SB3/PPO inference is needed (the impassability/arrival/degeneracy properties
  are env-physics, not learned behaviour) — so they all run in the ``crowd`` tier on CI without
  torch (gymnasium-only), exactly like the V1 ``test_obs_action_spaces``.

These env tests are EXPECTED RED until the crowd extra is installed — correct, and excluded
from the base suite by ``-m "not crowd"``.
"""

from __future__ import annotations

import numpy as np
import pytest

# These helpers are pure (numpy / shapely / constants) — safe at module top-level. The
# conftest_crowd module is imported EXPLICITLY (it is not auto-loaded) for the mini-site +
# flow-field ground truth, exactly like the grid/orchestrator tests.
from conftest_crowd import mini_site
from crowd.constants import (
    ARRIVAL_WINDOW_STEPS,
    OBS_RADIUS_M,
    SEED,
    SPAWN_FRAC_GATE_A,
    V_MAX,
)

pytestmark = pytest.mark.crowd


def _tiny_lattice() -> dict:
    """A small master-lattice descriptor (the env derives its site bbox from this)."""
    return {
        "origin_x_m": 0.0,
        "origin_y_m": 0.0,
        "cell_size_m": 6.0,
        "cols": 10,
        "rows": 10,
    }


def _real_scale_lattice() -> dict:
    """A real-scale lattice (~600 m across) so a far-corner agent is ~600 m from its goal.

    The point: under the V1 raw goal_dx/dy obs this produced a 600 m unbounded offset (the OOD
    root cause). The V2 obs must stay bounded at ANY position on this lattice.
    """
    return {
        "origin_x_m": 0.0,
        "origin_y_m": 0.0,
        "cell_size_m": 6.0,
        "cols": 139,
        "rows": 153,
    }


def _mini_site_geometry() -> dict:
    """Build a site_geometry dict from the hand-built mini_site (boundary + blocker + gates + stages).

    Uses the committed pure loader (``crowd.site.load_site_geometry``) on the mini geojson so the
    blocked cells / stages / entrances / weights are exactly what the real path consumes.
    """
    from crowd.site import load_site_geometry

    ms = mini_site()
    geo = load_site_geometry(
        festival_geo=ms["festival"],
        boundary_geo=ms["boundary"],
        nogo_geo=ms["nogo"],
        lattice=ms["lattice"],
    )
    geo["lattice"] = ms["lattice"]
    return geo


# ─────────────────────────────────────────────────────────────────────────────
# Task 1 — OBS_DIM 6→7 scale-free observation + periodic-mode degeneracy
# ─────────────────────────────────────────────────────────────────────────────
def test_obs_dim_is_seven():
    """OBS_DIM == 7; observation_space.shape == (7,); a reset obs is contained in the Box."""
    from crowd.env import OBS_DIM, FestivalEnv

    assert OBS_DIM == 7
    env = FestivalEnv(lattice=_tiny_lattice(), utci_cells=[], n_agents=4)
    assert env.observation_space.shape == (7,)
    obs, _ = env.reset(seed=SEED)
    assert obs.shape == (7,)
    assert env.observation_space.contains(obs)


def test_obs_bounded_anywhere():
    """At the far corner of the real-scale lattice (~600 m from goal) EVERY obs field is finite
    and inside the Box — the V1 unbounded-goal-offset OOD failure cannot recur (T-02.1-07)."""
    from crowd.env import FestivalEnv

    env = FestivalEnv(lattice=_real_scale_lattice(), utci_cells=[], n_agents=2)
    env.reset(seed=SEED)
    # Force one agent to the far corner — the maximally-OOD position under the V1 obs.
    env._pos[0] = np.array([env._x_max - 1.0, env._y_max - 1.0])
    obs = env._observe_agent(0)
    assert np.all(np.isfinite(obs)), obs
    assert env.observation_space.contains(obs.astype(np.float32)), obs
    # flow unit vector ∈ [-1, 1]; near_dx clipped to ±OBS_RADIUS_M (NOT `big`).
    assert -1.0 <= obs[2] <= 1.0 and -1.0 <= obs[3] <= 1.0
    assert abs(obs[6]) <= OBS_RADIUS_M + 1e-6
    # log_goal_dist is bounded and small (log-compressed), never the raw ~600 m offset.
    assert 0.0 <= obs[4] <= 20.0


def test_periodic_obs_degenerates_to_plus_x():
    """In periodic mode the obs flow field is (1,0) and log_goal_dist is the documented large
    constant — the FD harness sees the SAME constant forward cue the V1 obs used (Q4, T-02.1-10)."""
    from crowd.env import _PERIODIC_LOG_GOAL_DIST, FestivalEnv

    lattice = {
        "origin_x_m": 0.0, "origin_y_m": 0.0,
        "cell_size_m": 1.0, "cols": 16, "rows": 4,
    }
    env = FestivalEnv(
        lattice=lattice, utci_cells=[], n_agents=8,
        uniform_spawn=True, periodic=True,
    )
    env.reset(seed=SEED)
    for i in range(env._n_agents):
        obs = env._observe_agent(i)
        assert obs[2] == pytest.approx(1.0)   # flow_dx
        assert obs[3] == pytest.approx(0.0)   # flow_dy
        assert obs[4] == pytest.approx(_PERIODIC_LOG_GOAL_DIST)  # the documented constant


def test_v1_corridor_env_still_constructs():
    """make_corridor_env / make_env build and observe_all() returns shape (n,7) without error —
    the FD harness keeps running on the new obs (no contamination)."""
    from crowd.train import make_corridor_env, make_env

    for factory in (lambda: make_corridor_env(n_agents=12, seed=SEED), lambda: make_env(seed=SEED)):
        env = factory()
        env.reset(seed=SEED)
        all_obs = env.observe_all()
        assert all_obs.shape == (env._n_agents, 7)
        assert np.all(np.isfinite(all_obs))


# ─────────────────────────────────────────────────────────────────────────────
# Task 2 — Site-geometry path + seeded staggered arrivals
# ─────────────────────────────────────────────────────────────────────────────
def test_no_agent_in_blocked_cell():
    """Over a short reactive rollout on a mini real-geometry env, NO agent is EVER inside a
    blocked cell at any step (property test — PRD impassability honoured every step, T-02.1-09)."""
    from crowd.env import FestivalEnv

    geo = _mini_site_geometry()
    assert geo["blocked_cells"], "mini-site must have blocked cells to make this test meaningful"
    env = FestivalEnv(
        lattice=geo["lattice"], utci_cells=[], n_agents=30,
        site_geometry=geo,
    )
    env.reset(seed=SEED)

    def _in_blocked() -> bool:
        cols = ((env._pos[:, 0] - env._origin[0]) // env._cell_size_m).astype(int)
        rows = ((env._pos[:, 1] - env._origin[1]) // env._cell_size_m).astype(int)
        return any((int(c), int(r)) in env._blocked for c, r in zip(cols, rows))

    assert not _in_blocked(), "an agent spawned inside a blocked cell"
    for _ in range(60):
        env.step_reactive()
        assert not _in_blocked(), "an agent entered a blocked cell during the rollout"


def test_staggered_arrival_deterministic():
    """Two resets at the same seed produce identical per-agent activate_step arrays; before
    activation an agent sits at its gate with zero velocity and is excluded from density."""
    from crowd.env import FestivalEnv

    geo = _mini_site_geometry()
    env_a = FestivalEnv(lattice=geo["lattice"], utci_cells=[], n_agents=40, site_geometry=geo)
    env_b = FestivalEnv(lattice=geo["lattice"], utci_cells=[], n_agents=40, site_geometry=geo)
    env_a.reset(seed=SEED)
    env_b.reset(seed=SEED)
    assert np.array_equal(env_a._activate_step, env_b._activate_step)
    assert env_a._activate_step.min() >= 0
    assert env_a._activate_step.max() < ARRIVAL_WINDOW_STEPS

    # A pre-arrival agent (activate_step > 0) sits at its gate with zero velocity at t=0.
    pre = np.flatnonzero(env_a._activate_step > 0)
    assert pre.size > 0, "with a 300-step window over 40 agents some must be pre-arrival"
    assert np.allclose(env_a._vel[pre], 0.0)
    # Pre-arrival agents are excluded from the local-density count (parked, not in the crowd).
    # An agent whose only neighbours are all still-inactive sees density 0.
    inactive_all = env_a._active.copy()
    assert inactive_all.dtype == bool
    assert not env_a._active[pre].any()  # the pre-arrival agents are inactive at t=0


def test_weighted_spawn_and_goal_seeded():
    """Gate split ~85/15 (A/B) + demand-weighted goal assignment are drawn from the seeded
    self.np_random → byte-identical given the seed (T-02.1-08)."""
    from crowd.env import FestivalEnv

    geo = _mini_site_geometry()
    env_a = FestivalEnv(lattice=geo["lattice"], utci_cells=[], n_agents=200, site_geometry=geo)
    env_b = FestivalEnv(lattice=geo["lattice"], utci_cells=[], n_agents=200, site_geometry=geo)
    env_a.reset(seed=SEED)
    env_b.reset(seed=SEED)
    # Byte-identical spawn positions and goal assignment for the same seed.
    assert np.array_equal(env_a._pos, env_b._pos)
    assert np.array_equal(env_a._goal_idx, env_b._goal_idx)
    # Gate split: which entrance each agent is nearest to ≈ 85/15 (loose band — jittered).
    ent = np.asarray(geo["entrances_utm"], dtype=np.float64)
    d_a = np.linalg.norm(env_a._pos - ent[0], axis=1)
    d_b = np.linalg.norm(env_a._pos - ent[1], axis=1)
    frac_a = float((d_a < d_b).mean())
    assert SPAWN_FRAC_GATE_A - 0.12 <= frac_a <= SPAWN_FRAC_GATE_A + 0.12, frac_a


def test_flow_field_cache_built_once():
    """The env builds the per-goal flow fields at reset (cache populated for the assigned goals);
    a second reset reuses/rebuilds deterministically (same keys, same arrays)."""
    from crowd.env import FestivalEnv

    geo = _mini_site_geometry()
    env = FestivalEnv(lattice=geo["lattice"], utci_cells=[], n_agents=20, site_geometry=geo)
    env.reset(seed=SEED)
    assert env._flow_fields is not None
    assert len(env._flow_fields) == len(geo["stages_utm"])  # one field per stage goal
    # The cache is keyed by goal index; each entry is (dist[cols,rows], flow[cols,rows,2]).
    g0 = next(iter(env._flow_fields))
    dist, flow = env._flow_fields[g0]
    assert dist.shape == (env._cols, env._rows)
    assert flow.shape == (env._cols, env._rows, 2)
    # Rebuild on a second reset is deterministic (identical arrays).
    first = {k: (d.copy(), f.copy()) for k, (d, f) in env._flow_fields.items()}
    env.reset(seed=SEED)
    for k, (d, f) in first.items():
        assert np.array_equal(d, env._flow_fields[k][0])
        assert np.array_equal(f, env._flow_fields[k][1])


def test_v1_synthetic_path_unaffected_no_site_geometry():
    """Without site_geometry the env keeps the V1 synthetic behaviour (no blocked set, no flow
    cache, no staggered arrivals) — additive guarantee for the corridor/benchmark harness."""
    from crowd.env import FestivalEnv

    env = FestivalEnv(lattice=_tiny_lattice(), utci_cells=[], n_agents=6)
    env.reset(seed=SEED)
    assert env._flow_fields is None
    assert not env._blocked  # empty set / falsy
    # All agents active immediately (V1 had no staggered arrivals).
    assert env._active.all()
    assert env.snapshot().shape == (env._n_agents, 4)
