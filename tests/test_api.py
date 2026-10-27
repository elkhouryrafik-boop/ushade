"""FastAPI endpoint tests — Phase 2.2.

Wave 0 stubs activated in Plan 02 (xfail marks removed) — the endpoints are implemented in src/api/app.py.
conftest_api provides mock_climate + mock_crowd fixtures (torch-free, fast).
"""
import pytest

# ------------------------------------------------------------------
# Import guard: skip the whole module if fastapi is not installed yet
# ------------------------------------------------------------------
pytest.importorskip("fastapi", reason="fastapi not installed — run: pip install -e '.[api,dev]'")

from pathlib import Path  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402 (after importorskip)


@pytest.fixture()
def client(mock_climate, mock_crowd):  # noqa: F811
    """TestClient wrapping the FastAPI app with mocked stages."""
    from src.api.app import app  # imported here so importorskip gates it
    return TestClient(app)


# ------------------------------------------------------------------
# Wave 0 stubs — turn GREEN in Plan 02
# ------------------------------------------------------------------

def test_parsed_brief_fixture():
    """projects/primavera-demo/parsed_brief.json exists and has capacity=65000."""
    import json
    from pathlib import Path
    p = Path("projects/primavera-demo/parsed_brief.json")
    assert p.exists(), "parsed_brief.json fixture missing — Wave 0 must commit it"
    data = json.loads(p.read_text())
    assert data["capacity"] == 65000
    assert data["date"] == "2026-06-14"
    # contracts/parsed_brief.schema.json theme enum is lowercase:
    # ['maritime', 'natural', 'industrial', 'urban'] — plan's "Natural" was schema-invalid
    assert data["theme"] == "natural"


def test_run_endpoint_returns_started(client):
    resp = client.post("/api/run/primavera-demo")
    assert resp.status_code == 200
    assert resp.json()["status"] == "started"


def test_run_endpoint_idempotent(client, monkeypatch):
    """MD-01: re-POST while a run is in flight returns already_running and
    must NOT reset/corrupt the in-flight _run_status (no stepper regression,
    no second rollout queued)."""
    import src.api.app as app_module
    in_flight = {"utci_grid": "done", "crowd_grid": "running"}
    monkeypatch.setitem(app_module._run_status, "primavera-demo", dict(in_flight))
    resp = client.post("/api/run/primavera-demo")
    assert resp.status_code == 200
    assert resp.json() == {"project_id": "primavera-demo", "status": "already_running"}
    # The rejected re-trigger left the in-flight status untouched.
    assert app_module._run_status["primavera-demo"] == in_flight


def test_status_endpoint_returns_stage_states(client):
    resp = client.get("/api/status/primavera-demo")
    assert resp.status_code == 200
    body = resp.json()
    assert "utci_grid" in body
    assert "crowd_grid" in body


def test_no_secrets_in_response(client, monkeypatch):
    """T-2.2-05: no secret VALUE, env-var name, or traversal payload in any response.

    MD-03: canary values are planted in the env — a leaked key would carry its
    value, not its variable name, so we assert on both. (The old
    `... or "infrared" in ["infrared"]` clause was a tautology — removed.)
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-canary-123")
    monkeypatch.setenv("INFRARED_API_KEY", "infrared-canary-456")
    resp_run = client.post("/api/run/primavera-demo")
    resp_status = client.get("/api/status/primavera-demo")
    for resp in (resp_run, resp_status):
        body = resp.text
        assert "anthropic-canary-123" not in body  # secret VALUE, not just the name
        assert "infrared-canary-456" not in body
        assert "ANTHROPIC_API_KEY" not in body
        assert "INFRARED_API_KEY" not in body
        assert ".." not in body  # no path traversal in response


def test_artifacts_heat_endpoint(client):
    resp = client.get("/api/artifacts/primavera-demo/heat")
    assert resp.status_code == 200


def test_artifacts_crowd_endpoint(client):
    resp = client.get("/api/artifacts/primavera-demo/crowd")
    assert resp.status_code == 200


# viz/data/demo_*.json is gitignored upstream (demo/scratch outputs), so the demo fallback
# this route serves only exists where the viz generator has been run. Skipping keeps a fresh
# clone green without pretending the artifact is committed.
@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "viz" / "data" / "demo_trajectories.json").exists(),
    reason="viz/data/demo_*.json is gitignored upstream — run the viz generator to exercise this fallback",
)
def test_artifacts_trajectories_endpoint(client):
    resp = client.get("/api/artifacts/primavera-demo/trajectories")
    assert resp.status_code == 200


def test_inventory_query(client, monkeypatch):
    """D-10 / T-05-03: GET /inventory/query rejects bad params with 422 and never echoes a
    secret in any response body.

    DESIGNED-RED until Plan 04: the /inventory/query route does NOT exist yet, so the bad-param
    requests currently 404 (route-missing) instead of 422. Plan 04 adds the endpoint cloning the
    PROJECT_ID_PATTERN validated-path-param pattern in src/api/app.py — at which point the 422
    assertions below turn GREEN with NO test edits. The no-secret-leak assertions hold in BOTH
    states (a 404 body must also never carry a key value). Marked clearly: Plan 04 makes this GREEN.

    Bad params asserted:
      - material_class not in the frozen set (e.g. 'unobtanium')   -> 422
      - negative min_qty (e.g. -5)                                  -> 422
      - a path-traversal-ish location (encoded '..')               -> 422
    """
    # Plant canary secrets in the env — a leaked key would carry its VALUE, not its name.
    monkeypatch.setenv("ORS_API_KEY", "ors-canary-789")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-canary-123")

    bad_requests = [
        "/inventory/query?material_class=unobtanium&min_qty=1&location=barcelona",
        "/inventory/query?material_class=membrane&min_qty=-5&location=barcelona",
        "/inventory/query?material_class=membrane&min_qty=1&location=%2e%2e",
    ]
    for url in bad_requests:
        resp = client.get(url)
        # Plan 04 GREEN: the route exists and each bad param is a validated 422.
        assert resp.status_code == 422, (
            f"{url} must be a validated 422 now that the /inventory/query route exists"
        )
        # no-secret-leak holds in BOTH states:
        body = resp.text
        assert "ors-canary-789" not in body  # secret VALUE
        assert "anthropic-canary-123" not in body
        assert "ORS_API_KEY" not in body
        assert "ANTHROPIC_API_KEY" not in body

    # A VALID query returns a 200 availability view (empty list is fine if no snapshot
    # has been persisted yet) — and STILL never echoes a secret into the response/logs.
    good = client.get("/inventory/query?material_class=membr&min_qty=1&location=barcelona")
    assert good.status_code == 200, "a valid /inventory/query must return the availability view"
    body = good.json()
    assert body["material_class"] == "membr"
    assert "availability" in body and isinstance(body["availability"], list)
    raw = good.text
    assert "ors-canary-789" not in raw  # secret VALUE never in the success body
    assert "ORS_API_KEY" not in raw
    assert "ANTHROPIC_API_KEY" not in raw
    # Every returned listing id belongs to the requested class (no struct leaking into membr).
    for entry in body["availability"]:
        assert str(entry.get("material_id", "")).startswith("membr-")


def test_project_id_path_traversal_rejected(client):
    """T-2.2-01: project_id regex must reject path traversal attempts.

    httpx normalizes a literal "../" out of the URL before sending (RFC 3986 dot-segment
    removal), so "/api/run/../etc/passwd" never reaches the route — it 404s at routing.
    Payloads whose DECODED form contains "/" (e.g. "..%2fetc") also 404: the route's
    {project_id} segment is [^/]+ and cannot match across a slash. The payload that
    actually reaches the validator is the encoded single segment "%2e%2e" — Starlette
    decodes it to ".." in the path param, which PROJECT_ID_PATTERN must reject with 422.
    """
    # Encoded ".." reaches the route as a single segment -> regex validator 422s
    assert client.post("/api/run/%2e%2e").status_code == 422
    assert client.get("/api/status/%2e%2e").status_code == 422
    # Other [a-z0-9-]+ violations that match the route are rejected too
    for bad in ("UPPER", "has_underscore", "dot.dot"):
        assert client.post(f"/api/run/{bad}").status_code == 422
        assert client.get(f"/api/status/{bad}").status_code == 422
    # Decoded-slash variants never match the route at all (404 == never touches the fs)
    assert client.post("/api/run/..%2fetc%2fpasswd").status_code == 404
    # Literal ../ never even matches the route (httpx normalizes; route 404s) — fine either way
    resp_literal = client.post("/api/run/../etc/passwd")
    assert resp_literal.status_code in (404, 422)
