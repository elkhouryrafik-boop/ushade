"""DAYCROWD-02 — ONE persistent migrating population across the daytime hours (crowdsim tier).

The night path (``crowdsim.simulation``) runs a SINGLE schedule slice: spawn → walk → dwell, one
``(steps × agents × 4)`` trajectory. Phase 16 turns that into ONE persistent ``jps.Simulation`` held
across all 11 daytime intervals (09:00→20:00). At each program boundary the per-stage demand is
recomputed (``crowd.daytime_demand.daytime_goal_weights``) and a POPULARITY-DELTA cohort of agents
is REASSIGNED to the newly-busier stages via the VERIFIED jupedsim 1.2.1 call
``switch_agent_journey(agent_id, journey_id, stage_id)`` — the agents re-path and physically WALK
across the site, the visible migration the owner + prof want to SEE.

INVARIANTS (the migration is honest):

1. **Constant agent count** — migration is REASSIGNMENT, never spawn/exit. ``_assign_stages``
   apportions a FIXED ``n_agents`` at every boundary, so the per-boundary delta has
   ``shed-total == receive-total`` by construction (Pitfall 2). The concatenated trajectory therefore
   stays RECTANGULAR for the FROZEN ``adapter.to_trajectory`` / ``build_crowd_grid`` contract.
2. **RNG-free reproducible selection** — WHICH agents shed is a pinned deterministic rule (lowest
   agent-ids first, receivers filled in ascending stage-index order; :func:`popularity_delta_select`).
   No stochastic draw and no unsorted-collection iteration anywhere in the selection (Pitfall 3,
   T-16-09) — same inputs yield the same cohort, every time (CROWD-10).
3. **Journeys built ONCE** — the per-stage ``[waypoint → waiting_set]`` journeys are built a single
   time at spawn via the REUSED ``crowdsim.simulation._build_stage_journeys``; the loop ONLY
   ``switch_agent_journey`` thereafter (never re-``add_journey`` per boundary — T-16-12 anti-pattern).

REUSE DISCIPLINE (~90% wiring, RESEARCH "Key insight"): the spawn block, journey-build, dwell-spread
and apportionment are imported VERBATIM from ``crowdsim.simulation`` (``_spawn_positions``,
``_build_stage_journeys``, ``_waiting_positions``, ``_assign_stages``); the demand vector from
``crowd.daytime_demand``; the velocity finite-diff from ``crowdsim.adapter.to_trajectory``. The only
NEW logic here is the per-boundary RNG-free delta selection + the ``switch_agent_journey`` call.

LAZY-IMPORT QUARANTINE (mirror ``simulation._default_sim_factory``): ``jupedsim`` and ``shapely`` are
imported INSIDE the run body, NEVER at module top — ``import crowdsim.continuous`` stays engine-free
(the base-tier purity guard). The pure :func:`popularity_delta_select` / :func:`select_migration_cohort`
selection helpers carry no engine import at all (they are unit-testable without the jupedsim wheel).

NAMED CONSTANTS (anti-tuning, CLAUDE.md non-negotiable): the per-hour frame budget is the NAMED
``FRAMES_PER_HOUR_JPS`` (never an inline 1400), the hour grid is ``DAYTIME_HOURS``, the seed is
``SEED`` — all from ``crowd.constants``. crowd_density stays DERIVED-from-ASSUMED (this phase never
calls the permission-gated UTCI service — DAYCROWD-NG).

ENGINE: built against the INSTALLED jupedsim 1.2.1 — ``switch_agent_journey(agent_id, journey_id,
stage_id)`` VERIFIED present with that exact signature this session (RESEARCH Pattern 2). Do NOT
upgrade (the numpy 1.26 pin the FROZEN grid.py DBSCAN needs).
"""

from __future__ import annotations

import numpy as np

from crowd.constants import AGENT_DIVISOR, DAYTIME_HOURS, FRAMES_PER_HOUR_JPS, SEED
from crowd.daytime_demand import daytime_goal_weights, load_occupancy_curve, load_daytime_program
from crowdsim.adapter import to_trajectory
from crowdsim.mapping import build_primitive_spec
from crowdsim.simulation import (
    _RECORD_EVERY,
    _assign_stages,
    _build_stage_journeys,
    _spawn_positions,
)

#: Default cohort size for the pure :func:`select_migration_cohort` (the migration-SELECTION unit
#: test, which passes no capacity). REUSES the documented Primavera anchor // AGENT_DIVISOR so the
#: selection exercises the SAME agent-count scale the real run uses — NAMED (never an inline literal),
#: derived from the existing constants so it tracks any capacity change.
from crowd.constants import PRIMAVERA_DAILY_CAPACITY

_DEFAULT_COHORT_N: int = max(1, PRIMAVERA_DAILY_CAPACITY // AGENT_DIVISOR)


def popularity_delta_select(
    current_stage_of: dict[int, int], target_counts: list[int]
) -> list[tuple[int, int]]:
    """The PINNED RNG-free popularity-delta migration rule → ``[(agent_id, dest_stage_idx), ...]``.

    Given the CURRENT per-agent stage assignment and the TARGET per-stage agent COUNT (the
    ``_assign_stages`` apportionment of the boundary's demand vector over the SAME fixed
    ``n_agents``), decide which agents migrate and where, deterministically (CROWD-10, T-16-09):

    1. ``current_counts[s]`` = number of agents currently at stage ``s`` (from ``current_stage_of``).
    2. ``delta[s] = target_counts[s] - current_counts[s]``: stages with ``delta < 0`` SHED ``|delta|``
       agents; stages with ``delta > 0`` RECEIVE them.
    3. WHICH agents shed: from each shedding stage, take its LOWEST agent-ids FIRST (sorted ascending)
       — a fixed, reproducible cohort (never a Python ``set`` iterated without sorting, Pitfall 3).
    4. Assign the shed pool to receiving stages in ASCENDING stage-index order, filling each receiver
       up to its positive delta.

    ``shed-total == receive-total`` by construction (both ``target_counts`` and ``current_counts``
    sum to the SAME fixed ``n_agents`` — ``_assign_stages`` apportions a fixed total), so the agent
    count stays CONSTANT and the trajectory array stays rectangular (Pitfall 2). No RNG → same inputs
    yield the same ``(agent_id, dest)`` list, every time.

    Returns:
        A list of ``(agent_id, dest_stage_idx)`` pairs (the cohort to ``switch_agent_journey``),
        ordered by destination stage then agent-id (a stable, reproducible order).
    """
    n_stages = len(target_counts)

    # current_counts + the per-stage SORTED agent-id lists (ascending → lowest-id-first shed order).
    current_counts = [0] * n_stages
    agents_at: dict[int, list[int]] = {s: [] for s in range(n_stages)}
    for aid in sorted(current_stage_of):  # sorted: deterministic, RNG-free (no unsorted dict/set iter)
        s = current_stage_of[aid]
        if 0 <= s < n_stages:
            current_counts[s] += 1
            agents_at[s].append(aid)

    # Shed pool: lowest agent-ids first from each shedding stage, stages in ascending index order.
    shed_pool: list[int] = []
    for s in range(n_stages):
        delta = target_counts[s] - current_counts[s]
        if delta < 0:
            shed_pool.extend(agents_at[s][: -delta])  # already ascending → lowest ids first

    # Fill receivers in ascending stage-index order, each up to its positive delta.
    moves: list[tuple[int, int]] = []
    pool_idx = 0
    for s in range(n_stages):
        delta = target_counts[s] - current_counts[s]
        for _ in range(max(0, delta)):
            if pool_idx >= len(shed_pool):
                break
            moves.append((shed_pool[pool_idx], s))
            pool_idx += 1
    return moves


def select_migration_cohort(
    *,
    program: dict,
    occupancy: dict | None = None,
    from_hour: str,
    to_hour: str,
    profile: str | None = None,
    n_agents: int | None = None,
    seed: int = SEED,  # noqa: ARG001 — selection is RNG-free; seed accepted for call-site symmetry
) -> dict[str, dict[str, list[int]]]:
    """Pure popularity-delta migration cohort between two hours → ``{"shed": {...}, "receive": {...}}``.

    The unit-testable (no-engine) face of the boundary migration (DAYCROWD-02, the
    ``test_daytime_migration`` contract). Computes the per-stage agent COUNT at ``from_hour`` and at
    ``to_hour`` (``_assign_stages`` of each hour's ``daytime_goal_weights`` over a FIXED
    ``n_agents``), assigns a stable lowest-id-first cohort to the from-hour stages, then runs the
    pinned :func:`popularity_delta_select` to get the moves and groups them by stage name.

    The ``seed`` is accepted (call-site symmetry with the engine run) but the selection is RNG-FREE —
    ``_assign_stages`` and the lowest-id shed rule are both deterministic, so the cohort is identical
    on repeat (CROWD-10). ``shed-total == receive-total`` by construction (the rectangular invariant).

    Args:
        program: organiser stage program (REQUIRED; the demand helper raises on ``None``).
        occupancy: pre-loaded occupancy curve (else the committed default is loaded).
        from_hour / to_hour: the two ``HH:MM`` boundary marks.
        profile: arrival profile (else the curve's ``default_profile``).
        n_agents: fixed population size (defaults to the Primavera anchor // AGENT_DIVISOR).
        seed: accepted for symmetry; unused (selection is RNG-free).

    Returns:
        ``{"shed": {stage_name: [agent_id, ...]}, "receive": {stage_name: [agent_id, ...]}}`` —
        agents leaving each shedding stage and arriving at each receiving stage.
    """
    occ = occupancy if occupancy is not None else load_occupancy_curve()
    n = int(n_agents) if n_agents is not None else _DEFAULT_COHORT_N

    # Stage names = the program's stages (the migration domain); class defaults to "main" (the demo
    # program carries no explicit capacity_class — same default as daytime_demand_table).
    sp = program["stage_program"] if "stage_program" in program else program
    stage_names = list(sp.keys())
    classes = [sp[s].get("capacity_class", "main") for s in stage_names]

    w_from = daytime_goal_weights(stage_names, classes, from_hour, program=program, occupancy=occ, profile=profile)
    w_to = daytime_goal_weights(stage_names, classes, to_hour, program=program, occupancy=occ, profile=profile)

    counts_from = _assign_stages(w_from, n)
    counts_to = _assign_stages(w_to, n)

    # Per-stage target COUNT vectors (number of agents at each stage at each hour).
    target_from = [0] * len(stage_names)
    for s in counts_from:
        target_from[s] += 1
    target_to = [0] * len(stage_names)
    for s in counts_to:
        target_to[s] += 1

    # Materialise the from-hour assignment as a deterministic aid → stage map (agents 0..n-1 in
    # stage-index order — the SAME canonical order _assign_stages emits), then run the pinned rule.
    current_stage_of: dict[int, int] = {aid: stage for aid, stage in enumerate(counts_from)}
    moves = popularity_delta_select(current_stage_of, target_to)

    shed: dict[str, list[int]] = {}
    receive: dict[str, list[int]] = {}
    for aid, dst in moves:
        src = current_stage_of[aid]
        shed.setdefault(stage_names[src], []).append(aid)
        receive.setdefault(stage_names[dst], []).append(aid)
    return {"shed": shed, "receive": receive}


def run_continuous_daytime(
    project_id: str, *, projects_root, seed: int = SEED
) -> np.ndarray:
    """ONE persistent migrating CFSM run over all 11 daytime intervals → ``(steps × agents × 4)``.

    Holds a SINGLE ``jps.Simulation`` across 09:00→20:00: spawn once, build journeys once, then at
    each of the 11 hour boundaries recompute the per-stage target counts (``_assign_stages`` of the
    boundary's ``daytime_goal_weights``) and migrate the popularity-delta cohort via
    ``switch_agent_journey``, recording ``FRAMES_PER_HOUR_JPS`` frames per interval. The concatenated
    positions are finite-differenced into the FROZEN ``(steps × agents × 4)`` array — rectangular,
    constant agent column count (no spawn/exit mid-day).

    ``steps == FRAMES_PER_HOUR_JPS × (len(DAYTIME_HOURS) - 1)`` (11 intervals × the named per-hour
    budget). ``jupedsim``/``shapely`` are lazy-imported INSIDE this body (the engine quarantine).

    Args:
        project_id: project dir name under ``projects_root`` (carries ``parsed_brief.json`` +
            ``utci_grid.json`` — the conftest seeds it from the committed real-site inputs).
        projects_root: the projects root path.
        seed: spawn seed (the seeded ``distribute_by_number``; the migration selection is RNG-free).

    Returns:
        ``np.ndarray`` ``(steps × agents × 4)`` — the continuous migrating daytime trajectory.
    """
    import json
    from pathlib import Path

    import jupedsim as jps  # LAZY — keeps import crowdsim.continuous jupedsim-free (T-16 purity)
    import shapely
    from shapely.ops import unary_union

    pdir = Path(projects_root) / project_id
    brief = json.loads((pdir / "parsed_brief.json").read_text(encoding="utf-8"))
    utci = json.loads((pdir / "utci_grid.json").read_text(encoding="utf-8"))
    lattice = utci["lattice"]  # AUTHORITY — passed UNCHANGED (CONTRACT-03)
    capacity = brief["capacity"]
    n_agents = max(1, capacity // AGENT_DIVISOR)  # PRD: N = capacity / 100 (named constant)

    # The organiser daytime program (REQUIRED — daytime_goal_weights raises on absence) + occupancy.
    program = load_daytime_program()
    occupancy = load_occupancy_curve()

    # ── Build ONE simulation (reuse the SAME boundary − blockers set-op the night factory uses) ──
    spec = build_primitive_spec(lattice=lattice, n_agents=int(n_agents))  # jupedsim-free spec
    boundary = unary_union([shapely.Polygon(r) for r in spec["boundary_rings"]])
    blockers = unary_union([shapely.Polygon(r) for r in spec["blocker_rings"]])
    walkable = boundary.difference(blockers)

    from crowdsim.simulation import _SIM_DT_S  # the small stable CFSM ODE step (lazy with the engine)

    sim = jps.Simulation(
        model=jps.CollisionFreeSpeedModel(),
        geometry=walkable,
        dt=_SIM_DT_S,
    )

    # Journeys built ONCE (REUSED helper); only switch_agent_journey thereafter (T-16-12).
    journey_ids, first_stage_ids = _build_stage_journeys(sim, spec, walkable, lattice)
    # Seeded spawn over disjoint gate patches (REUSED helper) — canonical (gate-then-index) order.
    spawn_positions = _spawn_positions(sim, spec, walkable, seed=seed)

    # Site stage names/classes (the FROZEN festival layer — the SAME source build_primitive_spec
    # reads). The program's 7 stages are a subset (INT-001 holds); off-program stages pull at
    # ACTIVE_BASELINE. daytime_goal_weights returns one weight per site stage in this column order.
    from crowd.site import load_site_geometry

    geo = load_site_geometry(lattice=lattice)
    stage_names = [m["name"] for m in geo["stage_meta"]]
    classes = [m["class"] for m in geo["stage_meta"]]

    # Initial assignment: apportion at the FIRST daytime hour, add agents to those journeys.
    w0 = daytime_goal_weights(stage_names, classes, DAYTIME_HOURS[0], program=program, occupancy=occupancy)
    initial = _assign_stages(w0, len(spawn_positions))
    agent_ids: list[int] = []
    current_stage_of: dict[int, int] = {}
    for pos, stage_idx in zip(spawn_positions, initial):
        aid = sim.add_agent(
            jps.CollisionFreeSpeedModelAgentParameters(
                journey_id=journey_ids[stage_idx],
                stage_id=first_stage_ids[stage_idx],
                position=pos,
                radius=spec_radius(),
            )
        )
        agent_ids.append(aid)
        current_stage_of[aid] = stage_idx

    # Stable agent-id → column order (sorted once at spawn; a parked agent keeps its last position).
    ordered_ids = sorted(agent_ids)
    col_of = {aid: i for i, aid in enumerate(ordered_ids)}
    n_cols = len(ordered_ids)

    def _frame(last_frame: np.ndarray) -> np.ndarray:
        frame = last_frame.copy()
        for a in sim.agents():
            frame[col_of[a.id]] = a.position
        return frame

    positions_all: list[np.ndarray] = []
    last = np.zeros((n_cols, 2), dtype=float)
    for a in sim.agents():
        last[col_of[a.id]] = a.position

    # ── 11 intervals: migrate the delta cohort, then record FRAMES_PER_HOUR_JPS frames each ──
    for h_idx in range(len(DAYTIME_HOURS) - 1):
        demand_vec = daytime_goal_weights(
            stage_names, classes, DAYTIME_HOURS[h_idx], program=program, occupancy=occupancy
        )
        # WR-01 fix: apportion migration targets over the REALISED live population (n_cols), NOT
        # the REQUESTED n_agents. _spawn_positions can realise fewer agents than n_agents when the
        # disjoint-gate clipping / per-gate source rounding drops a few spawn slots. The
        # shed-total == receive-total conservation (Pitfall 2) requires sum(target_count_vec) to
        # equal the live population, which is exactly n_cols (== len(spawn_positions) == len(agent_ids)).
        target_counts = _assign_stages(demand_vec, n_cols)
        # _assign_stages returns a flat aid→stage list; convert to a per-stage COUNT vector.
        target_count_vec = [0] * len(stage_names)
        for s in target_counts:
            target_count_vec[s] += 1
        # Invariant: targets must sum to the live population, else the popularity-delta cohort
        # cannot conserve (some agents would be mis-migrated or starved). Cheap, runs once per hour.
        assert sum(target_count_vec) == n_cols, (
            f"migration target total {sum(target_count_vec)} != live population {n_cols} "
            f"(hour {DAYTIME_HOURS[h_idx]}) — conservation would break"
        )
        # STAGGERED migration (realism): the cohort does NOT pivot in lockstep at the hour boundary —
        # that produced a robotic "boom rearrange". Release the switches deterministically over the
        # first ~third of the interval so the crowd TRICKLES to the newly-busier stages, like a real
        # festival. The SELECTION is unchanged (same deterministic cohort); only the TIMING of applying
        # it is spread — conservation, determinism and the rectangular shape all hold (all switches are
        # applied by frame `stagger_span`, before the next interval reads current_stage_of).
        switches = list(popularity_delta_select(current_stage_of, target_count_vec))
        stagger_span = max(1, FRAMES_PER_HOUR_JPS // 3)
        si = 0
        for fi in range(FRAMES_PER_HOUR_JPS):
            release_to = len(switches) if fi >= stagger_span else ((fi + 1) * len(switches)) // stagger_span
            while si < release_to:
                aid, dst = switches[si]
                sim.switch_agent_journey(
                    agent_id=aid, journey_id=journey_ids[dst], stage_id=first_stage_ids[dst]
                )
                current_stage_of[aid] = dst
                si += 1
            for _ in range(_RECORD_EVERY):
                if sim.agent_count() == 0:
                    break
                sim.iterate()
            last = _frame(last)
            positions_all.append(last)

    positions = np.asarray(positions_all, dtype=float)  # (steps, agents, 2)
    return to_trajectory(positions)  # (steps, agents, 4)


def spec_radius() -> float:
    """The NAMED CFSM agent body radius (metres) for spawned agents — never an inline literal."""
    from crowd.constants import AGENT_RADIUS_M

    return AGENT_RADIUS_M
