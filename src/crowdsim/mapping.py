"""Festival layer → JuPedSim primitive spec (CROWD-07, RESEARCH Pattern 2).

:func:`build_primitive_spec` reuses the FROZEN festival layer VERBATIM — ``load_site_geometry``
(19 real stages + 2 entrances + the boundary/blocker rings) and ``goal_weights_for_slice`` (the
demand-weighted popularity split for the representative slice) — and maps it onto a PLAIN-DATA spec
dict the simulation builder (``simulation.py``) turns into JuPedSim ``Simulation``/``Journey``/
``Transition`` objects. This module imports NO jupedsim wheel: the jupedsim objects are constructed
from this spec in ``simulation.py``, so the mapping stays unit-testable without the engine (the
lazy-import quarantine; mirror of ``crowd.crowd::_default_env_factory``).

Mapping table (RESEARCH Pattern 2):
  * ``geo["entrances_utm"]`` A/B → agent sources, split by ``SPAWN_FRAC_GATE_A`` (gate A gets
    ``round(n · SPAWN_FRAC_GATE_A)``, gate B the remainder); each source is a small ``SPAWN_JITTER_M``
    spawn polygon (square patch) around the entrance point.
  * walkable area = boundary rings − blocker rings → ``boundary_rings`` + ``blocker_rings`` (reuse
    the FROZEN ``site._polygon_rings_to_utm`` ring builder; NEVER hand-roll geometry). The robust
    shapely ``boundary.difference(blockers)`` set-op (which yields a VALID walkable polygon even when
    blockers straddle the boundary edge — a naive ``Polygon(exterior, holes=blockers)`` is invalid
    there) is done in ``simulation.py`` from these plain rings, matching how the FROZEN
    ``site.build_blocked_cells`` rasterises the SAME boundary − blocker set.
  * ``geo["stages_utm"]`` + ``geo["goal_weights"]`` → carried through for the round-robin transition
    + waypoint stages, with ``reach_radius_m = REACH_RADIUS_M``.

All scales are NAMED constants from ``crowd.constants`` (never inline literals — anti-tuning).
``n_agents`` is passed by the caller (``simulation.py``: the shell computes ``n = capacity //
AGENT_DIVISOR``); it is NOT recomputed from capacity here.
"""

from __future__ import annotations

from crowd.constants import REACH_RADIUS_M, SPAWN_FRAC_GATE_A, SPAWN_JITTER_M


def _spawn_patch(center: tuple[float, float], half: float) -> list[tuple[float, float]]:
    """A small square spawn ring (CCW) of half-width ``half`` metres around ``center`` (UTM31N).

    A plain coordinate ring (not a shapely object) — ``simulation.py`` builds the shapely Polygon
    and hands it to ``distribute_by_number``. The patch is the gate's spawn region; agents are
    distributed inside it (seeded), so it must be wide enough to hold the gate's agent share.
    """
    cx, cy = center
    return [
        (cx - half, cy - half),
        (cx + half, cy - half),
        (cx + half, cy + half),
        (cx - half, cy + half),
    ]


def _walkable_rings(*, lattice):
    """Collect the boundary + blocker rings (UTM31N metres) for the walkable-area set-op.

    Reuses the FROZEN ``site._polygon_rings_to_utm`` ring builder verbatim (boundary geojson rings,
    blocker geojson rings) — the SAME geometry ``build_blocked_cells`` rasterises, so the JuPedSim
    walkable area (boundary − blockers, assembled in ``simulation.py``) matches the lattice
    blocked-cell set. Lazy-imports the site loader + geojson defaults INSIDE the function (no
    jupedsim/shapely at module top).

    Returns ``(boundary_rings, blocker_rings)`` — each a list of UTM rings. ``simulation.py`` does
    the robust ``unary_union(boundary).difference(unary_union(blockers))`` (a naive
    ``Polygon(exterior, holes=blockers)`` is INVALID where a blocker straddles the boundary edge).
    """
    from crowd.site import (
        DEFAULT_BOUNDARY_PATH,
        DEFAULT_NOGO_PATH,
        _load_geojson,
        _polygon_rings_to_utm,
    )

    boundary_geo = _load_geojson(None, DEFAULT_BOUNDARY_PATH)
    nogo_geo = _load_geojson(None, DEFAULT_NOGO_PATH)

    boundary_rings: list[list[tuple[float, float]]] = []
    for f in boundary_geo["features"]:
        boundary_rings.extend(_polygon_rings_to_utm(f["geometry"]))
    if not boundary_rings:
        raise ValueError("boundary geojson produced no UTM rings (site geometry missing)")

    blocker_rings: list[list[tuple[float, float]]] = []
    for f in nogo_geo["features"]:
        blocker_rings.extend(_polygon_rings_to_utm(f["geometry"]))

    return boundary_rings, blocker_rings


def build_primitive_spec(*, lattice, n_agents: int = 1) -> dict:
    """Map the FROZEN festival layer onto a plain-data JuPedSim primitive spec.

    Lazy-imports ``load_site_geometry`` + ``goal_weights_for_slice`` + ``load_set_times`` INSIDE the
    function (mirror ``crowd.crowd::_default_env_factory``) and reuses the EXACT demand-weighting
    block, then maps ``geo`` onto a plain-data dict. No jupedsim import — the engine objects are
    built from this spec in ``simulation.py``.

    Args:
        lattice: the READ master lattice descriptor (from ``utci_grid.json``; CONTRACT-03).
        n_agents: total agents to spawn (the shell's ``capacity // AGENT_DIVISOR``), split A/B by
            ``SPAWN_FRAC_GATE_A``.

    Returns:
        A dict with: ``boundary_rings`` (list of UTM rings), ``blocker_rings`` (list of UTM rings),
        ``sources`` (``[(spawn_ring, count), ...]`` per gate, A then B),
        ``stages_utm`` (19 stage centres), ``goal_weights`` (demand-weighted, same order),
        ``reach_radius_m`` (= ``REACH_RADIUS_M``).
    """
    from crowd.demand import goal_weights_for_slice, load_set_times
    from crowd.site import load_site_geometry

    geo = load_site_geometry(lattice=lattice)  # FROZEN — reuse verbatim

    # Demand-weighted goals for the committed representative slice (EXACT _default_env_factory block).
    table = load_set_times()
    slice_meta = table["_meta"]["default_slice"]
    names = [m["name"] for m in geo["stage_meta"]]
    classes = [m["class"] for m in geo["stage_meta"]]
    goal_weights = list(
        goal_weights_for_slice(
            names, classes, day=slice_meta["day"], hour_block=slice_meta["hour_block"], table=table
        )
    )

    # Gates → sources, split by SPAWN_FRAC_GATE_A (count-based; gate A general, gate B VIP).
    n = int(n_agents)
    n_a = round(n * SPAWN_FRAC_GATE_A)
    n_b = n - n_a
    gate_a, gate_b = geo["entrances_utm"][0], geo["entrances_utm"][1]
    sources = [
        (_spawn_patch(gate_a, SPAWN_JITTER_M), n_a),
        (_spawn_patch(gate_b, SPAWN_JITTER_M), n_b),
    ]

    boundary_rings, blocker_rings = _walkable_rings(lattice=lattice)

    return {
        "boundary_rings": boundary_rings,
        "blocker_rings": blocker_rings,
        "sources": sources,
        "stages_utm": list(geo["stages_utm"]),
        "goal_weights": goal_weights,
        "reach_radius_m": REACH_RADIUS_M,
    }
