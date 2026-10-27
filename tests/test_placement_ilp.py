"""Phase 13 Nyquist coverage for the exact ILP-MCLP engine (was DESIGNED-RED scaffold).

Every PLACE-05 / PLACE-06 / AMEND-01 behavior got a NAMED, automated test BEFORE the engine
existed (Nyquist compliance — feedback latency < 30 s, implementation test-driven). The scaffold
landed RED in Plan 02; Plan 03 turned the six solver behaviors green; Plan 04 wired
``run_placement_stage(engine="ilp")`` and turned the remaining stage-path behaviors green. ALL
markers are now dropped — the whole file runs in the green base suite
(``-m "not crowd and not geom"``).

Imports of the solver symbols live INSIDE the test bodies (NOT at module top) so COLLECTION
succeeds independently of the lazy scipy import discipline (D-02) — the tests exercise behavior,
never a collection-time import side effect.

Behavior map (CONTEXT D-01..D-15; RESEARCH test map):

  * AMEND-01  test_vocab_firewall      "optimal" lives ONLY in optimality_certificate.json on the
                                       ILP path; absent from structure_zones[.meta].json + provenance
  * PLACE-05  test_solves_optimal      certificate status==0, mip_gap==0, proven_optimal is True
  *           test_determinism         two solves of a TIED-optima instance => byte-identical selection
  *           test_cross_check         ilp covered >= greedy; strictly greater on a trap instance
  *           test_cross_check_raises  a broken/under-covering model trips the fail-loud ilp>=greedy guard
  *           test_ceiling_raises      n_demand x n_cand > ILP_MAX_CONSTRAINT_CELLS RAISES (never subsamples)
  *           test_stage_engine        engine folded into the cache key => greedy-then-ilp is a MISS
  *           test_lazy_import         import core.placement_stage pulls NO scipy at module load (D-02)
  * PLACE-06  test_certificate_fields  the PLACE-06 certificate field set + proven_optimal == (mip_gap==0)

Site-generality (D-15): the determinism / cross-check / ceiling contracts are proven on the SMALL
synthetic ``synthetic_tied_lattice`` fixture (NON-Forum 6x6), valid for ANY lattice size.

Runs in the BASE tier (``-m "not crowd and not geom"``) — scipy is a base dependency (Plan 02 Task 1).
"""

from __future__ import annotations

import json
import sys

import pytest

# conftest_core is imported EXPLICITLY (pytest only auto-loads conftest.py).
from conftest import _ILP_TRAP_RADIUS_M  # the trap-radius the greedy-trap instance needs
from conftest_core import _seed_inputs, tiny_score_inputs  # noqa: F401

from core.coverage_models import RadiusCoverage
from core.placement import build_demand, dense_candidate_grid, greedy_mclp

# Plan 03 turned the six solver tests GREEN (solves_optimal, determinism, cross_check,
# cross_check_raises, ceiling_raises, certificate_fields). Plan 04 wired engine="ilp" into
# run_placement_stage, turning the remaining stage-path tests GREEN and dropping their red markers:
# test_vocab_firewall, test_ceiling_raises_stage, test_stage_engine, test_lazy_import. The whole
# file now runs in the green base suite (-m "not crowd and not geom"); no red markers remain.

# Coverage radius sized to the synthetic clusters (10 m cells; a 6 m disc covers a cell's own
# centre only, so a per-cell structure shades its own demand cell — keeps the instances
# hand-computable). The ILP and greedy MUST share this SAME model instance (D-10 like-for-like).
_RADIUS_M = 6.0


def _covered_demand_float(result: dict) -> float:
    """The real float covered_demand from an engine result dict (integerization is solver-internal)."""
    return result["covered_demand"]


def _selection_xy(result: dict) -> list[tuple[float, float]]:
    """The selected structure centres in selection order — the byte-stable determinism witness."""
    return [(z["center"]["x_m"], z["center"]["y_m"]) for z in result["structures"]]


# ── AMEND-01: the positive vocab firewall (certificate is the SOLE legal "optimal" site) ──
def test_vocab_firewall(tmp_path, tiny_score_inputs):
    """On the ILP path, "optimal" appears in optimality_certificate.json ONLY — absent from
    structure_zones.json, structure_zones_meta.json, provenance.json (D-04). The earned claim
    EXISTS (falsifiability) but the firewall holds on the pipeline artifacts."""
    from core.placement_stage import run_placement_stage

    pdir = tmp_path / "proj"
    _seed_inputs(
        pdir,
        utci=tiny_score_inputs["utci"],
        crowd=tiny_score_inputs["crowd"],
        budget=tiny_score_inputs["budget"],
    )
    run_placement_stage("proj", projects_root=tmp_path, k=5, engine="ilp")

    cert = (pdir / "optimality_certificate.json").read_text(encoding="utf-8").lower()
    assert "optimal" in cert  # the earned claim exists (falsifiable)
    for name in ("structure_zones.json", "structure_zones_meta.json", "provenance.json"):
        text = (pdir / name).read_text(encoding="utf-8").lower()
        assert "optimal" not in text, f"{name} must stay optimal-token-free on the ILP path"


# ── PLACE-05: the solver proves optimality ──
def test_solves_optimal(synthetic_tied_lattice):
    """solve_mclp_exact returns a certificate proving optimality (status==0, mip_gap==0)."""
    from placement_ilp.mclp import solve_mclp_exact

    inst = synthetic_tied_lattice["tied"]
    sites = dense_candidate_grid(inst["utci"]["lattice"])
    _result, certificate = solve_mclp_exact(
        inst["utci"], inst["crowd"], sites, RadiusCoverage(_RADIUS_M), k=2
    )
    assert certificate["status"] == 0
    assert certificate["mip_gap"] == 0
    assert certificate["proven_optimal"] is True


# ── PLACE-05 / D-12: byte-identical determinism on a TIED-optima instance ──
def test_determinism(synthetic_tied_lattice):
    """Two solves of the SAME tied-optima instance yield byte-identical selected candidates —
    the scale-separated lexicographic (row,col,index) tiebreak, not an epsilon-nudge (D-12)."""
    from placement_ilp.mclp import solve_mclp_exact

    inst = synthetic_tied_lattice["tied"]
    sites = dense_candidate_grid(inst["utci"]["lattice"])
    a, _ = solve_mclp_exact(inst["utci"], inst["crowd"], sites, RadiusCoverage(_RADIUS_M), k=1)
    b, _ = solve_mclp_exact(inst["utci"], inst["crowd"], sites, RadiusCoverage(_RADIUS_M), k=1)
    assert _selection_xy(a) == _selection_xy(b)


# ── PLACE-05 / D-10: the greedy lower-bound cross-check ──
def test_cross_check(synthetic_tied_lattice):
    """ilp covered_demand >= greedy covered_demand on the shared instance; STRICTLY greater on
    the designed trap instance (proves the ILP does real work, not echoing the greedy)."""
    from placement_ilp.mclp import solve_mclp_exact

    model = RadiusCoverage(_RADIUS_M)

    tied = synthetic_tied_lattice["tied"]
    tsites = dense_candidate_grid(tied["utci"]["lattice"])
    ilp_t, _ = solve_mclp_exact(tied["utci"], tied["crowd"], tsites, model, k=2)
    greedy_t = greedy_mclp(tied["utci"], tied["crowd"], tsites, model, k=2)
    assert _covered_demand_float(ilp_t) >= _covered_demand_float(greedy_t)

    # The trap only bites under a NEIGHBOURHOOD coverage model (overlapping discs). A 6 m disc on
    # the 10 m lattice reaches only the own cell => max-coverage = "pick top-k cells" => greedy is
    # already optimal => no trap. Use the trap-radius the fixture engineered the line for.
    trap_model = RadiusCoverage(_ILP_TRAP_RADIUS_M)
    trap = synthetic_tied_lattice["trap"]
    psites = dense_candidate_grid(trap["utci"]["lattice"])
    ilp_p, _ = solve_mclp_exact(trap["utci"], trap["crowd"], psites, trap_model, k=2)
    greedy_p = greedy_mclp(trap["utci"], trap["crowd"], psites, trap_model, k=2)
    assert _covered_demand_float(ilp_p) > _covered_demand_float(greedy_p)


# ── PLACE-05 / D-10: the cross-check is fail-loud ──
def test_cross_check_raises(synthetic_tied_lattice):
    """A coverage model that under-covers FOR THE ILP drives its covered_demand below the greedy
    lower bound — the in-path ilp>=greedy guard must RAISE, never silently return.

    The cross-check shares ONE coverage model between the ILP matrix-build and the greedy witness,
    so a model that covers nothing for BOTH yields ilp==greedy==0 (no violation). To exercise the
    fail-loud path we inject a STATEFUL broken model that under-covers on the ILP's matrix-build
    calls (the first ``n_cand`` ``covered_keys`` calls, which build the constraint matrix) but
    returns real coverage afterwards — i.e. for the greedy cross-check witness. The ILP then
    covers strictly less than the greedy lower bound, tripping the guard (the realistic shape of a
    broken MILP: the SOLVE under-covers what a feasible heuristic on the same data achieves)."""
    from placement_ilp.mclp import solve_mclp_exact

    class _StatefulBrokenCoverage:
        """Real RadiusCoverage, but returns EMPTY for the first ``n_cand`` calls (the ILP's matrix
        build) so the ILP under-covers, then real coverage (the greedy witness sees the truth)."""

        name = "stateful-broken"

        def __init__(self, radius_m, n_cand):
            self._real = RadiusCoverage(radius_m)
            self._calls = 0
            self._n_cand = n_cand

        def covered_keys(self, site_xy, demand):
            self._calls += 1
            if self._calls <= self._n_cand:
                return frozenset()  # ILP matrix build sees nothing => ILP under-covers
            return self._real.covered_keys(site_xy, demand)

        def area_m2(self):
            return self._real.area_m2()

    inst = synthetic_tied_lattice["tied"]
    sites = dense_candidate_grid(inst["utci"]["lattice"])
    broken = _StatefulBrokenCoverage(_RADIUS_M, len(sites))
    with pytest.raises(Exception):
        solve_mclp_exact(inst["utci"], inst["crowd"], sites, broken, k=2)


# ── PLACE-05 / D-13: the scale guard RAISES (never subsamples / degrades to greedy) ──
def test_ceiling_raises(tiny_score_inputs):
    """An instance whose n_demand x n_cand exceeds ILP_MAX_CONSTRAINT_CELLS RAISES a clear
    "too large for exact solve" message — never silently subsamples (D-13/D-15)."""
    from placement_ilp.mclp import solve_mclp_exact

    inst_utci = tiny_score_inputs["utci"]
    inst_crowd = tiny_score_inputs["crowd"]
    sites = dense_candidate_grid(inst_utci["lattice"])
    # Force the ceiling tiny so the small synthetic instance trips it (site-general: the guard
    # is a function of n_demand x n_cand, not a Forum literal).
    with pytest.raises(Exception, match="(?i)too large|exact solve"):
        solve_mclp_exact(
            inst_utci, inst_crowd, sites, RadiusCoverage(_RADIUS_M), k=2, max_constraint_cells=1
        )


# ── PLACE-05 / D-13 (STAGE PATH): the ceiling raise leaves NO structure_zones.json ──
def test_ceiling_raises_stage(tmp_path, tiny_score_inputs):
    """On the stage path the ceiling raise leaves NO structure_zones.json behind (Plan 04 —
    requires engine="ilp" + max_constraint_cells wired into run_placement_stage)."""
    from core.placement_stage import run_placement_stage

    pdir = tmp_path / "proj"
    _seed_inputs(
        pdir,
        utci=tiny_score_inputs["utci"],
        crowd=tiny_score_inputs["crowd"],
        budget=tiny_score_inputs["budget"],
    )
    with pytest.raises(Exception):
        run_placement_stage(
            "proj", projects_root=tmp_path, k=5, engine="ilp", max_constraint_cells=1
        )
    assert not (pdir / "structure_zones.json").exists()


# ── PLACE-06: the optimality certificate fields ──
def test_certificate_fields(synthetic_tied_lattice):
    """The certificate carries the PLACE-06 field set (D-09); proven_optimal == (mip_gap==0);
    seed is None (HiGHS has no RNG — determinism is by construction)."""
    from placement_ilp.mclp import solve_mclp_exact

    inst = synthetic_tied_lattice["tied"]
    sites = dense_candidate_grid(inst["utci"]["lattice"])
    _result, cert = solve_mclp_exact(
        inst["utci"], inst["crowd"], sites, RadiusCoverage(_RADIUS_M), k=2
    )
    required = {
        "status",
        "objective",
        "best_bound",
        "mip_gap",
        "solver",
        "scipy_version",
        "seed",
        "proven_optimal",
        "determinism",
    }
    assert required <= set(cert.keys())
    assert cert["proven_optimal"] == (cert["mip_gap"] == 0)
    assert cert["seed"] is None


# ── D-03: the engine is part of the cache key (greedy-then-ilp is a MISS) ──
def test_stage_engine(tmp_path, tiny_score_inputs):
    """engine="ilp" produces a contract-valid structure_zones.json; switching engine flips the
    cache key, so a greedy run followed by an ilp run is a MISS (re-solve), not a stale hit (D-03)."""
    from core.placement_stage import run_placement_stage

    pdir = tmp_path / "proj"
    _seed_inputs(
        pdir,
        utci=tiny_score_inputs["utci"],
        crowd=tiny_score_inputs["crowd"],
        budget=tiny_score_inputs["budget"],
    )
    run_placement_stage("proj", projects_root=tmp_path, k=5, engine="greedy")
    greedy_zones = json.loads((pdir / "structure_zones.json").read_text(encoding="utf-8"))

    out = run_placement_stage("proj", projects_root=tmp_path, k=5, engine="ilp")
    assert out is not None
    ilp_zones = json.loads((pdir / "structure_zones.json").read_text(encoding="utf-8"))
    # The ilp run is a MISS (different engine in the cache key) and emits a valid contract artifact.
    assert "structures" in ilp_zones
    # The certificate (ilp-only sidecar) now exists — proof the ilp path actually ran (a stale
    # greedy cache hit would have left no certificate).
    assert (pdir / "optimality_certificate.json").exists()
    # The greedy artifact had no certificate sidecar; the engine flip forced a real re-solve.
    assert "coverage_model" in greedy_zones


# ── D-02: the greedy default path imports NO scipy at module load ──
def test_lazy_import():
    """import core.placement_stage on the greedy default path must NOT import scipy at module
    load — scipy is lazy-imported inside the engine="ilp" miss/solve path (D-02)."""
    # Drop any already-imported scipy so this asserts the IMPORT-TIME behavior, not test-order.
    for mod in [m for m in sys.modules if m == "scipy" or m.startswith("scipy.")]:
        del sys.modules[mod]
    import importlib

    import core.placement_stage as ps

    importlib.reload(ps)
    assert "scipy" not in sys.modules, "core.placement_stage must not import scipy at module load (D-02)"
