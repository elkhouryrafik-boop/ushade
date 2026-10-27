"""BLOCKING DoD reach gate for the JuPedSim crowd swap (D-01/D-02, CROWD-07).

The swap's Definition-of-Done is the **all-stages-reachable boolean** (D-01): on the real
~800 m Parc del Fòrum site, every mapped stage's waiting-set region must receive NON-ZERO crowd
density within SIM time. JuPedSim agents follow SCRIPTED journeys (unlike the learned PPO), so
reach is ~100% by construction — this gate catches a MIS-WIRE (unreachable geometry, a stranded
journey transition, a too-short ``SIM_STEPS_JPS`` horizon), not a re-measured learned policy. It
replaces the retired ``STAGE_REACH_FRAC=0.70`` gate; there is NO ``@pytest.mark.xfail`` and NO
latched-fraction measurement.

``@pytest.mark.crowdsim`` (D-02): this BLOCKS — a red here means the swap is NOT done. It runs the
real JuPedSim path (needs the ``crowdsim`` extra), never the base tier.

DoD GRANULARITY — REGION, not pixel (D-01, faithful): D-01 is "every mapped stage's waiting-set
REGION receives non-zero density." The gate asserts exactly that: for EACH farthest-reachable stage,
its ``REACH_RADIUS_M`` waiting region (the finite-bfs disc cells) receives density SOMEWHERE — i.e.
the cohort actually arrives and dwells in that region. This is the honest, physically-meaningful and
source-faithful contract: it KILLS the old "far stages ~0%" failure (a stranded/wandering far stage
has its ENTIRE region at zero → RED), while NOT demanding the physically-impossible "every individual
6 m pixel of a 30 m disc is occupied" (a far stage attended by N agents can occupy at most N distinct
cells, and JuPedSim's WaitingSetStage fills its dwell slots in order — so a sparsely-attended far
stage cannot light every disc cell even when correctly reached). A per-pixel assert would relax ONLY
by tuning attendance/horizon — exactly the dishonesty D-03 forbids; the region gate needs no such
fudge. See 15-04-SUMMARY for the full reach evidence (all far-stage regions reached on the real run).

ACCEPTANCE DISCIPLINE: ``REACH_RADIUS_M`` is read from ``crowd.constants`` — NEVER an inline literal
(it lives in the shared ``_far_stage_waiting_regions`` helper). D-03: the ONLY honest relaxation is
genuine geometric unreachability (``flowfield.bfs_distance == inf`` from gate A — a stage centre or a
disc cell inside a blocker), applied inside the helper and documented in 15-04-SUMMARY; never relaxed
to paper over broken journey wiring (a finite-bfs region that reads all-zero still FAILS).

GREEN at Wave 3: the JuPedSim engine routes each agent to its assigned destination stage (deterministic
popularity apportionment) and the cohort dwells in the stage's waiting region → every far-stage region
carries density.
"""

from __future__ import annotations

import pytest

# conftest_crowdsim is imported EXPLICITLY (not auto-loaded). The real-site project seeder is the DoD
# gate's geometry source (committed geojson + utci lattice); _far_stage_waiting_regions is the shared
# per-stage far-region derivation promoted from the Plan-01 inline body (15-04 Task 1), applying the
# honest D-03 stage- AND cell-level bfs_distance == inf exclusions inside conftest_crowdsim.
from conftest_crowdsim import (
    _cell_index,
    _far_stage_waiting_regions,
    crowdsim_real_site_project,
    load_committed_utci,
)
from crowd.crowd import run_crowd_stage

pytestmark = pytest.mark.crowdsim


def test_all_far_stages_reachable(tmp_path):
    """Every far-stage waiting REGION receives non-zero crowd density on the real site (D-01/D-02).

    Runs the real-site JuPedSim ``run_crowd_stage`` and asserts each farthest-reachable stage's
    ``REACH_RADIUS_M`` waiting region carries density SOMEWHERE (D-01, region granularity). A RED here
    means the swap is NOT done: a mis-wired journey/waiting-set stranded a far stage's cohort, or
    ``SIM_STEPS_JPS`` is too short — that stage's WHOLE region reads zero (the old far-stage-starvation
    failure). D-03: only a genuinely unreachable stage/cell (gate-A ``bfs_distance == inf``, already
    excluded inside the helper) is an honest relaxation — never loosen this to hide broken wiring.
    """
    crowdsim_real_site_project(tmp_path, "forum-real")
    lattice = load_committed_utci()["lattice"]
    regions = _far_stage_waiting_regions(lattice)
    assert regions, "no far-stage waiting regions derived — fixture/geometry is broken"
    assert all(r["cells"] for r in regions), "a far-stage region has no reachable cells — geometry broken"

    grid = run_crowd_stage("forum-real", projects_root=tmp_path)

    # Density lookup keyed by (col, row) from each emitted cell's centre coords (join-not-zip).
    dens: dict[tuple[int, int], float] = {}
    for cell in grid["cells"]:
        key = _cell_index(cell["x_m"], cell["y_m"], lattice)
        dens[key] = cell["crowd_density_agents_per_cell"]

    # D-01: EVERY far-stage waiting region must receive density somewhere (the region is reached).
    starved = [
        r["name"] for r in regions if not any(dens.get(cell, 0.0) > 0 for cell in r["cells"])
    ]
    assert not starved, (
        f"far-stage waiting region(s) received ZERO density anywhere: {starved}. The JuPedSim "
        "mapping stranded the far cohort (mis-wired journey / waiting-set, or SIM_STEPS_JPS too "
        "short) — the old far-stage-starvation failure. D-03: relax ONLY for a genuinely unreachable "
        "stage (flowfield.bfs_distance == inf, excluded in the helper), never to hide a mis-wire."
    )
