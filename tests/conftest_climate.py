"""Reusable FAKE infrared.city SDK client + fixture loaders for the offline Climate suite.

The default Phase 2a test suite runs with NO ``infrared-sdk`` installed (Pitfall 6;
the SDK lives in the OPTIONAL ``live`` extra). This module therefore imports the real
SDK **nowhere** — ``FakeInfraredClient`` is a pure-Python object that mimics the exact
call surface ``src/climate`` will exercise (RESEARCH §Code Examples / Wave 0 Gaps):

    client.weather.get_weather_file_from_location(lat, lon, radius) -> [{"uuid": ...}]
    client.weather.filter_weather_data(identifier, time_period)     -> weather_data
    client.buildings.get_area(polygon)                              -> area (area.buildings)
    client.preview_area(polygon, analysis_type=...)                 -> preview dict
    client.run_area_and_wait(payload, polygon, buildings=...)       -> FakeAreaResult
        result.merged_grid -> 2-D list (row0=SOUTH, col0=WEST, NaN outside, deg C)
        result.bounds      -> (min_lng, min_lat, max_lng, max_lat) WGS84 (SDK 0.4.4+)

The client RECORDS what it was called with (time_period on both weather + run calls,
preview analysis_type, a live-run counter) so the call-sequence contract tests
(CLIMATE-01) can assert the SAME single-month TimePeriod was passed to
``filter_weather_data`` and ``run_area_and_wait`` (Pitfall 4) and that
``preview_area`` got a non-None ``analysis_type`` (Site-Geometry tile-count check).

Failure modes (``raise_area_error``, ``weather_500``) let later tests exercise the
EPW-fallback (CLIMATE-03) and the fail-stage-not-done (CLIMATE-03) paths.

``null`` cells in the recorded fixture are converted to ``float('nan')`` on load so the
fake's ``merged_grid`` matches what the real SDK returns (NaN outside the polygon).

karpathy: one fake object, no mock framework, no real SDK import.
"""

from __future__ import annotations

import json
from math import isnan
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_INFRARED_FIXTURE = _TESTS_DIR / "fixtures" / "infrared" / "utci_response_small.json"
_SITE_FIXTURE = _TESTS_DIR / "fixtures" / "climate" / "parc_del_forum.geojson"


# --------------------------------------------------------------------------- #
# Fixture loaders
# --------------------------------------------------------------------------- #
def load_recorded_utci_response() -> dict:
    """Load the recorded UTCI response fixture (merged_grid still as JSON null)."""
    return json.loads(_INFRARED_FIXTURE.read_text(encoding="utf-8"))


def load_site_polygon() -> dict:
    """Load the fixed-site Parc del Forum boundary fixture (WGS84 closed ring)."""
    return json.loads(_SITE_FIXTURE.read_text(encoding="utf-8"))


def _grid_with_nan(grid: list[list]) -> list[list[float]]:
    """Convert JSON ``null`` cells to ``float('nan')`` (NaN = outside polygon)."""
    return [[float("nan") if c is None else float(c) for c in row] for row in grid]


# --------------------------------------------------------------------------- #
# Fake SDK surface
# --------------------------------------------------------------------------- #
class FakeAreaResult:
    """Mimics the real ``AreaResult``: per-cell grid + georeferencing + job status."""

    def __init__(self, response: dict):
        self.merged_grid = _grid_with_nan(response["merged_grid"])
        self.bounds = tuple(response["bounds"])  # (min_lng, min_lat, max_lng, max_lat)
        self.min_legend = response.get("min_legend")
        self.max_legend = response.get("max_legend")
        # ≥1 success returns an AreaResult with these populated (empty == all-OK).
        self.failed_jobs: list = []
        self.skipped_jobs: list = []


class _FakeWeather:
    """Mimics ``client.weather`` — station lookup + time-windowed weather pull."""

    def __init__(self, weather_500: bool):
        self._weather_500 = weather_500
        self.last_time_period = None  # records the tp passed to filter_weather_data

    def get_weather_file_from_location(self, lat, lon, radius=50):
        if self._weather_500:
            # The documented weather-endpoint 500 (since 2026-05-29). The stage is
            # expected to fall back to a bundled EPW (labelled provenance), not fake.
            raise RuntimeError("infrared weather endpoint returned HTTP 500")
        return [{"uuid": "fake-station"}]

    def filter_weather_data(self, identifier, time_period):
        if self._weather_500:
            raise RuntimeError("infrared weather endpoint returned HTTP 500")
        self.last_time_period = time_period
        return {"_fake_weather_data": True, "identifier": identifier}


class _FakeBuildings:
    """Mimics ``client.buildings`` — building footprints ground the MRT shadow grid."""

    def get_area(self, polygon):
        class _Area:
            buildings: list = []

        return _Area()


class FakeInfraredClient:
    """Pure-Python stand-in for ``infrared_sdk.InfraredClient`` (NO real SDK import).

    Records the call surface so the offline contract tests can assert the call
    sequence without any network or paid SDK. Supports a context-manager protocol
    so ``with FakeInfraredClient() as c:`` mirrors the real client's usage.

    Args:
        raise_area_error: when True, ``run_area_and_wait`` raises (simulates a total
            tile failure / ``AreaRunError``) so the fail-stage-not-done test fires.
        weather_500: when True, the weather calls raise HTTP-500 so the EPW-fallback
            path is exercised.
    """

    def __init__(self, raise_area_error: bool = False, weather_500: bool = False):
        self.raise_area_error = raise_area_error
        self.weather = _FakeWeather(weather_500=weather_500)
        self.buildings = _FakeBuildings()
        # Recorded call state for the contract assertions.
        self.last_preview_analysis_type = None
        self.last_run_time_period = None
        self.run_count = 0  # number of LIVE run_area_and_wait dispatches

    # -- context manager -------------------------------------------------- #
    def __enter__(self) -> "FakeInfraredClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False  # do not suppress exceptions

    # -- call surface ----------------------------------------------------- #
    def preview_area(self, polygon, analysis_type=None):
        # Always pass analysis_type or the SDK under-counts UTCI tiles ~4x
        # (RESEARCH §Site Geometry). Record it so the contract test can assert it.
        self.last_preview_analysis_type = analysis_type
        return {"tiles": 1, "estimated_cost_tokens": 10}

    def run_area_and_wait(self, payload, polygon, buildings=None):
        self.run_count += 1
        # Record the TimePeriod carried on the payload so a test can assert it is the
        # SAME instance handed to filter_weather_data (Pitfall 4: mismatch corrupts
        # the result silently).
        self.last_run_time_period = getattr(payload, "time_period", None)
        if self.raise_area_error:
            raise RuntimeError("AreaRunError: every job failed")
        return FakeAreaResult(load_recorded_utci_response())


# --------------------------------------------------------------------------- #
# pytest fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def fake_infrared_client() -> FakeInfraredClient:
    """A fresh fake SDK client (default success path)."""
    return FakeInfraredClient()


@pytest.fixture
def recorded_utci_response() -> dict:
    """The recorded UTCI response fixture (merged_grid as JSON null, not NaN)."""
    return load_recorded_utci_response()


@pytest.fixture
def site_polygon() -> dict:
    """The fixed-site Parc del Forum boundary (WGS84 closed-ring Polygon Feature)."""
    return load_site_polygon()
