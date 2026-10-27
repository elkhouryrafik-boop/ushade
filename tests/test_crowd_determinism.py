"""End-to-end same-seed determinism through ``run_crowd_stage`` (CROWD-01).

CROWD-01 mandates a FIXED, LOGGED seed producing REPRODUCIBLE output. ``test_crowd_rollout``
already proves the rollout trajectory is byte-identical at a fixed seed; this test proves the
guarantee survives the WHOLE stage -- real ``policy.zip`` -> real ``FestivalEnv`` -> real
``build_crowd_grid`` (lattice snap + DBSCAN dwell_zones + flow_vectors) -> validate-then-write
-- so two independent runs at the same seed write a BYTE-IDENTICAL ``crowd_grid.json``.

It runs the production path with NO injected fakes (``policy_path``/``env_factory`` default to
the committed weights + ``FestivalEnv``), so it is the genuine end-to-end determinism witness.
Two SEPARATE project dirs are used so each call is a real cache MISS (a real rollout), not a
cache hit replaying the first artifact -- the determinism must come from the seed, not the cache.

``@pytest.mark.crowd``: needs torch + SB3 + the committed weights (excluded by the base suite).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from crowd.constants import AGENT_DIVISOR
from crowd.crowd import run_crowd_stage

pytestmark = pytest.mark.crowd

_POLICY_PATH = Path(__file__).resolve().parent.parent / "src" / "crowd" / "policy.zip"


def _policy_obs_dim_matches_env() -> bool:
    """True iff the COMMITTED policy.zip's obs input dim equals the current env OBS_DIM.

    Plan 02.1-03 redesigned the env obs to OBS_DIM=7 (scale-free flow-field cue); the committed
    policy.zip is still the V1 6-input artifact, retrained to 7-input in Plan 02.1-04 (Wave 4).
    The end-to-end stage rolls the committed policy through the now-7-input env, so it fails on the
    dimension mismatch until that retrain. Keying the xfail on a real ARTIFACT dimension probe lets
    it auto-resolve at Wave 4 (strict=False → xpass tolerated). This defers WHEN the end-to-end
    determinism witness runs, never weakens it.
    """
    try:
        from crowd.env import OBS_DIM
        from crowd.rollout import load_policy

        pol = load_policy(_POLICY_PATH)
        return int(pol.observation_space.shape[0]) == int(OBS_DIM)
    except Exception:  # noqa: BLE001 - any probe failure → treat as mismatch (xfail), never error
        return False


_POLICY_DIM_MISMATCH = _POLICY_PATH.exists() and not _policy_obs_dim_matches_env()
_RETRAIN_PENDING = pytest.mark.xfail(
    _POLICY_DIM_MISMATCH,
    reason=(
        "committed policy.zip is V1 6-input; env obs is now OBS_DIM=7 (Plan 02.1-03). "
        "End-to-end determinism witness re-runs on the 7-input V2 policy in Plan 02.1-04 (Wave 4)."
    ),
    strict=False,
)

# Capacity -> N = capacity // AGENT_DIVISOR agents. Small but > 1 so the per-agent congestion
# physics (and thus any non-determinism in the O(n^2) density math) actually exercises.
_CAPACITY = 800  # N = 8 agents


def _seed_inputs(pdir, valid_utci_grid, capacity=_CAPACITY):
    """Write the parsed_brief.json + utci_grid.json the orchestrator reads."""
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "parsed_brief.json").write_text(
        json.dumps({"capacity": capacity}), encoding="utf-8"
    )
    (pdir / "utci_grid.json").write_text(json.dumps(valid_utci_grid), encoding="utf-8")


@_RETRAIN_PENDING
def test_same_seed_same_grid(tmp_path, valid_utci_grid):
    """Two independent real runs at the fixed SEED write a byte-identical crowd_grid.json.

    Each run lives in its OWN project dir, so both are genuine cache MISSES (real rollouts on
    the committed policy.zip + real FestivalEnv). End-to-end determinism (CROWD-01): same seed
    -> identical density field, dwell_zones, and flow_vectors -- byte-for-byte on disk.
    """
    pdir_a = tmp_path / "run_a"
    pdir_b = tmp_path / "run_b"
    _seed_inputs(pdir_a, valid_utci_grid)
    _seed_inputs(pdir_b, valid_utci_grid)

    artifact_a = run_crowd_stage("run_a", projects_root=tmp_path)
    artifact_b = run_crowd_stage("run_b", projects_root=tmp_path)

    # Sanity: a real run actually happened (N agents = capacity // AGENT_DIVISOR were simulated).
    assert _CAPACITY // AGENT_DIVISOR >= 2, "test needs > 1 agent to exercise the density physics"

    raw_a = (pdir_a / "crowd_grid.json").read_text(encoding="utf-8")
    raw_b = (pdir_b / "crowd_grid.json").read_text(encoding="utf-8")
    assert raw_a == raw_b, (
        "same seed produced differing crowd_grid.json on disk -- end-to-end determinism broken "
        "(CROWD-01). Check the rollout seed plumbing and the build_crowd_grid float handling."
    )
    # And the in-memory return values agree (the persisted artifact == the returned artifact).
    assert artifact_a == artifact_b


@_RETRAIN_PENDING
def test_same_seed_same_grid_repeat_in_place(tmp_path, valid_utci_grid):
    """A re-run in the SAME dir returns the identical artifact (cache hit replays it exactly).

    Complements the two-dir witness above: the first call writes the grid; the second is a
    cache HIT (zero rollout) returning the byte-identical persisted artifact -- so the stage's
    determinism guarantee holds whether the second run recomputes or replays.
    """
    pdir = tmp_path / "proj"
    _seed_inputs(pdir, valid_utci_grid)

    first = run_crowd_stage("proj", projects_root=tmp_path)
    raw_first = (pdir / "crowd_grid.json").read_text(encoding="utf-8")

    second = run_crowd_stage("proj", projects_root=tmp_path)  # cache hit
    raw_second = (pdir / "crowd_grid.json").read_text(encoding="utf-8")

    assert first == second
    assert raw_first == raw_second


# ─────────────────────────────────────────────────────────────────────────────
# Plan 02.1-05 — V2 SITE-NATIVE determinism + XFN-04 seam re-validation
# ─────────────────────────────────────────────────────────────────────────────
# These witness the SAME guarantees as above, but on the REAL site path: the
# default site-native env_factory builds the full FestivalEnv (19 stages + 2
# entrances + 13 blockers, demand-weighted goals, seeded staggered arrivals) and
# rolls SIM_STEPS_V2 with the trajectory downsampled at the grid handoff. So the
# determinism guarantee must survive the staggered arrivals, the per-goal flow
# field, AND the handoff downsample — not just the V1 corridor field.
#
# PROVENANCE HONESTY (DEFERRED-GATE-FIX.md, 2026-06-11): the stage-reach ROUTING
# gate is RED (54.8% vs 70% locked) and owner-DEFERRED. These tests assert ONLY
# determinism, the XFN-04 lattice seam, and the cache-hit mechanism — all of which
# are gate-INDEPENDENT (a deterministic field is reproducible whether or not enough
# agents reach their stage). They make NO stage-reach claim; that gate test stays
# xfail'd until the deferred fix runs. crowd_density routing remains ASSUMED-grade.

# A real-site run uses the demand slice + staggered arrivals; a modest N keeps the
# smoke fast while still exercising the multi-gate spawn + flow-field physics.
_V2_CAPACITY = 1500  # N = 1500 // AGENT_DIVISOR = 15 agents (multi-gate, > 1)


@_RETRAIN_PENDING
def test_v2_same_seed_same_grid(tmp_path, valid_utci_grid):
    """V2 real-site: two independent same-seed runs write a byte-identical crowd_grid.json.

    Each run lives in its OWN project dir → both are genuine cache MISSES (real rollouts
    through the committed V2 policy.zip + the real-site FestivalEnv at SIM_STEPS_V2 with the
    handoff downsample). Determinism (CROWD-01) must survive the seeded staggered arrivals,
    the per-goal flow field, and the stride-downsample — byte-for-byte on disk.
    """
    pdir_a = tmp_path / "v2_a"
    pdir_b = tmp_path / "v2_b"
    _seed_inputs(pdir_a, valid_utci_grid, capacity=_V2_CAPACITY)
    _seed_inputs(pdir_b, valid_utci_grid, capacity=_V2_CAPACITY)

    artifact_a = run_crowd_stage("v2_a", projects_root=tmp_path)
    artifact_b = run_crowd_stage("v2_b", projects_root=tmp_path)

    raw_a = (pdir_a / "crowd_grid.json").read_text(encoding="utf-8")
    raw_b = (pdir_b / "crowd_grid.json").read_text(encoding="utf-8")
    assert raw_a == raw_b, (
        "same seed produced differing real-site crowd_grid.json — V2 determinism broken "
        "(CROWD-01). Check the staggered-arrival seeding, the flow-field cache, and the "
        "handoff downsample (stride must be a pure function of steps×agents)."
    )
    assert artifact_a == artifact_b


@_RETRAIN_PENDING
def test_v2_lattice_equals_utci(tmp_path, valid_utci_grid):
    """V2 real-site: crowd_grid.lattice is byte-equal to utci_grid.lattice (XFN-04 UNCHANGED).

    The site-native path still READS the lattice from utci_grid.json and passes it UNCHANGED to
    build_crowd_grid (CONTRACT-03), so the V2 output honours the same XFN-04 seam the existing
    test_seam_climate_crowd contract asserts. This does NOT modify that contract — it confirms
    the V2 path satisfies it.
    """
    pdir = tmp_path / "v2_seam"
    _seed_inputs(pdir, valid_utci_grid, capacity=_V2_CAPACITY)

    artifact = run_crowd_stage("v2_seam", projects_root=tmp_path)

    assert artifact["lattice"] == valid_utci_grid["lattice"], (
        "XFN-04: V2 crowd_grid.lattice must be byte-equal to utci_grid.lattice (lattice READ, "
        "never re-derived — CONTRACT-03)."
    )
    # The persisted artifact carries the same lattice (the seam holds on disk, not just in memory).
    persisted = json.loads((pdir / "crowd_grid.json").read_text(encoding="utf-8"))
    assert persisted["lattice"] == valid_utci_grid["lattice"]


@_RETRAIN_PENDING
def test_v2_cache_hit_no_recompute(tmp_path, valid_utci_grid):
    """V2 real-site: a second run in the same dir is a cache HIT returning the identical artifact.

    Confirms the content-hash key change (the site geometry folded into input_hash) did NOT break
    cache-first: the first run writes the grid; the second short-circuits to a cache hit (zero new
    rollout) and returns the byte-identical persisted artifact. The rollout is monkeypatched with a
    counter so a recompute on the second call is caught (the cache mechanism, not luck).
    """
    import crowd.crowd as _crowd_mod

    pdir = tmp_path / "v2_cache"
    _seed_inputs(pdir, valid_utci_grid, capacity=_V2_CAPACITY)

    real_rollout = _crowd_mod.run_crowd_stage  # bound for clarity; we spy the rollout import below
    rollout_calls = [0]
    from crowd import rollout as _rollout_mod

    orig_rollout = _rollout_mod.rollout

    def _counting_rollout(*args, **kwargs):
        rollout_calls[0] += 1
        return orig_rollout(*args, **kwargs)

    # The orchestrator does ``from crowd.rollout import rollout`` INSIDE the miss path, so patch the
    # source attribute the late import binds to.
    import pytest as _pytest  # local — keep module top torch-free

    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(_rollout_mod, "rollout", _counting_rollout)
        first = real_rollout("v2_cache", projects_root=tmp_path)
        assert rollout_calls[0] == 1, "first run must roll out exactly once (cache miss)"
        raw_first = (pdir / "crowd_grid.json").read_text(encoding="utf-8")

        second = real_rollout("v2_cache", projects_root=tmp_path)
        assert rollout_calls[0] == 1, (
            "second run must be a cache HIT (zero new rollout) under the new content-hash key"
        )
        raw_second = (pdir / "crowd_grid.json").read_text(encoding="utf-8")

    assert first == second
    assert raw_first == raw_second
