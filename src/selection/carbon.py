"""Transport carbon + cost roll-up + the ONE carbon-vs-tent comparison — all tau-FREE.

This module owns the two numbers the Golden Rule keeps material/transport-only:

  * ``transport_carbon`` = ``2 * Distance_km * Mass_tonnes * transport_mode_factor`` (the
    frozen ``data/materials.json`` ``_meta.carbon_formula``, verbatim). Recycled cut-off,
    manufacturing = 0 (ASSUMED, ISO 14044 §4.3.4). The ``2 *`` is the round trip — do NOT
    double the routing distance.
  * ``cost_rollup`` = ``quantity * cost_per_unit`` summed into the locked budget (D-02).

NON-NEGOTIABLE (CLAUDE.md / Pitfall 1): NEITHER signature carries tau. tau is a thermal
property handled in ``cooling.py`` ONLY; letting it leak here would fabricate a relationship
the PRD explicitly decoupled. ``test_tau_not_in_cost_or_carbon`` asserts both outputs are
byte-identical across tau (they cannot accept it).

``tent_comparison`` is the ONE D-13 capped comparison (ICE v2.0, ASSUMED-labelled).
``ledger_carbon_entries`` routes the carbon numbers through ``ledger.carbon()`` (which forces
the ASSUMED tier — the path of least resistance, never a hand-written tier string).
"""

from __future__ import annotations

# transport_mode_factor: 0.10 HGV-equivalent PLACEHOLDER (kgCO2e per tonne-km, road), pending
# DEFRA/EPD-grade sourcing. Disclosed ASSUMED inline + in the ledger (D-04, MAT-05, Pitfall 7).
DEFAULT_TRANSPORT_MODE_FACTOR = 0.10

# D-13 ONE carbon-vs-single-use-tent baseline (ICE v2.0, conservative ~4 kgCO2e/m2 — fabric
# only, frame excluded, so the reuse saving is never overclaimed). Q4 of 05-RESEARCH.
TENT_BASELINE_KGCO2E_PER_M2 = 4.0
TENT_SOURCE = (
    "single-use PVC marquee baseline, ICE v2.0 (Hammond & Jones, Univ. of Bath), "
    "PVC 5.6 kgCO2e/kg A1-A3, ~0.7 kg/m2 fabric ASSUMED"
)


def transport_carbon(
    qty: float,
    unit_mass_kg: float,
    distance_km: float,
    factor: float = DEFAULT_TRANSPORT_MODE_FACTOR,
) -> float:
    """Transport carbon = ``2 * Distance_km * Mass_tonnes * transport_mode_factor`` (MAT-02).

    ``Mass_tonnes = (qty * unit_mass_kg) / 1000``. The ``2 *`` is the round trip. There is NO
    ``tau`` parameter — carbon is transport-only (Golden Rule, Pitfall 1).
    """
    mass_tonnes = (qty * unit_mass_kg) / 1000.0
    return 2.0 * distance_km * mass_tonnes * factor


def cost_rollup(qty: float, cost_per_unit: float) -> float:
    """Financial roll-up = ``quantity * cost_per_unit`` (MAT-03, D-02). NO ``tau`` parameter."""
    return qty * cost_per_unit


def tent_comparison() -> dict:
    """The ONE D-13 ASSUMED-labelled carbon-vs-single-use-tent baseline (ICE v2.0).

    Exactly one comparison, capped — do NOT add a second (no cradle-to-grave variant, no
    per-event total). Framed as avoided burden, never regeneration (instructor).
    """
    return {
        "label": "ASSUMED",
        "baseline_kgco2e_per_m2": TENT_BASELINE_KGCO2E_PER_M2,
        "source": TENT_SOURCE,
    }


def ledger_carbon_entries(
    ledger,
    *,
    transport_carbon_kgco2e: float,
    stage: str,
    distance_km: float,
    factor: float = DEFAULT_TRANSPORT_MODE_FACTOR,
) -> None:
    """Append the carbon provenance: transport carbon + tent baseline ASSUMED, factor ASSUMED.

    ``ledger.carbon(...)`` FORCES the ASSUMED tier (recycled cut-off, manufacturing = 0) so the
    correct tier is the path of least resistance — never a hand-written tier string (CLAUDE.md).
    The 0.10 placeholder is disclosed via ``ledger.assumed(...)`` (Pitfall 7).
    """
    ledger.carbon(
        "transport_carbon_kgco2e",
        transport_carbon_kgco2e,
        stage,
        unit="kgco2e",
        formula="2 * Distance_km * Mass_tonnes * transport_mode_factor",
        inputs=["distance_km", "unit_mass_kg", "quantity", "transport_mode_factor"],
    )
    ledger.carbon(
        "tent_baseline_kgco2e_per_m2",
        TENT_BASELINE_KGCO2E_PER_M2,
        stage,
        source=TENT_SOURCE,
        unit="kgco2e",
    )
    ledger.assumed(
        "transport_mode_factor",
        factor,
        "0.10 HGV-equivalent PLACEHOLDER (kgCO2e/tonne-km, road); pending DEFRA/EPD-grade sourcing",
        stage,
    )
