"""RED Nyquist scaffold for the Phase-5 material selection core (MAT-01..06, D-06/12/14).

EXPECTED TO FAIL RED at collection: ``selection.selection`` does NOT exist yet — Plan 03
wires the real implementation. This scaffold locks the selection contract (the four
load-bearing honesty assertions + MAT-01..06 + the recovery-reporting fields) every later
plan is verified against; when Plan 03 ships ``src/selection/*`` these turn GREEN with NO
test edits (mirror ``test_climate.py`` designed-RED on ``climate.climate``).

The four load-bearing assertions (05-VALIDATION §):
  1. (1-tau) DIRECTION (MAT-04)        — test_tau_direction
  2. tau ISOLATION (cost/carbon)        — test_tau_not_in_cost_or_carbon
  3. availability GATES, never re-ranks — test_availability_gates_not_reranks
  4. never-silent-drop conservation     — (lives in test_inventory.py)

NOTE (Plan 03): the ASSUMED entrypoints —
  ``select_material(candidates, *, theme=None, availability=None) -> material_selection dict``
     (a dict that validates against contracts/material_selection.schema.json 1.1.0),
  ``cooling_estimate(geometry, tau) -> float``  (the (1-tau) correction, tau ONLY here),
  ``load_materials() -> list[dict]``            (the frozen 10 from data/materials.json).
If Plan 03 picks different names/signatures, update the imports here in lock-step.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# RED: these imports fail until Plan 03 ships src/selection/*. The whole module fails at
# collection — correct for a Wave 0 scaffold (05-VALIDATION §Wave 0 Requirements).
from selection.selection import (  # noqa: E402
    select_material,
    cooling_estimate,
    load_materials,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_MATERIALS_PATH = _REPO_ROOT / "data" / "materials.json"

# Frozen tau values (verbatim from data/materials.json, also guarded in conftest):
TAU_TARP = 0.15   # membr-recycled-pe-tarp (low tau -> MORE cooling)
TAU_HDPE = 0.40   # membr-hdpe-shade-net   (high tau -> LESS cooling)


def _frozen_materials() -> list[dict]:
    return json.loads(_MATERIALS_PATH.read_text(encoding="utf-8"))["materials"]


# --------------------------------------------------------------------------- #
# MAT-01 — soft-filter by parsed theme over the frozen 10
# --------------------------------------------------------------------------- #
def test_theme_soft_filter():
    """MAT-01: candidates are soft-filtered by the parsed theme; a maritime brief keeps the
    maritime-tagged membranes and drops non-matching ones (membrane class only)."""
    candidates = [m for m in _frozen_materials() if m["type"] == "MEMBR"]
    result = select_material(candidates, theme="maritime")
    selected = next(m for m in _frozen_materials() if m["id"] == result["selected_id"])
    assert "maritime" in selected["theme"], (
        "a maritime soft-filter must select a maritime-tagged membrane"
    )


# --------------------------------------------------------------------------- #
# MAT-02 — transport carbon 2*Dist*Mass*factor, select the minimum (index 0)
# --------------------------------------------------------------------------- #
def test_transport_carbon_min_selected():
    """MAT-02: with availability open, the selected membrane is the global
    transport-carbon minimum (2 * Distance_km * Mass_tonnes * factor), index 0 after sort."""
    candidates = [m for m in _frozen_materials() if m["type"] == "MEMBR"]

    def carbon(m: dict) -> float:
        lca = m["lca_profile"]
        mass_t = m["dimensions"]["unit_mass_kg"] / 1000.0
        return 2 * lca["distance_km"] * mass_t * lca["transport_mode_factor"]

    expected_min_id = min(candidates, key=carbon)["id"]
    result = select_material(candidates)
    assert result["selected_id"] == expected_min_id, (
        "selection must be the transport-carbon minimum (the sort-key index 0)"
    )
    assert result["selection_basis"] == "transport_carbon_min"


# --------------------------------------------------------------------------- #
# MAT-03 — financial roll-up qty x cost_per_unit into the locked budget
# --------------------------------------------------------------------------- #
def test_cost_rollup():
    """MAT-03: cost_total_eur is quantity x cost_per_unit for the selected material."""
    candidates = [m for m in _frozen_materials() if m["type"] == "MEMBR"]
    qty = 100.0
    result = select_material(candidates, quantity=qty)
    selected = next(m for m in _frozen_materials() if m["id"] == result["selected_id"])
    assert result["cost_total_eur"] == pytest.approx(qty * selected["cost_per_unit"]), (
        "cost_total_eur must be quantity x cost_per_unit"
    )


# --------------------------------------------------------------------------- #
# LOAD-BEARING #1 — (1-tau) cooling DIRECTION (MAT-04)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "tau_low,tau_high",
    [(TAU_TARP, TAU_HDPE)],
)
def test_tau_direction(tau_low, tau_high):
    """LOAD-BEARING #1 (MAT-04): over IDENTICAL geometry, a higher tau yields LESS cooling,
    and cooling == geometry*(1-tau) EXACTLY. A sign flip (geometry*tau) would silently
    overstate cooling for loose nets — the honesty-critical assertion."""
    geometry = 100.0
    cool_low = cooling_estimate(geometry, tau_low)    # tarp 0.15 -> more cooling
    cool_high = cooling_estimate(geometry, tau_high)  # hdpe 0.40 -> less cooling
    assert cool_high < cool_low, "higher tau must yield LESS cooling (direction)"
    assert cool_low == pytest.approx(geometry * (1 - tau_low)), (
        "cooling must equal geometry*(1-tau) exactly (no sign flip)"
    )
    assert cool_high == pytest.approx(geometry * (1 - tau_high))


# --------------------------------------------------------------------------- #
# LOAD-BEARING #2 — tau ISOLATION (never touches cost or carbon)
# --------------------------------------------------------------------------- #
def test_tau_not_in_cost_or_carbon():
    """LOAD-BEARING #2: cost_total_eur and transport_carbon_kgco2e are byte-identical
    whether the membrane's tau is 0.15 or 0.40 for the SAME selection — tau touches the
    cooling estimate ONLY, never cost or carbon (Golden Rule: carbon stays material-only)."""
    candidates = [m for m in _frozen_materials() if m["type"] == "MEMBR"]
    # Select the same material twice; the artifact's cost+carbon must not depend on tau.
    result = select_material(candidates)
    selected_id = result["selected_id"]
    same = [m for m in candidates if m["id"] == selected_id]
    again = select_material(same)
    assert again["cost_total_eur"] == result["cost_total_eur"], (
        "cost must be independent of tau"
    )
    assert again["transport_carbon_kgco2e"] == result["transport_carbon_kgco2e"], (
        "transport carbon must be independent of tau"
    )


# --------------------------------------------------------------------------- #
# MAT-05 — carbon ASSUMED-boundary; transport_mode_factor now GROUNDED (DEFRA 2024)
# --------------------------------------------------------------------------- #
def test_carbon_assumed_labelled():
    """MAT-05: the carbon comparison stays ASSUMED-boundary (recycled cut-off,
    manufacturing=0 — that boundary choice is still an assumption), but the
    transport_mode_factor is now the GROUNDED DEFRA/DESNZ 2024 'All HGVs' figure
    (0.09752 kgCO2e/tonne-km) — the 0.10 placeholder has been retired (2026-06-22)."""
    candidates = [m for m in _frozen_materials() if m["type"] == "MEMBR"]
    result = select_material(candidates)
    tent = result.get("tent_comparison", {})
    assert tent.get("label") == "ASSUMED", "the carbon comparison must be ASSUMED-labelled"
    # The cited DEFRA 2024 factor (0.09752) is what the artifact now carries.
    assert all(
        abs(m["lca_profile"]["transport_mode_factor"] - 0.09752) < 1e-9 for m in candidates
    ), "every candidate must carry the GROUNDED DEFRA 2024 factor 0.09752"


# --------------------------------------------------------------------------- #
# MAT-06 — catalog UNFROZEN 2026-06-22 (CLAUDE.md owner directive). The frozen-10
# cap is retired; the invariants that still hold are: _meta count matches the array,
# the STRUCT/MEMBR split in _meta is accurate, ids are unique, and every archetype
# has a matching deterministic classifier rule (the scrape→archetype binding contract).
# --------------------------------------------------------------------------- #
def test_materials_catalog_invariants():
    """The catalog may grow (UNFROZEN), but it must stay self-consistent and every
    archetype must be reachable by exactly one deterministic classifier rule."""
    import json
    from pathlib import Path

    from inventory.classifier import _RULES

    materials = load_materials()
    doc = json.loads(
        (Path(__file__).resolve().parent.parent / "data" / "materials.json").read_text(
            encoding="utf-8"
        )
    )
    meta = doc["_meta"]
    struct = [m for m in materials if m["type"] == "STRUCT"]
    membr = [m for m in materials if m["type"] == "MEMBR"]

    assert meta["count"] == len(materials), "_meta.count must match the materials array"
    assert meta["structural"] == len(struct), "_meta.structural must match STRUCT entries"
    assert meta["membrane"] == len(membr), "_meta.membrane must match MEMBR entries"

    ids = [m["id"] for m in materials]
    assert len(ids) == len(set(ids)), "material ids must be unique"

    # Every archetype must have a matching classifier rule (so a scrape can bind to it).
    rule_ids = {r["material_id"] for r in _RULES}
    missing = set(ids) - rule_ids
    assert not missing, f"archetypes with no classifier rule: {sorted(missing)}"


# --------------------------------------------------------------------------- #
# Phase-5 evaluation (2026-06-22 CRISP-DM): every spec field is provenance-tiered,
# transmissivity is physically valid, and the carbon factor is the cited DEFRA value.
# --------------------------------------------------------------------------- #
def test_specs_provenance_and_validity():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    materials = load_materials()
    ledger = json.loads((root / "data" / "materials_provenance.json").read_text(encoding="utf-8"))
    fields = ledger["fields"]
    tiers = {"GROUNDED", "DERIVED", "DECLARED"}

    for m in materials:
        mid = m["id"]
        assert mid in fields, f"no provenance ledger entry for {mid}"
        for fname, rec in fields[mid].items():
            assert rec["tier"] in tiers, f"{mid}.{fname} bad tier {rec['tier']!r}"
            assert rec.get("source"), f"{mid}.{fname} missing source"
        # transmissivity physically valid (0..1) or null for opaque structural
        t = m["solar_transmissivity"]
        assert t is None or (0.0 <= t <= 1.0), f"{mid} transmissivity {t} out of [0,1]"
        # transport factor is the cited DEFRA 2024 figure (placeholder retired)
        assert abs(m["lca_profile"]["transport_mode_factor"] - 0.09752) < 1e-9, (
            f"{mid} must carry the DEFRA 2024 transport factor"
        )


# --------------------------------------------------------------------------- #
# LOAD-BEARING #3 — availability GATES, never re-ranks by price (D-06)
# --------------------------------------------------------------------------- #
def test_availability_gates_not_reranks():
    """LOAD-BEARING #3 (D-06): when the cheapest AVAILABLE material has HIGHER transport
    carbon than an UNAVAILABLE one, the selection is the lowest-carbon AVAILABLE material —
    NOT the cheapest, NOT the global carbon minimum. Availability filters; it never re-ranks
    by price/availability — the sort key stays transport-carbon-only."""
    candidates = [m for m in _frozen_materials() if m["type"] == "MEMBR"]

    def carbon(m: dict) -> float:
        lca = m["lca_profile"]
        mass_t = m["dimensions"]["unit_mass_kg"] / 1000.0
        return 2 * lca["distance_km"] * mass_t * lca["transport_mode_factor"]

    by_carbon = sorted(candidates, key=carbon)
    global_min = by_carbon[0]
    # Mark the global carbon-minimum UNAVAILABLE -> the gate must fall through to the
    # next-lowest-carbon AVAILABLE candidate, not the cheapest.
    availability = {m["id"]: "available" for m in candidates}
    availability[global_min["id"]] = "out_of_stock"
    expected = by_carbon[1]["id"]  # lowest-carbon AVAILABLE

    result = select_material(candidates, availability=availability)
    assert result["selected_id"] == expected, (
        "availability must FILTER then min-by-carbon — never re-rank by price/availability"
    )
    assert result["selected_id"] != global_min["id"], (
        "the unavailable global-min must not be selected"
    )
    assert result["availability_gated"] is True


# --------------------------------------------------------------------------- #
# D-06 — unavailable min -> next-lowest-carbon -> all unavailable -> infeasible
# --------------------------------------------------------------------------- #
def test_gate_fallback_then_infeasible():
    """D-06: when EVERY candidate is unavailable, the selection emits infeasible:true
    (an infeasibility report) rather than silently picking an unavailable material."""
    candidates = [m for m in _frozen_materials() if m["type"] == "MEMBR"]
    availability = {m["id"]: "out_of_stock" for m in candidates}
    result = select_material(candidates, availability=availability)
    assert result.get("infeasible") is True, (
        "all-unavailable must yield infeasible:true, never an unavailable pick"
    )
    # BL-01: the infeasible dict must use a NON-EMPTY sentinel for selected_id so it
    # satisfies the contract's minLength:1 and persists honestly (never an empty string
    # that fails validate() and gets swallowed by the stage fail-safe).
    assert result["selected_id"] == "INFEASIBLE", (
        "infeasible selected_id must be the non-empty sentinel, never an empty string"
    )
    from validate.validate import validate  # noqa: PLC0415

    validate(result, "material_selection")  # must validate clean, not raise


# --------------------------------------------------------------------------- #
# BL-01 — an all-unavailable run WRITES a contract-valid infeasible artifact
#         through run_selection_stage (not a crash, not a swallowed fail-safe).
# --------------------------------------------------------------------------- #
def test_infeasible_stage_writes_contract_valid_artifact(tmp_path):
    """BL-01: a stage run where every candidate is out_of_stock must persist a
    contract-valid material_selection.json with infeasible:true — proving the
    infeasibility report is HONESTLY written, never swallowed by the fail-safe."""
    from selection.selection import run_selection_stage, load_materials  # noqa: PLC0415
    from validate.validate import validate  # noqa: PLC0415

    membranes = [m for m in load_materials() if m["type"] == "MEMBR"]
    # A merged availability map marking every membrane out_of_stock (forces infeasible).
    availability = {m["id"]: "out_of_stock" for m in membranes}

    project_id = "infeasible-run"
    result = run_selection_stage(
        project_id,
        {"theme": None},
        inventory=availability,  # already-merged {material_id: availability} map
        projects_root=tmp_path,
    )

    assert result.get("infeasible") is True, "stage must return the infeasible result"
    assert result["selected_id"] == "INFEASIBLE"

    artifact_path = tmp_path / project_id / "material_selection.json"
    assert artifact_path.exists(), (
        "infeasibility artifact MUST be written to disk, not swallowed by the fail-safe"
    )
    written = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert written.get("infeasible") is True
    validate(written, "material_selection")  # the persisted artifact validates clean


# --------------------------------------------------------------------------- #
# D-12 — mass-balance fills the EXACT reserved field names (no drift)
# --------------------------------------------------------------------------- #
def test_mass_balance_field_names():
    """D-12 / Pitfall 10: the artifact's mass_balance carries EXACTLY the reserved field
    names from src/geom/geom.py — scaffold_kg_rented, membrane_m2_recovered, fixings_kg_new
    (+ label) — so the Phase-7 dossier reads one consistent shape."""
    candidates = [m for m in _frozen_materials() if m["type"] == "MEMBR"]
    result = select_material(candidates)
    mb = result["mass_balance"]
    assert set(mb) == {
        "label",
        "scaffold_kg_rented",
        "membrane_m2_recovered",
        "fixings_kg_new",
    }, "mass_balance field names must match the reserved geom.py names exactly"


# --------------------------------------------------------------------------- #
# D-14 — next_life ASSUMED placeholder, never a fabricated receiver
# --------------------------------------------------------------------------- #
def test_next_life_assumed_placeholder():
    """D-14 / Pitfall 9: next_life.status == 'ASSUMED' and receiver is the exact placeholder
    'receiver TBD — team contact pending' — never an invented Barcelona cooperative name."""
    candidates = [m for m in _frozen_materials() if m["type"] == "MEMBR"]
    result = select_material(candidates)
    nl = result["next_life"]
    assert nl["status"] == "ASSUMED", "next_life must be ASSUMED until the team supplies a name"
    assert nl["receiver"] == "receiver TBD — team contact pending", (
        "the receiver must be the exact ASSUMED placeholder — never fabricated"
    )
