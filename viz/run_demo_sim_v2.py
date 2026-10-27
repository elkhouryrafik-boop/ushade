"""DEMO ARTIFACT (V2 site-native) — Primavera 2026 real-layout crowd-simulation rollout.

Supersedes ``viz/run_demo_sim.py`` (V1-era ``DemoEnv``). This script rolls the COMMITTED
V2 policy (``src/crowd/policy.zip``, seed 1789) through the CANONICAL real-site
``FestivalEnv`` — the SAME env the V2 stage-reach gate uses
(``tests/conftest_crowd.build_real_site_env``): 7-float flow-field obs, the real
139×153 @ 6 m UTCI lattice, 19 real stages + 2 entrances + 13 impassable blockers,
demand-weighted goals for the documented Saturday-22:00 slice, and seeded staggered
arrivals. N = PRIMAVERA_DAILY_CAPACITY // AGENT_DIVISOR = 650 agents (= 65,000 people at
1:100). It runs SIM_STEPS_V2 = 1400 steps.

It is READ-ONLY w.r.t. src/ and tests/ — it imports ``build_real_site_env`` from the test
scaffolding and the pure ``crowd``/``crs`` modules; it never modifies them. Emits, into the
gitignored ``viz/data/``:

  * demo_trajectories.json — WGS84 per-step agent positions+speed, downsampled to every
    2nd step (700 frames), single clean run.
  * demo_crowd_grid.json   — density + dwell_zones + flow_vectors (WGS84 mirror) from
    crowd.grid.build_crowd_grid on the READ lattice.
  * demo_heat.json         — UTCI WGS84 heat (REUSED if present, else regenerated).
  * demo_meta.json         — sidecar the HTML reads (seed, N, steps, reach, honesty line).

Honest labels everywhere: stage/entrance positions are INDICATIVE ±30 m; the stage-reach
gate is RED (54.8% vs 70% locked target), surfaced in the metadata as a deferred known gap.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
ROOT = HERE.parent
SRC = ROOT / "src"
TESTS = ROOT / "tests"
DATA = HERE / "data"
sys.path.insert(0, str(SRC))    # reuse src/ modules (read-only): crowd.*, crs.*
sys.path.insert(0, str(TESTS))  # reuse the canonical real-site env builder (read-only)

from conftest_crowd import build_real_site_env  # noqa: E402
from crowd.constants import (  # noqa: E402
    AGENT_DIVISOR,
    PRIMAVERA_DAILY_CAPACITY,
    REACH_RADIUS_M,
    SEED,
    SIM_STEPS_V2,
    TRAJ_DOWNSAMPLE_BUDGET_MB,
)
from crowd.grid import build_crowd_grid  # noqa: E402
from crowd.wgs84_export import (  # noqa: E402  (single source of truth for the map shapes)
    emit_crowd_grid_wgs84,
    emit_heat,
    emit_trajectories,
)

POLICY_PATH = SRC / "crowd" / "policy.zip"
N_AGENTS = PRIMAVERA_DAILY_CAPACITY // AGENT_DIVISOR  # 650
UTCI_GRID_PATH = ROOT / "projects" / "primavera-demo" / "utci_grid.json"


def _load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
# Rollout (the V2 canonical real-site env + committed V2 policy)
# ─────────────────────────────────────────────────────────────────────────────
def rollout(policy, env, n_steps: int) -> np.ndarray:
    """Deterministic decentralised per-agent PPO rollout on the V2 site env.

    Each step: env yields one obs per agent (observe_all → (N, 7)); the shared policy is
    applied batched-deterministic; the env integrates all agents (step_all). Records the
    per-step snapshot ([x,y,vx,vy]); returns (n_steps+1, N, 4).
    """
    env.reset(seed=SEED)
    frames = [env.snapshot()]
    for _ in range(n_steps):
        obs = env.observe_all()
        actions, _ = policy.predict(obs, deterministic=True)
        env.step_all(actions)
        frames.append(env.snapshot())
    return np.asarray(frames, dtype=np.float64)


def latched_reach(env, traj) -> tuple[float, np.ndarray]:
    """Per-agent LATCHED stage-reach fraction (the gate's measure), plus per-stage arrival counts.

    Mirrors tests/test_crowd_stage_reach._measure_latched_reach: agent i latches reached the
    first step >= its activate_step it is within REACH_RADIUS_M of its ASSIGNED stage centre.
    """
    goals = env._goals[env._goal_idx]          # (N, 2) assigned stage centre per agent
    activate = env._activate_step              # (N,) staggered arrival step
    reached = np.zeros(env._n_agents, dtype=bool)
    for step in range(traj.shape[0]):
        pos = traj[step, :, :2]
        arrived = step >= activate
        dist = np.linalg.norm(pos - goals, axis=1)
        reached |= arrived & (dist <= REACH_RADIUS_M)
    return float(reached.mean()), reached


def traj_sha256(traj: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(traj).tobytes()).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Emitters live in ``crowd.wgs84_export`` (single source of truth — the live
# ``run_crowd_stage`` emits the SAME shapes). Imported above. The demo passes its
# own ``note=`` so the on-map metadata still flags these as DEMO artifacts.
# ─────────────────────────────────────────────────────────────────────────────
_DEMO_TRAJ_NOTE = "DEMO V2 site-native rollout; stage/entrance positions INDICATIVE +/-30 m"


def write_json(path: Path, obj: dict) -> float:
    path.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")
    return path.stat().st_size / 1e6


# ─────────────────────────────────────────────────────────────────────────────
def main():
    grid = _load_json(UTCI_GRID_PATH)
    lattice = grid["lattice"]
    utci_cells = grid["cells"]

    print(f"[demo-v2] N agents = {PRIMAVERA_DAILY_CAPACITY} // {AGENT_DIVISOR} = {N_AGENTS}")
    print(f"[demo-v2] lattice {lattice['cols']}x{lattice['rows']} @ {lattice['cell_size_m']} m, "
          f"seed {SEED}, {SIM_STEPS_V2} steps")

    # Build the CANONICAL real-site env (real stages/entrances/blockers, demand-weighted
    # goals, staggered arrivals) — the SAME builder the stage-reach gate uses.
    env = build_real_site_env(n_agents=N_AGENTS, seed=SEED)
    print(f"[demo-v2] env: {len(env._goals)} stages, {len(env._entrances)} entrances, "
          f"{len(env._blocked)} blocked cells")

    from crowd.rollout import load_policy
    policy = load_policy(POLICY_PATH)
    policy_hash = hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()[:8]
    print(f"[demo-v2] policy loaded ({POLICY_PATH.name}, short-hash {policy_hash})")

    print(f"[rollout] {SIM_STEPS_V2} steps x {N_AGENTS} agents (V2 flow-field obs)...")
    traj = rollout(policy, env, SIM_STEPS_V2)
    sha = traj_sha256(traj)
    print(f"[rollout] trajectory shape {traj.shape}, SHA-256 {sha}")

    # ── Stage-reach + per-stage arrival stats ─────────────────────────────────
    reach_frac, reached = latched_reach(env, traj)
    stage_names = [m["name"] for m in env._site_geometry["stage_meta"]]
    per_stage = np.zeros(len(env._goals), dtype=int)
    for gi in range(len(env._goals)):
        per_stage[gi] = int(reached[env._goal_idx == gi].sum())
    assigned = np.bincount(env._goal_idx, minlength=len(env._goals))
    print(f"[reach] latched stage-reach = {reach_frac:.1%} "
          f"(N={N_AGENTS}, REACH_RADIUS_M={REACH_RADIUS_M} m)")
    order = np.argsort(-per_stage)
    print("[reach] per-stage arrivals (reached / assigned):")
    for gi in order[:8]:
        print(f"          {stage_names[gi]:<28} {per_stage[gi]:>4} / {assigned[gi]:<4}")

    # ── crowd_grid (density + dwell + flow) on the READ lattice ───────────────
    # Bound the dwell-DBSCAN still-point memory: downsample the grid-input trajectory if the
    # steps×agents still-point count would be excessive (a handoff concern; grid.py untouched).
    from crowd.constants import GRID_STILLPOINT_BUDGET
    est_points = traj.shape[0] * traj.shape[1]
    if est_points > GRID_STILLPOINT_BUDGET:
        stride_g = int(np.ceil(est_points / GRID_STILLPOINT_BUDGET))
        idx = np.unique(np.concatenate([np.arange(0, traj.shape[0], stride_g),
                                        [traj.shape[0] - 1]]))
        grid_traj = traj[idx]
        print(f"[grid] downsampled grid input: {traj.shape[0]} -> {len(idx)} steps "
              f"(stride {stride_g}) to bound DBSCAN memory")
    else:
        grid_traj = traj
    cg = build_crowd_grid(grid_traj, lattice)
    top = max((c["crowd_density_agents_per_cell"] for c in cg["cells"]), default=0)
    print(f"[grid] density cells={len(cg['cells'])} top-cell={top:.0f} "
          f"dwell_zones={len(cg['dwell_zones'])} flow_vectors={len(cg['flow_vectors'])}")

    # ── trajectories: downsample to every 2nd step (700 frames); tighten if >budget ──
    stride = 2
    payload = emit_trajectories(traj, "V2 site-native run", stride, note=_DEMO_TRAJ_NOTE)
    mb = len(json.dumps(payload, separators=(",", ":"))) / 1e6
    while mb > TRAJ_DOWNSAMPLE_BUDGET_MB and stride < 16:
        stride *= 2
        payload = emit_trajectories(traj, "V2 site-native run", stride, note=_DEMO_TRAJ_NOTE)
        mb = len(json.dumps(payload, separators=(",", ":"))) / 1e6
        print(f"[emit] over {TRAJ_DOWNSAMPLE_BUDGET_MB} MB -> stride {stride} ({mb:.1f} MB)")
    traj_payload = {"default": "v2", "runs": {"v2": payload}}
    sz = write_json(DATA / "demo_trajectories.json", traj_payload)
    print(f"[write] demo_trajectories.json {sz:.1f} MB ({payload['n_steps_recorded']} frames, "
          f"stride {stride})")

    cg_payload = {"default": "v2", "runs": {"v2": emit_crowd_grid_wgs84(cg)}}
    sz = write_json(DATA / "demo_crowd_grid.json", cg_payload)
    print(f"[write] demo_crowd_grid.json {sz:.2f} MB")

    # ── heat: REUSE if present, else regenerate from the UTCI grid ────────────
    heat_path = DATA / "demo_heat.json"
    if heat_path.exists():
        print(f"[heat] reusing existing demo_heat.json ({heat_path.stat().st_size/1e6:.2f} MB)")
    else:
        sz = write_json(heat_path, emit_heat(utci_cells, lattice))
        print(f"[write] demo_heat.json {sz:.2f} MB (regenerated)")

    # ── metadata sidecar for the HTML ─────────────────────────────────────────
    meta = {
        "model": "V2 site-native",
        "seed": SEED,
        "n_agents": N_AGENTS,
        "people_represented": PRIMAVERA_DAILY_CAPACITY,
        "scale": "1:100 (AGENT_DIVISOR=100)",
        "policy_short_hash": policy_hash,
        "sim_steps": SIM_STEPS_V2,
        "sim_minutes_approx": round(SIM_STEPS_V2 / 60.0),
        "n_stages": len(env._goals),
        "n_entrances": len(env._entrances),
        "blocked_cells": len(env._blocked),
        "reach_pct": round(reach_frac * 100.0, 1),
        "reach_radius_m": REACH_RADIUS_M,
        "frames": payload["n_steps_recorded"],
        "stride": stride,
        "position_accuracy": "positions indicative +/-30 m",
        "trajectory_sha256": sha,
        "honesty_note": (
            "Known gap (deferred): the 3 farthest stages are under-represented - agents "
            "en route; routing gate 54.8% vs 70% target, fix scheduled."
        ),
        "summary_line": (
            f"V2 site-native model, seed {SEED}, {N_AGENTS} agents = "
            f"{PRIMAVERA_DAILY_CAPACITY:,} people (1:100), {SIM_STEPS_V2} steps "
            f"(~{round(SIM_STEPS_V2/60)} min), staggered arrivals, real 2026 set-times demand."
        ),
    }
    write_json(DATA / "demo_meta.json", meta)
    print("[write] demo_meta.json")
    print("\n[demo-v2] DONE.")


if __name__ == "__main__":
    main()
