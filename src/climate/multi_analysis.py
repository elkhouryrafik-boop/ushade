"""Live multi-analysis fetch — the *extra* infrared layers beyond baseline UTCI.

``run_site_diagnostics`` runs the three high-value diagnostic analyses the project was
NOT using — ``direct-sun-hours`` (which cells bake in the sun, justifies shade placement),
``solar-radiation`` (W/m^2 load per cell, shade ROI), and ``thermal-comfort-statistics``
heat-stress (fraction of the window each cell is heat-stressed, the organiser headline) —
against ONE fetched area, sharing buildings + ground materials + vegetation + weather so
the paid area is fetched once and every layer snaps to the same lattice the UTCI baseline,
crowd field, and placer already use.

This is a LIVE-ONLY module (paid infrared dispatches). Like ``infrared_client``, the
``infrared_sdk`` package is imported **lazily inside the run function**, never at module
top, so importing this module needs no SDK and the offline suite stays SDK-free. It reuses
``infrared_client``'s budget, typed error, optional-overlay fetch, and weather resolution —
no second copy of those policies.

Permission note: firing this spends real infrared budget. The orchestrator/script must be
explicitly authorised to call it (infrared is permission-gated, per project policy).

karpathy: one run function + a small per-analysis spec table. No analysis class hierarchy.
"""

from __future__ import annotations

from climate.infrared_client import (
    ClimateFetchError,
    LiveCallBudget,
    _fetch_optional_layers,
    _resolve_weather,
)

# --------------------------------------------------------------------------- #
# Per-analysis windows (local hours). ASSUMED — PRD is silent on exact bands.
# --------------------------------------------------------------------------- #
# Direct-sun-hours is CUMULATIVE over its window, so the full festival daytime is the
# meaningful frame (how many hours of sun each cell eats across the day). Solar-radiation
# and heat-stress are aggregated loads — the same daytime window keeps all three on one
# comparable festival-day frame.
DAYTIME_BAND: tuple[int, int] = (9, 20)  # ASSUMED — 09:00..20:00 festival daytime

# The analyses run by default + the per-cell value key each writes into its artifact.
DIAGNOSTIC_VALUE_KEYS: dict[str, str] = {
    "direct_sun_hours": "sun_hours",
    "solar_radiation": "solar_wm2",
    "tcs_heat_stress": "heat_stress_frac",
}
DEFAULT_ANALYSES: tuple[str, ...] = tuple(DIAGNOSTIC_VALUE_KEYS)


# --------------------------------------------------------------------------- #
# Lazy SDK namespace (Pattern 1 — imported INSIDE the run function only)
# --------------------------------------------------------------------------- #
def _load_diagnostic_sdk():
    """Lazily import the SDK symbols the three diagnostic analyses need.

    Raises ``ClimateFetchError`` with an install hint on ImportError (typed, like the
    UTCI path) so a missing SDK surfaces as a climate failure, not a bare ImportError.
    """
    try:  # imported here, NEVER at module top
        from infrared_sdk import (  # noqa: PLC0415
            AreaRunError,
            AreaTimeoutError,
            InfraredClient,
            InfraredJobError,
        )
        from infrared_sdk.analyses.types import (  # noqa: PLC0415
            AnalysesName,
            BaseAnalysisPayload,
            SolarModelRequest,
            SolarRadiationModelRequest,
            TcsModelBaseRequest,
            TcsModelRequest,
            TcsSubtype,
        )
        from infrared_sdk.models import Location, TimePeriod  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - exercised only without the SDK
        raise ClimateFetchError(
            "infrared SDK not installed — `pip install infrared-sdk` to run diagnostics"
        ) from exc
    return {
        "InfraredClient": InfraredClient,
        "TimePeriod": TimePeriod,
        "Location": Location,
        "AnalysesName": AnalysesName,
        "BaseAnalysisPayload": BaseAnalysisPayload,
        "SolarModelRequest": SolarModelRequest,
        "SolarRadiationModelRequest": SolarRadiationModelRequest,
        "TcsModelBaseRequest": TcsModelBaseRequest,
        "TcsModelRequest": TcsModelRequest,
        "TcsSubtype": TcsSubtype,
        "area_errors": (AreaRunError, AreaTimeoutError, InfraredJobError),
    }


# --------------------------------------------------------------------------- #
# Per-analysis payload builders
# --------------------------------------------------------------------------- #
def _build_time_period(sdk, date, band):
    from datetime import date as _date

    d = date if isinstance(date, _date) else _date.fromisoformat(str(date)[:10])
    start_hour, end_hour = band
    return sdk["TimePeriod"](
        start_month=d.month,
        start_day=d.day,
        start_hour=start_hour,
        end_month=d.month,  # single-month window (multi-month fails server-side)
        end_day=d.day,
        end_hour=end_hour,
    )


def _build_sun_hours_payload(sdk, lat, lon, tp, _weather):
    """direct-sun-hours: geometry + sun only — NO weather file (SolarModelRequest)."""
    return sdk["SolarModelRequest"](
        analysis_type=sdk["AnalysesName"].direct_sun_hours,
        latitude=lat,
        longitude=lon,
        time_period=tp,
    )


def _build_solar_radiation_payload(sdk, lat, lon, tp, weather_data):
    """solar-radiation: W/m^2, weather-driven (SolarRadiationModelRequest)."""
    return sdk["SolarRadiationModelRequest"].from_weatherfile_payload(
        payload=sdk["BaseAnalysisPayload"](
            analysis_type=sdk["AnalysesName"].solar_radiation
        ),
        location=sdk["Location"](latitude=lat, longitude=lon),
        time_period=tp,  # SAME tp handed to filter_weather_data (Pitfall 4)
        weather_data=weather_data,
    )


def _build_tcs_heat_stress_payload(sdk, lat, lon, tp, weather_data):
    """thermal-comfort-statistics heat-stress: fraction-of-hours heat-stressed."""
    return sdk["TcsModelRequest"].from_weatherfile_payload(
        payload=sdk["TcsModelBaseRequest"](
            analysis_type=sdk["AnalysesName"].thermal_comfort_statistics,
            subtype=sdk["TcsSubtype"].heat_stress,
        ),
        location=sdk["Location"](latitude=lat, longitude=lon),
        time_period=tp,
        weather_data=weather_data,
    )


# (builder, analysis_type_attr, needs_weather) per analysis key.
_ANALYSIS_SPECS = {
    "direct_sun_hours": (_build_sun_hours_payload, "direct_sun_hours", False),
    "solar_radiation": (_build_solar_radiation_payload, "solar_radiation", True),
    "tcs_heat_stress": (_build_tcs_heat_stress_payload, "thermal_comfort_statistics", True),
}


# --------------------------------------------------------------------------- #
# The run (fetch once, run many)
# --------------------------------------------------------------------------- #
def run_site_diagnostics(
    *,
    lat,
    lon,
    polygon,
    date,
    analyses=DEFAULT_ANALYSES,
    band: tuple[int, int] = DAYTIME_BAND,
    weather_mode: str = "auto",
    budget: LiveCallBudget | None = None,
    client_factory=None,
):
    """Run the requested diagnostic analyses once over a shared fetched area.

    Args:
        lat, lon: site centroid (WGS84) — drives sun position.
        polygon: site boundary (GeoJSON Polygon geometry, WGS84 closed ring).
        date: brief date (``datetime.date`` or ISO ``YYYY-MM-DD`` string).
        analyses: subset of ``("direct_sun_hours", "solar_radiation", "tcs_heat_stress")``.
        band: ``(start_hour, end_hour)`` local window the analyses aggregate over.
        weather_mode: ``"auto"`` / ``"epw"`` / ``"infrared"`` (passed to weather resolution).
        budget: a ``LiveCallBudget``; one sized to the run is created if omitted.
        client_factory: zero-arg callable returning a client context manager. ``None``
            lazily builds the real ``InfraredClient`` (the live path).

    Returns:
        ``{analysis_key: (merged_grid, bounds)}`` for each requested analysis. Shaping to
        the 6 m lattice artifact is the caller's job (``grid_to_value_artifact`` with the
        ``DIAGNOSTIC_VALUE_KEYS[key]`` value key) — this only owns the paid fetch.

    Raises:
        ClimateFetchError: on an unknown analysis key, any SDK area/job error, a holey
            (failed/skipped-tile) result, or the live-call cap.
    """
    unknown = [a for a in analyses if a not in _ANALYSIS_SPECS]
    if unknown:
        raise ClimateFetchError(f"unknown diagnostic analysis key(s): {unknown}")

    sdk = _load_diagnostic_sdk()
    # 2 dispatches/analysis (preview + run) + a couple of weather/area fetches headroom.
    budget = budget or LiveCallBudget(cap=2 * len(analyses) + 4)
    client_cm = client_factory() if client_factory is not None else sdk["InfraredClient"]()

    results: dict[str, tuple] = {}
    try:
        with client_cm as client:
            # Fetch the shared inputs ONCE (buildings + optional overlays). Ground +
            # vegetation lift solar/TCS realism the same way they lift UTCI.
            area = client.buildings.get_area(polygon)
            veg, ground = _fetch_optional_layers(client, polygon)
            overlay_kwargs = {}
            if veg:
                overlay_kwargs["vegetation"] = veg
            if ground:
                overlay_kwargs["ground_materials"] = ground

            # Weather only if some analysis needs it; resolved once for the band.
            tp = _build_time_period(sdk, date, band)
            weather_data = None
            if any(_ANALYSIS_SPECS[a][2] for a in analyses):
                weather_data, _src = _resolve_weather(client, tp, lat, lon, weather_mode)

            for key in analyses:
                builder, atype_attr, _needs_weather = _ANALYSIS_SPECS[key]
                analysis_type = getattr(sdk["AnalysesName"], atype_attr)
                payload = builder(sdk, lat, lon, tp, weather_data)

                budget.record(f"preview:{key}")
                client.preview_area(polygon, analysis_type=analysis_type)

                budget.record(f"run:{key}")
                result = client.run_area_and_wait(payload, polygon, buildings=area.buildings, **overlay_kwargs)

                failed = list(getattr(result, "failed_jobs", []) or [])
                skipped = list(getattr(result, "skipped_jobs", []) or [])
                if failed or skipped:
                    raise ClimateFetchError(
                        f"{key} run had {len(failed)} failed / {len(skipped)} skipped "
                        "tile job(s); refusing a holey grid"
                    )
                results[key] = (result.merged_grid, result.bounds)
    except ClimateFetchError:
        raise
    except sdk["area_errors"] as exc:
        raise ClimateFetchError(
            f"infrared diagnostic run failed: {type(exc).__name__}: {exc}", cause=exc
        ) from exc
    except Exception as exc:
        raise ClimateFetchError(
            f"infrared diagnostic fetch failed: {type(exc).__name__}: {exc}", cause=exc
        ) from exc

    return results
