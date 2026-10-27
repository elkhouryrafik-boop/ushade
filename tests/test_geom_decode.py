"""Wave-0 designed-RED scaffold — GEOM-05 OUT_Mesh decode.

Behaviour map (CONTEXT.md + RESEARCH §Phase Requirements -> Test Map):

  * GEOM-05  test_decode_emits_gltf_and_obj      OUT_Mesh.b64 -> .gltf + .obj on disk
  * GEOM-05  test_decoded_mesh_is_venue_scaled    decoded mesh bbox span is within [BBOX_MIN_M,
  *                                                BBOX_MAX_M] (metres + Y-up + origin-translated)

RED mechanism (clone tests/test_crowd_grid.py lines 9-16): ``geom.decode`` lands in Wave 3, so
each test ``skipif``-guards on its absence + imports lazily inside the body so the base suite
stays green; the skips lift when decode.py ships, becoming the GREEN gate. Needs rhino3dm/trimesh
(the geom extra) so it is ``@pytest.mark.geom`` + ``importorskip``.
"""

from __future__ import annotations

import importlib.util

import pytest

pytest.importorskip("rhino3dm")
pytest.importorskip("trimesh")

from conftest_geom import load_gh_response_fixture  # noqa: E402  (explicit import)

pytestmark = pytest.mark.geom

_DECODE_AVAILABLE = importlib.util.find_spec("geom.decode") is not None
_needs_decode = pytest.mark.skipif(
    not _DECODE_AVAILABLE, reason="src/geom/decode.py lands in Wave 3 (RED scaffold)"
)


@_needs_decode
def test_decode_emits_gltf_and_obj(tmp_path):
    """GEOM-05: decoding the recorded OUT_Mesh writes both a .gltf and a .obj artifact."""
    from geom.decode import decode_mesh

    resp = load_gh_response_fixture()
    result = decode_mesh(resp["OUT_Mesh"]["b64"], out_dir=tmp_path)
    assert (tmp_path / "structure.gltf").exists(), "decode must emit structure.gltf"
    assert (tmp_path / "structure.obj").exists(), "decode must emit structure.obj"
    assert result is not None


@_needs_decode
def test_decoded_mesh_is_venue_scaled():
    """GEOM-05: the decoded mesh bbox span is venue-scaled (within [BBOX_MIN_M, BBOX_MAX_M])."""
    from geom.decode import decode_mesh
    from geom.constants import BBOX_MAX_M, BBOX_MIN_M

    resp = load_gh_response_fixture()
    bbox = decode_mesh(resp["OUT_Mesh"]["b64"]).bbox_span_m  # (span_x, span_y)
    for span in bbox[:2]:
        assert BBOX_MIN_M <= span <= BBOX_MAX_M, (
            f"decoded mesh span {span} m outside venue bounds [{BBOX_MIN_M}, {BBOX_MAX_M}]"
        )
