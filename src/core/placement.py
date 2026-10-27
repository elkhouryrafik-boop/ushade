"""Greedy submodular MCLP placer — recommends WHERE to put discrete shade structures (PLACE-01).

The post-pivot replacement for ``core.score.score_and_allocate``. The old greedy funded *cells*
(confetti, useless to a human architect); this answers the architect's real question — *"where do
I place K buildable structures to cover the most hot×busy demand?"* — the **Maximal Covering
Location Problem (MCLP)**. This module is the **submodular-greedy** solver of it: deterministic,
solver-free, with the classic (1 − 1/e) ≈ 63 % worst-case coverage bound. It is BOTH a shippable
baseline AND the honesty cross-check for the later exact ILP (if the ILP's covered demand is not
≥ this greedy's, something is wrong). It makes NO best-coverage claim — the greedy is a bounded
heuristic; the exact best-coverage selection (with its certificate) is the ILP's job, not this
module's (CORE-05 honesty lock — same discipline as ``score.py``).

Pure transform — no I/O, no manifest, no network, no randomness (mirrors ``score.py`` discipline).
Engine-agnostic: it does NOT wait on JuPedSim; it consumes any lattice-snapped ``crowd_grid``.

Demand (PLACE-02): per cell ``weight = crowd_density · LITERATURE_DENSITY_MAGNITUDE · max(utci−26,0)``
— the same crowd×heat coupling as the old greedy, scaled by the literature density anchor. The
``max(…,0)`` clamp (CORE-06) means a sub-26 / zero-density cell has weight 0 and is dropped from the
demand field entirely, so a structure is NEVER credited for shading a cell that needs no shade.

Coverage is supplied as a pluggable ``coverage_model`` (``core.coverage_models``) — the placer calls
``covered_keys`` only and never hard-codes the shadow geometry. The real model is the sun-offset
projected shadow; radius-R is the swappable baseline.

Output (PLACE-05) = **ranked structure zones**: ``{rank, center, area_m2, marginal_demand,
cumulative_demand, coverage_pct, newly_covered_cell_count}`` — center + size + priority + coverage,
NOT footprint polygons (drawing the footprint is a design act the human architect owns).
"""

from __future__ import annotations

from core.constants import COMFORT_THRESHOLD_C, LITERATURE_DENSITY_MAGNITUDE


def _rc_fn(lattice: dict):
    """A (row, col) lattice-key function — IDENTICAL rounding to ``score.py`` (the join key).

    Centres sit at ``origin + (idx + 0.5)·cell``; subtract the half-cell BEFORE rounding so an
    exact .5 does not banker's-round to even and collide adjacent columns.
    """
    ox = lattice["origin_x_m"]
    oy = lattice["origin_y_m"]
    cell = lattice["cell_size_m"]

    def rc(x_m: float, y_m: float) -> tuple[int, int]:
        return (round((y_m - oy) / cell - 0.5), round((x_m - ox) / cell - 0.5))

    return rc


def build_demand(
    utci: dict,
    crowd: dict,
    *,
    density_magnitude: float = LITERATURE_DENSITY_MAGNITUDE,
) -> dict:
    """Couple the two grids into the positive-weight demand field (PLACE-02).

    JOIN on the ``(row, col)`` lattice key (never zip — the grids have different cell counts).
    Returns ``{(row,col): {"x_m", "y_m", "weight"}}`` for cells with ``weight > 0`` ONLY; a
    sub-threshold or zero-density cell is dropped (CORE-06 — never a candidate-coverage target).
    """
    rc = _rc_fn(utci["lattice"])

    dens = {
        rc(c["x_m"], c["y_m"]): c["crowd_density_agents_per_cell"] for c in crowd["cells"]
    }
    if len(dens) != len(crowd["cells"]):
        raise AssertionError("duplicate (row,col) keys in crowd grid — lattice-snapped input violated")

    demand: dict[tuple[int, int], dict] = {}
    for c in utci["cells"]:
        key = rc(c["x_m"], c["y_m"])
        excess = max(c["utci_c"] - COMFORT_THRESHOLD_C, 0.0)  # CORE-06 clamp
        weight = dens.get(key, 0.0) * density_magnitude * excess
        if weight > 0:
            demand[key] = {"x_m": c["x_m"], "y_m": c["y_m"], "weight": weight}
    return demand


def dense_candidate_grid(lattice: dict, *, step_cells: int = 1) -> list[tuple[float, float]]:
    """A DENSE candidate-site grid = lattice cell centres, optionally subsampled by ``step_cells``.

    A dense candidate set is deliberate: a sparse set (e.g. DBSCAN blobs) neuters the solver
    (the optimum can sit between blobs). Use ``step_cells=1`` for full density; >1 only to bound
    compute on a large lattice. Sites come back in a fixed (row-major) order.
    """
    if step_cells < 1:
        raise ValueError("step_cells must be >= 1")
    ox = lattice["origin_x_m"]
    oy = lattice["origin_y_m"]
    cell = lattice["cell_size_m"]
    rows = lattice["rows"]
    cols = lattice["cols"]
    return [
        (ox + (col + 0.5) * cell, oy + (row + 0.5) * cell)
        for row in range(0, rows, step_cells)
        for col in range(0, cols, step_cells)
    ]


def greedy_mclp(
    utci: dict,
    crowd: dict,
    candidate_sites: list[tuple[float, float]],
    coverage_model,
    *,
    k: int | None = None,
    budget: float | None = None,
    cost_per_structure: float | None = None,
    density_magnitude: float = LITERATURE_DENSITY_MAGNITUDE,
) -> dict:
    """Greedily select structure sites maximising covered weighted demand (PLACE-01).

    Stopping rule (PLACE-04): structures are added until the FIRST of —
      * ``k`` structures placed (the primary cap: "I can build N canopies"), OR
      * the next structure is unaffordable (``budget`` + ``cost_per_structure`` secondary cap), OR
      * the best remaining marginal gain is 0 (no uncovered demand left — diminishing-returns /
        honesty stop: a zero-gain structure is NEVER placed, mirroring CORE-06's no-zero-spend).
    At least one of ``k`` / ``budget`` should be given; with neither, the gain==0 stop bounds it.

    The greedy step is submodular max-coverage: each round, pick the unused candidate whose
    NEWLY-covered demand weight is largest. Ties break deterministically by the candidate's
    ``(row, col)`` lattice key, then its index — a total order, so the output is byte-stable
    regardless of ``candidate_sites`` ordering (the determinism that backs the rerun proof).

    Returns ``{structures, total_demand, covered_demand, coverage_pct, coverage_model,
    infeasible}``:

    * ``structures`` — ranked zones in selection order, each
      ``{rank, center{x_m,y_m}, area_m2, marginal_demand, cumulative_demand, coverage_pct,
      newly_covered_cell_count}``.
    * ``total_demand`` — Σ weight over the whole demand field (the denominator).
    * ``covered_demand`` / ``coverage_pct`` — Σ weight covered by the chosen set / its %.
    * ``infeasible`` — ``None`` if ≥1 structure placed, else a report dict (true reason:
      budget-below-one-structure vs no-positive-demand — never a false claim, mirrors ``score.py``).
    """
    demand = build_demand(utci, crowd, density_magnitude=density_magnitude)
    total_weight = sum(d["weight"] for d in demand.values())

    rc = _rc_fn(utci["lattice"])
    # Deterministic candidate order: by (row,col) lattice key. Index kept as final tiebreak so two
    # sites snapping to the SAME key (sub-cell candidates) still order stably.
    indexed = sorted(
        enumerate(candidate_sites),
        key=lambda it: (rc(it[1][0], it[1][1]), it[0]),
    )

    # Precompute each candidate's covered demand keys ONCE (coverage is site-static).
    coverage = [(i, site, coverage_model.covered_keys(site, demand)) for i, site in indexed]
    area = coverage_model.area_m2()

    covered: set[tuple[int, int]] = set()
    covered_weight = 0.0
    used: set[int] = set()
    structures: list[dict] = []

    while True:
        if k is not None and len(structures) >= k:
            break
        if (
            budget is not None
            and cost_per_structure is not None
            and (len(structures) + 1) * cost_per_structure > budget
        ):
            break

        best = None  # (-gain, site_row, site_col, idx, new_keys, site)
        for i, site, keys in coverage:
            if i in used:
                continue
            new_keys = keys - covered
            gain = sum(demand[key]["weight"] for key in new_keys)
            r, c = rc(site[0], site[1])
            cand = (-gain, r, c, i)
            if best is None or cand < best[0]:
                best = (cand, gain, i, new_keys, site)

        if best is None:
            break  # no candidates left
        _, gain, idx, new_keys, site = best
        if gain <= 0:
            break  # honesty stop: never place a zero-gain structure

        used.add(idx)
        covered |= new_keys
        covered_weight += gain
        structures.append(
            {
                "rank": len(structures) + 1,
                "center": {"x_m": site[0], "y_m": site[1]},
                "area_m2": area,
                "marginal_demand": gain,
                "cumulative_demand": covered_weight,
                "coverage_pct": (100.0 * covered_weight / total_weight) if total_weight else 0.0,
                "newly_covered_cell_count": len(new_keys),
            }
        )

    # Empty result has TWO distinct causes — report the TRUE one (mirrors score.py infeasibility).
    infeasible = None
    if not structures:
        if total_weight <= 0:
            infeasible = {
                "reason": "no cell scores > 0 (no crowd-heat overlap above 26 C)",
                "k": k,
                "budget": budget,
            }
        elif (
            budget is not None
            and cost_per_structure is not None
            and cost_per_structure > budget
        ):
            infeasible = {
                "reason": "budget < cost of one structure",
                "budget": budget,
                "cost_per_structure": cost_per_structure,
            }
        elif k is not None and k <= 0:
            infeasible = {"reason": "k <= 0 (no structures requested)", "k": k}
        else:
            infeasible = {"reason": "no structure covers any positive demand", "k": k}

    return {
        "structures": structures,
        "total_demand": total_weight,
        "covered_demand": covered_weight,
        "coverage_pct": (100.0 * covered_weight / total_weight) if total_weight else 0.0,
        "coverage_model": coverage_model.name,
        "infeasible": infeasible,
    }
