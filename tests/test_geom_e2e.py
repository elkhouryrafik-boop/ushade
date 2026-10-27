"""Wave-0 designed-RED scaffold — the offline geom SEAM end-to-end.

Behaviour map (CONTEXT.md + RESEARCH §Phase Requirements -> Test Map):

  * (seam)  test_footprint_to_structure   footprint.json -> FakeRhinoClient.solve(gh_request)
  *                                        -> recorded gh_response -> structure.gltf + .obj on disk;
  *                                        the gh_request the client saw is contract-valid + carries
  *                                        the three frozen IN_ fields (flow_vectors dropped in, NO
  *                                        reshape).

RED mechanism (clone tests/test_crowd_grid.py lines 9-16): ``geom.geom`` (the stage spine) lands
in Wave 3, so the test ``skipif``-guards on its absence + imports lazily; the skip lifts when the
spine ships, becoming the GREEN gate. Needs the geom extra so ``@pytest.mark.geom`` + importorskip.
"""

from __future__ import annotations

import importlib.util

import pytest

pytest.importorskip("rhino3dm")

from conftest_geom import FakeRhinoClient, load_flow_vectors, load_footprint  # noqa: E402

pytestmark = pytest.mark.geom

_SPINE_AVAILABLE = importlib.util.find_spec("geom.geom") is not None
_needs_spine = pytest.mark.skipif(
    not _SPINE_AVAILABLE, reason="src/geom/geom.py lands in Wave 3 (RED scaffold)"
)


@_needs_spine
def test_footprint_to_structure(tmp_path):
    """Seam: footprint -> FakeRhinoClient -> gh_response -> structure.gltf/.obj; request is contract-valid."""
    from geom.geom import run_gh_stage
    from src.validate.validate import validate

    client = FakeRhinoClient()
    run_gh_stage(load_footprint(), load_flow_vectors(), client=client, out_dir=tmp_path)

    # The client saw exactly one contract-valid gh_request carrying the three frozen IN_ fields.
    req = client.last_request
    assert req is not None, "the stage must have solved a gh_request"
    validate(req, "gh_request")
    assert set(req) >= {"schema_version", "IN_Footprint", "IN_FlowVectors", "IN_SunVector"}
    assert req["schema_version"] == "1.0.0"

    # The decoded artifacts landed on disk.
    assert (tmp_path / "structure.gltf").exists()
    assert (tmp_path / "structure.obj").exists()
