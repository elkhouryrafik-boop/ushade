"""Site-native runtime path for ``run_crowd_stage`` (Plan 02.1-05, CROWD-01/04).

Plan 02.1-05 wires the trusted V2 policy into the runtime pipeline: ``rollout`` runs
``SIM_STEPS_V2`` on the REAL site, ``run_crowd_stage`` reads the real site geometry
(gates/stages/blockers) with the geojson CONTENT-HASH folded into the manifest cache key,
and the trajectory is downsampled at the EMIT/grid-handoff seam ONLY (``grid.py`` stays
FROZEN) to bound DBSCAN memory at 650 agents × 1400 steps.

Two tiers:

* BASE (torch-free, ``-m "not crowd"``): the SIM_STEPS_V2 rollout horizon, the
  content-hash-in-key cache-miss behaviour, and the downsample-at-handoff property are all
  proven with an INJECTED fake policy + a tiny replay env + static grep guards — NO
  torch/SB3/gymnasium. These are the authoritative structural witnesses (T-02.1-15/16/18).
* CROWD (``-m crowd``): one full-scale real-site smoke (committed ``policy.zip`` + real
  ``FestivalEnv``) confirming a contract-valid crowd_grid whose lattice is byte-equal to the
  utci_grid lattice.

PROVENANCE HONESTY (DEFERRED-GATE-FIX.md, 2026-06-11): the stage-reach routing gate is RED
(54.8% vs 70% locked) and owner-DEFERRED. The benchmark-artifact DERIVED promotion keys ONLY
on the GREEN Weidmann FD gate (LOCAL physics calibration), NOT on routing — so a DERIVED
crowd_density here certifies the speed-density CAP only; ROUTING stays ASSUMED-grade for
spatial allocation. These tests never assert a green stage-reach gate (that test stays xfail'd).

karpathy: a tiny numpy replay env + grep guards in the base suite; one real smoke under -m crowd.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

# conftest_crowd is imported EXPLICITLY (pytest only auto-loads conftest.py).
from conftest_crowd import fake_policy, synthetic_trajectory
from crowd.constants import (
    AGENT_DIVISOR,
    GRID_STILLPOINT_BUDGET,
    SIM_STEPS,
    SIM_STEPS_V2,
)

_SRC_CROWD = Path(__file__).resolve().parent.parent / "src" / "crowd"
_GRID_PY = _SRC_CROWD / "grid.py"

_CAPACITY = 1900  # -> N = 1900 // 100 = 19 (matches synthetic_trajectory's 19-agent layout)


# --------------------------------------------------------------------------- #
# A tiny torch-free / gymnasium-free replay env exposing exactly the rollout call
# surface (reset / observe_all / step_all / snapshot). It records how many steps the
# rollout drove it (so we can witness the SIM_STEPS_V2 horizon) and replays a known
# synthetic trajectory frame-by-frame (so build_crowd_grid sees a real field).
# --------------------------------------------------------------------------- #
class _ReplayEnv:
    """Replays a fixed trajectory; counts rollout steps + constructions."""

    def __init__(self, *, lattice, utci_cells=None, n_agents=1, seed=0, traj=None):
        self.lattice = lattice
        self.n_agents = int(n_agents)
        base = synthetic_trajectory() if traj is None else traj
        self._traj = base[:, : self.n_agents, :]
        self._t = 0
        self.step_calls = 0

    def reset(self, seed=None):  # noqa: ARG002 - mirrors gymnasium signature
        self._t = 0
        self.step_calls = 0
        return self.observe_all(), {}

    def observe_all(self):
        return np.zeros((self.n_agents, 7), dtype=np.float32)  # OBS_DIM=7 (V2)

    def step_all(self, actions):  # noqa: ARG002 - actions ignored (replay)
        self.step_calls += 1
        self._t = min(self._t + 1, self._traj.shape[0] - 1)

    def snapshot(self):
        return self._traj[self._t]


def _seed_inputs(pdir, valid_utci_grid, capacity=_CAPACITY):
    """Write the parsed_brief.json + utci_grid.json the orchestrator reads."""
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "parsed_brief.json").write_text(
        json.dumps({"capacity": capacity}), encoding="utf-8"
    )
    (pdir / "utci_grid.json").write_text(json.dumps(valid_utci_grid), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# rollout.py — SIM_STEPS_V2 runtime horizon (V1 SIM_STEPS=200 retained)
# ─────────────────────────────────────────────────────────────────────────────
def test_runtime_rollout_uses_sim_steps_v2():
    """``rollout(..., steps=SIM_STEPS_V2)`` returns SIM_STEPS_V2 leading frames; the default
    (no steps) stays SIM_STEPS=200 (V1 back-compat — the corridor harness is untouched)."""
    from crowd.rollout import rollout

    lattice = {"origin_x_m": 0.0, "origin_y_m": 0.0, "cell_size_m": 6.0, "cols": 20, "rows": 20}
    # A long-enough synthetic trajectory so the env can replay SIM_STEPS_V2 distinct frames.
    long_traj = synthetic_trajectory(steps=SIM_STEPS_V2)

    env_v2 = _ReplayEnv(lattice=lattice, n_agents=5, traj=long_traj)
    traj_v2 = rollout(fake_policy(), env_v2, 5, steps=SIM_STEPS_V2)
    assert traj_v2.shape[0] == SIM_STEPS_V2, "runtime rollout must run exactly SIM_STEPS_V2 frames"
    assert env_v2.step_calls == SIM_STEPS_V2

    env_v1 = _ReplayEnv(lattice=lattice, n_agents=5, traj=long_traj)
    traj_v1 = rollout(fake_policy(), env_v1, 5)  # no steps -> V1 default
    assert traj_v1.shape[0] == SIM_STEPS, "default rollout must stay SIM_STEPS=200 (V1 back-compat)"
    assert env_v1.step_calls == SIM_STEPS


# ─────────────────────────────────────────────────────────────────────────────
# crowd.py — the site-geometry CONTENT-HASH folds into the manifest cache key
# ─────────────────────────────────────────────────────────────────────────────
def test_site_geometry_in_cache_key(tmp_path, valid_utci_grid, monkeypatch):
    """run_crowd_stage folds the site-geometry content-hash into ``input_hash`` — mutating a
    site file (its content-hash) is a cache MISS (re-sim), never a stale-grid hit (T-02.1-15).

    Phase 15 (D-06): driven through the LIVE ``sim_factory`` seam (the JuPedSim engine's signature),
    not the dormant ``env_factory``. The ``_site_content_hash`` term in the cache key is UNCHANGED by
    the swap, so the site-invalidates-cache property holds exactly as before — only the injection
    seam moves from the PPO rollout to the JuPedSim sim.
    """
    import crowd.crowd as _crowd_mod

    pdir = tmp_path / "proj"
    _seed_inputs(pdir, valid_utci_grid)

    # The orchestrator must expose the site-geometry content-hash helper folded into the cache key.
    assert hasattr(_crowd_mod, "_site_content_hash"), (
        "orchestrator must expose a site-geometry content-hash helper folded into the cache key"
    )

    counter = [0]

    def _sim_factory(*, lattice=None, utci_cells=None, n_agents=1, seed=0):  # noqa: ARG001
        counter[0] += 1
        return synthetic_trajectory()[:, : int(n_agents), :]  # (steps×agents×4) the engine returns

    common = dict(projects_root=tmp_path, sim_factory=_sim_factory)

    # First run: a genuine miss (one sim). Fix the site hash to a known value.
    monkeypatch.setattr(_crowd_mod, "_site_content_hash", lambda _lat: "SITE_HASH_A")
    run_crowd_stage = _crowd_mod.run_crowd_stage
    run_crowd_stage("proj", **common)
    assert counter[0] == 1, "first run must run the sim exactly once"

    # Same site hash -> cache HIT (zero new sim).
    run_crowd_stage("proj", **common)
    assert counter[0] == 1, "unchanged site hash must be a cache hit (zero sim)"

    # A CHANGED site hash (a corrected layout) -> cache MISS (re-sim), never a stale grid.
    monkeypatch.setattr(_crowd_mod, "_site_content_hash", lambda _lat: "SITE_HASH_B")
    run_crowd_stage("proj", **common)
    assert counter[0] == 2, "a changed site-geometry content-hash MUST be a cache miss (T-02.1-15)"


# ─────────────────────────────────────────────────────────────────────────────
# crowd.py — downsample at the grid HANDOFF only (grid.py FROZEN)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.crowd  # memory-heavy (real-scale DBSCAN input) — crowd tier, like the docs say
def test_downsample_at_handoff_only(tmp_path, valid_utci_grid, monkeypatch):
    """When est still-points (SIM_STEPS_V2 × N) exceed GRID_STILLPOINT_BUDGET, the grid INPUT is
    stride-downsampled with the TERMINAL frame anchored; grid.py is NEVER edited — build_crowd_grid
    still receives a (steps×agents×4) array (T-02.1-16/18).

    The runtime horizon is SIM_STEPS_V2 (1400); the trigger is N large enough that 1400×N > budget
    (the real run is N=650 → 910k still-points). We pick N so the budget is genuinely blown, drive
    a SIM_STEPS_V2-length replay trajectory, and assert the handoff downsamples that rollout output
    (not grid.py) with the rollout's FINAL frame anchored."""
    import crowd.crowd as _crowd_mod

    # N chosen so SIM_STEPS_V2 × N comfortably exceeds the budget (mirrors the real N=650 case).
    n_agents = (GRID_STILLPOINT_BUDGET // SIM_STEPS_V2) + 200  # > budget at the SIM_STEPS_V2 horizon
    capacity = n_agents * AGENT_DIVISOR
    pdir = tmp_path / "proj"
    _seed_inputs(pdir, valid_utci_grid, capacity=capacity)

    # A SIM_STEPS_V2-length, n_agents-wide MOVING trajectory (no dwell cluster — this test isolates
    # the downsample SHAPE/anchor behaviour, not the dwell DBSCAN). Each agent walks a short, unique
    # line inside the tiny lattice extent so build_crowd_grid runs cheaply on the downsampled input.
    rng = np.random.default_rng(0)
    starts = rng.uniform(5.0, 25.0, size=(n_agents, 2))
    ends = rng.uniform(80.0, 110.0, size=(n_agents, 2))
    wide = np.zeros((SIM_STEPS_V2, n_agents, 4), dtype=np.float64)
    for t in range(SIM_STEPS_V2):
        frac = t / max(1, SIM_STEPS_V2 - 1)
        wide[t, :, 0:2] = (1.0 - frac) * starts + frac * ends
        wide[t, :, 2:4] = (ends - starts) / max(1, SIM_STEPS_V2 - 1)  # moving: |v| > V_STILL
    # Give the terminal frame a unique signature so the anchor assertion is unambiguous.
    wide[-1, :, 0] += 777.0

    captured = {}
    real_build = _crowd_mod.build_crowd_grid

    def _spy_build(trajectory, lattice):
        arr = np.asarray(trajectory)
        captured["shape"] = arr.shape
        captured["terminal"] = arr[-1].copy()
        return real_build(trajectory, lattice)

    monkeypatch.setattr(_crowd_mod, "build_crowd_grid", _spy_build)

    def _wide_factory(*, lattice, utci_cells=None, n_agents=1, seed=0):
        return _ReplayEnv(
            lattice=lattice, utci_cells=utci_cells, n_agents=n_agents, seed=seed, traj=wide
        )

    _crowd_mod.run_crowd_stage(
        "proj",
        projects_root=tmp_path,
        policy_path=fake_policy(),
        env_factory=_wide_factory,
    )

    assert "shape" in captured, "build_crowd_grid must have been called"
    ds_steps, ds_agents, ds_fields = captured["shape"]
    # Downsampled: fewer rows than the SIM_STEPS_V2 rollout, still a (steps×agents×4) array.
    assert ds_agents == n_agents and ds_fields == 4
    assert ds_steps < SIM_STEPS_V2, "the grid input MUST be downsampled below the SIM_STEPS_V2 rollout"
    assert ds_steps * ds_agents <= GRID_STILLPOINT_BUDGET, (
        "the downsampled still-point count must be within GRID_STILLPOINT_BUDGET (DBSCAN memory bound)"
    )
    # Terminal frame anchored: the last downsampled row equals the rollout's last frame.
    assert np.array_equal(captured["terminal"], wide[SIM_STEPS_V2 - 1]), (
        "the terminal frame must be ANCHORED so density snaps to the final positions"
    )


def test_grid_py_is_frozen():
    """Static guard: grid.py imports none of the ML backends and carries no SIM_STEPS_V2 token —
    the downsample is an ORCHESTRATOR concern at the handoff, never a transform edit (T-02.1-16)."""
    text = _GRID_PY.read_text(encoding="utf-8")
    for forbidden in ("torch", "stable_baselines3", "gymnasium"):
        assert forbidden not in text, f"grid.py must stay torch-free (found {forbidden!r})"
    assert "SIM_STEPS_V2" not in text, "grid.py is horizon-agnostic — no SIM_STEPS_V2 token"
    assert "build_crowd_grid" in text, "grid.py must still define the frozen transform"


# ─────────────────────────────────────────────────────────────────────────────
# CROWD-marked: full real-site smoke (committed policy.zip + real FestivalEnv)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.crowd
def test_real_site_rollout_smoke(tmp_path, valid_utci_grid):
    """A small-capacity real-site run produces a contract-valid crowd_grid with
    cells/dwell_zones/flow_vectors and lattice byte-equal to the utci_grid lattice.

    Uses the REAL committed lattice + geojson (via the default site-native env factory) so the
    runtime path is exercised end-to-end. DERIVED-vs-ASSUMED is the orchestrator's concern; this
    smoke only asserts the contract + the XFN-04 seam hold on the V2 path.
    """
    from validate.validate import validate

    # The real-site path reads the committed utci_grid + geojson; the project's utci_grid is the
    # real lattice authority. Seed a project dir pointing at the committed real utci_grid.
    real_utci = json.loads(
        (Path(__file__).resolve().parent.parent / "projects" / "primavera-demo" / "utci_grid.json")
        .read_text(encoding="utf-8")
    )
    pdir = tmp_path / "proj"
    pdir.mkdir(parents=True, exist_ok=True)
    # Small capacity -> few agents so the smoke is fast but > 1 (exercise density physics).
    (pdir / "parsed_brief.json").write_text(json.dumps({"capacity": 300}), encoding="utf-8")
    (pdir / "utci_grid.json").write_text(json.dumps(real_utci), encoding="utf-8")

    artifact = run_crowd_stage("proj", projects_root=tmp_path)

    validate(artifact, "crowd_grid")
    assert artifact["lattice"] == real_utci["lattice"], "XFN-04: crowd lattice == utci lattice"
    assert "cells" in artifact and "dwell_zones" in artifact and "flow_vectors" in artifact


# run_crowd_stage is imported at call sites above via the module to keep monkeypatch live;
# also bind the bare name for the smoke test.
from crowd.crowd import run_crowd_stage  # noqa: E402
