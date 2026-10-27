"""Schema meta-validation (CONTRACT-02).

Proves every file under contracts/ is itself a structurally valid JSON Schema
draft 2020-12, and that each top-level contract requires a ``schema_version``
``const`` so a bumped contract loudly rejects a stale artifact (T-00-04 schema
drift mitigation).

These tests run on the schema files themselves — no real pipeline data needed.
"""

import glob
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONTRACTS_DIR = _REPO_ROOT / "contracts"

# All schema files (the named contracts + gh_request + inventory_snapshot +
# structure_zones + crs/lattice _defs).
_SCHEMA_PATHS = sorted(
    Path(p) for p in glob.glob(str(_CONTRACTS_DIR / "**" / "*.json"), recursive=True)
)

# Top-level contracts carry a required schema_version const. The shared _defs
# (crs, lattice) are referenced fragments, not standalone artifacts, so they do
# not — they are excluded from the schema_version assertion.
_TOPLEVEL_PATHS = [p for p in _SCHEMA_PATHS if p.parent.name != "_defs"]


def test_schema_files_exist():
    """The named contracts + gh_request + inventory_snapshot + structure_zones + 2 _defs
    = 13 schema files are present.

    Phase 5 (05-01) added contracts/inventory_snapshot.schema.json; Phase 12 (12-01) added
    contracts/structure_zones.schema.json. Phase 14 (14-04, D-05/D-06) RETIRED the greedy
    score_grid + footprint schemas with their producer, dropping the total from 15 to 13.
    """
    assert len(_SCHEMA_PATHS) == 13, [p.name for p in _SCHEMA_PATHS]


def test_named_contracts_plus_gh_request():
    """11 contracts/*.schema.json named contracts; _defs are separate.

    Phase 5 (05-01) added inventory_snapshot.schema.json and Phase 12 (12-01) added
    structure_zones.schema.json; Phase 14 (14-04) retired score_grid + footprint, taking
    the named count from 13 to 11.
    """
    named = sorted(glob.glob(str(_CONTRACTS_DIR / "*.schema.json")))
    assert len(named) == 11, [Path(p).name for p in named]


@pytest.mark.parametrize("path", _SCHEMA_PATHS, ids=lambda p: p.name)
def test_each_file_is_valid_2020_12_schema(path):
    """Every contracts/**/*.json is a structurally valid draft-2020-12 schema."""
    schema = json.loads(path.read_text(encoding="utf-8"))
    assert (
        schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
    ), f"{path.name} does not declare draft 2020-12"
    # Raises SchemaError if the schema is not itself valid 2020-12.
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("path", _TOPLEVEL_PATHS, ids=lambda p: p.name)
def test_each_contract_requires_schema_version_const(path):
    """Each top-level contract requires schema_version and pins it as a const."""
    schema = json.loads(path.read_text(encoding="utf-8"))
    assert "schema_version" in schema.get("required", []), (
        f"{path.name} must require 'schema_version'"
    )
    sv = schema.get("properties", {}).get("schema_version", {})
    assert "const" in sv, f"{path.name} schema_version must be a const"


@pytest.mark.parametrize("path", _TOPLEVEL_PATHS, ids=lambda p: p.name)
def test_each_contract_has_id_and_version(path):
    """Each contract embeds a version ($id + x-schema-version)."""
    schema = json.loads(path.read_text(encoding="utf-8"))
    assert schema.get("$id", "").startswith("https://heatguard/contracts/"), path.name
    assert schema.get("x-schema-version"), f"{path.name} missing x-schema-version"


@pytest.mark.parametrize("path", _SCHEMA_PATHS, ids=lambda p: p.name)
def test_no_etrs89_leak(path):
    """No schema may carry the ETRS89/25831 CRS (canonical is EPSG:32631)."""
    assert "25831" not in path.read_text(encoding="utf-8"), (
        f"{path.name} leaks ETRS89/25831"
    )
