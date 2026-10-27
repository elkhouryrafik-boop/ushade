"""Orchestrator integration tests for ``run_crowd_stage`` (CROWD-01/04/06).

These run in the BASE (torch-free AND jupedsim-free) suite: a tiny synthetic ``sim_factory`` is
injected, so the cache-first, fail-safe, and provenance behaviours are proven WITHOUT torch / SB3 /
gymnasium / jupedsim (T-02b-14 / CROWD-06). The happy-path grid build uses the SAME injected fake,
so it too stays base-suite.

LIVE PATH (Phase 15, D-06): ``run_crowd_stage`` drives the JuPedSim CFSM engine
(``crowdsim.simulation._default_sim_factory``) by default; the injected ``sim_factory`` here is the
SAME seam, returning a synthetic ``(steps×agents×4)`` array in place of the real CFSM roll. The
legacy ``policy_path``/``env_factory`` kwargs are accepted-but-ignored on the live path (dormant
PPO, D-04) and are no longer exercised by these tests.

Four behaviours asserted (mirrors ``tests/test_climate.py`` integration style):

  * ``test_stage_builds_valid_grid``       — contract-valid crowd_grid; lattice == utci.lattice;
                                              N == capacity // AGENT_DIVISOR.
  * ``test_cache_hit_no_compute``          — a 2nd unchanged-input call does ZERO sim compute (the
                                              injected sim-build counter stays at 1) (T-02b-11).
  * ``test_failure_leaves_stage_not_done`` — an injected failing sim_factory raises, leaves the
                                              stage NOT done, writes NO crowd_grid.json (T-02b-12).
  * ``test_provenance_crowd_density_assumed`` — provenance.json crowd_density tier == ASSUMED, with
                                              a Fruin/Still source (never Weidmann/policy.zip),
                                              (T-02b-13 / CROWD-09).

karpathy: a tiny numpy synthetic trajectory, no SB3/torch/gymnasium/jupedsim anywhere in this file.
"""

from __future__ import annotations

import json

import pytest

# conftest_crowd is imported EXPLICITLY (not auto-loaded — pytest only auto-loads conftest.py).
from conftest_crowd import synthetic_trajectory
from crowd.constants import AGENT_DIVISOR, SIM_STEPS
from crowd.crowd import run_crowd_stage

_CAPACITY = 1900  # -> N = 1900 // 100 = 19 (matches synthetic_trajectory's 19-agent layout)


# --------------------------------------------------------------------------- #
# A tiny torch-free / jupedsim-free synthetic sim_factory: the SAME injection seam the live
# JuPedSim engine plugs into, returning a KNOWN (steps×agents×4) trajectory sliced to n_agents
# (so build_crowd_grid sees a real dwell cluster + flow groups on the utci lattice extent). The
# call-counter is the sim-compute proxy the cache-hit test asserts stays at 1.
# --------------------------------------------------------------------------- #
def _make_sim_factory(counter: list[int]):
    """Build a sim_factory that bumps ``counter`` on each call (the sim-compute proxy).

    Mirrors the JuPedSim engine's signature ``(*, lattice, utci_cells, n_agents, seed) ->
    (steps×agents×4) ndarray`` (``crowdsim.simulation._default_sim_factory``'s factory), returning a
    synthetic trajectory sliced to ``n_agents`` — so the base suite drives the live seam WITHOUT
    jupedsim installed.
    """

    def _factory(*, lattice=None, utci_cells=None, n_agents=1, seed=0):  # noqa: ARG001
        counter[0] += 1
        traj = synthetic_trajectory()  # (steps × 19 × 4) known-structure ground truth
        return traj[:, : int(n_agents), :]

    return _factory


class _FailingSimError(RuntimeError):
    """Distinct error type so the fail-safe test asserts the SAME exception propagates."""


def _failing_sim_factory(*, lattice=None, utci_cells=None, n_agents=1, seed=0):  # noqa: ARG001
    raise _FailingSimError("injected JuPedSim/sim failure")


def _seed_inputs(pdir, valid_utci_grid, capacity=_CAPACITY):
    """Write the parsed_brief.json + utci_grid.json the orchestrator reads."""
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "parsed_brief.json").write_text(
        json.dumps({"capacity": capacity}), encoding="utf-8"
    )
    (pdir / "utci_grid.json").write_text(json.dumps(valid_utci_grid), encoding="utf-8")


# --------------------------------------------------------------------------- #
# CROWD-01/04 — the stage builds a contract-valid, lattice-snapped grid
# --------------------------------------------------------------------------- #
def test_stage_builds_valid_grid(tmp_path, valid_utci_grid):
    """A run with the injected sim_factory emits a contract-valid crowd_grid; lattice == utci."""
    from validate.validate import validate

    pdir = tmp_path / "proj"
    _seed_inputs(pdir, valid_utci_grid)

    artifact = run_crowd_stage(
        "proj",
        projects_root=tmp_path,
        sim_factory=_make_sim_factory([0]),
    )

    # Contract-valid (validate raises on failure).
    validate(artifact, "crowd_grid")
    # XFN-04: the emitted lattice IS the utci_grid lattice (byte-equal authority).
    assert artifact["lattice"] == valid_utci_grid["lattice"]
    # The artifact is what was persisted (validate-then-write).
    written = json.loads((pdir / "crowd_grid.json").read_text(encoding="utf-8"))
    assert written["lattice"] == valid_utci_grid["lattice"]


def test_n_agents_is_capacity_over_divisor(tmp_path, valid_utci_grid):
    """N driven into the sim == capacity // AGENT_DIVISOR (PRD inference-only count)."""
    pdir = tmp_path / "proj"
    _seed_inputs(pdir, valid_utci_grid, capacity=_CAPACITY)

    seen = {}

    def _factory(*, lattice=None, utci_cells=None, n_agents=1, seed=0):  # noqa: ARG001
        seen["n"] = n_agents
        return synthetic_trajectory()[:, : int(n_agents), :]

    run_crowd_stage("proj", projects_root=tmp_path, sim_factory=_factory)
    assert seen["n"] == _CAPACITY // AGENT_DIVISOR


# --------------------------------------------------------------------------- #
# CROWD / T-02b-11 — cache hit: second call does ZERO sim compute
# --------------------------------------------------------------------------- #
def test_cache_hit_no_compute(tmp_path, valid_utci_grid):
    """A 2nd run on unchanged (capacity, lattice, seed) returns the artifact with ZERO compute.

    The static ``"injected"`` engine fingerprint (``_jupedsim_fingerprint`` when a sim_factory is
    injected) keeps the cache key stable across the two calls WITHOUT importing jupedsim — so the
    cache-hit-zero-compute proof holds under the new seam.
    """
    pdir = tmp_path / "proj"
    _seed_inputs(pdir, valid_utci_grid)

    counter = [0]
    factory = _make_sim_factory(counter)
    common = dict(projects_root=tmp_path, sim_factory=factory)

    first = run_crowd_stage("proj", **common)
    assert counter[0] == 1, "first run must call the sim exactly once"

    second = run_crowd_stage("proj", **common)  # cache hit — must NOT re-run the sim
    assert counter[0] == 1, "cache hit must do ZERO sim compute (sim-build counter stays at 1)"
    assert second == first, "cache hit returns the persisted artifact"


# --------------------------------------------------------------------------- #
# T-02b-12 — failure leaves the stage NOT done and writes NO partial artifact
# --------------------------------------------------------------------------- #
def test_failure_leaves_stage_not_done(tmp_path, valid_utci_grid):
    """An injected failing sim raises; stage NOT done; NO crowd_grid.json written (fail-safe)."""
    from manifest.manifest import DONE

    pdir = tmp_path / "proj"
    _seed_inputs(pdir, valid_utci_grid)

    with pytest.raises(_FailingSimError):
        run_crowd_stage(
            "proj",
            projects_root=tmp_path,
            sim_factory=_failing_sim_factory,
        )

    # No partial artifact on failure (T-02b-12).
    assert not (pdir / "crowd_grid.json").exists()

    # The manifest stage is recorded NOT done (mark_failed + write before re-raise).
    manifest = json.loads((pdir / "manifest.json").read_text(encoding="utf-8"))
    crowd_stage = next(s for s in manifest["stages"] if s["name"] == "crowd_grid")
    assert crowd_stage["status"] != DONE


# --------------------------------------------------------------------------- #
# T-02b-13 / CROWD-09 — provenance: crowd_density tier == ASSUMED, Fruin/Still source
# (CLAUDE.md non-negotiable; the JuPedSim path never promotes past ASSUMED — Pitfall 5.6)
# --------------------------------------------------------------------------- #
_FORBIDDEN_SOURCE_TOKENS = ("Weidmann", "policy.zip", "MODEL_CARD")


def test_provenance_crowd_density_assumed(tmp_path, valid_utci_grid):
    """provenance.json crowd_density tier == ASSUMED with a Fruin/Still source (no dead PPO tokens)."""
    pdir = tmp_path / "proj"
    _seed_inputs(pdir, valid_utci_grid)

    run_crowd_stage(
        "proj",
        projects_root=tmp_path,
        sim_factory=_make_sim_factory([0]),
    )

    provenance = json.loads((pdir / "provenance.json").read_text(encoding="utf-8"))
    entries = provenance["entries"]
    crowd_entries = [e for e in entries if e["key"] == "crowd_density"]
    assert crowd_entries, "provenance must record a crowd_density entry"
    assert all(e["tier"] == "ASSUMED" for e in crowd_entries), (
        "crowd_density MUST stay ASSUMED on the JuPedSim path — no FD benchmark validates the CFSM "
        "distribution (CLAUDE.md non-negotiable / CROWD-09)"
    )
    # CROWD-09 / Pitfall 5.6: the source is Fruin/Still-anchored, never the dead PPO concepts.
    for entry in crowd_entries:
        assert "Fruin" in entry["source"] or "Still" in entry["source"], (
            "crowd_density source must be Fruin/Still-anchored on the JuPedSim path (CROWD-09)"
        )
        for token in _FORBIDDEN_SOURCE_TOKENS:
            assert token not in entry["source"], (
                f"crowd_density source must not reference {token!r} on the JuPedSim path "
                "(the Weidmann/policy.zip/MODEL_CARD benchmark validated the RETIRED PPO, not the "
                "CFSM distribution — Pitfall 5.6)"
            )
    # The fixed sim seed is logged (determinism provenance).
    assert any(e["key"] == "sim_seed" for e in entries), "sim seed must be logged"


# --------------------------------------------------------------------------- #
# Provenance NEVER promotes on the live path: even across a cache hit the tier stays ASSUMED
# (the live JuPedSim path never calls the dormant _benchmark_is_green DERIVED gate — T-15-08).
# --------------------------------------------------------------------------- #
def test_provenance_assumed_persists_across_cache_hit(tmp_path, valid_utci_grid):
    """A 2nd (cache-hit) run re-emits provenance and crowd_density stays ASSUMED (never promoted)."""
    pdir = tmp_path / "proj"
    _seed_inputs(pdir, valid_utci_grid)

    common = dict(projects_root=tmp_path, sim_factory=_make_sim_factory([0]))
    run_crowd_stage("proj", **common)  # miss
    run_crowd_stage("proj", **common)  # hit — re-emits provenance

    provenance = json.loads((pdir / "provenance.json").read_text(encoding="utf-8"))
    crowd_entries = [e for e in provenance["entries"] if e["key"] == "crowd_density"]
    assert crowd_entries
    assert all(e["tier"] == "ASSUMED" for e in crowd_entries), (
        "the live JuPedSim path must never promote crowd_density past ASSUMED, even on a cache hit"
    )


# --------------------------------------------------------------------------- #
# Sanity: the named SIM_STEPS constant survives (guards an inlined magic-number regression in the
# dormant PPO rollout backstop; the live JuPedSim loop uses SIM_STEPS_JPS, asserted in its own suite).
# --------------------------------------------------------------------------- #
def test_sim_steps_is_named_constant():
    """SIM_STEPS is the PRD-exact 200-step backstop (guards against an inlined magic number)."""
    assert SIM_STEPS == 200
