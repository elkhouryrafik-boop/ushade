"""GEOM-01/03 (Python half) — deterministic IN_SunVector + validate-then-solve gh_request assembler.

The Wave-1 RED stage tests drive a PYTHON spine (``geom.geom.run_gh_stage``), so the request
assembly + the deterministic sun vector need Python implementations alongside the Node
``request.ts`` / ``sun_vector.ts`` (the Node seam is the live-EC2 path; this is the offline-spine
path). Both runtimes assemble the SAME frozen ``gh_request`` (contracts/gh_request.schema.json) and
validate it BEFORE any solve (validate-then-solve; clone parser Gate 2 / ``request.ts``).

``schema_version`` is a code-owned const (clone parser A1) — never read from the input.

The sun vector is computed with a self-contained NOAA solar-position approximation (no extra
dependency — keeps the base suite dep-free, mirroring ``constants.py`` loading numpy-only). It is a
3D UNIT vector at the peak-sun hour over the fixed Parc-del-Fòrum centroid, so a fixed ``brief_date``
yields a byte-identical tuple every call (determinism = the GEOM-03 gate). The constants mirror
``src/geom/constants.py`` (the ONE source of truth).
"""

from __future__ import annotations

import math

from geom.constants import PARC_DEL_FORUM_LATLON, PEAK_SUN_HOUR
from validate.validate import validate

_SCHEMA_VERSION = "1.0.0"

#: The deterministic default brief date for the Parc-del-Fòrum demo (mid-June peak season).
_DEFAULT_BRIEF_DATE = "2026-06-14"


def _day_of_year(year: int, month: int, day: int) -> int:
    """Ordinal day-of-year (1-366) without importing datetime (pure arithmetic, deterministic)."""
    cum = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
    doy = cum[month - 1] + day
    if leap and month > 2:
        doy += 1
    return doy


def sun_vector(brief_date: str | None = None) -> tuple[float, float, float]:
    """Deterministic 3D UNIT solar direction at the peak-sun hour over Parc del Fòrum (GEOM-03).

    Returns ``[x=east, y=north, z=up]`` — a unit vector pointing FROM the ground TO the sun (z>0 at
    peak sun). NOAA solar-position approximation (declination + hour-angle); no I/O, no dependency,
    so a fixed ``brief_date`` is byte-identical every call.
    """
    date = (brief_date or _DEFAULT_BRIEF_DATE)[:10]
    year, month, day = (int(p) for p in date.split("-"))
    lat_deg, lon_deg = PARC_DEL_FORUM_LATLON
    lat = math.radians(lat_deg)

    doy = _day_of_year(year, month, day)
    # Solar declination (Cooper's equation), radians.
    decl = math.radians(23.45) * math.sin(2.0 * math.pi * (284 + doy) / 365.0)
    # Hour angle at PEAK_SUN_HOUR (UTC clock; the demo uses the local peak band midpoint).
    # H = 15°/hr * (solar_time - 12). Use the longitude correction so the vector is venue-anchored.
    solar_time = PEAK_SUN_HOUR + lon_deg / 15.0
    hour_angle = math.radians(15.0 * (solar_time - 12.0))

    # Solar altitude + azimuth (standard astronomy).
    sin_alt = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(hour_angle)
    sin_alt = max(-1.0, min(1.0, sin_alt))
    altitude = math.asin(sin_alt)
    cos_alt = math.cos(altitude)
    if abs(cos_alt) < 1e-9:
        azimuth = 0.0
    else:
        cos_az = (math.sin(decl) - math.sin(lat) * sin_alt) / (math.cos(lat) * cos_alt)
        cos_az = max(-1.0, min(1.0, cos_az))
        azimuth = math.acos(cos_az)  # from north, before the afternoon flip
        if hour_angle > 0:  # afternoon -> sun to the west
            azimuth = 2.0 * math.pi - azimuth

    x = cos_alt * math.sin(azimuth)  # east
    y = cos_alt * math.cos(azimuth)  # north
    z = sin_alt  # up
    # Unit by construction (x²+y²+z² = cos²alt + sin²alt = 1).
    return (x, y, z)


def build_gh_request(
    footprint: dict | list,
    flow_vectors: list[dict],
    sun: tuple[float, float, float] | list[float],
) -> dict:
    """Assemble + validate the frozen ``gh_request`` (validate-then-solve; clone ``request.ts``).

    ``footprint`` accepts the ``footprint.json`` dict (``{polygons: [...]}``) or a raw polygon list.
    ``flow_vectors`` is already the frozen line shape (origin/destination) — NO reshape. Raises a
    ``jsonschema.ValidationError`` if the assembled request is contract-invalid, so an invalid
    request never reaches the solve (the wire or the PREVIEW generator).
    """
    polygons = footprint.get("polygons", footprint) if isinstance(footprint, dict) else footprint
    req = {
        "schema_version": _SCHEMA_VERSION,  # code-owned const (clone parser A1) — never from input
        "IN_Footprint": polygons,
        "IN_FlowVectors": flow_vectors,  # already the line shape — NO reshape
        "IN_SunVector": [float(c) for c in sun],
    }
    validate(req, "gh_request")  # throws if invalid — never reaches the solve
    return req
