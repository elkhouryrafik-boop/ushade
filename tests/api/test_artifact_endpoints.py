"""Backend RED spec — Plan 07-02 builds the terminal artifact endpoints.

Wave-0 DESIGNED-RED: src/api/app.py today serves only the three Phase-2.2
artifact routes (/heat, /crowd, /trajectories). Phase 7 (Plan 02) adds the
terminal-artifact routes the dashboard + export consume:

  GET /api/artifacts/{id}/material_selection  -> selected_id
  GET /api/artifacts/{id}/acceptance          -> verdict
  GET /api/artifacts/{id}/bom                  -> bom            (from gh_meta.json)
  GET /api/artifacts/{id}/render               -> render_url (null = STUB), status
  GET /api/artifacts/{id}/provenance          -> entries

Phase 14 (Plan 04, D-05/D-06): the /api/artifacts/{id}/footprint endpoint RETIRED with
the greedy core + geometry stage (no footprint producer remains post-pivot), so it is
dropped from the parametrized terminal-artifact set below.

These return 404 today (routes unwritten) -> RED. They turn GREEN in Plan 02.
project_id "primavera-demo" has REAL persisted artifacts on disk, so the GREEN
assertions are against real shapes, not mocks.

LOAD-BEARING ASSERTION #4 (updated 2026-06-16, Phase 6 built): the render endpoint
serves a real render_url ONLY when projects/<id>/render.json exists; a project with no
render gets render_url null (pending/stub). The "never fabricate a render_url" honesty
property is enforced in the render stage itself (tests/test_render.py — the no-key path
writes a labelled pending sidecar and never invents a url). primavera-demo now has a real
FLUX.1 render on disk, so its /render returns a non-null url + status "done".
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed — run: pip install -e '.[api,dev]'")

from fastapi.testclient import TestClient  # noqa: E402

# Plan 07-02 GREEN: the six terminal artifact endpoints are implemented; the
# `red` marker is dropped so this module joins the default suite.

PID = "primavera-demo"

# endpoint suffix -> the top-level key its 200 response must carry.
# (footprint retired in Phase 14 Plan 04 — no producer remains; see module docstring.)
TERMINAL_ARTIFACTS = {
    "material_selection": "selected_id",
    "acceptance": "verdict",
    "bom": "bom",
    "render": "render_url",
    "provenance": "entries",
}


@pytest.fixture()
def client():
    from src.api.app import app

    return TestClient(app)


@pytest.mark.parametrize("suffix,top_key", sorted(TERMINAL_ARTIFACTS.items()))
def test_each_terminal_endpoint_returns_persisted_shape(client, suffix, top_key):
    """Each terminal artifact endpoint returns 200 with its expected top-level key."""
    resp = client.get(f"/api/artifacts/{PID}/{suffix}")
    assert resp.status_code == 200, (
        f"/api/artifacts/{PID}/{suffix} not implemented yet (Plan 02) — got {resp.status_code}"
    )
    assert top_key in resp.json(), (
        f"{suffix} response must carry top-level key '{top_key}'"
    )


def test_render_serves_real_render_when_present(client):
    """Phase 6 built: primavera-demo has a real FLUX.1 render.json on disk, so /render
    returns a non-null render_url + status 'done' + the locked conditioning_scale 1.0."""
    resp = client.get(f"/api/artifacts/{PID}/render")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("render_url"), "primavera-demo has a real render — render_url must be served"
    assert body.get("status") == "done"
    assert body.get("conditioning_scale") == 1.0, "the structural-compliance lock must be 1.0"


def test_render_url_is_null_when_no_render_exists(client):
    """A project with no render.json gets render_url null (pending/stub) — never a fabricated
    url (the honesty property; the stage-level guard lives in tests/test_render.py)."""
    resp = client.get("/api/artifacts/no-render-here/render")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("render_url") is None
    assert body.get("status") in ("pending", "pending_live")


def test_unknown_project_id_422(client):
    """A path-traversal-shaped project_id is rejected 422 (T-2.2-01 guard)."""
    resp = client.get("/api/artifacts/..%2Fetc/material_selection")
    assert resp.status_code == 422, (
        "a project_id violating [a-z0-9-]+ must be rejected 422 (path-traversal guard)"
    )


def test_missing_artifact_404(client):
    """A valid-but-empty project_id yields 404, never a 500."""
    resp = client.get("/api/artifacts/nonexistent-empty/material_selection")
    assert resp.status_code == 404, (
        f"a valid-but-missing project artifact must be 404, never 500 — got {resp.status_code}"
    )
