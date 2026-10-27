"""Torch-free test scaffolding for the Phase-2b crowd suite (NO SB3/torch import).

Like ``conftest_climate.py``, this module is imported EXPLICITLY by the grid/orchestrator
tests — it is NOT auto-loaded (pytest only auto-loads ``conftest.py``). It exists so the
PURE downstream transforms (grid.py: lattice snap + DBSCAN dwell_zones + flow_vectors,
Plan 03) and the orchestrator (Plan 04) can be unit-tested with a KNOWN synthetic
trajectory and a deterministic fake policy, with NO real PPO/torch/SB3 inference.

Provides:

* ``synthetic_trajectory()`` — a pure-numpy trajectory shaped ``steps × agents × {x,y,vx,vy}``
  with deliberately KNOWN structure so the grid transforms have a ground truth:
    - a DWELL cluster: ≥ DBSCAN_MIN_SAMPLES agents held near-zero velocity
      (``|v| < V_STILL``) for STRICTLY MORE than DWELL_MIN_STEPS consecutive steps, all
      within one lattice cell → a dwell zone MUST emerge (CROWD-02).
    - ≥ 2 MAJOR flow groups with distinct spawn→sink mean positions → ≥2 flow vectors
      MUST emerge (CROWD-03).
* ``tiny_lattice()`` — a small master-lattice descriptor (matches ``_defs/lattice.schema.json``),
  the snap authority for the grid tests (CROWD-04). cell_size_m = 6.0 (Phase-2a master).
* ``fake_policy`` — a deterministic ``predict(obs, deterministic=True) -> (action, None)``
  callable (no torch) the Plan-04 orchestrator integration test injects in place of SB3.

karpathy: plain numpy, no fixture-factory framework, no SB3/torch anywhere in this file.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from crowd.constants import (
    DBSCAN_MIN_SAMPLES,
    DWELL_MIN_STEPS,
    SIM_STEPS,
    V_STILL,
)

# Trajectory axis layout: [x, y, vx, vy]. The grid transform consumes exactly this.
_FIELDS = 4


def synthetic_trajectory(
    *,
    steps: int = SIM_STEPS,
    dwell_agents: int = DBSCAN_MIN_SAMPLES + 2,  # comfortably above the min-samples floor
    flow_agents_per_group: int = 6,
) -> np.ndarray:
    """Build a deterministic ``steps × agents × {x,y,vx,vy}`` trajectory with KNOWN structure.

    Structure (so the pure grid transforms have a verifiable ground truth):

    * **Dwell cluster** (CROWD-02): ``dwell_agents`` (≥ DBSCAN_MIN_SAMPLES) agents parked
      within a single ~6 m cell around (30, 30) m, velocity 0 for the WHOLE rollout
      (``|v| = 0 < V_STILL`` for far more than DWELL_MIN_STEPS consecutive steps).
    * **Two flow groups** (CROWD-03): group A travels SW→centre (spawn ~(6,6) →
      sink ~(54,54)); group B travels NE→SW (spawn ~(108,108) → sink ~(54,6)). Distinct
      origins and destinations → two clean flow vectors.

    All positions are in metres on the ``tiny_lattice()`` extent. Returns a contiguous
    float64 array; agents are ordered [dwell..., groupA..., groupB...].
    """
    rng = np.random.default_rng(0)  # local, deterministic — NOT the env/policy seed

    n_dwell = int(dwell_agents)
    n_flow = int(flow_agents_per_group)
    n_agents = n_dwell + 2 * n_flow
    traj = np.zeros((steps, n_agents, _FIELDS), dtype=np.float64)

    # --- Dwell cluster: still agents inside one ~6 m cell around (30, 30) m. -------------
    dwell_centre = np.array([30.0, 30.0])
    dwell_xy = dwell_centre + rng.uniform(-1.0, 1.0, size=(n_dwell, 2))  # within ~1 cell
    for s in range(steps):
        traj[s, :n_dwell, 0:2] = dwell_xy
        traj[s, :n_dwell, 2:4] = 0.0  # |v| = 0 < V_STILL, every step (a dwell MUST emerge)

    # --- Flow group A: spawn ~(6,6) → sink ~(54,54), linear interpolation. ---------------
    def _linear_group(start, end, base_slot):
        start = np.asarray(start, dtype=float)
        end = np.asarray(end, dtype=float)
        spawn = start + rng.uniform(-2.0, 2.0, size=(n_flow, 2))
        sink = end + rng.uniform(-2.0, 2.0, size=(n_flow, 2))
        for s in range(steps):
            t = s / max(1, steps - 1)
            pos = (1.0 - t) * spawn + t * sink
            traj[s, base_slot : base_slot + n_flow, 0:2] = pos
            # velocity = per-step displacement (moving, so |v| > V_STILL → not a dwell).
            step_vec = (sink - spawn) / max(1, steps - 1)
            traj[s, base_slot : base_slot + n_flow, 2:4] = step_vec

    _linear_group((6.0, 6.0), (54.0, 54.0), n_dwell)
    _linear_group((108.0, 108.0), (54.0, 6.0), n_dwell + n_flow)

    return traj


def tiny_lattice() -> dict:
    """A small master-lattice descriptor (the snap authority for grid tests, CROWD-04).

    cell_size_m = 6.0 matches the Phase-2a master lattice; cols/rows span the synthetic
    trajectory extent (0..120 m). Matches ``_defs/lattice.schema.json`` (origin/cell/cols/rows).
    """
    return {
        "origin_x_m": 0.0,
        "origin_y_m": 0.0,
        "cell_size_m": 6.0,
        "cols": 20,
        "rows": 20,
    }


def fake_policy(action=(0.0, 0.0)):
    """Return a deterministic SB3-shaped policy stand-in (no torch).

    The returned object has ``predict(obs, deterministic=True) -> (np.ndarray, None)`` — the
    exact call surface ``rollout`` exercises — so the Plan-04 orchestrator integration test
    can inject it in place of ``PPO.load(...)`` and stay torch-free.
    """

    class _FakePolicy:
        def __init__(self, act):
            self._act = np.asarray(act, dtype=np.float32)

        def predict(self, obs, deterministic=True):  # noqa: ARG002 - mirrors SB3 signature
            return self._act.copy(), None

    return _FakePolicy(action)


# --------------------------------------------------------------------------- #
# pytest fixtures (thin wrappers so tests can request them by name)
# --------------------------------------------------------------------------- #
@pytest.fixture
def synthetic_traj() -> np.ndarray:
    """A fresh known-structure synthetic trajectory (steps × agents × 4)."""
    return synthetic_trajectory()


@pytest.fixture
def crowd_lattice() -> dict:
    """The tiny master-lattice snap authority for grid tests."""
    return tiny_lattice()


# --------------------------------------------------------------------------- #
# Phase 2.1 flow-field ground truth (pure numpy — NO SB3/torch/scipy here)
# --------------------------------------------------------------------------- #
def blocked_wall_lattice() -> dict:
    """A small obstacle lattice — the ground truth for the flow-field tests (Plan 02.1-01).

    A ``cols×rows`` walkable grid with a VERTICAL blocker wall at ``col == wall_col`` that
    splits the lattice left↔right, EXCEPT a single one-cell gap at ``gap_row``. So:

    * Cells on the side WITHOUT the goal are reachable ONLY through the gap (the BFS must
      route around the wall — there is exactly one corridor).
    * If the gap is closed, the far side is unreachable (BFS distance == ∞) — used by the
      blocked-goal / no-path-through-blocker tests.

    Returns ``{cols, rows, wall_col, gap_row, blocked, goal_near, goal_far}`` where ``blocked``
    is a ``set[(col,row)]`` (the env/flow-field convention: ``(pos-origin)//cell_size_m`` →
    ``(col,row)``, cols-major). Goals sit on opposite sides of the wall.
    """
    cols, rows = 20, 20
    wall_col = 10
    gap_row = 9
    blocked: set[tuple[int, int]] = {
        (wall_col, r) for r in range(rows) if r != gap_row
    }
    return {
        "cols": cols,
        "rows": rows,
        "wall_col": wall_col,
        "gap_row": gap_row,
        "blocked": blocked,
        "goal_near": (3, 3),       # left of the wall
        "goal_far": (16, 16),      # right of the wall — reachable only via the gap
    }


@pytest.fixture
def flow_lattice() -> dict:
    """The blocker-wall lattice ground truth for the flow-field obstacle/monotonicity tests."""
    return blocked_wall_lattice()


# --------------------------------------------------------------------------- #
# Phase 2.1 site loader ground truth (Plan 02.1-02 — site.py)
# --------------------------------------------------------------------------- #
def mini_site() -> dict:
    """A tiny hand-built site (geojson dicts + lattice) — ground truth for site.py tests.

    Self-contained so the blocked/clear-cell assertions never need the full real geojson
    (one full-geojson load lives in its own test). Geometry is laid out in WGS84 near
    Parc del Fòrum so :func:`crs.to_utm31n` projects it into sane UTM31N metres, then the
    lattice is sized to span that projected footprint at 6 m/cell.

    Layout (lon/lat, hand-chosen so the rasterisation has a KNOWN truth):

    * boundary: a rectangle enclosing the whole mini-site.
    * one blocker: a small square building INSIDE the boundary (cells over it MUST be blocked).
    * two stages: ``S_main`` (capacity_class ``main``) and ``S_elec`` (``electronic``).
    * two entrances: ``ENTRANCE A (general)`` and ``ENTRANCE B (VIP)`` — ordered [A, B].

    Returns ``{festival, boundary, nogo, lattice, inside_clear_ll, inside_blocker_ll}`` where
    the two ``*_ll`` points are a (lon, lat) KNOWN to be in open ground vs inside the blocker —
    the ground truth for ``test_blocked_*``.
    """
    # A small WGS84 window near Parc del Fòrum (Barcelona). ~ (2.224..2.230 E, 41.408..41.412 N).
    lon0, lat0 = 2.2240, 41.4080
    lon1, lat1 = 2.2300, 41.4120

    def _ring(a, b, c, d):
        # closed exterior ring (lon, lat) — rectangle a(SW) b(SE) c(NE) d(NW)
        return [list(a), list(b), list(c), list(d), list(a)]

    boundary_ring = _ring(
        (lon0, lat0), (lon1, lat0), (lon1, lat1), (lon0, lat1)
    )
    # Blocker: a small square building near the centre.
    bl0, bla0 = 2.2265, 41.4095
    bl1, bla1 = 2.2275, 41.4101
    blocker_ring = _ring(
        (bl0, bla0), (bl1, bla0), (bl1, bla1), (bl0, bla1)
    )

    festival = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "S_main", "layer": "stage", "kind": "stage",
                               "capacity_class": "main"},
                "geometry": {"type": "Point", "coordinates": [2.2250, 41.4088]},
            },
            {
                "type": "Feature",
                "properties": {"name": "S_elec", "layer": "stage", "kind": "stage",
                               "capacity_class": "electronic"},
                "geometry": {"type": "Point", "coordinates": [2.2288, 41.4112]},
            },
            {
                "type": "Feature",
                "properties": {"name": "ENTRANCE A (general)", "layer": "access",
                               "kind": "entrance", "capacity_class": "main"},
                "geometry": {"type": "Point", "coordinates": [2.2243, 41.4082]},
            },
            {
                "type": "Feature",
                "properties": {"name": "ENTRANCE B (VIP)", "layer": "amenity",
                               "kind": "entrance"},
                "geometry": {"type": "Point", "coordinates": [2.2296, 41.4117]},
            },
        ],
    }
    boundary = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"name": "site"},
             "geometry": {"type": "Polygon", "coordinates": [boundary_ring]}},
        ],
    }
    nogo = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"name": "building"},
             "geometry": {"type": "Polygon", "coordinates": [blocker_ring]}},
        ],
    }

    # Lattice sized to the projected boundary footprint at 6 m/cell, with a small margin.
    from crs.crs import to_utm31n
    xs, ys = [], []
    for lon, lat in boundary_ring:
        x, y = to_utm31n(lon, lat)
        xs.append(x)
        ys.append(y)
    cell = 6.0
    ox = min(xs) - cell  # one-cell margin so boundary edge cells are well-defined
    oy = min(ys) - cell
    cols = int((max(xs) - ox) / cell) + 2
    rows = int((max(ys) - oy) / cell) + 2
    lattice = {
        "origin_x_m": ox,
        "origin_y_m": oy,
        "cell_size_m": cell,
        "cols": cols,
        "rows": rows,
    }

    return {
        "festival": festival,
        "boundary": boundary,
        "nogo": nogo,
        "lattice": lattice,
        # A point KNOWN to be in open festival ground (inside boundary, off the blocker).
        "inside_clear_ll": (2.2250, 41.4088),
        # A point KNOWN to be inside the blocker building.
        "inside_blocker_ll": (2.2270, 41.4098),
    }


@pytest.fixture
def mini_site_fixture() -> dict:
    """The hand-built tiny site (boundary + one blocker + 2 entrances + 2 stages) for site.py."""
    return mini_site()


# --------------------------------------------------------------------------- #
# Phase 2.1 REAL-SITE env fixture (Plan 02.1-04 stage-reach gate + Plan 06)
# --------------------------------------------------------------------------- #
#: The committed REAL lattice + the three committed geojson layers (INPUTS, 259d3fb). The
#: stage-reach gate (and Plan 06's site-native run) build the full-scale FestivalEnv from
#: exactly these so the gate measures the policy on the geometry the runtime stage will use.
_REPO_ROOT_CROWD = Path(__file__).resolve().parent.parent
_UTCI_GRID_PATH = _REPO_ROOT_CROWD / "projects" / "primavera-demo" / "utci_grid.json"


def build_real_site_env(*, n_agents: int, seed=None):
    """Build the FULL real-site ``FestivalEnv`` from the committed geojson + utci lattice.

    This is the env the V2 stage-reach gate rolls the committed ``policy.zip`` through and the
    geometry Plan 06's site-native ``run_crowd_stage`` will use: the real 139×153 @ 6 m lattice
    (READ from ``projects/primavera-demo/utci_grid.json`` — CONTRACT-03, never re-derived), the
    19 real stages + 2 real entrances + 13 impassable blockers (``load_site_geometry`` on the
    committed layer files), demand-weighted goals for the documented Saturday-22:00 slice, and
    seeded staggered arrivals. ``n_agents`` is driven by the caller (the gate uses
    ``PRIMAVERA_DAILY_CAPACITY // AGENT_DIVISOR = 650``). Imports the gymnasium/numpy env INSIDE
    the function so this module stays torch/gymnasium-free at import (crowd-marked usage only).
    """
    from pathlib import Path as _P  # local, keep module-top torch/gym-free

    from crowd.constants import SEED as _SEED
    from crowd.demand import goal_weights_for_slice, load_set_times
    from crowd.env import FestivalEnv
    from crowd.site import load_site_geometry

    use_seed = _SEED if seed is None else int(seed)
    utci = json.loads(_UTCI_GRID_PATH.read_text(encoding="utf-8"))
    lattice = utci["lattice"]  # the READ master lattice (139×153 @ 6 m)

    geo = load_site_geometry(lattice=lattice)  # real committed geojson defaults

    # Demand-weighted goals for the committed representative slice (capacity-class × headliner
    # popularity). Falls back to the capacity-class floors if the slice is empty. Refines demand;
    # it does NOT gate acceptance (threat T-02.1-04) — a wrong weight cannot make the gate pass.
    table = load_set_times()
    slice_meta = table["_meta"]["default_slice"]
    names = [m["name"] for m in geo["stage_meta"]]
    classes = [m["class"] for m in geo["stage_meta"]]
    geo["goal_weights"] = list(
        goal_weights_for_slice(
            names, classes,
            day=slice_meta["day"], hour_block=slice_meta["hour_block"], table=table,
        )
    )

    return FestivalEnv(
        lattice=lattice,
        utci_cells=utci["cells"],
        n_agents=int(n_agents),
        seed=use_seed,
        site_geometry=geo,
    )


@pytest.fixture
def real_site_env():
    """Factory fixture → the full real-site FestivalEnv (committed geojson + utci lattice).

    Returns the ``build_real_site_env`` callable so a test can pick ``n_agents`` (the stage-reach
    gate uses N=650). Crowd-marked usage: only called under ``-m crowd`` (it imports the env)."""
    return build_real_site_env


# Sanity self-checks at import (cheap; guard the fixture invariants the grid tests rely on).
def _assert_fixture_invariants() -> None:
    t = synthetic_trajectory()
    assert t.ndim == 3 and t.shape[2] == _FIELDS, f"bad trajectory shape {t.shape!r}"
    # The dwell agents are still (|v| < V_STILL) for more than DWELL_MIN_STEPS steps.
    dwell_v = np.linalg.norm(t[: DWELL_MIN_STEPS + 5, :DBSCAN_MIN_SAMPLES, 2:4], axis=2)
    assert (dwell_v < V_STILL).all(), "dwell agents are not still enough for a dwell zone"


_assert_fixture_invariants()
