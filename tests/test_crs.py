"""Canonical CRS module (CONTRACT-01 / threat T-00-07 — lattice/units drift).

Asserts the single CRS boundary is EPSG:32631, that a real-site lon/lat round-trips
through UTM-31N within tolerance (fail-closed guard returns, does not raise), and
that the EPSG:25831 (ETRS89) trap does NOT leak into src/crs in either language.
"""

from pathlib import Path

import pytest

from crs.crs import (
    EPSG,
    UNITS,
    CRSConsistencyError,
    assert_crs_roundtrip,
    to_lonlat,
    to_utm31n,
)

_SRC_CRS_DIR = Path(__file__).resolve().parent.parent / "src" / "crs"

# Parc del Fòrum, Barcelona — HeatGuard's fixed site (PROJECT.md).
_FORUM_LON = 2.2203
_FORUM_LAT = 41.4106


def test_canonical_epsg_is_32631():
    assert EPSG == 32631
    assert UNITS == "metre"


def test_roundtrip_holds_on_site_coords():
    """lon/lat -> UTM31N -> lon/lat drifts < 1 mm at the real site (does not raise)."""
    error_m = assert_crs_roundtrip(_FORUM_LON, _FORUM_LAT, tol_m=0.001)
    assert error_m < 0.001


def test_forward_inverse_are_consistent():
    """to_lonlat is the algebraic inverse of to_utm31n within sub-mm."""
    x_m, y_m = to_utm31n(_FORUM_LON, _FORUM_LAT)
    # Forum sits in UTM zone 31N — eastings ~430 km, northings ~4.586 Mm.
    assert 400_000 < x_m < 500_000, x_m
    assert 4_500_000 < y_m < 4_650_000, y_m
    lon, lat = to_lonlat(x_m, y_m)
    assert abs(lon - _FORUM_LON) < 1e-7, lon
    assert abs(lat - _FORUM_LAT) < 1e-7, lat


def test_roundtrip_guard_is_fail_closed():
    """A tolerance of 0 m makes the guard fail closed (numerical drift > 0)."""
    with pytest.raises(CRSConsistencyError):
        assert_crs_roundtrip(_FORUM_LON, _FORUM_LAT, tol_m=0.0)


def test_no_etrs89_25831_leak_in_src_crs():
    """No source file under src/crs may reference the ETRS89 zone-31 variant."""
    trap = "258" + "31"  # split so this test file itself never carries the token
    for path in _SRC_CRS_DIR.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".ts"}:
            assert trap not in path.read_text(encoding="utf-8"), (
                f"{path} leaks EPSG:25831 (ETRS89) — inherit only EPSG:32631"
            )
