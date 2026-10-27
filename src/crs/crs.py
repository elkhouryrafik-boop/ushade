"""Canonical CRS module — the single coordinate-reference boundary (CONTRACT-01).

HeatGuard carries **one** projected CRS everywhere downstream of ingestion:
**UTM 31N / EPSG:32631, units metre**. infrared.city returns lat/lon (degrees);
that is converted to EPSG:32631 exactly **once**, on ingestion (Phase 2a), and
metres are carried through the greedy core, Grasshopper, and the Phase 5b gate.
This module is that single conversion point — no other module may convert CRS.

Adapted from CoolSpend ``coolspend/spatial_engine.py`` (already EPSG:32631 with a
fail-closed ``assert_crs_roundtrip``), per ``.planning/REUSE.md``. The EPSG constant
is conformed to 32631 and the **ETRS89 zone-31 variant that NatureGooddest mixes in
is NOT inherited** — there is intentionally no ETRS89 EPSG token anywhere in src/crs
(the no-leak contract is enforced by ``tests/test_crs.py``).

karpathy: thin and direct. Two pyproj transformers, two functions, one fail-closed
roundtrip guard. No site-local-frame offset (callers carry absolute UTM metres);
no class hierarchy. The transform is never hand-rolled (00-RESEARCH §Don't Hand-Roll)
— pyproj owns the projection math.
"""

from __future__ import annotations

# ── CANONICAL CONSTANTS ──────────────────────────────────────────────────────
# The single source of truth for the project CRS. Every spatial schema's
# _defs/crs const and the Node-side src/crs/crs.ts constant must agree with these.
EPSG: int = 32631  # UTM zone 31N — valid citywide in Barcelona, sub-metre distortion
UNITS: str = "metre"

# ── PYPROJ TRANSFORMERS (the only projection math in HeatGuard) ───────────────
# always_xy=True fixes call order: (lon, lat) -> (easting, northing) for _TO_UTM,
# (easting, northing) -> (lon, lat) for _TO_LONLAT. Consistent (lon, lat) order.
try:
    from pyproj import Transformer as _Transformer
except ImportError as _err:  # pragma: no cover - environment guard
    raise RuntimeError(
        "src.crs.crs requires pyproj. Install it with: pip install 'pyproj>=3.6,<4'. "
        "Do NOT hand-roll the lat/lon->UTM transform (00-RESEARCH Don't Hand-Roll)."
    ) from _err

_TO_UTM = _Transformer.from_crs("EPSG:4326", f"EPSG:{EPSG}", always_xy=True)
_TO_LONLAT = _Transformer.from_crs(f"EPSG:{EPSG}", "EPSG:4326", always_xy=True)


class CRSConsistencyError(RuntimeError):
    """Raised when a lon/lat -> UTM -> lon/lat round-trip exceeds tolerance.

    Fail-closed: when raised, the downstream spatial operation is aborted. The
    message names the round-trip error in metres.
    """


def to_utm31n(lon_deg: float, lat_deg: float) -> tuple[float, float]:
    """Convert WGS84 (lon, lat) in degrees to EPSG:32631 (x_m, y_m) in metres.

    THE single forward CRS conversion in HeatGuard. Import from here; do not
    reproduce the transform elsewhere (CONTRACT-01).

    Args:
        lon_deg: WGS84 longitude in decimal degrees.
        lat_deg: WGS84 latitude in decimal degrees.

    Returns:
        (x_m, y_m) — easting/northing in metres (EPSG:32631).
    """
    x_m, y_m = _TO_UTM.transform(lon_deg, lat_deg)
    return (x_m, y_m)


def to_lonlat(x_m: float, y_m: float) -> tuple[float, float]:
    """Convert EPSG:32631 (x_m, y_m) in metres back to WGS84 (lon, lat) in degrees.

    Exact algebraic inverse of :func:`to_utm31n` via the same pyproj UTM-31N
    transformer. THE single inverse CRS conversion in HeatGuard (CONTRACT-01).

    Args:
        x_m: easting in metres (EPSG:32631).
        y_m: northing in metres (EPSG:32631).

    Returns:
        (lon, lat) — WGS84 longitude/latitude in decimal degrees.
    """
    lon, lat = _TO_LONLAT.transform(x_m, y_m)
    return (lon, lat)


def assert_crs_roundtrip(lon_deg: float, lat_deg: float, tol_m: float = 0.001) -> float:
    """Fail-closed guard: a lon/lat -> UTM -> lon/lat round-trip must drift < tol_m.

    Projects (lon, lat) to EPSG:32631, projects straight back, and measures the
    ground error in **metres** (EPSG:32631 euclidean distance — not degrees).
    Raises :class:`CRSConsistencyError` if the drift reaches ``tol_m``; otherwise
    returns the round-trip error in metres.

    This is the lattice/units-drift tripwire (threat T-00-07 / Pitfall 5): a CRS
    misconfiguration produces a large round-trip error and aborts rather than
    silently emitting lat/lon coordinates downstream.

    Args:
        lon_deg: WGS84 longitude in decimal degrees.
        lat_deg: WGS84 latitude in decimal degrees.
        tol_m: tolerance in metres (default 1 mm).

    Returns:
        max_error_m — the round-trip error in metres (< tol_m).

    Raises:
        CRSConsistencyError: if the round-trip error is >= tol_m (fail-closed).
    """
    x_m, y_m = to_utm31n(lon_deg, lat_deg)
    lon2, lat2 = to_lonlat(x_m, y_m)
    # Re-project the round-tripped lon/lat to metres and measure euclidean drift.
    x2_m, y2_m = to_utm31n(lon2, lat2)
    error_m = ((x_m - x2_m) ** 2 + (y_m - y2_m) ** 2) ** 0.5
    if error_m >= tol_m:
        raise CRSConsistencyError(
            f"CRS round-trip drift {error_m:.6f} m >= tolerance {tol_m} m at "
            f"(lon={lon_deg}, lat={lat_deg}); EPSG:{EPSG} conversion is inconsistent."
        )
    return error_m
