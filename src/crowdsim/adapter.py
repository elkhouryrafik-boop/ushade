"""Pure-numpy finite-difference trajectory adapter (CROWD-08, RESEARCH Pattern 3).

JuPedSim exposes per-agent ``position`` (x, y) per ``iterate()`` step but NOT the velocity the
FROZEN ``build_crowd_grid`` expects (``[x, y, vx, vy]``). :func:`to_trajectory` finite-differences
the recorded positions to fill ``vx, vy`` and emits the SAME ``(steps × agents × 4)`` array
``grid.py`` already consumes — the seam between the JuPedSim engine and the frozen contract.

PURITY: this module is PURE numpy — it imports NO jupedsim/shapely, so it is unit-testable in the
base tier without the engine wheel (the lazy-import discipline; jupedsim only enters on
``simulation.py``'s factory path). ``import numpy`` at module top is fine — numpy is a base dep.

UNITS: positions are UTM31N ABSOLUTE metres — the SAME frame ``site.py``/``snap_to_lattice`` use
(``snap_to_lattice`` does ``(x_m - origin_x_m) // cell_size_m``, grid.py). The caller
(``simulation.py``) MUST pass positions in absolute UTM metres ordered by a STABLE agent-id sort
across steps (an agent that parks at a stage front keeps its last position → velocity 0, A2), so
the array stays rectangular and the terminal-frame snap lands on the final positions.
"""

from __future__ import annotations

import numpy as np

from crowd.constants import STEP_DT_JPS_S


def to_trajectory(positions) -> np.ndarray:
    """Finite-difference per-step positions into the FROZEN ``(steps × agents × 4)`` array.

    Args:
        positions: array-like of shape ``(steps, agents, 2)`` — per-step per-agent ``(x, y)`` in
            UTM31N absolute metres, agents in a STABLE id-sorted column order across all steps.

    Returns:
        ``np.ndarray`` of shape ``(steps, agents, 4)`` = ``[x, y, vx, vy]`` where columns 2:4 are
        finite-difference velocities: ``vel[0] = 0`` and ``vel[t] = (pos[t] - pos[t-1]) /
        STEP_DT_JPS_S``. A parked agent (no position change) holds velocity 0 (A2), so the array
        stays rectangular for a fixed agent count.
    """
    pos = np.asarray(positions, dtype=float)  # (steps, agents, 2)
    vel = np.zeros_like(pos)
    vel[1:] = (pos[1:] - pos[:-1]) / STEP_DT_JPS_S  # finite-diff per step; vel[0] stays 0
    return np.concatenate([pos, vel], axis=2)  # (steps, agents, 4) = [x, y, vx, vy]
