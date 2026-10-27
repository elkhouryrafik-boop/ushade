"""DAYCROWD-04 determinism limb — byte-identical per-hour field on two same-seed runs (crowdsim tier).

Two same-seed daytime runs in SEPARATE project dirs (two genuine cache MISSES — real continuous
rollouts, not a cache replay) must produce a BYTE-IDENTICAL per-hour crowd density field.
Determinism is asserted at the INTEGER ``snap_to_lattice`` field, NOT raw CFSM positions: the integer
snap quantises sub-cell ODE float jitter away, so the field is reproducible even though raw positions
need not be byte-identical cross-platform (Pitfall 4.3). MIRRORS
``tests/test_crowdsim_determinism.py`` exactly — single-process, seed pinned, two genuine misses.

``@pytest.mark.crowdsim``: runs the real continuous path. DESIGNED-RED at Wave 0 — imports the
not-yet-written run path (``crowd.daytime_runner.run_daytime``; Plan 04 turns it GREEN). Skip-guarded
so it COLLECTS cleanly with no jupedsim installed.
"""

from __future__ import annotations

import importlib.util

import pytest

from conftest_crowdsim import crowdsim_real_site_project  # noqa: F401

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
def test_continuous_run_is_byte_identical_at_lattice_field(tmp_path):
    """Two independent same-seed daytime runs → a BYTE-IDENTICAL per-hour density field (DAYCROWD-04).

    Each run lives in its OWN project dir (two genuine cache MISSES — real continuous rollouts, not a
    cache replay). Same seed → identical lattice-snapped per-hour density field byte-for-byte. The
    equality is asserted at the INTEGER ``snap_to_lattice`` field (the persisted per-hour density),
    NOT raw CFSM positions: the integer snap quantises the sub-cell float jitter (Pitfall 4.3).
    Mirrors ``test_crowdsim_determinism.py::test_same_seed_byte_identical_grid``.
    """
    from crowd.daytime_runner import run_daytime

    crowdsim_real_site_project(tmp_path, "daydet_a", capacity=_CAPACITY)
    crowdsim_real_site_project(tmp_path, "daydet_b", capacity=_CAPACITY)

    payload_a = run_daytime("daydet_a", projects_root=tmp_path, seed=1789)
    payload_b = run_daytime("daydet_b", projects_root=tmp_path, seed=1789)

    import json

    field_a = json.dumps(payload_a["per_hour_density"], sort_keys=True)
    field_b = json.dumps(payload_b["per_hour_density"], sort_keys=True)
    assert field_a == field_b, (
        "same seed produced differing per-hour density fields — daytime determinism broken "
        "(DAYCROWD-04). Determinism must hold at the integer snap_to_lattice field, not raw CFSM "
        "positions (Pitfall 4.3); check the seed plumbing and fixed spawn order."
    )
