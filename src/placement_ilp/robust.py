"""Multi-scenario robustness wrapper — robust / conditional labels over a structured family (PLACE-08).

This is the exact-solver's HONESTY headline. Where ``placement_ilp.mclp.solve_mclp_exact`` answers
"the max-coverage selection over ONE world (the cached crowd grid)", THIS module asks the harder,
more honest question — *"which of those zones survive every plausible world, and which depend on the
routing estimate?"* — and turns the answer into a per-zone label: ``robust`` (selected in ALL
snapshots) vs ``conditional`` (selected in SOME). A single-snapshot "optimal" answer over an
ASSUMED-grade crowd field can read as more confident than the physics warrants; the robust/
conditional split is the antidote (T-14-03).

It lives DELIBERATELY OUTSIDE ``src/core/`` — like ``mclp.py`` it sits in the glob-exempt
``src/placement_ilp/`` tree (the ``tests/test_core.py::test_no_optimal_vocab`` glob over
``src/core/*.py``). It WRAPS ``solve_mclp_exact`` per snapshot, so the earned-optimal claim stays
bound to that call's certificate; THIS module makes NO new optimality claim and emits NO certificate.

Honesty discipline (the load-bearing invariants):

* **The robust label is over covered DEMAND, never cooling/°C (Pitfall 6).** ``robust`` means "this
  zone is selected across the whole structured family of demand worlds" — it is NEVER fused with a
  cooling / °C delta. The demand itself is DERIVED-from-ASSUMED (``crowd_density`` is ASSUMED-grade),
  and the attached ``provenance`` says so.
* **Structured, directional perturbation only (D-01).** The family is a small ENUMERATED set: the
  as-cached world + structured sun×crowd-slice variants + a load-bearing ``far-stage-corrected`` world
  that boosts density on the known under-served far stages (cells beyond
  ``ROBUST_FAR_STAGE_DISTANCE_THRESHOLD_M`` from the demand centroid). No RNG, no undirected jitter,
  no per-cell ±-percent perturbation — every member is a deterministic structured correction toward a
  KNOWN failure direction. (See ``core.constants`` D-01 for the rejected-alternatives rationale.)
* **Determinism by construction (D-07).** Snapshots iterate in fixed ``sorted(snapshot_id)`` order;
  the shared candidate grid is built ONCE; votes are on the canonical ``(row,col)`` integer key
  (never float coords); ``surviving_snapshots`` is ``sorted()`` before it is written. Two solves of
  the same family are byte-identical.
* **The greedy cross-check is INHERITED, not re-added.** ``solve_mclp_exact`` runs ``greedy_mclp`` as
  a permanent lower-bound witness inside EVERY call and RAISES ``CrossCheckError`` if the model is
  wrong. PLACE-10's "permanent cross-check wired" prerequisite is met BY THE WRAP — this module adds
  no second comparison (Don't-Hand-Roll).

Pure transform — no I/O, no manifest, no network, no RNG. scipy is NEVER imported at this
module's top: it is lazy-imported INSIDE ``solve_mclp_exact`` (D-02), so ``import placement_ilp.robust``
and the greedy default stage path stay solver-import-free (the Windows two-tier base/extra split).
"""

from __future__ import annotations

import copy

from core.constants import (
    ASSUMED_CANOPY_HEIGHT_M,
    ILP_MAX_CONSTRAINT_CELLS,
    LITERATURE_DENSITY_MAGNITUDE,
    ROBUST_FAR_STAGE_DENSITY_BOOST,
    ROBUST_FAR_STAGE_DISTANCE_THRESHOLD_M,
    ROBUST_SNAPSHOT_CROWD_SLICES,
    ROBUST_SNAPSHOT_SUN_SLICES,
)

# NO top-level ``import scipy`` (Pitfall 4 / D-02). We import the WRAPPED fn (scipy is deferred to
# INSIDE that call) plus the canonical-identity primitives from the greedy core. Importing these at
# module top is safe — none pull scipy.
from core.placement import _rc_fn, build_demand, dense_candidate_grid
from placement_ilp.mclp import solve_mclp_exact

__all__ = ["solve_robust", "build_snapshot_family", "Snapshot"]


class Snapshot:
    """One member of the structured snapshot family: a (deterministic) world to solve.

    ``id`` is a stable, descriptive label (NOT a timestamp) — it sorts the family and lands in each
    zone's ``surviving_snapshots`` list. ``crowd`` is a deep-copied crowd grid (the SAME lattice as
    the cached grid — XFN-04: never re-derive the lattice); ``coverage_model`` is the per-snapshot
    coverage model (the as-cached model, or a sun-offset variant). The perturbation that produced
    ``crowd`` is structured and directional (a deterministic far-stage / peak-ward correction, never
    undirected jitter — D-01).
    """

    __slots__ = ("id", "crowd", "coverage_model")

    def __init__(self, snapshot_id: str, crowd: dict, coverage_model) -> None:
        self.id = snapshot_id
        self.crowd = crowd
        self.coverage_model = coverage_model

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return f"Snapshot(id={self.id!r})"


def _demand_centroid(utci: dict, crowd: dict, *, density_magnitude: float) -> tuple[float, float]:
    """Weight-weighted centroid (x_m, y_m) of the positive-demand field — the far-stage anchor.

    Reuses ``build_demand`` (the SAME crowd×heat coupling the placer uses), so "far stage" is defined
    relative to where the demand actually IS, on ANY lattice (D-15 — never a Fòrum literal). Falls
    back to the geometric mean of the crowd cells when there is no positive demand (degenerate, but
    keeps the family construction total).
    """
    demand = build_demand(utci, crowd, density_magnitude=density_magnitude)
    tw = sum(d["weight"] for d in demand.values())
    if tw > 0:
        cx = sum(d["x_m"] * d["weight"] for d in demand.values()) / tw
        cy = sum(d["y_m"] * d["weight"] for d in demand.values()) / tw
        return (cx, cy)
    cells = crowd["cells"]
    n = max(len(cells), 1)
    return (
        sum(c["x_m"] for c in cells) / n,
        sum(c["y_m"] for c in cells) / n,
    )


def _boost_far_stage(crowd: dict, centroid: tuple[float, float], *, threshold_m: float, factor: float) -> dict:
    """Deep-copy ``crowd`` and multiply density on every cell BEYOND ``threshold_m`` from ``centroid``.

    The load-bearing structured DIRECTIONAL correction (D-01): it lifts the KNOWN under-served far
    stages so they can compete, which is exactly the failure direction a single-snapshot answer
    misses. A pure deterministic function of the cached grid — NO RNG, NEVER undirected jitter.
    """
    boosted = copy.deepcopy(crowd)
    cx, cy = centroid
    t2 = threshold_m * threshold_m
    for cell in boosted["cells"]:
        dx = cell["x_m"] - cx
        dy = cell["y_m"] - cy
        if dx * dx + dy * dy > t2 and cell["crowd_density_agents_per_cell"] > 0.0:
            cell["crowd_density_agents_per_cell"] *= factor
    return boosted


def _redistribute_toward_peak(crowd: dict, *, share: float) -> dict:
    """Deep-copy ``crowd`` and shift a deterministic ``share`` of density toward the peak cells.

    A STRUCTURED crowd-time-slice perturbation (the "peak"/"headliner" axis): later in a set the
    crowd concentrates around the densest cells. We move a fixed fraction of every below-mean cell's
    density into the single densest cell — a directional, mass-preserving redistribution, NOT
    undirected jitter. Deterministic: the donor set and target are picked by value+canonical order.
    """
    shifted = copy.deepcopy(crowd)
    cells = shifted["cells"]
    densities = [c["crowd_density_agents_per_cell"] for c in cells]
    positive = [d for d in densities if d > 0.0]
    if not positive:
        return shifted
    mean = sum(positive) / len(positive)
    # Target = the densest cell (ties broken by canonical (x_m, y_m) order — deterministic).
    target = max(
        range(len(cells)),
        key=lambda i: (cells[i]["crowd_density_agents_per_cell"], -cells[i]["x_m"], -cells[i]["y_m"]),
    )
    moved = 0.0
    for i, c in enumerate(cells):
        d = c["crowd_density_agents_per_cell"]
        if i != target and 0.0 < d <= mean:
            take = d * share
            c["crowd_density_agents_per_cell"] = d - take
            moved += take
    cells[target]["crowd_density_agents_per_cell"] += moved
    return shifted


def _sun_offset_for(slice_name: str) -> tuple[float, float]:
    """A deterministic, structured shadow offset (dx, dy) for a named sun slice.

    The real per-cell ``sun_vector`` arrives with JuPedSim/real-sun runs (Phase 15); here the named
    slices map to plausible offset directions (morning shadow falls west→east, late-afternoon longer
    and the other way) scaled by the ASSUMED canopy height. NOT drawn from any RNG — an enumerated
    structured axis. The base/as-cached model keeps its own offset; these variants apply to the sun-varied
    family members.
    """
    h = ASSUMED_CANOPY_HEIGHT_M
    table = {
        "morning": (-h, 0.0),
        "mid-afternoon": (0.0, 0.0),
        "late-afternoon": (h, h * 0.5),
        "early": (-h * 0.5, 0.0),
        "peak": (0.0, 0.0),
        "headliner": (h * 0.5, h * 0.25),
    }
    return table.get(slice_name, (0.0, 0.0))


def _offset_variant(base_coverage_model, slice_name: str):
    """An OffsetShadowCoverage variant of ``base_coverage_model`` for a sun slice, when possible.

    If the base model is an ``OffsetShadowCoverage`` we reuse its canopy ring with a structured sun
    offset; otherwise (e.g. ``RadiusCoverage``) sun geometry does not apply, so we keep the base
    model unchanged — the crowd-slice axis still varies that family member (like-for-like otherwise,
    Pitfall 2). Lazy local import keeps the dependency surface tight.
    """
    from core.coverage_models import OffsetShadowCoverage

    if isinstance(base_coverage_model, OffsetShadowCoverage):
        ring = list(base_coverage_model._canopy.exterior.coords)
        return OffsetShadowCoverage(ring, _sun_offset_for(slice_name))
    return base_coverage_model


def build_snapshot_family(
    utci: dict,
    crowd: dict,
    base_coverage_model=None,
    *,
    density_magnitude: float = LITERATURE_DENSITY_MAGNITUDE,
) -> list[Snapshot]:
    """Build the ENUMERATED structured snapshot family (D-01) from ONE cached crowd grid.

    Members (a deterministic ``ROBUST_SNAPSHOT_FAMILY_SIZE``-member set):

    * ``as-cached`` — the unperturbed cached crowd + the base coverage model.
    * ``sun-<slice>+crowd-<slice>`` (×2) — structured sun×crowd-slice variants drawn from
      ``ROBUST_SNAPSHOT_SUN_SLICES`` × ``ROBUST_SNAPSHOT_CROWD_SLICES``: a directional sun offset on
      the coverage model and a mass-preserving peak-ward crowd redistribution.
    * ``far-stage-corrected`` (LOAD-BEARING) — density boosted on every cell beyond
      ``ROBUST_FAR_STAGE_DISTANCE_THRESHOLD_M`` from the demand centroid, by
      ``ROBUST_FAR_STAGE_DENSITY_BOOST``.

    All variants share the SAME lattice (XFN-04). ``base_coverage_model is None`` is tolerated for the
    family-introspection test path (the sun axis then collapses to the crowd axis only).
    """
    centroid = _demand_centroid(utci, crowd, density_magnitude=density_magnitude)

    members: list[Snapshot] = [Snapshot("as-cached", copy.deepcopy(crowd), base_coverage_model)]

    # Two structured sun×crowd-slice variants (skip the neutral "mid-afternoon"/"peak" pair so the
    # variants genuinely differ from as-cached). Pair the sun and crowd axes positionally.
    sun_pick = [s for s in ROBUST_SNAPSHOT_SUN_SLICES if s != "mid-afternoon"][:2]
    crowd_pick = [c for c in ROBUST_SNAPSHOT_CROWD_SLICES if c != "peak"][:2]
    for sun_s, crowd_s in zip(sun_pick, crowd_pick):
        variant_crowd = _redistribute_toward_peak(crowd, share=0.5)
        members.append(
            Snapshot(
                f"sun-{sun_s}+crowd-{crowd_s}",
                variant_crowd,
                _offset_variant(base_coverage_model, sun_s),
            )
        )

    # The load-bearing far-stage-corrected world (D-01 / D-03).
    members.append(
        Snapshot(
            "far-stage-corrected",
            _boost_far_stage(
                crowd,
                centroid,
                threshold_m=ROBUST_FAR_STAGE_DISTANCE_THRESHOLD_M,
                factor=ROBUST_FAR_STAGE_DENSITY_BOOST,
            ),
            base_coverage_model,
        )
    )

    # Fixed sorted snapshot order (D-07) — deterministic family iteration.
    return sorted(members, key=lambda s: s.id)


_PROVENANCE = {
    "tier": "DERIVED-from-ASSUMED",
    "derived": "robust/conditional labels are DERIVED by voting selected zones across the family",
    "assumed": (
        "demand uses ASSUMED-grade crowd_density (LITERATURE_DENSITY_MAGNITUDE); the snapshot family "
        "(sun×crowd slices + far-stage threshold/boost) is ASSUMED, tunable pre-run, immutable after "
        "an accepted run"
    ),
    "note": (
        "the robust label is over covered DEMAND across a structured sun×crowd family incl. a "
        "far-stage-corrected world (robust=in-all, conditional=in-some) — NEVER fused with a "
        "cooling / °C delta (Pitfall 6); structured directional perturbation, never undirected "
        "jitter (D-01)"
    ),
}


def solve_robust(
    utci: dict,
    crowd: dict,
    base_coverage_model,
    *,
    snapshot_family: list[Snapshot] | None = None,
    k: int | None = None,
    budget: float | None = None,
    cost_per_structure: float | None = None,
    density_magnitude: float = LITERATURE_DENSITY_MAGNITUDE,
    max_constraint_cells: int = ILP_MAX_CONSTRAINT_CELLS,
) -> dict:
    """Solve the structured snapshot family and label each ever-selected zone robust / conditional.

    Returns a CONTRACT-VALID ``structure_zones`` artifact (``validate(_, "structure_zones")`` passes):
    the same shape ``run_placement_stage`` persists, with each zone carrying ``robustness`` ∈
    {``robust``, ``conditional``, ``single-snapshot``} and a sorted ``surviving_snapshots`` list, plus
    a top-level ``provenance`` summary tagging the output DERIVED-from-ASSUMED.

    The base ordering / coverage numbers come from the ``as-cached`` snapshot's ranked zones (the
    answer for the real cached world); the robustness label per zone is the vote across the whole
    family on the canonical ``(row,col)`` key.

    Args mirror ``solve_mclp_exact``; ``base_coverage_model`` is the SHARED model the as-cached world
    and (where applicable) the sun variants derive from.
    """
    family = (
        snapshot_family
        if snapshot_family is not None
        else build_snapshot_family(
            utci, crowd, base_coverage_model, density_magnitude=density_magnitude
        )
    )
    family = sorted(family, key=lambda s: s.id)  # fixed sorted order (D-07), even if caller-supplied
    n = len(family)

    rc = _rc_fn(utci["lattice"])
    # SHARED candidate set — built ONCE and reused for every snapshot. Regenerating per snapshot
    # would break center identity → labels become noise (T-14-04 anti-pattern guard).
    sites = dense_candidate_grid(utci["lattice"])

    selected_by_snap: dict[str, set[tuple[int, int]]] = {}
    as_cached_result: dict | None = None
    for snap in family:
        model_s = snap.coverage_model if snap.coverage_model is not None else base_coverage_model
        result_s, _cert_s = solve_mclp_exact(
            utci,
            snap.crowd,
            sites,
            model_s,
            k=k,
            budget=budget,
            cost_per_structure=cost_per_structure,
            density_magnitude=density_magnitude,
            max_constraint_cells=max_constraint_cells,
        )
        # The permanent greedy cross-check already RAN inside that call (inherited — no second one).
        selected_by_snap[snap.id] = {
            rc(st["center"]["x_m"], st["center"]["y_m"]) for st in result_s["structures"]
        }
        if snap.id == "as-cached":
            as_cached_result = result_s

    if as_cached_result is None:  # no as-cached member (caller-supplied family) — use the first id
        first_id = family[0].id
        as_cached_result, _ = solve_mclp_exact(
            utci, family[0].crowd, sites, family[0].coverage_model or base_coverage_model,
            k=k, budget=budget, cost_per_structure=cost_per_structure,
            density_magnitude=density_magnitude, max_constraint_cells=max_constraint_cells,
        )
        selected_by_snap.setdefault(first_id, {
            rc(st["center"]["x_m"], st["center"]["y_m"]) for st in as_cached_result["structures"]
        })

    # ── Aggregate: canonical (row,col) key -> sorted list of snapshot ids that selected it ────────
    survivors: dict[tuple[int, int], list[str]] = {}
    for sid in sorted(selected_by_snap):  # deterministic accumulation order
        for key in selected_by_snap[sid]:
            survivors.setdefault(key, []).append(sid)

    def _label(key: tuple[int, int]) -> str:
        if n == 1:
            return "single-snapshot"
        return "robust" if len(survivors.get(key, [])) == n else "conditional"

    # ── Build the output zones from the as-cached ranking; attach robustness + surviving_snapshots ─
    structures: list[dict] = []
    for z in as_cached_result["structures"]:
        key = rc(z["center"]["x_m"], z["center"]["y_m"])
        structures.append(
            {
                **z,
                "robustness": _label(key),
                "surviving_snapshots": sorted(survivors.get(key, [])),
            }
        )

    artifact = {
        "schema_version": "1.0.0",
        "crs": utci["crs"],
        "lattice": utci["lattice"],
        "coverage_model": as_cached_result["coverage_model"],
        "stopping_rule": {
            "k": k,
            "budget": budget,
            "cost_per_structure": cost_per_structure,
        },
        "total_demand": as_cached_result["total_demand"],
        "covered_demand": as_cached_result["covered_demand"],
        "coverage_pct": as_cached_result["coverage_pct"],
        "structures": structures,
        "infeasible": as_cached_result["infeasible"],
        "provenance": dict(_PROVENANCE),
    }
    return artifact
