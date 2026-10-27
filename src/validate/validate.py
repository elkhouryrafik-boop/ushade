"""Python contract validator over the neutral ``contracts/`` schemas (CONTRACT-02).

The single source of truth for every inter-stage contract is the set of
``contracts/*.schema.json`` files (JSON Schema draft 2020-12). This module is the
Python *consumer* of those files — the Node ``validate.ts`` consumes the SAME files
with Ajv2020, so the two runtimes cannot drift (00-RESEARCH §Single-Source Schema
Strategy, Pitfall A).

Cross-file ``$ref`` resolution uses a ``referencing.Registry`` built from
``contracts/_defs/*`` — the supported mechanism for jsonschema >=4.18 (the
deprecated ``RefResolver`` is never used; 00-RESEARCH §Code Examples / State of the
Art). The shared crs/lattice defs self-key by their embedded absolute ``$id``
(``https://heatguard/contracts/_defs/<name>.schema.json``), which is exactly what
the spatial schemas ``$ref`` — so resolution is unambiguous regardless of referrer
(see 00-02-SUMMARY deviation #1: absolute def ``$id``, never a relative path).

karpathy: thin and direct — load a schema, build a registry, return a validator.
No schema registry abstraction, no codegen; jsonschema owns the validation math
(00-RESEARCH §Don't Hand-Roll).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

# Repo root = parent of src/. contracts/ holds the single-source schemas.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTRACTS_DIR = _REPO_ROOT / "contracts"
_DEFS_DIR = _CONTRACTS_DIR / "_defs"


def _schema_filename(name: str) -> str:
    """Accept either a bare contract name (``utci_grid``) or a full file name
    (``utci_grid.schema.json``) and return the file name."""
    return name if name.endswith(".schema.json") else f"{name}.schema.json"


def load_schema(name: str) -> dict:
    """Load a contract schema by name.

    ``name`` may be ``"utci_grid"`` or ``"utci_grid.schema.json"``.
    """
    path = _CONTRACTS_DIR / _schema_filename(name)
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def build_defs_registry() -> Registry:
    """Build a ``referencing.Registry`` from ``contracts/_defs/*.json``.

    Each def resource self-keys by its absolute ``$id`` (``Resource.from_contents``
    reads the embedded ``$id``), so the spatial schemas' absolute ``$ref``s resolve
    regardless of the referring schema's base URI. Cached: the defs are immutable
    contract files. Mirrors ``tests/conftest.build_defs_registry`` so test fixtures
    and runtime validation resolve refs identically.
    """
    registry = Registry()
    for path in sorted(_DEFS_DIR.glob("*.json")):
        resource = Resource.from_contents(json.loads(path.read_text(encoding="utf-8")))
        registry = resource @ registry
    return registry


@lru_cache(maxsize=1)
def get_format_checker() -> FormatChecker:
    """Build the ``FormatChecker`` that makes ``format`` ASSERT (parity with ajv).

    Starts from the draft 2020-12 base checker (``date`` is registered there via
    stdlib ``date.fromisoformat`` — no extra dep) and then GUARANTEES ``uri``
    asserts. We register ``uri`` explicitly rather than trusting jsonschema's
    optional-dependency auto-detection: with ``rfc3987`` installed, jsonschema
    registers ``iri`` (not ``uri``), so ``uri`` can silently no-op even though a
    "format" extra is present. Wiring ``rfc3986-validator`` directly removes that
    ordering fragility — the only formats our contracts use are ``date`` and
    ``uri``, and both now assert deterministically on every machine.
    """
    checker = FormatChecker()
    base = Draft202012Validator.FORMAT_CHECKER
    for fmt, entry in base.checkers.items():
        checker.checkers[fmt] = entry

    if "uri" not in checker.checkers:
        from rfc3986_validator import validate_rfc3986

        @checker.checks("uri")
        def _is_uri(instance: object) -> bool:
            # Non-strings are other schemas' concern (mirror ajv-formats / jsonschema).
            if not isinstance(instance, str):
                return True
            return validate_rfc3986(instance, rule="URI") is not None

    return checker


def get_validator(name: str) -> Draft202012Validator:
    """Return a ``Draft202012Validator`` for the named contract, registry-backed.

    Meta-validates the schema itself (``check_schema``) before constructing the
    validator, so a malformed schema fails loudly rather than silently accepting
    everything.

    ``format_checker`` is wired in so ``format`` keywords (``date`` in
    parsed_brief, ``uri`` in render) are ASSERTED, not merely annotated. Without
    it, 2020-12 makes ``format`` annotation-only and Python would ACCEPT a value
    Node's ``ajv-formats`` REJECTS — the exact cross-runtime drift CONTRACT-02
    forbids (Pitfall A). See ``get_format_checker`` for the deterministic
    ``uri`` wiring; the runtime ``rfc3986-validator`` dep is pinned in
    pyproject so the checker never silently no-ops.
    """
    schema = load_schema(name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(
        schema,
        registry=build_defs_registry(),
        format_checker=get_format_checker(),
    )


def validate(artifact: dict, name: str) -> None:
    """Validate ``artifact`` against the named contract; raise on failure.

    Raises ``jsonschema.exceptions.ValidationError`` on the first violation
    (``.validate`` raises immediately). Returns ``None`` on success.
    """
    get_validator(name).validate(artifact)


def is_valid(artifact: dict, name: str) -> bool:
    """Non-raising convenience: ``True`` iff ``artifact`` satisfies the contract."""
    return get_validator(name).is_valid(artifact)
