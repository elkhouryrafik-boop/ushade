"""Open-Meteo weather context for a festival date and location.

Three scenarios depending on how far the date is from today:
  - Past / near (≤ today): Open-Meteo archive API (measured data).
  - Forecast window (1–16 days ahead): Open-Meteo forecast API.
  - Far future (> 16 days): pull the same calendar date from the previous
    five years via the archive API and return best-case / worst-case
    summaries alongside the 5-year mean.

All returned values are labelled ASSUMED — they inform the organiser but
never gate the pipeline acceptance (Phase 5b gate uses real UTCI).

No authentication required: Open-Meteo is a free, open API.
"""

from __future__ import annotations

import json
import logging
import ssl
import urllib.request
import urllib.parse
from datetime import date, timedelta
from typing import Any

_LOG = logging.getLogger("heatguard.weather_forecast")

# Parc del Fòrum default site coordinates (WGS84). Sourced from the ONE canonical
# venue centroid (geom.constants.PARC_DEL_FORUM_LATLON = the Phase-2a fixed-site
# centroid the UTCI climate grid was computed over) so the weather context anchors
# to the same point as the heat grid it informs. Do NOT hardcode a separate value
# here — that drift is what produced the ~0.7 km mismatch reconciled 2026-06-24.
from geom.constants import PARC_DEL_FORUM_LATLON  # noqa: E402

_DEFAULT_LAT, _DEFAULT_LON = PARC_DEL_FORUM_LATLON

# Open-Meteo endpoints (no key required)
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Rain risk threshold: precipitation probability > this % → rain risk flagged
_RAIN_RISK_PCT = 30

# How many years of historical data to use for climate normals
_NORM_YEARS = 5

# Forecast horizon: beyond this many days we switch to climate normals
_FORECAST_HORIZON_DAYS = 16

_DAILY_FIELDS = ",".join([
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_probability_max",
    "weather_code",
])

# WMO weather code → short human label
_WMO_LABELS: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Icy fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Light freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Showers", 82: "Heavy showers",
    85: "Light snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm + heavy hail",
}


def _ssl_ctx() -> ssl.SSLContext:
    """Best-effort SSL context: certifi → system CA → unverified (with warning)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    try:
        ctx = ssl.create_default_context()
        ctx.load_default_certs()
        return ctx
    except Exception:
        pass
    _LOG.warning("SSL cert verification disabled for Open-Meteo (no CA bundle found)")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


_SSL_CTX = _ssl_ctx()


def _get(url: str, params: dict) -> dict:
    full = url + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(full, timeout=8, context=_SSL_CTX) as r:
        return json.loads(r.read().decode())


def _wmo_label(code: int | None) -> str:
    if code is None:
        return "Unknown"
    return _WMO_LABELS.get(int(code), f"Code {code}")


def _daily_row(data: dict, idx: int = 0) -> dict[str, Any]:
    """Extract one day's values from a /forecast or /archive daily response."""
    d = data.get("daily", {})
    return {
        "temperature_max": _safe(d.get("temperature_2m_max"), idx),
        "temperature_min": _safe(d.get("temperature_2m_min"), idx),
        "precipitation_probability": _safe(d.get("precipitation_probability_max"), idx),
        "weather_code": _safe(d.get("weather_code"), idx),
    }


def _safe(lst: list | None, idx: int) -> Any:
    if not lst or idx >= len(lst):
        return None
    return lst[idx]


def _utci_estimate(temp_max: float | None) -> list[float] | None:
    """Very rough rule-of-thumb UTCI range from air temperature (ASSUMED).
    UTCI ≈ T_air + solar/wind penalty; in an open festival site, daytime UTCI
    typically runs 8–14 °C above air temperature maximum.
    """
    if temp_max is None:
        return None
    return [round(temp_max + 6, 1), round(temp_max + 14, 1)]


def fetch_weather_context(
    date_str: str,
    lat: float = _DEFAULT_LAT,
    lon: float = _DEFAULT_LON,
) -> dict:
    """Fetch Open-Meteo weather context for a festival date.

    Parameters
    ----------
    date_str : str
        ISO date "YYYY-MM-DD".
    lat, lon : float
        Site centroid (WGS84). Defaults to Parc del Fòrum, Barcelona.

    Returns
    -------
    dict
        Weather context with provenance labels.  All numeric values are
        ASSUMED — they are informational only and never gate the pipeline.
    """
    try:
        target = date.fromisoformat(date_str)
    except ValueError:
        return _unavailable(date_str, "invalid date format")

    today = date.today()
    delta = (target - today).days

    try:
        if delta > _FORECAST_HORIZON_DAYS:
            return _climate_normals(date_str, target, lat, lon)
        elif delta >= 0:
            return _from_forecast(date_str, lat, lon)
        else:
            return _from_archive(date_str, lat, lon)
    except Exception as exc:
        _LOG.warning("Open-Meteo unavailable for %s: %s", date_str, exc)
        return _unavailable(date_str, str(exc))


# ── scenario helpers ────────────────────────────────────────────────────────

def _from_forecast(date_str: str, lat: float, lon: float) -> dict:
    data = _get(_FORECAST_URL, {
        "latitude": lat, "longitude": lon,
        "daily": _DAILY_FIELDS,
        "timezone": "auto",
        "start_date": date_str, "end_date": date_str,
    })
    row = _daily_row(data)
    return _build(date_str, "forecast", row)


def _from_archive(date_str: str, lat: float, lon: float) -> dict:
    data = _get(_ARCHIVE_URL, {
        "latitude": lat, "longitude": lon,
        "daily": _DAILY_FIELDS,
        "timezone": "auto",
        "start_date": date_str, "end_date": date_str,
    })
    row = _daily_row(data)
    return _build(date_str, "historical", row)


def _climate_normals(date_str: str, target: date, lat: float, lon: float) -> dict:
    """Fetch the same calendar date for the past N years, return statistics.

    Best case  = year with coolest max temp AND lowest rain probability.
    Worst case = year with hottest max temp AND highest rain probability.
    """
    target_month, target_day = target.month, target.day
    rows: list[dict] = []

    for yr in range(target.year - 1, target.year - 1 - _NORM_YEARS, -1):
        try:
            d = date(yr, target_month, target_day)
        except ValueError:
            continue  # Feb 29 in non-leap years
        d_str = d.isoformat()
        try:
            data = _get(_ARCHIVE_URL, {
                "latitude": lat, "longitude": lon,
                "daily": _DAILY_FIELDS,
                "timezone": "auto",
                "start_date": d_str, "end_date": d_str,
            })
            row = _daily_row(data)
            row["year"] = yr
            rows.append(row)
        except Exception as exc:
            _LOG.debug("archive miss for %s: %s", d_str, exc)

    if not rows:
        return _unavailable(date_str, "no historical data found")

    temps   = [r["temperature_max"] for r in rows if r["temperature_max"] is not None]
    rains   = [r["precipitation_probability"] for r in rows if r["precipitation_probability"] is not None]
    t_min_p = [r["temperature_min"] for r in rows if r["temperature_min"] is not None]

    t_max_mean = round(sum(temps) / len(temps), 1) if temps else None
    t_min_mean = round(sum(t_min_p) / len(t_min_p), 1) if t_min_p else None
    rain_mean  = round(sum(rains) / len(rains)) if rains else None

    best_row  = min(rows, key=lambda r: (r["temperature_max"] or 999, r["precipitation_probability"] or 999))
    worst_row = max(rows, key=lambda r: (r["temperature_max"] or 0, r["precipitation_probability"] or 0))

    base = _build(date_str, "climate_normals", {
        "temperature_max": t_max_mean,
        "temperature_min": t_min_mean,
        "precipitation_probability": rain_mean,
        "weather_code": None,
    })
    base["best_case"] = {
        "year": best_row.get("year"),
        "temperature_max": best_row["temperature_max"],
        "precipitation_probability": best_row["precipitation_probability"],
        "weather_condition": _wmo_label(best_row.get("weather_code")),
        "is_rain_risk": (best_row["precipitation_probability"] or 0) > _RAIN_RISK_PCT,
    }
    base["worst_case"] = {
        "year": worst_row.get("year"),
        "temperature_max": worst_row["temperature_max"],
        "precipitation_probability": worst_row["precipitation_probability"],
        "weather_condition": _wmo_label(worst_row.get("weather_code")),
        "is_rain_risk": (worst_row["precipitation_probability"] or 0) > _RAIN_RISK_PCT,
    }
    base["years_sampled"] = len(rows)
    return base


# ── shared builder ──────────────────────────────────────────────────────────

def _build(date_str: str, scenario: str, row: dict) -> dict:
    precip = row.get("precipitation_probability")
    t_max  = row.get("temperature_max")
    is_rain = (precip or 0) > _RAIN_RISK_PCT

    return {
        "date": date_str,
        "scenario": scenario,
        "temperature_max": t_max,
        "temperature_min": row.get("temperature_min"),
        "precipitation_probability": precip,
        "is_rain_risk": is_rain,
        "weather_condition": _wmo_label(row.get("weather_code")),
        "utci_likely_range_assumed": _utci_estimate(t_max),
        "rain_note": (
            "Rain likely — shade structures should use waterproof membranes."
            if is_rain else
            "No significant rain risk on the forecast date."
        ),
        "provenance": "ASSUMED — Open-Meteo free API (open-meteo.com). Informational only; does not gate Phase 5b.",
        "source": "https://open-meteo.com/",
    }


def _unavailable(date_str: str, reason: str) -> dict:
    return {
        "date": date_str,
        "scenario": "unavailable",
        "reason": reason,
        "provenance": "ASSUMED — weather data unavailable",
        "source": "https://open-meteo.com/",
    }
