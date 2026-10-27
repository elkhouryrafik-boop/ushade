"""DAYCROWD-02/03 — ONE rectangular trajectory across all daytime intervals (crowdsim tier).

The continuous run does NOT restart the sim each hour (the old per-slice modulo loop). It produces
ONE continuous trajectory spanning every interval: a single ``(steps × agents × 4)`` array whose
agent column count is CONSTANT (the rectangular population) and whose step count is the documented
concatenated horizon ``FRAMES_PER_HOUR_JPS × (len(DAYTIME_HOURS) - 1)`` (11 intervals × 1400).

``@pytest.mark.crowdsim``: runs the real continuous path on the real-site geometry. DESIGNED-RED at
Wave 0 — imports the not-yet-written ``crowdsim.continuous`` (Plan 03 turns it GREEN). Skip-guarded
so it COLLECTS cleanly with no jupedsim installed.
"""

from __future__ import annotations

import importlib.util

import pytest

from conftest_crowdsim import crowdsim_real_site_project  # noqa: F401
from crowd.constants import DAYTIME_HOURS, FRAMES_PER_HOUR_JPS

pytestmark = pytest.mark.crowdsim

_HELPER_PRESENT = importlib.util.find_spec("crowdsim.continuous") is not None

if _HELPER_PRESENT:  # pragma: no cover - exercised once Plan 03 ships the engine
    from crowdsim.continuous import run_continuous_daytime  # noqa: F401

_skip_no_engine = pytest.mark.skipif(
    not _HELPER_PRESENT,
    reason="crowdsim.continuous absent — Wave-0 RED scaffold (GREEN at Plan 03)",
)

# A modest capacity keeps the smoke fast while still exercising multi-agent CFSM migration physics.
_CAPACITY = 1500


@_skip_no_engine
def test_one_rectangular_trajectory_across_intervals(tmp_path):
    """A continuous run → ONE (steps × agents × 4) array, constant agent column, full daytime horizon.

    ``steps == FRAMES_PER_HOUR_JPS * (len(DAYTIME_HOURS) - 1)`` (the 11-interval concat length) and
    the agent column count is identical at the first and last recorded frame (rectangular population,
    nobody spawned/culled mid-day). This is the "one trajectory, no per-slice modulo restart" claim
    made testable.
    """
    crowdsim_real_site_project(tmp_path, "cont", capacity=_CAPACITY)
    from crowdsim.continuous import run_continuous_daytime

    traj = run_continuous_daytime("cont", projects_root=tmp_path, seed=1789)

    assert traj.ndim == 3 and traj.shape[2] == 4
    expected_steps = FRAMES_PER_HOUR_JPS * (len(DAYTIME_HOURS) - 1)
    assert traj.shape[0] == expected_steps, (
        f"continuous trajectory has {traj.shape[0]} steps, expected the 11-interval concat "
        f"{expected_steps} (DAYCROWD-02/03 — one trajectory, no per-slice restart)"
    )
    # Constant agent column count across the whole run (rectangular invariant).
    assert traj.shape[1] >= 1
    first_frame_agents = traj[0].shape[0]
    last_frame_agents = traj[-1].shape[0]
    assert first_frame_agents == last_frame_agents == traj.shape[1]
