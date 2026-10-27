"""Material catalog + canonical serve projection (HARV-02 / HARV-05).

The join layer between the read-only harvest snapshots (``src/inventory``) and the
binding marketplace (``holds.py``). For a project it:

  1. reads the persisted per-source ``inventory_snapshot`` files (never a live scrape),
  2. binds each listing to its frozen archetype in ``data/materials.json`` (name, type,
     unit, supplier, per-unit mass, solar-transmissivity),
  3. computes **transport carbon** from the frozen formula (the number that has been
     sitting unused in ``materials.json`` meta) — labelled ASSUMED, transport-only,
  4. derives a supplier pin ([lon, lat]) from the archetype's source town,
  5. seeds the marketplace hold pool for each listing (so a hold can BIND real stock),

and emits the canonical ``MaterialItem`` the frontend ``MaterialsProvider`` consumes,
with a provenance tier on every number and an aggregate ``live/stale_snapshot/unavailable``
status (weakest-input-wins — never a fake "live").

karpathy: pure functions over JSON + one dict lookup. No ORM, no ML, no network.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

# data/materials.json — the 10 frozen archetypes (the ONLY material set; MAT-06 frozen).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_MATERIALS_JSON = _REPO_ROOT / "data" / "materials.json"
_PROVENANCE_JSON = _REPO_ROOT / "data" / "materials_provenance.json"

# Site centroid (Parc del Fòrum) — the fallback pin + the routing destination.
_SITE_LONLAT: tuple[float, float] = (2.2203, 41.4106)

# Supplier-town centroids ([lon, lat]) — a DERIVED pin when the archetype source names a
# known town; otherwise an ASSUMED fallback near the site. NOT an exact supplier address
# (we never scraped one), so the pin tier is at best DERIVED (geocoded town centroid).
_TOWN_LONLAT: dict[str, tuple[float, float]] = {
    "polinya": (2.1567, 41.5576),
    "terrassa": (2.0089, 41.5615),
    "zona franca": (2.1340, 41.3380),
    "sant adria": (2.2220, 41.4250),
    "montjuic": (2.1560, 41.3640),
    "estadi olimpic": (2.1556, 41.3650),
    "mataro": (2.4440, 41.5390),  # demo plastics recycler
    "port": (2.1780, 41.3530),
    "fira": (2.1490, 41.3540),
    "barcelona": (2.1686, 41.3874),  # generic centroid — keep LAST (broadest match)
}


@lru_cache(maxsize=1)
def load_archetypes() -> dict[str, dict]:
    """Return the material archetypes keyed by id (cached). Catalog UNFROZEN 2026-06-22."""
    doc = json.loads(_MATERIALS_JSON.read_text(encoding="utf-8"))
    return {m["id"]: m for m in doc["materials"]}


@lru_cache(maxsize=1)
def load_provenance() -> dict[str, dict]:
    """Per-(material, field) provenance ledger (CRISP-DM Phase 2/3); {} if absent."""
    if not _PROVENANCE_JSON.exists():
        return {}
    return json.loads(_PROVENANCE_JSON.read_text(encoding="utf-8")).get("fields", {})


def _strip_accents(s: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def supplier_slug(name: str) -> str:
    """Stable supplier id from a display name (so the catalog, the hold's ``supplier_id``,
    and supplier onboarding all key on ONE id). Accent-stripped, non-alnum -> '-'."""
    import re

    base = re.sub(r"[^a-z0-9]+", "-", _strip_accents(name or "")).strip("-")
    return base[:64] or "unknown-supplier"


def supplier_pin(source: str) -> tuple[list[float], str]:
    """Derive a [lon, lat] pin + tier from an archetype source string.

    A named known town -> that town centroid (DERIVED); otherwise the site centroid
    nudged deterministically by the source hash so pins don't all stack (ASSUMED).
    """
    blob = _strip_accents(source or "")
    for town, lonlat in _TOWN_LONLAT.items():
        if town in blob:
            return [lonlat[0], lonlat[1]], "DERIVED"
    # Deterministic small offset (~±0.01°) so multiple unknown-town pins are distinct.
    h = int(hashlib.sha1((source or "x").encode("utf-8")).hexdigest(), 16)
    dlon = ((h % 2000) / 1000.0 - 1.0) * 0.012
    dlat = (((h // 2000) % 2000) / 1000.0 - 1.0) * 0.012
    return [round(_SITE_LONLAT[0] + dlon, 5), round(_SITE_LONLAT[1] + dlat, 5)], "ASSUMED"


def transport_carbon_kg(archetype: dict, quantity: float | None, distance_km: float | None) -> float | None:
    """Transport carbon (kgCO2e) per the frozen materials.json formula — ASSUMED, transport-only.

    ``Transport_Carbon = 2 * Distance_km * Mass_tonnes * transport_mode_factor`` (round trip;
    manufacturing = 0, recycled cut-off). ``Mass_tonnes = quantity * unit_mass_kg / 1000``.
    Returns None when quantity or distance is unknown (honest — never a fabricated number).
    """
    if quantity is None or distance_km is None:
        return None
    unit_mass_kg = archetype.get("dimensions", {}).get("unit_mass_kg")
    factor = archetype.get("lca_profile", {}).get("transport_mode_factor")
    if unit_mass_kg is None or factor is None:
        return None
    mass_tonnes = (quantity * unit_mass_kg) / 1000.0
    return round(2.0 * distance_km * mass_tonnes * factor, 1)


def transport_carbon_per_unit_kg(archetype: dict, distance_km: float | None) -> float | None:
    """Transport carbon PER UNIT (kgCO2e per metre / m2 / unit) — ASSUMED, transport-only.

    Computable from distance + per-unit mass alone, so it shows a real number even when
    the scraped listing's total quantity is unknown (the common case — most feeds don't
    expose stock counts). Total = quantity x this; None when distance is unknown.
    """
    if distance_km is None:
        return None
    unit_mass_kg = archetype.get("dimensions", {}).get("unit_mass_kg")
    factor = archetype.get("lca_profile", {}).get("transport_mode_factor")
    if unit_mass_kg is None or factor is None:
        return None
    return round(2.0 * distance_km * (unit_mass_kg / 1000.0) * factor, 4)


def listing_id_for(material_id: str, source_url: str) -> str:
    """Stable listing id = archetype id + short hash of its source url.

    One archetype can have several scraped listings (different supplier urls); the hash
    keeps them distinct and stable across runs (so a hold's listing_id is reproducible).
    """
    h = hashlib.sha1((source_url or material_id).encode("utf-8")).hexdigest()[:8]
    return f"{material_id}--{h}"


def canonical_item(listing: dict, archetype: dict) -> dict:
    """Build the frontend MaterialItem from a snapshot listing + its frozen archetype.

    Every number carries a tier: quantity ASSUMED (scraped availability, not a datasheet),
    distance from the listing's DERIVED/GROUNDED route, carbon ASSUMED (transport-only),
    pin DERIVED/ASSUMED. weakest-input-wins is applied by the caller for aggregates.
    """
    material_id = listing["material_id"]
    qty = listing.get("qty_available")
    distance_km = listing.get("distance_km")
    distance_tier = listing.get("distance_tier", "ASSUMED")
    source = archetype.get("source", "")
    pin, pin_tier = supplier_pin(source)
    supplier = source.split(",")[0].strip() if source else "Unknown supplier"
    mtype = "struct" if archetype.get("type") == "STRUCT" else "membr"
    return {
        "id": listing_id_for(material_id, listing.get("source_url", "")),
        "materialId": material_id,
        "name": archetype.get("name", material_id),
        "type": mtype,
        "quantity": qty,
        "unit": archetype.get("unit", ""),
        "quantityTier": "ASSUMED",
        "distanceKm": distance_km,
        "distanceTier": distance_tier,
        "transportCarbonKg": transport_carbon_kg(archetype, qty, distance_km),
        "transportCarbonPerUnitKg": transport_carbon_per_unit_kg(archetype, distance_km),
        "transportCarbonTier": "ASSUMED",
        "origin": source,
        "supplier": supplier,
        "supplierId": supplier_slug(supplier),
        "sourceUrl": listing.get("source_url", ""),
        "availability": listing.get("availability", "unknown"),
        "lonLat": pin,
        "lonLatTier": pin_tier,
        "solarTransmissivity": archetype.get("solar_transmissivity"),
    }


def _availability_rank(a: str) -> int:
    """available > unknown > out_of_stock — a product with ANY in-stock variant is available."""
    return {"available": 2, "unknown": 1, "out_of_stock": 0}.get(a, 1)


def dedupe(items: list[dict]) -> list[dict]:
    """Collapse listings that are the SAME physical listing into one golden record.

    Same ``id`` == same (archetype, source_url) — which is exactly how a Shopify product's
    N variants arrive (one listing per variant, identical source_url). Deterministic
    field-level survivorship (research §04): quantity = SUM of known variant quantities
    (additive stock of one product), distance/carbon/pin/name identical within a group,
    availability = the strongest variant. Records ``listingsRolledUp`` per record and never
    silently drops — ``sum(listingsRolledUp) == len(items_in)`` (conservation).
    """
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for it in items:
        if it["id"] not in groups:
            groups[it["id"]] = []
            order.append(it["id"])
        groups[it["id"]].append(it)

    golden: list[dict] = []
    for gid in order:
        members = groups[gid]
        head = dict(members[0])  # archetype-derived fields are identical across the group
        qtys = [m["quantity"] for m in members if isinstance(m["quantity"], (int, float))]
        head["quantity"] = sum(qtys) if qtys else None
        head["availability"] = max((m["availability"] for m in members), key=_availability_rank)
        head["transportCarbonKg"] = (
            transport_carbon_kg(load_archetypes()[head["materialId"]], head["quantity"], head["distanceKm"])
            if head["quantity"] is not None else None
        )
        head["listingsRolledUp"] = len(members)
        golden.append(head)
    return golden


def aggregate_by_archetype(listings: list[dict]) -> list[dict]:
    """Roll deduped listings up to ONE card per archetype (the browse granularity).

    The 10-archetype model means many distinct scraped products bind to the same material
    type; showing 57 identical "Scaffold Tube" rows is noise. This collapses them to one
    card per material with aggregate facts (nearest distance, supplier count, summed known
    quantity) AND the bindable underlying ``listings`` (sorted nearest-first) so a hold
    still binds ONE specific supplier's listing — the aggregate never hides which.
    """
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for it in listings:
        if it["materialId"] not in groups:
            groups[it["materialId"]] = []
            order.append(it["materialId"])
        groups[it["materialId"]].append(it)

    cards: list[dict] = []
    for mid in order:
        members = groups[mid]
        with_dist = [m for m in members if m["distanceKm"] is not None]
        nearest = min(with_dist, key=lambda m: m["distanceKm"]) if with_dist else members[0]
        qtys = [m["quantity"] for m in members if isinstance(m["quantity"], (int, float))]
        supplier_ids = sorted({m["supplierId"] for m in members})
        head = dict(members[0])
        head.update({
            "id": mid,                      # card id = archetype id (browse-level)
            "materialId": mid,
            "quantity": sum(qtys) if qtys else None,
            "distanceKm": nearest["distanceKm"],
            "distanceTier": nearest["distanceTier"],
            "lonLat": nearest["lonLat"],
            "lonLatTier": nearest["lonLatTier"],
            "supplier": nearest["supplier"],
            "supplierId": nearest["supplierId"],
            "availability": max((m["availability"] for m in members), key=_availability_rank),
            "listingCount": len(members),
            "supplierCount": len(supplier_ids),
            "transportCarbonKg": (
                transport_carbon_kg(load_archetypes()[mid], sum(qtys), nearest["distanceKm"])
                if qtys else None
            ),
            # the bindable underlying listings (a hold binds ONE of these), nearest first
            "listings": sorted(
                ({"id": m["id"], "supplier": m["supplier"], "supplierId": m["supplierId"],
                  "distanceKm": m["distanceKm"], "quantity": m["quantity"],
                  "availability": m["availability"], "sourceUrl": m["sourceUrl"]} for m in members),
                key=lambda x: (x["distanceKm"] is None, x["distanceKm"] or 0),
            ),
        })
        cards.append(head)
    return cards


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle km between two [lon, lat] points (radius filter only — pins are coarse)."""
    from math import asin, cos, radians, sin, sqrt

    lon1, lat1, lon2, lat2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(h))


def read_snapshots(project_id: str, projects_root: Path | str = "projects") -> tuple[list[dict], str, str | None]:
    """Read persisted per-source snapshots -> (listings, aggregate_status, as_of).

    Aggregate status is WEAKEST-INPUT-WINS across sources: any ``live`` source with stock
    makes the view live; else any ``stale_snapshot`` -> stale (with the newest fetched_at
    as ``as_of``); else ``unavailable``. Never a fake "live" — no snapshots dir yields
    ``unavailable`` (the inventory stage simply hasn't run), never a fabricated list.
    """
    inv_dir = Path(projects_root) / project_id / "inventory"
    listings: list[dict] = []
    statuses: list[str] = []
    as_of: str | None = None
    if inv_dir.is_dir():
        for latest in sorted(inv_dir.glob("*/latest.json")):
            try:
                snap = json.loads(latest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            statuses.append(snap.get("status", "unavailable"))
            fetched = snap.get("fetched_at")
            if fetched and (as_of is None or fetched > as_of):
                as_of = fetched
            for lst in snap.get("listings", []):
                listings.append(lst)
    if any(s == "live" for s in statuses) and listings:
        status = "live"
    elif any(s == "stale_snapshot" for s in statuses) and listings:
        status = "stale_snapshot"
    else:
        status = "unavailable"
    return listings, status, as_of


def build_catalog(
    project_id: str,
    *,
    center: tuple[float, float] | None = None,
    radius_km: float | None = None,
    group: str = "archetype",
    projects_root: Path | str = "projects",
    store=None,
) -> dict:
    """Serve projection: snapshot listings -> canonical MaterialItems (+ optional pool seed).

    Joins archetypes, computes carbon, derives pins, applies a radius filter (transport-
    carbon thesis — never surface material too far to be viable), and — when a HoldStore
    is passed — registers each listing's bindable pool so a hold can BIND real stock.

    Returns ``{status, as_of, items}`` matching the frontend ``MaterialsResult``.
    """
    archetypes = load_archetypes()
    raw, status, as_of = read_snapshots(project_id, projects_root)
    site = center or _SITE_LONLAT

    # 1) raw canonical items (one per snapshot listing / Shopify variant).
    raw_items = [
        canonical_item(listing, archetypes[listing["material_id"]])
        for listing in raw
        if listing.get("material_id") in archetypes
    ]
    # 2) DEDUPE to golden records (collapse variants of the same listing).
    items = dedupe(raw_items)

    # 3) radius filter (transport-carbon thesis — never surface material too far). Road
    #    distance when known; else the coarse supplier-pin haversine.
    def _within(it: dict) -> bool:
        if radius_km is None:
            return True
        if it["distanceKm"] is not None:
            return it["distanceKm"] <= radius_km
        return _haversine_km(tuple(it["lonLat"]), site) <= radius_km

    listings = [it for it in items if _within(it)]

    # 4) seed the bindable pool per surviving LISTING (always at listing granularity —
    #    a hold binds one supplier's listing, regardless of how we group for display).
    if store is not None:
        for it in listings:
            qty = it["quantity"]
            total = float(qty) if isinstance(qty, (int, float)) and qty > 0 else 1.0
            store.register_listing(
                it["id"], total_units=total, material_id=it["materialId"],
                supplier_id=it["supplierId"], unit=it["unit"], source_url=it["sourceUrl"],
            )

    # 5) display granularity: one card per archetype (default, the browse view) or the raw
    #    deduped per-listing view.
    items = aggregate_by_archetype(listings) if group == "archetype" else listings

    return {
        "status": status,
        "as_of": as_of,
        "items": items,
        "raw_count": len(raw_items),     # listings before variant-dedup (transparency)
        "listing_count": len(listings),  # distinct bindable listings after dedup
        "count": len(items),             # cards served (archetypes, or listings if group=listing)
    }


# Map ledger field names -> the per-spec provenance keys the frontend card reads.
_PROV_FIELDS = {
    "solarTransmissivity": "solar_transmissivity",
    "unitMassKg": "unit_mass_kg",
    "thicknessMm": "thickness_mm",
    "maxSpanMeters": "max_span_meters",
    "costPerUnit": "cost_per_unit",
    "distanceKm": "distance_km",
    "transportCarbonPerUnitKg": "transport_mode_factor",
}


def reference_catalogue(
    project_id: str,
    *,
    projects_root: Path | str = "projects",
    store=None,
) -> dict:
    """The FULL material catalogue (every archetype) with datasheet-sourced specs +
    per-field provenance — what the Materials stage shows so the organiser can SEE the
    whole reclaimed-material reference, not only the (few) archetypes a live scrape has
    bound. Each card carries ``bindable`` (true iff a live listing exists for it, with a
    ``bindListingId`` a hold can reserve); the rest are honest REFERENCE entries (real
    sourced specs, no live stock yet — reservable once a supplier onboards that stream).
    """
    archetypes = load_archetypes()
    prov = load_provenance()
    # Live bindable cards (also seeds the hold pools) — the SCRAPE bindability source.
    live = build_catalog(project_id, group="archetype", projects_root=projects_root, store=store)
    live_by_mid = {it["materialId"]: it for it in live["items"]}
    # ONBOARDED bindability: a supplier who listed stock makes that archetype reservable
    # even with no scrape feed (the "Uber for Materials" supply side). material_id -> pools.
    onboarded = store.available_listings_by_material() if store is not None else {}

    cards: list[dict] = []
    for mid, arch in archetypes.items():
        livecard = live_by_mid.get(mid)
        onb = onboarded.get(mid)
        dist = livecard["distanceKm"] if livecard else arch.get("lca_profile", {}).get("distance_km")
        pin, pin_tier = supplier_pin(arch.get("source", ""))
        if livecard:
            pin = livecard["lonLat"]
        t = arch.get("solar_transmissivity")
        source = arch.get("source", "")
        mled = prov.get(mid, {})
        # bindability: scrape listing first, else an onboarded supplier's listing.
        bind_listing_id = None
        bind_source = "reference"
        if livecard and livecard.get("listings"):
            bind_listing_id = livecard["listings"][0]["id"]
            bind_source = "scrape"
        elif onb:
            bind_listing_id = onb[0]["listing_id"]
            bind_source = "onboarded"
        cards.append({
            "id": mid,
            "materialId": mid,
            "name": arch.get("name", mid),
            "type": "struct" if arch.get("type") == "STRUCT" else "membr",
            "unit": arch.get("unit", ""),
            "solarTransmissivity": t,
            "shadePct": round((1.0 - t) * 100) if t is not None else None,
            "unitMassKg": arch.get("dimensions", {}).get("unit_mass_kg"),
            "thicknessMm": arch.get("dimensions", {}).get("thickness_mm"),
            "maxSpanMeters": arch.get("usage_conditions", {}).get("max_span_meters"),
            "waterproof": arch.get("usage_conditions", {}).get("waterproof"),
            "costPerUnit": arch.get("cost_per_unit"),
            "distanceKm": dist,
            "transportCarbonPerUnitKg": transport_carbon_per_unit_kg(arch, dist),
            "origin": source,
            "supplier": source.split(",")[0].strip() if source else "Unknown supplier",
            "lonLat": pin,
            "provenance": {
                key: mled.get(field, {}).get("tier", "DECLARED")
                for key, field in _PROV_FIELDS.items()
            },
            "provenanceSources": {
                key: mled.get(field, {}).get("source", "")
                for key, field in _PROV_FIELDS.items()
            },
            "bindable": bind_listing_id is not None,
            "bindListingId": bind_listing_id,
            "bindSource": bind_source,  # scrape | onboarded | reference
            "availability": (
                livecard["availability"] if livecard
                else "available" if onb else "reference"
            ),
            "quantity": (
                livecard["quantity"] if livecard
                else (round(onb[0]["available_units"]) if onb else None)
            ),
            "listingCount": (
                livecard.get("listingCount", 0) if livecard else (len(onb) if onb else 0)
            ),
            "supplierCount": (
                livecard.get("supplierCount", 0) if livecard
                else (len({o["supplier_id"] for o in onb}) if onb else 0)
            ),
        })

    # struct first (frames), then by best cooling (lowest transmissivity), then nearest.
    cards.sort(key=lambda c: (
        0 if c["type"] == "struct" else 1,
        c["solarTransmissivity"] if c["solarTransmissivity"] is not None else 0.0,
        c["distanceKm"] if c["distanceKm"] is not None else 1e9,
    ))
    return {
        "status": live["status"],
        "as_of": live["as_of"],
        "items": cards,
        "count": len(cards),
        "bindable_count": sum(1 for c in cards if c["bindable"]),
    }
