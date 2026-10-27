"""The PURE trajectory->crowd_grid transform of Phase 2b (the net-new code).

``build_crowd_grid(trajectory, lattice)`` converts a rollout trajectory
(``steps x agents x {x, y, vx, vy}``) into a contract-valid ``crowd_grid`` artifact:
lattice-snapped crowd density (CROWD-04), DBSCAN dwell_zones (CROWD-02), and
origin->destination flow_vectors (CROWD-03). It is the analogue of Phase-2a's
``src/climate/lattice.py`` — the seam where the crowd field snaps to the climate
master lattice.

NOTE — PURITY IS A CONTRACT: this module imports NONE of the three heavy ML deep-learning
backends (the neural-net engine, the RL-algorithm library, or the env API). It depends
only on ``numpy`` + ``sklearn`` (DBSCAN) + optionally ``shapely`` (convex hull, with a
hand-rolled monotone-chain fallback). That keeps these transforms in the BASE suite — the
rollout that PRODUCES the trajectory is the only place those heavy backends live
(lazy-imported in ``rollout.py``). The static guard in ``tests/test_crowd_grid.py`` greps
this file for any of those three forbidden tokens and a ``sys.modules`` guard asserts
importing this module pulls in none of them (T-02b-10).

Three responsibilities, in order:

1. SNAP terminal agent positions to the READ lattice by integer index
   (``(x_m - origin_x_m) // cell_size_m``); cell-centre convention IDENTICAL to
   ``lattice.py`` (``origin + (idx + 0.5) * cell_size_m``). Off-lattice agents are
   DROPPED, never emitted as out-of-range cells (T-02b-09). The lattice is the
   AUTHORITY read from ``utci_grid.json`` — NEVER re-derived (CONTRACT-03 / T-02b-08).
2. DBSCAN over positions where ``|velocity| < V_STILL`` for STRICTLY MORE than
   ``DWELL_MIN_STEPS`` consecutive steps; each non-noise cluster -> convex-hull
   polygon (>=3 points, contract ``minItems: 3``) -> a ``dwell_zone`` (CROWD-02).
3. Group agents by nearest spawn concentration; for each MAJOR group
   (>= ``FLOW_MIN_GROUP_FRAC * N``), emit ``origin`` = mean start position,
   ``destination`` = mean end position; cap at ``FLOW_TOP_K`` by group size (CROWD-03).

Emit the SAME ``lattice`` dict object read in into ``crowd_grid["lattice"]`` (no copy,
no re-derive) -> guarantees byte-equality with ``utci_grid.lattice`` (the XFN-04
climate x crowd alignment seam).

karpathy: three small pure helpers + one composer. No class, no abstraction layer.
"""

from __future__ import annotations

import numpy as np
from sklearn.cluster import DBSCAN

from crowd.constants import (
    DBSCAN_EPS_CELLS,
    DBSCAN_MIN_SAMPLES,
    DWELL_MIN_STEPS,
    FLOW_DBSCAN_EPS_CELLS,
    FLOW_MIN_GROUP_FRAC,
    FLOW_TOP_K,
    V_STILL,
)

# Trajectory axis layout [x, y, vx, vy] (matches conftest_crowd.synthetic_trajectory).
_X, _Y, _VX, _VY = 0, 1, 2, 3
_SCHEMA_VERSION = "1.0.0"
_CRS = {"epsg": 32631, "units": "metre"}


def snap_to_lattice(positions_xy, lattice) -> list[dict]:
    """Histogram agent positions into lattice cells by INTEGER INDEX (CROWD-04).

    Reads the lattice descriptor (origin/cell_size/cols/rows) — never re-derives it.
    Off-lattice agents are dropped. Cell-centre convention is identical to
    ``src/climate/lattice.py`` (``origin + (idx + 0.5) * cell_size_m``), so the crowd
    density cells land exactly on the master-lattice cell centres.
    """
    ox = lattice["origin_x_m"]
    oy = lattice["origin_y_m"]
    s = lattice["cell_size_m"]  # 6.0, READ from utci_grid (CONTRACT-03)
    cols = lattice["cols"]
    rows = lattice["rows"]

    counts: dict[tuple[int, int], int] = {}
    for x_m, y_m in positions_xy:
        col = int((x_m - ox) // s)
        row = int((y_m - oy) // s)
        if 0 <= col < cols and 0 <= row < rows:  # drop off-lattice agents (T-02b-09)
            counts[(col, row)] = counts.get((col, row), 0) + 1

    return [
        {
            "x_m": ox + (col + 0.5) * s,  # cell-centre, SAME convention as lattice.py
            "y_m": oy + (row + 0.5) * s,
            "crowd_density_agents_per_cell": float(n),
        }
        for (col, row), n in counts.items()
    ]


def _convex_hull_polygon(points) -> list[dict]:
    """Convex hull of ``points`` (>=3 ``point_m`` dicts) via shapely, monotone-chain fallback.

    Guarantees >=3 points (the contract ``dwell_zone.polygon`` ``minItems``): a cluster
    that is collinear/degenerate is padded by closing the ring so it still satisfies the
    contract honestly (a thin sliver is still a valid polygon).
    """
    pts = np.asarray(points, dtype=float)
    hull_xy = _hull_xy(pts)
    return [{"x_m": float(x), "y_m": float(y)} for x, y in hull_xy]


def _hull_xy(pts: np.ndarray) -> np.ndarray:
    """Return the convex-hull vertices (>=3) for an (N, 2) array of points."""
    try:  # prefer shapely (already in the crowd extra) for robust hull edge cases
        from shapely.geometry import MultiPoint

        hull = MultiPoint([(float(x), float(y)) for x, y in pts]).convex_hull
        coords = list(getattr(hull, "exterior", hull).coords)
        # shapely closes the ring (last == first); drop the duplicate closing vertex.
        if len(coords) >= 2 and coords[0] == coords[-1]:
            coords = coords[:-1]
        hull_xy = np.asarray(coords, dtype=float)
        if hull_xy.shape[0] >= 3:
            return hull_xy
        # Degenerate (point/line): fall through to the padding guarantee below.
    except Exception:  # shapely unavailable -> hand-rolled monotone-chain hull
        hull_xy = _monotone_chain(pts)
        if hull_xy.shape[0] >= 3:
            return hull_xy

    return _pad_to_three(pts)


def _monotone_chain(pts: np.ndarray) -> np.ndarray:
    """Andrew's monotone-chain convex hull (no shapely). Returns hull vertices (CCW)."""
    uniq = np.unique(pts, axis=0)
    if uniq.shape[0] < 3:
        return uniq
    order = np.lexsort((uniq[:, 1], uniq[:, 0]))
    p = uniq[order]

    def _cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[np.ndarray] = []
    for pt in p:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], pt) <= 0:
            lower.pop()
        lower.append(pt)
    upper: list[np.ndarray] = []
    for pt in p[::-1]:
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], pt) <= 0:
            upper.pop()
        upper.append(pt)
    hull = np.asarray(lower[:-1] + upper[:-1], dtype=float)
    return hull


def _pad_to_three(pts: np.ndarray) -> np.ndarray:
    """Guarantee a >=3-point polygon from a degenerate (point/line) cluster.

    A single point or collinear line is not a contract-valid polygon (minItems 3); pad
    with a tiny epsilon offset so the emitted zone is an honest (thin) triangle rather
    than dropping a real dwell cluster on a geometric technicality.
    """
    base = np.unique(pts, axis=0)
    centroid = pts.mean(axis=0)
    eps = 1e-6
    out = [tuple(centroid + [-eps, -eps]), tuple(centroid + [eps, -eps]), tuple(centroid + [0.0, eps])]
    # Prefer real cluster extent where available (keeps the polygon meaningful).
    if base.shape[0] >= 1:
        out[0] = tuple(base[0])
    if base.shape[0] >= 2:
        out[1] = tuple(base[-1])
    return np.asarray(out, dtype=float)


def extract_dwell_zones(trajectory: np.ndarray, lattice) -> list[dict]:
    """DBSCAN dwell zones over >DWELL_MIN_STEPS-consecutive near-still positions (CROWD-02).

    For each agent, find runs where ``|velocity| < V_STILL`` for STRICTLY MORE than
    ``DWELL_MIN_STEPS`` consecutive steps; collect those still positions; DBSCAN with
    ``eps = DBSCAN_EPS_CELLS * cell_size_m`` (dwell granularity = the shade-bay cell) and
    ``min_samples = DBSCAN_MIN_SAMPLES``; per non-noise cluster -> convex-hull polygon.
    """
    steps, n_agents, _ = trajectory.shape
    speed = np.linalg.norm(trajectory[:, :, _VX:_VY + 1], axis=2)  # (steps, agents)
    still = speed < V_STILL  # near-zero-velocity mask

    positions: list[tuple[float, float]] = []
    for a in range(n_agents):
        run = 0
        for t in range(steps):
            if still[t, a]:
                run += 1
            else:
                if run > DWELL_MIN_STEPS:  # STRICTLY more than 10 (CROWD-02)
                    positions.extend(_still_run_positions(trajectory, a, t - run, t))
                run = 0
        if run > DWELL_MIN_STEPS:  # trailing run (still at end of rollout)
            positions.extend(_still_run_positions(trajectory, a, steps - run, steps))

    if len(positions) < DBSCAN_MIN_SAMPLES:
        return []

    pts = np.asarray(positions, dtype=float)
    eps_m = DBSCAN_EPS_CELLS * lattice["cell_size_m"]  # eps tracks the master cell size
    labels = DBSCAN(eps=eps_m, min_samples=DBSCAN_MIN_SAMPLES).fit(pts).labels_

    zones: list[dict] = []
    for label in sorted(set(labels)):
        if label == -1:  # DBSCAN noise -> not a dwell zone
            continue
        cluster_pts = pts[labels == label]
        zones.append({"polygon": _convex_hull_polygon(cluster_pts)})
    return zones


def _still_run_positions(trajectory: np.ndarray, agent: int, t0: int, t1: int) -> list[tuple[float, float]]:
    """Positions of ``agent`` over the still run ``[t0, t1)`` (for the dwell clustering)."""
    return [
        (float(trajectory[t, agent, _X]), float(trajectory[t, agent, _Y]))
        for t in range(t0, t1)
    ]


def extract_flow_vectors(trajectory: np.ndarray, lattice) -> list[dict]:
    """origin->destination of the top-K MAJOR agent concentrations (CROWD-03).

    Group agents by their spawn concentration (DBSCAN over start positions — entrances
    are fixed, so spawn-side clusters ARE the major concentrations). For each major group
    (size >= ``FLOW_MIN_GROUP_FRAC * N``), emit ``origin`` = mean start, ``destination`` =
    mean end. Cap at ``FLOW_TOP_K`` by group size. Still (dwell) agents whose start ==
    end produce a degenerate zero-length vector and are excluded from major flows.

    The spawn-grouping ``eps`` is ``FLOW_DBSCAN_EPS_CELLS * lattice["cell_size_m"]`` — a
    PRINCIPLED, lattice-unit scale that tracks the master cell size (same discipline as the
    dwell path), NOT the old 0.25× spawn-spread heuristic that collapsed/merged groups on
    degenerate spawns (WR-05).
    """
    steps, n_agents, _ = trajectory.shape
    starts = trajectory[0, :, _X:_Y + 1]  # (agents, 2)
    ends = trajectory[steps - 1, :, _X:_Y + 1]

    # Exclude non-movers (dwell agents): their start == end -> not a flow.
    moved = np.linalg.norm(ends - starts, axis=1) > 1e-9
    if not moved.any():
        return []
    movers = np.where(moved)[0]

    eps_m = FLOW_DBSCAN_EPS_CELLS * lattice["cell_size_m"]  # lattice-unit scale (WR-05)
    labels = DBSCAN(eps=eps_m, min_samples=1).fit(starts[movers]).labels_

    min_group = max(1, int(np.ceil(FLOW_MIN_GROUP_FRAC * n_agents)))
    groups: list[tuple[int, np.ndarray]] = []
    for label in set(labels):
        members = movers[labels == label]
        if members.size >= min_group:
            groups.append((members.size, members))

    # Largest concentrations first, with a DETERMINISTIC tiebreaker on the group's mean spawn
    # position (WR-04): sorting on size ALONE leaves equal-size groups in `set(labels)` iteration
    # order — an implementation detail, not a guarantee — which sits on the byte-identical-artifact
    # determinism path (CROWD-01, test_same_seed_same_grid). Breaking ties on (-size, origin_x,
    # origin_y) makes the [:FLOW_TOP_K] truncation pick stably regardless of label numbering.
    def _flow_sort_key(g: tuple[int, np.ndarray]) -> tuple[float, float, float]:
        origin = starts[g[1]].mean(axis=0)
        return (float(-int(g[0])), float(origin[0]), float(origin[1]))

    groups.sort(key=_flow_sort_key)
    flows: list[dict] = []
    for _size, members in groups[:FLOW_TOP_K]:
        origin = starts[members].mean(axis=0)
        destination = ends[members].mean(axis=0)
        flows.append(
            {
                "origin": {"x_m": float(origin[0]), "y_m": float(origin[1])},
                "destination": {"x_m": float(destination[0]), "y_m": float(destination[1])},
            }
        )
    return flows


def build_crowd_grid(trajectory, lattice) -> dict:
    """Compose the PURE trajectory->crowd_grid transform (CROWD-02/03/04).

    Args:
        trajectory: ``steps x agents x {x, y, vx, vy}`` array-like (the rollout snapshot
            stack produced by ``rollout.py``; pure numpy here, no SB3).
        lattice: the master-lattice descriptor READ from ``utci_grid.json`` (the
            AUTHORITY — CONTRACT-03). Emitted verbatim into ``crowd_grid["lattice"]`` so
            it is byte-equal to ``utci_grid.lattice`` (XFN-04 seam).

    Returns:
        A contract-shaped ``crowd_grid`` dict (passes ``validate(d, "crowd_grid")``):
        ``schema_version``, ``crs``, ``lattice`` (the SAME object passed in), ``cells``,
        ``dwell_zones``, ``flow_vectors``. Not validated here — the orchestrator
        (Plan 04) validates-then-writes; this only shapes the artifact.
    """
    traj = np.asarray(trajectory, dtype=float)
    if traj.ndim != 3 or traj.shape[2] < 4:
        raise ValueError(f"trajectory must be steps x agents x >=4, got shape {traj.shape!r}")

    steps = traj.shape[0]
    terminal_positions = [
        (float(traj[steps - 1, a, _X]), float(traj[steps - 1, a, _Y]))
        for a in range(traj.shape[1])
    ]

    return {
        "schema_version": _SCHEMA_VERSION,
        "crs": _CRS,
        "lattice": lattice,  # SAME object read in — guarantees byte-equality (XFN-04)
        "cells": snap_to_lattice(terminal_positions, lattice),
        "dwell_zones": extract_dwell_zones(traj, lattice),
        "flow_vectors": extract_flow_vectors(traj, lattice),
    }
