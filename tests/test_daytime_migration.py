"""DAYCROWD-02 — popularity-delta migration SELECTION (crowdsim tier).

At each hour boundary the persistent population re-allocates: a deterministic cohort of agents
SHEDS from stages whose pull dropped and is RECEIVED by stages whose pull rose (popularity-delta
selection). Two invariants make the migration honest:

1. **Determinism** — same inputs → identical switch cohort, every time (no RNG drift).
2. **Conservation** — the population is RECTANGULAR: shed-total == receive-total, the agent count is
   constant across every boundary (nobody is spawned or culled mid-day; they MIGRATE).

``@pytest.mark.crowdsim``: needs the continuous run path. DESIGNED-RED at Wave 0 — imports the
not-yet-written ``crowdsim.continuous`` (Plan 03 turns it GREEN). Skip-guarded so it COLLECTS
cleanly with no jupedsim installed.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.crowdsim

_HELPER_PRESENT = importlib.util.find_spec("crowdsim.continuous") is not None

if _HELPER_PRESENT:  # pragma: no cover - exercised once Plan 03 ships the engine
    from crowdsim.continuous import select_migration_cohort  # noqa: F401

_skip_no_engine = pytest.mark.skipif(
    not _HELPER_PRESENT,
    reason="crowdsim.continuous absent — Wave-0 RED scaffold (GREEN at Plan 03)",
)

_DATA = Path(__file__).resolve().parents[1] / "src" / "crowd" / "data"
_PROGRAM = json.loads((_DATA / "daytime_program_2026.json").read_text(encoding="utf-8"))
_OCCUPANCY = json.loads((_DATA / "occupancy_curve_2026.json").read_text(encoding="utf-8"))


@_skip_no_engine
def test_popularity_delta_selection_is_deterministic():
    """Same (assignment, prev-demand, next-demand, seed) → byte-identical switch cohort, twice."""
    from crowdsim.continuous import select_migration_cohort

    kwargs = dict(program=_PROGRAM, occupancy=_OCCUPANCY, from_hour="14:00", to_hour="15:00", seed=1789)
    cohort_a = select_migration_cohort(**kwargs)
    cohort_b = select_migration_cohort(**kwargs)
    assert cohort_a == cohort_b


@_skip_no_engine
def test_agent_count_constant_across_boundaries():
    """Rectangular invariant: shed-total == receive-total at the boundary (no spawn/cull mid-day)."""
    from crowdsim.continuous import select_migration_cohort

    cohort = select_migration_cohort(
        program=_PROGRAM, occupancy=_OCCUPANCY, from_hour="14:00", to_hour="15:00", seed=1789
    )
    shed_total = sum(len(v) for v in cohort["shed"].values())
    receive_total = sum(len(v) for v in cohort["receive"].values())
    assert shed_total == receive_total, (
        "migration is not rectangular — shed-total != receive-total (DAYCROWD-02 conservation)"
    )
