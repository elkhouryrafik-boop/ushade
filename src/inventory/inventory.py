"""Material Recovery Inventory stage — ``run_inventory_stage`` (D-05..D-09, Q1, MAT-02).

The integration seam that wires the three Phase-5 building blocks (adapters, classifier,
routing) into one cache-first stage emitting a contract-valid ``inventory_snapshot`` per
source. It clones the climate-stage discipline step-for-step:

  1. CACHE-FIRST. The cache key is the content hash of ``(source_id, query, day-bucket)``
     (mirror ``_site_input_hash`` + ``Manifest.is_reusable``). A cache HIT loads and
     returns the persisted snapshot with ZERO live fetch calls (Q1;
     ``test_cache_hit_no_live_call``).
  2. DEGRADE-LABELLED, NEVER SILENT. On an ``InventoryFetchError`` the stage returns the
     last-good snapshot labelled ``status="stale_snapshot"`` if one exists, else a
     ``status="unavailable"`` record — NEVER an empty ``status="live"`` (Q1 / Pitfall 5;
     ``test_degrade_labelled_not_silent``).
  3. VALIDATE-THEN-WRITE. ``validate(snapshot, "inventory_snapshot")`` runs BEFORE any
     byte hits disk, so an invalid/partial snapshot can never be persisted (mirror
     ``validate(artifact, _STAGE)``).
  4. NEVER-SILENT PROVENANCE. Each listing is GROUNDED (+source_url +fetched_at); the
     road distance is DERIVED; suitability/availability is ASSUMED (D-08, 4-tier ledger).
  5. CONSERVATION. ``classify_batch`` guarantees accepted+rejected == scraped, every
     rejection carrying a reason — persisted into the required ``rejected[]`` array.

The fake fetcher (tests) and the real ``HttpFetcher`` share the ``fetch(source_id,
query)`` surface; ``None`` from the fetcher means a failed fetch and degrades (never an
empty live). No API secret is read or logged here (routing owns the geocoder key).

karpathy: one linear orchestration function + a tiny per-source snapshot cache on disk.
No DAG engine, no scheduler, no retry loop.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# pythonpath=["src"] (pyproject) makes the sibling packages importable bare.
from inventory.adapters import (
    ASSUMED_TIER_SOURCES,
    InventoryFetchError,
    LiveFetchBudget,
    SOURCE_BASE_URLS,
    adapter_for,
)
from inventory.classifier import classify_batch
from inventory.routing import DERIVED as _ROUTE_DERIVED
from inventory.routing import GROUNDED as _ROUTE_GROUNDED
from inventory.routing import road_route
from manifest.manifest import content_hash
from provenance.ledger import ProvenanceLedger
from validate.validate import validate

_CONTRACT = "inventory_snapshot"
_SCHEMA_VERSION = "1.0.0"

# A per-(source, query) cache lives under <projects_root>/<project_id>/inventory/. The
# snapshot file name embeds the input hash (Q1.7 naming discretion); ``latest.json`` is
# the per-source pointer the selection gate reads.
_INVENTORY_DIR = "inventory"

# Supplier geocodes for the no-public-stock / routing path (05-RESEARCH §Q2, Nominatim-
# verified). Keyed by the frozen materials.json source town. Used to attach a DERIVED
# ROAD distance to a bound listing; absent towns degrade to the frozen GROUNDED fallback.
_SUPPLIER_COORDS: dict[str, tuple[float, float]] = {
    "polinya": (41.5576, 2.1567),  # demo scaffold supplier, demo industrial district
    "barcelona": (41.3874, 2.1686),  # generic Barcelona supplier centroid
    "terrassa": (41.5615, 2.0089),  # HDPE shade-net production, Terrassa
    "zona franca": (41.3380, 2.1340),  # Zona Franca logistics hub
    "mataro": (41.5390, 2.4440),  # demo plastics recycler, demo district
    "port": (41.3420, 2.1650),  # Port de Barcelona (marine sailcloth, container yards)
}

# Frozen materials.json distance_km fallback per material id (GROUNDED last resort —
# 05-RESEARCH §Q2 ladder step 4; never a haversine guess).
_FROZEN_DISTANCE_KM: dict[str, float] = {
    "struct-scaffold-tube-48": 25.0,
    "struct-alu-truss-h30v": 4.0,
    "struct-euro-pallet-epal": 12.0,
    "struct-heras-fence-panel": 10.0,
    "struct-stadium-chair": 3.0,
    "membr-pvc-billboard-vinyl": 15.0,
    "membr-hdpe-shade-net": 30.0,
    "membr-recycled-pe-tarp": 12.0,
    "membr-pe-yacht-shrinkwrap": 6.0,
    "membr-pp-festival-carpet": 8.0,
    # atlas-sourced (2026-06-22)
    "struct-reclaimed-steel-ibeam": 6.0,
    "struct-corten-container-panel": 7.0,
    "membr-marine-sailcloth": 6.0,
    "membr-pp-cargo-net": 32.0,
    "membr-recycled-hdpe-sheet": 6.0,
    "membr-recycled-shade-cloth": 30.0,
}

# Default supplier coord used to DERIVE a road distance when a listing's town is unknown.
# Polinyà is the verified routing case; using it keeps the DERIVED distance honest (a real
# road route) rather than fabricating a per-listing town we did not scrape.
_DEFAULT_SUPPLIER = (41.5576, 2.1567)


# --------------------------------------------------------------------------- #
# Cache key + paths
# --------------------------------------------------------------------------- #
def _day_bucket(now: datetime | None = None) -> str:
    """The UTC calendar-day bucket — a same-day re-run is a cache HIT (Q1)."""
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d")


def _input_hash(source_id: str, query: dict | None) -> str:
    """Content hash of (source_id, query, day-bucket) — the cache key (Pitfall D).

    A changed source OR query OR calendar day -> changed hash -> cache MISS -> re-fetch.
    """
    return content_hash(
        {"source_id": source_id, "query": query or {}, "day": _day_bucket()}
    )


def _source_dir(project_root: Path, project_id: str, source_id: str) -> Path:
    return project_root / project_id / _INVENTORY_DIR / source_id


def _snapshot_path(source_dir: Path, input_hash: str) -> Path:
    return source_dir / f"{input_hash}.json"


def _latest_path(source_dir: Path) -> Path:
    return source_dir / "latest.json"


def _load_snapshot(path: Path) -> dict | None:
    """Load a persisted snapshot, re-validating it against the contract; None on miss."""
    if not path.exists():
        return None
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        validate(snapshot, _CONTRACT)  # corrupt/edited snapshot -> miss (re-fetch)
    except Exception:
        return None
    return snapshot


# --------------------------------------------------------------------------- #
# Distance routing (DERIVED road route, frozen GROUNDED fallback)
# --------------------------------------------------------------------------- #
def _distance_for(material_id: str, supplier_town: str | None) -> tuple[float | None, str]:
    """Return ``(distance_km, distance_tier)`` for a bound listing.

    A DERIVED road route from the supplier town (or the verified default supplier) to
    Parc del Fòrum; on a routing failure, the frozen materials.json distance_km labelled
    GROUNDED — NEVER a haversine guess (Pitfall 4 / 05-RESEARCH §Q2 ladder).
    """
    coords = None
    if supplier_town:
        coords = _SUPPLIER_COORDS.get(supplier_town.strip().lower())
    if coords is None:
        coords = _DEFAULT_SUPPLIER
    try:
        km, tier = road_route(coords)
        return round(km, 3), tier
    except Exception:
        frozen = _FROZEN_DISTANCE_KM.get(material_id)
        return frozen, _ROUTE_GROUNDED


# --------------------------------------------------------------------------- #
# Snapshot assembly
# --------------------------------------------------------------------------- #
def _availability_of(listing: dict) -> str:
    """Map a listing's ``available`` flag to the contract availability enum.

    True -> available; missing flag -> unknown (D-07 — never assume out_of_stock when
    we simply do not know); explicit False -> out_of_stock.
    """
    avail = listing.get("available")
    if avail is True:
        return "available"
    if avail is False:
        return "out_of_stock"
    return "unknown"


def _build_live_snapshot(
    source_id: str, raw_listings: list[dict], fetched_at: str
) -> dict:
    """Classify + route raw listings into a contract-valid inventory_snapshot.

    HONEST EMPTY-AFTER-CLASSIFY (Option A, Q1 / Pitfall 5 never-silent-empty-success): a
    fetch can SUCCEED (N>0 raw listings scraped) yet bind ZERO listings to a frozen id
    (all rejected — e.g. ``thefabricsales`` deadstock carries no frozen-id-equivalent
    stock). That is NOT ``status="live", listings=[]`` (a forbidden silent empty success
    the gate would read as 'live but nothing available'). It is a LABELLED ``unavailable``
    state — reachable, but no frozen-id stock found — that PRESERVES conservation: the
    ``rejected[]`` records (accepted+rejected == scraped) are carried so the never-silent-
    drop seam still reads. No binding is ever fabricated (Option B rejected).
    """
    accepted, rejected = classify_batch(raw_listings)

    # A source whose listings are an INFERENCE (scheduled-surplus: festival -> standard kit),
    # not a scraped product, carries an ASSUMED snapshot tier — the festival + its teardown
    # date are real, but the material surplus is assumed (V2C P2, RISK_REGISTER R1-e).
    tier = "ASSUMED" if source_id in ASSUMED_TIER_SOURCES else "GROUNDED"

    # Fetch succeeded but bound 0 frozen-id listings -> labelled unavailable, never empty
    # 'live'. Empty raw input (genuinely nothing scraped) folds into the same honest state.
    if not accepted:
        snapshot = _unavailable_snapshot(source_id, fetched_at)
        snapshot["rejected"] = rejected  # preserve conservation (accepted+rejected==scraped)
        return snapshot

    listings: list[dict] = []
    for item in accepted:
        material_id = item["material_id"]
        src = item["listing"]
        distance_km, distance_tier = _distance_for(material_id, src.get("supplier_town"))
        price = src.get("price_eur")
        entry = {
            "material_id": material_id,
            "source_url": str(src.get("source_url") or SOURCE_BASE_URLS.get(source_id, "")),
            "fetched_at": str(src.get("fetched_at") or fetched_at),
            "availability": _availability_of(src),
            "price_eur": float(price) if isinstance(price, (int, float)) else None,
            "distance_km": distance_km,
            "distance_tier": distance_tier,
        }
        qty = src.get("qty_available")
        entry["qty_available"] = float(qty) if isinstance(qty, (int, float)) else None
        # Optional collect-before-landfill window (scheduled-surplus only); scrape adapters
        # omit it. Carried through verbatim so the contract's optional field stays honest.
        window = src.get("availability_window")
        if isinstance(window, dict):
            entry["availability_window"] = window
        listings.append(entry)

    return {
        "schema_version": _SCHEMA_VERSION,
        "source_id": source_id,
        "source_url": SOURCE_BASE_URLS.get(source_id, ""),
        "fetched_at": fetched_at,
        "status": "live",
        "provenance_tier": tier,
        "listings": listings,
        "rejected": rejected,
    }


def _unavailable_snapshot(source_id: str, fetched_at: str) -> dict:
    """A labelled ``unavailable`` snapshot — never an empty 'live' (Q1 / Pitfall 5).

    Two honest paths reach here, both ``unavailable`` (never empty 'live'):
      - a live fetch FAILED with no prior snapshot (the source's stock is UNKNOWN), or
      - a fetch SUCCEEDED but the classifier bound 0 listings to a frozen id (reachable,
        no frozen-id stock found — ``_build_live_snapshot`` overrides ``rejected[]`` here
        to preserve conservation).

    Either way the selection gate reads ``unavailable`` and never treats it as a definitive
    out-of-stock. ``rejected`` defaults to empty (the no-data path); the empty-after-classify
    caller replaces it with the real rejection records.
    """
    return {
        "schema_version": _SCHEMA_VERSION,
        "source_id": source_id,
        "source_url": SOURCE_BASE_URLS.get(source_id, ""),
        "fetched_at": fetched_at,
        "status": "unavailable",
        "provenance_tier": "ASSUMED",
        "listings": [],
        "rejected": [],
    }


def _write_snapshot(source_dir: Path, input_hash: str, snapshot: dict) -> None:
    """Validate-then-write the snapshot + refresh the per-source latest.json pointer."""
    validate(snapshot, _CONTRACT)  # gate: invalid never reaches disk
    source_dir.mkdir(parents=True, exist_ok=True)
    _snapshot_path(source_dir, input_hash).write_text(
        json.dumps(snapshot, indent=2), encoding="utf-8"
    )
    _latest_path(source_dir).write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


def _append_provenance(source_dir: Path, snapshot: dict) -> None:
    """Append per-field provenance (listing GROUNDED, distance DERIVED, availability ASSUMED).

    For an ASSUMED-tier source (scheduled-surplus) the binding is an INFERENCE, not a scrape,
    so the material_id is recorded ASSUMED ("inferred from festival teardown schedule") — never
    grounded as "scraped" (that would be fabricated provenance).
    """
    ledger = ProvenanceLedger()
    is_inferred = snapshot.get("provenance_tier") == "ASSUMED"
    stage = f"inventory_{snapshot['source_id']}"
    for i, listing in enumerate(snapshot.get("listings", [])):
        if is_inferred:
            ledger.assumed(
                f"listing_{i}_material_id",
                listing["material_id"],
                source=f"INFERRED festival-teardown surplus {listing.get('source_url','')} "
                f"(deterministic kit table; fetched {listing.get('fetched_at','')})",
                stage=stage,
            )
        else:
            ledger.grounded(
                f"listing_{i}_material_id",
                listing["material_id"],
                source=f"scraped listing {listing.get('source_url','')} (fetched {listing.get('fetched_at','')})",
                stage=stage,
            )
        if listing.get("distance_km") is not None:
            tier_helper = ledger.derived if listing.get("distance_tier") == _ROUTE_DERIVED else ledger.grounded
            tier_helper(
                f"listing_{i}_distance_km",
                listing["distance_km"],
                source="geocoded ROAD route Nominatim+OSRM, supplier -> Parc del Fòrum"
                if listing.get("distance_tier") == _ROUTE_DERIVED
                else "materials.json frozen distance_km (GROUNDED fallback)",
                stage=stage,
                unit="km",
            )
        ledger.assumed(
            f"listing_{i}_availability",
            listing["availability"],
            source="availability from scraped variants[].available (ASSUMED until datasheet)",
            stage=stage,
        )
    ledger.write(source_dir / "provenance.json")


# --------------------------------------------------------------------------- #
# The stage
# --------------------------------------------------------------------------- #
def run_inventory_stage(
    source_id: str,
    query: dict | None = None,
    *,
    project_id: str = "default",
    fetcher=None,
    projects_root: Path | str | None = None,
    budget: LiveFetchBudget | None = None,
) -> dict:
    """Run the inventory stage for one source: cache-first -> fetch -> classify -> route
    -> validate-then-write -> ground.

    Args:
        source_id: a verified source id (``exoandamiajes`` | ``thefabricsales`` | ...).
        query: optional query dict (folded into the cache key).
        project_id: the run id; artifacts live under ``<projects_root>/<project_id>/``.
        fetcher: an injected fetcher with ``fetch(source_id, query)`` (the offline test
            injects a ``FakeFetcher``; ``None`` -> the live ``HttpFetcher`` is built).
        projects_root: where ``<project_id>/`` lives (default ``projects/``).
        budget: an optional ``LiveFetchBudget`` (a fresh one is created if omitted).

    Returns:
        The ``inventory_snapshot`` dict (contract-valid). ``status`` is ``live`` on a
        successful fetch, ``stale_snapshot`` when a fetch failure degrades to a prior
        snapshot, or ``unavailable`` when a fetch fails with no prior snapshot — NEVER an
        empty ``live``.
    """
    project_root = Path(projects_root) if projects_root is not None else Path("projects")
    source_dir = _source_dir(project_root, project_id, source_id)
    input_hash = _input_hash(source_id, query)

    # ── 1) CACHE CHECK (decide whether to fetch at all) ───────────────────────
    cached = _load_snapshot(_snapshot_path(source_dir, input_hash))
    if cached is not None:
        # Cache hit: return the persisted snapshot with ZERO live fetch calls (Q1).
        return cached

    fetched_at = datetime.now(timezone.utc).isoformat()

    # ── 2) MISS: fetch via the injected (or live) fetcher, degrade-safe ────────
    budget = budget or LiveFetchBudget()
    if fetcher is None:
        from inventory.adapters import HttpFetcher  # noqa: PLC0415  (lazy, prod path)

        fetcher = HttpFetcher()

    adapter = adapter_for(source_id)
    try:
        raw_listings = adapter.fetch(fetcher, query, budget=budget)
        snapshot = _build_live_snapshot(source_id, raw_listings, fetched_at)
    except InventoryFetchError:
        # ── DEGRADE-LABELLED (never silent empty live) ────────────────────────
        last_good = _load_snapshot(_latest_path(source_dir))
        if last_good is not None:
            stale = dict(last_good)
            stale["status"] = "stale_snapshot"  # relabel REAL prior data, never fabricate
            # MA-03: persist the relabelled stale snapshot under THIS run's input_hash so a
            # subsequent same-(source, query, day) call is a cache hit — otherwise every run
            # during a persistent outage re-attempts a live fetch and re-exhausts LIVE_FETCH_CAP.
            # Best-effort: a write failure must NOT crash the degrade path (still return stale).
            try:
                _write_snapshot(source_dir, input_hash, stale)
            except Exception:
                pass
            return stale
        # No prior snapshot: persist + return a labelled unavailable record.
        snapshot = _unavailable_snapshot(source_id, fetched_at)
        _write_snapshot(source_dir, input_hash, snapshot)
        _append_provenance(source_dir, snapshot)
        return snapshot

    # ── 3) VALIDATE-THEN-WRITE + PROVENANCE (the success path) ────────────────
    _write_snapshot(source_dir, input_hash, snapshot)
    _append_provenance(source_dir, snapshot)
    return snapshot
