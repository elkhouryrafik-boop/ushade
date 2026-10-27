"""Pure-numpy flow-field (navigation-function) routing — the V2 deterministic global router.

This module is the ONE net-new idea in the V2 site-native crowd model (RESEARCH §Q1). It fixes
the V1 out-of-distribution failure (raw, unbounded ``goal_dx/dy`` → 0.8% stage-reach on the real
800 m site) by precomputing, per goal, a BFS wavefront over the 4-connected WALKABLE lattice:

* :func:`bfs_distance` — geodesic distance in CELLS from a goal cell over walkable cells
  (``∞`` for blocked / unreachable cells), so the cue is obstacle-aware (no local-minima trap a
  raw bearing has) and the agent's GOAL HEADING becomes a precomputed unit vector.
* :func:`flow_dir` — the per-cell unit flow vector toward the lowest-distance 4-neighbour (the
  routing gradient the policy FOLLOWS); ``(0,0)`` at the goal, blocked, and unreachable cells.
* :func:`build_flow_fields` — builds (and returns) the per-goal cache once.

PURITY CONTRACT — this module is PURE ``numpy`` + ``collections.deque``. It imports NONE of the
heavy crowd-extra / ML / sci-stack libraries (the deep-RL framework, its policy backend, the env
API, or the scientific-computing fast-marching lib): a static guard in ``tests/test_flowfield.py``
greps this file's text for those forbidden tokens and fails if any appears anywhere — prose
included — so the name list is kept in the TEST, not here. The flow field is deterministic global
ROUTING, not learned behaviour; the PPO policy only ever learns LOCAL collision/congestion physics.

DETERMINISM (RESEARCH A10): the BFS neighbour-visit order is PINNED to
``((1,0),(-1,0),(0,1),(0,-1))``, so the wavefront — and therefore both output arrays — are
byte-identical given the same ``(blocked, cols, rows, goal_cell)``. Asserted by
``test_flow_field_deterministic``.

LATTICE CONVENTION: cells are ``(col, row)`` integer indices (cols-major), matching
``env.py``'s ``(pos - origin) // cell_size_m`` mapping. Arrays are shaped ``(cols, rows)``
(distance) and ``(cols, rows, 2)`` (flow, ``[dcol, drow]``).

COST / CACHE (RESEARCH §Q1): BFS is O(cells) per goal; the real lattice is 139×153 = 21,267
cells × 19 goals ≈ 0.4 M cell-visits → sub-second. The in-memory cache is ~4 MB (one float32
``(cols,rows)`` distance + one float32 ``(cols,rows,2)`` flow per goal × 19 goals); no disk /
network egress, no new dependency. ``numpy`` stays ``1.26.*``.
"""

from __future__ import annotations

from collections import deque

import numpy as np

#: PINNED 4-connected neighbour-visit order → byte-deterministic BFS (RESEARCH A10).
_NEIGHBOURS: tuple[tuple[int, int], ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))


def bfs_distance(
    blocked: set[tuple[int, int]],
    cols: int,
    rows: int,
    goal_cell: tuple[int, int],
) -> np.ndarray:
    """4-connected BFS wavefront from ``goal_cell`` over walkable cells → distance in CELLS.

    Args:
        blocked: set of ``(col, row)`` cells that are impassable (outside boundary ∪ inside a
            blocker polygon — rasterised upstream).
        cols, rows: lattice dimensions (the array is shaped ``(cols, rows)``).
        goal_cell: the ``(col, row)`` target cell the wavefront expands FROM.

    Returns:
        A ``float32`` ``(cols, rows)`` array: geodesic distance in cells to ``goal_cell`` over
        walkable cells; ``np.inf`` for blocked or unreachable cells. If ``goal_cell`` is itself
        blocked (or out of bounds), the field is ALL ``∞``.

    The neighbour-visit order is PINNED (:data:`_NEIGHBOURS`) so the result is byte-deterministic.
    """
    dist = np.full((cols, rows), np.inf, dtype=np.float32)
    gc, gr = goal_cell
    # Out-of-bounds or blocked goal → unreachable everywhere (all-∞).
    if not (0 <= gc < cols and 0 <= gr < rows) or (gc, gr) in blocked:
        return dist

    dist[gc, gr] = 0.0
    q: deque[tuple[int, int]] = deque([(gc, gr)])
    while q:
        c, r = q.popleft()
        d_next = dist[c, r] + 1.0
        for dc, dr in _NEIGHBOURS:  # pinned order → deterministic wavefront
            nc, nr = c + dc, r + dr
            if (
                0 <= nc < cols
                and 0 <= nr < rows
                and (nc, nr) not in blocked
                and not np.isfinite(dist[nc, nr])
            ):
                dist[nc, nr] = d_next
                q.append((nc, nr))
    return dist


def flow_dir(dist: np.ndarray) -> np.ndarray:
    """Per-cell unit flow vector toward the lowest-distance 4-neighbour (the routing gradient).

    Args:
        dist: a ``(cols, rows)`` BFS distance field from :func:`bfs_distance`.

    Returns:
        A ``float32`` ``(cols, rows, 2)`` array of ``[dcol, drow]`` unit vectors. Each cell holds
        an axis-aligned unit vector pointing to the strictly-lower-distance 4-neighbour, or
        ``(0, 0)`` at the goal (dist 0), at blocked cells, and at unreachable cells (``∞``).
        Vectors NEVER point into a blocked / unreachable / higher-distance neighbour.

    The neighbour scan order is PINNED (:data:`_NEIGHBOURS`); on ties the first-listed lower
    neighbour wins → deterministic.
    """
    cols, rows = dist.shape
    out = np.zeros((cols, rows, 2), dtype=np.float32)
    for c in range(cols):
        for r in range(rows):
            here = dist[c, r]
            if not np.isfinite(here) or here == 0.0:
                continue  # blocked / unreachable / goal → (0,0)
            best: tuple[int, int] | None = None
            best_val = here
            for dc, dr in _NEIGHBOURS:
                nc, nr = c + dc, r + dr
                if 0 <= nc < cols and 0 <= nr < rows and dist[nc, nr] < best_val:
                    best_val = dist[nc, nr]
                    best = (dc, dr)
            if best is not None:  # axis-aligned step → already a unit vector
                out[c, r, 0] = float(best[0])
                out[c, r, 1] = float(best[1])
    return out


def build_flow_fields(
    blocked: set[tuple[int, int]],
    cols: int,
    rows: int,
    goal_cells: list[tuple[int, int]],
) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """Build the per-goal flow-field cache once: ``{goal_idx: (dist, flow_dir)}``.

    Args:
        blocked: impassable ``(col, row)`` cells (shared across all goals).
        cols, rows: lattice dimensions.
        goal_cells: ordered list of goal ``(col, row)`` cells; the dict key is the list index.

    Returns:
        A dict keyed by ``goal_idx`` → ``(dist, flow)`` where ``dist`` is ``(cols, rows)`` and
        ``flow`` is ``(cols, rows, 2)``. Built once and returned for in-memory caching by the env
        (~4 MB for the real 19-goal / 21,267-cell lattice; sub-second; no new dependency).
    """
    fields: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for idx, goal in enumerate(goal_cells):
        dist = bfs_distance(blocked, cols, rows, goal)
        fields[idx] = (dist, flow_dir(dist))
    return fields
