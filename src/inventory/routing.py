"""Supplier -> Parc del Fòrum ROAD routing (MAT-02, Pitfall 4, D-08).

The frozen ``data/materials.json`` ``lca_profile.distance_km`` values are ROAD
distances (05-RESEARCH §Q2 — Polinyà->Parc del Fòrum is 23.2 km road vs ~17 km
great-circle, and the frozen entry carries 25.0). So any DERIVED inventory distance
fed into the transport-carbon formula MUST be a ROAD route, never a haversine /
EPSG:32631-Euclidean straight line (that understates km -> understates carbon ->
overstates the green claim — the exact Pitfall 4).

Provider ladder (05-RESEARCH §Q2):
  1. ORS ``/v2/directions/driving-car`` if ``${ORS_API_KEY}`` is set (keyed, stable).
  2. OSRM ``/route/v1/driving`` public demo (keyless).
  3. Deterministic offline ROAD estimate = great-circle × an ASSUMED road-circuity
     factor (so the value is a ROAD distance strictly longer than the great-circle even
     with no network), labelled DERIVED.
The supplier-keyed last resort (the stage owns it) is the frozen ``materials.json``
``distance_km`` labelled GROUNDED — never a haversine guess into the carbon formula.

Secrets: ``${ORS_API_KEY}`` is read from the environment ONLY and is NEVER logged,
returned, or embedded in any persisted string (T-05-07). httpx is imported LAZILY
inside the live call so importing this module needs no network library.

karpathy: two tiny pure functions (great-circle + circuity) + one live-route function
with a typed fallback. No routing engine, no graph, no projection.
"""

from __future__ import annotations

import math
import os

# Distance tier labels (mirror the inventory_snapshot ``distance_tier`` enum).
DERIVED = "DERIVED"
GROUNDED = "GROUNDED"

# ASSUMED road-circuity factor: real road routes are longer than the great-circle by a
# detour ratio. 1.30 is a conservative mid value that reproduces the verified
# Polinyà->Parc del Fòrum case (great-circle ~17.2 km × 1.30 = ~22.3 km vs 23.2 km live
# OSRM road). Used ONLY for the keyless/offline DERIVED estimate; a live OSRM/ORS route
# supersedes it whenever the network is reachable. ASSUMED (05-RESEARCH §Q2). It is
# strictly > 1.0 so the DERIVED road km always exceeds the great-circle (Pitfall 4).
ROAD_CIRCUITY_FACTOR: float = 1.30  # ASSUMED

# Parc del Fòrum site coords (materials.json _meta.site_coords) — GROUNDED.
SITE_LAT: float = 41.4106
SITE_LON: float = 2.2203

_EARTH_RADIUS_KM = 6371.0088  # mean Earth radius (km)

# Routing endpoints (fixed allow-list — no user-supplied host; SSRF-safe, T-05-08).
_OSRM_BASE = "https://router.project-osrm.org/route/v1/driving"
_ORS_BASE = "https://api.openrouteservice.org/v2/directions/driving-car"

# Opt-in live routing: the default OFFLINE test suite must NOT hit the network, so a
# live OSRM/ORS dispatch happens only when explicitly enabled (mirror the climate
# offline seam). When off, road_distance_km returns the deterministic circuity estimate.
_LIVE_ROUTING_ENV = "HEATGUARD_LIVE_ROUTING"


def great_circle_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Haversine great-circle distance in km between ``(lat, lon)`` points ``a`` and ``b``.

    Provided as the ROAD-vs-straight-line BASELINE only — it is NEVER fed into the
    carbon formula (Pitfall 4). The road route must strictly exceed this value.
    """
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def _live_road_km(supplier: tuple[float, float], site: tuple[float, float]) -> float | None:
    """Attempt a LIVE road route (ORS keyed, then OSRM keyless). Returns km or None.

    httpx is imported LAZILY here (mirror climate ``_load_sdk``) so this module imports
    with no network dependency. Any failure returns None so the caller degrades to the
    deterministic circuity estimate (never raises into the carbon path). The
    ``${ORS_API_KEY}`` is read from env and passed as a header only — never logged.
    """
    try:
        import httpx  # noqa: PLC0415  (intentional lazy import — offline suite stays light)
    except ImportError:
        return None

    s_lat, s_lon = supplier
    t_lat, t_lon = site

    ors_key = os.environ.get("ORS_API_KEY")
    try:
        if ors_key:
            # ORS expects [lon, lat] coordinate pairs.
            resp = httpx.post(
                _ORS_BASE,
                headers={"Authorization": ors_key},  # key in header only, never logged
                json={"coordinates": [[s_lon, s_lat], [t_lon, t_lat]]},
                timeout=10.0,
            )
            resp.raise_for_status()
            meters = resp.json()["routes"][0]["summary"]["distance"]
            return float(meters) / 1000.0

        # OSRM public demo (keyless). lon,lat;lon,lat path order.
        url = f"{_OSRM_BASE}/{s_lon},{s_lat};{t_lon},{t_lat}"
        resp = httpx.get(url, params={"overview": "false"}, timeout=10.0)
        resp.raise_for_status()
        meters = resp.json()["routes"][0]["distance"]
        return float(meters) / 1000.0
    except Exception:
        # Any HTTP/parse/timeout error -> degrade to the deterministic estimate.
        return None


def road_distance_km(
    supplier: tuple[float, float],
    site: tuple[float, float] | None = None,
) -> float:
    """ROAD distance (km) from ``supplier`` ``(lat, lon)`` to the Parc del Fòrum site.

    Returns a scalar that is ALWAYS a ROAD distance strictly greater than the
    great-circle (Pitfall 4). Tries a live ORS/OSRM route only when
    ``HEATGUARD_LIVE_ROUTING`` is set (so the offline suite never touches the network);
    otherwise returns the deterministic ``great_circle × ROAD_CIRCUITY_FACTOR`` estimate.
    Use :func:`road_route` to also obtain the provenance tier.
    """
    km, _tier = road_route(supplier, site)
    return km


def road_route(
    supplier: tuple[float, float],
    site: tuple[float, float] | None = None,
) -> tuple[float, str]:
    """Return ``(road_km, distance_tier)`` for ``supplier`` -> the site.

    ``distance_tier`` is ``"DERIVED"`` for a live or circuity-estimated road route.
    The supplier-keyed frozen ``materials.json`` GROUNDED fallback is owned by the
    inventory stage (it holds the per-supplier frozen ``distance_km``); this routing
    primitive only ever yields a DERIVED road km, never a haversine guess.
    """
    if site is None:
        site = (SITE_LAT, SITE_LON)

    if os.environ.get(_LIVE_ROUTING_ENV):
        live = _live_road_km(supplier, site)
        if live is not None:
            return live, DERIVED

    # Deterministic offline ROAD estimate: great-circle scaled by the circuity factor.
    # Strictly > great-circle (factor > 1.0), so it is a defensible road distance and
    # the road-vs-crow test holds with no network.
    crow = great_circle_km(supplier, site)
    return crow * ROAD_CIRCUITY_FACTOR, DERIVED
