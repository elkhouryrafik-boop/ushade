"""Bake the ANIMATED daytime viewer data: MOVING agent frames (not per-hour snapshots) + per-hour
REAL UTCI (infrared) + CD-B-ready density, all on the shared 6 m lattice.

Crowd part: re-runs the continuous migrating sim (now on GROUNDED Spotify draws) and downsamples the
(steps x agents x 4) trajectory into ~N animation frames of agent (col,row) positions — so the viewer
can render agents physically walking + leaving trails, and cross-fade the heat under them.
Heat part: reads the 12 real per-hour UTCI grids from projects/primavera-aug2026/ (infrared).

Writes presentations/daytime_anim_data.js (window.ANIM_DATA = {...};).
Run: PYTHONPATH=src python scripts/viz/build_animation_data.py
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np

from crowd.constants import DAYTIME_HOURS, FRAMES_PER_HOUR_JPS

_REPO = Path(__file__).resolve().parent.parent.parent
_PROJECTS = _REPO / "projects"
_CROWD_PROJECT = "primavera-demo"          # crowd geometry/brief (lattice matches the aug UTCI 139x153)
_HEAT_PROJECT = "primavera-aug2026"        # the 12 real infrared UTCI grids
_OUT = _REPO / "presentations" / "daytime_anim_data.js"
_TRAJ_CACHE = _REPO / "scripts" / "viz" / "_traj_cache.npy"   # raw trajectory, so re-bakes skip the 13-min sim
_FRAMES = 1100                              # animation frames across the whole day (~100/hour -> smooth walk, no zoom)


def main() -> None:
    from crowdsim.continuous import run_continuous_daytime

    # lattice (authority) from the crowd project's utci_grid.json
    utci0 = json.loads((_PROJECTS / _CROWD_PROJECT / "utci_grid.json").read_text(encoding="utf-8"))
    lat = utci0["lattice"]
    ox, oy, s, cols, rows = lat["origin_x_m"], lat["origin_y_m"], lat["cell_size_m"], lat["cols"], lat["rows"]

    if _TRAJ_CACHE.exists():
        traj = np.load(_TRAJ_CACHE)
        print(f"  trajectory (cached) {traj.shape}", flush=True)
    else:
        print("Running the continuous migrating sim (GROUNDED Spotify draws)...", flush=True)
        traj = run_continuous_daytime(_CROWD_PROJECT, projects_root=str(_PROJECTS))  # (steps, agents, 4)
        np.save(_TRAJ_CACHE, traj)
        print(f"  trajectory {traj.shape} (cached for re-bakes)", flush=True)
    n_steps = traj.shape[0]

    # downsample to animation frames; store agent (col,row) fractional, 1 dp, drop off-lattice
    stride = max(1, n_steps // _FRAMES)
    frames = []
    for i in range(0, n_steps, stride):
        f = traj[i]
        # ALL agents every frame, index-aligned (so the viewer can interpolate position[i] between
        # frames for smooth motion + trails). Off-lattice agents kept as-is; the viewer skips drawing them.
        col = np.round((f[:, 0] - ox) / s, 1)
        row = np.round((f[:, 1] - oy) / s, 1)
        frames.append(np.stack([col, row], axis=1).tolist())
    # which daytime hour each frame falls in (for the clock + heat cross-fade)
    frame_hour = [min(len(DAYTIME_HOURS) - 1, (i * stride) // FRAMES_PER_HOUR_JPS) for i in range(len(frames))]

    # 12 real per-hour UTCI grids -> compact [col,row,utci] per hour (+ global min/max)
    heat_hours, umin, umax = [], 1e9, -1e9
    hour_files = {f"{h:02d}:00": _PROJECTS / _HEAT_PROJECT / f"utci_{h:02d}.json" for h in range(9, 21)}
    for hh, fp in hour_files.items():
        if not fp.exists():
            print(f"  WARN missing UTCI {hh} ({fp.name}) — heat will interpolate over it", flush=True)
            heat_hours.append({"hour": hh, "cells": None})
            continue
        art = json.loads(fp.read_text(encoding="utf-8"))
        cells = []
        for c in art["cells"]:
            col = int((c["x_m"] - ox) // s)
            row = int((c["y_m"] - oy) // s)
            t = round(float(c["utci_c"]), 2)
            cells.append([col, row, t]); umin = min(umin, t); umax = max(umax, t)
        heat_hours.append({"hour": hh, "cells": cells,
                           "src": art.get("_meta", {}).get("weather_source", "infrared")})

    # 3 GROUNDED diagnostic layers (single grid each over the day) — sun-hours / solar / heat-stress
    diagnostics = {}
    DIAG = [("sun_hours", "sun_hours_grid.json", "sun_hours", "hours of direct sun"),
            ("solar", "solar_radiation_grid.json", "solar_wm2", "W/m² solar load"),
            ("heat_stress", "heat_stress_grid.json", "heat_stress_frac", "fraction of day heat-stressed")]
    for key, fname, vkey, label in DIAG:
        fp = _PROJECTS / _HEAT_PROJECT / fname
        if not fp.exists():
            print(f"  (diagnostic {key} not on disk yet — skipped)", flush=True)
            continue
        art = json.loads(fp.read_text(encoding="utf-8"))
        cells, vmin, vmax = [], 1e18, -1e18
        for c in art["cells"]:
            col = int((c["x_m"] - ox) // s); row = int((c["y_m"] - oy) // s)
            v = round(float(c[vkey]), 3); cells.append([col, row, v]); vmin = min(vmin, v); vmax = max(vmax, v)
        diagnostics[key] = {"cells": cells, "min": round(vmin, 3), "max": round(vmax, 3),
                            "value_key": vkey, "label": label}
        print(f"  diagnostic {key}: {vmin}..{vmax} {vkey}", flush=True)

    brief = json.loads((_PROJECTS / _CROWD_PROJECT / "parsed_brief.json").read_text(encoding="utf-8"))
    payload = {
        "diagnostics": diagnostics,
        "site": "Parc del Forum", "date": "2026-08-15", "capacity": brief.get("capacity"),
        "lattice": {"cols": cols, "rows": rows, "cell_size_m": s},
        "hours": DAYTIME_HOURS,
        "frames": frames, "frame_hour": frame_hour, "n_agents": int(traj.shape[1]),
        "heat_hours": heat_hours, "utci_min": round(umin, 2), "utci_max": round(umax, 2),
        "heat_tier": "GROUNDED (infrared.city UTCI, 2026-08-15 per-hour)",
        "density_tier": "ASSUMED", "popularity_tier": "GROUNDED (Spotify)",
    }
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text("window.ANIM_DATA=" + json.dumps(payload, separators=(",", ":")) + ";", encoding="utf-8")
    kb = _OUT.stat().st_size / 1024
    print(f"\nWrote {_OUT} ({kb:.0f} KB)")
    print(f"  {len(frames)} frames x {traj.shape[1]} agents | heat {umin}..{umax}C | "
          f"{sum(1 for h in heat_hours if h['cells'])}/12 real UTCI hours")


if __name__ == "__main__":
    main()
