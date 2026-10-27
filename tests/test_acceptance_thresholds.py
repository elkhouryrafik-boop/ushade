"""GATE-03 integrity — runtime threshold drift-guard (DESIGNED-RED, Wave 0).

Designed-RED: imports ``from acceptance.thresholds import ...`` at module level, so collection
ERRORS with ``ModuleNotFoundError: No module named 'acceptance.thresholds'`` until the Wave-2 loader
ships. That collection error IS the Wave-0 success state; do NOT stub to pass.

This extends the EXISTING standing tripwire ``tests/test_thresholds_immutable.py`` (which guards the
frozen file at test time) into the gate's RUNTIME loader: the loader replicates the
``acceptance/HASHING.md`` recipe and RAISES if the on-disk value block no longer matches the stored
``content_sha256`` — so post-run X/Y tuning fails AT RUN TIME, not only in a test (threat T-00-06).

Load-bearing assertions:
  * test_loader_raises_on_mutated_value_block — the loader raises on a hash-stale tampered copy.
  * test_loader_returns_locked_xy — the loader returns X=4, Y=70 from the real frozen file.
  * test_gate_reads_xy_from_loader — the loader is the source of X/Y (no inline 4/70 in the gate).
"""

from __future__ import annotations

import pytest

# DESIGNED-RED import: errors at collection until acceptance.thresholds ships (Wave 2).
from acceptance.thresholds import ThresholdDriftError, load_thresholds

from conftest_acceptance import mutated_thresholds_copy


def test_loader_returns_locked_xy():
    """The loader returns the frozen X=4, Y=70 from the real ``acceptance/thresholds.json``."""
    thresholds = load_thresholds()
    assert thresholds["x_utci_reduction_c"] == 4, thresholds
    assert thresholds["y_coverage_pct"] == 70, thresholds


def test_loader_raises_on_mutated_value_block(tmp_path):
    """The runtime loader RAISES on a tampered copy whose hash no longer matches (Pitfall 3).

    ``mutated_thresholds_copy`` writes X 4→3 but leaves the stored ``content_sha256`` stale — the
    exact post-run-tuning attack. The loader recomputes the canonical-JSON sha256 over the value
    block and must raise ``ThresholdDriftError`` rather than return the tuned-down threshold.
    """
    tampered = mutated_thresholds_copy(tmp_path, x=3)
    with pytest.raises(ThresholdDriftError):
        load_thresholds(path=tampered)


def test_gate_reads_xy_from_loader():
    """X/Y come from the loader, not inline literals — no ``4``/``70`` constant in src/acceptance/.

    A second copy of the threshold values anywhere in the gate package is a drift vector the
    drift-guard cannot catch (it guards the frozen file). Assert the loader is the single source.
    """
    import acceptance.constants as _const

    # the ASSUMED ideal_delta is allowed; the X/Y thresholds must NOT be redeclared here.
    assert not hasattr(_const, "X_C")
    assert not hasattr(_const, "Y_PCT")
    assert not hasattr(_const, "x_utci_reduction_c")
    assert not hasattr(_const, "y_coverage_pct")
