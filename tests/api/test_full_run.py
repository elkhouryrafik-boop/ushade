"""Backend spec — the API full-run orchestrator (Phase 14 / D-05/D-06 migration).

Phase 7 originally wired a 6-stage pipeline (climate -> crowd -> core -> gh ->
selection -> acceptance) through ``_do_full_run``. Phase 14 Plan 04 (the gated
score.py-retirement wave) MIGRATES the full-run off the retired greedy ``core.core``
placer onto the canonical ranked-zone placer ``run_placement_stage(engine="robust")``
(the SOLE placer post-pivot, D-06). The geometry -> material -> acceptance chain — which
required the retired ``footprint.json``/``gh_meta.json`` the v2.0 "AI proposes, human
commits" pivot dropped — RETIRES with the placer; cladding + the cooling-acceptance gate
await the human-committed geometry of a future phase, never a fabricated footprint.

LOAD-BEARING ASSERTION: the migrated pipeline seeds EXACTLY the three surviving stage
keys (utci_grid, crowd_grid, structure_zones) and drives them in dependency order. No
score_grid/geometry/material/acceptance key is fabricated.

These are fast + offline: the stage functions are monkeypatched to return instantly, so
no torch / network / Rhino / scipy solve is touched.
"""
from __future__ import annotations

import pytest

# Skip the whole module if fastapi is not installed (mirror tests/test_api.py).
pytest.importorskip("fastapi", reason="fastapi not installed — run: pip install -e '.[api,dev]'")

from fastapi.testclient import TestClient  # noqa: E402

# Phase 14 Plan 04 GREEN: _do_full_run runs climate -> crowd -> placement; the
# downstream geometry/material/acceptance chain retired with the greedy placer.

PIPELINE_STAGE_KEYS = {
    "utci_grid",
    "crowd_grid",
    "structure_zones",
}

# The required call order of the surviving stages (climate -> crowd -> placement).
EXPECTED_ORDER = ["climate", "crowd", "placement"]


@pytest.fixture()
def client():
    from src.api.app import app

    return TestClient(app)


@pytest.fixture()
def stub_all_stages(monkeypatch):
    """Monkeypatch the surviving stage functions to record call order and return fast.

    The placement stage (``run_placement_stage``) replaces the retired greedy core +
    geometry + selection + acceptance chain. Stubbing it keeps the run torch/scipy-free.
    """
    import src.api.app as app_module

    order: list[str] = []

    def _stub(name, ret):
        def _fn(*_a, **_k):
            order.append(name)
            return ret

        return _fn

    monkeypatch.setattr(app_module, "run_climate_stage", _stub("climate", {"ok": True}), raising=False)
    monkeypatch.setattr(app_module, "run_crowd_stage", _stub("crowd", {"ok": True}), raising=False)
    monkeypatch.setattr(
        app_module,
        "run_placement_stage",
        _stub("placement", {"structures": []}),
        raising=False,
    )
    return order


def test_post_run_seeds_pipeline_stage_keys(client, stub_all_stages):
    """POST /api/run then GET /api/status returns EXACTLY the surviving stage keys."""
    client.post("/api/run/primavera-demo")
    status = client.get("/api/status/primavera-demo").json()
    assert set(status.keys()) == PIPELINE_STAGE_KEYS, (
        f"status must expose exactly the surviving pipeline stages; got {sorted(status)}"
    )
    # The retired stages must NOT reappear as fabricated keys.
    for retired in ("score_grid", "geometry", "material", "acceptance"):
        assert retired not in status, f"retired stage {retired!r} must not be seeded"


def test_do_full_run_sequences_stages_in_order(stub_all_stages):
    """_do_full_run drives climate -> crowd -> placement in order (no retired stages)."""
    import asyncio
    import src.api.app as app_module

    do_full_run = getattr(app_module, "_do_full_run", None)
    assert do_full_run is not None, "_do_full_run orchestrator missing"

    asyncio.run(do_full_run("primavera-demo"))
    assert stub_all_stages == EXPECTED_ORDER, (
        f"stage call order must be {EXPECTED_ORDER}; got {stub_all_stages}"
    )


def test_placement_failure_is_terminal_failed(client, monkeypatch):
    """An INTERNAL placement error marks structure_zones 'failed' (fail-safe, CCA-F P6) —
    never silently 'done'. (The retired acceptance FAIL-is-success semantics retired with
    the acceptance stage; placement has no soft-FAIL verdict, only success or internal error.)"""
    import src.api.app as app_module

    def _boom_placement(*_a, **_k):
        raise RuntimeError("injected placement failure")

    monkeypatch.setattr(app_module, "run_climate_stage", lambda *a, **k: {"ok": True}, raising=False)
    monkeypatch.setattr(app_module, "run_crowd_stage", lambda *a, **k: {"ok": True}, raising=False)
    monkeypatch.setattr(app_module, "run_placement_stage", _boom_placement, raising=False)

    client.post("/api/run/primavera-demo")
    status = client.get("/api/status/primavera-demo").json()
    assert status.get("structure_zones") == "failed", (
        "an internal placement error is a fail-safe 'failed', never a silent 'done'"
    )
