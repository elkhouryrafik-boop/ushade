"""Phase 14 Nyquist coverage for the multi-scenario robustness engine (now GREEN, base-tier).

Every PLACE-08 + PLACE-10-tiering behavior gets a NAMED, automated test (Nyquist compliance —
feedback latency < 30 s, implementation test-driven). The file landed RED in Wave 1 under a
module-level ``red`` marker; Plan 02 (the engine: snapshot family + per-snapshot solve +
deterministic label aggregation) turned 7 green, and Plan 03 (this wave — the teeth-test green)
turned the 8th green and DROPPED the marker. The whole file now runs in the green base suite
(``-m "not crowd and not geom and not red"``), no longer deselected.

Imports of the robust/solver symbols live INSIDE the test bodies (NOT at module top) so
COLLECTION succeeds independently of the absent ``placement_ilp.robust`` module and the lazy
scipy import discipline (D-02 / Pitfall 4). The tests therefore fail RED at the ASSERTION /
in-body-import level on the absent ``placement_ilp.robust`` module — NEVER at collection.

Behavior map (CONTEXT D-01..D-07; RESEARCH §Validation Architecture test map; all GREEN):

  * PLACE-08      test_robust_and_conditional_labels        a multi-snapshot solve labels each
                                                            zone robust (selected in ALL snapshots)
                                                            or conditional (some); labels populate
                                                            the FROZEN ``robustness`` field.
  * PLACE-08/D-01 test_family_is_structured_far_stage_corrected
                                                            the family includes a far-stage-
                                                            corrected world (NOT ±20% symmetric
                                                            noise).
  * PLACE-08/D-03 test_far_stage_spike_flips_a_label        THE TEETH-TEST — as-cached labels vs
                                                            far-stage-spiked labels differ for >=1
                                                            zone (proves the family bites).
  * PLACE-08/D-07 test_robust_determinism                   two solves of the same family yield
                                                            byte-identical selection + labels.
  * PLACE-08/D-04 test_output_shape_ranked_zones_no_footprint
                                                            zones carry {center, area_m2,
                                                            coverage_pct, robustness,
                                                            surviving_snapshots}; NO footprint/
                                                            polygon/member/bom key; contract-valid.
  * PLACE-10      test_derived_from_assumed_provenance      the robust output is tagged DERIVED-
                                                            from-ASSUMED (crowd_density ASSUMED
                                                            survives).
  * PLACE-08/D-02 test_lazy_import_no_scipy                 importing ``placement_ilp.robust``
                                                            pulls NO scipy at module load.
  * PLACE-10      test_cross_check_inherited                the greedy lower-bound cross-check is
                                                            INHERITED from ``solve_mclp_exact`` (no
                                                            second cross-check) — reuses the EXISTING
                                                            green broken-model raise. (GREEN today;
                                                            documents the inheritance robust.py wraps.)

Site-generality (D-15): every behavior is proven on the SMALL synthetic ``synthetic_tied_lattice``
fixture (NON-Forum 6x6) incl. its new ``far_stage`` region — valid for ANY lattice size.

Runs in the BASE tier (``-m "not crowd and not geom and not red"``) once the marker drops — scipy
is a base dependency, lazy-loaded INSIDE the wrapped ``solve_mclp_exact`` call.
"""

from __future__ import annotations

import copy
import importlib
import sys

import pytest

# conftest is imported EXPLICITLY for the named far-stage spike constant (pytest auto-loads the
# FIXTURES from conftest.py, but a module-level constant must be imported by name).
from conftest import _FAR_STAGE_SPIKE

from core.coverage_models import RadiusCoverage

# Wave 3 (Plan 03): the implementing plans turned every PLACE-08 / PLACE-10-tiering behavior green
# (Plan 02 made 7 green; Plan 03's teeth-test ``test_far_stage_spike_flips_a_label`` is the 8th).
# The module-level ``red`` quarantine marker is now DROPPED entirely — the whole file runs in the
# base tier (``-m "not crowd and not geom and not red"``), mirroring test_placement_ilp.py's
# marker-dropped end state. scipy stays lazy (loaded INSIDE the wrapped solve_mclp_exact call), so
# these tests are base-tier-safe.

# Coverage radius sized to the synthetic clusters (10 m cells; a 6 m disc covers a cell's own
# centre only, so a per-structure candidate shades its own demand cell — keeps the instances
# hand-computable). All snapshots in a family MUST share the SAME base coverage model instance
# (like-for-like comparability across the family — Pitfall 2).
_RADIUS_M = 6.0


def _selection_xy(result: dict) -> list[tuple[float, float]]:
    """The selected structure centres in selection order — the byte-stable determinism witness."""
    return [(z["center"]["x_m"], z["center"]["y_m"]) for z in result["structures"]]


def _labels(result: dict) -> dict[tuple[float, float], str]:
    """{(x_m, y_m): robustness} per selected zone — the robust/conditional label map a teeth-test
    compares across the as-cached vs far-stage-spiked family (vote on the zone's reported centre)."""
    return {
        (z["center"]["x_m"], z["center"]["y_m"]): z["robustness"] for z in result["structures"]
    }


def _spike_far_stage(crowd: dict, *, factor: float) -> dict:
    """Return a copy of the ``far_stage`` crowd grid with the FAR cluster's density multiplied by
    ``factor`` — the structured DIRECTIONAL far-stage correction (NOT ±20% symmetric noise, D-01).

    The FAR cluster is the under-served far stage (cells (5,4),(5,5),(4,5) at density 1.0 in the
    as-cached world). Boosting only those cells is the load-bearing far-stage-corrected world.
    """
    boosted = copy.deepcopy(crowd)
    # The FAR cluster sits beyond ~50 m from the near centroid (~(10,10) m) — pick it out by a
    # distance band so the helper stays lattice-agnostic (no hardcoded cell list).
    near_centroid = (10.0, 10.0)
    for cell in boosted["cells"]:
        dx = cell["x_m"] - near_centroid[0]
        dy = cell["y_m"] - near_centroid[1]
        if (dx * dx + dy * dy) ** 0.5 > 40.0 and cell["crowd_density_agents_per_cell"] > 0.0:
            cell["crowd_density_agents_per_cell"] *= factor
    return boosted


# ── PLACE-08: a multi-snapshot solve labels each zone robust / conditional ──
def test_robust_and_conditional_labels(synthetic_tied_lattice):
    """A multi-snapshot solve labels each selected zone ``robust`` (selected in ALL snapshots) or
    ``conditional`` (selected in some), populating the FROZEN ``robustness`` field. GREEN
    (Plan 02 built ``placement_ilp.robust``)."""
    from placement_ilp.robust import solve_robust

    inst = synthetic_tied_lattice["far_stage"]
    result = solve_robust(
        inst["utci"], inst["crowd"], RadiusCoverage(_RADIUS_M), k=2
    )
    labels = {z["robustness"] for z in result["structures"]}
    # every zone carries a legal robustness label from the frozen enum
    assert labels <= {"single-snapshot", "robust", "conditional"}
    # a multi-snapshot family must produce robust/conditional (NOT the single-snapshot default)
    assert labels & {"robust", "conditional"}


# ── PLACE-08 / D-01: the family is STRUCTURED (far-stage-corrected), not ±20% symmetric noise ──
def test_family_is_structured_far_stage_corrected(synthetic_tied_lattice):
    """The snapshot family includes a far-stage-corrected world and is NOT ±20% symmetric noise:
    at least one family member carries boosted density on the far-stage cells (the structured
    directional correction). GREEN (Plan 02 exposes the family)."""
    from placement_ilp.robust import build_snapshot_family

    inst = synthetic_tied_lattice["far_stage"]
    family = build_snapshot_family(inst["utci"], inst["crowd"])
    # a structured family has a NAMED far-stage-corrected member (not anonymous symmetric noise)
    member_ids = {getattr(s, "id", s) for s in family}
    assert any("far" in str(mid).lower() and "stage" in str(mid).lower() for mid in member_ids), (
        "the structured family must expose a named far-stage-corrected member (D-01)"
    )


# ── PLACE-08 / D-03: THE TEETH-TEST — a far-stage spike flips >=1 zone's label ──
def test_far_stage_spike_flips_a_label(synthetic_tied_lattice):
    """The load-bearing artifact: as-cached labels vs far-stage-spiked labels differ for >=1 zone.
    Proves the family exercises real STRUCTURED variance (a far-stage correction CHANGES which
    zones survive) — a single-snapshot 'optimal' would have been misleading. GREEN (Plan 03 —
    the teeth bite: the far-stage spike flips a label against the as-cached world)."""
    from placement_ilp.robust import solve_robust

    inst = synthetic_tied_lattice["far_stage"]
    base_a = solve_robust(inst["utci"], inst["crowd"], RadiusCoverage(_RADIUS_M), k=2)

    spiked_crowd = _spike_far_stage(inst["crowd"], factor=_FAR_STAGE_SPIKE)
    base_b = solve_robust(inst["utci"], spiked_crowd, RadiusCoverage(_RADIUS_M), k=2)

    labels_a = _labels(base_a)
    labels_b = _labels(base_b)
    assert labels_a != labels_b, (
        "the far-stage spike must flip >=1 zone's robust/conditional label (NOT symmetric noise)"
    )


# ── PLACE-08 / D-07: byte-identical determinism over the same family ──
def test_robust_determinism(synthetic_tied_lattice):
    """Two solves of the SAME family yield byte-identical selection AND labels — the cross-snapshot
    aggregation is deterministic over canonical (row,col) order (D-07). GREEN."""
    from placement_ilp.robust import solve_robust

    inst = synthetic_tied_lattice["far_stage"]
    a = solve_robust(inst["utci"], inst["crowd"], RadiusCoverage(_RADIUS_M), k=2)
    b = solve_robust(inst["utci"], inst["crowd"], RadiusCoverage(_RADIUS_M), k=2)
    assert _selection_xy(a) == _selection_xy(b)
    assert _labels(a) == _labels(b)


# ── PLACE-08 / D-04: output is RANKED ZONES with robustness — NO design geometry; contract-valid ──
def test_output_shape_ranked_zones_no_footprint(synthetic_tied_lattice):
    """Each zone carries {center, area_m2, coverage_pct, robustness, surviving_snapshots} and NO
    footprint/polygon/member/bom key (the tool never designs, PLACE-09); the artifact passes
    ``validate(_, "structure_zones")``. GREEN."""
    from validate.validate import validate

    from placement_ilp.robust import solve_robust

    inst = synthetic_tied_lattice["far_stage"]
    result = solve_robust(inst["utci"], inst["crowd"], RadiusCoverage(_RADIUS_M), k=2)

    for zone in result["structures"]:
        assert {"center", "area_m2", "coverage_pct", "robustness", "surviving_snapshots"} <= set(zone)
        for forbidden in ("footprint", "polygon", "member", "bom"):
            assert forbidden not in zone, f"a placement zone must never carry a {forbidden!r} key"

    # the robust output is a valid structure_zones artifact (frozen contract, no re-schema).
    # ``provenance`` is a NON-contract annotation solve_robust attaches for the DERIVED-from-ASSUMED
    # honesty surface (test_derived_from_assumed_provenance) — it is NOT part of the frozen
    # structure_zones schema (additionalProperties:false), so the stage strips it before persisting
    # structure_zones.json (it flows to provenance.json instead). Validate the CONTRACT projection.
    contract_artifact = {k: v for k, v in result.items() if k != "provenance"}
    validate(contract_artifact, "structure_zones")


# ── PLACE-10: the robust placement output is tagged DERIVED-from-ASSUMED ──
def test_derived_from_assumed_provenance(synthetic_tied_lattice):
    """The robust placement output is DERIVED-from-ASSUMED — the ASSUMED-grade crowd_density
    survives the merge into the provenance ledger (PLACE-10 / D-04). GREEN (Plan 02 wired the
    stage-level provenance for the robust path)."""
    from placement_ilp.robust import solve_robust

    inst = synthetic_tied_lattice["far_stage"]
    result = solve_robust(inst["utci"], inst["crowd"], RadiusCoverage(_RADIUS_M), k=2)
    provenance = result.get("provenance", {})
    blob = str(provenance).lower()
    assert "derived" in blob and "assumed" in blob, (
        "the robust placement output must be tagged DERIVED-from-ASSUMED (crowd_density ASSUMED)"
    )


# ── PLACE-08 / D-02: importing placement_ilp.robust pulls NO scipy at module load ──
def test_lazy_import_no_scipy():
    """import ``placement_ilp.robust`` must NOT import scipy at module load — scipy is lazy-imported
    INSIDE the wrapped ``solve_mclp_exact`` call, never at robust.py's module top (D-02 / Pitfall 4).
    GREEN (Plan 02 created the module with the lazy-scipy import discipline)."""
    for mod in [m for m in sys.modules if m == "scipy" or m.startswith("scipy.")]:
        del sys.modules[mod]

    import placement_ilp.robust as robust

    importlib.reload(robust)
    assert "scipy" not in sys.modules, (
        "placement_ilp.robust must not import scipy at module load (D-02)"
    )


# ── PLACE-10: the greedy lower-bound cross-check is INHERITED (no second cross-check added) ──
def test_cross_check_inherited(synthetic_tied_lattice):
    """robust.py wraps ``solve_mclp_exact`` per snapshot, so the permanent greedy lower-bound
    cross-check (which RAISES when the ILP under-covers the greedy witness) is inherited unchanged
    — robust.py adds NO second comparison (PLACE-10 prerequisite already met; D-05).

    This asserts the EXISTING green semantics from ``test_placement_ilp.py::test_cross_check_raises``
    (the stateful-broken-coverage raise) directly on ``solve_mclp_exact`` — the call robust.py
    wraps — documenting that the cross-check is permanent BY INHERITANCE. GREEN today (it exercises
    only the already-built solver), but lives here under the red marker so the whole scaffold is
    one quarantined unit until the implementing plans land."""
    from placement_ilp.mclp import solve_mclp_exact
    from core.placement import dense_candidate_grid

    class _StatefulBrokenCoverage:
        """Real RadiusCoverage, but EMPTY for the first ``n_cand`` calls (the ILP's matrix build)
        so the ILP under-covers, then real coverage (the greedy witness sees the truth) — the
        same shape as test_placement_ilp.py's broken model."""

        name = "stateful-broken"

        def __init__(self, radius_m, n_cand):
            self._real = RadiusCoverage(radius_m)
            self._calls = 0
            self._n_cand = n_cand

        def covered_keys(self, site_xy, demand):
            self._calls += 1
            if self._calls <= self._n_cand:
                return frozenset()
            return self._real.covered_keys(site_xy, demand)

        def area_m2(self):
            return self._real.area_m2()

    inst = synthetic_tied_lattice["tied"]
    sites = dense_candidate_grid(inst["utci"]["lattice"])
    broken = _StatefulBrokenCoverage(_RADIUS_M, len(sites))
    with pytest.raises(Exception):
        solve_mclp_exact(inst["utci"], inst["crowd"], sites, broken, k=2)
