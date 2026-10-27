"""Wave-0 designed-RED scaffold — GEOM-05 stage cache + failure-leaves-stage-not-done.

Behaviour map (CONTEXT.md + RESEARCH §Phase Requirements -> Test Map; clones the Phase-3
test_core cache-hit counter + failure tests):

  * GEOM-05  test_cache_hit_no_solve              a 2nd run on the same footprint hash does ZERO
  *                                              solve (the solve_count counter stays 1)
  * GEOM-05  test_byte_identical_rerun             two reruns produce byte-identical artifacts
  * (spine)  test_failure_leaves_stage_not_done    a failing solve raises; the stage is NOT done

RED mechanism (clone tests/test_crowd_grid.py lines 9-16): ``geom.geom`` (the stage spine) lands
in Wave 3, so each test ``skipif``-guards on its absence + imports lazily; the skips lift when the
spine ships, becoming the GREEN gate. Needs the geom extra so ``@pytest.mark.geom`` + importorskip.
"""

from __future__ import annotations

import importlib.util

import pytest

pytest.importorskip("rhino3dm")

from conftest_geom import (  # noqa: E402  (explicit import)
    FakeRhinoClient,
    RhinoComputeError,
    load_flow_vectors,
    load_footprint,
)

pytestmark = pytest.mark.geom

_SPINE_AVAILABLE = importlib.util.find_spec("geom.geom") is not None
_needs_spine = pytest.mark.skipif(
    not _SPINE_AVAILABLE, reason="src/geom/geom.py lands in Wave 3 (RED scaffold)"
)


@_needs_spine
def test_cache_hit_no_solve(tmp_path):
    """GEOM-05: a 2nd unchanged-input run does ZERO solve (the solve_count stays 1)."""
    from geom.geom import run_gh_stage

    client = FakeRhinoClient()
    run_gh_stage(load_footprint(), load_flow_vectors(), client=client, out_dir=tmp_path)
    assert client.solve_count == 1, "first run solves exactly once"
    run_gh_stage(load_footprint(), load_flow_vectors(), client=client, out_dir=tmp_path)
    assert client.solve_count == 1, "cache hit must do ZERO solve"


@_needs_spine
def test_byte_identical_rerun(tmp_path):
    """GEOM-05: two fresh runs over the same inputs produce byte-identical artifacts."""
    from geom.geom import run_gh_stage

    def _run(name):
        out = tmp_path / name
        out.mkdir(parents=True, exist_ok=True)
        run_gh_stage(load_footprint(), load_flow_vectors(), client=FakeRhinoClient(), out_dir=out)
        return (out / "structure.gltf").read_bytes()

    assert _run("a") == _run("b"), "structure bytes must be identical across reruns (determinism)"


@_needs_spine
def test_failure_leaves_stage_not_done(tmp_path):
    """An injected failing solve raises; the stage is NOT done; no partial artifact written."""
    from geom.geom import run_gh_stage

    client = FakeRhinoClient(raise_solve_error=True)
    with pytest.raises(RhinoComputeError):
        run_gh_stage(load_footprint(), load_flow_vectors(), client=client, out_dir=tmp_path)
    assert not (tmp_path / "structure.gltf").exists(), "no partial artifact on failure"


@_needs_spine
def test_gh_meta_carries_shadow_polygon(tmp_path):
    """Q1 (Phase-5b GATE-01): the sidecar carries the projected shadow as PLAIN coords.

    A stage run writes ``gh_meta.json`` with ``shadow_polygon_m`` = origin-translated, per-disjoint-
    polygon exteriors + ``basis`` + ``min_corner_m`` — the base-tier input the cooling-acceptance gate
    consumes WITHOUT re-decoding the mesh (no rhino3dm in the gate tier). Asserts the field is present,
    non-empty, and labelled with an honest basis (roof-mesh-projection for the recorded fixture).
    """
    import json

    from geom.geom import run_gh_stage

    run_gh_stage(load_footprint(), load_flow_vectors(), client=FakeRhinoClient(), out_dir=tmp_path)
    gh_meta = json.loads((tmp_path / "gh_meta.json").read_text(encoding="utf-8"))

    sp = gh_meta["shadow_polygon_m"]
    assert sp["basis"] == "roof-mesh-projection", sp["basis"]
    assert isinstance(sp["min_corner_m"], list) and len(sp["min_corner_m"]) == 2, sp
    assert sp["polygons_xy_m"], "projected shadow must have at least one polygon ring"
    # Each ring is a list of [x, y] coordinate pairs (plain coords — base-tier).
    first_ring = sp["polygons_xy_m"][0]
    assert len(first_ring) >= 4, "a polygon exterior ring needs >= 4 coords (closed)"
    assert all(len(pt) == 2 for pt in first_ring), "coords are [x, y] pairs (plain, no rhino3dm)"
