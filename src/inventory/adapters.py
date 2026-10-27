"""Live cache-first scrape adapters per verified source (D-05, Q1, Pitfall 8).

Real adapters over the instructor's live-verified sources — NO mock data (Pitfall 8;
the only non-live path is the stage's LABELLED last-good snapshot of REAL prior data).
Each adapter clones the climate network-seam discipline exactly:

  * a typed ``InventoryFetchError(RuntimeError)`` (mirror ``ClimateFetchError``) wraps
    any HTTP/parse failure and carries ``.cause``;
  * a ``LiveFetchBudget`` cap (mirror ``LiveCallBudget``, CCA-F P2) bounds live
    dispatches per run so a retry storm can't hammer a source (T-05-06);
  * the fetch library (httpx / scrapling) is imported LAZILY INSIDE the fetch method
    only (mirror ``_load_sdk``), so importing this module needs no network lib and the
    offline suite injects a fake fetcher;
  * adapter base URLs are a FIXED allow-list of the verified sources, never a
    user-supplied host (SSRF-safe, T-05-08);
  * no API secret is read or logged here (the routing module owns the geocoder key).

The injected ``fetcher`` (the test ``FakeFetcher`` in ``tests/conftest_inventory.py``,
or the real ``HttpFetcher`` below) exposes ``fetch(source_id, query) -> raw payload |
None``. ``None`` signals a failed fetch -> the adapter raises ``InventoryFetchError`` so
the STAGE degrades to a labelled stale_snapshot/unavailable (never a silent empty live).

karpathy: one Shopify adapter (instantiated twice) + one scrapling HTML adapter + a typed
error + a budget. No adapter framework, no plugin registry.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Hard cap on LIVE fetch dispatches per run (ASSUMED 3, mirror LIVE_CALL_CAP; CCA-F P2
# — a backstop against a pagination/retry loop, not the primary terminator).
# --------------------------------------------------------------------------- #
LIVE_FETCH_CAP: int = 3  # ASSUMED

# Fixed allow-list of verified source base URLs (SSRF-safe; never user-supplied).
SOURCE_BASE_URLS: dict[str, str] = {
    # Retained in the allow-list (SSRF guard) but NOT in the active demo scrape set — the
    # greenwash fix means these dressmaking-fabric shops now correctly reject every listing
    # (apparel is not shade stock). Kept so the "reachable but 0 frozen-id" + apparel-reject
    # regressions stay testable; never scraped for the live demo.
    "thefabricsales": "https://www.thefabricsales.com",
    "fabricsight": "https://fabricsight.com",
    "exoandamiajes": "https://www.exoandamiajes.com",
    "mascus": "https://www.mascus.es",
    # MachineryZone skipped (403 to a default UA — 05-RESEARCH §Q1); use Mascus instead.
    # --- Real shade/structure Shopify feeds (live-verified 2026-06-22, Phase-2 supplier
    # hunt). EU/UK e-commerce with working /products.json that carry genuine shade-capable
    # stock (NOT apparel). Distance is shown honestly (UK ≈ high transport carbon — the
    # carbon-transport-only model penalises it; that is truthful, not greenwash). The retired
    # apparel fabric shops (thefabricsales/fabricsight) are removed — they only produced noise.
    "proflextruss": "https://www.proflextruss.com",          # F34 aluminium truss / staging
    "tarpaulinsuppliesuk": "https://tarpaulinsuppliesuk.co.uk",  # shade net / PE tarp / agri net
    "tarpaulinsuk": "https://tarpaulinsuk.uk",               # PVC/PE tarpaulins
    # plastock (recycled HDPE sheet) was live-verified but DROPPED 2026-06-22: its broad
    # plastic catalog false-bound 1411 generic plastic "tubes" → scaffold-tube and 735 PVC
    # sheets → billboard-vinyl (no diameter/areal gate to stop them). Recycled-HDPE-sheet is
    # covered by supplier onboarding instead. Re-add only behind a stricter sheet/tube gate.
    # --- Scheduled-surplus source (2026-06-23, V2C "permit-driven material surplus" P2 slice).
    # The Barcelona open-data portal's cultural-agenda dataset (real, public, dated festivals).
    # NOT a product-listing scrape: this source INFERS the standard reusable festival kit a
    # teardown yields, timed to the event's published end date — so the snapshot is labelled
    # ASSUMED tier (see ASSUMED_TIER_SOURCES) and every inferred listing carries qty=null +
    # an availability_window with end_date_proxy=true. The honest "collect before landfill"
    # clock the engine lacked. The live resource_id is env-gated (never a guessed UUID).
    "bcn-festival-calendar": "https://opendata-ajuntament.barcelona.cat",
}

# Sources served by the Shopify /products.json adapter (vs the scrapling HTML adapter).
SHOPIFY_SOURCES: frozenset[str] = frozenset(
    {"thefabricsales", "fabricsight", "proflextruss", "tarpaulinsuppliesuk", "tarpaulinsuk"}
)

# Sources whose snapshot provenance_tier is ASSUMED, not GROUNDED — the listings are a
# deterministic INFERENCE (festival schedule -> standard festival kit), not a scraped product
# listing. The festival + its teardown date are real (GROUNDED source_url + fetched_at), but
# the material surplus is assumed, so the binding is marked ASSUMED in the ledger (never
# grounded as "scraped"). karpathy: a one-element set, not an adapter-capability framework.
ASSUMED_TIER_SOURCES: frozenset[str] = frozenset({"bcn-festival-calendar"})

# The deterministic festival teardown -> reusable-kit inference table (V2C 01-01-PLAN W2:
# "deterministic permit→material rule table", the LLM is ABSENT from this path). Each row is
# one piece of standard festival hardware a teardown reliably sheds; ``keywords`` are written
# so the SHARED classifier (classify_batch) binds each to exactly one materials.json id —
# truss, Heras fence, euro pallet, PP carpet — with NO new classifier rule (the scrape already
# owns these archetypes). No quantity is asserted (qty stays null: ASSUMED band, no ground
# truth — R1-e). Adding a kit item is a one-line edit here, never a model guess.
_FESTIVAL_KIT: tuple[dict, ...] = (
    {"label": "Aluminium truss (H30V)", "keywords": "aluminium truss celosia staging"},
    {"label": "Heras fence panel", "keywords": "heras fence panel valla perimetral"},
    {"label": "Euro pallet (EPAL)", "keywords": "euro pallet epal palet madera"},
    {"label": "PP festival carpet", "keywords": "festival carpet moqueta walkway"},
)

# ASSUMED collect-before-landfill window (days after the published end date before the gear is
# skipped/landfilled). Labelled ASSUMED — a typical teardown/clearance lag, not a measured one.
TEARDOWN_WINDOW_DAYS: int = 3  # ASSUMED

# BCN open-data dataset slug for the cultural agenda (the real, public source page the listing
# source_url points at). The DATASTORE resource_id needed for the live CKAN query is NOT
# hardcoded (a guessed UUID would be fabricated provenance) — it is read from the environment
# (CCA-F P7: config via ${ENV_VAR}) and confirmed by the 01-01-PLAN §8 spike before the live
# path is trusted. Offline, the FakeFetcher injects real CKAN-shaped records (tests).
_BCN_DATASET_SLUG = "agenda-cultural"
_BCN_RESOURCE_ID_ENV = "BCN_FESTIVAL_RESOURCE_ID"


# --------------------------------------------------------------------------- #
# Untrusted-value coercion (MA-01): third-party price strings are NOT guaranteed
# numeric (real Shopify stores emit "N/A"/""/"—" for sold-out or draft variants).
# A raw float() here would raise ValueError OUTSIDE the InventoryFetchError handler
# and crash the stage — so coerce defensively, returning None on any parse failure
# (price unknown is recorded honestly; the listing is never silently dropped).
# --------------------------------------------------------------------------- #
def _safe_float(v) -> float | None:
    """Coerce a third-party price string to float, returning None on any parse failure."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Typed failure (mirror ClimateFetchError)
# --------------------------------------------------------------------------- #
class InventoryFetchError(RuntimeError):
    """Typed wrapper for any inventory-fetch failure.

    The stage catches this to DEGRADE to a labelled stale_snapshot/unavailable
    snapshot — never a silent empty ``live``. Carries the original error as ``cause``.
    """

    def __init__(self, message: str, *, cause: BaseException | None = None):
        super().__init__(message)
        self.cause = cause


# --------------------------------------------------------------------------- #
# Live-fetch budget (mirror LiveCallBudget)
# --------------------------------------------------------------------------- #
class LiveFetchBudget:
    """Counts LIVE fetch dispatches and raises past the cap (T-05-06, fetch DoS).

    ``record(label)`` increments and raises ``InventoryFetchError`` once the count
    exceeds the cap. ``.n`` is exposed so tests/logs can read the live-fetch count.
    """

    def __init__(self, cap: int = LIVE_FETCH_CAP):
        self.cap = cap
        self.n = 0

    def record(self, label: str) -> None:
        self.n += 1
        if self.n > self.cap:
            raise InventoryFetchError(
                f"inventory live-fetch cap {self.cap} exceeded at {label}"
            )


# --------------------------------------------------------------------------- #
# Default (live) fetcher — the production path; lazily imports httpx/scrapling
# --------------------------------------------------------------------------- #
class HttpFetcher:
    """Default LIVE fetcher: GETs JSON / HTML from the real verified sources.

    Mirrors the ``FakeFetcher`` call surface (``fetch(source_id, query)``) so the
    adapters are identical offline and live. Imports httpx / scrapling LAZILY inside
    ``fetch`` (NEVER at module top) so the offline suite stays network-free. Returns the
    raw source payload (Shopify ``products`` JSON dict, or a list of Exoandamiajes
    listing dicts), or raises so the adapter surfaces an ``InventoryFetchError``.

    This is the ONLY run-path fetcher; the fake lives strictly under tests/ (Pitfall 8).
    """

    def __init__(self, *, user_agent: str = "HeatGuard/0.1 (material-recovery-inventory)"):
        self.user_agent = user_agent

    def fetch(self, source_id: str, query: dict | None = None):
        import httpx  # noqa: PLC0415  (lazy — keeps the offline import light)

        base = SOURCE_BASE_URLS.get(source_id)
        if base is None:
            raise InventoryFetchError(f"unknown source_id {source_id!r} (not in allow-list)")

        headers = {"User-Agent": self.user_agent}
        try:
            if source_id in SHOPIFY_SOURCES:
                # Shopify structured JSON — paginate /products.json until empty.
                products: list[dict] = []
                for page in range(1, 1 + LIVE_FETCH_CAP):
                    resp = httpx.get(
                        f"{base}/products.json",
                        params={"limit": 250, "page": page},
                        headers=headers,
                        timeout=15.0,
                    )
                    resp.raise_for_status()
                    page_products = resp.json().get("products", [])
                    if not page_products:
                        break
                    products.extend(page_products)
                return {"products": products}

            if source_id == "bcn-festival-calendar":
                # BCN open-data CKAN datastore_search (real, public). The resource_id is
                # env-gated: without the §8-spike-confirmed id we raise rather than hit a
                # guessed endpoint and present its output as real (no fabricated provenance).
                import os  # noqa: PLC0415  (lazy)

                resource_id = os.environ.get(_BCN_RESOURCE_ID_ENV)
                if not resource_id:
                    raise InventoryFetchError(
                        f"{_BCN_RESOURCE_ID_ENV} not set — run the 01-01-PLAN §8 spike to "
                        f"confirm the BCN '{_BCN_DATASET_SLUG}' datastore resource_id before "
                        "the live scheduled-surplus path can run"
                    )
                resp = httpx.get(
                    f"{base}/data/api/3/action/datastore_search",
                    params={"resource_id": resource_id, "limit": 250},
                    headers=headers,
                    timeout=15.0,
                )
                resp.raise_for_status()
                return resp.json().get("result", {}).get("records", [])

            # Exoandamiajes / Mascus: scrapling static HTML fetch.
            from scrapling import Fetcher  # noqa: PLC0415  (lazy)

            page = Fetcher.get(f"{base}/andamios", headers=headers, timeout=15)
            return _scrapling_to_listings(page, base)
        except InventoryFetchError:
            raise
        except Exception as exc:  # any HTTP/parse error -> typed failure
            raise InventoryFetchError(
                f"live fetch failed for {source_id}: {type(exc).__name__}: {exc}",
                cause=exc,
            ) from exc


def _scrapling_to_listings(page, base: str) -> list[dict]:
    """Parse an Exoandamiajes/Mascus catalog page into raw listing dicts.

    Best-effort CSS/XPath extraction of product name + EUR price + m² from the
    server-rendered catalog. Kept defensive: a structure drift yields fewer rows, never
    an exception that would mask a real fetch as success.
    """
    from urllib.parse import urlparse  # noqa: PLC0415  (lazy — keeps the offline import light)

    expected_host = urlparse(base).netloc
    listings: list[dict] = []
    try:
        links = page.css("a::attr(href)") or []
    except Exception:
        links = []
    for href in links:
        href = str(href)
        if "/andamios/" not in href:
            continue
        # SSRF-safe allow-list (MN-01): an absolute href must resolve to the SAME host as the
        # adapter's fixed base URL. A cross-origin href injected into the scraped page (e.g.
        # https://evil.com/andamios/item) is REJECTED here rather than stored as source_url.
        if href.startswith("http"):
            if urlparse(href).netloc != expected_host:
                continue  # skip cross-origin injected href (rejected, never persisted)
            source_url = href
        else:
            source_url = f"{base}{href}"
        listings.append(
            {
                "raw_title": href.rsplit("/", 1)[-1].replace("-", " "),
                "source_url": source_url,
                "body": "andamio",
            }
        )
    return listings


# --------------------------------------------------------------------------- #
# ShopifyAdapter (The Fabric Sales + FabricSight, /products.json)
# --------------------------------------------------------------------------- #
class ShopifyAdapter:
    """Adapter over a Shopify storefront's public ``/products.json`` endpoint.

    Instantiated twice (The Fabric Sales + FabricSight). ``fetch(fetcher)`` dispatches
    through the injected fetcher (fake in tests, ``HttpFetcher`` live), normalizes each
    variant to a raw listing dict, and reads ``variants[].available`` as the D-06
    availability signal. A ``None`` payload (failed fetch) raises ``InventoryFetchError``.
    """

    def __init__(self, source_id: str, base_url: str | None = None):
        self.source_id = source_id
        self.base_url = base_url or SOURCE_BASE_URLS.get(source_id, "")

    def fetch(self, fetcher, query: dict | None = None, *, budget: LiveFetchBudget | None = None):
        """Fetch + normalize Shopify products into raw listing dicts.

        Raises ``InventoryFetchError`` if the fetcher signals failure (returns ``None``)
        or raises — so the stage degrades to a labelled snapshot, never a silent empty.
        """
        if budget is not None:
            budget.record(f"shopify:{self.source_id}")
        try:
            payload = fetcher.fetch(self.source_id, query)
        except InventoryFetchError:
            raise
        except Exception as exc:
            raise InventoryFetchError(
                f"shopify fetch raised for {self.source_id}: {type(exc).__name__}: {exc}",
                cause=exc,
            ) from exc

        if payload is None:
            raise InventoryFetchError(f"shopify fetch returned no payload for {self.source_id}")

        from datetime import datetime, timezone  # noqa: PLC0415

        fetched_at = datetime.now(timezone.utc).isoformat()
        listings: list[dict] = []
        for product in payload.get("products", []):
            variants = product.get("variants") or [{}]
            for variant in variants:
                price = variant.get("price")
                listings.append(
                    {
                        "raw_title": product.get("title", ""),
                        "title": product.get("title", ""),
                        "product_type": product.get("product_type", ""),
                        "body": product.get("body_html", ""),
                        "tags": product.get("tags", []),
                        "price_eur": _safe_float(price),
                        "available": bool(variant.get("available", False)),
                        "grams": variant.get("grams"),
                        "areal_weight_g_m2": variant.get("grams"),
                        "source_url": f"{self.base_url}/products/{product.get('handle', '')}",
                        "fetched_at": fetched_at,
                    }
                )
        return listings


# --------------------------------------------------------------------------- #
# ExoandamiajesAdapter (scrapling HTML) + Mascus (second scrapling adapter)
# --------------------------------------------------------------------------- #
class ExoandamiajesAdapter:
    """Adapter over the Exoandamiajes (Joomla) server-rendered scaffold catalog.

    ``fetch(fetcher)`` dispatches through the injected fetcher (which returns a list of
    raw listing dicts — already CSS/XPath-parsed by ``HttpFetcher`` live, or canned in
    tests), normalizing name + EUR + m² (m² may be embedded in the slug). A ``None``
    payload raises ``InventoryFetchError``.
    """

    def __init__(self, source_id: str = "exoandamiajes"):
        self.source_id = source_id

    def fetch(self, fetcher, query: dict | None = None, *, budget: LiveFetchBudget | None = None):
        if budget is not None:
            budget.record(f"exoandamiajes:{self.source_id}")
        try:
            payload = fetcher.fetch(self.source_id, query)
        except InventoryFetchError:
            raise
        except Exception as exc:
            raise InventoryFetchError(
                f"exoandamiajes fetch raised: {type(exc).__name__}: {exc}", cause=exc
            ) from exc

        if payload is None:
            raise InventoryFetchError("exoandamiajes fetch returned no payload")

        from datetime import datetime, timezone  # noqa: PLC0415

        fetched_at = datetime.now(timezone.utc).isoformat()
        listings: list[dict] = []
        for row in payload:
            listings.append(
                {
                    "raw_title": row.get("title") or row.get("raw_title", ""),
                    "title": row.get("title") or row.get("raw_title", ""),
                    "product_type": row.get("product_type", ""),
                    "body": row.get("body", ""),
                    "price_eur": row.get("price_eur"),
                    "available": True,  # a listed catalog row is offered (qty unknown)
                    "dimensions_mm": row.get("dimensions_mm"),
                    "source_url": row.get("source_url", ""),
                    "fetched_at": fetched_at,
                }
            )
        return listings


class MascusAdapter(ExoandamiajesAdapter):
    """Second scrapling adapter (Mascus ES, same scaffold stock as MachineryZone).

    Reuses the Exoandamiajes parse path (both are server-rendered scaffold catalogs);
    MachineryZone is skipped (403). 05-RESEARCH §Q1.
    """

    def __init__(self, source_id: str = "mascus"):
        super().__init__(source_id=source_id)


# --------------------------------------------------------------------------- #
# ScheduledSurplusAdapter (BCN festival calendar -> inferred teardown surplus)
# --------------------------------------------------------------------------- #
def _parse_date(value) -> "object | None":
    """Parse an untrusted CKAN date string to a ``datetime.date``; None on any failure.

    CKAN dates arrive as "2026-06-28" or "2026-06-28T00:00:00" (or "...Z"). We read the
    leading YYYY-MM-DD only — a non-date value (empty, "N/A", a malformed field) yields
    None so the caller skips the window honestly, never a ValueError escaping the stage.
    """
    if not isinstance(value, str) or len(value) < 10:
        return None
    from datetime import date  # noqa: PLC0415  (lazy)

    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


class ScheduledSurplusAdapter:
    """Infer the reusable festival kit a teardown sheds, timed to a real published end date.

    This is the ONE adapter that does not scrape a product listing — it reads a real, public
    BCN cultural-agenda record (festival name + published end date ``data_fi``) and, via the
    deterministic ``_FESTIVAL_KIT`` table, emits the standard reusable hardware that teardown
    yields (truss / Heras fence / euro pallet / PP carpet). The SHARED classifier binds each
    to one ``materials.json`` id with NO new rule. Honesty seams (V2C 01-01-PLAN, RISK_REGISTER):

      * the snapshot is labelled ASSUMED tier (source in ``ASSUMED_TIER_SOURCES``);
      * quantity is NEVER asserted (``qty_available`` stays null — ASSUMED band, no ground truth);
      * availability stays ``unknown`` (the gear is not yet torn down — never claimed in-stock);
      * each listing carries an ``availability_window`` (from = published end date, until = +
        ``TEARDOWN_WINDOW_DAYS``) with ``end_date_proxy=true`` — ``data_fi`` is a slipping
        planned date, a ± hypothesis window, NEVER a hard expiry;
      * ``source_url`` points at the real BCN dataset page; ``fetched_at`` is real.

    A record with no parseable end date yields no listings (the clock can't be computed) — a
    source-level filter, not a silent drop of a bound material (conservation is per-listing).
    """

    def __init__(self, source_id: str = "bcn-festival-calendar"):
        self.source_id = source_id
        self.base_url = SOURCE_BASE_URLS.get(source_id, "")

    def fetch(self, fetcher, query: dict | None = None, *, budget: LiveFetchBudget | None = None):
        if budget is not None:
            budget.record(f"scheduled-surplus:{self.source_id}")
        try:
            payload = fetcher.fetch(self.source_id, query)
        except InventoryFetchError:
            raise
        except Exception as exc:
            raise InventoryFetchError(
                f"scheduled-surplus fetch raised: {type(exc).__name__}: {exc}", cause=exc
            ) from exc

        if payload is None:
            raise InventoryFetchError("scheduled-surplus fetch returned no payload")

        from datetime import datetime, timedelta, timezone  # noqa: PLC0415

        fetched_at = datetime.now(timezone.utc).isoformat()
        dataset_url = f"{self.base_url}/data/dataset/{_BCN_DATASET_SLUG}"
        listings: list[dict] = []
        for record in payload:
            if not isinstance(record, dict):
                continue
            name = (
                record.get("denominacio")
                or record.get("name")
                or record.get("title")
                or "festival"
            )
            end = _parse_date(
                record.get("data_fi")
                or record.get("end_date")
                or record.get("data_final")
            )
            if end is None:
                continue  # no published end date -> no collect-before-landfill clock
            window = {
                "from": end.isoformat(),
                "until": (end + timedelta(days=TEARDOWN_WINDOW_DAYS)).isoformat(),
                "end_date_proxy": True,  # data_fi is a slipping planned date, not a hard expiry
            }
            for kit in _FESTIVAL_KIT:
                listings.append(
                    {
                        "raw_title": f"{kit['label']} — expected surplus from {name} teardown",
                        "title": kit["label"],
                        "body": kit["keywords"],
                        # availability deliberately omitted -> "unknown" (not yet torn down).
                        "qty_available": None,  # ASSUMED band, no ground truth
                        "availability_window": window,
                        "source_url": dataset_url,
                        "fetched_at": fetched_at,
                    }
                )
        return listings


# --------------------------------------------------------------------------- #
# Source -> adapter registry (the fixed allow-list of run-path adapters)
# --------------------------------------------------------------------------- #
def adapter_for(source_id: str):
    """Return the adapter instance for a known ``source_id`` (fixed allow-list).

    Raises ``InventoryFetchError`` for an unknown source so an out-of-allow-list id can
    never reach a live fetch (SSRF / scope guard, T-05-08).
    """
    if source_id in SHOPIFY_SOURCES:
        return ShopifyAdapter(source_id)
    if source_id == "exoandamiajes":
        return ExoandamiajesAdapter(source_id)
    if source_id == "mascus":
        return MascusAdapter(source_id)
    if source_id == "bcn-festival-calendar":
        return ScheduledSurplusAdapter(source_id)
    raise InventoryFetchError(f"no adapter for source_id {source_id!r} (not in allow-list)")
