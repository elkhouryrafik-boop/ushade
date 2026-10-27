"""Provenance ledger writer (CONTRACT-06).

Every reported number in HeatGuard must carry a provenance *tier* and a *source*,
so "why did it shade here?" always has an auditable answer (Pitfall E / T-00-11
"provenance decay"). This module is the writer: ``append_entry`` validates each
single entry against ``contracts/provenance_ledger.schema.json`` (via ``validate.py``
— the same neutral contract both runtimes share) and appends it; ``write`` dumps the
``{schema_version, entries}`` artifact.

The four tiers are LOCKED (00-RESEARCH §Provenance Ledger Format):
  - GROUNDED  — measured/sourced (infrared UTCI, materials.json distances)
  - DERIVED   — computed from grounded inputs (Score, Transport_Carbon, coverage_pct)
  - ASSUMED   — convention/placeholder (crowd_density until PPO validated, carbon cut-off)
  - INVENTED  — LLM-emitted pre-validation (parsed brief pre-check; promotes to DERIVED
                on schema-validation)

NON-NEGOTIABLE (CLAUDE.md): ``crowd_density`` and every carbon number are written
**ASSUMED by the writer's API** — the ``assumed(...)`` helper (and the dedicated
``crowd_density``/``carbon`` helpers) make the correct tier the path of least
resistance, so an unlabelled or mis-labelled number cannot reach the dashboard.

karpathy: a single class wrapping a list — no event bus, no ORM. The schema enum is
the validation; we don't re-encode the tier list except as a readable constant.
"""

from __future__ import annotations

import json
from pathlib import Path

# pythonpath=["src"] (pyproject) makes the sibling package importable as ``validate``.
from validate.validate import validate as _validate_contract

_LEDGER_CONTRACT = "provenance_ledger"
_SCHEMA_VERSION = "1.0.0"

# The locked 4-tier vocabulary. The authoritative enum lives in
# provenance_ledger.schema.json (entry.tier); this mirror is for readable helpers
# and lets callers reference the tiers by name. Validation always goes through the
# schema, so this constant can never silently diverge into acceptance.
GROUNDED = "GROUNDED"
DERIVED = "DERIVED"
ASSUMED = "ASSUMED"
INVENTED = "INVENTED"
TIERS = (GROUNDED, DERIVED, ASSUMED, INVENTED)


class ProvenanceLedger:
    """Append-only, schema-validated provenance ledger.

    Each ``append_entry`` validates the single entry against the provenance_ledger
    contract's ``entry`` shape by wrapping it in a one-entry ledger and validating
    that — so the same contract both runtimes share is the single gate, and an
    invalid ``tier`` (e.g. ``"MEASURED"``) is rejected by the schema enum.
    """

    def __init__(self) -> None:
        self._entries: list[dict] = []

    # ── core ──────────────────────────────────────────────────────────────────
    def append_entry(
        self,
        key: str,
        value,
        tier: str,
        source: str,
        stage: str,
        unit: str | None = None,
        formula: str | None = None,
        inputs: list[str] | None = None,
    ) -> dict:
        """Validate and append one provenance entry; return the stored entry.

        Raises ``jsonschema.exceptions.ValidationError`` if the entry violates the
        contract (e.g. an unknown ``tier``, a missing required field). The entry is
        appended ONLY after it validates, so the in-memory ledger is always valid.
        """
        entry: dict = {
            "key": key,
            "value": value,
            "tier": tier,
            "source": source,
            "stage": stage,
        }
        if unit is not None:
            entry["unit"] = unit
        if formula is not None:
            entry["formula"] = formula
        if inputs is not None:
            entry["inputs"] = inputs

        # Validate the entry by validating a one-entry ledger against the shared
        # contract — the schema's entry enum/required-fields are the single gate.
        _validate_contract(
            {"schema_version": _SCHEMA_VERSION, "entries": [entry]},
            _LEDGER_CONTRACT,
        )
        self._entries.append(entry)
        return entry

    # ── tier-specific convenience helpers ─────────────────────────────────────
    def grounded(self, key, value, source, stage, **kw) -> dict:
        """Measured/sourced number (infrared UTCI, materials.json distances)."""
        return self.append_entry(key, value, GROUNDED, source, stage, **kw)

    def derived(self, key, value, source, stage, **kw) -> dict:
        """Number computed from grounded inputs (Score, coverage_pct, ...)."""
        return self.append_entry(key, value, DERIVED, source, stage, **kw)

    def assumed(self, key, value, source, stage, **kw) -> dict:
        """Convention/placeholder number — tier forced to ASSUMED.

        Use for any value not yet grounded. crowd_density and every carbon number
        MUST flow through here (or the dedicated helpers below) so they ship
        pre-labelled ASSUMED (CLAUDE.md non-negotiable).
        """
        return self.append_entry(key, value, ASSUMED, source, stage, **kw)

    def invented(self, key, value, source, stage, **kw) -> dict:
        """LLM-emitted number before schema-validation (promotes to DERIVED later)."""
        return self.append_entry(key, value, INVENTED, source, stage, **kw)

    # ── domain helpers that HARD-CODE the ASSUMED tier (CLAUDE.md) ─────────────
    def crowd_density(self, value, stage, source=None, **kw) -> dict:
        """Write a crowd-density number — ALWAYS tier=ASSUMED.

        crowd_density stays ASSUMED until the Phase-2b PPO weights are validated
        (CLAUDE.md / PROJECT.md); the tier is not a caller choice here.
        """
        return self.assumed(
            "crowd_density",
            value,
            source or "Phase 2b PPO output (ASSUMED until weights validated)",
            stage,
            **kw,
        )

    def carbon(self, key, value, stage, source=None, **kw) -> dict:
        """Write a carbon number — ALWAYS tier=ASSUMED.

        Transport-only cut-off; manufacturing carbon = 0 (ASSUMED, ISO 14044
        §4.3.4). The tier is not a caller choice (CLAUDE.md non-negotiable).
        """
        return self.assumed(
            key,
            value,
            source or "transport-only cut-off; manufacturing=0 (ASSUMED, ISO 14044 4.3.4)",
            stage,
            **kw,
        )

    # ── serialization ─────────────────────────────────────────────────────────
    def to_artifact(self) -> dict:
        """Return the full ``{schema_version, entries}`` ledger artifact."""
        return {"schema_version": _SCHEMA_VERSION, "entries": list(self._entries)}

    def write(self, path) -> Path:
        """Validate the whole ledger and write it as JSON to ``path``; return Path."""
        artifact = self.to_artifact()
        _validate_contract(artifact, _LEDGER_CONTRACT)
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        return out

    @property
    def entries(self) -> list[dict]:
        """Read-only view of the appended entries."""
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)
