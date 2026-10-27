"""GATE-01 — projected-shadow coverage over the funded priority cells (DESIGNED-RED, Wave 0).

This file is designed-RED: it imports ``from acceptance.coverage import ...`` at MODULE level, so
collection ERRORS with ``ModuleNotFoundError: No module named 'acceptance.coverage'`` until the
Wave-2 transform lands (Nyquist — the test exists by name before the code). That collection error
IS the Wave-0 success state; do NOT stub ``acceptance.coverage`` to make it pass.

Load-bearing assertions (RESEARCH §GATE-01, Pitfall 12 + Pitfall 8):
  * test_shadow_not_footprint — a cell UNDER the footprint but OUTSIDE the projected shadow is NOT
    credited (coverage is the SHADOW∩priority ratio, never footprint area).
  * test_frame_alignment — priority-cell centres + the shadow translated by the SAME ``min_corner_m``
    intersect → a non-zero, correct coverage; never a false 0.0 from a frame mismatch.
  * test_coverage_ratio_known — the 3-of-4 synthetic set yields exactly 75 %.
"""

from __future__ import annotations

# DESIGNED-RED import: errors at collection until acceptance.coverage ships (Wave 2).
from acceptance.coverage import priority_shadow_coverage

from conftest_acceptance import synthetic_priority_set


def test_coverage_ratio_known():
    """The synthetic 3-of-4-shaded set yields exactly 75 % coverage."""
    s = synthetic_priority_set()
    result = priority_shadow_coverage(s["cells"], s["shadow_polygon_m"])
    assert result["coverage_pct"] == 75.0, result
    assert result["shaded_count"] == s["expected_shaded_count"], result
    assert result["priority_count"] == s["expected_priority_count"], result


def test_shadow_not_footprint():
    """Pitfall 12: a cell under the footprint but OUTSIDE the shadow is NOT credited.

    The 4th synthetic cell ``(50, 50)`` could sit under a footprint polygon but lies outside the
    projected shadow — a correct GATE-01 credits coverage by the SHADOW, never by footprint area, so
    that cell must be excluded (3 of 4 shaded, not 4 of 4).
    """
    s = synthetic_priority_set()
    result = priority_shadow_coverage(s["cells"], s["shadow_polygon_m"])
    # if the gate credited footprint membership it would read 100 %; the shadow ratio is 75 %.
    assert result["coverage_pct"] < 100.0, "must not credit a footprinted-but-unshaded cell"
    assert result["coverage_pct"] == 75.0, result


def test_frame_alignment():
    """Pitfall 8: cells + shadow translated by the SAME min_corner → non-zero, never a false 0 %.

    Offset BOTH the cell centres and the shadow polygon into an absolute-EPSG-scale frame
    (~435000 m) with a matching ``min_corner_m``. A frame-aware gate translates both by that offset
    and still finds the 3 shaded cells; a frame-blind gate would read a false 0 %.
    """
    s = synthetic_priority_set()
    offset = 435000.0
    shifted_cells = [
        {"x_m": c["x_m"] + offset, "y_m": c["y_m"] + offset, "baseline_utci_c": c["baseline_utci_c"]}
        for c in s["cells"]
    ]
    shifted_shadow = {
        "basis": "synthetic",
        "min_corner_m": [offset, offset],
        "polygons_xy_m": s["shadow_polygon_m"]["polygons_xy_m"],  # still near-origin
    }
    result = priority_shadow_coverage(shifted_cells, shifted_shadow)
    assert result["coverage_pct"] > 0.0, "frame-aware intersection must not read a false 0 %"
    assert result["coverage_pct"] == 75.0, result
