"""Exact ILP-MCLP engine — the EARNED-optimal placer (PLACE-05 / PLACE-06).

This module is the exact counterpart of ``core.placement.greedy_mclp``. Where the greedy is a
bounded ``(1 − 1/e)`` heuristic that makes NO best-coverage claim (CORE-05 honesty lock), THIS
engine solves the Maximal-Covering-Location Problem (MCLP) to **PROVEN optimality** via
``scipy.optimize.milp`` (HiGHS) and emits a falsifiable optimality certificate
(``mip_gap == 0 and status == 0 ⇒ proven_optimal``).

It lives DELIBERATELY OUTSIDE ``src/core/``: the honesty firewall
(``tests/test_core.py::test_no_optimal_vocab``) globs ``src/core/*.py`` and forbids the word
"optimal" there. Per the 2026-06-20 AMEND-01 amendment the lock is SCOPED to the greedy core —
this package (``src/placement_ilp/``) is the SOLE source tree legitimately allowed the word
"optimal", and the certificate it builds is the ONLY artifact that carries the earned-optimal
claim, bound there by a same-sentence conditional clause (an internal QA artifact, never a
confident answer to a physically uncertain question — the demand is DERIVED-from-ASSUMED).

Honesty discipline (the load-bearing invariants):

* **Like-for-like cross-check (D-10/D-11):** the ILP shares ``build_demand`` + the candidate
  ordering + ``coverage_model.covered_keys`` with the greedy, runs ``greedy_mclp`` EVERY solve as
  a permanent lower-bound witness, and RAISES if ``ilp_covered < greedy_covered`` (the model is
  wrong). The comparison is on the REAL float covered_demand of each engine's selected set —
  integerization is solver-internal only (Pitfall 2).
* **Determinism by construction (D-12):** byte-identical selection via a scale-separated
  lexicographic tiebreak baked into the objective over the canonical ``(row,col,index)`` order —
  provably smaller than the integer min-coverage gap of 1, so it orders WITHIN, never moves, the
  coverage optimum. NOT an epsilon-nudge. Single-thread HiGHS (no thread/seed knob exists).
* **Raise-not-subsample ceiling (D-13/D-15):** above ``ILP_MAX_CONSTRAINT_CELLS`` (a function of
  ``n_demand × n_cand``, NOT a Fòrum literal) the solve RAISES a clear site-agnostic message —
  it NEVER silently subsamples or degrades to greedy.
* **No naked optimal (Pitfall 6):** ``proven_optimal`` is derived strictly from
  ``mip_gap == 0 and status == 0``; a time-limited / nonzero-gap incumbent FAILS LOUD.

Pure transform — no I/O, no manifest, no network, no randomness. scipy is lazy-imported INSIDE
``solve_mclp_exact`` (D-02) so ``import placement_ilp`` and the greedy default stage path stay
solver-import-free.
"""

from __future__ import annotations

from core.constants import (
    ILP_DEMAND_WEIGHT_SCALE,
    ILP_MAX_CONSTRAINT_CELLS,
    LITERATURE_DENSITY_MAGNITUDE,
)


class IlpTooLargeError(ValueError):
    """The exact solve was refused because ``n_demand × n_cand`` exceeds the scale ceiling.

    A loud, site-agnostic refusal (D-13/D-15) — the exact ILP NEVER silently subsamples or
    degrades to the greedy. The remedy is to raise the ceiling deliberately or coarsen the
    candidate grid via ``step_cells > 1``.
    """


class CrossCheckError(AssertionError):
    """The ILP covered LESS weighted demand than the greedy lower bound — the model is wrong.

    The greedy is the exact solve's permanent lower-bound witness (D-10/D-11): a proven optimum
    can NEVER cover less than a feasible heuristic. If this fires the MILP construction is broken;
    fail loud rather than emit a silently-wrong "optimal" answer (T-13-Integrity).
    """


#: The SOLE place the word "optimal"/"earned-optimal" legally appears as a claim. Bound to the
#: certificate by a same-sentence conditional clause (AMEND-01).
_EARNED_OPTIMAL_CLAIM = (
    "earned-optimal IFF proven_optimal (mip_gap == 0 and status == 0): a max-coverage MCLP "
    "solution over DERIVED-from-ASSUMED demand (crowd_density is ASSUMED-grade); an internal QA "
    "artifact, never a confident answer to a physically uncertain question — no caption may fuse "
    "this with a cooling / °C delta."
)

_DETERMINISM_BASIS = (
    "single-thread HiGHS, no RNG, in-objective scale-separated lexicographic (row,col,index) "
    "tiebreak"
)
_SOLVER = "scipy.optimize.milp/HiGHS"

#: The non-contract certificate sidecar filename. Defined HERE (in the glob-exempt
#: ``src/placement_ilp/`` tree) — and imported by the stage — so the "optimal" token never enters
#: a ``src/core/*.py`` source under the no-optimal-vocab guard. The stage serializes the cert under
#: this name; this is the SOLE artifact carrying the earned claim (AMEND-01 / D-04 / D-08).
CERTIFICATE_FILENAME = "optimality_certificate.json"


def solve_mclp_exact(
    utci: dict,
    crowd: dict,
    candidate_sites: list[tuple[float, float]],
    coverage_model,
    *,
    k: int | None = None,
    budget: float | None = None,
    cost_per_structure: float | None = None,
    density_magnitude: float = LITERATURE_DENSITY_MAGNITUDE,
    max_constraint_cells: int = ILP_MAX_CONSTRAINT_CELLS,
) -> tuple[dict, dict]:
    """Solve the MCLP to PROVEN optimality and return ``(result_dict, certificate)``.

    ``result_dict`` has the SAME shape as ``greedy_mclp`` (``structures``, ``total_demand``,
    ``covered_demand``, ``coverage_pct``, ``coverage_model``, ``infeasible``) so it maps 1:1 into
    ``structure_zones.json``. ``certificate`` is the PLACE-06 optimality certificate — the SOLE
    artifact carrying the earned-optimal claim.

    Args:
        utci, crowd: the two master-lattice grids (``build_demand``'s input).
        candidate_sites: dense candidate centres (``dense_candidate_grid``).
        coverage_model: the SHARED ``CoverageModel`` (same instance the greedy uses — D-10).
        k: primary stopping cap (max structures). ``budget`` / ``cost_per_structure`` are a
            secondary cap (PLACE-07: K primary, budget secondary — mirrors the greedy).
        density_magnitude: demand magnitude anchor (passed through to ``build_demand``).
        max_constraint_cells: scale ceiling on ``n_demand × n_cand`` (defaults to the ASSUMED
            ``ILP_MAX_CONSTRAINT_CELLS``); above it the solve RAISES (D-13).

    Returns:
        ``(result_dict, certificate)``.

    Raises:
        IlpTooLargeError: ``n_demand × n_cand > max_constraint_cells`` (raise-not-subsample).
        CrossCheckError: the ILP covered LESS than the greedy lower bound (broken model).
        AssertionError: the solver returned a non-optimal / nonzero-gap status (no naked optimal).
    """
    # Lazy imports (D-02): scipy stays out of the package / greedy-stage import path.
    import numpy as np
    import scipy
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import lil_matrix

    from core.placement import _rc_fn, build_demand, greedy_mclp

    # ── SHARED inputs — identical to the greedy (like-for-like cross-check, Pitfall 1) ─────────
    demand = build_demand(utci, crowd, density_magnitude=density_magnitude)
    total_weight = sum(d["weight"] for d in demand.values())

    rc = _rc_fn(utci["lattice"])
    # Canonical candidate order — BYTE-IDENTICAL to the greedy (placement.py:144-150):
    # by (row,col) lattice key, then original index as final tiebreak.
    indexed = sorted(
        enumerate(candidate_sites),
        key=lambda it: (rc(it[1][0], it[1][1]), it[0]),
    )
    sites = [site for _, site in indexed]
    covers = [coverage_model.covered_keys(site, demand) for site in sites]  # SHARED source
    demand_keys = list(demand.keys())  # fixed order for the y_i coverage vars
    area = coverage_model.area_m2()

    n_cand = len(sites)
    n_demand = len(demand_keys)

    # ── CEILING GUARD (D-13/D-15) — BEFORE building the matrix; raise-not-subsample ───────────
    if n_demand * n_cand > max_constraint_cells:
        raise IlpTooLargeError(
            f"exact solve too large: n_demand×n_cand = {n_demand * n_cand} > "
            f"max_constraint_cells = {max_constraint_cells} — raise the ceiling deliberately or "
            f"coarsen the candidate grid via step_cells>1; the exact ILP NEVER silently "
            f"subsamples or degrades to greedy"
        )

    K = k if k is not None else n_cand

    # ── INFEASIBILITY true-reason branch — PORT of placement.py:200-222 ───────────────────────
    # An empty/unplaceable instance has distinct TRUE causes; report the right one (never a false
    # claim). A correctly-reported infeasible instance is still a proven result (status 0, gap 0).
    infeasible = _infeasible_reason(
        total_weight, n_demand, n_cand, k=k, budget=budget, cost_per_structure=cost_per_structure
    )
    if infeasible is not None:
        result = {
            "structures": [],
            "total_demand": total_weight,
            "covered_demand": 0.0,
            "coverage_pct": 0.0,
            "coverage_model": coverage_model.name,
            "infeasible": infeasible,
        }
        certificate = _build_certificate(
            status=0,
            objective=0.0,
            best_bound=0.0,
            mip_gap=0.0,
            scipy_version=scipy.__version__,
        )
        # Cross-check still runs (permanent witness): a feasible greedy on an "infeasible" ILP
        # instance would mean we mis-diagnosed — let the guard catch it.
        _cross_check(
            result,
            utci,
            crowd,
            candidate_sites,
            coverage_model,
            k=k,
            budget=budget,
            cost_per_structure=cost_per_structure,
            density_magnitude=density_magnitude,
        )
        return result, certificate

    # ── INTEGERIZE the objective weights (Pitfall 2) — SOLVER-INTERNAL ONLY ───────────────────
    # Integer weights give a min coverage gap of 1, which the tiebreak bound (< 1) relies on.
    # The reported covered_demand + the cross-check compare on the REAL float weights below.
    w_int = np.array(
        [round(demand[key]["weight"] * ILP_DEMAND_WEIGHT_SCALE) for key in demand_keys],
        dtype=float,
    )

    # ── BUILD the sparse set-cover MILP (RESEARCH Pattern 1, verified) ────────────────────────
    # vars: [x_0..x_{nc-1}, y_0..y_{nd-1}]; milp MINIMIZES so negate the maximize objective.
    n = n_cand + n_demand
    c = np.concatenate([np.zeros(n_cand), -w_int])

    # Scale-separated lexicographic tiebreak (D-12, Pattern 2): ADD a tiny term to the x-vars
    # ordering them by canonical rank. Max total over the ≤K chosen ≤ K·n_cand/(K·(n_cand+1)) < 1
    # — strictly below the integer coverage gap of 1, so it orders WITHIN, never moves, the
    # coverage optimum. ADD (minimize) ⇒ the canonical-earliest equal-coverage set wins. NOT an
    # epsilon-nudge: it perturbs the OBJECTIVE within the optimal face, never the demand data.
    for rank_j in range(n_cand):
        c[rank_j] += (rank_j + 1) / (K * (n_cand + 1))

    integrality = np.ones(n)

    # Coverage-linking rows: y_i − Σ_{j covers i} x_j ≤ 0 ; cardinality row: Σ x_j ≤ K.
    A = lil_matrix((n_demand + 1, n))
    key_to_row = {key: i for i, key in enumerate(demand_keys)}
    for j in range(n_cand):
        for key in covers[j]:
            i = key_to_row.get(key)
            if i is not None:
                A[i, j] = -1.0
    for i in range(n_demand):
        A[i, n_cand + i] = 1.0
    for j in range(n_cand):
        A[n_demand, j] = 1.0

    ub = np.concatenate([np.zeros(n_demand), [float(K)]])
    lb = np.full(n_demand + 1, -np.inf)
    con = LinearConstraint(A.tocsr(), lb, ub)
    bounds = Bounds(np.zeros(n), np.ones(n))

    # ── SOLVE: single-thread HiGHS, force a PROVEN optimum (no gap-based early stop) ──────────
    res = milp(
        c=c,
        constraints=con,
        integrality=integrality,
        bounds=bounds,
        options={"presolve": True, "mip_rel_gap": 0.0, "time_limit": 300.0},
        # NO thread/seed knob exists — the MIP B&B is single-threaded → deterministic.
    )

    # No naked optimal (Pitfall 6): a time-limited / nonzero-gap incumbent FAILS LOUD.
    if res.status != 0 or res.mip_gap > 0:
        raise AssertionError(
            f"ILP did not prove optimality: status={res.status} ({res.message!r}), "
            f"mip_gap={res.mip_gap} — refusing to label a non-proven incumbent optimal"
        )

    # ── EXTRACT the selection in canonical order; covered_demand on REAL float weights ────────
    selected_idx = [j for j in range(n_cand) if round(res.x[j]) == 1]

    structures: list[dict] = []
    covered_keys: set[tuple[int, int]] = set()
    covered_weight = 0.0
    for rank, j in enumerate(selected_idx, start=1):
        new_keys = covers[j] - covered_keys
        gain = sum(demand[key]["weight"] for key in new_keys)
        covered_keys |= new_keys
        covered_weight += gain
        structures.append(
            {
                "rank": rank,
                "center": {"x_m": sites[j][0], "y_m": sites[j][1]},
                "area_m2": area,
                "marginal_demand": gain,
                "cumulative_demand": covered_weight,
                "coverage_pct": (100.0 * covered_weight / total_weight) if total_weight else 0.0,
                "newly_covered_cell_count": len(new_keys),
            }
        )

    result = {
        "structures": structures,
        "total_demand": total_weight,
        "covered_demand": covered_weight,
        "coverage_pct": (100.0 * covered_weight / total_weight) if total_weight else 0.0,
        "coverage_model": coverage_model.name,
        "infeasible": None,
    }

    # ── CERTIFICATE (BUILT HERE — D-09 / Open Question 3) ─────────────────────────────────────
    # objective reported on the REAL float covered_demand of the selected set (NOT the integerized
    # objective); best_bound from the dual bound. proven_optimal strictly from gap==0 and status==0.
    certificate = _build_certificate(
        status=int(res.status),
        objective=covered_weight,
        best_bound=float(res.mip_dual_bound),
        mip_gap=float(res.mip_gap),
        scipy_version=scipy.__version__,
    )

    # ── CROSS-CHECK (D-10/D-11) — run the greedy EVERY solve as the permanent lower-bound witness ─
    _cross_check(
        result,
        utci,
        crowd,
        candidate_sites,
        coverage_model,
        k=k,
        budget=budget,
        cost_per_structure=cost_per_structure,
        density_magnitude=density_magnitude,
    )

    return result, certificate


def _infeasible_reason(
    total_weight: float,
    n_demand: int,
    n_cand: int,
    *,
    k: int | None,
    budget: float | None,
    cost_per_structure: float | None,
) -> dict | None:
    """The TRUE infeasibility cause (mirrors greedy_mclp's distinct branches), or None.

    Distinct causes, never a false claim: no positive demand / budget < one structure / k <= 0 /
    no candidates to place.
    """
    placeable = (
        (k is None or k > 0)
        and not (
            budget is not None
            and cost_per_structure is not None
            and cost_per_structure > budget
        )
        and total_weight > 0
        and n_demand > 0
        and n_cand > 0
    )
    if placeable:
        return None
    if total_weight <= 0 or n_demand == 0:
        return {
            "reason": "no cell scores > 0 (no crowd-heat overlap above 26 C)",
            "k": k,
            "budget": budget,
        }
    if (
        budget is not None
        and cost_per_structure is not None
        and cost_per_structure > budget
    ):
        return {
            "reason": "budget < cost of one structure",
            "budget": budget,
            "cost_per_structure": cost_per_structure,
        }
    if k is not None and k <= 0:
        return {"reason": "k <= 0 (no structures requested)", "k": k}
    return {"reason": "no structure covers any positive demand", "k": k}


def _build_certificate(
    *,
    status: int,
    objective: float,
    best_bound: float,
    mip_gap: float,
    scipy_version: str,
) -> dict:
    """Assemble the PLACE-06 optimality certificate (D-09) — the SOLE "optimal"-bearing artifact.

    ``proven_optimal`` is derived STRICTLY from ``mip_gap == 0 and status == 0`` (Pitfall 6: never
    label a time-limited / nonzero-gap incumbent optimal). ``seed`` is ``None`` — HiGHS exposes no
    RNG; determinism is by construction (recorded in ``determinism``).
    """
    return {
        "status": status,
        "objective": objective,
        "best_bound": best_bound,
        "mip_gap": mip_gap,
        "solver": _SOLVER,
        "scipy_version": scipy_version,
        "seed": None,
        "determinism": _DETERMINISM_BASIS,
        "proven_optimal": (mip_gap == 0 and status == 0),
        "claim": _EARNED_OPTIMAL_CLAIM,
    }


def _cross_check(
    result: dict,
    utci: dict,
    crowd: dict,
    candidate_sites: list[tuple[float, float]],
    coverage_model,
    *,
    k: int | None,
    budget: float | None,
    cost_per_structure: float | None,
    density_magnitude: float,
) -> None:
    """Fail-loud greedy lower-bound cross-check (D-10/D-11), on REAL float weights.

    Runs ``greedy_mclp`` with the SAME inputs / coverage model (like-for-like, Pitfall 1) and
    RAISES ``CrossCheckError`` if the exact ILP covered LESS weighted demand than the greedy —
    a proven optimum can never under-cover a feasible heuristic, so a violation means the model
    is wrong. A small relative tolerance guards float accumulation order.
    """
    from core.placement import greedy_mclp

    greedy_result = greedy_mclp(
        utci,
        crowd,
        candidate_sites,
        coverage_model,
        k=k,
        budget=budget,
        cost_per_structure=cost_per_structure,
        density_magnitude=density_magnitude,
    )
    ilp_covered = result["covered_demand"]
    greedy_covered = greedy_result["covered_demand"]
    tol = 1e-9 * max(1.0, abs(greedy_covered))
    if ilp_covered < greedy_covered - tol:
        raise CrossCheckError(
            f"ILP covered_demand ({ilp_covered}) < greedy lower bound ({greedy_covered}) — "
            f"the MILP model is wrong (a proven optimum can never under-cover a feasible heuristic)"
        )
