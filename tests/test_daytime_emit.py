"""DAYCROWD-03 — timestamps sidecar + per-hour density lattice snap (crowdsim tier).

The emit path kills the old ``% maxT`` modulo wall-clock loop: instead of deriving an hour by
modulo over total steps, every recorded frame carries an explicit ``timestamps`` index entry. Three
behaviours:

1. **Sidecar length** — ``timestamps`` length == number of recorded frames; ``timestamps[0]`` maps
   to "09:00" and the last to the final daytime hour.
2. **Wall-clock from timestamps, NOT modulo** — frame ``i``'s wall-clock is derivable PURELY from
   ``timestamps[i]`` (the index is monotonic non-decreasing; no ``% maxT`` wrap needed). This makes
   the "modulo eliminated" claim a real assertion.
3. **Lattice snap** — a per-hour density slice round-trips through the FROZEN ``build_crowd_grid`` on
   the SAME lattice object (XFN-04 byte-equality).

``@pytest.mark.crowdsim``: runs the real emit path. DESIGNED-RED at Wave 0 — imports the
not-yet-written ``crowd.daytime_runner`` (Plan 04 turns it GREEN). Skip-guarded so it COLLECTS
cleanly with no jupedsim installed.
"""

from __future__ import annotations

import importlib.util

import pytest

from conftest_crowdsim import crowdsim_real_site_project  # noqa: F401
from crowd.constants import DAYTIME_HOURS

pytestmark = pytest.mark.crowdsim

_HELPER_PRESENT = importlib.util.find_spec("crowd.daytime_runner") is not None

if _HELPER_PRESENT:  # pragma: no cover - exercised once Plan 04 ships the runner
    from crowd.daytime_runner import run_daytime  # noqa: F401

_skip_no_engine = pytest.mark.skipif(
    not _HELPER_PRESENT,
    reason="crowd.daytime_runner absent — Wave-0 RED scaffold (GREEN at Plan 04)",
)

_CAPACITY = 1500


@_skip_no_engine
def test_timestamps_sidecar_length_equals_recorded_frames(tmp_path):
    """The emitted payload carries a `timestamps` index of length == n recorded frames; ends frame-mapped.

    ``timestamps[0]`` is "09:00", ``timestamps[-1]`` is the final daytime hour, and the index length
    equals the number of recorded frames in the per-frame density/trajectory payload.
    """
    crowdsim_real_site_project(tmp_path, "emit_a", capacity=_CAPACITY)
    from crowd.daytime_runner import run_daytime

    payload = run_daytime("emit_a", projects_root=tmp_path, seed=1789)

    assert "timestamps" in payload, "emit payload missing the `timestamps` sidecar (DAYCROWD-03)"
    timestamps = payload["timestamps"]
    assert len(timestamps) == payload["n_frames"]
    assert timestamps[0] == "09:00"
    assert timestamps[-1] == DAYTIME_HOURS[-1]


@_skip_no_engine
def test_wallclock_is_derived_from_timestamps_not_modulo(tmp_path):
    """Wall-clock comes from `timestamps[i]` alone — no `% maxT` wrap (the modulo loop is gone).

    Asserts the payload CONTAINS a `timestamps` key whose length == n recorded frames, that it is
    monotonic non-decreasing (sorted == itself), and that the endpoints pin to 09:00 / the last
    daytime hour — i.e. an arbitrary frame ``i``'s HH:MM is read straight from ``timestamps[i]`` with
    NO modulo over total steps. This is the "% maxT eliminated" claim, made a real assertion.
    """
    crowdsim_real_site_project(tmp_path, "emit_b", capacity=_CAPACITY)
    from crowd.daytime_runner import run_daytime

    payload = run_daytime("emit_b", projects_root=tmp_path, seed=1789)
    timestamps = payload["timestamps"]

    assert len(timestamps) == payload["n_frames"]
    # Monotonic non-decreasing — frame i's wall-clock is timestamps[i], no wrap-around modulo.
    assert timestamps == sorted(timestamps), (
        "timestamps not monotonic — a modulo/wrap wall-clock leaked back in (DAYCROWD-03)"
    )
    assert timestamps[0] == "09:00"
    assert timestamps[-1] == DAYTIME_HOURS[-1]


@_skip_no_engine
def test_per_hour_density_snaps_to_lattice(tmp_path):
    """A per-hour density slice round-trips through FROZEN build_crowd_grid on the SAME lattice (XFN-04).

    The per-hour crowd density is produced by the FROZEN ``crowd.grid.build_crowd_grid`` reading the
    SAME lattice object the run was seeded with (identity, not a copy) — byte-equal lattice, integer
    snap. This holds the daytime emit to the established lattice-snap contract.
    """
    crowdsim_real_site_project(tmp_path, "emit_c", capacity=_CAPACITY)
    from crowd.daytime_runner import run_daytime

    payload = run_daytime("emit_c", projects_root=tmp_path, seed=1789)

    assert "per_hour_density" in payload
    lattice = payload["lattice"]
    for hour_slice in payload["per_hour_density"]:
        assert hour_slice["lattice"] == lattice, (
            "per-hour density slice carries a different lattice than the run lattice — "
            "XFN-04 byte-equality broken (DAYCROWD-03)"
        )
