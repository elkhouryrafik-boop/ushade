"""DEMO ARTIFACT — Primavera 2026 real-layout crowd-simulation rollout.

Runs the committed PPO policy (src/crowd/policy.zip, seed 1789) on the REAL
user-approved festival layout and emits interactive-animation JSON for
viz/crowd_sim_demo.html. This script lives in viz/ and is read-only with respect
to src/ and the PRD pipeline — it REUSES FestivalEnv, build_crowd_grid, the CRS
module, and the locked constants. It does NOT modify any of them.

What it does:
  1. Load festival map + boundary + blockers; project WGS84 -> EPSG:32631 via src/crs.
  2. DemoEnv(FestivalEnv): real entrances (A general / B VIP), real stage goals,
     weighted spawn + goal assignment, and walkability (blocker polygons + outside
     boundary rasterised to blocked lattice cells; agents reverting on entry).
  3. Roll out the policy deterministically for SIM_STEPS (and an EXTENDED run).
  4. Post-process to density + dwell_zones + flow_vectors via crowd.grid.
  5. Emit demo_trajectories.json / demo_crowd_grid.json / demo_heat.json (WGS84),
     prove byte-determinism (two rollouts, SHA-256 of the raw trajectory array).

ASSUMED constants are named with an ASSUMED comment. Honest labels everywhere:
stage/entrance positions are INDICATIVE +/-30 m; carbon/crowd terms stay demo-only.
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
DATA = HERE / "data"
sys.path.insert(0, str(SRC))  # reuse src/ modules (read-only): crowd.*, crs.*

from crowd.constants import AGENT_DIVISOR, SEED, SIM_STEPS, V_MAX  # noqa: E402
from crowd.env import FestivalEnv  # noqa: E402
from crowd.grid import build_crowd_grid  # noqa: E402
from crs.crs import to_lonlat, to_utm31n  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# DEMO-ONLY ASSUMED constants (named; not in src/, this is a viz artifact)
# ─────────────────────────────────────────────────────────────────────────────
#: a demo festival daily site capacity (people). [ASSUMED] public reporting ~65k/day;
#: drives N = capacity // AGENT_DIVISOR using the PRD-locked divisor (1:100 scale).
PRIMAVERA_DAILY_CAPACITY: int = 65_000
#: Fraction of agents spawning at ENTRANCE A (general gate) vs B (VIP). [ASSUMED]
#: General public dominates the gate split; VIP is a small minority.
SPAWN_FRAC_GATE_A: float = 0.85  # -> ~15% at gate B (VIP)
#: Spawn jitter radius (m) around a gate so agents don't stack on one point. [ASSUMED]
SPAWN_JITTER_M: float = 8.0
#: Goal-assignment weights by stage capacity_class. [ASSUMED] bigger stages pull more.
GOAL_WEIGHT_BY_CLASS: dict[str, int] = {"main": 3, "secondary": 2, "electronic": 2}
GOAL_WEIGHT_DEFAULT: int = 1  # club / promenade / indoor / non-stage
#: Extended-run step count for the honest-physics demo. [ASSUMED] 3x the PRD SIM_STEPS
#: so agents can physically cross the ~800 m site (V_MAX*200=268 m < site span).
EXTENDED_SIM_STEPS: int = 600
#: An agent within this many metres of its assigned stage centre has "reached" it. [ASSUMED]
#: Matches the env's internal _GOAL_REACH_RADIUS_M scale, loosened for the +/-30 m site.
GOAL_REACH_RADIUS_M: float = 30.0
#: Trajectory file-size budget (MB) above which per-step output downsamples to every 2nd step.
TRAJ_SIZE_BUDGET_MB: float = 15.0

POLICY_PATH = SRC / "crowd" / "policy.zip"


# ─────────────────────────────────────────────────────────────────────────────
# Geometry helpers (project the real layer files into the lattice coordinate frame)
# ─────────────────────────────────────────────────────────────────────────────
def _load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _polygon_rings_to_utm(geom: dict) -> list[list[tuple[float, float]]]:
    """Return list of exterior rings (UTM metre tuples) for Polygon/MultiPolygon."""
    rings: list[list[tuple[float, float]]] = []
    if geom["type"] == "Polygon":
        polys = [geom["coordinates"]]
    elif geom["type"] == "MultiPolygon":
        polys = geom["coordinates"]
    else:
        return rings
    for poly in polys:
        ext = poly[0]  # exterior ring
        rings.append([to_utm31n(lon, lat) for lon, lat in ext])
    return rings


class DemoEnv(FestivalEnv):
    """FestivalEnv subclass wired to the REAL Primavera 2026 layout (demo only).

    Overrides the synthetic entrances/goals with the user-approved gate + stage
    positions, applies weighted seeded spawn/goal assignment, and enforces
    walkability by reverting any agent that steps into a blocked lattice cell
    (blocker polygons OR outside the site boundary).
    """

    def __init__(self, *, lattice, utci_cells, n_agents, stages_utm,
                 entrances_utm, goal_weights, blocked_cells, **kw):
        super().__init__(lattice=lattice, utci_cells=utci_cells,
                         n_agents=n_agents, seed=SEED, **kw)
        # Replace synthetic entrances/goals with the real layout (UTM31N float64 arrays).
        self._entrances = np.asarray(entrances_utm, dtype=np.float64)  # [A, B]
        self._goals = np.asarray(stages_utm, dtype=np.float64)         # 19 real stages
        self._goal_weights = np.asarray(goal_weights, dtype=np.float64)
        self._blocked = blocked_cells  # set[(col,row)] on the utci lattice

    # -- seeded weighted spawn + goal assignment (deterministic) --------------- #
    def reset(self, *, seed=None, options=None):
        use_seed = self._seed if seed is None else int(seed)
        # Seed gymnasium's RNG the same way the base class does.
        super(FestivalEnv, self).reset(seed=use_seed)
        rng = self.np_random

        # Weighted gate choice: ~85% A, ~15% B (ASSUMED), then jitter so no stacking.
        gate = (rng.random(self._n_agents) >= SPAWN_FRAC_GATE_A).astype(int)  # 0=A, 1=B
        jitter = rng.normal(0.0, SPAWN_JITTER_M, size=(self._n_agents, 2))
        self._pos = self._entrances[gate] + jitter

        # Weighted goal assignment by capacity_class weight (ASSUMED), seeded.
        p = self._goal_weights / self._goal_weights.sum()
        self._goal_idx = rng.choice(len(self._goals), size=self._n_agents, p=p)

        self._vel = np.zeros((self._n_agents, 2), dtype=np.float64)
        self._steps = 0
        self._ego = 0
        self._prev_goal_dist = self._goal_dist_all()
        return self._observe_agent(self._ego), {}

    # -- walkability: revert agents that land in a blocked cell ---------------- #
    def _apply_actions(self, acts):
        pre = self._pos.copy()
        super()._apply_actions(acts)
        if self._blocked:
            cols = ((self._pos[:, 0] - self._origin[0]) // self._cell_size_m).astype(int)
            rows = ((self._pos[:, 1] - self._origin[1]) // self._cell_size_m).astype(int)
            blocked_mask = np.array(
                [(c, r) in self._blocked for c, r in zip(cols, rows)], dtype=bool
            )
            if blocked_mask.any():
                self._pos[blocked_mask] = pre[blocked_mask]
                self._vel[blocked_mask] = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Walkability rasterisation
# ─────────────────────────────────────────────────────────────────────────────
def build_blocked_cells(lattice: dict, boundary_geo: dict, nogo_geo: dict) -> set:
    """Rasterise blocker polygons AND outside-boundary area to blocked (col,row) cells.

    Cell-centre test using shapely prepared geometries on the UTCI lattice.
    """
    from shapely.geometry import Polygon, Point
    from shapely.prepared import prep
    from shapely.ops import unary_union

    ox, oy = lattice["origin_x_m"], lattice["origin_y_m"]
    s = lattice["cell_size_m"]
    cols, rows = lattice["cols"], lattice["rows"]

    # Site boundary polygon (union of all boundary features, UTM).
    bpolys = []
    for f in boundary_geo["features"]:
        for ring in _polygon_rings_to_utm(f["geometry"]):
            bpolys.append(Polygon(ring))
    boundary = unary_union(bpolys)
    boundary_prep = prep(boundary)

    # Blocker polygons (buildings/bridges) — agents may NOT enter.
    blockers = []
    for f in nogo_geo["features"]:
        for ring in _polygon_rings_to_utm(f["geometry"]):
            blockers.append(Polygon(ring))
    blockers_union = unary_union(blockers)
    blockers_prep = prep(blockers_union)

    blocked: set[tuple[int, int]] = set()
    for col in range(cols):
        cx = ox + (col + 0.5) * s
        for row in range(rows):
            cy = oy + (row + 0.5) * s
            pt = Point(cx, cy)
            if (not boundary_prep.contains(pt)) or blockers_prep.intersects(pt):
                blocked.add((col, row))
    return blocked


# ─────────────────────────────────────────────────────────────────────────────
# Layout loading
# ─────────────────────────────────────────────────────────────────────────────
def load_layout():
    festival = _load_json(DATA / "festival_map_2026.geojson")
    boundary = _load_json(DATA / "boundary_2026.geojson")
    nogo = _load_json(DATA / "walkable_nogo_2026.geojson")

    stages, stage_meta, weights = [], [], []
    for f in festival["features"]:
        if f["properties"].get("layer") != "stage":
            continue
        lon, lat = f["geometry"]["coordinates"]
        x, y = to_utm31n(lon, lat)
        stages.append((x, y))
        cls = f["properties"].get("capacity_class", "")
        weights.append(GOAL_WEIGHT_BY_CLASS.get(cls, GOAL_WEIGHT_DEFAULT))
        stage_meta.append({"name": f["properties"]["name"], "class": cls,
                           "lon": lon, "lat": lat})

    # Entrances: A (general, access layer) + B (VIP, amenity layer). Both kind=='entrance'.
    ents = {}
    for f in festival["features"]:
        if f["properties"].get("kind") == "entrance":
            lon, lat = f["geometry"]["coordinates"]
            ents[f["properties"]["name"]] = (to_utm31n(lon, lat), (lon, lat))
    # Order [A, B]: A is the "(general)" gate, B is the "(VIP" gate.
    a = next(v for k, v in ents.items() if "general" in k.lower())
    b = next(v for k, v in ents.items() if "vip" in k.lower())
    entrances_utm = [a[0], b[0]]
    entrances_ll = {"A": a[1], "B": b[1]}

    return {
        "stages_utm": stages, "stage_meta": stage_meta, "weights": weights,
        "entrances_utm": entrances_utm, "entrances_ll": entrances_ll,
        "boundary": boundary, "nogo": nogo,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Rollout
# ─────────────────────────────────────────────────────────────────────────────
def rollout(policy, lattice, utci_cells, layout, blocked, n_agents, n_steps):
    """Deterministic per-agent PPO rollout; returns trajectory (steps, agents, 4)."""
    env = DemoEnv(
        lattice=lattice, utci_cells=utci_cells, n_agents=n_agents,
        stages_utm=layout["stages_utm"], entrances_utm=layout["entrances_utm"],
        goal_weights=layout["weights"], blocked_cells=blocked,
    )
    env.reset(seed=SEED)
    frames = [env.snapshot()]
    for _ in range(n_steps):
        obs = env.observe_all()
        actions, _ = policy.predict(obs, deterministic=True)
        env.step_all(actions)
        frames.append(env.snapshot())
    traj = np.asarray(frames, dtype=np.float64)  # (n_steps+1, n_agents, 4)
    return traj, env


def reach_stats(traj, env):
    """% of agents that ended within GOAL_REACH_RADIUS_M of their assigned stage."""
    end = traj[-1, :, :2]
    goals = env._goals[env._goal_idx]
    dist = np.linalg.norm(end - goals, axis=1)
    return float((dist < GOAL_REACH_RADIUS_M).mean() * 100.0), float(dist.mean())


def traj_sha256(traj: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(traj).tobytes()).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Output emitters (everything mirrored to WGS84 lon/lat for the map)
# ─────────────────────────────────────────────────────────────────────────────
def emit_trajectories(traj, lattice, label, downsample):
    step_idx = list(range(0, traj.shape[0], 2)) if downsample else list(range(traj.shape[0]))
    frames = []
    for t in step_idx:
        pts = []
        for a in range(traj.shape[1]):
            x, y, vx, vy = traj[t, a]
            lon, lat = to_lonlat(x, y)
            speed = float((vx * vx + vy * vy) ** 0.5)
            pts.append([round(lon, 6), round(lat, 6), round(speed, 3)])
        frames.append(pts)
    return {
        "label": label,
        "note": "DEMO rollout on real layout; stage/entrance positions INDICATIVE +/-30 m",
        "n_agents": traj.shape[1],
        "n_steps_recorded": len(step_idx),
        "downsampled": downsample,
        "v_max_m_per_step": V_MAX,
        "agent_format": "[lon, lat, speed_m_per_step]",
        "frames": frames,
    }


def emit_crowd_grid_wgs84(crowd_grid: dict) -> dict:
    """Mirror the UTM crowd_grid into WGS84 coords the map can draw directly."""
    cells = []
    for c in crowd_grid["cells"]:
        lon, lat = to_lonlat(c["x_m"], c["y_m"])
        cells.append({"lon": round(lon, 6), "lat": round(lat, 6),
                      "density": c["crowd_density_agents_per_cell"]})
    dwell = []
    for z in crowd_grid["dwell_zones"]:
        ring = [[round(lo, 6), round(la, 6)]
                for lo, la in (to_lonlat(p["x_m"], p["y_m"]) for p in z["polygon"])]
        dwell.append({"polygon": ring})
    flows = []
    for fv in crowd_grid["flow_vectors"]:
        o_lon, o_lat = to_lonlat(fv["origin"]["x_m"], fv["origin"]["y_m"])
        d_lon, d_lat = to_lonlat(fv["destination"]["x_m"], fv["destination"]["y_m"])
        flows.append({"origin": [round(o_lon, 6), round(o_lat, 6)],
                      "destination": [round(d_lon, 6), round(d_lat, 6)]})
    return {
        "note": "DEMO crowd field (WGS84 mirror); density on the real UTCI lattice",
        "cell_size_m": crowd_grid["lattice"]["cell_size_m"],
        "cells": cells, "dwell_zones": dwell, "flow_vectors": flows,
    }


def emit_heat(utci_cells, lattice) -> dict:
    cells = []
    umin = min(c["utci_c"] for c in utci_cells)
    umax = max(c["utci_c"] for c in utci_cells)
    for c in utci_cells:
        lon, lat = to_lonlat(c["x_m"], c["y_m"])
        cells.append({"lon": round(lon, 6), "lat": round(lat, 6),
                      "utci_c": round(float(c["utci_c"]), 2)})
    return {
        "label": ("UTCI 12-16 h mean, June typical year - real infrared.city data; "
                  "entire site < 26 C comfort threshold on this date"),
        "cell_size_m": lattice["cell_size_m"],
        "utci_min_c": round(float(umin), 2), "utci_max_c": round(float(umax), 2),
        "cells": cells,
    }


def write_json(path: Path, obj: dict) -> float:
    path.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")
    return path.stat().st_size / 1e6


# ─────────────────────────────────────────────────────────────────────────────
def main():
    grid = _load_json(ROOT / "projects" / "primavera-demo" / "utci_grid.json")
    lattice = grid["lattice"]
    utci_cells = grid["cells"]
    layout = load_layout()
    n_agents = PRIMAVERA_DAILY_CAPACITY // AGENT_DIVISOR  # 650

    print(f"[demo] N agents = {PRIMAVERA_DAILY_CAPACITY} // {AGENT_DIVISOR} = {n_agents}")
    print(f"[demo] {len(layout['stages_utm'])} real stage goals, "
          f"2 entrances (A general / B VIP), seed {SEED}")

    print("[demo] rasterising walkability (blockers + outside-boundary)...")
    blocked = build_blocked_cells(lattice, layout["boundary"], layout["nogo"])
    total_cells = lattice["cols"] * lattice["rows"]
    print(f"[demo] blocked cells = {len(blocked)} / {total_cells} "
          f"({100*len(blocked)/total_cells:.1f}% of lattice)")

    # Lazy SB3 import (heavy backend stays out of the pure modules).
    from stable_baselines3 import PPO
    policy = PPO.load(str(POLICY_PATH), device="cpu")
    policy_hash = hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()[:8]
    print(f"[demo] policy loaded ({POLICY_PATH.name}, short-hash {policy_hash})")

    # Honest-physics budget.
    max_travel = V_MAX * SIM_STEPS
    site_span = max(lattice["cols"], lattice["rows"]) * lattice["cell_size_m"]
    print(f"[physics] V_MAX={V_MAX} m/step x {SIM_STEPS} steps = {max_travel:.0f} m max travel; "
          f"site ~{site_span:.0f} m across.")

    runs = {}
    for label, steps in [("prd", SIM_STEPS), ("extended", EXTENDED_SIM_STEPS)]:
        print(f"\n[rollout:{label}] {steps} steps x {n_agents} agents ...")
        traj_a, env = rollout(policy, lattice, utci_cells, layout, blocked, n_agents, steps)
        h1 = traj_sha256(traj_a)
        # Determinism proof: a second independent rollout must be byte-identical.
        traj_b, _ = rollout(policy, lattice, utci_cells, layout, blocked, n_agents, steps)
        h2 = traj_sha256(traj_b)
        assert h1 == h2, f"NON-DETERMINISTIC: {h1} != {h2}"
        pct, mean_d = reach_stats(traj_a, env)
        print(f"[rollout:{label}] trajectory SHA-256 = {h1}")
        print(f"[rollout:{label}] determinism: two rollouts byte-identical -> OK")
        print(f"[rollout:{label}] reached stage (<{GOAL_REACH_RADIUS_M:.0f} m): "
              f"{pct:.1f}% ; mean dist-to-goal = {mean_d:.0f} m")
        runs[label] = {"traj": traj_a, "env": env, "sha": h1, "pct": pct, "mean_d": mean_d}

    # Post-process both runs to crowd_grid via the PURE pipeline transform.
    # The dwell-zone DBSCAN scales with (still-positions) = ~steps x agents; for the
    # long EXTENDED run (650 agents x 600 steps, most near-still against blockers) the
    # pairwise neighbourhood blows past memory. We pass a STEP-DOWNSAMPLED trajectory to
    # the (read-only) pure transform when the still-point budget would be exceeded — a
    # demo-side guard that does not touch src/. [ASSUMED] cap below.
    #: Max still-point budget before downsampling the grid-input trajectory. [ASSUMED]
    GRID_STILLPOINT_BUDGET = 200_000
    grids = {}
    for label in ("prd", "extended"):
        t = runs[label]["traj"]
        est_points = t.shape[0] * t.shape[1]
        if est_points > GRID_STILLPOINT_BUDGET:
            stride = int(np.ceil(est_points / GRID_STILLPOINT_BUDGET))
            # Keep the terminal frame (density snaps to it) by anchoring the stride to the end.
            idx = np.unique(np.concatenate([np.arange(0, t.shape[0], stride), [t.shape[0] - 1]]))
            grid_traj = t[idx]
            print(f"[grid:{label}] downsampled grid input: {t.shape[0]} -> {len(idx)} steps "
                  f"(stride {stride}) to bound DBSCAN memory")
        else:
            grid_traj = t
        cg = build_crowd_grid(grid_traj, lattice)
        grids[label] = cg
        top = max((c["crowd_density_agents_per_cell"] for c in cg["cells"]), default=0)
        print(f"[grid:{label}] density cells={len(cg['cells'])} "
              f"top-cell={top:.0f} dwell_zones={len(cg['dwell_zones'])} "
              f"flow_vectors={len(cg['flow_vectors'])}")

    # Choose the default run for the HTML: extended if it materially improves reach.
    default = "extended" if runs["extended"]["pct"] > runs["prd"]["pct"] + 1.0 else "prd"
    print(f"\n[demo] HTML default run = '{default}' "
          f"(prd reach {runs['prd']['pct']:.0f}% vs extended {runs['extended']['pct']:.0f}%)")

    # --- emit trajectories (downsample if >budget) for BOTH runs ---
    traj_payload = {"default": default, "runs": {}}
    for label in ("prd", "extended"):
        # size probe at full resolution
        probe = emit_trajectories(runs[label]["traj"], lattice,
                                  f"{label} run", downsample=False)
        mb = len(json.dumps(probe, separators=(",", ":"))) / 1e6
        downsample = mb > TRAJ_SIZE_BUDGET_MB
        payload = emit_trajectories(runs[label]["traj"], lattice,
                                    f"{label} run", downsample=downsample)
        if label == "extended":
            payload["label"] = ("extended demo run - 3x PRD step count, demo only")
        traj_payload["runs"][label] = payload
        print(f"[emit:{label}] full ~{mb:.1f} MB -> downsample={downsample}")

    sz = write_json(DATA / "demo_trajectories.json", traj_payload)
    print(f"[write] demo_trajectories.json {sz:.1f} MB")

    # crowd grid: emit default run's grid (plus keep both available)
    cg_payload = {
        "default": default,
        "runs": {label: emit_crowd_grid_wgs84(grids[label]) for label in ("prd", "extended")},
    }
    sz = write_json(DATA / "demo_crowd_grid.json", cg_payload)
    print(f"[write] demo_crowd_grid.json {sz:.2f} MB")

    sz = write_json(DATA / "demo_heat.json", emit_heat(utci_cells, lattice))
    print(f"[write] demo_heat.json {sz:.2f} MB")

    # metadata sidecar for the HTML (seed, hash, entrances, stages, physics note)
    meta = {
        "seed": SEED,
        "n_agents": n_agents,
        "people_represented": PRIMAVERA_DAILY_CAPACITY,
        "scale": "1:100 (AGENT_DIVISOR=100)",
        "policy_short_hash": policy_hash,
        "prd_steps": SIM_STEPS,
        "extended_steps": EXTENDED_SIM_STEPS,
        "default_run": default,
        "spawn_split": {"A_general": SPAWN_FRAC_GATE_A, "B_vip": round(1 - SPAWN_FRAC_GATE_A, 2)},
        "entrances": layout["entrances_ll"],
        "n_stages": len(layout["stages_utm"]),
        "blocked_cells": len(blocked),
        "position_accuracy": "positions indicative +/-30 m",
        "physics_note": (f"V_MAX={V_MAX} m/step; {SIM_STEPS} steps => {max_travel:.0f} m max travel "
                         f"on a ~{site_span:.0f} m site. Extended run = {EXTENDED_SIM_STEPS} steps "
                         f"(3x PRD), demo only."),
        "reach_pct": {label: round(runs[label]["pct"], 1) for label in ("prd", "extended")},
        "trajectory_sha256": {label: runs[label]["sha"] for label in ("prd", "extended")},
    }
    write_json(DATA / "demo_meta.json", meta)
    print("[write] demo_meta.json")
    print("\n[demo] DONE.")


if __name__ == "__main__":
    main()
