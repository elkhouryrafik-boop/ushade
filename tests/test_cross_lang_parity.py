"""Cross-language accept/reject parity — the Python half (XFN-02 testable half).

For every contract, the SAME ``tests/fixtures/valid/<contract>.json`` must be
ACCEPTED and the SAME ``tests/fixtures/invalid/<contract>.json`` must be REJECTED.
``tests/parity.test.ts`` is the Node mirror that asserts the IDENTICAL outcomes
with Ajv2020 — that the two runtimes agree on every fixture is the cross-language
parity proof (defeats Pitfall A: silent schema drift between jsonschema and ajv).

This module is the jsonschema (Python) side; it calls ``src/validate/validate.py``
(``pythonpath = ["src"]`` in pyproject), the same validator Phase 1+ uses.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError

from validate.validate import is_valid, validate

# tests/fixtures/{valid,invalid}/<contract>.json — the SAME files parity.test.ts reads.
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_VALID_DIR = _FIXTURES_DIR / "valid"
_INVALID_DIR = _FIXTURES_DIR / "invalid"

# The 8 named contracts (the _defs crs/lattice are shared sub-schemas, not artifacts).
# Phase 14 (Plan 04, D-05/D-06): score_grid + footprint RETIRED with the greedy core —
# their orphan schemas + parity fixtures were removed in lock-step (a contract-count
# change forces a lock-step fixture update, the Phase-5 discipline).
CONTRACTS = [
    "parsed_brief",
    "utci_grid",
    "crowd_grid",
    "gh_response",
    "material_selection",
    "acceptance_verdict",
    "render",
    "provenance_ledger",
]


def _load(directory: Path, contract: str) -> dict:
    return json.loads((directory / f"{contract}.json").read_text(encoding="utf-8"))


def test_every_contract_has_both_fixtures():
    """Guard: a valid + invalid fixture exists for every named contract (parity needs both halves)."""
    for contract in CONTRACTS:
        assert (_VALID_DIR / f"{contract}.json").is_file(), f"missing valid {contract}"
        assert (_INVALID_DIR / f"{contract}.json").is_file(), f"missing invalid {contract}"
    assert len(list(_VALID_DIR.glob("*.json"))) == len(CONTRACTS)
    assert len(list(_INVALID_DIR.glob("*.json"))) == len(CONTRACTS)


@pytest.mark.parametrize("contract", CONTRACTS)
def test_valid_fixture_is_accepted(contract: str):
    """jsonschema ACCEPTS the valid fixture (raises nothing, is_valid True)."""
    artifact = _load(_VALID_DIR, contract)
    validate(artifact, contract)  # must not raise
    assert is_valid(artifact, contract) is True


@pytest.mark.parametrize("contract", CONTRACTS)
def test_invalid_fixture_is_rejected(contract: str):
    """jsonschema REJECTS the invalid fixture (validate raises, is_valid False)."""
    artifact = _load(_INVALID_DIR, contract)
    with pytest.raises(ValidationError):
        validate(artifact, contract)
    assert is_valid(artifact, contract) is False
