"""Wave-0 designed-RED scaffold — GEOM-04 provenance discipline.

Behaviour map (CONTEXT.md + INSTRUCTOR-FEEDBACK.md provenance-on-every-number + RESEARCH):

  * GEOM-04  test_karamba_labelled_pre_screening   provenance labels the Karamba result
  *                                                "live-only", "pre-screening", "requires
  *                                                engineering sign-off"
  * GEOM-04  test_never_claims_certified           the provenance NEVER says "certified" or
  *                                                "engineer-approved" (the LLM/geom never signs off)

RED mechanism (clone tests/test_crowd_grid.py lines 9-16): ``geom.geom`` (the stage spine) lands
in Wave 3, so each test ``skipif``-guards on its absence + imports lazily; the skips lift when the
spine ships, becoming the GREEN gate. Needs the geom extra (the spine drives the decode) so
``@pytest.mark.geom`` + importorskip.
"""

from __future__ import annotations

import importlib.util
import json

import pytest

pytest.importorskip("rhino3dm")

from conftest_geom import FakeRhinoClient, load_footprint, load_flow_vectors  # noqa: E402

pytestmark = pytest.mark.geom

_SPINE_AVAILABLE = importlib.util.find_spec("geom.geom") is not None
_needs_spine = pytest.mark.skipif(
    not _SPINE_AVAILABLE, reason="src/geom/geom.py lands in Wave 3 (RED scaffold)"
)


def _provenance_text(tmp_path) -> str:
    from geom.geom import run_gh_stage

    result = run_gh_stage(
        load_footprint(),
        load_flow_vectors(),
        client=FakeRhinoClient(),
        out_dir=tmp_path,
    )
    return json.dumps(result).lower()


@_needs_spine
def test_karamba_labelled_pre_screening(tmp_path):
    """GEOM-04: the provenance flags the structural result as live-only pre-screening needing sign-off."""
    text = _provenance_text(tmp_path)
    assert "pre-screening" in text or "pre screening" in text
    assert "sign-off" in text or "sign off" in text


@_needs_spine
def test_never_claims_certified(tmp_path):
    """GEOM-04: the provenance NEVER claims the structure is certified / engineer-approved."""
    text = _provenance_text(tmp_path)
    assert "certified" not in text, "geom must NEVER claim 'certified'"
    assert "engineer-approved" not in text, "geom must NEVER claim 'engineer-approved'"


@_needs_spine
def test_recorded_fixture_response_decodes_and_labels(tmp_path):
    """GEOM-04: a RECORDED (Karamba-thickened) gh_response is decoded + BOM'd + labelled —
    NOT a local Karamba solve. The recorded fixture stands in for the live GH+Karamba definition's
    response; the stage decodes its mesh, carries its BOM, and labels Karamba live-only."""
    from geom.geom import run_gh_stage

    result = run_gh_stage(
        load_footprint(),
        load_flow_vectors(),
        client=FakeRhinoClient(),  # returns the recorded valid_primavera.json fixture
        out_dir=tmp_path,
    )
    # The recorded response was decoded to real artifacts (no local Karamba solve was run).
    assert (tmp_path / "structure.gltf").exists()
    assert (tmp_path / "structure.obj").exists()
    # Its BOM survived into the stage output (DERIVED-preview, never re-derived offline).
    bom = result["gh_response"]["OUT_BOM"]
    assert bom["pillars"] >= 0 and bom["membrane_m2"] >= 0
    # The sidecar + provenance label Karamba live-only pre-screening (never offline-solved).
    meta = json.loads((tmp_path / "gh_meta.json").read_text(encoding="utf-8"))
    assert "wind-load certification" in meta["certification_needs"]
    assert meta["preview_label"] == "PREVIEW"
