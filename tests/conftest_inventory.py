"""Reusable FAKE inventory fetcher + frozen-listing sample fixtures for the offline
Phase-5 Material Recovery Inventory suite (mirror of ``conftest_climate.py``).

The default Phase-5 test suite runs with NO live network: scraper adapters live behind
an injected fake fetcher exactly the way the climate stage injects ``FakeInfraredClient``.
This module imports NO scraping/network library — ``FakeFetcher`` is a pure-Python object
that mimics the exact call surface ``src/inventory`` will exercise and RECORDS what it was
called with (a ``call_count`` so the cache-hit test can assert ZERO live calls on a hit,
and a per-query last-args record). It also carries failure modes (``fail`` /
``raise_on_fetch``) so the degrade-to-snapshot path (status stale_snapshot|unavailable,
NEVER an empty 'live') can be exercised.

Pitfall 8 (NO mock data): this fake exists ONLY under tests/ — it is NEVER a run path.
The sample listing fixtures below are canned EXACTLY for the classifier/conservation tests
(a parseable scaffold listing + a parseable membrane listing + an ambiguous both-class
listing + an unparseable-dimensions listing), so the never-silent-drop conservation test
(accepted + rejected == scraped, every rejection carries a non-empty reason, D-09) has a
known input.

karpathy: one fake object, no mock framework, no real scraper/network import.
"""

from __future__ import annotations

import pytest

# --------------------------------------------------------------------------- #
# Canned source-shaped listing payloads (REAL site shapes, recorded — not synthetic
# inventory: these are fixtures that drive the deterministic classifier, never a run
# path). Shopify-shape mirrors The Fabric Sales / FabricSight /products.json; the
# Exoandamiajes shape mirrors the Joomla scaffold catalog rows.
# --------------------------------------------------------------------------- #

# Shopify /products.json shape (textile deadstock — membrane class).
SHOPIFY_PRODUCTS = {
    "products": [
        {
            "id": 1001,
            "title": "Recycled PE Tarpaulin — Designer Deadstock",
            "product_type": "Fabric",
            "handle": "recycled-pe-tarpaulin",
            "body_html": "Heavy-duty recycled polyethylene tarpaulin, lona PE.",
            "tags": ["deadstock", "tarp", "lona"],
            "variants": [
                {"id": 5001, "price": "2.40", "available": True, "grams": 160},
            ],
        }
    ]
}

# Exoandamiajes (Joomla) scaffold catalog shape — structural class.
EXOANDAMIAJES_LISTINGS = [
    {
        "title": "Andamio Europeo Tubo 48.3 mm",
        "product_type": "andamio",
        "source_url": "https://exoandamiajes.example/andamios/tubo-48",
        "body": "Tubo de andamio 48.3 mm de diámetro, acero galvanizado.",
        "price_eur": 11.5,
        "dimensions_mm": {"diameter": 48.3},
    }
]

# BCN open-data CKAN ``datastore_search`` record shape (the real cultural-agenda fields:
# ``denominacio`` + ``data_inici`` / ``data_fi``). The adapter INFERS standard festival kit
# from each dated record — NOT a product scrape (Pitfall 8: these are fixtures, never a run
# path). One record carries a parseable end date (yields kit listings); one has no end date
# (must yield zero listings — the collect-before-landfill clock can't be computed).
BCN_AGENDA_RECORDS = [
    {
        "denominacio": "a demo festival",
        "data_inici": "2026-06-04",
        "data_fi": "2026-06-08",
    },
    {
        "denominacio": "Festival sense data de fi",  # no end date -> no window -> no listings
        "data_inici": "2026-07-01",
        "data_fi": "",
    },
]


@pytest.fixture
def fake_fetcher() -> "FakeFetcher":
    """A fresh fake inventory fetcher (default success path).

    ``fake_fetcher.call_count`` starts at 0 and increments on every LIVE fetch; the
    cache-hit test asserts it does not change on a second run over the same query hash.
    """
    return FakeFetcher()


class FakeFetcher:
    """Pure-Python stand-in for an ``src/inventory`` live fetch adapter (NO real
    network/scraper import).

    Records ``call_count`` (number of LIVE dispatches) and ``last_query`` so the
    cache-first test (second run on the same query hash => call_count unchanged) and
    the degrade test (fetch failure => stale_snapshot|unavailable, never empty 'live')
    can assert against it.

    Args:
        fail: when True, ``fetch`` returns no payload / signals a failed fetch so the
            degrade-to-snapshot path is exercised (the stage must label the result
            stale_snapshot or unavailable — never an empty 'live').
        raise_on_fetch: when True, ``fetch`` raises (simulates a hard HTTP/parse error
            wrapped by the stage's typed InventoryFetchError).
    """

    def __init__(self, fail: bool = False, raise_on_fetch: bool = False):
        self.fail = fail
        self.raise_on_fetch = raise_on_fetch
        self.call_count = 0
        self.last_query: dict | None = None

    def fetch(self, source_id: str, query: dict | None = None):
        """Mimic a single live source fetch. Returns canned source-shaped data on the
        success path; raises or signals failure on the configured failure modes."""
        self.call_count += 1
        self.last_query = {"source_id": source_id, "query": query}
        if self.raise_on_fetch:
            raise RuntimeError(f"fake fetch error for {source_id}")
        if self.fail:
            return None  # signals a failed fetch -> stage degrades, never empty 'live'
        if source_id == "thefabricsales":
            return SHOPIFY_PRODUCTS
        if source_id == "exoandamiajes":
            return EXOANDAMIAJES_LISTINGS
        if source_id == "bcn-festival-calendar":
            return BCN_AGENDA_RECORDS
        return None


# --------------------------------------------------------------------------- #
# Sample listings for the deterministic classifier + never-silent-drop conservation
# test. A mix: one cleanly-parseable scaffold, one cleanly-parseable membrane, one
# ambiguous (both coarse classes), one unparseable (no resolvable dimensions/type).
# --------------------------------------------------------------------------- #
@pytest.fixture
def sample_listings() -> list[dict]:
    """Four raw listings: 2 bind cleanly, 2 must be rejected-with-reason.

    Drives ``test_never_silent_drop_conservation`` (accepted + rejected == 4, every
    rejection carries a non-empty reason) and ``test_classifier_rejects_ambiguous``.
    """
    return [
        {
            "raw_title": "Andamio Europeo Tubo 48.3 mm",
            "source_url": "https://exoandamiajes.example/andamios/tubo-48",
            "body": "Tubo de andamio 48.3 mm de diámetro.",
            "dimensions_mm": {"diameter": 48.3},
        },
        {
            "raw_title": "Recycled PE Tarpaulin — Deadstock lona PE",
            "source_url": "https://thefabricsales.example/products/recycled-pe-tarp",
            "body": "Recycled polyethylene tarpaulin, lona PE.",
            "areal_weight_g_m2": 160,
        },
        {
            # Ambiguous: carries BOTH a structural ("andamio") and a membrane ("lona")
            # keyword -> coarse class is ambiguous -> reject, never guess.
            "raw_title": "Lona para andamio — tarp scaffold sheet",
            "source_url": "https://exoandamiajes.example/listings/ambiguous",
            "body": "lona andamio tarp",
        },
        {
            # Unparseable: no resolvable coarse class / dimensions -> reject with reason.
            "raw_title": "Lote varios sin clasificar",
            "source_url": "https://exoandamiajes.example/listings/misc",
            "body": "miscelánea",
        },
    ]
