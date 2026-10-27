"""Task-1 contract tests: cross-language validator (Python side) + provenance ledger.

Proves (00-04 Task 1 behaviors):
  - validate.py ACCEPTS the valid_utci_grid fixture against the utci_grid contract
  - the cross-file $ref to _defs/lattice + _defs/crs resolves via a referencing.Registry
    (never a deprecated RefResolver)
  - validate.py REJECTS a malformed utci_grid (baseline_utci_c deleted)
  - ledger.append_entry validates + appends; the appended entry round-trips
  - the ledger REJECTS an invalid tier ("MEASURED") via the schema enum
  - the crowd_density / carbon convenience helpers write tier == "ASSUMED" by default
    (CLAUDE.md non-negotiable)

These are the RED-discriminating assertions: each negative case asserts a real raise,
so the tests genuinely fail if the validator or the tier enum is broken.
"""

import copy

import pytest
from jsonschema.exceptions import ValidationError

from provenance.ledger import ASSUMED, ProvenanceLedger
from validate.validate import build_defs_registry, is_valid, validate

# ── validator: accept / reject + $ref resolution ─────────────────────────────


def test_validate_accepts_valid_utci_grid(valid_utci_grid):
    """The conftest master-lattice UTCI fixture satisfies the utci_grid contract."""
    # Raises on failure; reaching the assert means it validated.
    validate(valid_utci_grid, "utci_grid")
    assert is_valid(valid_utci_grid, "utci_grid")


def test_validate_accepts_full_filename(valid_utci_grid):
    """The loader accepts the full file name too (utci_grid.schema.json)."""
    validate(valid_utci_grid, "utci_grid.schema.json")


def test_cross_file_ref_resolves_via_registry(valid_utci_grid):
    """The utci_grid $refs the absolute _defs/crs + _defs/lattice $id; a
    referencing.Registry resolves them. If the registry were empty the validate
    would raise an unresolved-reference error rather than validating the data."""
    registry = build_defs_registry()
    # Both shared defs are present in the registry under their absolute $id.
    assert registry.contents(
        "https://heatguard/contracts/_defs/crs.schema.json"
    )["$id"].endswith("crs.schema.json")
    assert registry.contents(
        "https://heatguard/contracts/_defs/lattice.schema.json"
    )["$id"].endswith("lattice.schema.json")
    # And the cross-file refs actually resolve during validation.
    validate(valid_utci_grid, "utci_grid")


def test_validate_rejects_missing_baseline_utci_c(valid_utci_grid):
    """Deleting the required baseline_utci_c from a cell -> contract violation."""
    malformed = copy.deepcopy(valid_utci_grid)
    del malformed["cells"][0]["baseline_utci_c"]
    assert not is_valid(malformed, "utci_grid")
    with pytest.raises(ValidationError):
        validate(malformed, "utci_grid")


def test_validate_rejects_lattice_extra_property(valid_utci_grid):
    """additionalProperties:false on the shared lattice def is enforced through the
    registry-resolved $ref (proves the def is genuinely applied, not skipped)."""
    malformed = copy.deepcopy(valid_utci_grid)
    malformed["lattice"]["bogus_key"] = 1
    with pytest.raises(ValidationError):
        validate(malformed, "utci_grid")


# ── provenance ledger: append/validate + tier enforcement ────────────────────


def test_append_entry_validates_and_appends():
    ledger = ProvenanceLedger()
    entry = ledger.append_entry(
        key="utci_delta_c",
        value=4.2,
        tier="DERIVED",
        source="Phase5b re-sim",
        stage="acceptance",
        unit="celsius",
        formula="(baseline - shaded) * (1 - tau)",
        inputs=["utci_grid.baseline_utci_c", "material_selection.solar_transmissivity"],
    )
    assert len(ledger) == 1
    assert entry["tier"] == "DERIVED"
    assert ledger.entries[0]["key"] == "utci_delta_c"


def test_ledger_rejects_invalid_tier():
    """An off-enum tier ("MEASURED") is rejected by the schema enum, and nothing
    is appended (validate-then-append ordering keeps the ledger valid)."""
    ledger = ProvenanceLedger()
    with pytest.raises(ValidationError):
        ledger.append_entry(
            key="x",
            value=1,
            tier="MEASURED",  # not one of GROUNDED/DERIVED/ASSUMED/INVENTED
            source="bogus",
            stage="acceptance",
        )
    assert len(ledger) == 0


def test_ledger_rejects_missing_required_field():
    """Omitting a required field (source) is a contract violation."""
    ledger = ProvenanceLedger()
    with pytest.raises(ValidationError):
        ledger.append_entry(key="x", value=1, tier="GROUNDED", source="", stage="s")
    # (source minLength:1 -> empty string also rejected)


def test_crowd_density_helper_defaults_to_assumed():
    """CLAUDE.md non-negotiable: crowd_density ships pre-labelled ASSUMED."""
    ledger = ProvenanceLedger()
    entry = ledger.crowd_density(value=20.0, stage="crowd_grid")
    assert entry["tier"] == ASSUMED == "ASSUMED"
    assert entry["key"] == "crowd_density"


def test_carbon_helper_defaults_to_assumed():
    """CLAUDE.md non-negotiable: every carbon number ships pre-labelled ASSUMED."""
    ledger = ProvenanceLedger()
    entry = ledger.carbon(
        key="transport_carbon_kgco2e", value=512.0, stage="material_selection"
    )
    assert entry["tier"] == "ASSUMED"


def test_all_four_tiers_accepted():
    """The four locked tiers each validate (positive cover of the enum)."""
    ledger = ProvenanceLedger()
    ledger.grounded("baseline_utci_c", 34.5, "infrared.city", "utci_grid", unit="celsius")
    ledger.derived("score", 120.0, "Crowd*(UTCI-26)", "score_grid")
    ledger.assumed("transport_mode_factor", 0.10, "placeholder", "material_selection")
    ledger.invented("capacity", 50000, "LLM parse pre-check", "parsed_brief")
    artifact = ledger.to_artifact()
    # The whole ledger validates against the contract.
    validate(artifact, "provenance_ledger")
    assert {e["tier"] for e in artifact["entries"]} == {
        "GROUNDED",
        "DERIVED",
        "ASSUMED",
        "INVENTED",
    }


def test_ledger_write_round_trips(tmp_path):
    """write() validates the whole ledger and persists a re-validatable artifact."""
    ledger = ProvenanceLedger()
    ledger.crowd_density(value=8.0, stage="crowd_grid")
    out = ledger.write(tmp_path / "provenance_ledger.json")
    assert out.exists()
    import json

    reloaded = json.loads(out.read_text(encoding="utf-8"))
    validate(reloaded, "provenance_ledger")
    assert reloaded["entries"][0]["tier"] == "ASSUMED"
