"""GATE-02 — (1−τ) ΔUTCI over the shaded priority cells (DESIGNED-RED, Wave 0).

Designed-RED: imports ``from acceptance.delta import ...`` at module level, so collection ERRORS
with ``ModuleNotFoundError: No module named 'acceptance.delta'`` until the Wave-2 transform ships.
That collection error IS the Wave-0 success state; do NOT stub ``acceptance.delta`` to pass.

Load-bearing assertions (RESEARCH §GATE-02, Pitfall 2/3 + Pitfall 4):
  * test_tau_direction — higher τ → SMALLER ΔUTCI → harder to pass (the single most important
    honesty assertion; a ``·τ`` sign flip would overstate cooling for the loosest membranes).
  * test_baseline_grounded — the delta reads each cell's persisted ``baseline_utci_c`` (never a
    re-derived / grid-mean value); no infrared / live import is reachable from the gate.
  * test_mean_delta — the mean ΔUTCI over the shaded priority set equals ideal·(1−τ).
"""

from __future__ import annotations

import importlib.util

# DESIGNED-RED import: errors at collection until acceptance.delta ships (Wave 2).
from acceptance.delta import mean_shaded_delta

from acceptance.constants import IDEAL_DELTA_C_ASSUMED
from conftest_acceptance import synthetic_priority_set


def test_tau_direction():
    """Higher τ → smaller ΔUTCI (Pitfall 2/3 — honesty-critical).

    For the SAME ideal geometric cooling and the SAME shaded cells, a loose membrane (τ=0.4) must
    cool LESS than a tight one (τ=0.15). A ``·τ`` sign flip would reverse this and silently overstate
    cooling for the worst membranes.
    """
    cells = synthetic_priority_set()["cells"][:3]  # the 3 shaded cells
    loose = mean_shaded_delta(cells, ideal_delta_c=IDEAL_DELTA_C_ASSUMED, tau=0.40)
    tight = mean_shaded_delta(cells, ideal_delta_c=IDEAL_DELTA_C_ASSUMED, tau=0.15)
    assert loose < tight, f"higher τ must yield SMALLER delta (got loose={loose}, tight={tight})"


def test_mean_delta():
    """Mean ΔUTCI over the shaded priority set = ideal·(1−τ) (the demo path clears X=4)."""
    cells = synthetic_priority_set()["cells"][:3]
    delta = mean_shaded_delta(cells, ideal_delta_c=8.0, tau=0.40)
    assert delta == 8.0 * (1.0 - 0.40), delta  # 4.8 °C — clears X=4 through the real (1−τ) path


def test_baseline_grounded():
    """The delta reads persisted ``baseline_utci_c`` per cell, never a re-derived/grid-mean value.

    The gate must consume the byte-stable baseline; mutating one cell's ``baseline_utci_c`` must be
    visible to a baseline-grounded computation (proving it reads the persisted value, not a constant
    grid mean). Also assert no infrared/live module is reachable from the gate (Pitfall 4: never a
    second API call).
    """
    base = synthetic_priority_set()["cells"][:3]
    bumped = [dict(c, baseline_utci_c=c["baseline_utci_c"] + 5.0) for c in base]
    grounded = mean_shaded_delta(base, ideal_delta_c=8.0, tau=0.40, ground_to_baseline=True)
    bumped_delta = mean_shaded_delta(bumped, ideal_delta_c=8.0, tau=0.40, ground_to_baseline=True)
    assert grounded != bumped_delta, "delta must read the persisted baseline_utci_c, not ignore it"
    # Pitfall 4: the gate tier must never reach an infrared/live import.
    assert importlib.util.find_spec("acceptance.delta") is not None
    import acceptance.delta as _d

    src = _d.__file__ or ""
    text = open(src, encoding="utf-8").read() if src else ""
    assert "infrared" not in text and "import live" not in text, "gate must not re-run the sim"
