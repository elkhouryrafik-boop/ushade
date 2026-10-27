"""RED Nyquist scaffold for the Phase-5 Material Recovery Inventory (D-09, Q1, MAT-02).

These tests are EXPECTED TO FAIL RED at collection: the modules under test
(``inventory.classifier``, ``inventory.routing``, ``inventory.inventory``) do NOT exist
yet — Plan 02 wires the real implementations. This scaffold locks the contract every later
plan is verified against; when Plan 02 ships ``src/inventory/*`` these tests turn GREEN with
NO test edits (mirror how ``test_climate.py`` was designed-RED on ``climate.climate``).

The fake fetcher + sample-listing fixtures are real and live in ``tests/conftest_inventory.py``
(imported explicitly below — pytest only auto-loads ``conftest.py``). The fake exists ONLY in
tests (Pitfall 8): it is never a run path.

NOTE (Plan 02): the import names below are the ASSUMED entrypoints —
``classify(listing) -> {"material_id": ...} | {"status": "rejected", "reason": ...}``,
``road_distance_km`` / ``great_circle_km`` (DERIVED road route vs great-circle, Q2),
``run_inventory_stage(source_id, *, fetcher, projects_root, ...)`` (cache-first, degrade-
labelled). If Plan 02 picks different names/signatures, update the imports here in lock-step.
"""

from __future__ import annotations

import pytest

from conftest_inventory import (  # noqa: F401 (explicit import; real fixtures)
    BCN_AGENDA_RECORDS,
    FakeFetcher,
    fake_fetcher,
    sample_listings,
)

# RED: these imports fail until Plan 02 ships src/inventory/*. The whole module fails at
# collection — correct for a Wave 0 scaffold (05-VALIDATION §Wave 0 Requirements).
from inventory.classifier import classify  # noqa: E402
from inventory.routing import road_distance_km, great_circle_km  # noqa: E402
from inventory.inventory import run_inventory_stage  # noqa: E402

# A known supplier->site pair: Polinyà (demo supplier) -> Parc del Fòrum. Research Q2 verified the
# road route (~23.2 km) is materially LONGER than the great-circle (~16 km) — the frozen
# materials.json distance_km is ROAD, so DERIVED inventory distance MUST be a road route.
POLINYA = (41.5576, 2.1567)   # (lat, lon), Nominatim-verified
PARC_DEL_FORUM = (41.4106, 2.2203)  # materials.json _meta.site_coords


# --------------------------------------------------------------------------- #
# MAT-02 — distance is a ROAD route (DERIVED), not a great-circle / Euclidean delta
# --------------------------------------------------------------------------- #
def test_distance_is_road_route():
    """MAT-02 / Pitfall 4: the DERIVED distance is a ROAD route strictly longer than the
    great-circle for Polinyà -> Parc del Fòrum (a haversine guess would understate carbon
    and break parity with the frozen ROAD distance_km)."""
    road = road_distance_km(POLINYA, PARC_DEL_FORUM)
    crow = great_circle_km(POLINYA, PARC_DEL_FORUM)
    assert road > crow, (
        "road route must exceed great-circle distance (frozen distance_km is ROAD, "
        "never haversine)"
    )


# --------------------------------------------------------------------------- #
# D-09 — ambiguous listing rejected-with-reason, never silently dropped or guessed
# --------------------------------------------------------------------------- #
def test_classifier_rejects_ambiguous(sample_listings):
    """D-09: a listing carrying BOTH a structural and a membrane keyword (or no resolvable
    class) is REJECTED with a non-empty reason — never bound to a frozen type by guess."""
    ambiguous = sample_listings[2]  # "Lona para andamio — tarp scaffold sheet"
    result = classify(ambiguous)
    assert result.get("status") == "rejected", "ambiguous coarse class must be rejected"
    assert result.get("reason"), "a rejection must carry a non-empty reason (never silent)"


# --------------------------------------------------------------------------- #
# GREENWASH REGRESSION (2026-06-22): apparel "shrink" must NOT bind to the maritime
# yacht-shrink-wrap shade material. A bare "shrink" token (dressmaking deadstock) once
# false-bound 117 fabricsight apparel listings to membr-pe-yacht-shrinkwrap — surfacing
# apparel as shade (breaks the honesty rule). The rule now requires a marine/PE qualifier.
# --------------------------------------------------------------------------- #
def test_apparel_shrink_does_not_bind_yacht_shrinkwrap():
    """Apparel listings with a 'shrink' token but no marine/PE context must be rejected,
    while a real PE/marine shrink-wrap listing still binds."""
    for title in (
        "Pre-shrunk cotton jersey deadstock",
        "Shrink-resistant viscose dress fabric",
        "Anti-shrink wool textile remnant",
    ):
        result = classify({"raw_title": title, "body": "fabric textile deadstock"})
        assert result.get("status") == "rejected", f"apparel must not bind: {title!r}"
    # a genuine marine shrink-wrap listing still binds (no false NEGATIVE)
    real = classify({"raw_title": "Boat shrink wrap PE film", "body": "marine yacht"})
    assert real.get("material_id") == "membr-pe-yacht-shrinkwrap"


def test_atlas_archetypes_bind():
    """Each 2026-06-22 atlas-sourced archetype is reachable by a representative listing
    (the scrape→archetype binding contract for the unfrozen catalog)."""
    cases = {
        "struct-reclaimed-steel-ibeam": ("Reclaimed steel I-beam IPE200", "girder"),
        "struct-corten-container-panel": ("Shipping container corten side panel", "corten"),
        "membr-marine-sailcloth": ("Reclaimed marine sailcloth", "dacron sail"),
        "membr-pp-cargo-net": ("Polypropylene cargo net", "cargo mesh"),
        "membr-recycled-hdpe-sheet": ("Recycled HDPE sheet 4mm", "polyethylene panel"),
        "membr-recycled-shade-cloth": ("Knitted shade cloth 70%", "shade-cloth"),
    }
    for expected_id, (title, body) in cases.items():
        result = classify({"raw_title": title, "body": body})
        assert result.get("material_id") == expected_id, (
            f"{title!r} should bind {expected_id}, got {result}"
        )


# --------------------------------------------------------------------------- #
# D-09 (load-bearing #4) — never-silent-drop conservation
# --------------------------------------------------------------------------- #
def test_never_silent_drop_conservation(sample_listings):
    """LOAD-BEARING #4 (D-09): feed N listings (some unparseable); assert
    accepted + rejected == N and every rejection carries a non-empty reason. Nothing
    vanishes — the inventory-stage analogue of the Phase-3 infeasibility report."""
    accepted: list[dict] = []
    rejected: list[dict] = []
    for listing in sample_listings:
        result = classify(listing)
        if result.get("status") == "rejected":
            rejected.append(result)
        else:
            accepted.append(result)
    assert len(accepted) + len(rejected) == len(sample_listings), (
        "conservation: accepted + rejected must equal the number scraped (no silent drop)"
    )
    assert rejected, "the sample set intentionally contains unparseable/ambiguous listings"
    for r in rejected:
        assert r.get("reason"), "every rejection must carry a non-empty reason"


# --------------------------------------------------------------------------- #
# Q1 — fetch failure degrades to a LABELLED status, never a silent empty 'live'
# --------------------------------------------------------------------------- #
def test_degrade_labelled_not_silent(tmp_path):
    """Q1 / Pitfall 5: a fetch failure must yield status stale_snapshot or unavailable —
    NEVER an empty ``listings:[]`` with status 'live' (which the gate would read as
    'nothing available')."""
    failing = FakeFetcher(fail=True)
    snapshot = run_inventory_stage(
        "exoandamiajes",
        fetcher=failing,
        projects_root=tmp_path,
    )
    assert snapshot["status"] in ("stale_snapshot", "unavailable"), (
        "a failed fetch must be labelled stale_snapshot|unavailable, never empty 'live'"
    )
    assert snapshot["status"] != "live", "a failed fetch is NEVER reported as live"


# --------------------------------------------------------------------------- #
# Q1 (Option A) — fetch SUCCEEDS but classifier binds 0 -> labelled unavailable,
# never an empty 'live' (the live thefabricsales "reachable but 0 frozen-id" case)
# --------------------------------------------------------------------------- #
class _ZeroBindFetcher:
    """A fetcher whose payload is REAL-shaped (N>0 raw listings) but binds to NO frozen
    id — every listing is rejected-with-reason by the deterministic classifier.

    Mirrors the live ``thefabricsales`` finding: ~750 real deadstock listings scrape
    successfully, yet none of the source's catalog matches one of the 10 frozen
    ``data/materials.json`` ids. The titles below carry a membrane coarse-class keyword
    (``fabric``/``textile``) so Stage A resolves, but match NO Stage-B frozen rule ->
    ``reason="no frozen type matched"`` (a non-empty rejection, never a silent drop).
    """

    def __init__(self):
        self.call_count = 0

    def fetch(self, source_id: str, query: dict | None = None):
        self.call_count += 1
        return {
            "products": [
                {
                    "title": "Silk Chiffon Fabric — Designer Deadstock",
                    "product_type": "Fabric",
                    "handle": "silk-chiffon",
                    "body_html": "Lightweight silk chiffon textile, deadstock roll.",
                    "variants": [{"price": "9.00", "available": True, "grams": 40}],
                },
                {
                    "title": "Organic Cotton Twill Textile",
                    "product_type": "Fabric",
                    "handle": "cotton-twill",
                    "body_html": "Heavyweight organic cotton twill fabric.",
                    "variants": [{"price": "12.50", "available": True, "grams": 320}],
                },
            ]
        }


def test_fetch_success_zero_bind_is_unavailable_never_empty_live(tmp_path):
    """Option A (Q1 / Pitfall 5 never-silent-empty-success): a fetch that SUCCEEDS with
    N>0 raw listings but binds 0 to a frozen id must yield ``status != "live"`` (a
    labelled ``unavailable``) with empty ``listings`` and a NON-EMPTY ``rejected[]`` —
    never an empty ``status="live"`` the gate would read as 'live but nothing available'.

    This is the regression for the live ``thefabricsales`` discrepancy: reachable, ~750
    real listings scraped, 0 bound to one of the 10 frozen ids."""
    fetcher = _ZeroBindFetcher()
    snapshot = run_inventory_stage(
        "thefabricsales",
        fetcher=fetcher,
        projects_root=tmp_path,
    )

    assert fetcher.call_count >= 1, "the fetch must have actually run (reachable source)"
    assert snapshot["status"] != "live", (
        "a fetch that binds 0 frozen-id listings is NEVER reported as empty 'live'"
    )
    assert snapshot["status"] == "unavailable", (
        "reachable-but-0-bound is the labelled 'unavailable' state (Option A)"
    )
    assert snapshot["listings"] == [], "no frozen-id stock found -> empty listings"
    # Conservation preserved: every scraped-but-rejected listing is recorded with a reason.
    assert snapshot["rejected"], (
        "the rejected[] records must be carried (conservation: accepted+rejected==scraped)"
    )
    for r in snapshot["rejected"]:
        assert r.get("reason"), "every rejection must carry a non-empty reason (never silent)"


# --------------------------------------------------------------------------- #
# Q1 — cache hit performs ZERO live calls
# --------------------------------------------------------------------------- #
def test_cache_hit_no_live_call(tmp_path):
    """Q1: a second run over the same query hash is served from the persisted snapshot —
    the fake fetcher's call_count is UNCHANGED (cache-first, mirror the climate stage)."""
    fetcher = FakeFetcher()
    run_inventory_stage("thefabricsales", fetcher=fetcher, projects_root=tmp_path)
    after_first = fetcher.call_count
    assert after_first >= 1, "the first run must perform at least one live fetch"
    run_inventory_stage("thefabricsales", fetcher=fetcher, projects_root=tmp_path)
    assert fetcher.call_count == after_first, (
        "a cache hit must perform ZERO additional live calls (call_count unchanged)"
    )


# --------------------------------------------------------------------------- #
# MA-01 — a non-numeric Shopify price string must NOT crash the stage; the listing
# is recorded with price unknown (None), never a raw ValueError escaping the
# InventoryFetchError degrade handler.
# --------------------------------------------------------------------------- #
class _BadPriceFetcher:
    """A Shopify-shaped fetcher whose variant price is non-numeric ("N/A"/"") — real
    stores emit this for sold-out/draft variants. A raw float() would crash the stage."""

    def __init__(self):
        self.call_count = 0

    def fetch(self, source_id: str, query: dict | None = None):
        self.call_count += 1
        return {
            "products": [
                {
                    "title": "Recycled PE Tarpaulin Sheet",
                    "product_type": "Tarpaulin",
                    "handle": "pe-tarp",
                    "body_html": "Recycled polyethylene tarp membrane sheet.",
                    "variants": [
                        {"price": "N/A", "available": True, "grams": 250},
                        {"price": "", "available": False, "grams": 250},
                    ],
                }
            ]
        }


def test_non_numeric_price_does_not_crash_stage(tmp_path):
    """MA-01: a non-numeric Shopify price must degrade to price unknown (None), never a
    ValueError escaping the InventoryFetchError handler and crashing the stage."""
    fetcher = _BadPriceFetcher()
    # Must not raise; the stage returns a labelled snapshot (live/unavailable), not a crash.
    snapshot = run_inventory_stage(
        "thefabricsales",
        fetcher=fetcher,
        projects_root=tmp_path,
    )
    assert snapshot["status"] != "live" or isinstance(snapshot.get("listings"), list), (
        "a non-numeric price must yield a valid labelled snapshot, never a raw crash"
    )

    from inventory.adapters import _safe_float  # noqa: PLC0415

    assert _safe_float("N/A") is None
    assert _safe_float("") is None
    assert _safe_float(None) is None
    assert _safe_float("12.50") == 12.50


# --------------------------------------------------------------------------- #
# MA-02 — a non-numeric scraped dimension must NOT crash the classifier; it is
# treated as ABSENT (gate not contradicted), conservation preserved.
# --------------------------------------------------------------------------- #
def test_non_numeric_dimension_does_not_crash_classifier():
    """MA-02: a non-numeric dimension string (e.g. "~48mm") must be treated as absent
    (gate not contradicted), never a ValueError out of classify()."""
    from inventory.classifier import _safe_float_dim, _dimension_gate_ok  # noqa: PLC0415

    assert _safe_float_dim("~48mm") is None
    assert _safe_float_dim("N/A") is None
    assert _safe_float_dim(None) is None
    assert _safe_float_dim("48") == 48.0

    gate = {"kind": "diameter_mm", "values": [48.3], "tol": 1.0}
    # A non-numeric diameter must be "not contradicted" (True), never raise.
    bad = {"dimensions_mm": {"diameter": "~48mm"}}
    assert _dimension_gate_ok(gate, bad) is True

    # classify() over a listing with a garbage dimension must not raise.
    listing = {
        "raw_title": "Tubo de andamio multidireccional",
        "body": "tubo de acero galvanizado para andamio",
        "product_type": "andamio",
        "dimensions_mm": {"diameter": "~48mm"},
    }
    result = classify(listing)  # must not raise a ValueError
    assert isinstance(result, dict)
    assert "material_id" in result or result.get("status") == "rejected"


# --------------------------------------------------------------------------- #
# MA-03 — the stale_snapshot degrade path WRITES the relabelled snapshot under the
# current input_hash so a subsequent same-key run is a cache hit (no re-fetch).
# --------------------------------------------------------------------------- #
class _OncePassThenFailFetcher:
    """Succeeds for the seeding query, fails (returns None) for every other query — so a
    last_good snapshot exists, then a later query degrades to a stale_snapshot."""

    def __init__(self, good_query):
        self.good_query = good_query
        self.call_count = 0

    def fetch(self, source_id: str, query: dict | None = None):
        self.call_count += 1
        if query == self.good_query:
            from conftest_inventory import SHOPIFY_PRODUCTS  # noqa: PLC0415

            return SHOPIFY_PRODUCTS
        return None  # failed fetch -> degrade


def test_stale_snapshot_is_cached_under_current_hash(tmp_path):
    """MA-03: when a fetch fails and a last_good snapshot exists, the relabelled
    stale_snapshot must be WRITTEN under the current input_hash — so a subsequent run on
    the same (source, query, day) triple is a cache hit and does NOT re-fetch live."""
    good_query = {"q": "seed"}
    outage_query = {"q": "outage"}
    fetcher = _OncePassThenFailFetcher(good_query)

    # 1) Seed a last_good snapshot (latest.json) via a successful fetch.
    run_inventory_stage(
        "thefabricsales", good_query, fetcher=fetcher, projects_root=tmp_path
    )
    seeded_calls = fetcher.call_count
    assert seeded_calls >= 1

    # 2) First outage run: live fetch fails -> degrade to stale_snapshot (one live attempt).
    snap1 = run_inventory_stage(
        "thefabricsales", outage_query, fetcher=fetcher, projects_root=tmp_path
    )
    assert snap1["status"] == "stale_snapshot", "an outage with a prior snapshot is stale_snapshot"
    after_outage1 = fetcher.call_count
    assert after_outage1 > seeded_calls, "the first outage run attempts a live fetch"

    # 3) Second outage run on the SAME outage_query: must be a CACHE HIT now (zero re-fetch),
    #    because the stale snapshot was persisted under the outage_query input_hash.
    snap2 = run_inventory_stage(
        "thefabricsales", outage_query, fetcher=fetcher, projects_root=tmp_path
    )
    assert snap2["status"] == "stale_snapshot"
    assert fetcher.call_count == after_outage1, (
        "the stale snapshot must be cached under the current input_hash so the next "
        "same-key run is a cache hit (no re-fetch / no LIVE_FETCH_CAP re-exhaustion)"
    )


# --------------------------------------------------------------------------- #
# SCHEDULED-SURPLUS (2026-06-23, V2C P2): the BCN festival-calendar source INFERS the
# standard reusable festival kit a teardown sheds, timed to the published end date. It
# binds to the SAME materials.json archetypes via the SHARED classifier (no new rule),
# is labelled ASSUMED tier, carries no quantity, and attaches a collect-before-landfill
# availability_window with end_date_proxy=true.
# --------------------------------------------------------------------------- #
_KIT_IDS = {
    "struct-alu-truss-h30v",
    "struct-heras-fence-panel",
    "struct-euro-pallet-epal",
    "membr-pp-festival-carpet",
}


def test_scheduled_surplus_binds_kit_as_assumed_with_window(tmp_path):
    """A dated festival record yields one ASSUMED-tier snapshot whose listings bind the four
    standard kit archetypes, each with a collect-before-landfill window (end_date_proxy=true),
    qty unknown (null), and availability 'unknown' (not yet torn down — never claimed in-stock)."""
    snapshot = run_inventory_stage(
        "bcn-festival-calendar",
        fetcher=FakeFetcher(),
        projects_root=tmp_path,
    )
    assert snapshot["status"] == "live"
    assert snapshot["provenance_tier"] == "ASSUMED", (
        "an inferred (not scraped) surplus snapshot must be labelled ASSUMED tier"
    )
    bound = {listing["material_id"] for listing in snapshot["listings"]}
    assert bound == _KIT_IDS, f"the four festival-kit archetypes must bind, got {bound}"
    for listing in snapshot["listings"]:
        assert listing["qty_available"] is None, "inferred surplus asserts NO quantity (ASSUMED band)"
        assert listing["availability"] == "unknown", "gear not yet torn down -> never in-stock"
        window = listing.get("availability_window")
        assert window, "every inferred listing must carry the collect-before-landfill window"
        assert window["from"] == "2026-06-08", "window opens at the published end date (data_fi)"
        assert window["until"] == "2026-06-11", "window closes at data_fi + TEARDOWN_WINDOW_DAYS (3)"
        assert window["end_date_proxy"] is True, "data_fi is a slipping planned date, never a hard expiry"


def test_scheduled_surplus_record_without_end_date_yields_no_listing(tmp_path):
    """A record with no parseable end date yields NO listings (the clock can't be computed) —
    only the single dated festival's four kit listings appear, never a windowless guess."""
    snapshot = run_inventory_stage(
        "bcn-festival-calendar",
        fetcher=FakeFetcher(),
        projects_root=tmp_path,
    )
    # BCN_AGENDA_RECORDS has 2 records, only 1 dated -> 1 festival x 4 kit items.
    assert len(snapshot["listings"]) == 4, (
        "only the dated festival yields listings; the undated record is filtered out honestly"
    )


def test_scheduled_surplus_provenance_marks_material_id_assumed(tmp_path):
    """The inferred binding is recorded ASSUMED in the ledger — never grounded as 'scraped'
    (that would be fabricated provenance for an inference)."""
    import json

    run_inventory_stage(
        "bcn-festival-calendar",
        fetcher=FakeFetcher(),
        projects_root=tmp_path,
    )
    ledger_path = tmp_path / "default" / "inventory" / "bcn-festival-calendar" / "provenance.json"
    assert ledger_path.exists(), "the stage must write a provenance ledger"
    entries = json.loads(ledger_path.read_text(encoding="utf-8"))
    rows = entries.get("entries", entries) if isinstance(entries, dict) else entries
    material_rows = [
        e for e in rows if isinstance(e, dict) and str(e.get("key", "")).endswith("_material_id")
    ]
    assert material_rows, "material_id provenance entries must exist"
    for e in material_rows:
        assert e.get("tier") == "ASSUMED", (
            f"inferred material_id must be ASSUMED, never GROUNDED 'scraped': {e}"
        )


def test_scheduled_surplus_degrades_labelled_not_silent(tmp_path):
    """A failed festival-calendar fetch degrades to a labelled unavailable snapshot — never an
    empty 'live' (the same never-silent-degrade discipline as every other source)."""
    snapshot = run_inventory_stage(
        "bcn-festival-calendar",
        fetcher=FakeFetcher(fail=True),
        projects_root=tmp_path,
    )
    assert snapshot["status"] in ("stale_snapshot", "unavailable")
    assert snapshot["status"] != "live"
