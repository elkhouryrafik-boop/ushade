"""Unit tests for the greedy submodular MCLP placer (``core.placement``) + coverage models.

Hand-computable on the SAME tiny 3×3 lattice as ``conftest_core`` (so the demand weights are the
known ``score = density·max(utci−26,0)`` values, here with the identity density magnitude 1.0).

The six positive-demand cells and their weights (see conftest_core docstring):

    (row,col)  centre(x,y)   weight
    (0,2)      (15, 3)        8.0
    (1,1)      ( 9, 9)        8.0
    (1,2)      (15, 9)        6.0
    (2,0)      ( 3,15)        6.0
    (2,2)      (15,15)        5.0
    (1,0)      ( 3, 9)        3.0      total = 36.0

With ``RadiusCoverage(6.0)`` a site at a cell centre covers itself + the four ORTHOGONAL
neighbours (distance 6 ≤ 6) but NOT diagonals (distance 8.49 > 6). Hand-walking the greedy:

  Round 1 — site (15,9) covers {(15,9)=6, (15,3)=8, (9,9)=8, (15,15)=5} → marginal 27 (the max).
  Round 2 — remaining demand {(3,15)=6, (3,9)=3}. Sites (3,9) and (3,15) BOTH cover both (each
            covers itself + its orthogonal neighbour) → marginal 9 tie; (row,col) tiebreak picks
            (3,9) [rc (1,0)] over (3,15) [rc (2,0)]. → all 36 covered, 100 %.
  Round 3 — best marginal gain is 0 → STOP (honesty stop, never place a zero-gain structure).
"""

from __future__ import annotations

# conftest_core is imported EXPLICITLY (pytest only auto-loads conftest.py).
from conftest_core import (  # noqa: F401
    COST_PER_CELL,
    tiny_score_inputs,
)

import pytest

from core.coverage_models import (
    OffsetShadowCoverage,
    RadiusCoverage,
    shadow_offset_from_sun,
    square_canopy_ring,
)
from core.placement import build_demand, dense_candidate_grid, greedy_mclp


# ── PLACE-02: the demand field ──────────────────────────────────────────────
def test_build_demand_drops_zero_weight_cells(tiny_score_inputs):
    """Demand = the SIX positive crowd×heat cells only; the 3 zero cells are dropped (CORE-06)."""
    demand = build_demand(tiny_score_inputs["utci"], tiny_score_inputs["crowd"])
    assert set(demand) == {(0, 2), (1, 1), (1, 2), (2, 0), (2, 2), (1, 0)}
    assert demand[(0, 2)]["weight"] == 8.0
    assert demand[(1, 0)]["weight"] == 3.0
    assert sum(d["weight"] for d in demand.values()) == 36.0
    # Sub-26, zero-density, and ==26 cells never enter the field.
    assert (0, 0) not in demand and (0, 1) not in demand and (2, 1) not in demand


def test_density_magnitude_rescales_but_preserves_ranking(tiny_score_inputs):
    """A positive global magnitude scales weights linearly and leaves the SELECTION unchanged."""
    u, c = tiny_score_inputs["utci"], tiny_score_inputs["crowd"]
    sites = dense_candidate_grid(u["lattice"])
    base = greedy_mclp(u, c, sites, RadiusCoverage(6.0), k=2)
    scaled = greedy_mclp(u, c, sites, RadiusCoverage(6.0), k=2, density_magnitude=3.0)
    assert [s["center"] for s in base["structures"]] == [s["center"] for s in scaled["structures"]]
    assert scaled["total_demand"] == pytest.approx(3.0 * base["total_demand"])


# ── PLACE-01: the greedy selection (hand-verified) ──────────────────────────
def test_greedy_first_pick_and_full_coverage(tiny_score_inputs):
    """Greedy picks (15,9) first (marginal 27), then (3,9) (marginal 9) → 2 structures, 100 %."""
    u, c = tiny_score_inputs["utci"], tiny_score_inputs["crowd"]
    sites = dense_candidate_grid(u["lattice"])
    out = greedy_mclp(u, c, sites, RadiusCoverage(6.0), k=5)

    assert len(out["structures"]) == 2  # gain==0 stop fires before k=5 is reached
    first, second = out["structures"]
    assert first["center"] == {"x_m": 15.0, "y_m": 9.0}
    assert first["marginal_demand"] == 27.0
    assert first["rank"] == 1
    assert second["center"] == {"x_m": 3.0, "y_m": 9.0}
    assert second["marginal_demand"] == 9.0
    assert out["covered_demand"] == 36.0
    assert out["coverage_pct"] == pytest.approx(100.0)
    assert out["infeasible"] is None
    assert out["coverage_model"] == "radius"


def test_greedy_is_order_invariant(tiny_score_inputs):
    """Shuffling candidate_sites yields byte-identical structure selection (deterministic)."""
    u, c = tiny_score_inputs["utci"], tiny_score_inputs["crowd"]
    sites = dense_candidate_grid(u["lattice"])
    a = greedy_mclp(u, c, sites, RadiusCoverage(6.0), k=5)
    b = greedy_mclp(u, c, list(reversed(sites)), RadiusCoverage(6.0), k=5)
    assert a["structures"] == b["structures"]


def test_k_caps_structure_count(tiny_score_inputs):
    """k=1 stops after the single best structure (75 % coverage = 27/36)."""
    u, c = tiny_score_inputs["utci"], tiny_score_inputs["crowd"]
    sites = dense_candidate_grid(u["lattice"])
    out = greedy_mclp(u, c, sites, RadiusCoverage(6.0), k=1)
    assert len(out["structures"]) == 1
    assert out["coverage_pct"] == pytest.approx(75.0)


# ── PLACE-04: stopping rules ────────────────────────────────────────────────
def test_budget_secondary_cap(tiny_score_inputs):
    """budget=1 structure-cost caps the set to one even when k is larger."""
    u, c = tiny_score_inputs["utci"], tiny_score_inputs["crowd"]
    sites = dense_candidate_grid(u["lattice"])
    out = greedy_mclp(
        u, c, sites, RadiusCoverage(6.0), k=5, budget=900.0, cost_per_structure=900.0
    )
    assert len(out["structures"]) == 1


def test_infeasible_budget_below_one_structure(tiny_score_inputs):
    """budget < one structure → no structures, infeasibility report names the budget cause."""
    u, c = tiny_score_inputs["utci"], tiny_score_inputs["crowd"]
    sites = dense_candidate_grid(u["lattice"])
    out = greedy_mclp(
        u, c, sites, RadiusCoverage(6.0), k=5, budget=450.0, cost_per_structure=900.0
    )
    assert out["structures"] == []
    assert out["infeasible"]["reason"].startswith("budget")


def test_infeasible_no_demand(tiny_score_inputs):
    """All-cool grid → empty demand → infeasibility names the no-overlap cause, not budget."""
    u = tiny_score_inputs["utci"]
    cool = {**u, "cells": [{**cell, "utci_c": 20.0} for cell in u["cells"]]}
    sites = dense_candidate_grid(u["lattice"])
    out = greedy_mclp(cool, tiny_score_inputs["crowd"], sites, RadiusCoverage(6.0), k=5)
    assert out["structures"] == []
    assert "no crowd-heat overlap" in out["infeasible"]["reason"]


# ── PLACE-02: the pluggable coverage models ─────────────────────────────────
def test_offset_shadow_zero_offset_covers_under_canopy(tiny_score_inputs):
    """A high-noon (zero-offset) 6 m-half-span canopy at (15,9) shades the cells under it."""
    u, c = tiny_score_inputs["utci"], tiny_score_inputs["crowd"]
    model = OffsetShadowCoverage(square_canopy_ring(6.0), sun_offset_m=(0.0, 0.0))
    out = greedy_mclp(u, c, dense_candidate_grid(u["lattice"]), model, k=1)
    assert out["structures"][0]["area_m2"] == pytest.approx(144.0)  # (2*6)^2
    assert out["coverage_model"] == "offset_shadow"


def test_offset_shadow_displaces_coverage(tiny_score_inputs):
    """A low sun offsets the shadow east → covered cells differ from the zero-offset case."""
    u, c = tiny_score_inputs["utci"], tiny_score_inputs["crowd"]
    sites = dense_candidate_grid(u["lattice"])
    noon = OffsetShadowCoverage(square_canopy_ring(3.0), sun_offset_m=(0.0, 0.0))
    low = OffsetShadowCoverage(square_canopy_ring(3.0), sun_offset_m=(6.0, 0.0))
    a = greedy_mclp(u, c, sites, noon, k=2)
    b = greedy_mclp(u, c, sites, low, k=2)
    assert [s["center"] for s in a["structures"]] != [s["center"] for s in b["structures"]] \
        or a["covered_demand"] != b["covered_demand"]


def test_shadow_offset_from_sun_geometry():
    """Offset points away from the sun and lengthens as the sun drops; below-horizon raises."""
    # Sun low in the east (+x), 45° altitude-ish: offset goes west (−x), length = height.
    dx, dy = shadow_offset_from_sun((1.0, 0.0, 1.0), canopy_height_m=4.0)
    assert dx == pytest.approx(-4.0) and dy == pytest.approx(0.0)
    with pytest.raises(ValueError):
        shadow_offset_from_sun((1.0, 0.0, 0.0), canopy_height_m=4.0)  # sun on horizon
