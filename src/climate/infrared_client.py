"""infrared.city UTCI fetch wrapper — the Phase 2a network seam (CLIMATE-01/03).

This module owns the *paid network call* only. It runs the verified UTCI call
sequence against infrared.city, enforces a hard live-call cap, falls back to a
LABELLED Barcelona EPW weather source on a weather-endpoint 500 (never silent),
fails on any tile failure (no holey master lattice), and wraps SDK failures in a
typed ``ClimateFetchError`` the orchestrator (Plan 04) maps to a manifest stage
left NOT done. It returns the *raw* ``(merged_grid, bounds, weather_source)`` —
shaping into the ``utci_grid`` contract is Plan 02's ``grid_to_utci_artifact``,
and orchestration/cache/write is Plan 04's ``run_climate_stage``.

Design discipline (RESEARCH §Pattern 1 / Pitfall 6):
    The ``infrared_sdk`` package is imported LAZILY, inside the live-call factory,
    NEVER at module top — so this module imports cleanly with no SDK installed and
    the default offline suite stays SDK-free. Offline tests inject a
    ``client_factory`` returning the Plan-01 ``FakeInfraredClient`` (the offline
    seam — no module patching).

karpathy: one function + a budget class + a typed error. No client class
hierarchy, no scheduler, no DAG engine.
"""

from __future__ import annotations

from datetime import date as _date

# --------------------------------------------------------------------------- #
# Module constants
# --------------------------------------------------------------------------- #
# Peak-heat hour band (local) the UTCI sim windows on. PRD is silent on the exact
# band, so this is ASSUMED (RESEARCH §Peak-Heat Hour Band, A1): 12:00-16:00 brackets
# the max solar load and sits inside the empirically-validated coastal-Barcelona
# range. Named as ONE constant so the band lives in exactly one place.
PEAK_HEAT_HOUR_BAND: tuple[int, int] = (12, 16)  # ASSUMED (A1)

# Hard cap on LIVE (paid) infrared dispatches per run. ASSUMED 3 (lifted from
# CoolSpend's SimBudget; RESEARCH A2). A single 2a run makes 1 UTCI call; the cap is
# a backstop against a retry storm / loop bug (CCA-F P2: cap as backstop, not the
# primary terminator).
LIVE_CALL_CAP: int = 3  # ASSUMED (A2)

# Provenance labels for the weather source (T-02a-09: never silent).
_WEATHER_SOURCE_INFRARED = "infrared"
_WEATHER_SOURCE_EPW = "epw-barcelona"


# --------------------------------------------------------------------------- #
# Typed failure
# --------------------------------------------------------------------------- #
class ClimateFetchError(RuntimeError):
    """Typed wrapper for any climate-fetch failure.

    The orchestrator catches this to mark the ``utci_grid`` manifest stage NOT
    done (resume re-runs it) — never a partial/holey artifact. Carries the
    original SDK exception as ``cause`` for diagnostics.
    """

    def __init__(self, message: str, *, cause: BaseException | None = None):
        super().__init__(message)
        self.cause = cause


# --------------------------------------------------------------------------- #
# Live-call budget (RESEARCH Pattern 3)
# --------------------------------------------------------------------------- #
class LiveCallBudget:
    """Counts LIVE infrared dispatches and raises past the cap (T-02a-08, cost DoS).

    ``record(label)`` increments and raises ``ClimateFetchError`` once the count
    exceeds the cap. ``.n`` is exposed so tests/logs can read the live-call count.
    """

    def __init__(self, cap: int = LIVE_CALL_CAP):
        self.cap = cap
        self.n = 0

    def record(self, label: str) -> None:
        self.n += 1
        if self.n > self.cap:
            raise ClimateFetchError(
                f"infrared live-call cap {self.cap} exceeded at {label}"
            )


# --------------------------------------------------------------------------- #
# TimePeriod construction (single-month, peak-heat band)
# --------------------------------------------------------------------------- #
def _coerce_date(value) -> _date:
    """Accept a ``datetime.date`` or an ISO ``YYYY-MM-DD`` string; return a date."""
    if isinstance(value, _date):
        return value
    if isinstance(value, str):
        return _date.fromisoformat(value[:10])
    raise ClimateFetchError(
        f"date must be a datetime.date or ISO 'YYYY-MM-DD' string, got {type(value)!r}"
    )


def build_time_period(date, sdk_models):
    """Build the single-month, peak-heat-band ``TimePeriod`` for ``date``.

    ``sdk_models`` is the lazily-imported namespace exposing ``TimePeriod`` (the
    real SDK module, or a fake namespace in tests) so this stays testable without
    the SDK. Enforces the SDK's hard single-month constraint by construction:
    ``start_month == end_month`` and ``start_day == end_day`` (RESEARCH Pitfall 3 —
    multi-month windows silently fail server-side). The hour band comes from the
    single ``PEAK_HEAT_HOUR_BAND`` constant.
    """
    d = _coerce_date(date)
    start_hour, end_hour = PEAK_HEAT_HOUR_BAND
    return sdk_models.TimePeriod(
        start_month=d.month,
        start_day=d.day,
        start_hour=start_hour,
        end_month=d.month,  # single-month window (Pitfall 3)
        end_day=d.day,
        end_hour=end_hour,
    )


# --------------------------------------------------------------------------- #
# Lazy SDK namespace (Pattern 1 — imported INSIDE the live function only)
# --------------------------------------------------------------------------- #
class _SdkNamespace:
    """Holds the lazily-imported SDK symbols so call sites read them off one object."""

    def __init__(self, client_cls, models, types):
        self.InfraredClient = client_cls
        self.TimePeriod = models["TimePeriod"]
        self.Location = models["Location"]
        self.UtciModelRequest = types["UtciModelRequest"]
        self.UtciModelBaseRequest = types["UtciModelBaseRequest"]
        self.AnalysesName = types["AnalysesName"]
        # Error hierarchy (mapped to ClimateFetchError below).
        self.AreaRunError = types["AreaRunError"]
        self.AreaTimeoutError = types["AreaTimeoutError"]
        self.InfraredJobError = types["InfraredJobError"]


def _load_sdk() -> _SdkNamespace:
    """Lazily import the real infrared SDK (Pattern 1). Never called offline.

    Raises ``ClimateFetchError`` with an actionable install hint on ImportError so
    a missing SDK surfaces as a typed climate failure, not a bare ImportError.
    """
    try:  # imported here, NEVER at module top (Pitfall 6 / T-02a-10)
        from infrared_sdk import (  # noqa: PLC0415  (intentional lazy import)
            AreaRunError,
            AreaTimeoutError,
            InfraredClient,
            InfraredJobError,
        )
        from infrared_sdk.analyses.types import (  # noqa: PLC0415
            AnalysesName,
            UtciModelBaseRequest,
            UtciModelRequest,
        )
        from infrared_sdk.models import Location, TimePeriod  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - exercised only without the SDK
        raise ClimateFetchError(
            "infrared SDK not installed — `pip install infrared-sdk` "
            "(or install the project's optional `live` extra) to run the live fetch"
        ) from exc
    return _SdkNamespace(
        client_cls=InfraredClient,
        models={"TimePeriod": TimePeriod, "Location": Location},
        types={
            "UtciModelRequest": UtciModelRequest,
            "UtciModelBaseRequest": UtciModelBaseRequest,
            "AnalysesName": AnalysesName,
            "AreaRunError": AreaRunError,
            "AreaTimeoutError": AreaTimeoutError,
            "InfraredJobError": InfraredJobError,
        },
    )


# --------------------------------------------------------------------------- #
# Default (live) client factory
# --------------------------------------------------------------------------- #
def _default_client_factory(sdk: _SdkNamespace):
    """Return a live ``InfraredClient`` context manager (reads the key from env).

    The SDK reads its credential from the environment itself; this wrapper never
    reads, assigns, or logs the secret (T-02a-07).
    """
    return sdk.InfraredClient()


# --------------------------------------------------------------------------- #
# Weather resolution (infrared first, labelled EPW fallback on 500)
# --------------------------------------------------------------------------- #
def _epw_barcelona_weather(tp):
    """Deterministic labelled EPW weather payload (real measured Barcelona weather).

    EPW is REAL measured weather, not fabricated data — it is fed to the SAME
    ``from_weatherfile_payload`` so the sim window stays consistent. The point under
    test offline is the LABEL + "never silent", not EPW byte-parsing; the live path
    (Plan 04 wiring) swaps in the bundled EPW file. Returns a payload tagged with the
    time period so the same-tp discipline is preserved through the fallback too.
    """
    return {"_epw_weather_data": True, "source": _WEATHER_SOURCE_EPW, "time_period": tp}


def _resolve_weather(client, tp, lat, lon, weather_mode):
    """Resolve weather data, returning ``(weather_data, weather_source)``.

    Tries the infrared weather endpoint first; on a weather 500 (or an explicit
    ``weather_mode == "epw"``) falls back to the labelled Barcelona EPW. NEVER
    fabricates weather: if neither resolves, raises ``ClimateFetchError`` (the EPW
    fallback is the documented graceful-degradation path, RESEARCH Pitfall 5).
    The SAME ``tp`` instance flows into ``filter_weather_data`` (Pitfall 4).
    """
    if weather_mode == "epw":
        return _epw_barcelona_weather(tp), _WEATHER_SOURCE_EPW

    try:
        stations = client.weather.get_weather_file_from_location(
            lat=lat, lon=lon, radius=50
        )
        weather_data = client.weather.filter_weather_data(
            identifier=stations[0]["uuid"], time_period=tp  # SAME tp (Pitfall 4)
        )
        return weather_data, _WEATHER_SOURCE_INFRARED
    except Exception as exc:  # weather endpoint 500 (documented since 2026-05-29)
        if weather_mode == "infrared":
            # Caller forced infrared-only weather; surface the failure, don't fake.
            raise ClimateFetchError(
                "infrared weather endpoint failed and EPW fallback disabled "
                "(weather_mode='infrared')",
                cause=exc,
            ) from exc
        # weather_mode == "auto": degrade to the LABELLED EPW source (never silent).
        return _epw_barcelona_weather(tp), _WEATHER_SOURCE_EPW


# --------------------------------------------------------------------------- #
# The fetch (the spine of the stage)
# --------------------------------------------------------------------------- #
def fetch_utci(
    *,
    lat,
    lon,
    polygon,
    date,
    weather_mode: str = "auto",
    budget: LiveCallBudget | None = None,
    client_factory=None,
):
    """Fetch the raw UTCI grid for the site + date over the peak-heat band.

    Runs the verified call sequence — ``get_weather_file_from_location`` ->
    ``filter_weather_data`` -> ``get_area`` -> ``from_weatherfile_payload`` ->
    ``preview_area`` (with ``analysis_type``, pre-paid tile/cost check) ->
    ``run_area_and_wait`` — with ONE shared single-month ``TimePeriod`` passed to
    both ``filter_weather_data`` and ``from_weatherfile_payload`` (Pitfall 4).

    Args:
        lat, lon: site centroid (WGS84) — drives sun position; goes straight to the
            SDK. The RESULT is converted to EPSG:32631 later, by Plan 02.
        polygon: site boundary (WGS84 closed ring) for the area run.
        date: ``datetime.date`` or ISO ``YYYY-MM-DD`` string (the brief's date).
        weather_mode: ``"auto"`` (infrared, EPW on 500), ``"epw"`` (force EPW), or
            ``"infrared"`` (no fallback — raise on a weather 500).
        budget: a ``LiveCallBudget``; a fresh one is created if omitted.
        client_factory: callable ``(sdk_namespace) -> client_context_manager``. The
            DEFAULT (None) lazily imports the real SDK (Pattern 1). Offline tests
            pass a factory returning a ``FakeInfraredClient`` — the injection seam.

    Returns:
        ``(merged_grid, bounds, weather_source)`` — the raw per-cell grid (2-D, row0
        = south, col0 = west, NaN outside, deg C), the WGS84 ``bounds`` 4-tuple, and
        a provenance label (``"infrared"`` | ``"epw-barcelona"``). NOT reduced to a
        scalar mean and NOT shaped into the contract (that is Plan 02).

    Raises:
        ClimateFetchError: on any tile failure (no holey grid), any SDK area/timeout/
            job error, a forced-infrared weather failure, or the live-call cap.
    """
    budget = budget or LiveCallBudget()

    # The offline seam: tests inject a factory whose client is a FakeInfraredClient
    # and whose models namespace is a lightweight fake. The default lazily loads the
    # real SDK (Pattern 1) — so importing THIS module never imports the SDK.
    if client_factory is None:
        sdk = _load_sdk()
        client_cm = _default_client_factory(sdk)
        thermal_comfort = sdk.AnalysesName.thermal_comfort_index
        area_errors = (sdk.AreaRunError, sdk.AreaTimeoutError, sdk.InfraredJobError)
        models = sdk
        build_payload = _build_live_payload
    else:
        # Test factory: returns a client; we build a fake models namespace + a
        # simple payload carrying ``time_period`` (the fake reads payload.time_period).
        client_cm = client_factory()
        models = _FakeModels()
        thermal_comfort = "thermal_comfort_index"
        area_errors = ()  # the fake raises plain RuntimeError; mapped generically below
        build_payload = _build_fake_payload

    # ONE TimePeriod, shared by construction (Pitfall 4 — single variable).
    tp = build_time_period(date, models)

    try:
        with client_cm as client:
            weather_data, weather_source = _resolve_weather(
                client, tp, lat, lon, weather_mode
            )

            area = client.buildings.get_area(polygon)

            # Ground materials + vegetation materially improve UTCI realism (byo-inputs
            # §When each layer is needed): WITHOUT ground materials every cell defaults to
            # emissivity 0.97 (asphalt vs grass vs water all collapse to one fake surface);
            # WITHOUT vegetation tree shade/evapotranspiration cooling is ignored. Both are
            # "recommended" (not "required") for thermal-comfort-index, so we inject them
            # when available and gracefully degrade to buildings-only on a fetch failure —
            # never fail a paid UTCI run because an optional overlay 500'd.
            veg, ground = _fetch_optional_layers(client, polygon)

            payload = build_payload(models, lat, lon, tp, weather_data, thermal_comfort)

            # Preview BEFORE the paid run — always pass analysis_type or the SDK
            # under-counts UTCI tiles ~4x (RESEARCH §Site Geometry). Counted against
            # the budget (cost/tile check happens here).
            budget.record("preview")
            client.preview_area(polygon, analysis_type=thermal_comfort)

            # The paid run. Only attach the optional layers when present so the SDK-free
            # offline seam (fake client exposes neither accessor -> both None) calls the
            # exact original two-positional signature unchanged.
            run_kwargs = {"buildings": area.buildings}
            if veg:
                run_kwargs["vegetation"] = veg
            if ground:
                run_kwargs["ground_materials"] = ground
            budget.record("run")
            result = client.run_area_and_wait(payload, polygon, **run_kwargs)

    except ClimateFetchError:
        # Already typed (cap, forced-infrared weather, import) — propagate as-is.
        raise
    except area_errors as exc:  # SDK area/timeout/job errors -> typed not-done
        raise ClimateFetchError(
            f"infrared area run failed: {type(exc).__name__}: {exc}", cause=exc
        ) from exc
    except Exception as exc:
        # The fake raises a plain RuntimeError for the AreaRunError path; the real
        # SDK's 401/403 (bad key) are NOT retried and surface here. Either way the
        # orchestrator needs a typed failure, never a bare/leaking SDK exception.
        raise ClimateFetchError(
            f"infrared fetch failed: {type(exc).__name__}: {exc}", cause=exc
        ) from exc

    # Fail-on-any-tile (CONTEXT Q4 / Pitfall 7): a partial AreaResult carries
    # failed/skipped jobs — never return a holey master lattice.
    failed = list(getattr(result, "failed_jobs", []) or [])
    skipped = list(getattr(result, "skipped_jobs", []) or [])
    if failed or skipped:
        raise ClimateFetchError(
            f"infrared run had {len(failed)} failed and {len(skipped)} skipped "
            "tile job(s); refusing to return a holey master lattice"
        )

    # Raw grid + bounds + provenance label. No scalar reduction; no contract shaping.
    return result.merged_grid, result.bounds, weather_source


# --------------------------------------------------------------------------- #
# Optional ground-material + vegetation overlays (improve UTCI/solar realism)
# --------------------------------------------------------------------------- #
def _fetch_optional_layers(client, polygon):
    """Fetch ground-material + vegetation overlays if the client exposes them.

    Guarded by ``getattr`` so the offline ``FakeInfraredClient`` (which need not expose
    ``.vegetation`` / ``.ground_materials``) skips injection and the SDK-free seam stays
    byte-identical. Both layers are optional/recommended for thermal comfort, so a fetch
    failure degrades to buildings-only rather than sinking the paid UTCI run.

    Returns ``(vegetation_features_or_None, ground_layers_or_None)`` — both ready to pass
    straight to ``run_area_and_wait(vegetation=..., ground_materials=...)``. ``area_gm.layers``
    keys are already correct material names (``asphalt``/``vegetation``/``water``/...), the
    only safe source (UUID keys silently corrupt UTCI -> emissivity 0.97; byo-inputs Pitfall).
    """
    veg = None
    ground = None
    veg_api = getattr(client, "vegetation", None)
    if veg_api is not None:
        try:
            veg = getattr(veg_api.get_area(polygon), "features", None) or None
        except Exception:  # optional overlay — never fail the UTCI run on it
            veg = None
    gm_api = getattr(client, "ground_materials", None)
    if gm_api is not None:
        try:
            ground = getattr(gm_api.get_area(polygon), "layers", None) or None
            # Drop any non-material layer the SDK includes (e.g. 'building' — buildings are passed
            # separately via buildings=; an unrecognised ground name reaches the server as-is and
            # corrupts UTCI). Keep only the 5 real ground materials the server knows.
            if ground is not None:
                KNOWN = {"asphalt", "concrete", "soil", "vegetation", "water"}
                if isinstance(ground, dict):
                    ground = {k: v for k, v in ground.items() if k in KNOWN} or None
                elif isinstance(ground, list):
                    ground = [g for g in ground
                              if (getattr(g, "name", None) or getattr(g, "material", None)
                                  or (g.get("name") if isinstance(g, dict) else None)) in KNOWN] or None
        except Exception:
            ground = None
    return veg, ground


# --------------------------------------------------------------------------- #
# Payload builders (live vs fake)
# --------------------------------------------------------------------------- #
def _build_live_payload(sdk, lat, lon, tp, weather_data, thermal_comfort):
    """Build the real ``UtciModelRequest`` payload (SAME ``tp`` — Pitfall 4)."""
    return sdk.UtciModelRequest.from_weatherfile_payload(
        payload=sdk.UtciModelBaseRequest(analysis_type=thermal_comfort),
        location=sdk.Location(latitude=lat, longitude=lon),
        time_period=tp,  # SAME tp instance handed to filter_weather_data
        weather_data=weather_data,
    )


def _build_fake_payload(models, lat, lon, tp, weather_data, thermal_comfort):
    """Build a minimal offline payload carrying ``time_period`` for the fake client.

    The Plan-01 ``FakeInfraredClient.run_area_and_wait`` reads ``payload.time_period``
    to assert the SAME tp reached both calls (Pitfall 4) — so the offline payload must
    expose that attribute. No SDK involved.
    """
    return _FakePayload(
        analysis_type=thermal_comfort,
        location=(lat, lon),
        time_period=tp,
        weather_data=weather_data,
    )


# --------------------------------------------------------------------------- #
# Offline fakes for the SDK-free seam (used only when a client_factory is injected)
# --------------------------------------------------------------------------- #
class _FakeTimePeriod:
    """A plain TimePeriod stand-in so ``build_time_period`` works without the SDK."""

    def __init__(self, *, start_month, start_day, start_hour, end_month, end_day, end_hour):
        self.start_month = start_month
        self.start_day = start_day
        self.start_hour = start_hour
        self.end_month = end_month
        self.end_day = end_day
        self.end_hour = end_hour

    def __eq__(self, other) -> bool:
        if not isinstance(other, _FakeTimePeriod):
            return NotImplemented
        return vars(self) == vars(other)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"_FakeTimePeriod(month={self.start_month}, day={self.start_day}, "
            f"band=({self.start_hour},{self.end_hour}))"
        )


class _FakeModels:
    """Lightweight namespace exposing ``TimePeriod`` for the offline seam."""

    TimePeriod = _FakeTimePeriod


class _FakePayload:
    """Offline payload exposing ``time_period`` (the fake client reads it)."""

    def __init__(self, *, analysis_type, location, time_period, weather_data):
        self.analysis_type = analysis_type
        self.location = location
        self.time_period = time_period
        self.weather_data = weather_data
