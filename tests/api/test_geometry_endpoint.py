"""Backend RED spec — Plan 08-02 builds the GET /api/artifacts/{id}/geometry route.

Wave-0 DESIGNED-RED (mirrors the Phase-7 `red` marker convention): src/api/app.py
today serves the terminal artifact routes (/bom, /footprint, /render, …) but NOT
the binary geometry route the Real Structural View needs:

  GET /api/artifacts/{id}/geometry  -> 200 + binary GLB (model/gltf-binary)

This 404s today (route unwritten) -> RED. The implementing wave (Plan 02) adds the
endpoint (clone of get_render_input — path-traversal-guarded FileResponse) and DROPS
the `red` marker so this module joins the default green suite.

project_id "primavera-demo" has a REAL self-contained structure.glb on disk (Plan 01
added the file_type="glb" export to decode.py), so the GREEN assertion is against a
real binary, not a mock.

T-08-01: the route must reject a path-traversal-shaped project_id (422) and must not
leak any secret/credential in the served bytes (mesh geometry only).
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed — run: pip install -e '.[api,dev]'")

from fastapi.testclient import TestClient  # noqa: E402

# Plan 02 wrote GET /api/artifacts/{id}/geometry — the RED quarantine is dropped; this
# module now joins the default green suite.

PID = "primavera-demo"


@pytest.fixture()
def client():
    from src.api.app import app

    return TestClient(app)


def test_geometry_serves_binary_for_real_project(client):
    """primavera-demo has structure.glb on disk -> 200 + binary glTF media type."""
    resp = client.get(f"/api/artifacts/{PID}/geometry")
    assert resp.status_code == 200, (
        f"/api/artifacts/{PID}/geometry not implemented yet (Plan 02) — got {resp.status_code}"
    )
    assert resp.headers["content-type"] in ("model/gltf-binary", "model/gltf+json")
    assert len(resp.content) > 0


def test_traversal_project_id_422(client):  # T-08-01
    """A path-traversal-shaped project_id is rejected 422 (the _validated_project_id guard)."""
    resp = client.get("/api/artifacts/..%2Fetc/geometry")
    assert resp.status_code == 422


def test_missing_artifact_404(client):
    """A valid-but-empty project_id yields an honest 404, never a 500."""
    resp = client.get("/api/artifacts/nonexistent-empty/geometry")
    assert resp.status_code == 404


def test_geometry_response_carries_no_secret(client):  # T-08-01 (no cred leak)
    """The served geometry is mesh bytes only — no key/secret token in the body."""
    resp = client.get(f"/api/artifacts/{PID}/geometry")
    body = resp.content.decode("latin-1", errors="ignore").lower()
    for tok in ("aws", "secret", "api_key", "fal_key", "anthropic"):
        assert tok not in body
