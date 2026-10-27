"""Baseline-definition completeness (CONTRACT-05 / threat T-00-08).

`acceptance/baseline_spec.md` must fix the Phase 5b delta denominator BEFORE any
climate code exists: what the no-shade baseline is, where it lives, which cells the
delta covers, the (1 - tau) scaling, the GROUNDED/DERIVED provenance, and that the
X/Y gate is immutable. These assertions catch a baseline spec that silently drops a
required clause (which would make the cooling delta unfalsifiable).
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BASELINE_SPEC_PATH = _REPO_ROOT / "acceptance" / "baseline_spec.md"


def test_baseline_spec_covers_all_required_clauses():
    text = _BASELINE_SPEC_PATH.read_text(encoding="utf-8")

    # WHERE: names the persisted denominator field in utci_grid.
    assert "baseline_utci_c" in text

    # tau SCALING: the (1 - tau) cooling correction must be stated.
    assert ("(1 − solar_transmissivity)" in text) or ("(1 − τ)" in text) or (
        "(1 - tau)" in text
    ), "baseline_spec.md must state the (1 - tau) cooling correction"

    # PROVENANCE: baseline is GROUNDED.
    assert "GROUNDED" in text

    # WHICH CELLS: shadow overlap, not raw footprint area.
    assert "shadow" in text

    # IMMUTABILITY: X/Y locked, immutable post-run.
    assert "immutable" in text
