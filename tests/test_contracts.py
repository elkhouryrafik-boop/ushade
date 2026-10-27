"""Contract conformance for the two Phase-5 contracts (Task 3, GREEN after Task 1).

The two frozen contracts authored in 05-01 Task 1 —
``contracts/inventory_snapshot.schema.json`` (NEW) and
``contracts/material_selection.schema.json`` (bumped to 1.1.0) — must ACCEPT a
well-formed artifact and REJECT a malformed one, through the SAME single-source
``validate(artifact, name)`` Node + the runtime use (never a hand-rolled shape check;
mirrors ``test_core_contract.py`` / ``test_crowd_contract.py``).

Unlike the designed-RED ``test_inventory.py`` / ``test_selection.py`` scaffolds (which fail
at import on absent ``src.inventory`` / ``src.selection``), THESE tests run NOW — they touch
only the contract files, which exist after Task 1, so they are GREEN, not RED. They are the
contract acceptance gate Plans 02/03/04 validate against.

NOTE: this file did not exist before 05-01; the plan said "extend tests/test_contracts.py"
but the contract-conformance suite previously lived in test_schemas_valid.py (meta-validation)
and the per-stage test_*_contract.py files. Creating test_contracts.py satisfies the plan's
grep/pytest acceptance criteria (which name this exact file) and gives the two Phase-5
contracts a dedicated valid/invalid gate.
"""

from __future__ import annotations

import pytest
from jsonschema.exceptions import ValidationError

from validate.validate import is_valid, validate


# --------------------------------------------------------------------------- #
# inventory_snapshot (NEW, 1.0.0)
# --------------------------------------------------------------------------- #
def _live_snapshot_one_listing() -> dict:
    """A well-formed live snapshot: one bound listing + empty rejected[]."""
    return {
        "schema_version": "1.0.0",
        "source_id": "thefabricsales",
        "source_url": "https://thefabricsales.example",
        "fetched_at": "2026-06-15T00:00:00Z",
        "status": "live",
        "provenance_tier": "GROUNDED",
        "listings": [
            {
                "material_id": "membr-recycled-pe-tarp",
                "source_url": "https://thefabricsales.example/products/recycled-pe-tarp",
                "fetched_at": "2026-06-15T00:00:00Z",
                "qty_available": 120.0,
                "availability": "available",
                "price_eur": 2.40,
                "distance_km": 23.2,
                "distance_tier": "DERIVED",
            }
        ],
        "rejected": [],
    }


def test_inventory_snapshot_valid_live():
    """A live snapshot with one listing + empty rejected[] is ACCEPTED."""
    artifact = _live_snapshot_one_listing()
    validate(artifact, "inventory_snapshot")  # must not raise
    assert is_valid(artifact, "inventory_snapshot") is True


def test_inventory_snapshot_missing_rejected_is_rejected():
    """rejected[] is REQUIRED (the never-silent-drop seam) — omitting it is invalid."""
    artifact = _live_snapshot_one_listing()
    del artifact["rejected"]
    with pytest.raises(ValidationError):
        validate(artifact, "inventory_snapshot")
    assert is_valid(artifact, "inventory_snapshot") is False


def test_inventory_snapshot_bad_status_is_rejected():
    """status 'empty' is not in the {live, stale_snapshot, unavailable} enum — invalid.

    A failed fetch must degrade to a LABELLED status, never an off-enum 'empty' that the
    gate could silently read as 'nothing available'."""
    artifact = _live_snapshot_one_listing()
    artifact["status"] = "empty"
    with pytest.raises(ValidationError):
        validate(artifact, "inventory_snapshot")
    assert is_valid(artifact, "inventory_snapshot") is False


def test_inventory_snapshot_unavailable_empty_listings_valid():
    """A LABELLED unavailable snapshot with empty listings[] is valid (D-07 no-public-stock /
    Q1 degrade) — the never-silent shape (not an empty 'live')."""
    artifact = {
        "schema_version": "1.0.0",
        "source_id": "ulma",
        "fetched_at": "2026-06-15T00:00:00Z",
        "status": "unavailable",
        "listings": [],
        "rejected": [],
    }
    validate(artifact, "inventory_snapshot")
    assert is_valid(artifact, "inventory_snapshot") is True


# --------------------------------------------------------------------------- #
# material_selection (bumped to 1.1.0)
# --------------------------------------------------------------------------- #
def _full_selection_1_1_0() -> dict:
    """A full 1.1.0 selection artifact: mass_balance + next_life + tent_comparison +
    selection_basis."""
    return {
        "schema_version": "1.1.0",
        "selected_id": "membr-recycled-pe-tarp",
        "is_membrane": True,
        "transport_carbon_kgco2e": 0.768,
        "cost_total_eur": 200.0,
        "solar_transmissivity": 0.15,
        "selection_basis": "transport_carbon_min",
        "availability_gated": True,
        "candidates_considered": 5,
        "cooling_correction_factor": 0.85,
        "mass_balance": {
            "label": "ASSUMED",
            "scaffold_kg_rented": 0.0,
            "membrane_m2_recovered": 100.0,
            "fixings_kg_new": 5.0,
        },
        "next_life": {
            "status": "ASSUMED",
            "receiver": "receiver TBD — team contact pending",
            "return_mass_kg": 16.0,
        },
        "tent_comparison": {
            "label": "ASSUMED",
            "baseline_kgco2e_per_m2": 4.0,
            "source": "single-use PVC marquee baseline, ICE v2.0 (Hammond & Jones), PVC 5.6 kgCO2e/kg A1-A3, ~0.7 kg/m2 ASSUMED",
        },
        "infeasible": False,
    }


def test_material_selection_1_1_0_valid_full():
    """A full 1.1.0 artifact (all 7 new fields + the original 6) is ACCEPTED."""
    artifact = _full_selection_1_1_0()
    validate(artifact, "material_selection")  # must not raise
    assert is_valid(artifact, "material_selection") is True


def test_material_selection_membrane_tau_null_still_rejected():
    """The kept is_membrane⇒τ-non-null allOf still bites: a membrane with τ=null is invalid
    (the (1−τ) cooling correction would be undefined)."""
    artifact = _full_selection_1_1_0()
    artifact["solar_transmissivity"] = None
    with pytest.raises(ValidationError):
        validate(artifact, "material_selection")
    assert is_valid(artifact, "material_selection") is False


def test_material_selection_bad_selection_basis_rejected():
    """selection_basis is a const 'transport_carbon_min' — a 'price_min' basis is REJECTED.

    The artifact cannot claim a price-based selection (the honesty / sort-key marker)."""
    artifact = _full_selection_1_1_0()
    artifact["selection_basis"] = "price_min"
    with pytest.raises(ValidationError):
        validate(artifact, "material_selection")
    assert is_valid(artifact, "material_selection") is False


def test_material_selection_missing_selection_basis_rejected():
    """selection_basis is REQUIRED in 1.1.0 (always emitted, the honesty marker)."""
    artifact = _full_selection_1_1_0()
    del artifact["selection_basis"]
    with pytest.raises(ValidationError):
        validate(artifact, "material_selection")
    assert is_valid(artifact, "material_selection") is False


def test_material_selection_mass_balance_field_name_drift_rejected():
    """mass_balance.additionalProperties:false bites a drifted field name
    (scaffold_rented_kg ≠ the reserved scaffold_kg_rented) — Pitfall 10."""
    artifact = _full_selection_1_1_0()
    artifact["mass_balance"]["scaffold_rented_kg"] = 1.0  # wrong name
    with pytest.raises(ValidationError):
        validate(artifact, "material_selection")
    assert is_valid(artifact, "material_selection") is False
