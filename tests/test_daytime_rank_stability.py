"""DAYCROWD-05 — worst-HOUR rank stability under perturbation (BASE tier, no marker).

The decision-relevant output of the demand model is WHICH hour is busiest (the hot-hour that drives
shade placement). That ranking must be ROBUST to ASSUMED-grade inputs: a small shift in the program
hours, a small occupancy nudge, or a different organiser arrival-profile must NOT swing the worst
hour wildly. The gate: under each perturbation the worst (busiest) HOUR moves ≤ one slot in
``DAYTIME_HOURS``.

BASE tier (no jupedsim): the per-hour total demand vector is a pure transform of the demand table.
DESIGNED-RED at Wave 0 (the demand helper ships in Plan 02); skip-guarded so it COLLECTS cleanly.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from crowd.constants import DAYTIME_HOURS

_HELPER_PRESENT = importlib.util.find_spec("crowd.daytime_demand") is not None
pytestmark = pytest.mark.skipif(
    not _HELPER_PRESENT,
    reason="crowd.daytime_demand absent — Wave-0 RED scaffold (GREEN at Plan 02)",
)

if _HELPER_PRESENT:  # pragma: no cover - exercised once Plan 02 ships the helper
    from crowd.daytime_demand import per_hour_total_demand  # noqa: F401

_DATA = Path(__file__).resolve().parents[1] / "src" / "crowd" / "data"
_PROGRAM = json.loads((_DATA / "daytime_program_2026.json").read_text(encoding="utf-8"))
_OCCUPANCY = json.loads((_DATA / "occupancy_curve_2026.json").read_text(encoding="utf-8"))


def _worst_hour_index(program: dict, occupancy: dict, profile: str) -> int:
    """Index in DAYTIME_HOURS of the busiest hour for one (program, occupancy, profile)."""
    from crowd.daytime_demand import per_hour_total_demand

    totals = per_hour_total_demand(program=program, occupancy=occupancy, profile=profile)
    return max(range(len(totals)), key=lambda i: totals[i])


def _shift_program_hours(program: dict, delta: int) -> dict:
    """Return a copy of the program with every active hour shifted by ±delta slots (clamped)."""
    shifted = copy.deepcopy(program)
    for stage in shifted["stage_program"].values():
        new_hours = []
        for h in stage["active_hours"]:
            idx = DAYTIME_HOURS.index(h)
            j = min(max(idx + delta, 0), len(DAYTIME_HOURS) - 1)
            new_hours.append(DAYTIME_HOURS[j])
        stage["active_hours"] = sorted(set(new_hours))
    return shifted


def _nudge_occupancy(occupancy: dict, profile: str, eps: float) -> dict:
    """Return a copy of the occupancy curve with the profile's values nudged by ±eps (clamped 0-1)."""
    nudged = copy.deepcopy(occupancy)
    occ = nudged["profiles"][profile]["occupancy"]
    nudged["profiles"][profile]["occupancy"] = [min(max(v + eps, 0.0), 1.0) for v in occ]
    return nudged


def test_worst_hour_moves_at_most_one_slot():
    """The busiest hour moves ≤ 1 slot under ±1h shift, ±0.1 occupancy, and each of the 3 profiles.

    Baseline worst hour = default profile, committed data. Each perturbation must keep the worst
    hour within one ``DAYTIME_HOURS`` slot of the baseline (DAYCROWD-05 rank stability on ASSUMED
    demand).
    """
    default_profile = _OCCUPANCY["default_profile"]
    baseline = _worst_hour_index(_PROGRAM, _OCCUPANCY, default_profile)

    perturbations: list[tuple[str, dict, dict, str]] = []
    for delta in (+1, -1):
        perturbations.append((f"shift{delta:+d}h", _shift_program_hours(_PROGRAM, delta), _OCCUPANCY, default_profile))
    for eps in (+0.1, -0.1):
        perturbations.append((f"occ{eps:+.1f}", _PROGRAM, _nudge_occupancy(_OCCUPANCY, default_profile, eps), default_profile))
    for profile in _OCCUPANCY["profiles"]:
        perturbations.append((f"profile={profile}", _PROGRAM, _OCCUPANCY, profile))

    for label, prog, occ, profile in perturbations:
        worst = _worst_hour_index(prog, occ, profile)
        assert abs(worst - baseline) <= 1, (
            f"worst hour moved >1 slot under {label}: baseline={DAYTIME_HOURS[baseline]} "
            f"-> {DAYTIME_HOURS[worst]} (DAYCROWD-05 rank instability)"
        )
