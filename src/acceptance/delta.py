"""GATE-02 — (1−τ) mean ΔUTCI over the shaded priority cells vs the persisted baseline (D-03).

The cooling claim is ``actual_delta = ideal_delta · (1 − τ)`` per shaded priority cell, where
τ (the selected membrane's ``solar_transmissivity``) enters EXACTLY one place — the
``selection.cooling.cooling_estimate`` call. There is NO second ``1 - tau`` literal in this
file: a sign flip or a duplicated correction would silently overstate cooling for the loosest
(worst) membranes, so the direction is made structural by reusing the single τ site.

Direction (honesty-critical, Pitfall 2/3): higher τ → smaller ``(1−τ)`` → SMALLER delta →
HARDER to pass. ``test_tau_direction`` asserts ``delta(τ=0.4) < delta(τ=0.15)``.

Baseline (Pitfall 4): the denominator/anchor is each cell's PERSISTED ``baseline_utci_c`` —
read from the byte-stable ``utci_grid.json``, NEVER re-derived, NEVER a grid-wide mean, NEVER a
second climate-sim API call (no such import is reachable from this module). The default delta
path returns the pure ``ideal·(1−τ)`` magnitude; the ``ground_to_baseline`` path additionally
anchors the realizable cooling to how far each cell sits above the comfort floor (you cannot
cool a cell below comfort, nor beyond the geometric ideal), so a mutated persisted baseline is
VISIBLE in the output (``test_baseline_grounded``).

PROVENANCE: the returned ΔUTCI is **DERIVED**, never GROUNDED — it is the arithmetic of an
ASSUMED ``ideal_delta`` (``constants.IDEAL_DELTA_C_ASSUMED``, Q3) × the (1−τ) correction over a
GROUNDED baseline. Flip ``ideal_delta`` to a grounded source ONLY when a real shaded sim lands
(threat T-05b-03).

BASE TIER — NON-NEGOTIABLE: numpy + selection.cooling only. The gate never re-runs the climate
sim and never imports the paid SDK or any heavy geometry/ML dependency.
"""

from __future__ import annotations

import numpy as np

# The comfort floor (26 °C) is the SAME PRD constant Phase 3 uses for score>0 funding — reused,
# never re-inlined, so the gate's "cannot cool below comfort" anchor cannot drift from it.
from core.constants import COMFORT_THRESHOLD_C

# τ enters ONLY here — the single (1−τ) site (selection.cooling). NO `1 - tau` literal below.
from selection.cooling import cooling_estimate

from acceptance.constants import IDEAL_DELTA_C_ASSUMED


def _baseline_for_cell(cell: dict) -> float:
    """Read a cell's PERSISTED ``baseline_utci_c`` — never fabricate or re-derive one.

    The shaded-priority cells carry the byte-stable baseline forward from ``utci_grid.json``;
    a shaded priority cell with no persisted baseline is a contract violation (the baseline is
    the locked denominator, baseline_spec.md), so this raises rather than inventing a value.
    """
    if "baseline_utci_c" not in cell:
        raise KeyError(
            "shaded priority cell carries no persisted baseline_utci_c; the GATE-02 "
            "denominator must be the byte-stable baseline, never re-derived (Pitfall 4)"
        )
    return float(cell["baseline_utci_c"])


def mean_shaded_delta(
    shaded_priority: list[dict],
    *,
    ideal_delta_c: float | None = None,
    tau: float,
    ground_to_baseline: bool = False,
) -> float:
    """Mean (1−τ) ΔUTCI over the shaded priority set (GATE-02).

    Per cell the realizable cooling is ``cooling_estimate(ideal_delta_c, tau)`` = ``ideal·(1−τ)``
    — τ via the ONE ``selection.cooling`` site (no second literal). The mean over the shaded
    priority cells is returned (numpy). ``ideal_delta_c`` defaults to the ASSUMED Q3 constant
    ``IDEAL_DELTA_C_ASSUMED``.

    Default path (``ground_to_baseline=False``): returns the pure ``ideal·(1−τ)`` magnitude —
    the demo path that clears X=4 (8·0.6 = 4.8). ``test_mean_delta`` / ``test_tau_direction``.

    Grounded path (``ground_to_baseline=True``): anchors each cell's ideal to the persisted
    baseline — the realizable τ=0 cooling cannot exceed how far the cell sits above the comfort
    floor (``baseline_utci_c − COMFORT_THRESHOLD_C``) nor the geometric ideal, so a mutated
    persisted baseline is VISIBLE in the result (``test_baseline_grounded``). The baseline is
    READ from each cell, never re-derived.
    """
    if not shaded_priority:
        return 0.0

    ideal = IDEAL_DELTA_C_ASSUMED if ideal_delta_c is None else ideal_delta_c

    per_cell: list[float] = []
    for cell in shaded_priority:
        if ground_to_baseline:
            # The realizable τ=0 cooling at this cell: bounded by the gap above the comfort
            # floor (cannot cool below comfort) AND by the geometric ideal. Reads the PERSISTED
            # baseline_utci_c — a mutated baseline changes this gap, so it is observable.
            baseline = _baseline_for_cell(cell)
            comfort_gap = max(0.0, baseline - COMFORT_THRESHOLD_C)
            cell_ideal = min(ideal, comfort_gap)
        else:
            cell_ideal = ideal
        # τ enters ONLY via cooling_estimate (= cell_ideal * (1 - tau)); no second (1−τ) site.
        per_cell.append(cooling_estimate(cell_ideal, tau))

    return float(np.mean(per_cell))
