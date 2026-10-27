"""WGS84 emitters — UTM31N env artifacts → lon/lat payloads for the MapLibre/Mapbox map.

Single source of truth for the three map-facing JSON shapes the frontend consumes:

  * ``emit_trajectories``     — per-step agent ``[lon, lat, speed]``, step-downsampled.
  * ``emit_crowd_grid_wgs84`` — density cells + dwell polygons + flow vectors (WGS84 mirror).
  * ``emit_heat``             — UTCI heat cells (WGS84) + min/max range.

Promoted verbatim out of ``viz/run_demo_sim_v2.py`` so BOTH the demo generator AND the live
``crowd`` pipeline stage (``run_crowd_stage``) emit byte-identical shapes from one code path —
no drift between the demo aesthetic and the real run (the whole point of the de-mock).

Pure functions: numpy in, JSON-ready dict out. ``to_lonlat`` (pyproj UTM31N→WGS84) is the only
projection seam. ``stride_for_budget`` re-implements the demo's "tighten stride until the payload
fits the MB budget" loop so the live stage can bound the per-run trajectory size identically.
"""
from __future__ import annotations

import json

import numpy as np

from crowd.constants import DAYTIME_HOURS, FRAMES_PER_HOUR_JPS, TRAJ_DOWNSAMPLE_BUDGET_MB, V_MAX
from crs.crs import to_lonlat


def daytime_timestamps(
    n_steps_recorded: int,
    stride: int,
    *,
    hours: list[str] = DAYTIME_HOURS,
    frames_per_hour: int = FRAMES_PER_HOUR_JPS,
) -> list[str]:
    """Per-recorded-frame wall-clock index keyed to the real festival hours (DAYCROWD-03 timeline).

    The continuous daytime run records ``frames_per_hour × (len(hours) - 1)`` pre-stride frames — one
    ``frames_per_hour`` budget per daytime INTERVAL, ``len(hours) - 1`` intervals spanning the full
    ``hours[0] → hours[-1]`` clock (e.g. 11 intervals across 09:00→20:00, 12 hour marks). For each
    RECORDED (post-stride) frame ``i`` we report the wall-clock REACHED after that frame's elapsed
    simulation. Letting ``total = frames_per_hour × (len(hours) - 1)`` be the pre-stride frame count
    and ``elapsed = i * stride + 1`` the pre-stride frames simulated through frame ``i``::

        hour_index = (elapsed * (len(hours) - 1)) // total      (clamped to len(hours) - 1)

    so frame 0 (``elapsed == 1``) maps to ``hours[0]`` ("09:00") and the FINAL recorded frame
    (``elapsed == total``) maps to ``hours[-1]`` ("20:00") — both day endpoints are hit exactly.
    ``elapsed`` is strictly increasing in ``i`` and integer-division is monotonic, so the list is
    MONOTONIC NON-DECREASING by construction. The wall-clock for any frame ``i`` is therefore
    derivable PURELY from ``timestamps[i]`` — NO modulo over total steps is ever needed. This is
    exactly what kills the frontend ``% maxT`` wrap-around clock (``TrajectoryPlayback.tsx``
    ~line 114): the real clock advances across the full festival day, it does not wrap.

    Args:
        n_steps_recorded: number of recorded (post-stride) frames — the emitted ``frames`` length.
        stride: the step-downsample stride applied to the raw trajectory before emit.
        hours: the daytime hour grid (``DAYTIME_HOURS`` — NAMED, never inlined, anti-tuning).
        frames_per_hour: pre-stride recorded frames per daytime interval (``FRAMES_PER_HOUR_JPS``).

    Returns:
        A list of ``"HH:MM"`` strings of length ``n_steps_recorded``, monotonic non-decreasing,
        starting at ``hours[0]`` and ending at ``hours[-1]``.
    """
    last_hour = len(hours) - 1
    total = frames_per_hour * last_hour  # pre-stride frame count across the full day
    out: list[str] = []
    for i in range(n_steps_recorded):
        elapsed = i * stride + 1  # pre-stride frames simulated through recorded frame i
        hour_index = (elapsed * last_hour) // total if total > 0 else 0
        if hour_index > last_hour:
            hour_index = last_hour
        out.append(hours[hour_index])
    return out


def emit_daytime_trajectories(
    traj: np.ndarray,
    label: str,
    stride: int,
    *,
    hour_boundary_frames: list[int],
    note: str | None = None,
) -> dict:
    """``emit_trajectories`` + a ``timestamps`` sidecar and ``hour_boundaries`` (DAYCROWD-03).

    PURELY ADDITIVE over :func:`emit_trajectories`: it calls it verbatim and ADDS two keys to the
    returned dict — no existing key is removed or renamed (``n_steps_recorded`` / ``frames`` /
    ``stride`` stay byte-compatible, so ``runs.v2.n_steps_recorded`` keeps working):

    * ``timestamps`` — :func:`daytime_timestamps` of length == ``n_steps_recorded``; a monotonic
      non-decreasing ``"HH:MM"`` index so a later frontend phase renders a REAL clock (advance
      ``timestamps[i]``) instead of the ``% maxT`` modulo wrap. (Frontend rewrite is a NON-GOAL of
      this phase — this only EMITS the artifact that makes the kill possible.)
    * ``hour_boundaries`` — the POST-stride recorded-frame indices where the wall-clock hour switches,
      derived from the pre-stride ``hour_boundary_frames`` via ``frame // stride`` (de-duplicated,
      sorted), so a scrubber can mark the 11 interval edges.

    Args:
        traj: ``(steps, n_agents, 4)`` continuous daytime trajectory.
        label: run label surfaced in the map metadata panel.
        stride: step-downsample stride.
        hour_boundary_frames: PRE-stride frame indices where an hour switch happens (the
            ``FRAMES_PER_HOUR_JPS`` multiples the continuous run records per interval).
        note: optional honesty note (passed through to :func:`emit_trajectories`).
    """
    inner = emit_trajectories(traj, label, stride, note=note)
    timestamps = daytime_timestamps(inner["n_steps_recorded"], stride)
    boundaries = sorted({fr // stride for fr in hour_boundary_frames})
    inner["timestamps"] = timestamps
    inner["hour_boundaries"] = boundaries
    return inner


def emit_trajectories(traj: np.ndarray, label: str, stride: int, *, note: str | None = None) -> dict:
    """WGS84 per-step agent ``[lon, lat, speed]``, step-downsampled by ``stride``.

    Args:
        traj: ``(steps, n_agents, 4)`` rollout trajectory — per-step per-agent ``[x, y, vx, vy]``
            in UTM31N metres (the shape ``crowd.rollout.rollout`` returns).
        label: short run label surfaced in the map metadata panel.
        stride: keep every ``stride``-th step (the demo uses 2 → ~700 frames at 1400 steps).
        note: optional honesty note; defaults to the indicative-positions disclaimer.
    """
    step_idx = list(range(0, traj.shape[0], stride))
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
        "note": note or "site-native rollout; stage/entrance positions INDICATIVE +/-30 m",
        "n_agents": traj.shape[1],
        "n_steps_recorded": len(step_idx),
        "stride": stride,
        "v_max_m_per_step": V_MAX,
        "agent_format": "[lon, lat, speed_m_per_step]",
        "frames": frames,
    }


def trajectories_payload(traj: np.ndarray, label: str, *, note: str | None = None,
                         budget_mb: float = TRAJ_DOWNSAMPLE_BUDGET_MB) -> dict:
    """Full ``{"default": "v2", "runs": {"v2": <emit_trajectories>}}`` payload, stride-bounded.

    Starts at stride 2 and doubles (cap 16) until the serialised payload fits ``budget_mb`` —
    the same DoS/size guard the demo generator applies (T-2.2-06).
    """
    stride = 2
    inner = emit_trajectories(traj, label, stride, note=note)
    payload = {"default": "v2", "runs": {"v2": inner}}
    while _payload_mb(payload) > budget_mb and stride < 16:
        stride *= 2
        inner = emit_trajectories(traj, label, stride, note=note)
        payload = {"default": "v2", "runs": {"v2": inner}}
    return payload


def _payload_mb(payload: dict) -> float:
    return len(json.dumps(payload, separators=(",", ":"))) / 1e6


def emit_crowd_grid_wgs84(crowd_grid: dict) -> dict:
    """WGS84 mirror of the UTM crowd_grid (density cells + dwell polygons + flow vectors)."""
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
        "note": "crowd field (WGS84 mirror); density on the real UTCI lattice",
        "cell_size_m": crowd_grid["lattice"]["cell_size_m"],
        "cells": cells, "dwell_zones": dwell, "flow_vectors": flows,
    }


def crowd_grid_payload(crowd_grid: dict) -> dict:
    """Full ``{"default": "v2", "runs": {"v2": <emit_crowd_grid_wgs84>}}`` payload."""
    return {"default": "v2", "runs": {"v2": emit_crowd_grid_wgs84(crowd_grid)}}


def emit_structure_zones(zones: dict) -> dict:
    """WGS84 view of the ranked placement output (``structure_zones.json``).

    The placer emits ranked ZONES in UTM31N (each ``structure`` has a ``center``
    ``{x_m, y_m}`` + ``area_m2``); the map needs WGS84 footprints. We project the
    center to lon/lat and build an axis-aligned square footprint of side
    ``sqrt(area_m2)`` around it (the zone is reported as an area, not a fitted
    polygon — a square is the honest minimal footprint, NOT a fabricated shape).
    Every ranked field (rank, coverage_pct, marginal/cumulative demand, robustness,
    surviving_snapshots) passes through verbatim so the side list can mirror the map.

    Coverage/demand figures stay ASSUMED-grade (crowd weights unvalidated per site);
    the frontend tags them — this emitter does not invent or relabel provenance.
    """
    out = []
    for s in zones.get("structures", []):
        cx, cy = s["center"]["x_m"], s["center"]["y_m"]
        half = (float(s["area_m2"]) ** 0.5) / 2.0
        corners_utm = [
            (cx - half, cy - half), (cx + half, cy - half),
            (cx + half, cy + half), (cx - half, cy + half),
        ]
        ring = [[round(lo, 6), round(la, 6)]
                for lo, la in (to_lonlat(x, y) for x, y in corners_utm)]
        ring.append(ring[0])  # close the polygon
        c_lon, c_lat = to_lonlat(cx, cy)
        out.append({
            "rank": s.get("rank"),
            "center": [round(c_lon, 6), round(c_lat, 6)],
            "footprint": ring,
            "area_m2": round(float(s["area_m2"]), 1),
            "coverage_pct": s.get("coverage_pct"),
            "marginal_demand": s.get("marginal_demand"),
            "cumulative_demand": s.get("cumulative_demand"),
            "newly_covered_cell_count": s.get("newly_covered_cell_count"),
            "robustness": s.get("robustness"),
            "surviving_snapshots": s.get("surviving_snapshots", []),
        })
    return {
        "note": "ranked shade-priority zones (WGS84); square footprint = sqrt(area_m2)",
        "coverage_model": zones.get("coverage_model"),
        "stopping_rule": zones.get("stopping_rule"),
        "total_demand": zones.get("total_demand"),
        "covered_demand": zones.get("covered_demand"),
        "coverage_pct": zones.get("coverage_pct"),
        "infeasible": zones.get("infeasible"),
        "structures": out,
    }


def emit_heat(utci_cells: list[dict], lattice: dict) -> dict:
    """WGS84 UTCI heat cells + min/max range, from the UTM ``utci_grid.json`` cells."""
    umin = min(c["utci_c"] for c in utci_cells)
    umax = max(c["utci_c"] for c in utci_cells)
    cells = []
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
