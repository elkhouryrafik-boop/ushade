"""D-05/D-06 — instructor Comfort-Gap sidecar (NON-contract ``acceptance_meta.json``).

The frozen ``acceptance_verdict`` schema is ``additionalProperties:false`` (7 fields only,
Pitfall 7), so it CANNOT hold the instructor's Comfort-Gap extras. Those extras live in a
NON-contract sidecar dict — exactly as Phase-4 ``geom.py`` puts its extras in ``gh_meta.json``
beside the frozen ``gh_response.json``, marked ``schema_version = "1.0.0-sidecar"`` so the
sidecar is never mistaken for a contract artifact and never passed to ``validate()``.

This module is a PURE builder (no I/O): the Plan-04 orchestrator writes the returned dict to
``acceptance_meta.json``. Base tier — no ``rhino3dm`` / ``torch`` / ``infrared`` import.

Instructor metrics (INSTRUCTOR-FEEDBACK.md §Phase 5b, CONTEXT D-05/D-06):

  * **% comfort gap closed** (``comfort_gap_pct``) = ``utci_delta_c / (baseline_mean_c − 26)``
    over the target shaded cells. DERIVED. The instructor's single most-wanted metric
    ("this geometry closes X percent of the comfort gap").
  * **€ per °C** (``eur_per_deg_c``) = ``cost_total_eur / utci_delta_c`` (numerator = the
    Phase-5 ``cost_total_eur`` roll-up — Q4). The demo cost is ``0.0`` (free recovered
    material), so the metric is DISCLOSED as a labelled placeholder — never a misleading
    numeric ``0 €/°C`` (threat T-05b-09 / Q4).
  * **baseline conditions inline** (``baseline_conditions``): site, latlon, date, peak band,
    baseline mean, coverage basis, sky/albedo — so the number is falsifiable on its face
    ("under which sky, at which hour, over which surface albedo does that figure hold?").
  * **predicted-vs-measured seam** (D-06, ISO 7726): ``predicted_utci_delta_c`` carries the
    PREDICTED delta; ``measured_utci_delta_c`` is ALWAYS ``None`` in v1 — a reserved null
    placeholder, NEVER a fabricated measured value (threat T-05b-10; placeholder discipline
    cloned from ``selection.reporting.next_life``). The monitoring protocol is a team
    deliverable; the pipeline only reserves the seam.

All numbers carry a provenance tier (GROUNDED / DERIVED / ASSUMED / PLACEHOLDER).
"""

from __future__ import annotations

from acceptance.constants import (
    PEAK_BAND_LABEL,
    SIDECAR_VERSION,
    SITE_LATLON,
    SITE_NAME,
)

#: PRD comfort threshold (°C). The baseline excess the comfort gap is measured against is
#: ``(UTCI − 26)`` (INSTRUCTOR-FEEDBACK §Phase 3/5b). Named once here; the same 26 °C as
#: ``core.constants.COMFORT_THRESHOLD_C`` — repeated only so this base-tier sidecar builder
#: needs no heavy import. (If core ever moves it, update both — this comment is the link.)
_COMFORT_THRESHOLD_C: float = 26.0

#: The ISO-7726 on-site monitoring protocol the measured seam reserves (D-06). Stated so the
#: reserved ``measured_utci_delta_c=None`` is the honest "here is how you'd verify it" hook.
_MONITORING_PROTOCOL: str = (
    "ISO 7726: globe thermometer + air-temperature/RH probes at 1.1 m; stations at canopy "
    "centre, canopy edge, and an unshaded control; 5-min logging; raw CSV published open. "
    "measured_utci_delta_c stays null until a real on-site campaign lands — never fabricated."
)

#: The sky/surface label the instructor demands beside every reported delta ("under which sky,
#: over which surface albedo?"). ASSUMED — sourced from the infrared.city model assumptions.
_SKY_ALBEDO_LABEL: str = (
    "ASSUMED (infrared.city radiation-based model assumptions; see acceptance/baseline_spec.md)"
)


def build_sidecar(
    *,
    utci_delta_c: float,
    coverage_pct: float,
    baseline_mean_c: float,
    material_selection: dict,
    brief_date: str | None = None,
    coverage_basis: str = "roof-mesh-projection",
) -> dict:
    """Build the NON-contract Comfort-Gap sidecar dict (D-05/D-06).

    Args:
        utci_delta_c: the PREDICTED achieved ΔUTCI (°C) from GATE-02 (DERIVED: ASSUMED ideal
            × (1−τ) over the GROUNDED baseline). Also the €/°C and %/°C denominator.
        coverage_pct: the GATE-01 projected-shadow priority-cell coverage (%). DERIVED.
        baseline_mean_c: the GROUNDED no-shade baseline mean UTCI (°C) over the target cells —
            the comfort-gap denominator anchor and an inline baseline condition.
        material_selection: the Phase-5 ``material_selection`` dict; ``cost_total_eur`` is the
            €/°C numerator (Q4). ``0.0`` (free recovered material) → placeholder disclosure.
        brief_date: the run/brief date for the inline baseline conditions (None → reserved).
        coverage_basis: the shadow-projection basis label carried inline (provenance honesty).

    Returns:
        A NON-contract dict marked ``schema_version = "1.0.0-sidecar"``. It MUST NEVER be passed
        to ``validate()`` against the frozen ``acceptance_verdict`` schema (it would be rejected —
        and that is the point: instructor extras live OUTSIDE the contract).
    """
    cost_total_eur = float(material_selection.get("cost_total_eur", 0.0))

    # ── D-05a: % comfort gap closed = utci_delta_c / (baseline_mean − 26) ─────────────────
    # Guard the denominator: a baseline at/below comfort has no gap to close — null, never
    # a fabricated/inf number (placeholder discipline, threat T-05b-10).
    gap_denominator = baseline_mean_c - _COMFORT_THRESHOLD_C
    if gap_denominator > 0:
        comfort_gap_pct: float | None = round(
            utci_delta_c / gap_denominator * 100.0, 6
        )
        comfort_gap_label = "DERIVED"
        comfort_gap_note = (
            f"= utci_delta_c / (baseline_mean_c − {_COMFORT_THRESHOLD_C:.0f}) × 100; "
            "% of the (UTCI − 26) comfort gap closed over the target shaded cells."
        )
    else:
        comfort_gap_pct = None
        comfort_gap_label = "PLACEHOLDER"
        comfort_gap_note = (
            f"baseline_mean_c ({baseline_mean_c}) is at/below the {_COMFORT_THRESHOLD_C:.0f} °C "
            "comfort threshold — no comfort gap to close; null, not a fabricated value."
        )

    # ── D-05b: € per °C = cost_total_eur / utci_delta_c (Q4 placeholder discipline) ───────
    # cost==0 (free recovered demo material) OR a zero/negative delta → DISCLOSE a labelled
    # placeholder, NEVER print a misleading numeric 0 €/°C (threat T-05b-09).
    if cost_total_eur > 0 and utci_delta_c > 0:
        eur_per_deg_c: dict = {
            "value_eur_per_c": round(cost_total_eur / utci_delta_c, 6),
            "placeholder": False,
            "cost_total_eur": cost_total_eur,
            "provenance": "DERIVED",
            "note": "= Phase-5 cost_total_eur / utci_delta_c (Q4 numerator).",
        }
    else:
        eur_per_deg_c = {
            "value_eur_per_c": None,
            "placeholder": True,
            "cost_total_eur": cost_total_eur,
            "provenance": "PLACEHOLDER",
            "note": (
                "free recovered material in the demo (cost_total_eur = 0.0); €/°C is a "
                "PLACEHOLDER, NOT a real 0 €/°C. Computes normally once a non-zero Phase-5 "
                "cost_total_eur lands."
            ),
        }

    # ── D-05c: baseline conditions inline (falsifiable on its face) ───────────────────────
    baseline_conditions = {
        "site": SITE_NAME,
        "latlon": list(SITE_LATLON),
        "date": brief_date,  # None until the orchestrator threads the brief date
        "peak_band": PEAK_BAND_LABEL,
        "baseline_mean_c": baseline_mean_c,
        "coverage_basis": coverage_basis,
        "sky_albedo": _SKY_ALBEDO_LABEL,
    }

    # ── D-06: predicted-vs-measured ISO-7726 seam (measured is ALWAYS null in v1) ─────────
    predicted_vs_measured = {
        "predicted_utci_delta_c": utci_delta_c,
        "measured_utci_delta_c": None,  # reserved placeholder — NEVER fabricated
        "monitoring_protocol": _MONITORING_PROTOCOL,
    }

    return {
        "schema_version": SIDECAR_VERSION,  # "1.0.0-sidecar" — NON-contract marker
        # D-05 metrics
        "comfort_gap_pct": comfort_gap_pct,
        "eur_per_deg_c": eur_per_deg_c,
        "coverage_pct": round(coverage_pct, 6),
        # D-05 baseline-inline
        "baseline_conditions": baseline_conditions,
        # D-06 measured seam (flattened for the test's direct asserts AND nested for the dossier)
        "predicted_utci_delta_c": utci_delta_c,
        "measured_utci_delta_c": None,
        "predicted_vs_measured": predicted_vs_measured,
        # provenance tiers — every reported number carries its tag (instructor non-negotiable)
        "provenance_labels": {
            "comfort_gap_pct": comfort_gap_label,
            "comfort_gap_note": comfort_gap_note,
            "eur_per_deg_c": eur_per_deg_c["provenance"],
            "coverage_pct": "DERIVED",
            "utci_delta_c": "DERIVED (ASSUMED ideal_delta × (1−τ) over GROUNDED baseline)",
            "baseline_mean_c": "GROUNDED",
            "measured_utci_delta_c": "PLACEHOLDER (reserved; ISO 7726 — never fabricated)",
        },
    }
