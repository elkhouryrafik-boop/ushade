"""GATE-03 — both-required verdict, contract-valid, FAIL-persisted (DESIGNED-RED, Wave 0).

Designed-RED: imports ``from acceptance.acceptance import ...`` at module level, so collection
ERRORS with ``ModuleNotFoundError: No module named 'acceptance.acceptance'`` until the Wave-3 spine
ships. That collection error IS the Wave-0 success state; do NOT stub to pass.

Load-bearing assertions (RESEARCH §GATE-03, Pitfall 5 + Pitfall 6 + Pitfall 7):
  * test_both_required — PASS iff coverage≥Y AND delta≥X across all 4 quadrants (no soft single pass).
  * test_contract_valid — the emitted ``acceptance.json`` validates against the frozen 7-field schema
    (``additionalProperties:false`` — schema field names win: utci_delta_c / X_c / Y_pct / verdict).
  * test_fail_persisted — a FAIL verdict is WRITTEN with ``verdict=="FAIL"``, never swallowed by the
    fail-safe (a FAIL is a successful stage outcome; fail-safe is for internal errors only).
"""

from __future__ import annotations

import pytest

# DESIGNED-RED import: errors at collection until acceptance.acceptance ships (Wave 3).
from acceptance.acceptance import build_verdict

from validate.validate import validate


@pytest.mark.parametrize(
    "coverage_pct, utci_delta_c, expected",
    [
        (80.0, 5.0, "PASS"),  # both clear (Y=70, X=4)
        (80.0, 3.0, "FAIL"),  # coverage-only → FAIL (delta short)
        (60.0, 5.0, "FAIL"),  # delta-only → FAIL (coverage short)
        (60.0, 3.0, "FAIL"),  # neither → FAIL
    ],
)
def test_both_required(coverage_pct, utci_delta_c, expected):
    """PASS iff coverage≥Y AND delta≥X across all 4 quadrants (Pitfall 5 — no soft pass)."""
    verdict = build_verdict(coverage_pct=coverage_pct, utci_delta_c=utci_delta_c, X_c=4, Y_pct=70)
    assert verdict["verdict"] == expected, verdict


def test_contract_valid():
    """The emitted verdict validates against the frozen ``acceptance_verdict`` schema (7 fields).

    Schema field names win (additionalProperties:false): schema_version, coverage_pct, utci_delta_c,
    X_c, Y_pct, verdict, baseline_ref. An extra key or a wrong name (e.g. the CONTEXT conceptual
    ``pass``/``utci_delta``) would make validate-then-write RAISE.
    """
    verdict = build_verdict(coverage_pct=80.0, utci_delta_c=5.0, X_c=4, Y_pct=70)
    validate(verdict, "acceptance_verdict")  # raises on any extra/misnamed key
    assert set(verdict) == {
        "schema_version",
        "coverage_pct",
        "utci_delta_c",
        "X_c",
        "Y_pct",
        "verdict",
        "baseline_ref",
    }, verdict
    assert verdict["schema_version"] == "1.0.0"
    assert verdict["baseline_ref"], "baseline_ref must be a non-empty reference to the persisted base"


def test_fail_persisted():
    """A FAIL is a real, contract-valid, persisted verdict — never silently dropped (Pitfall 6)."""
    verdict = build_verdict(coverage_pct=60.0, utci_delta_c=3.0, X_c=4, Y_pct=70)
    validate(verdict, "acceptance_verdict")  # a FAIL must ALSO satisfy the frozen schema
    assert verdict["verdict"] == "FAIL", verdict
