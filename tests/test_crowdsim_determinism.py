"""Same-process double-run determinism at the lattice-snapped density field (CROWD-10).

On a pinned ``jupedsim`` version, two same-seed runs in SEPARATE project dirs (two genuine cache
MISSES — real JuPedSim rollouts, not a cache replay) must write a BYTE-IDENTICAL
``crowd_grid.json``. Determinism is asserted at the lattice-snapped INTEGER density field, NOT raw
trajectories: the integer ``snap_to_lattice`` quantises sub-cell CFSM float jitter away, so the
field is reproducible even though the raw ODE positions need not be byte-identical cross-platform
(Pitfall 4.3). The recipe: seed ``distribute_by_number(seed=SEED)``, fixed (gate-then-index) spawn
order, single-process, version pinned in the cache key.

``@pytest.mark.crowdsim``: runs the real JuPedSim path. DESIGNED-RED at Wave 0 (no engine yet);
GREEN at Wave 3. There is NO ``@pytest.mark.xfail`` (the old PPO obs-dim xfail is retired). Collects
cleanly today.
"""

from __future__ import annotations

import pytest

# conftest_crowdsim is imported EXPLICITLY (not auto-loaded).
from conftest_crowdsim import crowdsim_real_site_project
from crowd.crowd import run_crowd_stage

pytestmark = pytest.mark.crowdsim

# A modest capacity keeps the smoke fast while still exercising the multi-agent CFSM physics.
_CAPACITY = 1500  # N = 1500 // AGENT_DIVISOR = 15 agents (multi-gate, > 1)


def test_same_seed_byte_identical_grid(tmp_path):
    """Two independent same-seed real runs write a byte-identical crowd_grid.json (CROWD-10).

    Each run lives in its OWN project dir → both are genuine cache MISSES (real JuPedSim rollouts,
    not a cache replay). Same seed → identical lattice-snapped density field, dwell_zones, and
    flow_vectors — byte-for-byte on disk. The determinism comes from the SEED + the integer snap,
    not the cache.
    """
    pdir_a = crowdsim_real_site_project(tmp_path, "det_a", capacity=_CAPACITY)
    pdir_b = crowdsim_real_site_project(tmp_path, "det_b", capacity=_CAPACITY)

    artifact_a = run_crowd_stage("det_a", projects_root=tmp_path)
    artifact_b = run_crowd_stage("det_b", projects_root=tmp_path)

    raw_a = (pdir_a / "crowd_grid.json").read_text(encoding="utf-8")
    raw_b = (pdir_b / "crowd_grid.json").read_text(encoding="utf-8")
    assert raw_a == raw_b, (
        "same seed produced differing crowd_grid.json on disk — JuPedSim determinism broken "
        "(CROWD-10). Check the distribute_by_number(seed=SEED) plumbing, the fixed gate-then-index "
        "spawn order, and that the integer snap quantises the CFSM float jitter (Pitfall 4.3)."
    )
    # The in-memory returns agree too (persisted == returned).
    assert artifact_a == artifact_b
