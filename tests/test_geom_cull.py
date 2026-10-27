"""Wave-0 designed-RED scaffold — GEOM-02 flow-buffer culling.

Behaviour map (CONTEXT.md test list + RESEARCH §Phase Requirements -> Test Map):

  * GEOM-02  test_points_within_buffer_are_culled   grid points within FLOW_BUFFER_M of ANY flow
  *                                                  line are removed (shade never lands on a route)
  * GEOM-02  test_points_outside_buffer_survive      a point clear of every route is kept

RED mechanism (clone tests/test_crowd_grid.py lines 9-16 — the project's Wave-0 convention):
``geom.reference_generator`` does not exist until Wave 2, so a bare top-level
``from geom.reference_generator import cull_grid`` would ERROR this whole module at COLLECTION
and turn the base ``-m "not crowd and not geom"`` suite RED (the CLAUDE.md base-green
non-negotiable). To keep the base regression green WHILE staying honestly RED, each test
``skipif``-guards on the absence of ``geom.reference_generator`` and imports lazily inside the
body. When Wave 2 ships ``reference_generator.py``, ``find_spec`` finds it, the skips lift, and
these become the GREEN gate — locking the contract every later plan is verified against.

shapely is a BASE dependency (Phase 3, A1), so cull_grid needs no geom extra — but this file is
marked ``geom`` per the RESEARCH test map for tier consistency.
"""

from __future__ import annotations

import importlib.util

import pytest

from conftest_geom import load_flow_vectors  # noqa: F401  (explicit import, not auto-loaded)

pytestmark = pytest.mark.geom

# Lifts automatically once Wave 2 ships src/geom/reference_generator.py (honest RED-until-then).
_REF_AVAILABLE = importlib.util.find_spec("geom.reference_generator") is not None
_needs_ref = pytest.mark.skipif(
    not _REF_AVAILABLE, reason="src/geom/reference_generator.py lands in Wave 2 (RED scaffold)"
)


@_needs_ref
def test_points_within_buffer_are_culled():
    """GEOM-02: a candidate grid point on a flow line is culled (within FLOW_BUFFER_M)."""
    from geom.reference_generator import cull_grid
    from geom.constants import FLOW_BUFFER_M

    flow = load_flow_vectors()
    line = flow[0]
    on_route = (
        (line["origin"]["x_m"] + line["destination"]["x_m"]) / 2.0,
        (line["origin"]["y_m"] + line["destination"]["y_m"]) / 2.0,
    )
    survivors = cull_grid([on_route], flow, buffer_m=FLOW_BUFFER_M)
    assert on_route not in survivors, "a point on a flow route must be culled"


@_needs_ref
def test_points_outside_buffer_survive():
    """GEOM-02: a point far from every route is kept."""
    from geom.reference_generator import cull_grid
    from geom.constants import FLOW_BUFFER_M

    flow = load_flow_vectors()
    far = (0.0, 0.0)  # origin-corner, clear of the EPSG-coord routes
    survivors = cull_grid([far], flow, buffer_m=FLOW_BUFFER_M)
    assert far in survivors, "a point clear of every route must survive culling"
