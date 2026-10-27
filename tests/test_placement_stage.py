"""Wave-0 RED scaffold for the persisted placement stage (PLACE-03/04/07/09).

These tests describe the EXPECTED behaviour of ``core.placement_stage.run_placement_stage`` — the
orchestrator written in Plan 02. They are DESIGNED-RED: the whole file MUST fail at COLLECTION with
an ``ImportError`` on ``from core.placement_stage import run_placement_stage`` (the module does not
exist yet). Once Plan 02 lands it, these same tests become the GREEN acceptance gate
(interface-first: the behaviour contract is fixed BEFORE the implementation).

Validation-point map (12-VALIDATION VP-1..9 + the determinism/failure pair):

  * VP-1  test_cache_hit_no_compute               2nd unchanged run does ZERO greedy_mclp compute
  * VP-2  test_byte_identical_rerun_determinism    two fresh runs -> byte-identical structure_zones
  *       test_input_change_busts_cache            retuning k busts the cache (transform re-runs)
  * (P-03) test_failure_leaves_stage_not_done      a failing transform leaves the stage NOT done
  * VP-3  test_artifact_is_contract_valid_schema   emits a contract-valid structure_zones; lattice==utci's
  * VP-4  test_no_design_geometry                  no polygon/footprint/member/bom key in the artifact
  * VP-5  test_demo_uses_offset_shadow_and_ranks   demo model is per-structure offset_shadow -> real ranked zones
  * VP-6  test_coverage_provenance_recorded        coverage_model + offset SOURCE provenance-tagged (never silent)
  * VP-7  test_infeasibility_true_reason           true-reason infeasibility written; unlinked on feasible re-run
  * VP-8  test_xfn04_lattice_drift                 crowd lattice != utci lattice -> AssertionError
  * VP-9  test_provenance_tiers_derived_from_assumed DERIVED coverage_pct + ASSUMED k/cost; crowd_density survives

The stage signature Plan 02 implements: ``run_placement_stage(project_id, *, projects_root=None,
k=None)`` (budget from parsed_brief; K defaults to ASSUMED_K_DEFAULT). No crowd/geom marker — the
placement stage is base-tier (shapely only, torch-free), like test_core.py / test_placement.py.

karpathy: hand-computable tiny lattice; no fixture-factory framework; no torch.
"""

from __future__ import annotations

import copy
import json

# conftest_core is imported EXPLICITLY (not auto-loaded — pytest only auto-loads conftest.py).
from conftest_core import (  # noqa: F401
    TINY_SHADOW_POLYGON_M,
    _seed_inputs,
    _seed_inputs_with_gh_meta,
    tiny_score_inputs,
)

import pytest

# ── THE RED IMPORT: this module does not exist until Plan 02 ────────────────
from core.placement_stage import run_placement_stage  # noqa: E402  (designed-RED)


def _iter_keys(obj):
    """Recursively yield every dict key in a nested JSON structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _iter_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_keys(item)


# ── VP-1: cache hit does ZERO greedy_mclp compute ───────────────────────────
def test_cache_hit_no_compute(tmp_path, tiny_score_inputs, monkeypatch):
    """A 2nd unchanged-input call does ZERO transform (the greedy_mclp counter stays 1)."""
    import core.placement_stage as stage_mod

    counter = [0]
    real = stage_mod.greedy_mclp

    def _counting(*args, **kwargs):
        counter[0] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(stage_mod, "greedy_mclp", _counting)

    pdir = tmp_path / "proj"
    _seed_inputs(pdir, utci=tiny_score_inputs["utci"], crowd=tiny_score_inputs["crowd"],
                 budget=tiny_score_inputs["budget"])
    first = run_placement_stage("proj", projects_root=tmp_path)
    assert counter[0] == 1, "first run computes exactly once"
    second = run_placement_stage("proj", projects_root=tmp_path)
    assert counter[0] == 1, "cache hit must do ZERO greedy_mclp compute"
    assert second == first


# ── VP-2: byte-identical reruns (determinism) ───────────────────────────────
def test_byte_identical_rerun_determinism(tmp_path, tiny_score_inputs):
    """Two fresh runs over the same inputs produce byte-identical structure_zones.json."""
    def _run(name):
        pdir = tmp_path / name
        _seed_inputs(pdir, utci=tiny_score_inputs["utci"], crowd=tiny_score_inputs["crowd"],
                     budget=tiny_score_inputs["budget"])
        run_placement_stage(name, projects_root=tmp_path)
        return (pdir / "structure_zones.json").read_bytes()

    assert _run("a") == _run("b"), "structure_zones bytes must be identical across reruns"


# ── VP-2: a changed stopping cap busts the cache ────────────────────────────
def test_input_change_busts_cache(tmp_path, tiny_score_inputs, monkeypatch):
    """Re-running with a different k is a cache MISS (greedy_mclp runs again)."""
    import core.placement_stage as stage_mod

    counter = [0]
    real = stage_mod.greedy_mclp

    def _counting(*args, **kwargs):
        counter[0] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(stage_mod, "greedy_mclp", _counting)

    pdir = tmp_path / "proj"
    _seed_inputs(pdir, utci=tiny_score_inputs["utci"], crowd=tiny_score_inputs["crowd"],
                 budget=tiny_score_inputs["budget"])
    run_placement_stage("proj", projects_root=tmp_path, k=1)
    assert counter[0] == 1
    run_placement_stage("proj", projects_root=tmp_path, k=3)
    assert counter[0] == 2, "retuning k must bust the cache (MN-02 / Pitfall D)"


# ── PLACE-03: a failing transform leaves the stage NOT done ─────────────────
def test_failure_leaves_stage_not_done(tmp_path, tiny_score_inputs, monkeypatch):
    """An injected failing greedy_mclp raises; stage NOT done; NO structure_zones.json written."""
    import core.placement_stage as stage_mod
    from manifest.manifest import DONE

    class _InjectedError(RuntimeError):
        pass

    def _boom(*_args, **_kwargs):
        raise _InjectedError("injected transform failure")

    monkeypatch.setattr(stage_mod, "greedy_mclp", _boom)

    pdir = tmp_path / "proj"
    _seed_inputs(pdir, utci=tiny_score_inputs["utci"], crowd=tiny_score_inputs["crowd"],
                 budget=tiny_score_inputs["budget"])
    with pytest.raises(_InjectedError):
        run_placement_stage("proj", projects_root=tmp_path)

    assert not (pdir / "structure_zones.json").exists(), "no partial artifact on failure"
    manifest = json.loads((pdir / "manifest.json").read_text(encoding="utf-8"))
    stage = next(s for s in manifest["stages"] if s["name"] == "structure_zones")
    assert stage["status"] != DONE


# ── VP-3: emits a contract-valid structure_zones (lattice == utci's) ────────
def test_artifact_is_contract_valid_schema(tmp_path, tiny_score_inputs):
    """run_placement_stage emits a contract-valid structure_zones; lattice == utci's."""
    from validate.validate import validate

    pdir = tmp_path / "proj"
    _seed_inputs(pdir, utci=tiny_score_inputs["utci"], crowd=tiny_score_inputs["crowd"],
                 budget=tiny_score_inputs["budget"])
    artifact = run_placement_stage("proj", projects_root=tmp_path)

    validate(artifact, "structure_zones")
    on_disk = json.loads((pdir / "structure_zones.json").read_text(encoding="utf-8"))
    validate(on_disk, "structure_zones")
    assert artifact["lattice"] == tiny_score_inputs["utci"]["lattice"]


# ── VP-4: no design geometry anywhere in the artifact (PLACE-09) ────────────
def test_no_design_geometry(tmp_path, tiny_score_inputs):
    """The tool never designs: no polygon/footprint/member/bom key in the emitted artifact."""
    pdir = tmp_path / "proj"
    _seed_inputs(pdir, utci=tiny_score_inputs["utci"], crowd=tiny_score_inputs["crowd"],
                 budget=tiny_score_inputs["budget"])
    artifact = run_placement_stage("proj", projects_root=tmp_path)

    keys = {k.lower() for k in _iter_keys(artifact)}
    banned = {"polygons", "polygon", "footprint", "member", "members", "bom", "member_sizing"}
    assert not (keys & banned), f"design-geometry key leaked: {keys & banned}"


# ── VP-5: the DEMO model is a per-structure offset_shadow -> real ranked zones ─
def test_demo_uses_offset_shadow_and_ranks(tmp_path, tiny_score_inputs, monkeypatch):
    """Seeding WITHOUT gh_meta, the demo model is a per-structure OffsetShadowCoverage giving real
    per-candidate variation: distinct centres + at least two distinct marginal_demand values, with
    the first pick the highest-demand zone. A small canopy (1 cell each) makes the ranking explicit."""
    import core.placement_stage as stage_mod

    # A 6x6 m canopy (half-span 3) shades ~one tiny-grid cell -> each candidate covers a different
    # cell, so the MCLP ranks by per-cell demand (a 24x24 m canopy would blanket the whole 18 m grid).
    monkeypatch.setattr(stage_mod, "ASSUMED_CANOPY_HALF_SPAN_M", 3.0)

    pdir = tmp_path / "proj"
    _seed_inputs(pdir, utci=tiny_score_inputs["utci"], crowd=tiny_score_inputs["crowd"],
                 budget=tiny_score_inputs["budget"])
    artifact = run_placement_stage("proj", projects_root=tmp_path, k=5)

    assert artifact["coverage_model"] == "offset_shadow"
    assert artifact["coverage_pct"] > 0
    zones = artifact["structures"]
    assert len(zones) >= 2, "the per-structure canopy must produce >= 2 ranked zones"
    centres = [(z["center"]["x_m"], z["center"]["y_m"]) for z in zones]
    assert len(set(centres)) == len(centres), "each ranked zone has a distinct centre"
    assert len({z["marginal_demand"] for z in zones}) >= 2, "marginal demand varies per candidate"
    # First pick = the highest-demand cell (0,2): centre (15.0, 3.0), demand 8.0 (hand-computed).
    assert zones[0]["rank"] == 1
    assert zones[0]["center"] == {"x_m": 15.0, "y_m": 3.0}
    assert zones[0]["marginal_demand"] == 8.0
    assert zones[0]["robustness"] == "single-snapshot"


# ── VP-6: coverage_model + offset SOURCE are provenance-tagged (never silent) ─
def test_coverage_provenance_recorded(tmp_path, tiny_score_inputs):
    """provenance.json records a coverage_model entry whose source names the shadow-offset SOURCE.
    With no sun_vector on disk the offset is the ASSUMED high-noon (0,0) default — and the ledger
    MUST say so (never silently presents an assumed offset as a real-sun result)."""
    pdir = tmp_path / "proj"
    _seed_inputs(pdir, utci=tiny_score_inputs["utci"], crowd=tiny_score_inputs["crowd"],
                 budget=tiny_score_inputs["budget"])
    run_placement_stage("proj", projects_root=tmp_path)

    entries = json.loads((pdir / "provenance.json").read_text(encoding="utf-8"))["entries"]
    cov = next((e for e in entries if e["key"] == "coverage_model"), None)
    assert cov is not None, "coverage_model must be provenance-tagged"
    assert cov["tier"] == "ASSUMED"
    assert "noon" in cov["source"].lower(), "the assumed high-noon offset source must be disclosed"


# ── VP-7: true-reason infeasibility, unlinked on a feasible re-run ──────────
def test_infeasibility_true_reason(tmp_path, tiny_score_inputs):
    """Three sub-cases: no crowd-heat overlap names that reason; a sub-structure budget names the
    budget reason; a feasible re-run unlinks the stale infeasibility.json (MJ-04)."""
    # (a) all-cool grid -> every score 0 -> no-overlap reason
    cool = copy.deepcopy(tiny_score_inputs["utci"])
    for c in cool["cells"]:
        c["utci_c"] = 24.0
    pdir_a = tmp_path / "cool"
    _seed_inputs(pdir_a, utci=cool, crowd=tiny_score_inputs["crowd"], budget=1_000_000.0)
    run_placement_stage("cool", projects_root=tmp_path)
    report_a = json.loads((pdir_a / "infeasibility.json").read_text(encoding="utf-8"))
    assert "crowd-heat overlap" in report_a["reason"], "must name the no-overlap cause, not budget"

    # (b) budget below the cost of one structure -> budget reason
    pdir_b = tmp_path / "broke"
    _seed_inputs(pdir_b, utci=tiny_score_inputs["utci"], crowd=tiny_score_inputs["crowd"],
                 budget=10_000.0)  # < ASSUMED_COST_PER_STRUCTURE (50_000)
    run_placement_stage("broke", projects_root=tmp_path)
    report_b = json.loads((pdir_b / "infeasibility.json").read_text(encoding="utf-8"))
    assert "budget" in report_b["reason"].lower()

    # (c) a feasible re-run removes the stale report
    _seed_inputs(pdir_b, utci=tiny_score_inputs["utci"], crowd=tiny_score_inputs["crowd"],
                 budget=tiny_score_inputs["budget"])
    run_placement_stage("broke", projects_root=tmp_path)
    assert not (pdir_b / "infeasibility.json").exists(), "stale infeasibility must be unlinked"


# ── VP-8: XFN-04 lattice drift is refused ───────────────────────────────────
def test_xfn04_lattice_drift(tmp_path, tiny_score_inputs):
    """A crowd grid whose lattice differs from utci's makes run_placement_stage raise."""
    drifted = copy.deepcopy(tiny_score_inputs["crowd"])
    drifted["lattice"]["cell_size_m"] = 12.0  # != utci's 6.0
    pdir = tmp_path / "proj"
    _seed_inputs(pdir, utci=tiny_score_inputs["utci"], crowd=drifted,
                 budget=tiny_score_inputs["budget"])
    with pytest.raises(AssertionError):
        run_placement_stage("proj", projects_root=tmp_path)


# ── VP-9: DERIVED-from-ASSUMED provenance; upstream crowd_density survives ───
def test_provenance_tiers_derived_from_assumed(tmp_path, tiny_score_inputs):
    """The merged ledger carries a DERIVED coverage_pct + ASSUMED k/cost/coverage_model entries,
    and the upstream crowd stage's ASSUMED crowd_density entry SURVIVES the merge (MJ-02)."""
    from provenance.ledger import ProvenanceLedger

    pdir = tmp_path / "proj"
    _seed_inputs(pdir, utci=tiny_score_inputs["utci"], crowd=tiny_score_inputs["crowd"],
                 budget=tiny_score_inputs["budget"])
    # Seed a prior provenance.json with the upstream crowd_density entry (a different stage).
    led = ProvenanceLedger()
    led.crowd_density(2.5, stage="crowd")
    led.write(pdir / "provenance.json")

    run_placement_stage("proj", projects_root=tmp_path)

    entries = json.loads((pdir / "provenance.json").read_text(encoding="utf-8"))["entries"]
    by_key = {e["key"]: e for e in entries}

    assert "crowd_density" in by_key, "upstream crowd_density entry must survive the merge"
    assert by_key["crowd_density"]["tier"] == "ASSUMED"
    assert by_key["crowd_density"]["stage"] == "crowd"

    assert by_key["coverage_pct"]["tier"] == "DERIVED"
    assert by_key["coverage_pct"]["stage"] == "structure_zones"
    assert by_key["k"]["tier"] == "ASSUMED"
    assert by_key["cost_per_structure"]["tier"] == "ASSUMED"
    assert by_key["coverage_model"]["tier"] == "ASSUMED"


# ── CORE-05 honesty guard — RE-ANCHORED from the retired tests/test_core.py ──
#
# The greedy `score.py`/`footprint.py`/`core.py` modules + `tests/test_core.py` (which
# held the original `test_no_optimal_vocab` + `test_no_optimal_vocab_structure_zones`)
# RETIRED in the Phase-14 Plan-04 deletion wave. The honesty guard is LOAD-BEARING — it
# is re-anchored here, onto the SURVIVING `src/core/*.py` sources + the canonical
# `structure_zones` artifacts the placement stage emits. It is NEVER lost in the deletion:
# the greedy placer made no best-coverage claim (CORE-05 / Pitfall 10), and neither does
# the ranked MCLP placer that superseded it. The SOLE legal home for "optimal" is the
# glob-exempt `src/placement_ilp/` certificate (AMEND-01), never `src/core/`.
from pathlib import Path  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_no_optimal_vocab(tmp_path, tiny_score_inputs):
    """CORE-05 / Pitfall 10 (RE-ANCHORED): neither the surviving src/core/*.py sources nor
    the emitted structure_zones artifacts contain the word "optimal" — the placement output
    is NEVER claimed best-coverage. (Was anchored on the retired run_core_stage + score_grid/
    footprint; now driven by run_placement_stage + the structure_zones artifacts.)"""
    src_core = _REPO_ROOT / "src" / "core"
    for py in src_core.glob("*.py"):
        assert "optimal" not in py.read_text(encoding="utf-8").lower(), (
            f"{py.name} must not contain optimization vocabulary (CORE-05)"
        )

    pdir = tmp_path / "proj"
    _seed_inputs(pdir, utci=tiny_score_inputs["utci"], crowd=tiny_score_inputs["crowd"],
                 budget=tiny_score_inputs["budget"])
    run_placement_stage("proj", projects_root=tmp_path, k=5)
    for name in ("structure_zones.json", "structure_zones_meta.json", "provenance.json"):
        text = (pdir / name).read_text(encoding="utf-8").lower()
        assert "optimal" not in text, f"{name} must not claim optimality (CORE-05)"
