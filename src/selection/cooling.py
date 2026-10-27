"""The (1 - tau) cooling correction — the ONLY module that accepts tau (MAT-04, D-03).

The 2026-06-09 Golden-Rule amendment re-couples cooling to the membrane's solar
transmissivity: a selected membrane's geometric cooling is scaled by ``(1 - tau)``, so a
loose net (high tau) cools LESS than a solid tarp (low tau). This is the load-bearing
honesty seam that feeds the Phase 5b cooling-acceptance gate.

NON-NEGOTIABLE (CLAUDE.md / Pitfall 1+2): tau enters EXACTLY one place — here. The carbon
and cost transforms (``carbon.py``) carry NO tau parameter, so cost/carbon are byte-identical
across tau (the Golden Rule keeps carbon material/transport-only). And the direction is
``(1 - tau)`` — NEVER ``tau`` (Pitfall 2: a sign flip would silently overstate cooling for
the worst, loosest membranes).
"""

from __future__ import annotations


def cooling_correction_factor(tau: float) -> float:
    """The DERIVED Phase-5b cooling correction = ``1 - tau``, a number in [0, 1].

    tau is the membrane's solar_transmissivity (fraction of solar radiation passing
    THROUGH). The fraction blocked — and therefore the cooling fraction — is ``1 - tau``.
    A sign flip (returning ``tau``) is Pitfall 2 and is caught by ``test_tau_direction``.
    """
    return 1.0 - tau


def cooling_estimate(geometric_cooling: float, tau: float) -> float:
    """Scale a geometric cooling estimate by the (1 - tau) correction (MAT-04).

    ``cooling_estimate(g, 0.40) < cooling_estimate(g, 0.15)`` for the same ``g`` — higher
    tau yields LESS cooling. Takes NO cost/carbon argument: tau touches cooling ONLY.
    Single expression so the direction cannot drift (Pitfall 2).
    """
    return geometric_cooling * cooling_correction_factor(tau)
