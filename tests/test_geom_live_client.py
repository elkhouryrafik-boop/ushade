"""GEOM-01 LIVE client — offline test of the Rhino.Compute bridge (geom marker).

The literal HTTP solve (``Grasshopper.EvaluateDefinition``) is the ONE part that needs a running
compute server, so it is monkeypatched. Everything else is exercised for real against installed
``rhino3dm``: gh_request -> RH_IN DataTrees (real ``.Encode()``), a synthetic RH_OUT compute
response carrying a REAL encoded mesh + BOM scalars, then the gh_response assembly + contract
validation + a decode_mesh round-trip (the bbox-sanity gate the spine relies on).

This proves the bridge's request-build and response-parse logic without a server; the live wire is
covered by the operator smoke run (``scripts/run_live_geom.py``) once compute + the .gh exist.
"""

from __future__ import annotations

import base64
import importlib.util
import json

import pytest

pytestmark = pytest.mark.geom

_HAS_GEOM = importlib.util.find_spec("rhino3dm") is not None and (
    importlib.util.find_spec("compute_rhino3d") is not None
)


def _encoded_mesh_data(rhino3dm, width_m: float, depth_m: float) -> str:
    """A real venue-scaled flat quad mesh, encoded as compute would return it (archive3dm JSON str)."""
    mesh = rhino3dm.Mesh()
    mesh.Vertices.Add(0.0, 0.0, 0.0)
    mesh.Vertices.Add(width_m, 0.0, 0.0)
    mesh.Vertices.Add(width_m, depth_m, 0.0)
    mesh.Vertices.Add(0.0, depth_m, 0.0)
    mesh.Faces.AddFace(0, 1, 2, 3)
    return json.dumps(mesh.Encode())


def _fake_compute_response(rhino3dm, *, pillars: int, membrane_m2: float) -> dict:
    """Mimic ``EvaluateDefinition``'s return: a values list keyed by RH_OUT param names."""
    return {
        "values": [
            {
                "ParamName": "RH_OUT:OUT_Mesh",
                "InnerTree": {"{0}": [{"type": "Rhino.Geometry.Mesh",
                                       "data": _encoded_mesh_data(rhino3dm, 600.0, 700.0)}]},
            },
            {
                "ParamName": "RH_OUT:OUT_Pillars",
                "InnerTree": {"{0}": [{"type": "System.Int32", "data": json.dumps(pillars)}]},
            },
            {
                "ParamName": "RH_OUT:OUT_Membrane_m2",
                "InnerTree": {"{0}": [{"type": "System.Double", "data": json.dumps(membrane_m2)}]},
            },
        ]
    }


@pytest.mark.skipif(not _HAS_GEOM, reason="geom extra (rhino3dm/compute_rhino3d) not installed")
def test_live_client_assembles_contract_valid_gh_response(tmp_path, monkeypatch):
    """Mock the wire; assert the bridge builds a contract-valid gh_response that decodes cleanly."""
    import rhino3dm

    import compute_rhino3d.Grasshopper as Grasshopper

    from geom.live_client import ComputeRhinoClient
    from geom.decode import decode_mesh
    from geom.request import sun_vector
    from geom.reference_generator import _footprint_polygon  # build a real gh_request footprint

    # A dummy .gh file so the is_file() guard passes (EvaluateDefinition is mocked, contents unused).
    gh_path = tmp_path / "festcool_structure.gh"
    gh_path.write_bytes(b"GH-DEFINITION-PLACEHOLDER")

    captured = {}

    def _fake_eval(definition, trees):
        captured["definition"] = definition
        captured["trees"] = trees
        return _fake_compute_response(rhino3dm, pillars=84, membrane_m2=5976.0)

    monkeypatch.setattr(Grasshopper, "EvaluateDefinition", _fake_eval)

    # Minimal but contract-valid gh_request (one square footprint, one flow line, real sun vector).
    gh_request = {
        "schema_version": "1.0.0",
        "IN_Footprint": [[{"x_m": 0.0, "y_m": 0.0}, {"x_m": 600.0, "y_m": 0.0},
                          {"x_m": 600.0, "y_m": 700.0}, {"x_m": 0.0, "y_m": 700.0}]],
        "IN_FlowVectors": [{"origin": {"x_m": 0.0, "y_m": 0.0},
                            "destination": {"x_m": 600.0, "y_m": 700.0}}],
        "IN_SunVector": list(sun_vector("2026-06-14")),
    }

    client = ComputeRhinoClient(gh_path=str(gh_path), url="http://localhost:6500/")
    gh_response = client.solve(gh_request)

    # gh_response is contract-shaped (validate ran inside solve; re-assert the salient fields).
    assert gh_response["schema_version"] == "1.0.0"
    assert gh_response["OUT_BOM"] == {"pillars": 84, "membrane_m2": 5976.0}
    assert isinstance(gh_response["OUT_Mesh"]["b64"], str) and gh_response["OUT_Mesh"]["b64"]

    # The b64 is the exact format decode.py inverts — bbox gate must pass (600x700 in [50,2000]).
    result = decode_mesh(gh_response["OUT_Mesh"]["b64"])
    span_x, span_z, _vert = result.bbox_span_m
    assert 50.0 < span_x < 2000.0 and 50.0 < span_z < 2000.0

    # The request carried three RH_IN trees with the right names + geometry counts.
    names = {t.data["ParamName"] for t in captured["trees"]}
    assert names == {"RH_IN:IN_Footprint", "RH_IN:IN_FlowVectors", "RH_IN:IN_SunVector"}


@pytest.mark.skipif(not _HAS_GEOM, reason="geom extra not installed")
def test_live_client_missing_gh_path_raises_typed_error():
    """No GH_DEFINITION_PATH -> typed RhinoComputeError (spine maps to a failed, not-done stage)."""
    from geom.live_client import ComputeRhinoClient, RhinoComputeError

    client = ComputeRhinoClient(gh_path=None, url="http://localhost:6500/")
    with pytest.raises(RhinoComputeError, match="GH_DEFINITION_PATH"):
        client.solve({"schema_version": "1.0.0", "IN_Footprint": [],
                      "IN_FlowVectors": [], "IN_SunVector": [0.0, 0.0, 1.0]})


@pytest.mark.skipif(not _HAS_GEOM, reason="geom extra not installed")
def test_live_client_no_values_raises_typed_error(tmp_path, monkeypatch):
    """A compute response with no 'values' (bad RH_OUT wiring) -> typed RhinoComputeError."""
    import compute_rhino3d.Grasshopper as Grasshopper

    from geom.live_client import ComputeRhinoClient, RhinoComputeError
    from geom.request import sun_vector

    gh_path = tmp_path / "x.gh"
    gh_path.write_bytes(b"x")
    monkeypatch.setattr(Grasshopper, "EvaluateDefinition", lambda d, t: {"values": []})

    client = ComputeRhinoClient(gh_path=str(gh_path))
    gh_request = {
        "schema_version": "1.0.0",
        "IN_Footprint": [[{"x_m": 0.0, "y_m": 0.0}, {"x_m": 600.0, "y_m": 0.0},
                          {"x_m": 600.0, "y_m": 700.0}]],
        "IN_FlowVectors": [],
        "IN_SunVector": list(sun_vector("2026-06-14")),
    }
    with pytest.raises(RhinoComputeError, match="OUT_Mesh"):
        client.solve(gh_request)
