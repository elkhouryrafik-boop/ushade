"""Marketplace hold API tests — exercises the FastAPI surface end-to-end.

Gated behind the `api` extra (importorskip fastapi). The store is pointed at a tmp DB so
the suite never touches projects/marketplace.db. Proves the organiser->hold->supplier
loop, the 409 no-double-book rejection, and idempotent replay over HTTP.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed — run: pip install -e '.[api,dev]'")

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(tmp_path):
    import src.api.app as app_module
    from marketplace.holds import HoldStore
    from marketplace.suppliers import SupplierStore

    db = tmp_path / "mk.db"
    app_module._HOLD_STORE = HoldStore(db)            # isolate from projects/
    app_module._SUPPLIER_STORE = SupplierStore(db)
    yield TestClient(app_module.app)
    app_module._HOLD_STORE.close()
    app_module._SUPPLIER_STORE.close()
    app_module._HOLD_STORE = None
    app_module._SUPPLIER_STORE = None


def _register(client, listing_id="scaffold-01", total=1000.0):
    r = client.post("/api/marketplace/listings", json={
        "listing_id": listing_id, "total_units": total,
        "material_id": "struct-scaffold-tube-48", "supplier_id": "rebuild-cat", "unit": "kg",
    })
    assert r.status_code == 201
    return listing_id


def test_place_confirm_collect_loop(client):
    lid = _register(client)
    r = client.post("/api/marketplace/holds", json={
        "listing_id": lid, "organiser_id": "primavera", "qty": 600, "idempotency_key": "k1",
    })
    assert r.status_code == 201
    hold = r.json()
    assert hold["state"] == "requested"
    assert hold["remaining_seconds"] > 0
    hid = hold["id"]

    # supplier sees it in the inbox
    inbox = client.get("/api/marketplace/holds/incoming", params={"supplier_id": "rebuild-cat"}).json()
    assert any(h["id"] == hid for h in inbox["holds"])

    # confirm -> collect
    assert client.post(f"/api/marketplace/holds/{hid}/confirm",
                       json={"supplier_id": "rebuild-cat"}).json()["state"] == "confirmed"
    assert client.post(f"/api/marketplace/holds/{hid}/collect").json()["state"] == "collected"

    # pool stays decremented (collected units are gone)
    avail = client.get(f"/api/marketplace/listings/{lid}/availability").json()
    assert avail["available_units"] == 400.0


def test_double_book_returns_409(client):
    lid = _register(client, total=100.0)
    client.post("/api/marketplace/holds", json={
        "listing_id": lid, "organiser_id": "a", "qty": 80, "idempotency_key": "ka"})
    r = client.post("/api/marketplace/holds", json={
        "listing_id": lid, "organiser_id": "b", "qty": 40, "idempotency_key": "kb"})
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "insufficient_stock"
    assert r.json()["detail"]["available"] == 20.0


def test_idempotent_replay_over_http(client):
    lid = _register(client, total=100.0)
    body = {"listing_id": lid, "organiser_id": "a", "qty": 30, "idempotency_key": "same"}
    h1 = client.post("/api/marketplace/holds", json=body).json()
    h2 = client.post("/api/marketplace/holds", json=body).json()
    assert h1["id"] == h2["id"]
    assert h2["replayed"] is True
    assert client.get(f"/api/marketplace/listings/{lid}/availability").json()["available_units"] == 70.0


def test_place_on_unknown_listing_404(client):
    r = client.post("/api/marketplace/holds", json={
        "listing_id": "ghost", "organiser_id": "a", "qty": 1, "idempotency_key": "k"})
    assert r.status_code == 404


def test_invalid_id_422(client):
    r = client.get("/api/marketplace/holds/incoming", params={"supplier_id": "../etc"})
    assert r.status_code == 422


def test_materials_no_snapshots_is_honest_unavailable(client):
    r = client.get("/api/marketplace/materials", params={"project_id": "empty-proj-xyz"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "unavailable"     # never a fake "live"
    assert body["items"] == []


def test_materials_bad_radius_422(client):
    r = client.get("/api/marketplace/materials", params={"project_id": "p", "radius_km": 0})
    assert r.status_code == 422


def test_supplier_onboard_and_fetch(client):
    r = client.post("/api/marketplace/suppliers", json={
        "supplier_id": "rebuild-cat", "name": "ReBuild Cataluña", "contact_email": "demo-operator@example.org"})
    assert r.status_code == 201
    assert r.json()["verified"] is False       # honest: not self-verified
    assert client.get("/api/marketplace/suppliers/rebuild-cat").json()["name"] == "ReBuild Cataluña"
    assert any(s["supplier_id"] == "rebuild-cat" for s in client.get("/api/marketplace/suppliers").json()["suppliers"])


def test_supplier_not_found_404(client):
    assert client.get("/api/marketplace/suppliers/ghost").status_code == 404
