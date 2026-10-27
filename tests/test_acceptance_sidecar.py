"""D-05/06 — instructor Comfort-Gap sidecar + reserved measured seam (DESIGNED-RED, Wave 0).

Designed-RED: imports ``from acceptance.comfort_gap import ...`` at module level, so collection
ERRORS with ``ModuleNotFoundError: No module named 'acceptance.comfort_gap'`` until the Wave-2/3
transform ships. That collection error IS the Wave-0 success state; do NOT stub to pass.

All of these live in the NON-contract ``acceptance_meta.json`` sidecar (the frozen 7-field verdict
is ``additionalProperties:false`` and cannot hold them — Pitfall 7).

Load-bearing assertions (RESEARCH §Instructor Comfort Gap, D-05/06):
  * test_comfort_gap_and_measured_seam — the sidecar carries % comfort gap closed, €/°C, baseline
    conditions inline, and a reserved ``measured_utci_delta_c: null`` ISO-7726 seam; the €/°C
    discloses the 0.0 cost as a placeholder rather than printing a misleading 0.
"""

from __future__ import annotations

# DESIGNED-RED import: errors at collection until acceptance.comfort_gap ships (Wave 2/3).
from acceptance.comfort_gap import build_sidecar

from conftest_acceptance import known_tau_membrane


def test_comfort_gap_and_measured_seam():
    """The sidecar carries the D-05/06 metrics honestly, including the placeholder disclosure."""
    sidecar = build_sidecar(
        utci_delta_c=4.8,
        coverage_pct=75.0,
        baseline_mean_c=30.99,
        material_selection=known_tau_membrane(0.40),  # cost_total_eur = 0.0
    )

    # D-05: % comfort gap closed = utci_delta_c / (baseline_mean − 26), DERIVED.
    assert "comfort_gap_pct" in sidecar, sidecar
    assert sidecar["comfort_gap_pct"] > 0.0, sidecar

    # D-05: €/°C — the demo cost is 0.0, so the metric must DISCLOSE the placeholder, not print 0.
    assert "eur_per_deg_c" in sidecar, sidecar
    assert sidecar["eur_per_deg_c"].get("placeholder") is True, (
        "a 0.0 cost must be disclosed as a placeholder, never a misleading 0 €/°C"
    )

    # D-05: baseline conditions inline (site, date/peak band, baseline mean) — falsifiable on its face.
    baseline = sidecar["baseline_conditions"]
    assert "Parc del F" in baseline["site"], baseline
    assert baseline["peak_band"], baseline
    assert baseline["baseline_mean_c"] == 30.99, baseline

    # D-06: reserved predicted-vs-measured ISO-7726 seam — predicted present, measured NULL (never faked).
    assert sidecar["predicted_utci_delta_c"] == 4.8, sidecar
    assert sidecar["measured_utci_delta_c"] is None, "measured seam must be a null placeholder"

    # sidecar marker (non-contract) — never validated against the frozen verdict schema.
    assert sidecar["schema_version"] == "1.0.0-sidecar", sidecar
