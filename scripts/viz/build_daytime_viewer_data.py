"""Bake a standalone-viewer JSON from the REAL Phase-16 daytime crowd sim + the offline UTCI grid.

Runs `crowdsim.continuous.run_continuous_daytime` on the committed primavera-demo project (ONE
persistent migrating JuPedSim run across 09:00->20:00), then derives per-hour crowd density with a
plain numpy histogram on the 6 m lattice (NO DBSCAN dwell-zone clustering — that path OOMs at 650
agents and the viewer only needs per-cell counts). Reads the existing `utci_grid.json` heat field
(NO infrared call — offline only). Writes presentations/daytime_viewer_data.js (a `window.VIEWER_DATA`
assignment so the HTML opens with a double-click, no server / no CORS).

Run: PYTHONPATH=src python scripts/viz/build_daytime_viewer_data.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from crowd.constants import DAYTIME_HOURS, FRAMES_PER_HOUR_JPS

_REPO = Path(__file__).resolve().parent.parent.parent
_PROJECTS = _REPO / "projects"
_PROJECT = "primavera-demo"
_OUT = _REPO / "presentations" / "daytime_viewer_data.js"
_FRAME_STRIDE = 50  # sample ~28 frames/hour for the per-hour mean density (smooth + fast)


def main() -> None:
    from crowdsim.continuous import run_continuous_daytime

    print("Running the real daytime continuous migrating sim (one persistent run)...", flush=True)
    traj = run_continuous_daytime(_PROJECT, projects_root=str(_PROJECTS))  # (steps, agents, 4)
    print(f"  trajectory: {traj.shape}", flush=True)

    utci = json.loads((_PROJECTS / _PROJECT / "utci_grid.json").read_text(encoding="utf-8"))
    lat = utci["lattice"]
    ox, oy, s = lat["origin_x_m"], lat["origin_y_m"], lat["cell_size_m"]
    cols, rows = lat["cols"], lat["rows"]

    # Static heat field (offline UTCI — NO infrared call).
    heat, umin, umax = [], 1e9, -1e9
    for c in utci["cells"]:
        col = int((c["x_m"] - ox) // s)
        row = int((c["y_m"] - oy) // s)
        t = round(float(c["utci_c"]), 2)
        heat.append([col, row, t])
        umin, umax = min(umin, t), max(umax, t)

    # Per-hour density = MEAN agents per 6 m cell over the hour's sampled frames (plain histogram).
    n_intervals = len(DAYTIME_HOURS) - 1
    hours, cmax = [], 0.0
    for h in range(n_intervals):
        sl = traj[h * FRAMES_PER_HOUR_JPS:(h + 1) * FRAMES_PER_HOUR_JPS:_FRAME_STRIDE]  # (f, agents, 4)
        acc = np.zeros((rows, cols), dtype=float)
        for frame in sl:
            ix = ((frame[:, 0] - ox) // s).astype(int)
            iy = ((frame[:, 1] - oy) // s).astype(int)
            m = (ix >= 0) & (ix < cols) & (iy >= 0) & (iy < rows)
            np.add.at(acc, (iy[m], ix[m]), 1.0)
        acc /= max(1, len(sl))  # mean agents/cell this hour
        cells = []
        rr, cc = np.nonzero(acc)
        for r, c in zip(rr.tolist(), cc.tolist()):
            d = round(float(acc[r, c]), 3)
            cells.append([c, r, d])
            cmax = max(cmax, d)
        hours.append({"hour": DAYTIME_HOURS[h],
                      "max_density": round(max((x[2] for x in cells), default=0), 3),
                      "crowd": cells})

    worst_idx = int(np.argmax([hh["max_density"] for hh in hours]))
    brief = json.loads((_PROJECTS / _PROJECT / "parsed_brief.json").read_text(encoding="utf-8"))

    # Honest magnitude tier (reads the same fingerprint-bound gate the engine uses).
    from crowd.daytime_runner import _magnitude_tier
    mag_tier, mag_src = _magnitude_tier()

    payload = {
        "site": "Parc del Forum (primavera-demo)",
        "capacity": brief.get("capacity"),
        "lattice": {"cols": cols, "rows": rows, "cell_size_m": s, "origin_x_m": ox, "origin_y_m": oy},
        "utci_min": round(umin, 2), "utci_max": round(umax, 2), "heat": heat,
        "crowd_max": round(cmax, 3), "hours": hours,
        "worst_hour": DAYTIME_HOURS[worst_idx], "worst_hour_index": worst_idx,
        "magnitude_tier": mag_tier, "magnitude_source": mag_src,
        "field_tier": "DERIVED-from-ASSUMED", "n_frames": int(traj.shape[0]),
    }
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text("window.VIEWER_DATA=" + json.dumps(payload) + ";", encoding="utf-8")
    print(f"\nWrote {_OUT}")
    print(f"  heat cells={len(heat)} utci={umin}..{umax} C | hours={len(hours)} "
          f"crowd_max={cmax:.2f}/cell worst={DAYTIME_HOURS[worst_idx]} tier={mag_tier}")


if __name__ == "__main__":
    main()
