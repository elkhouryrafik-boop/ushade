<!--
SUPERSEDED 2026-06-21 (Phase 15): JuPedSim (src/crowdsim/) is the live crowd engine.
This PPO stack is a DORMANT, reversible reference (D-04) — importable but NOT called on the
live path. Do not delete; do not wire. Kept because the JuPedSim festival→primitive mapping is
only MEDIUM-confidence until proven on the real site across runs.

`policy.zip` is likewise DORMANT: the live path loads no pickled PPO weights (run_crowd_stage
drives the JuPedSim CFSM engine). This card describes the retired PPO Weidmann-FD provenance gate,
retained as the labelled-legacy fallback.

LIVE JuPedSim provenance (2026-06-22, the Lyon density gate — supersedes the "always ASSUMED on the
JuPedSim path" note this card used to carry):
  - crowd_density MAGNITUDE -> DERIVED when src/crowd/benchmark_result_crowdsim.json is green for the
    live engine identity. Validated against the REAL measured MADRAS Lyon Fete-des-Lumieres festival
    density (Zenodo 10.5281/zenodo.13830435, CC-BY 4.0): on the real Lyon walkable geometry with the
    observed population, the simulated density distribution matches the measured one within +/-50% on
    mean/p90/p99 and respects the Fruin <=6 ped/m2 jam ceiling. Raw single-cell max is a reported
    DIAGNOSTIC, not a gate metric. Gate: crowd.crowd._crowdsim_benchmark_is_green; producer:
    scripts/crowd_validation/; data sheets: phase-2-crowd/.
  - crowd_spatial_allocation -> ALWAYS ASSUMED. Agent goals follow the REAL Primavera
    set_times_2026.json timetable and the organiser CAPACITY input (grounded drivers), but the
    per-stage popularity ordinal (1-5) and 85/15 gate spawn split are assumptions, and NO open data
    measures crowd density inside Parc del Forum -> WHICH cells are busiest stays ASSUMED.
  - Net: placement still inherits ASSUMED by weakest-input-wins. Honest headline: density magnitudes
    are real (validated vs a real festival); where the crowd gathers at this site is a reasoned estimate.
-->

# Model Card — HeatGuard Crowd Policy (Phase 2b) — SUPERSEDED (dormant PPO reference)

**Artifact:** `src/crowd/policy.zip` (committed, 141,787 B — direct git, no LFS) — DORMANT, not loaded on the live path
**Seed:** 1789 (`src/crowd/policy_seed.txt`)
**Requirement:** CROWD-01 / CROWD-05
**Status:** Benchmark-validated — `crowd_density` promoted ASSUMED → DERIVED (gated on the Weidmann FD benchmark; see [Provenance gate](#provenance-gate-assumed--derived)).
**Date:** 2026-06-10

> This card is the **provenance ledger source** for the `crowd_density` DERIVED promotion.
> The `crowd_density` number is trusted (DERIVED) **only because** the durable Weidmann/NKW
> fundamental-diagram benchmark (`tests/test_crowd_benchmark.py`) passes against the committed
> weights. If that benchmark is ever red, the promotion is withdrawn (the stage falls back to
> ASSUMED) — see the [honesty statement](#limitations--honesty-statement) on exactly what the
> benchmark does and does not prove.

---

## Model details

| Property | Value |
|----------|-------|
| Algorithm | PPO (Proximal Policy Optimization) |
| Library | Stable-Baselines3 2.8.x (`MlpPolicy`), Gymnasium 1.x, PyTorch 2.12 CPU |
| Architecture | 2-layer MLP, `net_arch=[64, 64]` (shared pi/vf), tanh activations (SB3 default) |
| Observation | 6-float Box **per agent**: `[own_vx, own_vy, goal_dx, goal_dy, local_density, near_dx]` |
| Action | 2-float Box `[vx, vy]`, clipped to ±`V_MAX` (1.34 m/step) |
| Training device | CPU (`device="cpu"`) — no CUDA, no GPU non-determinism |
| Training budget | 150,000 timesteps (`DEFAULT_TIMESTEPS`) |
| Seed | 1789 (`SEED` in `crowd/constants.py`; logged to `policy_seed.txt`) |
| Inference | Decentralised shared policy: one obs per agent → batched `predict(deterministic=True)` → one action per agent. Exactly `SIM_STEPS = 200` deterministic steps (CROWD-01). |

**Decentralised shared-policy design (Option A, 02b-02).** SB3 trains ONE *ego* agent under
the single-agent gym contract; at FD-measurement and runtime the *same* learned policy is
applied **per-agent** to all N agents (`observe_all` → batched `predict` → `step_all`). This is
the standard crowd-RL design (CADRL / social-force-style decentralised shared policy) and the
only architecture in which a pedestrian fundamental diagram can physically emerge — each agent
must individually slow when *its own* neighbourhood is congested. The prior aggregate-observation
env (one mean obs → one broadcast action) could not express a per-agent congestion response and
was replaced (see `deferred-items.md` / 02b-02 SUMMARY).

---

## Training data — the synthetic `FestivalEnv`

There is **no real-world crowd dataset**. The policy is trained entirely in a synthetic,
seeded Gymnasium environment (`src/crowd/env.py`), which is the smallest honest world that
(a) hosts the runtime inference rollout and (b) lets the Weidmann benchmark emit a
speed–density curve.

- **World:** continuous 2D box in metres, derived from the Phase-2a master-lattice extent
  (read, never re-derived — CONTRACT-03).
- **Training scenario:** a bounded **periodic corridor strip** (16 m × 4 m, `_STRIP_*` in
  `train.py`). The ego flows +x among a reactive moving crowd; each episode draws a fresh
  agent **count** from `_DENSITY_AGENT_RANGE = (16, 260)`, spanning free-flow (ρ≈0.5) to jam
  (ρ≈4), so the single shared policy learns the whole speed–**density** function rather than one
  operating point.
- **Reward (verbatim PRD, `R = +P_DEST − P_HEAT − P_COLLISION` + potential-based goal shaping):**
  `P_DEST=+10`, `P_HEAT=−5`, `P_COLLISION=−2` (PRD-exact, `crowd/constants.py`). In the periodic
  FD-flow scenario the reward is realised +x progress only (volume-exclusion physics, not a
  reward penalty, is what caps speed in congestion — so the speed–density law stays geometric,
  not a tuned penalty). Heat is a runtime concern, excluded from the FD.
- **Goal-progress shaping** (`GOAL_PROGRESS_WEIGHT=1.0`, ASSUMED): potential-based F = Φ(s) − Φ(s′)
  shaping (Ng et al. 1999) — policy-invariant, changes learning dynamics not the optimal policy
  or the FD acceptance.

---

## Train-vs-source decision

**Decision: train locally (do not import a pretrained policy).**

Rationale (02b-RESEARCH §Decision): published crowd-RL repositories ship **robot-navigation**
weights (CADRL, social-GAN, RVO variants) trained on indoor/sidewalk geometries with their own
observation contracts and action spaces — none ship a *festival-scale, lattice-aligned,
heat-coupled* policy with verifiable provenance. Adapting one would require re-training anyway and
would inherit an unverifiable upstream provenance chain. A small 64×64 MLP over a 6-float
observation converges within ~1e5–1e6 CPU steps; training locally at a fixed, logged seed gives a
fully auditable artifact whose only acceptance burden is **re-passing the published FD benchmark**.

---

## Benchmark result — Weidmann/NKW fundamental diagram (CROWD-05)

The emergent speed–density curve of the committed policy is validated against the cited
Weidmann/NKW pedestrian fundamental diagram (Kladek form):

> v(ρ) = V₀ · (1 − exp(−γ · (1/ρ − 1/ρ_max)))
> **[CITED: Weidmann 1993, *Transporttechnik der Fussgänger*, ETH Zürich IVT Bericht 90; Kladek/NKW form]**
> V₀ = 1.34 m/s, ρ_max = 5.4 ped/m², γ = 1.913 /m²

Measured emergent v(ρ) (committed `policy.zip`, seed 1789), tolerance band `BENCH_TOL = ±20%`
(**LOCKED**), sampled at ≥ 3 densities:

| ρ (ped/m²) | emergent v (m/s) | Weidmann v (m/s) | rel. error | result |
|------------|------------------|------------------|-----------|--------|
| 0.5        | 1.278            | 1.298            | 1.5%      | PASS   |
| 2.0        | 0.691            | 0.606            | 14.0%     | PASS   |
| 4.0        | 0.135            | 0.156            | 13.7%     | PASS   |

Curve is **monotonically decreasing**; free-flow (ρ=0.5) speed is within ±20% of V₀. All three
densities inside the LOCKED ±20%. The durable gate is `tests/test_crowd_benchmark.py`
(`@pytest.mark.crowd`), which re-runs this measurement against the committed weights — the test
the DERIVED promotion is gated on.

**Acceptance discipline (LOCKED, mirrors the Phase-0 X/Y threshold lock):** `BENCH_TOL` is
immutable and is **never** widened to make a weak policy pass. A failing gate is fixed by
**retraining** (`python -m crowd.train` — widen the observation / shape the reward / train more
steps), not by editing the test.

---

## Unit scaling (env ↔ SI) — ASSUMED

| Constant | Value | Meaning | Tier |
|----------|-------|---------|------|
| `STEP_DT_S` | 1.0 s | seconds of wall-clock per env step | ASSUMED (A8) |
| `CELL_LEN_M` | 6.0 m | metres per lattice cell (mirror of the Phase-2a master `cell_size_m`) | ASSUMED (A8) |
| `V_MAX` | 1.34 m/step | per-step speed cap; equals V₀ under 1 unit = 1 m, dt = 1 s | ASSUMED |

The env uses 1 unit = 1 m and dt = 1 s, so a per-step displacement maps directly to m/s. The
runtime lattice `cell_size_m` read from `utci_grid.json` is the authority; `CELL_LEN_M` is its
documented mirror.

---

## ASSUMED parameters (Claude's discretion — `crowd/constants.py`)

All fixed **pre-run** and immutable after (acceptance-integrity discipline). Documented here as
the single ledger; adjustable only before any accepted run.

| Parameter | Value | Role |
|-----------|-------|------|
| `SEED` | 1789 | fixed runtime + training seed |
| `V_STILL_FRAC` | 0.10 | "near-zero" velocity threshold (× V_MAX) for the dwell detector |
| `DBSCAN_EPS_CELLS` | 1.0 | DBSCAN eps for `dwell_zones`, in lattice-cell units (CROWD-02) |
| `DBSCAN_MIN_SAMPLES` | 5 | min still agents for a dwell zone (CROWD-02) |
| `FLOW_MIN_GROUP_FRAC` | 0.05 | min fraction of N for a "major" flow group (CROWD-03) |
| `FLOW_TOP_K` | 4 | max dominant flow vectors emitted (CROWD-03) |
| `FLOW_DBSCAN_EPS_CELLS` | 3.0 | DBSCAN eps for spawn-side flow grouping, in lattice-cell units (~18 m at cell_size_m=6 m); principled lattice-unit scale, not a data-range heuristic (CROWD-03, WR-05) |
| `OBS_RADIUS_M` | 5.0 | observation neighbourhood radius (PRD-cited 5 m) |
| `DENSITY_RADIUS_M` | 2.0 | radius for the local-density neighbour count feeding the speed cap |
| `DENSITY_CAL_SLOPE` | 0.15472 | unbiased count→ped/m² calibration slope (fit for the 16×4 strip + R=2.0) |
| `DENSITY_CAL_INTERCEPT` | 0.11562 | calibration intercept |
| `BENCH_TOL` | 0.20 | **LOCKED** FD acceptance band (never tuned to pass) |

The Weidmann constants (`WEIDMANN_V0_MS`, `WEIDMANN_RHO_MAX`, `WEIDMANN_GAMMA`) are **CITED**
(Weidmann 1993), not assumed.

---

## Provenance gate (ASSUMED → DERIVED)

`crowd_density` is **ASSUMED by default** at the writer API (`ProvenanceLedger.crowd_density`
hard-codes the ASSUMED tier — CLAUDE.md non-negotiable). It is promoted to **DERIVED** with
`source="MODEL_CARD.md"` **only** when a benchmark-produced, policy-bound artifact proves the
gate passed against the exact weights in use — **there is no caller-supplied flag** (a boolean a
caller can set freely is not validation; CR-01). The mechanism:

1. On a **GREEN** FD gate, `tests/test_crowd_benchmark.py` writes
   `src/crowd/benchmark_result.json` recording the `policy_sha256` of the EXACT `policy.zip`
   the measurements ran against, the LOCKED `bench_tol`, the per-density measured/reference
   speeds, and `passed: true`. This committed artifact is the real benchmark result.
2. `run_crowd_stage` re-hashes the `policy.zip` it is about to roll out and promotes
   `crowd_density` to **DERIVED** **only if** `benchmark_result.json` exists, its
   `policy_sha256` **matches** that hash, and `passed` is true.

A missing artifact, a hash mismatch (e.g. a retrained-but-not-rebenchmarked policy), a red
gate, or an injected non-hashable fake policy all keep the tier **ASSUMED**. The tier is
re-evaluated on **every** call — including cache hits — so a since-gone-red benchmark cannot
leave a stale DERIVED label stuck on disk. See
`tests/test_crowd.py::test_crowd_density_derived_when_benchmark_artifact_matches_policy` and the
`..._hash_mismatch` / `..._red` / `..._no_benchmark_artifact` spoof-guard tests.

---

## Limitations — honesty statement

**What the FD benchmark proves (and does not).** The environment applies the Weidmann/NKW
speed–density law **as a local kinematic cap** on each agent's forward speed: an agent's
achievable forward speed is `min(policy_desired_speed, v_Weidmann(ρ_local))`, where ρ_local is the
agent's calibrated local density (`crowd/env.py::_density_speed_cap`). Consequently:

- The benchmark validates the **calibration of the simulation** — that the emergent local
  densities and the cited speed law are correctly coupled, and that the PPO policy produces
  realistic goal-seeking motion *under that law* (it learns to drive forward into the crowd as
  hard as the physics permits, rather than freezing or stalling).
- The benchmark **does NOT claim** that the PPO policy *independently discovered* the
  speed–density relation. The speed–density law is the **cited physics being enforced** (Weidmann
  1993 / Kladek form), not an emergent property the network learned unaided.

This distinction is what makes the provenance defensible rather than overclaimed: HeatGuard
asserts a correctly-calibrated, physically-grounded crowd simulation whose motion is produced by a
real PPO policy under a cited pedestrian-dynamics closure — not a network that re-derived
pedestrian physics from scratch.

**Other limitations:**

- **Synthetic only.** No real festival crowd data; the env is a deliberately small honest world.
  Real-data fine-tuning is deferred (V2-CROWD-01).
- **Single fixed scenario.** Two entrances + two stage attractors derived from the site bbox
  (ASSUMED A3); no scenario/curriculum variety.
- **FD measured on a corridor strip, not the full site.** Realising ρ=4 on the 120 m × 120 m site
  would need ~57,600 agents (O(n²) density/collision math → infeasible); the FD is read on a small
  periodic measurement strip under sustained flow (standard pedestrian-dynamics practice). The
  count→density calibration is fit for that strip geometry + `DENSITY_RADIUS_M`; it must be
  recomputed if either changes.
- **Training reproducibility caveat.** PPO training is subject to floating-point
  non-associativity during gradient accumulation, so a *retrained* policy may NOT be byte-identical
  to the committed `policy.zip`. That is acceptable: the runtime determinism guarantee is about
  **inference** on the committed weights (same seed → byte-identical rollout *and* end-to-end
  `crowd_grid.json`, asserted by `test_same_seed_same_trajectory` / `test_same_seed_same_grid`).
  The only requirement on a retrained policy is that it **re-passes the FD benchmark** at the
  LOCKED tolerance.
- **CPU-only determinism.** The same-seed guarantee holds on one CPU machine; a different
  BLAS/CPU or GPU may diverge at the bit level.

---

## References

- Weidmann, U. (1993). *Transporttechnik der Fussgänger.* ETH Zürich, IVT Bericht 90. (Kladek/NKW
  speed–density fundamental diagram: V₀=1.34 m/s, ρ_max=5.4 ped/m², γ=1.913 /m².)
- Ng, A., Harada, D., Russell, S. (1999). *Policy invariance under reward transformations.* ICML.
  (Potential-based shaping.)
- Schulman et al. (2017). *Proximal Policy Optimization Algorithms.* (PPO.)
- Chen et al. (2017). *Decentralized Non-communicating Multiagent Collision Avoidance (CADRL).*
  (Decentralised shared-policy crowd RL design.)
- Helbing, D., Molnár, P. (1995). *Social force model for pedestrian dynamics.* Physical Review E.
  (Lane-formation self-organisation in counter- and co-flowing pedestrian streams — cited for the
  deferred alignment-aware lateral-push fix, V2 §Limitations.)

---

# V2 — Site-Native Model (Phase 2.1)

**Artifact:** `src/crowd/policy.zip` (V2 7-input PPO weights), sha256 `93ecbf67…`, seed **1789**
(`src/crowd/policy_seed.txt`)
**Requirement:** CROWD-01..05 re-validated on V2 weights
**Status:** **PARTIAL — FD/local-physics gate GREEN and accepted; stage-reach/ROUTING gate RED at
54.8% < the LOCKED 70%, owner-DEFERRED 2026-06-11.** `crowd_density` is promoted ASSUMED → DERIVED
**for the local speed–density physics only** (gated on the GREEN Weidmann FD benchmark, re-bound to
the V2 SHA); the **global-routing / spatial-allocation half remains ASSUMED-grade** until the deferred
stage-reach gate is green.
**Date:** 2026-06-11

> **This card is the auditable provenance ledger for V2.** The V2 model retrains the policy on a
> 7-float scale-free observation and deploys it on the **real georeferenced Parc del Fòrum site**,
> closing the V1 out-of-distribution transfer failure. Two LOCKED acceptance gates were authored
> BEFORE the training run (X/Y acceptance-integrity discipline). One passed; one did not and is
> formally **deferred, not accepted** — see [Both gates](#v2-both-acceptance-gates-honest-status) and
> [`DEFERRED-GATE-FIX.md`](../../.planning/phases/02.1-crowd-v2-site-native/DEFERRED-GATE-FIX.md).
> **No threshold was loosened to manufacture a pass.**

---

## V2 — Before / after (the closed transfer-failure story)

| | Stage-reach on the real ~800 m site | Note |
|---|---|---|
| **V1 (Phase 2b)** | **0.8%** (recorded baseline) | raw unbounded `goal_dx/dy` obs → out-of-distribution on 600 m+ offsets the policy never trained on; the crowd did **not** navigate the real site |
| **V2 (Phase 2.1)** | **54.8%** (356/650 agents @ SIM_STEPS_V2=1400) | scale-free flow-field obs (V1 OOD cannot recur) — a **68× lift**, but **below** the LOCKED 70% bar (RED, deferred) |

The before/after is real and large; it is **also** an honest, unfinished story — 54.8% is a genuine
68× improvement AND a genuine acceptance miss. Both are stated, neither is laundered.

---

## V2 — Architecture delta (the one learned-side change)

| Property | V1 (Phase 2b) | V2 (Phase 2.1) |
|----------|---------------|----------------|
| Observation | 6-float `[own_vx, own_vy, goal_dx, goal_dy, local_density, near_dx]` (raw unbounded offsets) | **7-float scale-free** `[own_vx, own_vy, flow_dx, flow_dy, log_goal_dist, local_density, near_dx]` |
| Guidance | raw vector to goal | **deterministic obstacle-aware flow field** (per-goal BFS navigation function; `src/crowd/flowfield.py`) read at the agent's cell each step; `flow_dx,flow_dy ∈ [-1,1]`, `log_goal_dist` bounded |
| Deploy geometry | synthetic bbox (2 gates + 2 stage attractors) | **real site** — 19 user-placed stages, ENTRANCE A/B, 13 impassable blockers, real 139×153 @ 6 m UTCI lattice |
| Network / action | MLP `[64,64]`, action `±V_MAX` | **unchanged** `[64,64]`, action `±V_MAX` |

The flow field hands the policy a **bounded, in-distribution local routing cue at every position**, so
the V1-learned *local pedestrian physics* transfers to the big site by construction ("train local,
deploy global"). The raw unbounded `goal_dx/dy` — the V1 OOD root cause — is **removed**; every V2
obs field is bounded ∀ position, so the V1 failure mode cannot recur.

---

## V2 — Environment geometry provenance

- **Source:** the **user-corrected 2026 a demo festival / Parc del Fòrum layout**, committed as
  `viz/data/{festival_map,boundary,walkable_nogo}_2026.geojson` (git `259d3fb`), rasterised onto the
  READ `projects/primavera-demo/utci_grid.json` lattice (139×153 @ 6 m) by `src/crowd/site.py`.
- **Spatial accuracy:** **indicative, ±30 m** — the stage/blocker placements are the user's best
  manual georeferencing of the published site map, NOT a surveyed cadastral dataset. This indicative
  tolerance is *why* `REACH_RADIUS_M = 30 m` is the acceptance radius (a reach to within one
  indicative-error of the assigned stage centre).
- **Elements:** **19 user-placed stages** (goals, demand-weighted); **ENTRANCE A** (general) / **B**
  (VIP) spawns with an ASSUMED **~85/15 split** (`SPAWN_FRAC_GATE_A = 0.85`, A-grade assumption);
  **13 impassable blocker polygons** + the outside-boundary band rasterised to a blocked-cell set
  (`build_blocked_cells`, "Obstacles flagged as impassable" honoured literally). Agents are reverted
  out of any blocked cell every step (impassability invariant). A stage whose indicative ±30 m centre
  lands inside a blocker has its **flow-field goal snapped to the nearest walkable cell** (BFS snap,
  consistent with `site.py`); reach is still measured to the true stage centre within 30 m.

---

## V2 — Flow-field guidance architecture (7-float obs)

`src/crowd/flowfield.py` is a **pure-numpy, torch-free** deterministic router (no learned weights):

- `bfs_distance(blocked, cols, rows, goal_cell)` — 4-connected BFS wavefront → per-cell geodesic
  distance (∞ for blocked/unreachable); neighbour-visit order PINNED → byte-deterministic.
- `flow_dir(dist)` — per-cell unit vector toward the lowest-distance walkable 4-neighbour (never
  points into a blocked cell; `(0,0)` at goal/blocked/unreachable).
- `build_flow_fields(...)` — a per-goal `{idx: (dist, flow_dir)}` cache (~4 MB, sub-second for the
  real 19-goal × 21,267-cell lattice), built ONCE at reset.

Each step the env reads the agent's cell `flow_dir` (→ `flow_dx, flow_dy`) and `log1p(geodesic
distance)` (→ `log_goal_dist`) from the cache for the agent's ASSIGNED goal. This is the
navigation-function prior the policy follows; the periodic-corridor FD-measurement mode emits a
degenerate constant `flow=(1,0)` so the **Weidmann FD harness is uncontaminated** (it sees the
identical V1 forward cue — RESEARCH §Q4).

---

## V2 — Both acceptance gates (honest status)

Both gates were authored as LOCKED tests **before** the training run (acceptance integrity;
thresholds read from `crowd.constants`, never inline literals).

### Gate 1 — Weidmann FD ±20% (LOCAL physics) — ✅ GREEN (accepted)

Re-run on the V2 7-input policy via the **UNCHANGED** periodic-corridor harness
(`tests/test_crowd_benchmark.py`, `@pytest.mark.crowd`); on green it re-binds
`src/crowd/benchmark_result.json` to the V2 `policy_sha256` (`93ecbf67…`, `passed: true`).

| ρ (ped/m²) | emergent v (m/s) | Weidmann v (m/s) | rel. error | result |
|------------|------------------|------------------|-----------|--------|
| 0.5        | 1.278            | 1.298            | **1.5%**  | PASS   |
| 2.0        | 0.691            | 0.606            | **14.0%** | PASS   |
| 4.0        | 0.135            | 0.156            | **13.7%** | PASS   |

Monotone-decreasing; free-flow within ±20% of V₀; all three inside the LOCKED `BENCH_TOL = ±20%`.
This is the gate the DERIVED promotion of `crowd_density` (local speed–density calibration) rests on.

### Gate 2 — Stage-reach ≥70% within 30 m, latched (GLOBAL routing) — ❌ RED — DEFERRED 2026-06-11

`tests/test_crowd_stage_reach.py` rolls the committed V2 policy through the full real-site env
(N = `PRIMAVERA_DAILY_CAPACITY // AGENT_DIVISOR` = 650) for `SIM_STEPS_V2 = 1400` steps and asserts
the **latched** reach fraction ≥ `STAGE_REACH_FRAC = 0.70` within `REACH_RADIUS_M = 30 m`.

| Gate | Locked threshold | Measured (committed policy @ SIM_STEPS_V2=1400) | Status |
|------|------------------|-------------------------------------------------|--------|
| **Stage-reach** | ≥ 70% within 30 m, latched | **54.8%** (356/650) | **RED — DEFERRED** |

**This is a deferral, not an acceptance.** The owner decided 2026-06-11 ("run with this model we have
now, with the gaps that it has" — presentation deadline) to proceed with the current policy; the
approved fix scope is recorded in
[`DEFERRED-GATE-FIX.md`](../../.planning/phases/02.1-crowd-v2-site-native/DEFERRED-GATE-FIX.md). The
gate test is **xfail'd with a reason pointing there** — the RED is documented, not deleted; un-xfail
when the fix is executed. The threshold itself is **UNTOUCHED**.

**Per-stage breakdown** (the deficit is concentrated, not diffuse):

- **14 of 19 stages reach 95–100%.** The entire deficit is **3 far stages at 0%** — Estrella Damm
  (n=187), Revolut (n=51), Plenitude (n=34) — plus **Auditori** (n=19, 0%, a measurement/snap
  structural issue: its true centre is inside a building, no walkable cell within 30 m). These four
  cohorts ≈ 291 of the ~294 unreached agents.
- **Two measured root causes** (not guessed): (1) a **lane/alignment bug in the env social force** —
  co-moving far-cohort agents command 78–90% V_MAX but net goal-progress ≈ 0.29 m/step because
  `_lateral_push` disperses them sideways within co-moving streams (real crowds form lanes; our push
  is alignment-blind); (2) the **Auditori snap** measures to an unreachable building-centre cell → 0%
  by construction. The Sat/22:00 demand slice also stacks ~30% of all agents (≈187) onto the single
  **farthest** stage (Estrella Damm, 768 m geodesic), concentrating the gate's difficulty.
- **What was tried and did NOT close it** (the audit trail): the full sanctioned escalation ladder
  (corridor-only → flow-follow → +elbow obstacle → **streaming flow-follow, the BEST at 54.5%** →
  heavier streaming / 8-direction / seeds 7/42/2024, all worse); the owner-approved horizon
  correction SIM_STEPS_V2 1000→1400 (bought only **+0.3 pp** — the far cohort plateaus by step ~1200);
  and **4 assertiveness-reward retrains** (weights 0.5/1.0/2.0, seeds 1789/7) that **ALL degraded**
  reach (49.4 / 7.8 / 34.6 / 14.3%) and were **reverted** — the committed policy is the unchanged BEST.
  STOPPED per owner action #4 (do not iterate forever, do not loosen anything).

---

## V2 — Honest composition framing (RESEARCH §Q3 — no overclaim)

The V2 crowd field is the **composition of two independently-validated halves**, and the card claims
**exactly** what each gate proves:

| Half | What it is | Validating gate | Status |
|------|-----------|-----------------|--------|
| **Local pedestrian physics** | the PPO policy's speed–density response under the cited Weidmann closure | Weidmann FD ±20% | ✅ **validated** (DERIVED-grade) |
| **Global routing / spatial allocation** | the deterministic BFS flow field the policy follows to the right stages | stage-reach ≥70% | ❌ **NOT validated** (RED/deferred — **ASSUMED-grade**) |

Neither half overclaims. `crowd_density` reverts to ASSUMED on any policy swap and **re-binds DERIVED
only on the green V2 benchmark SHA — and only for the local speed–density physics**. For **spatial
allocation / routing**, `crowd_density` stays **ASSUMED-grade** while the stage-reach gate is RED:
downstream consumers (Phase 3 coupling) may read `crowd_grid.json` (contract-valid, deterministic) but
**must treat far-stage cells as UNDER-represented** (the far cohort is strung out along the route, not
yet at the stage) and must NOT present the routing as gate-passed. The FD benchmark proves the
*calibration of the local simulation*, NOT that the network re-derived pedestrian physics nor that the
crowd correctly reaches its destinations.

---

## V2 — Training curriculum + budget

- **Recipe (the winning artifact):** seed **1789**, a warm-transferred curriculum —
  **streaming flow-follow 120k** (40 co-moving agents sharing goals → the policy learns fast
  crowd-streaming, the real-site condition) → **elbow obstacle 100k** (obstacle-aware turning) →
  **corridor FD 50k** (the Weidmann speed–density physics on the periodic strip). Total **270k**
  timesteps.
- **Wall-clock:** **~10 min CPU** for the winning run (the strips are small/fast). The full escalation
  search across all variants/seeds was ~3.5 h; the assertiveness gate-fix iteration added ~4 retrains.
- **Training-mode env flags** (runtime byte-unchanged): `stagger_arrivals=False` (ego active from t=0,
  else it parks at its gate and learns nothing); seedless reset advances the RNG for per-episode goal
  variety (an explicit seed still pins → runtime determinism preserved); `TimeLimit`-wrapped strips.
- **Reproducibility caveat (carried from V1):** PPO gradient accumulation is float-non-associative, so
  a *retrained* policy may not be byte-identical; the determinism guarantee is about **inference** on
  the committed weights (same seed → byte-identical rollout AND `crowd_grid.json`). A retrained policy's
  only obligation is to **re-pass the FD benchmark** at the LOCKED tolerance.

---

## V2 — Demand source + date

- **Table:** `src/crowd/data/set_times_2026.json` — **22 real headliner rows** hand-transcribed from
  the **official a demo festival 2026 lineup** + the **Clashfinder `ps26` HTML grid**
  (sources: `primaverasound.com/en/barcelona/lineup`, `clashfinder.com/m/ps26/`), **transcribed
  2026-06-10**, festival-day mapped (post-midnight sets assigned to the prior evening). Stage names
  mapped exactly to the 19 geojson names. `tier: ASSUMED`.
- **Popularity weights:** ordinal `popularity_weight` 1–5 (hand Spotify-tier table) — **ASSUMED**;
  it REFINES demand and does **NOT** gate acceptance (T-02.1-04).
- **Representative slice (A8):** one documented **Saturday 22:00 headliner peak** (My Bloody Valentine
  @ Estrella Damm 22:05, etc.) — a single deterministic snapshot, the demand profile the stage-reach
  gate runs against. Revisiting the slice would change test conditions and must be an explicit, dated
  decision, never a pass-engineering move.

---

## V2 — ASSUMED constants (additive to the V1 ledger; `crowd/constants.py`)

All fixed **pre-run** and immutable after (acceptance-integrity discipline). The V1 constants
(`SIM_STEPS = 200`, `BENCH_TOL = 0.20`, Weidmann literals, `V_MAX`, OBS/density radii) are
**UNCHANGED**; V2 only ADDS:

| Parameter | Value | Tier | Role / derivation |
|-----------|-------|------|-------------------|
| `SIM_STEPS_V2` | **1400** | ASSUMED | runtime rollout horizon. Derived by the committed formula `round100(D_far_walkable / (V0·f_congested·STEP_DT_S) + DWELL_MARGIN_STEPS)` with the **MEASURED** 766 m far-stage geodesic (768 m BFS): `996 / (1.34·0.6) + 150 ≈ 1389 → 1400`. (Corrected 2026-06-11 from 1000, which used the 641 m straight-line as a geodesic proxy; the *formula* never changed.) ≈ 23 min walking budget. |
| `STAGE_REACH_FRAC` | **0.70** | ASSUMED, **LOCKED** | stage-reach acceptance fraction; immutable post-lock, never tuned to pass. |
| `REACH_RADIUS_M` | **30.0** | ASSUMED, **LOCKED** | reach radius (= the indicative ±30 m site-georeferencing tolerance). |
| `ARRIVAL_WINDOW_STEPS` | **300** | ASSUMED (A9) | staggered-arrival window; agents activate at a seeded step ∈ [0, 300). Pre-arrival agents are parked at their gate (velocity 0) and density-excluded → honest gate-queue dwell. |
| `SPAWN_FRAC_GATE_A` | **0.85** | ASSUMED | general/VIP entrance split (~85/15). |
| `PRIMAVERA_DAILY_CAPACITY` / `AGENT_DIVISOR` | 65000 / 100 | ASSUMED | N = 650 agents (CROWD-01: N = capacity // 100). |

`BENCH_TOL`, `STAGE_REACH_FRAC`, and `REACH_RADIUS_M` were **never** widened/loosened — the RED gate
is documented and deferred, not laundered.

---

## V2 — V1-suite supersession audit (additive, not destructive)

Per CONTEXT §Testing ("additive, not destructive"), every existing V1 crowd test was re-run on the V2
weights. **Result: ALL GREEN — none superseded, none deleted, none weakened.** The V2 retrain produced
a **7-input** `policy.zip`, which auto-resolved the four+ Plan-03 artifact-keyed xfails (rollout /
benchmark / determinism inference tests, previously xfail'd on the V1 6-input ↔ V2 7-input dimension
mismatch; lifted automatically the moment the dimension-matched policy was committed — strict=False
xpass tolerated, here they hard-pass):

| V1 suite | On V2 weights | Note |
|----------|---------------|------|
| `test_crowd_env` (structural / PRD-exact constants) | ✅ green | `OBS_DIM` read dynamically → 7; V1 SIM_STEPS=200 unchanged |
| `test_crowd_rollout` (200-step + same-seed trajectory) | ✅ green | Plan-03 xfail lifted on the 7-input policy |
| `test_crowd_grid` (dwell / flow / snap) | ✅ green | grid.py FROZEN |
| `test_crowd_contract` / `test_seam_climate_crowd` (XFN-04) | ✅ green | lattice seam unchanged |
| `test_crowd_benchmark` (Weidmann FD) | ✅ green | re-run on the V2 SHA; benchmark_result.json re-bound |
| `test_crowd_determinism` (same-seed grid) | ✅ green | Plan-03 xfails lifted; V2 real-site determinism witnesses added |
| `test_crowd` (provenance gate ASSUMED→DERIVED) | ✅ green | hash-bound DERIVED promotion unchanged |

The **only** non-green crowd item is the NEW `test_crowd_stage_reach.py::test_stage_reach_meets_locked_threshold`
— intentionally **xfail'd** (deferred RED, documented above + in `DEFERRED-GATE-FIX.md`), NOT a
regression of any V1 test.

---

## V2 — Limitations

In addition to the V1 limitations (synthetic training world, single-fixed-scenario FD, CPU-only
determinism — all still apply):

- **Lane physics not yet modelled (the binding stage-reach wall).** `_lateral_push` is alignment-blind:
  it disperses co-moving agents sideways instead of letting them form lanes (Helbing & Molnár 1995).
  The deferred fix (alignment-aware damping of the lateral force between similar-heading pairs, named
  ASSUMED constants, Weidmann speed-cap untouched) is the primary lever for the far cohort.
- **Auditori snap-vs-centre gap.** One stage's true centre is inside a building with no walkable cell
  within `REACH_RADIUS_M = 30 m`; its cohort latches to an unreachable point → 0% by construction. The
  deferred fix snaps the GOAL (not the radius) to the nearest walkable cell for the latch measurement.
- **Global routing is ASSUMED-grade.** Until the stage-reach gate is green, the crowd field's *spatial
  allocation* (which cells are busy) is ASSUMED, not DERIVED — far-stage cells are under-represented.
  Only the *local speed–density physics* is DERIVED (FD-validated). Carried to Phase 3 context.
