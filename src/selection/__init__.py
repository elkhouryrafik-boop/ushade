"""Phase-5 material selection core (MAT-01..06, D-06/12/14).

Soft-filter the frozen 10 by theme, gate on inventory availability, select the
minimum-transport-carbon AVAILABLE membrane, roll cost into the locked budget, apply the
amended Golden-Rule (1 - tau) cooling correction, and emit the three reporting artifacts.

tau enters EXACTLY one place (``cooling``); carbon/cost are transport-only and tau-free.
"""

from __future__ import annotations

from selection.carbon import (
    cost_rollup,
    ledger_carbon_entries,
    tent_comparison,
    transport_carbon,
)
from selection.cooling import cooling_correction_factor, cooling_estimate
from selection.reporting import mass_balance, next_life
from selection.selection import (
    load_materials,
    run_selection_stage,
    select_from_live_inventory,
    select_material,
)

__all__ = [
    "transport_carbon",
    "cost_rollup",
    "tent_comparison",
    "ledger_carbon_entries",
    "cooling_estimate",
    "cooling_correction_factor",
    "mass_balance",
    "next_life",
    "load_materials",
    "select_material",
    "run_selection_stage",
    "select_from_live_inventory",
]
