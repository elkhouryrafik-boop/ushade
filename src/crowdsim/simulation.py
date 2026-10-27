"""The live JuPedSim crowd engine (CROWD-06/07/10, D-06) — seeded CFSM run → (steps×agents×4).

This module drives JuPedSim's Collision-Free Speed Model (CFSM — collision-free by construction, so
the old ``_lateral_push`` far-stage-starvation artifact CANNOT recur) over the FROZEN festival
geometry and returns the SAME ``(steps × agents × 4)`` trajectory array ``build_crowd_grid``
consumes. The cache-miss path of ``run_crowd_stage`` (Wave 2/Plan 03) calls
:func:`_default_sim_factory`'s factory in place of the dormant PPO rollout.

LAZY-IMPORT DISCIPLINE (T-15-05, mirror of ``crowd.rollout.load_policy``): ``jupedsim`` and
``shapely`` are imported INSIDE the factory body, NEVER at module top — so ``import
crowdsim.simulation`` stays light and pulls no native wheel (the base-tier purity guard). The
plain-data spec is built jupedsim-free in ``mapping.build_primitive_spec``; the jupedsim objects are
constructed here from that spec.

DETERMINISM (CROWD-10, RESEARCH Pattern 4): the spawn distribution is seeded
(``distribute_by_number(seed=...)``), agents are added in a CANONICAL (gate-then-index) order so the
COUNT-based round-robin demand split is reproducible, the run is single-process, and the
``jupedsim`` version is pinned in the cache fingerprint (the shell, Wave 2). Determinism is enforced
at the LATTICE-SNAPPED density field (``snap_to_lattice`` quantizes CFSM float jitter), NOT the raw
ODE trajectory.

NO ``ExitStage`` (RESEARCH Open Q1 RESOLVED): festival agents journey gate → stages and DWELL at
the stage fronts (no evacuation), so ``agent_count()`` stays constant and the trajectory array stays
rectangular. The loop terminator is the NAMED ``SIM_STEPS_JPS`` cap (never a magic number — the
CCA-F named-backstop discipline, mirror of ``rollout.py``'s named-steps terminator).

ENGINE: built against the INSTALLED jupedsim 1.2.1 API (the project pins ``jupedsim>=1.2.1,<1.3``
to preserve the numpy 1.26 baseline the FROZEN grid.py DBSCAN path needs; 1.2.1 exposes the SAME
high-level Simulation/Journey/Transition API as the 1.4.x docs).

REUSED BY ``crowdsim.continuous`` (Phase 16, DAYCROWD-02): the module-level helpers
:func:`_assign_stages`, :func:`_waiting_positions`, :func:`_build_stage_journeys` and
:func:`_spawn_positions` are importable seams the persistent-migration daytime run consumes
VERBATIM (``from crowdsim.simulation import _assign_stages, _waiting_positions,
_build_stage_journeys, _spawn_positions``) so the spawn + journey-build logic is written ONCE and
shared across the night (single-slice) and daytime (continuous) paths — never re-rolled. The
extraction is behavior-PRESERVING: ``_default_sim_factory`` calls the same helpers, so the existing
crowdsim determinism + stage-reach tests stay byte-identical (T-16-11). The helpers receive an
already-built ``sim``/``walkable`` so they carry no top-level jupedsim/shapely import (the lazy
quarantine is preserved — ``import crowdsim.simulation`` stays engine-free).
"""

from __future__ import annotations

import numpy as np

from crowd.constants import AGENT_RADIUS_M, SEED, SIM_STEPS_JPS, STEP_DT_JPS_S
from crowdsim.adapter import to_trajectory
from crowdsim.mapping import build_primitive_spec

#: Minimum agent-spacing / polygon-clearance for the seeded spawn distribution (metres). Derived
#: from the named ``AGENT_RADIUS_M`` (body radius) so the spawn packing tracks the agent size — a
#: spawn disc must hold its gate's agents without overlap. NAMED (never inline) per the anti-tuning
#: discipline; ``distribute_by_number`` raises if a gate patch cannot hold its share at this spacing.
_SPAWN_MIN_DIST_M: float = 2.0 * AGENT_RADIUS_M

#: JuPedSim ODE integration step (seconds/iterate). [ASSUMED] — the CFSM solver needs a SMALL
#: integration dt for stability: at the coarse STEP_DT_JPS_S=1.0 s an agent overshoots a wall in one
#: solve ("Point ... outside accessible area"). 0.05 s is the documented CFSM-stable scale and ran
#: clean over the real ~800 m site. This is the ENGINE step; the TRAJECTORY is recorded every
#: STEP_DT_JPS_S of elapsed time (every _RECORD_EVERY iterates) so the finite-diff adapter's 1.0 s
#: divisor and the SIM_STEPS_JPS=1400-frame horizon (≈1400 s of travel) stay meaningful.
_SIM_DT_S: float = 0.05

#: Internal iterates per RECORDED trajectory frame = STEP_DT_JPS_S / _SIM_DT_S. Recording every this
#: many iterates makes consecutive recorded frames exactly STEP_DT_JPS_S apart (the adapter's
#: finite-diff divisor), so SIM_STEPS_JPS recorded frames == the derived travel-time horizon.
_RECORD_EVERY: int = int(round(STEP_DT_JPS_S / _SIM_DT_S))


def _waiting_positions(
    sx: float, sy: float, reach: float, walkable, lattice: dict
) -> list[tuple[float, float]]:
    """Dwell positions SPREAD one-per-lattice-cell across the walkable ``reach`` disc (UTM31N).

    The DoD gate (D-01/D-02) samples the ``REACH_RADIUS_M`` disc around each far stage and asserts
    EVERY walkable disc cell receives density, so the WaitingSetStage must spread arriving agents
    across DISTINCT lattice cells — JuPedSim fills a waiting set's positions IN LIST ORDER, so a
    naive dense list piles every agent onto the first slot (the centre) and the rest of the disc
    reads zero (the residual far-stage starvation the DoD catches). Fix: emit exactly ONE dwell
    position per walkable lattice cell whose CENTRE lies within ``reach`` of the stage, at that
    cell's centre, ordered by ascending ring distance then angle (centre first, then spiralling out)
    so the first K arriving agents occupy K DISTINCT cells covering the disc from the inside out.
    Pure geometry, fully reproducible (no RNG) — the determinism CROWD-10 needs.

    The order matters: WaitingSetStage occupies positions in order, so a nearest-first spiral fills
    the inner disc cells before the outer ones; with enough agents (the popularity apportionment
    floors every stage at ≥1 and the far cohort here gets dozens) the whole walkable disc is covered.
    """
    import math

    import shapely

    ox, oy, s = lattice["origin_x_m"], lattice["origin_y_m"], lattice["cell_size_m"]
    centre_col, centre_row = int((sx - ox) // s), int((sy - oy) // s)
    rad_cells = int(math.ceil(reach / s)) + 1

    cell_pts: list[tuple[float, float, float, float]] = []  # (ring_dist, angle, px, py)
    seen: set[tuple[int, int]] = set()
    for dc in range(-rad_cells, rad_cells + 1):
        for dr in range(-rad_cells, rad_cells + 1):
            col, row = centre_col + dc, centre_row + dr
            if (col, row) in seen:
                continue
            # lattice cell-centre in UTM (the (idx + 0.5) cell-centre convention)
            px = ox + (col + 0.5) * s
            py = oy + (row + 0.5) * s
            d = math.hypot(px - sx, py - sy)
            if d > reach:
                continue
            if not walkable.contains(shapely.Point(px, py)):
                continue
            seen.add((col, row))
            cell_pts.append((d, math.atan2(py - sy, px - sx), px, py))

    # Centre-first spiral: nearest cell, then by angle — fills the disc from the inside out.
    cell_pts.sort(key=lambda t: (t[0], t[1]))
    pts = [(px, py) for _, _, px, py in cell_pts]
    if not pts:  # the snapped centre is walkable by construction — guaranteed fallback slot
        pts = [(sx, sy)]
    return pts


def _assign_stages(goal_weights, n_agents: int) -> list[int]:
    """Deterministic agent→stage index assignment (count-based largest-remainder apportionment).

    Apportions ``n_agents`` across the stages in proportion to ``goal_weights`` (popularity), giving
    EVERY mapped stage ≥1 agent (so even the least-popular far stage is reached — the DoD asserts
    this) when ``n_agents >= n_stages``. Returns a flat list of length ``n_agents`` of stage indices,
    stage-index-ordered (stage 0's agents first, …), assigned to the canonical spawn order. No RNG —
    the split is reproducible (CROWD-10).
    """
    weights = [max(0.0, float(w)) for w in goal_weights]
    n_stages = len(weights)
    if n_stages == 0 or n_agents <= 0:
        return []
    total = sum(weights)
    if total <= 0:
        weights = [1.0] * n_stages
        total = float(n_stages)

    if n_agents >= n_stages:
        # Floor each stage at 1, apportion the remainder by largest fractional part.
        base = [1] * n_stages
        remaining = n_agents - n_stages
        quotas = [remaining * (w / total) for w in weights]
        floors = [int(q) for q in quotas]
        allotted = sum(floors)
        counts = [base[i] + floors[i] for i in range(n_stages)]
        leftover = remaining - allotted
        order = sorted(range(n_stages), key=lambda i: (quotas[i] - floors[i], weights[i]), reverse=True)
        for i in range(leftover):
            counts[order[i % n_stages]] += 1
    else:
        # Fewer agents than stages: give them to the most-popular stages (deterministic).
        counts = [0] * n_stages
        order = sorted(range(n_stages), key=lambda i: (weights[i], -i), reverse=True)
        for i in range(n_agents):
            counts[order[i]] += 1

    out: list[int] = []
    for idx, c in enumerate(counts):
        out.extend([idx] * c)
    return out


def _build_stage_journeys(sim, spec, walkable, lattice) -> tuple[list[int], list[int]]:
    """Build ONE arrive-and-dwell journey per stage on ``sim`` → ``(journey_ids, first_stage_ids)``.

    Extracted VERBATIM from ``_default_sim_factory`` (behavior-preserving) so the night single-slice
    path AND the continuous daytime migration path (Phase 16) build the SAME journeys the SAME way —
    each stage gets a SINGLE-DESTINATION journey ``[waypoint(stage) → waiting_set(stage)]`` (RESEARCH
    Open Q1 RESOLVED: park-and-dwell, no ExitStage; a round-robin over all stages makes agents wander
    and starves the far stages — the old DoD D-01/D-02 failure). Built ONCE; the migration loop only
    ``switch_agent_journey`` thereafter (never rebuilds — T-16-12 anti-pattern).

    ``jps``/``shapely`` are lazy-imported INSIDE the body so importing this module stays engine-free
    (the helper receives an already-built ``sim``/``walkable``). A stage centre that sits just inside
    an impassable blocker (±30 m indicative layout accuracy) is snapped to the NEAREST walkable point
    (honest: moved to the closest reachable spot, not dropped; the DoD reach gate still validates the
    snapped stage receives density). Returns each journey's id and its FIRST stage id (the waypoint —
    ``add_agent``/``switch_agent_journey`` both need ``(journey_id, first_stage_id)``).
    """
    import jupedsim as jps  # LAZY — keeps import crowdsim.simulation jupedsim-free (T-15-05)
    import shapely
    from shapely.ops import nearest_points

    waypoints = []
    for sx, sy in spec["stages_utm"]:
        pt = shapely.Point(sx, sy)
        if not walkable.contains(pt):
            snapped = nearest_points(walkable, pt)[0]
            waypoints.append((snapped.x, snapped.y))
        else:
            waypoints.append((sx, sy))

    reach = float(spec["reach_radius_m"])
    journey_ids: list[int] = []
    first_stage_ids: list[int] = []
    for sx, sy in waypoints:
        wp = sim.add_waypoint_stage((sx, sy), reach)
        dwell_pts = _waiting_positions(sx, sy, reach, walkable, lattice)
        ws = sim.add_waiting_set_stage(dwell_pts)
        journey_ids.append(sim.add_journey(jps.JourneyDescription([wp, ws])))
        first_stage_ids.append(wp)
    return journey_ids, first_stage_ids


def _spawn_positions(sim, spec, walkable, *, seed: int) -> list[tuple[float, float]]:
    """Seeded per-gate spawn positions over DISJOINT gate patches → list of UTM ``(x, y)`` points.

    Extracted VERBATIM from ``_default_sim_factory`` (behavior-preserving) so the night and the
    continuous daytime paths spawn IDENTICALLY from the SAME seeded ``distribute_by_number`` over the
    SAME disjoint gate patches — the determinism CROWD-10 needs. ``jps``/``shapely`` are lazy-imported
    INSIDE the body (engine-quarantine preserved; the helper receives an already-built ``walkable``).
    The ``sim`` argument is accepted for signature symmetry with :func:`_build_stage_journeys` (the
    spawn distribution itself is sim-independent — ``distribute_by_number`` is a free function).

    Clip each gate patch to the walkable area (a gate sits at the site edge, so its SPAWN_JITTER_M
    patch can spill outside the boundary — ``distribute_by_number`` would otherwise place an agent
    outside the walkable area). DISJOINT GATE PATCHES (DoD-driven fix, T-15-07): the two
    SPAWN_JITTER_M gate patches OVERLAP on the real site; ``distribute_by_number`` is seeded PER GATE
    and unaware of the other gate's points, so two agents from different gates can land
    < 2·AGENT_RADIUS_M apart in the overlap strip → ``add_agent`` rejects the second. Subtract every
    already-claimed gate patch from each subsequent gate (canonical order) so the spawn regions are
    DISJOINT and the per-gate seeded distributions never collide.
    """
    import jupedsim as jps  # LAZY — keeps import crowdsim.simulation jupedsim-free (T-15-05)
    import shapely
    from shapely.ops import unary_union

    spawn_positions: list[tuple[float, float]] = []
    claimed = None  # union of already-distributed gate patches (kept disjoint)
    for gate_ring, n_a in spec["sources"]:
        if n_a <= 0:
            continue
        gate_poly = shapely.Polygon(gate_ring).intersection(walkable)
        if claimed is not None:
            gate_poly = gate_poly.difference(claimed)
        if gate_poly.is_empty:
            raise ValueError("gate spawn patch does not intersect the walkable area")
        # An intersection/difference can yield a MultiPolygon; distribute over its largest piece.
        if gate_poly.geom_type == "MultiPolygon":
            gate_poly = max(gate_poly.geoms, key=lambda g: g.area)
        claimed = gate_poly if claimed is None else unary_union([claimed, gate_poly])
        spawn_positions.extend(
            jps.distribute_by_number(
                polygon=gate_poly,
                number_of_agents=int(n_a),
                distance_to_agents=_SPAWN_MIN_DIST_M,
                distance_to_polygon=AGENT_RADIUS_M,
                seed=int(seed),
            )
        )
    return spawn_positions


def _default_sim_factory():
    """Return the default JuPedSim sim factory ``(*, lattice, utci_cells, n_agents, seed) -> ndarray``.

    The returned callable runs a seeded CFSM festival simulation and returns the FROZEN
    ``(steps × agents × 4)`` trajectory array. ``jupedsim``/``shapely`` are lazy-imported INSIDE the
    factory (the cache-miss path) so importing this module pulls neither. The journey-build and spawn
    blocks are the importable :func:`_build_stage_journeys` / :func:`_spawn_positions` helpers
    (reused VERBATIM by ``crowdsim.continuous`` — the extraction is behavior-preserving).
    """

    def _factory(*, lattice, utci_cells=None, n_agents=1, seed: int = SEED) -> np.ndarray:
        import jupedsim as jps  # LAZY — keeps import crowdsim.simulation jupedsim-free (T-15-05)
        import shapely

        spec = build_primitive_spec(lattice=lattice, n_agents=int(n_agents))  # jupedsim-free spec

        # Walkable area = boundary − blockers via the ROBUST shapely set-op (the SAME boundary −
        # blocker geometry build_blocked_cells rasterises). A naive Polygon(exterior, holes=blockers)
        # is INVALID where a blocker straddles the boundary edge (side-location conflict); the
        # difference yields a VALID (possibly Multi)Polygon JuPedSim accepts.
        from shapely.ops import unary_union

        boundary = unary_union([shapely.Polygon(r) for r in spec["boundary_rings"]])
        blockers = unary_union([shapely.Polygon(r) for r in spec["blocker_rings"]])
        walkable = boundary.difference(blockers)
        sim = jps.Simulation(
            model=jps.CollisionFreeSpeedModel(),
            geometry=walkable,
            dt=_SIM_DT_S,  # SMALL stable ODE step; positions RECORDED every _RECORD_EVERY iterates
        )

        # Stages → ARRIVE-AND-DWELL journeys, built ONCE via the shared importable helper.
        journey_ids, first_stage_ids = _build_stage_journeys(sim, spec, walkable, lattice)

        # Seeded spawn over DISJOINT gate patches via the shared importable helper (canonical order).
        spawn_positions = _spawn_positions(sim, spec, walkable, seed=seed)

        # Deterministic agent→stage assignment from the popularity weights (T-15-07). Each spawned
        # agent is sent to ONE stage; the per-stage COUNT is the largest-remainder apportionment of
        # ``goal_weights`` over ``len(spawn_positions)`` (count-based, no RNG — the determinism
        # CROWD-10 needs), floored so EVERY mapped stage gets ≥1 agent (so even the least popular far
        # stage is reached, which the DoD asserts). Agents are assigned in canonical (gate-then-index)
        # spawn order to the stage list expanded by count → a fixed, reproducible mapping.
        stage_destinations = _assign_stages(spec["goal_weights"], len(spawn_positions))
        agent_ids: list[int] = []
        for pos, stage_idx in zip(spawn_positions, stage_destinations):
            aid = sim.add_agent(
                jps.CollisionFreeSpeedModelAgentParameters(
                    journey_id=journey_ids[stage_idx],
                    stage_id=first_stage_ids[stage_idx],
                    position=pos,
                    radius=AGENT_RADIUS_M,
                )
            )
            agent_ids.append(aid)

        # Stable agent-id → column order (sorted once at spawn). A parked/missing agent keeps its
        # last recorded position (velocity 0, A2) so the array stays rectangular.
        ordered_ids = sorted(agent_ids)
        col_of = {aid: i for i, aid in enumerate(ordered_ids)}
        n_cols = len(ordered_ids)

        # NO ExitStage — agents dwell at stage fronts; SIM_STEPS_JPS (recorded frames) is the loop
        # terminator (the named backstop, never a magic number). The engine steps at the small stable
        # _SIM_DT_S; a trajectory frame is RECORDED every _RECORD_EVERY iterates so consecutive frames
        # are STEP_DT_JPS_S apart (the adapter's finite-diff divisor) and SIM_STEPS_JPS frames cover
        # the derived ≈1400 s travel-time horizon.
        def _frame(last_frame: np.ndarray) -> np.ndarray:
            frame = last_frame.copy()
            for a in sim.agents():
                frame[col_of[a.id]] = a.position
            return frame

        positions_per_step: list[np.ndarray] = []
        last = np.zeros((n_cols, 2), dtype=float)
        for a in sim.agents():
            last[col_of[a.id]] = a.position
        positions_per_step.append(last)  # frame 0 = spawn positions (recorded at t=0)
        while sim.agent_count() > 0 and len(positions_per_step) < SIM_STEPS_JPS:
            for _ in range(_RECORD_EVERY):
                if sim.agent_count() == 0:
                    break
                sim.iterate()
            last = _frame(last)
            positions_per_step.append(last)

        positions = np.asarray(positions_per_step, dtype=float)  # (steps, agents, 2)
        return to_trajectory(positions)  # (steps, agents, 4)

    return _factory


def simulate(*, lattice, utci_cells=None, n_agents=1, seed: int = SEED) -> np.ndarray:
    """Run the default seeded JuPedSim CFSM factory and return the ``(steps × agents × 4)`` array.

    A thin public wrapper over :func:`_default_sim_factory` so the crowdsim-marked tests can call
    ``crowdsim.simulation.simulate(...)`` directly (the engine path; requires the jupedsim wheel).
    """
    factory = _default_sim_factory()
    return factory(lattice=lattice, utci_cells=utci_cells, n_agents=n_agents, seed=seed)
