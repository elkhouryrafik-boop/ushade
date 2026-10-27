"""Flow-field BFS routing tests — pure numpy, BASE (torch-free) suite (Plan 02.1-01).

The flow field is the V2 navigation-function prior the PPO policy FOLLOWS (RESEARCH §Q1):
a per-goal BFS wavefront over the 4-connected walkable lattice giving each cell its geodesic
distance (in cells) to the goal and a unit flow vector toward the goal. It is the ONLY net-new
idea in V2 that is fully deterministic + obstacle-aware + base-suite testable — it produces ZERO
learned behaviour and imports NO torch/SB3/gymnasium/scipy.

These tests assert the four must-have truths (plan frontmatter):
  * obstacle-awareness — no path through a blocker; ∞ on the unreachable side;
  * monotonicity — geodesic distance is non-increasing toward each goal over walkable cells;
  * unit-or-zero flow — every flow vector is (0,0) or an axis-aligned unit vector to a
    strictly-lower-distance neighbour, NEVER pointing into a blocked cell;
  * byte-determinism — same (blocked, cols, rows, goal) ⇒ byte-identical arrays (pinned BFS
    neighbour order, RESEARCH A10);
plus build_flow_fields over all goals, and a STATIC torch-free guard (the module text must not
contain torch/stable_baselines3/gymnasium/scipy).

All tests run under ``pytest -q -m "not crowd"`` — pure numpy, no crowd extra.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

# conftest_crowd is imported EXPLICITLY (it is not auto-loaded — see its docstring).
from conftest_crowd import blocked_wall_lattice

from crowd.flowfield import bfs_distance, build_flow_fields, flow_dir

_NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def test_no_path_through_blocker():
    """A wall with NO gap makes the far side unreachable; flow never points INTO a blocker."""
    L = blocked_wall_lattice()
    cols, rows, wall_col = L["cols"], L["rows"], L["wall_col"]
    # Seal the gap → a complete wall splitting the lattice.
    blocked = {(wall_col, r) for r in range(rows)}
    goal_near = L["goal_near"]  # left of the wall

    dist = bfs_distance(blocked, cols, rows, goal_near)

    # Every cell strictly RIGHT of the wall is unreachable from a left-side goal.
    for c in range(wall_col + 1, cols):
        for r in range(rows):
            assert not np.isfinite(dist[c, r]), f"cell ({c},{r}) should be unreachable past the sealed wall"
    # The wall cells themselves are blocked → ∞.
    for r in range(rows):
        assert not np.isfinite(dist[wall_col, r]), f"blocked wall cell ({wall_col},{r}) must be ∞"

    # No flow vector points INTO a blocked cell.
    flow = flow_dir(dist)
    for c in range(cols):
        for r in range(rows):
            dx, dy = flow[c, r]
            if dx == 0.0 and dy == 0.0:
                continue
            nc, nr = c + int(dx), r + int(dy)
            assert (nc, nr) not in blocked, f"flow at ({c},{r}) points into blocked ({nc},{nr})"


def test_bfs_distance_monotone_to_goal():
    """dist[goal]==0, blocked cells ∞, and stepping toward the goal is non-increasing."""
    L = blocked_wall_lattice()
    cols, rows = L["cols"], L["rows"]
    blocked = L["blocked"]
    goal = L["goal_far"]

    dist = bfs_distance(blocked, cols, rows, goal)

    assert dist[goal] == 0.0
    for c, r in blocked:
        assert not np.isfinite(dist[c, r]), f"blocked ({c},{r}) must be ∞"

    # Monotonicity: every finite cell has SOME 4-neighbour with dist exactly one less
    # (the BFS predecessor) — i.e. a strictly-descending path to the goal exists.
    for c in range(cols):
        for r in range(rows):
            d = dist[c, r]
            if not np.isfinite(d) or d == 0.0:
                continue
            has_lower = any(
                0 <= c + dc < cols
                and 0 <= r + dr < rows
                and np.isfinite(dist[c + dc, r + dr])
                and dist[c + dc, r + dr] == d - 1.0
                for dc, dr in _NEIGHBOURS
            )
            assert has_lower, f"cell ({c},{r}) dist={d} has no descending neighbour toward goal"


def test_flow_dir_is_unit_or_zero():
    """Every flow vector is (0,0) or an axis-aligned unit vector to a strictly-lower neighbour."""
    L = blocked_wall_lattice()
    cols, rows = L["cols"], L["rows"]
    blocked = L["blocked"]
    goal = L["goal_far"]

    dist = bfs_distance(blocked, cols, rows, goal)
    flow = flow_dir(dist)
    assert flow.shape == (cols, rows, 2)

    for c in range(cols):
        for r in range(rows):
            dx, dy = float(flow[c, r, 0]), float(flow[c, r, 1])
            # axis-aligned: exactly one of dx,dy is ±1 (or both zero).
            assert (dx, dy) == (0.0, 0.0) or (abs(dx) + abs(dy) == 1.0 and dx in (-1.0, 0.0, 1.0) and dy in (-1.0, 0.0, 1.0)), (
                f"flow at ({c},{r}) = {(dx, dy)} is not unit-or-zero"
            )
            if (dx, dy) != (0.0, 0.0):
                nc, nr = c + int(dx), r + int(dy)
                assert dist[nc, nr] < dist[c, r], f"flow at ({c},{r}) does not descend"
    # Goal cell has zero flow.
    assert tuple(flow[goal[0], goal[1]]) == (0.0, 0.0)


def test_flow_field_deterministic():
    """Building the field twice on the same input yields byte-identical arrays (A10)."""
    L = blocked_wall_lattice()
    cols, rows = L["cols"], L["rows"]
    blocked = L["blocked"]
    goal = L["goal_far"]

    d1 = bfs_distance(blocked, cols, rows, goal)
    d2 = bfs_distance(set(blocked), cols, rows, goal)
    f1 = flow_dir(d1)
    f2 = flow_dir(d2)

    assert hashlib.sha256(d1.tobytes()).hexdigest() == hashlib.sha256(d2.tobytes()).hexdigest()
    assert hashlib.sha256(f1.tobytes()).hexdigest() == hashlib.sha256(f2.tobytes()).hexdigest()


def test_build_flow_fields_all_goals():
    """build_flow_fields returns a per-goal dict of (dist, flow_dir) with correct shapes."""
    L = blocked_wall_lattice()
    cols, rows = L["cols"], L["rows"]
    blocked = L["blocked"]
    goal_cells = [L["goal_near"], L["goal_far"]]

    fields = build_flow_fields(blocked, cols, rows, goal_cells)

    assert set(fields.keys()) == {0, 1}
    for idx, goal in enumerate(goal_cells):
        dist, flow = fields[idx]
        assert dist.shape == (cols, rows)
        assert flow.shape == (cols, rows, 2)
        assert dist[goal] == 0.0


def test_blocked_goal_is_all_infinite():
    """A goal cell that is itself blocked → an all-∞ distance field (edge case)."""
    L = blocked_wall_lattice()
    cols, rows = L["cols"], L["rows"]
    blocked = L["blocked"]
    blocked_goal = (L["wall_col"], 0)  # on the wall → blocked
    assert blocked_goal in blocked

    dist = bfs_distance(blocked, cols, rows, blocked_goal)
    assert not np.isfinite(dist).any(), "a blocked goal must yield an all-∞ field"
    flow = flow_dir(dist)
    assert (flow == 0.0).all(), "all-∞ field must give all-zero flow"


def test_flowfield_module_is_torch_free():
    """STATIC guard: flowfield.py must NOT reference torch/SB3/gymnasium/scipy (base-suite purity)."""
    src = Path(__file__).resolve().parents[1] / "src" / "crowd" / "flowfield.py"
    text = src.read_text(encoding="utf-8")
    for token in ("torch", "stable_baselines3", "gymnasium", "scipy"):
        assert token not in text, f"forbidden token {token!r} found in flowfield.py (must stay pure-numpy)"
