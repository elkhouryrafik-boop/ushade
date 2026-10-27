"""The ONE place every Phase-2b PRD/ASSUMED magic number lives (T-02b-01).

Every downstream Phase-2b module (``env.py``, ``rollout.py``, ``grid.py``, ``crowd.py``,
the benchmark test) imports its constants from here — the numbers are NEVER inlined. The
PRD-exact integers are the immutable acceptance numbers: drift here is silent acceptance
corruption, so ``tests/test_crowd_env.py::test_constants_are_prd_exact`` asserts them
exactly and runs in the base (torch-free) suite so any drift fails CI.

This module imports nothing heavy (pure ints/floats) so it loads with NO crowd extra
installed.

Two provenance tiers are tagged inline:

* ``[CITED: PRD §Phase-2]`` — verbatim PRD numbers. Immutable; never tune to pass a test.
* ``[ASSUMED]`` — Claude's-discretion defaults (CONTEXT §Claude's Discretion). Documented
  here and in ``MODEL_CARD.md`` (Plan 05); adjustable BEFORE any accepted run, immutable
  after (acceptance-integrity discipline — mirrors the Phase-0 X/Y lock).
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# PRD-EXACT runtime constants  [CITED: PRD §Phase-2]
# ─────────────────────────────────────────────────────────────────────────────

#: Agents per inference run = capacity // AGENT_DIVISOR. [CITED: PRD §Phase-2 "N = capacity/100"]
AGENT_DIVISOR: int = 100

#: Exactly this many deterministic rollout steps per run. [CITED: PRD §Phase-2 "200 steps"]
SIM_STEPS: int = 200

#: A "dwell" run requires velocity ≈ 0 for STRICTLY MORE than this many consecutive steps.
#: [CITED: PRD §Phase-2 "velocity ≈ 0 for > 10 consecutive steps" — CROWD-02]
DWELL_MIN_STEPS: int = 10

# Reward coefficients — verbatim PRD ``R = P_destination − P_heat − P_collision``.
# [CITED: PRD §Phase-2 Reward (+10 / −5 / −2)]
#: +reward on goal-polygon entry.
P_DEST: int = 10
#: −reward for stepping onto a UTCI > 26 °C cell.
P_HEAT: int = 5
#: −reward per neighbour within COLLISION_RADIUS_M.
P_COLLISION: int = 2

# ─────────────────────────────────────────────────────────────────────────────
# ASSUMED constants  [ASSUMED]  (Claude's discretion — documented, tunable pre-run)
# ─────────────────────────────────────────────────────────────────────────────

#: Fixed, logged runtime seed. Same seed → byte-identical density field on CPU inference.
#: [ASSUMED] arbitrary fixed value; logged to the provenance ledger + model card.
SEED: int = 1789

#: Max agent speed in env units (metres/step). [ASSUMED] human walking ~1.34 m/s × STEP_DT_S.
V_MAX: float = 1.34

#: "Near-zero" velocity threshold for the dwell detector, as a fraction of V_MAX.
#: V_STILL = V_STILL_FRAC * V_MAX. [ASSUMED] tighter risks empty clusters, looser captures
#: slow-walkers (RESEARCH §DBSCAN).
V_STILL_FRAC: float = 0.10
#: Absolute near-zero-velocity threshold (metres/step) derived from V_STILL_FRAC × V_MAX.
V_STILL: float = V_STILL_FRAC * V_MAX

#: Two agents closer than this (metres) count as a collision (−P_COLLISION each).
#: [CITED: PRD §Phase-2 "collision <0.5 m"]
COLLISION_RADIUS_M: float = 0.5

#: Observation neighbourhood radius (metres) for local_density + mean_neighbor_heat.
#: [CITED: PRD §Phase-2 "agent sees a 5 m radius around itself"]
OBS_RADIUS_M: float = 5.0

#: UTCI threshold (°C): a cell at or above this is "hot" and triggers −P_HEAT.
#: [CITED: PRD §Phase-2 / CONTRACT comfort threshold — 26 °C]
HEAT_THRESHOLD_C: float = 26.0

# DBSCAN params for dwell_zones (CROWD-02). [ASSUMED] documented in MODEL_CARD (Plan 05).
#: DBSCAN eps in LATTICE-CELL units (so it tracks cell_size_m): 1 cell = the shade-bay
#: granularity — agents within one 6 m cell are "the same queue". [ASSUMED]
DBSCAN_EPS_CELLS: float = 1.0
#: A dwell "zone" needs ≥ this many still agents to matter for shade placement. [ASSUMED]
DBSCAN_MIN_SAMPLES: int = 5

# flow_vectors params (CROWD-03). [ASSUMED] documented in MODEL_CARD (Plan 05).
#: A group must be ≥ this fraction of N agents to count as a "major" concentration. [ASSUMED]
FLOW_MIN_GROUP_FRAC: float = 0.05
#: Emit at most this many dominant flow vectors (the "invisible highways"). [ASSUMED]
FLOW_TOP_K: int = 4
#: DBSCAN eps for the spawn-side flow GROUPING, in LATTICE-CELL units (so it tracks cell_size_m,
#: exactly like the dwell-zone eps — a PRINCIPLED, lattice-unit scale, not a data-dependent range
#: heuristic). Entrances are fixed clusters of spawns; agents whose spawns fall within this many
#: master cells are "the same entrance/flow". WR-05: replaces the old 0.25× spawn-spread heuristic
#: (which collapsed to one group on tight spawns and merged distinct entrances on wide spawns). At
#: cell_size_m = 6 m this is a ~18 m grouping radius — wider than the dwell granularity because a
#: flow ORIGIN is an entrance region, not a single shade-bay cell. [ASSUMED]
FLOW_DBSCAN_EPS_CELLS: float = 3.0

# Benchmark (CROWD-05 — Weidmann/NKW fundamental diagram, Plan 05).
#: ±tolerance band on the emergent speed–density curve vs Weidmann/NKW. [ASSUMED] matches
#: inter-dataset FD scatter (~±20–30%); immutable post-run, never tuned to pass (RESEARCH
#: §Benchmark Validation).
BENCH_TOL: float = 0.20

# Env↔metre/second unit scaling (used by the benchmark to map env units → SI). [ASSUMED]
#: Seconds of wall-clock per env step. [ASSUMED A8] recorded in the model card.
STEP_DT_S: float = 1.0
#: Metres per lattice cell. Mirror of the Phase-2a master-lattice cell_size_m (6.0 m);
#: the lattice descriptor read from utci_grid.json is the runtime authority. [ASSUMED A8]
CELL_LEN_M: float = 6.0

# ─────────────────────────────────────────────────────────────────────────────
# Crowd kinematics — Weidmann speed–density closure (the FD physics)  [ASSUMED]
# ─────────────────────────────────────────────────────────────────────────────
# An agent's achievable forward speed is physically limited by its LOCAL crowd density via the
# Weidmann/NKW speed–density law: v(ρ_local) = V0·(1 − exp(−γ·(1/ρ_local − 1/ρ_max))). This is
# the standard pedestrian-dynamics kinematic closure (the fundamental diagram used as a local
# motion law) — NOT a tuned pass-the-test hack: V0/ρ_max/γ are the CITED Weidmann constants, and
# the policy still runs real PPO inference and must learn to drive forward into the crowd. As
# density rises the cap falls, so the emergent v(ρ) reproduces Weidmann (CROWD-05). The local
# density is estimated from the neighbour count within DENSITY_RADIUS_M and mapped to ped/m² by a
# calibrated unbiased linear fit (slope/intercept below) so the LOCAL estimate tracks the true
# global density across the benchmark range. All [ASSUMED]; documented in MODEL_CARD (Plan 05),
# fixed pre-run (acceptance lock). The acceptance band BENCH_TOL stays LOCKED regardless.
#: Free walking speed (m/s) — Weidmann v₀. [CITED: Weidmann 1993]
WEIDMANN_V0_MS: float = 1.34
#: Jam density (ped/m²) at which movement stops — Weidmann ρ_max. [CITED: Weidmann 1993]
WEIDMANN_RHO_MAX: float = 5.4
#: Kladek shape constant (/m²) — Weidmann γ. [CITED: Weidmann 1993]
WEIDMANN_GAMMA: float = 1.913
#: Radius (m) for the local-density neighbour count feeding the speed cap. [ASSUMED]
DENSITY_RADIUS_M: float = 2.0
#: Unbiased count→density linear calibration (ρ_est = slope·count + intercept), fit so the local
#: neighbour-count estimate tracks the true global ped/m² across 0.3–5.0 ped/m² on the FD strip.
#: [ASSUMED] documented in MODEL_CARD; recomputed if DENSITY_RADIUS_M or the strip changes.
DENSITY_CAL_SLOPE: float = 0.15472
DENSITY_CAL_INTERCEPT: float = 0.11562

# ═════════════════════════════════════════════════════════════════════════════
# Phase 2.1 — V2 site-native constants  (ADDITIVE — every V1 constant above is
# RETAINED unchanged for the V1 corridor/benchmark harness; RESEARCH §"What stays
# FROZEN"). Each value carries its provenance tag. The two acceptance constants
# (STAGE_REACH_FRAC, REACH_RADIUS_M) plus the horizon (SIM_STEPS_V2) are LOCKED
# pre-run — the acceptance-integrity discipline that mirrors the Phase-0 X/Y lock
# and BENCH_TOL: declared in the plan BEFORE any training run, immutable after,
# NEVER tuned to pass (RESEARCH §Q2, T-02.1-01).
# ═════════════════════════════════════════════════════════════════════════════

#: Deterministic rollout steps for the V2 site-native runtime rollout (replaces SIM_STEPS=200,
#: which is RETAINED for the V1 corridor harness). [ASSUMED] — derivation (RESEARCH §Q2):
#:
#:   SIM_STEPS_V2 = round100( D_far_walkable / (V0 · f_congested · STEP_DT_S) + DWELL_MARGIN_STEPS )
#:     D_far_walkable     = 766 m farthest-stage geodesic × 1.3 detour ≈ 996 m  [ASSUMED detour factor]
#:     V0                 = 1.34 m/s        [CITED Weidmann free-flow]
#:     f_congested        = 0.6             [ASSUMED effective-speed fraction under festival congestion]
#:     STEP_DT_S          = 1.0 s/step      [ASSUMED A8, unchanged from V1]
#:     DWELL_MARGIN_STEPS = 150             [ASSUMED dwell/settle headroom so reached agents stay parked]
#:   => 996 / (1.34 · 0.6) + 150 ≈ 1389, rounded to 1400 (nearest-100 convention — same rounding
#:      that took the old 1032 → 1000).
#:
#: FORMULA UNCHANGED — only the INPUT was corrected from an ESTIMATE to a MEASUREMENT
#: (owner-approved 2026-06-11). The original derivation used D_far = 641 m, which was the
#: STRAIGHT-LINE Euclidean distance to the farthest stage (Estrella Damm) used as a geodesic
#: ESTIMATE; the real walkable route winds around the 11.5k blocked cells. The MEASURED geodesic
#: is the BFS flow-field distance (``flowfield.bfs_distance``) from gate A (general entrance, the
#: env's own per-goal router — the SAME field the policy follows) to the farthest reachable stage
#: cell: 766 m (768 m reproduced by the committed BFS; the small delta is the blocked-goal snap
#: cell). So the old 830 m D_far_walkable understated the true 996 m, and the old 1000-step horizon
#: cut off the far-stage cohort before they could physically arrive. Real-world cross-check
#: (festival travel guides for a venue this size: ~10–15 min gate → main stages, ~20 min to the
#: far ends): at 1 s/step, 1400 steps ≈ 23 min of walking budget — consistent with the 20-min far-
#: end figure under congestion, and the ~13 min (766 m / 1.0 m·s⁻¹) free-flow lower bound.
#:
#: SIM_STEPS_V2 × V_MAX = 1876 m of free-travel headroom > the 1240 m lattice diagonal
#: (834×918 m site), comfortably covering the 996 m walkable worst case under heavy congestion.
#: STAGE_REACH_FRAC / REACH_RADIUS_M (the ACCEPTANCE bar) are UNTOUCHED — this corrects only the
#: physical travel-time HORIZON to its own committed formula's measured output, not the gate.
SIM_STEPS_V2: int = 1400

#: Reach radius (metres): an agent "reached" its stage when within this distance.
#: [ASSUMED, LOCKED] — matches the layout's indicative ±30 m positional accuracy (a tighter
#: radius would test geolocation noise, not navigation) and the demo's GOAL_REACH_RADIUS_M.
#: Immutable post-lock; never tuned to pass (acceptance integrity, X/Y discipline, T-02.1-01).
REACH_RADIUS_M: float = 30.0

#: Stage-reach acceptance threshold: ≥ this fraction of agents come within REACH_RADIUS_M of
#: their assigned stage at ANY step ≥ their (staggered) arrival step — a per-agent latch.
#: [ASSUMED, LOCKED pre-run — acceptance integrity, X/Y discipline, T-02.1-01].
#: IMMUTABLE POST-LOCK; NEVER tuned to pass. Massively beats the 0.8% V1 OOD baseline (recorded
#: as the "before" in MODEL_CARD V2). The Plan-05 stage-reach test reads THIS constant (never an
#: inline literal), so any loosening is a visible diff caught by the `! grep` anti-tuning guard.
STAGE_REACH_FRAC: float = 0.70

#: Reuse of REACH_RADIUS_M as the env's reach radius on the ±30 m site (kept as a distinct named
#: constant so env code reads an env-scoped name). [ASSUMED, LOCKED] — equals REACH_RADIUS_M.
GOAL_REACH_RADIUS_M: float = REACH_RADIUS_M

#: Staggered-arrival window (steps): agents activate uniformly at random over the first ~30% of
#: the horizon (replaces the V1 all-at-t=0 spawn). [ASSUMED] — seeded activate_step ∈
#: [0, ARRIVAL_WINDOW_STEPS); before activation an agent sits at its spawn gate (velocity 0,
#: excluded from density). Makes flow_vectors (CROWD-03) read as real entrance highways.
ARRIVAL_WINDOW_STEPS: int = 300

#: Spawn split: ~this fraction at general ENTRANCE A, the remainder (~15%) at VIP ENTRANCE B.
#: [ASSUMED] — promoted from the demo (viz/run_demo_sim.py).
SPAWN_FRAC_GATE_A: float = 0.85

#: Gate spawn jitter (metres) around the entrance point. [ASSUMED] — promoted from the demo.
SPAWN_JITTER_M: float = 8.0

#: Real-attendance anchor (public figure) → N = PRIMAVERA_DAILY_CAPACITY // AGENT_DIVISOR = 650.
#: [ASSUMED] — a demo festival daily capacity, documented in MODEL_CARD V2.
PRIMAVERA_DAILY_CAPACITY: int = 65_000

#: Capacity-class FLOOR weights for weighted goal assignment (demand.py in Plan 02 multiplies by
#: the active-headliner popularity weight). [ASSUMED] — promoted from the demo's
#: GOAL_WEIGHT_BY_CLASS; default weight for unlisted classes is GOAL_WEIGHT_DEFAULT.
GOAL_WEIGHT_BY_CLASS: dict[str, int] = {"main": 3, "secondary": 2, "electronic": 2}
#: Default capacity-class weight for any stage class not in GOAL_WEIGHT_BY_CLASS. [ASSUMED]
GOAL_WEIGHT_DEFAULT: int = 1

#: Emit-side trajectory downsample budget (MB): the Phase-2.2 console animation does not need
#: full-res 1000-frame trajectories; downsample (e.g. every-2nd-step) when the JSON emit would
#: exceed this. [ASSUMED] — promoted from the demo's TRAJ_SIZE_BUDGET_MB; used by the Plan-06
#: runtime emit path (NOT a grid.py concern).
TRAJ_DOWNSAMPLE_BUDGET_MB: float = 15.0

#: Grid-handoff still-point budget (count): when rollout→grid still-points would exceed this,
#: step-downsample the trajectory BEFORE build_crowd_grid (an orchestrator/handoff concern, NOT
#: a grid.py edit; grid.py still receives a steps×agents×4 array). [ASSUMED] — promoted from the
#: demo's GRID_STILLPOINT_BUDGET.
GRID_STILLPOINT_BUDGET: int = 200_000

# ═════════════════════════════════════════════════════════════════════════════
# Phase 15 — JuPedSim crowd-swap constants (ADDITIVE — every constant above is
# RETAINED; the labelled-legacy PPO harness still reads SIM_STEPS_V2/SEED/etc.).
# Named here so the DoD + determinism tests read constants, NEVER inline literals
# (anti-tuning discipline). NOTE D-03: the NEW DoD reach gate is ADVISORY (relaxable
# only for a genuine geometric unreachability), UNLIKE the immutable X/Y and the
# retired STAGE_REACH_FRAC=0.70.
# ═════════════════════════════════════════════════════════════════════════════

#: JuPedSim agent body radius (metres). [ASSUMED] — CFSM default pedestrian radius
#: (jupedsim CollisionFreeSpeedModelAgentParameters); 0.12 m ≈ Weidmann shoulder half-width.
AGENT_RADIUS_M: float = 0.12

#: JuPedSim integration step (seconds/iterate). [ASSUMED A8, reuses the V1 STEP_DT_S = 1.0 s]
#: — the finite-diff adapter (src/crowdsim/adapter.py) divides position deltas by this.
STEP_DT_JPS_S: float = 1.0

#: Deterministic JuPedSim sim horizon (iterate() calls). [ASSUMED] — SIM_STEPS_JPS derivation
#: mirrors SIM_STEPS_V2 (lines 146-175): ceil(D_far_walkable / (V0 · f_congested · STEP_DT_JPS_S)) +
#: DWELL_MARGIN_STEPS, with the SAME measured 766 m far-stage geodesic × 1.3 detour ≈ 996 m,
#: V0=1.34 m/s [CITED Weidmann free-flow], f_congested=0.6 [ASSUMED], DWELL_MARGIN_STEPS=150
#: [ASSUMED settle headroom]: 996 / (1.34·0.6) + 150 ≈ 1389 → 1400 (nearest-100). A too-short
#: horizon cuts off far-stage arrivals (the exact OLD failure) — the BLOCKING DoD gate
#: (test_crowdsim_stage_reach) validates the horizon is long enough on the real site.
SIM_STEPS_JPS: int = 1400

# ═════════════════════════════════════════════════════════════════════════════
# Phase 16 — Continuous migrating daytime constants (ADDITIVE — every constant
# above is RETAINED; SIM_STEPS_JPS is REUSED below under a per-hour name, NEVER
# mutated, since the FROZEN night path reads it). Named ONCE here so no later
# task inlines 0.1 / 1400 / the hour list — the anti-tuning discipline (T-16-01):
# the demand + determinism + emit tests read these constants, never a literal.
# ═════════════════════════════════════════════════════════════════════════════

#: Daytime festival hours (local HH:MM), 09:00→20:00 inclusive = 12 hour marks → 11 intervals.
#: [ASSUMED] — the CD-A daytime window (decisions.md CON-004); mirrors occupancy_curve_2026.json
#: "hours" (same 12-mark list, verified INT-001).
DAYTIME_HOURS: list[str] = ["09:00","10:00","11:00","12:00","13:00","14:00","15:00","16:00","17:00","18:00","19:00","20:00"]

#: active() baseline pull for an INACTIVE stage in the daytime demand formula (DAYCROWD-01).
#: [ASSUMED, owner-LOCKED] — a stage outside its active_hours still exerts a LOW (people-mill)
#: pull, not zero: 0 over-empties the site (funnels onto 1-2 live stages → can exceed Fruin 6/m²),
#: 1.0 ("always-on") kills the migration. 0.1 << 1.0 preserves visible migration. NEVER tuned to
#: pass (CON-003 + occupancy_curve_2026.json _meta.active_means both require low-but-nonzero).
ACTIVE_BASELINE: float = 0.1

#: Per-HOUR recorded-frame budget for the continuous daytime run (DAYCROWD-02/03). [ASSUMED] —
#: REUSES the SIM_STEPS_JPS value (1400, the validated single-slice travel+dwell horizon: a
#: migration re-path is bounded by the SAME worst-case site crossing) under a NEW name so the
#: per-hour budget reads as a constant, never an inline 1400. The full daytime horizon is
#: FRAMES_PER_HOUR_JPS × (len(DAYTIME_HOURS) - 1) = 1400 × 11 = 15,400 recorded frames.
#: SIM_STEPS_JPS is NOT mutated (the FROZEN night path reads it).
FRAMES_PER_HOUR_JPS: int = SIM_STEPS_JPS
