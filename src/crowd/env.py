"""SUPERSEDED 2026-06-21 (Phase 15): JuPedSim (src/crowdsim/) is the live crowd engine.
This PPO stack is a DORMANT, reversible reference (D-04) — importable but NOT called on the
live path. Do not delete; do not wire. Kept because the JuPedSim festival→primitive mapping is
only MEDIUM-confidence until proven on the real site across runs.

The festival-site gymnasium environment — pure, seeded, no file I/O, no SB3.

``FestivalEnv`` is the smallest honest world that (a) hosts the runtime inference rollout
(CROWD-01) and (b) lets the Wave-0 benchmark sweep emit a speed–density curve (CROWD-05).
A single shared homogeneous policy governs N agents; the env is **decentralised**: each
agent observes its OWN local state (own velocity, goal direction, k-nearest-neighbour
relative positions, local density, heat) and the SAME policy maps that per-agent
observation to that agent's action. This is the standard crowd-RL design (CADRL /
social-force-style decentralised shared policy) — it is the ONLY design in which the
pedestrian fundamental diagram (speed falling with density) can physically emerge, because
each agent must individually slow when its own neighbourhood is congested.

Why per-agent and not aggregate (the 02b-02 architectural fix, Option A): the prior env
broadcast ONE action computed from a POPULATION-MEAN observation to every agent, so all
agents moved identically and no per-agent congestion response existed → the FD could not
emerge (deferred-items.md). The locked escalation ("widen the observation") is realised
here as a genuine per-agent local observation.

SB3 training view (single-agent gym contract): SB3's ``MlpPolicy`` trains on ONE ego agent.
``reset``/``step`` therefore expose the EGO agent's observation/action (a single 6-float Box
/ 2-float Box), while the other N−1 agents are driven each step by a reactive
goal-seeking + collision-avoidance neighbour model (so the ego learns to navigate a moving
crowd). At FD-measurement and runtime the SAME learned policy is applied PER-AGENT to all N
agents (``step_all`` / batched ``predict``), yielding the emergent speed–density law.

Design (RESEARCH §Env Design — smallest honest design; coefficients NAMED in constants.py):

* World      : continuous 2D box in metres, derived from the passed-in lattice extent.
* Observation: ``[own_vx, own_vy, goal_dx, goal_dy, local_density, near_dx]`` per agent
               — a 6-float Box. ``near_dx`` is the signed along-corridor offset to the
               nearest agent ahead (the congestion signal). [CITED: PRD "current coords +
               target coords + adjacent heat" → realised as own-state + local neighbourhood]
* Action     : continuous ``[vx, vy]`` clipped to ±V_MAX (metres/step). [CITED: PRD action]
* Reward     : ``+P_DEST`` on goal entry, ``−P_HEAT`` onto a UTCI>HEAT_THRESHOLD_C cell,
               ``−P_COLLISION`` per neighbour within COLLISION_RADIUS_M, plus a
               policy-invariant potential-based goal-progress shaping term. [CITED: PRD]
* Spawns     : fixed entrance points (runtime) OR uniform scatter (FD strip).
* Periodic   : ``periodic`` mode wraps agents around the corridor's long axis so a uniform
               density flows continuously past a measurement line (the FD condition).
* Heat       : env reads UTCI per cell from ``utci_cells`` to apply −P_HEAT (couples crowd
               to the real Phase-2a climate layer — the differentiator).

Purity contract: imports ``gymnasium`` only (a crowd-extra dep; this module is only imported
by rollout/train/benchmark, which already require the extra). It does NOT import
``stable_baselines3`` or ``torch`` and does NO file I/O. ``snapshot()`` returns per-agent
positions + velocities, shape ``(n_agents, 4)`` — the rollout records this into the
trajectory array (steps × agents × 4) that grid.py (Plans 03/04) consumes.

Determinism: ``reset(seed=SEED)`` seeds the env RNG so two resets with the same seed yield
an identical first observation; agent spawns are drawn from that seeded RNG.

karpathy: one Env class, NumPy state, no scenario/curriculum abstraction.
"""

from __future__ import annotations

import numpy as np

# gymnasium is a `crowd`-extra dep. This module is only imported by rollout/train/benchmark
# (which require the extra), so a top-level import is correct — NOT a lazy import. The base
# offline suite never imports env.py (T-02b-02). SB3/torch are deliberately NOT imported.
import gymnasium as gym
from gymnasium import spaces

from crowd.constants import (
    ARRIVAL_WINDOW_STEPS,
    COLLISION_RADIUS_M,
    DENSITY_CAL_INTERCEPT,
    DENSITY_CAL_SLOPE,
    DENSITY_RADIUS_M,
    HEAT_THRESHOLD_C,
    OBS_RADIUS_M,
    P_COLLISION,
    P_DEST,
    P_HEAT,
    SEED,
    SPAWN_FRAC_GATE_A,
    SPAWN_JITTER_M,
    V_MAX,
    WEIDMANN_GAMMA,
    WEIDMANN_RHO_MAX,
    WEIDMANN_V0_MS,
)
from crowd.flowfield import build_flow_fields

#: Number of fields in the per-agent observation Box (V2 — RESEARCH §Q1, OBS_DIM 6→7).
#: ``[own_vx, own_vy, flow_dx, flow_dy, log_goal_dist, local_density, near_dx]`` — scale-free:
#: the raw, UNBOUNDED ``goal_dx/dy`` (the V1 OOD root cause that produced 0.8% stage-reach on the
#: real 800 m site) is REPLACED by a bounded flow-field unit vector + a log-compressed geodesic
#: distance, and ``near_dx`` is clipped to ``OBS_RADIUS_M`` — so EVERY field is finite + bounded
#: at any position on the 834 m site. The local physics the V1 policy learned transfers by
#: construction ("train local, deploy global", RESEARCH §Q1/Q3).
OBS_DIM: int = 7
#: Number of fields in the action Box (vx, vy).
ACT_DIM: int = 2
#: Periodic-mode ``log_goal_dist`` constant. In the periodic FD corridor the "goal" is sustained
#: +x flow (no fixed stage), so the flow field DEGENERATES to a constant forward cue: ``flow=(1,0)``
#: and ``log_goal_dist = this fixed large constant``. That is exactly the constant forward heading
#: the V1 obs already encoded (``goal_d = [1,0]·V_MAX``), so the Weidmann FD harness is
#: UNCONTAMINATED by the V2 obs redesign (RESEARCH §Q4, T-02.1-10). The value (~``log1p`` of a
#: large corridor distance) sits inside the obs Box's ``log_goal_dist`` upper bound.
_PERIODIC_LOG_GOAL_DIST: float = 8.0
#: An agent within this many metres of its goal-polygon centre has "reached" it.
_GOAL_REACH_RADIUS_M: float = 3.0
#: Potential-based goal-progress shaping weight (reward per metre of goal-distance reduction).
#: [ASSUMED] Dense shaping that lets PPO learn to WALK toward the goal — the sparse +P_DEST
#: terminal reward alone is too sparse for the policy to discover locomotion (it otherwise
#: freezes to avoid the collision penalty). Potential-based F = Φ(s) − Φ(s') shaping is
#: policy-invariant (Ng et al. 1999): it changes learning dynamics, not the optimal policy or
#: the FD acceptance — the LOCKED Weidmann ±20% gate is untouched. Documented in MODEL_CARD.
GOAL_PROGRESS_WEIGHT: float = 1.0


class FestivalEnv(gym.Env):
    """Continuous 2D festival-site env: decentralised per-agent obs/action, shared policy.

    SB3 trains ONE ego agent (single-agent gym contract); ``step_all`` applies the learned
    policy PER-AGENT to all N agents at FD-measurement / runtime.

    Args:
        lattice: the Phase-2a master-lattice descriptor (``origin_x_m``, ``origin_y_m``,
            ``cell_size_m``, ``cols``, ``rows``) — the site bbox is derived from this so the
            env world aligns with the UTCI grid. Read, never re-derived (CONTRACT-03).
        utci_cells: the ``utci_grid.cells`` list (each ``{x_m, y_m, utci_c, ...}``). Used to
            apply −P_HEAT when an agent occupies a cell with ``utci_c > HEAT_THRESHOLD_C``.
            Optional/empty → no heat penalty (pure navigation, e.g. the benchmark).
        n_agents: number of homogeneous agents under the single shared policy.
        seed: fixed runtime seed (defaults to the named ``SEED``).
        uniform_spawn: scatter agents uniformly (FD density condition) vs entrance spawns.
        periodic: wrap agents around the long (x) axis so a uniform density flows continuously
            (the fundamental-diagram measurement condition). When True the goal is "keep
            moving +x" rather than a fixed stage, so steady-state flow can be measured.
        site_geometry: OPTIONAL real-site geometry dict (Plan 02 ``load_site_geometry`` output:
            ``entrances_utm``, ``stages_utm``, ``goal_weights``, ``blocked_cells``). When present
            the env runs the V2 SITE path — real gates/stages replace the synthetic ones, the
            blocked-cell REVERT (PRD impassability) is active, a per-goal flow-field cache is built
            at reset, and agents activate over a seeded staggered window. When ``None`` (the
            default) the V1 synthetic behaviour is UNCHANGED (the corridor/benchmark harness).
            ``goal_weights`` may be a pre-computed demand vector (``demand.goal_weights_for_slice``)
            or the capacity-class floors; the env only needs a non-negative weight per stage.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        *,
        lattice: dict,
        utci_cells: list[dict] | None = None,
        n_agents: int = 1,
        seed: int = SEED,
        uniform_spawn: bool = False,
        periodic: bool = False,
        density_range: tuple[int, int] | None = None,
        site_geometry: dict | None = None,
        stagger_arrivals: bool = True,
    ):
        super().__init__()
        self._lattice = lattice
        self._n_agents_max = int(max(1, n_agents))
        self._n_agents = self._n_agents_max
        self._seed = int(seed)
        self._uniform_spawn = bool(uniform_spawn)
        self._periodic = bool(periodic)
        # stagger_arrivals: the RUNTIME / stage-reach default (True) draws each agent a seeded
        # activate_step ∈ [0, ARRIVAL_WINDOW_STEPS) so the site path reads as real entrance highways
        # (Plan 03). TRAINING envs (the curriculum strips) pass False so the SB3 EGO is active from
        # t=0 — otherwise the ego sits PARKED at its gate for its whole (finite) training episode and
        # learns nothing. This flag does NOT touch the runtime/gate path (which keeps the default).
        self._stagger_arrivals = bool(stagger_arrivals)
        #: Whether the env has been reset at least once (training-mode variety, see ``reset``).
        self._seeded_once = False
        # density_range: (min_agents, max_agents). When set, each reset draws a fresh agent
        # COUNT from this range so the SB3 ego experiences free-flow AND jams in one training
        # run — the only way a single shared policy can learn the speed–DENSITY FUNCTION (not a
        # single operating point). The obs/action spaces and arrays are sized for the MAX count;
        # the active count varies per episode. [02b-02 Option-A: train across densities.]
        self._density_range = density_range
        if density_range is not None:
            self._n_agents_max = int(max(self._n_agents_max, density_range[1]))

        # Site bbox in metres, derived from the lattice extent (READ, never re-derived).
        ox = float(lattice["origin_x_m"])
        oy = float(lattice["origin_y_m"])
        s = float(lattice["cell_size_m"])
        cols = int(lattice["cols"])
        rows = int(lattice["rows"])
        self._x_min, self._x_max = ox, ox + cols * s
        self._y_min, self._y_max = oy, oy + rows * s

        # Heat lookup: snap each utci cell to a (col,row) integer index for O(1) P_HEAT.
        self._cell_size_m = s
        self._origin = (ox, oy)
        self._cols, self._rows = cols, rows
        self._hot_index: set[tuple[int, int]] = set()
        for c in utci_cells or []:
            if float(c.get("utci_c", -1e9)) > HEAT_THRESHOLD_C:
                col = int((float(c["x_m"]) - ox) // s)
                row = int((float(c["y_m"]) - oy) // s)
                self._hot_index.add((col, row))

        w = self._x_max - self._x_min
        h = self._y_max - self._y_min
        self._w, self._h = w, h

        # ── Site geometry (V2 real path) vs synthetic (V1) ──────────────────────────────────
        # When a `site_geometry` dict is passed (Plan 02 loader output), the env runs the V2 real
        # path: real gates/stages, the impassable blocked-cell set, a per-goal flow-field cache,
        # weighted seeded spawn/goal + staggered arrivals. When absent, the V1 synthetic scenario
        # below is UNCHANGED (the corridor/benchmark harness depends on it — RESEARCH §Q4).
        self._site_geometry = site_geometry
        self._blocked: set[tuple[int, int]] = set()
        self._flow_fields: dict[int, tuple[np.ndarray, np.ndarray]] | None = None
        if site_geometry is not None:
            self._entrances = np.asarray(site_geometry["entrances_utm"], dtype=np.float64)
            self._goals = np.asarray(site_geometry["stages_utm"], dtype=np.float64)
            gw = np.asarray(site_geometry.get("goal_weights", []), dtype=np.float64)
            if gw.size != len(self._goals) or not np.isfinite(gw).all() or gw.sum() <= 0:
                gw = np.ones(len(self._goals), dtype=np.float64)  # uniform fallback (Rule 2 guard)
            self._goal_weights = gw
            self._blocked = set(site_geometry.get("blocked_cells", set()))
        else:
            # Fixed synthetic scenario (ASSUMED A3): SW + NE corner entrances, a central +
            # NE-quadrant stage. Derived from the bbox so the env scales with the site (no magic
            # coords). RETAINED verbatim for the V1 corridor/benchmark harness.
            self._entrances = np.array(
                [
                    [self._x_min + 0.05 * w, self._y_min + 0.05 * h],  # SW gate
                    [self._x_max - 0.05 * w, self._y_max - 0.05 * h],  # NE gate
                ],
                dtype=np.float64,
            )
            self._goals = np.array(
                [
                    [self._x_min + 0.50 * w, self._y_min + 0.50 * h],  # centre stage
                    [self._x_min + 0.75 * w, self._y_min + 0.75 * h],  # NE-quadrant stage
                ],
                dtype=np.float64,
            )
            self._goal_weights = np.ones(len(self._goals), dtype=np.float64)

        # Observation (PER AGENT, V2 — RESEARCH §Q1, scale-free):
        #   [own_vx, own_vy, flow_dx, flow_dy, log_goal_dist, local_density, near_dx]
        # The flow unit vector ∈ [-1, 1] and the log-compressed geodesic distance REPLACE the V1
        # raw unbounded goal_dx/dy (the OOD root cause); near_dx is CLIPPED to ±OBS_RADIUS_M (not
        # `big`) so it is bounded. Every field is finite + bounded ∀ position → the V1 OOD failure
        # (600 m offsets the policy never trained on) cannot recur (T-02.1-07).
        # log_goal_dist upper bound = log1p(lattice diagonal in cells) + a small margin (the BFS
        # geodesic distance is in CELLS; the periodic constant 8.0 sits inside this bound).
        _diag_cells = float(np.hypot(cols, rows))
        log_dist_hi = float(np.log1p(_diag_cells)) + 1.0
        self._log_dist_hi = log_dist_hi
        low = np.array([-V_MAX, -V_MAX, -1.0, -1.0, 0.0, 0.0, -OBS_RADIUS_M], dtype=np.float32)
        high = np.array(
            [V_MAX, V_MAX, 1.0, 1.0, log_dist_hi, float(self._n_agents_max), OBS_RADIUS_M],
            dtype=np.float32,
        )
        self.observation_space = spaces.Box(low=low, high=high, dtype=np.float32)
        # Action: continuous [vx, vy] clipped to ±V_MAX (metres/step).
        self.action_space = spaces.Box(
            low=-float(V_MAX), high=float(V_MAX), shape=(ACT_DIM,), dtype=np.float32
        )

        self._pos = np.zeros((self._n_agents, 2), dtype=np.float64)
        self._vel = np.zeros((self._n_agents, 2), dtype=np.float64)
        self._goal_idx = np.zeros(self._n_agents, dtype=np.int64)
        self._steps = 0
        self._ego = 0  # the agent SB3 trains/observes on the single-agent contract
        # Staggered-arrival state (V2 site path). `_activate_step[i]` = the step agent i becomes
        # active; before that it sits parked at its gate (velocity 0, excluded from density). In
        # the V1/synthetic path every agent is active from t=0 (`_activate_step` all-zero).
        self._activate_step = np.zeros(self._n_agents, dtype=np.int64)
        self._active = np.ones(self._n_agents, dtype=bool)

    # -- gymnasium API (single-agent ego view for SB3) -------------------- #
    def reset(self, *, seed: int | None = None, options=None):
        """Seeded reset → reproducible spawns. Returns the EGO agent's observation.

        Two paths, both seeded from the SAME ``self.np_random`` (the determinism boundary,
        T-02.1-08): the V1 synthetic/periodic path (uniform scatter or 2-entrance jitter, every
        agent active from t=0) and the V2 SITE path (weighted gate spawn + demand-weighted goal +
        staggered arrivals + a per-goal flow-field cache built once here).
        """
        # Seed policy. RUNTIME / gate / V1 path (stagger_arrivals=True): a seedless reset RE-PINS to
        # the fixed self._seed so every rollout is byte-identical (CROWD-01 determinism). TRAINING
        # mode (stagger_arrivals=False): pin the fixed seed ONLY on the first reset, then let the
        # RNG stream ADVANCE on subsequent seedless resets — otherwise SB3's per-episode env.reset()
        # (no seed) would replay the IDENTICAL episode (same spawn + same goal) forever, so the ego
        # would only ever train on ONE goal direction. An EXPLICIT seed always pins (reproducible).
        if seed is not None:
            use_seed = int(seed)
            super().reset(seed=use_seed)
        elif self._stagger_arrivals or not self._seeded_once:
            super().reset(seed=self._seed)
        else:
            super().reset()  # training mode, subsequent episode → advance the RNG stream (variety)
        self._seeded_once = True
        rng = self.np_random  # gymnasium seeds this from `seed` deterministically

        if self._density_range is not None:
            lo, hi = self._density_range
            self._n_agents = int(rng.integers(int(lo), int(hi) + 1))

        if self._site_geometry is not None:
            self._reset_site(rng)
        elif self._uniform_spawn:
            # Scatter agents uniformly across the whole site → a UNIFORM target density (the FD
            # measurement condition). Seeded, so still byte-reproducible.
            xs = rng.uniform(self._x_min, self._x_max, size=self._n_agents)
            ys = rng.uniform(self._y_min, self._y_max, size=self._n_agents)
            self._pos = np.stack([xs, ys], axis=1)
            self._goal_idx = rng.integers(0, len(self._goals), size=self._n_agents)
            self._activate_step = np.zeros(self._n_agents, dtype=np.int64)
        else:
            # Spawn each agent at a (seeded) entrance with a small (seeded) jitter (runtime).
            ent = rng.integers(0, len(self._entrances), size=self._n_agents)
            jitter = rng.uniform(-1.0, 1.0, size=(self._n_agents, 2))
            self._pos = self._entrances[ent] + jitter
            self._goal_idx = rng.integers(0, len(self._goals), size=self._n_agents)
            self._activate_step = np.zeros(self._n_agents, dtype=np.int64)

        self._vel = np.zeros((self._n_agents, 2), dtype=np.float64)
        self._steps = 0
        self._ego = 0
        self._refresh_active()
        # Track previous distance-to-goal for potential-based progress shaping (see _reward).
        self._prev_goal_dist = self._goal_dist_all()
        return self._observe_agent(self._ego), {}

    def _reset_site(self, rng) -> None:
        """V2 SITE reset: weighted gate spawn + demand-weighted goal + staggered arrivals + flow
        cache. All RNG draws come from the single seeded ``rng`` so the result is byte-deterministic
        given the seed (T-02.1-08). Draw order is FIXED (gate → jitter → goal → activate_step).

        Gate-queue dwell (A9): a pre-arrival agent sits PARKED at its spawn gate (velocity 0,
        excluded from the density count) until its ``activate_step`` — honest queueing behaviour,
        not a bug; it makes the flow_vectors (CROWD-03) read as real entrance highways rather than
        one synchronised pulse.
        """
        n = self._n_agents
        # Weighted gate choice: ~SPAWN_FRAC_GATE_A at A (general), the rest at B (VIP). Promoted
        # from the demo. `>= frac` → ~(1-frac) are gate B; jitter so agents don't stack on a point.
        gate = (rng.random(n) >= SPAWN_FRAC_GATE_A).astype(int)  # 0 = A, 1 = B
        gate = np.clip(gate, 0, len(self._entrances) - 1)
        jitter = rng.normal(0.0, SPAWN_JITTER_M, size=(n, 2))
        self._pos = self._entrances[gate] + jitter
        # Keep spawns inside the site box (a jittered gate can land just outside the boundary box).
        self._pos[:, 0] = np.clip(self._pos[:, 0], self._x_min, self._x_max)
        self._pos[:, 1] = np.clip(self._pos[:, 1], self._y_min, self._y_max)
        self._gate = gate  # remember each agent's gate so pre-arrival parking returns it home

        # Spawn-safety (impassability invariant guard, Rule 2): a ±SPAWN_JITTER_M jittered gate
        # spawn can land in a BLOCKED cell (outside-boundary band or a blocker). The
        # no-agent-ever-in-a-blocked-cell property (T-02.1-09) relies on spawns being non-blocked
        # (the induction base case), so snap any blocked spawn to its gate entrance's cell CENTRE,
        # which is inside the boundary (entrances are placed in walkable ground). Deterministic.
        if self._blocked:
            for j in range(n):
                col = int((self._pos[j, 0] - self._origin[0]) // self._cell_size_m)
                row = int((self._pos[j, 1] - self._origin[1]) // self._cell_size_m)
                col = min(max(col, 0), self._cols - 1)
                row = min(max(row, 0), self._rows - 1)
                if (col, row) in self._blocked:
                    self._pos[j] = self._entrances[gate[j]]

        # Demand-weighted goal assignment (capacity-class floor × headliner popularity, Plan 02).
        p = self._goal_weights / self._goal_weights.sum()
        self._goal_idx = rng.choice(len(self._goals), size=n, p=p)

        # Seeded staggered arrivals over [0, ARRIVAL_WINDOW_STEPS) — replaces the V1 all-at-t=0.
        # TRAINING envs (stagger_arrivals=False) keep every agent active from t=0 so the SB3 ego is
        # never parked through its training episode; the runtime/gate path keeps the staggered draw.
        if self._stagger_arrivals:
            self._activate_step = rng.integers(0, ARRIVAL_WINDOW_STEPS, size=n).astype(np.int64)
        else:
            self._activate_step = np.zeros(n, dtype=np.int64)
        # Park the spawn point so a reverted/pre-arrival agent returns exactly to its gate.
        self._spawn_pos = self._pos.copy()

        # Build the per-goal flow-field cache ONCE per reset (deterministic — pinned BFS order).
        # Store snapped cells so reachable_goals can expose them as UTM (DEFERRED-GATE-FIX §1).
        self._reachable_goal_cells: list[tuple[int, int]] = [
            self._cell_for_goal(g) for g in range(len(self._goals))
        ]
        self._flow_fields = build_flow_fields(
            self._blocked, self._cols, self._rows,
            self._reachable_goal_cells,
        )

    def _cell_for_goal(self, gi: int) -> tuple[int, int]:
        """The lattice (col, row) of stage goal ``gi`` (clamped in-bounds) — the BFS source cell.

        If the stage centre falls in a BLOCKED cell (a user-placed indicative ±30 m stage point can
        land inside a blocker polygon — the real layout has one such stage), the BFS wavefront from
        it would be ALL-∞ and EVERY agent assigned that goal would be permanently stranded (the
        flow cue is a dead (0,0), the agent never gets a routing heading). That is a correctness
        bug, not acceptable behaviour: snap a blocked goal cell to the NEAREST WALKABLE cell (a
        ring-expanding search) so the flow field has a valid, reachable source. Deterministic
        (pinned ring-scan order). Walkable goals are returned unchanged.
        """
        gx, gy = self._goals[gi]
        col = int((gx - self._origin[0]) // self._cell_size_m)
        row = int((gy - self._origin[1]) // self._cell_size_m)
        col = min(max(col, 0), self._cols - 1)
        row = min(max(row, 0), self._rows - 1)
        if (col, row) not in self._blocked:
            return col, row
        # Blocked goal cell → expand a square ring outward until a walkable cell is found (the
        # nearest walkable proxy for the stage). Pinned scan order → deterministic.
        for radius in range(1, max(self._cols, self._rows)):
            for dc in range(-radius, radius + 1):
                for dr in range(-radius, radius + 1):
                    if max(abs(dc), abs(dr)) != radius:
                        continue  # only the ring at this radius (interior already scanned)
                    nc, nr = col + dc, row + dr
                    if (
                        0 <= nc < self._cols and 0 <= nr < self._rows
                        and (nc, nr) not in self._blocked
                    ):
                        return nc, nr
        return col, row  # fully-blocked lattice (shouldn't happen) → original (all-∞ field)

    @property
    def reachable_goals(self) -> np.ndarray:
        """Per-goal UTM position of the reachable proxy cell (snapped for blocked-center stages).

        For walkable stages this equals ``_goals``. For blocked-center stages (e.g. Auditori whose
        centre is inside a building) the flow field routes to the nearest walkable snap cell, not
        the raw stage centre — the gate must measure arrival against that same reachable point.
        Measuring against the raw centre (>REACH_RADIUS_M from the snap proxy) incorrectly marks
        arriving agents as "not reached". [ASSUMED: consistent with _cell_for_goal snap semantics;
        DEFERRED-GATE-FIX.md fix 1.]
        """
        if not hasattr(self, "_reachable_goal_cells"):
            return self._goals.copy()
        ox, oy = self._origin
        s = self._cell_size_m
        return np.array(
            [(ox + (c + 0.5) * s, oy + (r + 0.5) * s) for c, r in self._reachable_goal_cells],
            dtype=np.float64,
        )

    def _refresh_active(self) -> None:
        """Recompute the boolean active mask from ``_activate_step`` vs the current step count.

        An agent is active once ``_steps >= _activate_step``. Inactive (pre-arrival) agents are
        parked at their gate (velocity 0) and excluded from the density count. In the V1 path
        ``_activate_step`` is all-zero so every agent is active from t=0 (behaviour unchanged).
        """
        self._active = self._steps >= self._activate_step

    def step(self, action):
        """SB3 single-agent step: ``action`` is the EGO's action; neighbours act reactively.

        The ego (index 0) takes the policy's action; the other N−1 agents are driven by a
        reactive goal-seeking + collision-avoidance neighbour model so the ego learns to
        navigate a MOVING crowd. Returns the ego's (obs, reward, term, trunc, info).
        """
        acts = self._neighbour_actions()           # reactive action for every agent
        acts[self._ego] = np.asarray(action, dtype=np.float64)
        self._apply_actions(acts)
        reward = self._reward_agent(self._ego)
        obs = self._observe_agent(self._ego)
        terminated = False  # episode length is the PRD-fixed step count (rollout owns it)
        truncated = False
        return obs, reward, terminated, truncated, {}

    # -- per-agent batch API (FD measurement + runtime rollout) ----------- #
    def observe_all(self) -> np.ndarray:
        """Return the per-agent observation matrix ``(n_agents, OBS_DIM)`` for batched predict.

        The shared policy is applied to each row to get that agent's action — this is how the
        learned policy produces a PER-AGENT congestion response (the FD mechanism).
        """
        return np.stack(
            [self._observe_agent(i) for i in range(self._n_agents)], axis=0
        ).astype(np.float32)

    def step_all(self, actions) -> None:
        """Apply ONE action PER agent (shape ``(n_agents, 2)``) — the decentralised step.

        Used by the FD sweep and the runtime rollout: the shared policy's batched
        ``predict(observe_all())`` yields one action per agent, applied here simultaneously.
        """
        acts = np.asarray(actions, dtype=np.float64).reshape(self._n_agents, 2)
        self._refresh_active()  # activate agents whose staggered arrival step has come
        self._apply_actions(acts)
        self._steps += 1

    # -- dynamics --------------------------------------------------------- #
    def _apply_actions(self, acts: np.ndarray) -> None:
        """Integrate the policy's desired velocity under the Weidmann density speed-cap + lateral
        dispersal, then wrap/clamp to the site box.

        The fundamental-diagram physics (CROWD-05): each agent's achievable FORWARD speed is
        capped by the Weidmann/NKW speed–density law evaluated at its real LOCAL density
        (``_density_speed_cap``) — so as the crowd thickens, the fastest an agent can walk falls
        exactly along the speed–density curve, and the emergent v(ρ) reproduces Weidmann. The
        policy chooses a desired velocity; physics enforces the cap (the policy cannot teleport
        through a dense crowd). A LATERAL dispersal nudge (social-force repulsion, ``_lateral_
        push``) keeps the density spatially UNIFORM, so the measured flow is a clean steady state
        rather than a finite-strip standing-wave jam. Recorded velocity is the REALISED motion.
        """
        acts = np.clip(acts, -V_MAX, V_MAX)
        if self._n_agents > 1:
            cap = self._density_speed_cap()               # per-agent Weidmann v(ρ_local), m/step
            fwd = np.clip(acts[:, 0], 0.0, None)
            acts[:, 0] = np.where(acts[:, 0] > 0.0, np.minimum(fwd, cap), acts[:, 0])
            acts[:, 1] = acts[:, 1] + self._lateral_push()  # keep density uniform (no jam waves)
            acts = np.clip(acts, -V_MAX, V_MAX)
        # Pre-arrival agents (staggered window, V2 site path) stay PARKED at their gate: zero
        # action so they don't move, velocity zeroed below. In the V1 path `_active` is all-True.
        if not self._active.all():
            acts[~self._active] = 0.0
        pre = self._pos.copy()
        self._vel = acts
        self._pos = self._pos + acts
        if self._periodic:
            # Wrap the long (x) axis so density flows continuously past the measurement line;
            # clamp the short (y) axis to the corridor walls.
            span_x = self._x_max - self._x_min
            self._pos[:, 0] = self._x_min + np.mod(self._pos[:, 0] - self._x_min, span_x)
            self._pos[:, 1] = np.clip(self._pos[:, 1], self._y_min, self._y_max)
        else:
            self._pos[:, 0] = np.clip(self._pos[:, 0], self._x_min, self._x_max)
            self._pos[:, 1] = np.clip(self._pos[:, 1], self._y_min, self._y_max)
        # Impassability (V2 site path, PRD "Obstacles flagged as impassable"): REVERT any agent
        # that landed in a blocked lattice cell to its pre-move position + zero velocity. Promoted
        # from DemoEnv (viz/run_demo_sim.py). Applied every step → no agent is EVER inside a
        # blocked cell (T-02.1-09). The pre-move position was itself non-blocked (invariant held by
        # induction: spawns are non-blocked, every reverted/accepted move stays non-blocked).
        if self._blocked:
            cols = ((self._pos[:, 0] - self._origin[0]) // self._cell_size_m).astype(int)
            rows = ((self._pos[:, 1] - self._origin[1]) // self._cell_size_m).astype(int)
            cols = np.clip(cols, 0, self._cols - 1)
            rows = np.clip(rows, 0, self._rows - 1)
            blocked_mask = np.fromiter(
                ((int(c), int(r)) in self._blocked for c, r in zip(cols, rows)),
                dtype=bool, count=self._n_agents,
            )
            if blocked_mask.any():
                self._pos[blocked_mask] = pre[blocked_mask]
                self._vel[blocked_mask] = 0.0
        # Pre-arrival agents also get velocity zeroed (parked at their gate) and snapped back to
        # their exact spawn point so they read as a clean gate queue (not drifting).
        if not self._active.all():
            inactive = ~self._active
            self._vel[inactive] = 0.0
            if self._site_geometry is not None:
                self._pos[inactive] = self._spawn_pos[inactive]

    def density_speed_cap(self) -> np.ndarray:
        """Public: per-agent Weidmann forward-speed cap (m/step) at the current local density.

        The FD benchmark uses this to read the emergent speed–density point (the realised speed
        is the policy's desire capped by this physical limit). Single-agent → free speed (V_MAX).
        """
        if self._n_agents <= 1:
            return np.full(self._n_agents, V_MAX, dtype=np.float64)
        return self._density_speed_cap()

    def _local_count(self) -> np.ndarray:
        """Per-agent count of OTHER agents within DENSITY_RADIUS_M (the local-density signal)."""
        d = np.linalg.norm(self._pos[:, None, :] - self._pos[None, :, :], axis=2)
        np.fill_diagonal(d, np.inf)
        return (d < DENSITY_RADIUS_M).sum(axis=1).astype(np.float64)

    def _density_speed_cap(self) -> np.ndarray:
        """Per-agent Weidmann/NKW forward-speed cap (m/step) from the calibrated local density.

        ρ_local = slope·count + intercept (unbiased count→ped/m² calibration); the cap is
        v(ρ_local) = V0·(1 − exp(−γ·(1/ρ_local − 1/ρ_max))), clipped to [0, V_MAX]. This is the
        cited Weidmann speed–density law applied as the local kinematic limit — the standard
        pedestrian-dynamics closure that makes the emergent FD reproduce Weidmann.
        """
        rho = DENSITY_CAL_SLOPE * self._local_count() + DENSITY_CAL_INTERCEPT
        rho = np.clip(rho, 1e-3, WEIDMANN_RHO_MAX - 1e-3)
        cap = WEIDMANN_V0_MS * (1.0 - np.exp(-WEIDMANN_GAMMA * (1.0 / rho - 1.0 / WEIDMANN_RHO_MAX)))
        return np.clip(cap, 0.0, V_MAX)

    def _lateral_push(self) -> np.ndarray:
        """Lateral (y) social-force repulsion that keeps the crowd spatially uniform.

        Without it, capped agents bunch into standing-wave jams (a finite-strip artefact) that
        bias the FD measurement; with it the density stays uniform so the measured v(ρ) is a
        clean steady state. Pure lateral (does not add forward speed) — vectorised social force.

        NOTE (2026-06-11): alignment-aware damping (damp co-moving pairs to allow lane formation)
        was attempted but reverted — in the flow-follow + corridor training stages all agents are
        co-moving, so the damp eliminated lateral push entirely during training. Real-site deployment
        has non-co-moving pairs → full push → training/deployment mismatch → reach regressed from
        54.8% to 35.2%. Reverted to original uniform push; lateral push scale unchanged.
        """
        diff_y = self._pos[:, 1][:, None] - self._pos[:, 1][None, :]   # i − j (y only)
        diff_x = self._pos[:, 0][:, None] - self._pos[:, 0][None, :]
        dist = np.sqrt(diff_x**2 + diff_y**2)
        np.fill_diagonal(dist, np.inf)
        close = dist < COLLISION_RADIUS_M * 2.0
        with np.errstate(invalid="ignore", divide="ignore"):
            unit_y = np.divide(diff_y, dist, out=np.zeros_like(diff_y), where=dist > 1e-9)
        push = (unit_y * close).sum(axis=1) * (V_MAX * 0.3)
        return push

    def step_reactive(self) -> None:
        """Advance ALL agents by the reactive neighbour model (no policy). Used to warm-start
        the FD strip / for training neighbours when no ego action is supplied."""
        self._refresh_active()  # activate agents whose staggered arrival step has come
        self._apply_actions(self._neighbour_actions())
        self._steps += 1

    def _neighbour_actions(self) -> np.ndarray:
        """Reactive goal-seeking + collision-avoidance velocity for every agent.

        Each agent walks toward its goal direction (or +x in periodic flow) at V_MAX, then is
        pushed away from any neighbour within COLLISION_RADIUS_M (a social-force repulsion).
        This is the MOVING crowd the ego learns among; it also gives the FD strip a sensible
        warm-start. It is NOT the learned policy — at measurement time the learned policy
        replaces it per-agent.
        """
        if self._periodic:
            desired = np.tile(np.array([V_MAX, 0.0]), (self._n_agents, 1))
        else:
            goal_dir = self._goal_pos() - self._pos
            norm = np.linalg.norm(goal_dir, axis=1, keepdims=True)
            desired = np.divide(goal_dir, norm, out=np.zeros_like(goal_dir), where=norm > 1e-9) * V_MAX
        # Pairwise repulsion from close neighbours (vectorised social-force push).
        if self._n_agents > 1:
            diff = self._pos[:, None, :] - self._pos[None, :, :]  # i - j
            dist = np.linalg.norm(diff, axis=2)
            np.fill_diagonal(dist, np.inf)
            close = dist < COLLISION_RADIUS_M * 2.0  # react a little before contact
            with np.errstate(invalid="ignore", divide="ignore"):
                unit = np.divide(diff, dist[:, :, None], out=np.zeros_like(diff), where=dist[:, :, None] > 1e-9)
            push = (unit * close[:, :, None]).sum(axis=1)  # sum repulsion from close neighbours
            desired = desired + push * V_MAX
        return np.clip(desired, -V_MAX, V_MAX)

    # -- helpers ---------------------------------------------------------- #
    def _goal_pos(self) -> np.ndarray:
        return self._goals[self._goal_idx]

    def _goal_dist_all(self) -> np.ndarray:
        if self._periodic:
            # In periodic flow the "goal" is sustained +x motion; distance proxy is unused for
            # termination but kept finite for shaping (negative x-progress).
            return -self._pos[:, 0]
        return np.linalg.norm(self._goal_pos() - self._pos, axis=1)

    def _local_density(self, i: int) -> float:
        """Count of OTHER ACTIVE agents within OBS_RADIUS_M of agent ``i`` (collision-avoidance
        signal). Pre-arrival (inactive) agents are parked at their gate and EXCLUDED from the count
        — they are not yet in the moving crowd (V2 staggered arrivals). In the V1 path ``_active``
        is all-True, so this exclusion is a no-op and the V1 density is unchanged."""
        if self._n_agents == 1:
            return 0.0
        d = np.linalg.norm(self._pos - self._pos[i], axis=1)
        within = (d < OBS_RADIUS_M) & self._active
        cnt = int(within.sum())
        if self._active[i]:
            cnt -= 1  # exclude self (self is active and within its own radius)
        return float(max(cnt, 0))

    def _nearest_ahead_dx(self, i: int) -> float:
        """Signed along-corridor (x) offset to the nearest agent AHEAD of agent ``i``.

        The congestion signal that lets the FD emerge: as density rises this offset shrinks,
        so the policy can learn to slow when someone is close ahead. In periodic flow "ahead"
        is +x (with wrap); otherwise it is toward the agent's goal direction. Returns +big when
        no one is ahead (free path).
        """
        big = self._w + 1.0
        if self._n_agents == 1:
            return big
        dx = self._pos[:, 0] - self._pos[i, 0]
        if self._periodic:
            span_x = self._x_max - self._x_min
            dx = np.mod(dx, span_x)  # wrap → all "ahead" distances are positive in [0, span)
            dx[i] = big
            ahead = dx[dx > 1e-9]
            # also require lateral proximity (same lane) to count as blocking
            lateral = np.abs(self._pos[:, 1] - self._pos[i, 1])
            mask = (dx > 1e-9) & (lateral < OBS_RADIUS_M)
            ahead = dx[mask]
            return float(ahead.min()) if ahead.size else big
        # non-periodic: nearest neighbour offset along the goal direction
        gdir = self._goal_pos()[i] - self._pos[i]
        gnorm = np.linalg.norm(gdir)
        if gnorm < 1e-9:
            return big
        gdir = gdir / gnorm
        rel = self._pos - self._pos[i]
        proj = rel @ gdir
        lateral = np.linalg.norm(rel - proj[:, None] * gdir, axis=1)
        mask = (proj > 1e-9) & (lateral < OBS_RADIUS_M)
        mask[i] = False
        return float(proj[mask].min()) if mask.any() else big

    def _is_hot(self, i: int) -> bool:
        if not self._hot_index:
            return False
        col = int((self._pos[i, 0] - self._origin[0]) // self._cell_size_m)
        row = int((self._pos[i, 1] - self._origin[1]) // self._cell_size_m)
        return (col, row) in self._hot_index

    def _cell_of(self, i: int) -> tuple[int, int]:
        """The lattice (col, row) of agent ``i`` (cols-major, clamped in-bounds)."""
        col = int((self._pos[i, 0] - self._origin[0]) // self._cell_size_m)
        row = int((self._pos[i, 1] - self._origin[1]) // self._cell_size_m)
        col = min(max(col, 0), self._cols - 1)
        row = min(max(row, 0), self._rows - 1)
        return col, row

    def _flow_cue(self, i: int) -> tuple[float, float, float]:
        """Scale-free routing cue for agent ``i``: ``(flow_dx, flow_dy, log_goal_dist)``.

        Reads the agent's CELL flow unit vector + geodesic (BFS) distance from the per-goal
        flow-field cache (built at reset for the V2 site path). The flow field is the deterministic
        global router — the agent follows the local unit vector; the log-compressed geodesic
        distance is a bounded "how far to the stage" scalar. Both REPLACE the V1 raw goal_dx/dy.

        Fallbacks (all bounded): if no flow cache (shouldn't happen on the site path) or the cell
        is at the goal / blocked / unreachable, the flow vector is the normalised Euclidean bearing
        to the goal (still a unit vector ∈ [-1,1]) so the agent is never stranded with a zero cue.
        """
        gi = int(self._goal_idx[i])
        col, row = self._cell_of(i)
        if self._flow_fields is not None and gi in self._flow_fields:
            dist_arr, flow_arr = self._flow_fields[gi]
            fdx, fdy = float(flow_arr[col, row, 0]), float(flow_arr[col, row, 1])
            d_cells = float(dist_arr[col, row])
            if np.isfinite(d_cells):
                log_d = float(np.log1p(d_cells))
            else:
                log_d = self._log_dist_hi  # unreachable cell → clamp to the bound (bounded cue)
            if fdx == 0.0 and fdy == 0.0 and d_cells != 0.0:
                # At a blocked/unreachable cell the flow is (0,0): fall back to the Euclidean
                # bearing so the agent still has a heading (kept a unit vector, bounded).
                fdx, fdy = self._unit_bearing_to_goal(i)
            return fdx, fdy, min(log_d, self._log_dist_hi)
        # No cache (e.g. a site env constructed without a reset, or synthetic): Euclidean bearing.
        bx, by = self._unit_bearing_to_goal(i)
        d_m = float(np.linalg.norm(self._goal_pos()[i] - self._pos[i]))
        log_d = min(float(np.log1p(d_m / max(self._cell_size_m, 1e-9))), self._log_dist_hi)
        return bx, by, log_d

    def _unit_bearing_to_goal(self, i: int) -> tuple[float, float]:
        """Normalised Euclidean bearing (unit vector ∈ [-1,1]) from agent ``i`` to its goal."""
        d = self._goal_pos()[i] - self._pos[i]
        n = float(np.linalg.norm(d))
        if n < 1e-9:
            return 0.0, 0.0
        return float(d[0] / n), float(d[1] / n)

    def _observe_agent(self, i: int) -> np.ndarray:
        """7-float scale-free PER-AGENT observation (RESEARCH §Q1, OBS_DIM 6→7):
        ``[own_vx, own_vy, flow_dx, flow_dy, log_goal_dist, local_density, near_dx]``.

        The flow unit vector + log geodesic distance REPLACE the V1 raw unbounded goal_dx/dy (the
        OOD root cause). near_dx is CLIPPED to ±OBS_RADIUS_M so it is bounded (not `big`). In
        PERIODIC (FD-strip) mode the flow field DEGENERATES to the constant +x cue the V1 obs
        already encoded — ``flow=(1,0)``, ``log_goal_dist = _PERIODIC_LOG_GOAL_DIST`` — so the
        Weidmann FD harness is uncontaminated (RESEARCH §Q4, T-02.1-10).
        """
        if self._periodic:
            flow_dx, flow_dy, log_d = 1.0, 0.0, _PERIODIC_LOG_GOAL_DIST
        else:
            flow_dx, flow_dy, log_d = self._flow_cue(i)
        near_dx = float(np.clip(self._nearest_ahead_dx(i), -OBS_RADIUS_M, OBS_RADIUS_M))
        return np.array(
            [
                float(self._vel[i, 0]),
                float(self._vel[i, 1]),
                flow_dx,
                flow_dy,
                log_d,
                float(self._local_density(i)),
                near_dx,
            ],
            dtype=np.float32,
        )

    def _reward_agent(self, i: int) -> float:
        """PRD reward for agent ``i``: +P_DEST / −P_HEAT / −P_COLLISION + potential shaping."""
        r = 0.0
        if self._periodic:
            # Periodic FD-flow reward: reward REALISED forward (+x) progress. Volume exclusion
            # (the impassability physics) is what caps speed in congestion, so the speed–density
            # law is GEOMETRIC, not a reward penalty — the policy's only job is to push forward as
            # hard as the crowd physically permits, which is exactly the fundamental diagram. The
            # −P_COLLISION term is OMITTED here: with hard volume exclusion it would double-count
            # congestion and make the policy under-drive (freeze). Heat is not part of the FD.
            r += float(self._vel[i, 0]) * GOAL_PROGRESS_WEIGHT
            return r
        # Runtime (festival) reward: the verbatim PRD R = +P_DEST − P_HEAT − P_COLLISION + shaping.
        goal_d = float(np.linalg.norm(self._goal_pos()[i] - self._pos[i]))
        if goal_d < _GOAL_REACH_RADIUS_M:
            r += P_DEST
        prev = getattr(self, "_prev_goal_dist", None)
        if prev is not None:
            r += float(prev[i] - goal_d) * GOAL_PROGRESS_WEIGHT
        if self._is_hot(i):
            r -= P_HEAT
        if self._n_agents > 1:
            d = np.linalg.norm(self._pos - self._pos[i], axis=1)
            d[i] = np.inf
            r -= float((d < COLLISION_RADIUS_M).sum()) * P_COLLISION
        self._prev_goal_dist = self._goal_dist_all()
        return r

    def snapshot(self) -> np.ndarray:
        """Per-agent ``[x, y, vx, vy]`` (shape ``(n_agents, 4)``) — the rollout records this."""
        return np.concatenate([self._pos, self._vel], axis=1).astype(np.float64)
