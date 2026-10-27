"""Catalog + supplier-store tests (HARV-02/05, MKT-01).

Base tier — pure stdlib (json + sqlite), no network. Covers the transport-carbon formula,
the canonical MaterialItem join, pool seeding, weakest-input-wins status, and the supplier
registry (honest unverified-by-default trust).
"""

from __future__ import annotations

import json

import pytest

from marketplace import catalog
from marketplace.holds import HoldStore
from marketplace.suppliers import SupplierNotFound, SupplierStore


def _write_snapshot(root, project_id, source_id, listings, status="live", fetched_at="2026-06-20T09:00:00.000Z"):
    d = root / project_id / "inventory" / source_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "latest.json").write_text(json.dumps({
        "schema_version": "1.0.0", "source_id": source_id, "status": status,
        "fetched_at": fetched_at, "listings": listings,
    }), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Carbon — the frozen formula, finally applied
# --------------------------------------------------------------------------- #
def test_transport_carbon_formula():
    arch = catalog.load_archetypes()["struct-scaffold-tube-48"]
    # 2 * distance * (qty * unit_mass_kg / 1000) * factor — computed from the archetype's
    # actual (datasheet-sourced) values so the test survives spec updates.
    mass = arch["dimensions"]["unit_mass_kg"]
    factor = arch["lca_profile"]["transport_mode_factor"]
    expected = round(2 * 25.0 * (100 * mass / 1000.0) * factor, 1)
    assert catalog.transport_carbon_kg(arch, quantity=100, distance_km=25.0) == expected


def test_transport_carbon_unknown_quantity_is_none():
    arch = catalog.load_archetypes()["struct-scaffold-tube-48"]
    assert catalog.transport_carbon_kg(arch, quantity=None, distance_km=25.0) is None


# --------------------------------------------------------------------------- #
# Canonical item shape + provenance tiers
# --------------------------------------------------------------------------- #
def test_canonical_item_shape_and_tiers():
    arch = catalog.load_archetypes()["membr-pvc-billboard-vinyl"]
    listing = {"material_id": "membr-pvc-billboard-vinyl", "qty_available": 200.0,
               "distance_km": 15.0, "distance_tier": "DERIVED", "source_url": "https://x/y",
               "availability": "available"}
    item = catalog.canonical_item(listing, arch)
    assert item["type"] == "membr"
    assert item["unit"] == "m2"
    assert item["quantityTier"] == "ASSUMED"           # scraped availability, not a datasheet
    assert item["transportCarbonTier"] == "ASSUMED"    # transport-only, never whole-life
    assert item["transportCarbonKg"] is not None
    assert len(item["lonLat"]) == 2
    assert item["supplierId"] == catalog.supplier_slug(item["supplier"])


# --------------------------------------------------------------------------- #
# build_catalog — status, radius, and pool seeding (so a hold can BIND)
# --------------------------------------------------------------------------- #
def test_build_catalog_seeds_bindable_pools(tmp_path):
    _write_snapshot(tmp_path, "p1", "exoandamiajes", [
        {"material_id": "struct-scaffold-tube-48", "qty_available": 500.0,
         "distance_km": 25.0, "distance_tier": "DERIVED", "source_url": "https://exo/tube",
         "availability": "available"},
    ])
    store = HoldStore(tmp_path / "mk.db")
    res = catalog.build_catalog("p1", radius_km=30.0, group="listing", projects_root=tmp_path, store=store)
    assert res["status"] == "live"
    assert len(res["items"]) == 1
    item = res["items"][0]
    # the pool was seeded: a hold binds real stock
    h = store.place_hold(listing_id=item["id"], organiser_id="org", qty=100, idempotency_key="k")
    assert h["state"] == "requested"
    assert store.availability(item["id"])["available_units"] == 400.0
    store.close()


def test_build_catalog_radius_filters_far_stock(tmp_path):
    _write_snapshot(tmp_path, "p1", "s", [
        {"material_id": "membr-hdpe-shade-net", "qty_available": 10.0,
         "distance_km": 30.0, "distance_tier": "DERIVED", "source_url": "u", "availability": "available"},
    ])
    res = catalog.build_catalog("p1", radius_km=8.0, projects_root=tmp_path)
    assert res["items"] == []          # 30 km > 8 km radius -> dropped


def test_dedupe_collapses_variants_conserving_count(tmp_path):
    # 3 "variants" of one Shopify product = same material_id + same source_url -> 1 golden.
    _write_snapshot(tmp_path, "p1", "thefabricsales", [
        {"material_id": "membr-pvc-billboard-vinyl", "qty_available": None, "distance_km": 15.0,
         "distance_tier": "DERIVED", "source_url": "https://shop/pvc", "availability": "out_of_stock"},
        {"material_id": "membr-pvc-billboard-vinyl", "qty_available": None, "distance_km": 15.0,
         "distance_tier": "DERIVED", "source_url": "https://shop/pvc", "availability": "available"},
        {"material_id": "membr-pvc-billboard-vinyl", "qty_available": None, "distance_km": 15.0,
         "distance_tier": "DERIVED", "source_url": "https://shop/pvc", "availability": "out_of_stock"},
    ])
    res = catalog.build_catalog("p1", radius_km=30.0, group="listing", projects_root=tmp_path)
    assert res["raw_count"] == 3
    assert res["count"] == 1                       # collapsed
    item = res["items"][0]
    assert item["listingsRolledUp"] == 3           # conservation: nothing silently dropped
    assert item["availability"] == "available"     # strongest variant wins


def test_dedupe_sums_known_variant_quantities(tmp_path):
    _write_snapshot(tmp_path, "p1", "s", [
        {"material_id": "struct-euro-pallet-epal", "qty_available": 40.0, "distance_km": 12.0,
         "distance_tier": "DERIVED", "source_url": "https://x/pallet", "availability": "available"},
        {"material_id": "struct-euro-pallet-epal", "qty_available": 60.0, "distance_km": 12.0,
         "distance_tier": "DERIVED", "source_url": "https://x/pallet", "availability": "available"},
    ])
    res = catalog.build_catalog("p1", radius_km=30.0, group="listing", projects_root=tmp_path)
    assert res["count"] == 1
    assert res["items"][0]["quantity"] == 100.0    # 40 + 60 (additive variant stock)


def test_distinct_listings_not_merged(tmp_path):
    _write_snapshot(tmp_path, "p1", "s", [
        {"material_id": "struct-euro-pallet-epal", "qty_available": 10.0, "distance_km": 12.0,
         "distance_tier": "DERIVED", "source_url": "https://x/pallet-a", "availability": "available"},
        {"material_id": "struct-euro-pallet-epal", "qty_available": 10.0, "distance_km": 12.0,
         "distance_tier": "DERIVED", "source_url": "https://x/pallet-b", "availability": "available"},
    ])
    res = catalog.build_catalog("p1", radius_km=30.0, group="listing", projects_root=tmp_path)
    assert res["count"] == 2                        # different source_urls = different listings


def test_archetype_grouping_collapses_to_one_card(tmp_path):
    # two distinct listings (different urls, different suppliers) of the same archetype
    _write_snapshot(tmp_path, "p1", "s", [
        {"material_id": "struct-euro-pallet-epal", "qty_available": 40.0, "distance_km": 12.0,
         "distance_tier": "DERIVED", "source_url": "https://a/pallet", "availability": "available"},
        {"material_id": "struct-euro-pallet-epal", "qty_available": 60.0, "distance_km": 5.0,
         "distance_tier": "DERIVED", "source_url": "https://b/pallet", "availability": "available"},
    ])
    res = catalog.build_catalog("p1", radius_km=30.0, projects_root=tmp_path)  # default = archetype
    assert res["count"] == 1                        # ONE browse card
    assert res["listing_count"] == 2                # two bindable listings underneath
    card = res["items"][0]
    assert card["listingCount"] == 2
    assert card["distanceKm"] == 5.0                # nearest of the two
    assert card["quantity"] == 100.0               # summed known stock
    assert len(card["listings"]) == 2              # bindable underlying listings exposed
    assert card["listings"][0]["distanceKm"] == 5.0  # sorted nearest-first


def test_no_snapshots_is_honest_unavailable(tmp_path):
    res = catalog.build_catalog("empty-proj", radius_km=15.0, projects_root=tmp_path)
    assert res["status"] == "unavailable"
    assert res["items"] == []          # never a fabricated list


def test_stale_snapshot_status_propagates(tmp_path):
    _write_snapshot(tmp_path, "p1", "s", [
        {"material_id": "struct-alu-truss-h30v", "qty_available": 50.0,
         "distance_km": 4.0, "distance_tier": "DERIVED", "source_url": "u", "availability": "available"},
    ], status="stale_snapshot", fetched_at="2026-06-19T08:00:00.000Z")
    res = catalog.build_catalog("p1", radius_km=15.0, projects_root=tmp_path)
    assert res["status"] == "stale_snapshot"
    assert res["as_of"] == "2026-06-19T08:00:00.000Z"   # newest fetched_at carried through
    assert res["items"][0]["distanceKm"] == 4.0


# --------------------------------------------------------------------------- #
# Supplier registry (MKT-01)
# --------------------------------------------------------------------------- #
def test_supplier_onboard_is_unverified_by_default(tmp_path):
    s = SupplierStore(tmp_path / "mk.db")
    prof = s.register("rebuild-cat", name="ReBuild Cataluña", contact_email="demo-operator@example.org")
    assert prof["verified"] is False        # never self-asserted trust
    assert prof["name"] == "ReBuild Cataluña"
    assert s.get("rebuild-cat")["supplier_id"] == "rebuild-cat"
    s.close()


def test_supplier_verify_is_separate_admin_gate(tmp_path):
    s = SupplierStore(tmp_path / "mk.db")
    s.register("x", name="X")
    assert s.set_verified("x", True)["verified"] is True
    with pytest.raises(SupplierNotFound):
        s.set_verified("ghost", True)
    s.close()


def test_supplier_listings_join(tmp_path):
    """A supplier sees the pools attributed to them with held/available split."""
    db = tmp_path / "mk.db"
    store = HoldStore(db)
    _write_snapshot(tmp_path, "p1", "s", [
        {"material_id": "struct-scaffold-tube-48", "qty_available": 500.0,
         "distance_km": 25.0, "distance_tier": "DERIVED",
         "source_url": "https://ulma/tube", "availability": "available"},
    ])
    res = catalog.build_catalog("p1", radius_km=30.0, group="listing", projects_root=tmp_path, store=store)
    sup_id = res["items"][0]["supplierId"]
    store.place_hold(listing_id=res["items"][0]["id"], organiser_id="o", qty=120, idempotency_key="k")
    listings = store.listings_for_supplier(sup_id)
    assert len(listings) == 1
    assert listings[0]["held_units"] == 120.0
    assert listings[0]["available_units"] == 380.0
    store.close()
