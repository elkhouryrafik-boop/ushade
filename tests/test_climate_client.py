"""Offline tests for the infrared fetch seam (CLIMATE-01/03) — NO SDK, NO network.

Drives ``fetch_utci`` with a ``client_factory`` returning the Plan-01
``FakeInfraredClient`` (the injection seam). Asserts the call-sequence
contracts the FakeInfraredClient records — the SAME single-month TimePeriod to
both calls (Pitfall 4), the single-month window (Pitfall 3), ``preview_area``
with ``analysis_type`` (UTCI tile-count correctness), the 12-16 peak-heat band,
the 3-call live cap (T-02a-08), the LABELLED EPW fallback on a weather-500
(Pitfall 5 / T-02a-09), ``ClimateFetchError`` wrapping of SDK area errors and
partial-tile failures (Pitfall 7 / T-02a-09), and that the return is the RAW
2-D grid, never a scalar mean (Anti-pattern guard).

All GREEN with no ``infrared-sdk`` installed.
"""

from __future__ import annotations

import datetime
from math import isnan

import pytest

from climate.infrared_client import (
    PEAK_HEAT_HOUR_BAND,
    ClimateFetchError,
    LiveCallBudget,
    fetch_utci,
)

# conftest_climate is imported explicitly (pytest only auto-loads conftest.py).
from conftest_climate import FakeInfraredClient, load_site_polygon

# A fixed brief date for the single-month window assertions.
_DATE = datetime.date(2026, 7, 15)


def _polygon() -> dict:
    """The fixed-site Parc del Forum boundary geometry (WGS84 closed ring)."""
    feature = load_site_polygon()
    return feature["geometry"] if "geometry" in feature else feature


def _run(fake: FakeInfraredClient, *, date=_DATE, weather_mode="auto", budget=None):
    """Drive fetch_utci with a client_factory that returns the given fake client."""
    return fetch_utci(
        lat=41.4106,
        lon=2.2203,
        polygon=_polygon(),
        date=date,
        weather_mode=weather_mode,
        budget=budget,
        client_factory=lambda: fake,
    )


# --------------------------------------------------------------------------- #
# Call-sequence discipline (CLIMATE-01)
# --------------------------------------------------------------------------- #
def test_same_time_period_to_both_calls():
    """Pitfall 4: the SAME tp instance reaches filter_weather_data AND the run."""
    fake = FakeInfraredClient()
    _run(fake)
    assert fake.weather.last_time_period is not None
    assert fake.last_run_time_period is not None
    # Same instance handed to both calls (enforced by construction in fetch_utci).
    assert fake.weather.last_time_period is fake.last_run_time_period


def test_time_period_single_month():
    """Pitfall 3: the built tp is a single-month window (start_month == end_month)."""
    fake = FakeInfraredClient()
    _run(fake)
    tp = fake.last_run_time_period
    assert tp.start_month == tp.end_month
    assert tp.start_month == _DATE.month
    assert tp.start_day == tp.end_day == _DATE.day


def test_preview_called_with_analysis_type():
    """preview_area must receive a non-None analysis_type (UTCI tile-count, ~4x)."""
    fake = FakeInfraredClient()
    _run(fake)
    assert fake.last_preview_analysis_type is not None


def test_hour_band_is_12_16():
    """The tp hour band equals PEAK_HEAT_HOUR_BAND == (12, 16)."""
    assert PEAK_HEAT_HOUR_BAND == (12, 16)
    fake = FakeInfraredClient()
    _run(fake)
    tp = fake.last_run_time_period
    assert (tp.start_hour, tp.end_hour) == PEAK_HEAT_HOUR_BAND


# --------------------------------------------------------------------------- #
# Live-call cap (CLIMATE-03 / T-02a-08)
# --------------------------------------------------------------------------- #
def test_live_call_cap_raises():
    """A LiveCallBudget(cap=1) trips on the second live record -> ClimateFetchError."""
    fake = FakeInfraredClient()
    # fetch_utci records "preview" then "run" — a cap of 1 must raise on the second.
    with pytest.raises(ClimateFetchError) as excinfo:
        _run(fake, budget=LiveCallBudget(cap=1))
    assert "cap" in str(excinfo.value)
    assert "1" in str(excinfo.value)


def test_budget_default_allows_one_run():
    """The default cap=3 comfortably permits the 2 live records of one run."""
    budget = LiveCallBudget()
    _run(FakeInfraredClient(), budget=budget)
    assert budget.n == 2  # preview + run
    assert budget.cap == 3


# --------------------------------------------------------------------------- #
# Weather-500 -> labelled EPW fallback (CLIMATE-03 / T-02a-09)
# --------------------------------------------------------------------------- #
def test_weather_500_falls_back_labelled():
    """Pitfall 5: weather-500 -> weather_source == 'epw-barcelona' (labelled, grid still returned)."""
    fake = FakeInfraredClient(weather_500=True)
    merged_grid, bounds, weather_source = _run(fake)
    assert weather_source == "epw-barcelona"  # labelled, never silent
    assert merged_grid is not None
    assert bounds is not None


def test_infrared_weather_source_on_success():
    """The happy path is labelled 'infrared' (GROUNDED direct output)."""
    _, _, weather_source = _run(FakeInfraredClient())
    assert weather_source == "infrared"


def test_forced_infrared_weather_500_raises():
    """weather_mode='infrared' disables the EPW fallback -> ClimateFetchError on 500."""
    fake = FakeInfraredClient(weather_500=True)
    with pytest.raises(ClimateFetchError):
        _run(fake, weather_mode="infrared")


# --------------------------------------------------------------------------- #
# Error typing (CLIMATE-03 / Pitfall 7)
# --------------------------------------------------------------------------- #
def test_area_error_wrapped():
    """Pitfall 7: a total tile failure surfaces as ClimateFetchError, not a bare SDK error."""
    fake = FakeInfraredClient(raise_area_error=True)
    with pytest.raises(ClimateFetchError):
        _run(fake)


def test_partial_tile_failure_raises():
    """CONTEXT Q4: a result with non-empty failed_jobs raises (no holey grid returned)."""
    fake = FakeInfraredClient()
    # Patch the fake's run to return a result carrying a failed tile job.
    base_result_loader = fake.run_area_and_wait

    def _run_with_failed_tile(payload, polygon, buildings=None):
        result = base_result_loader(payload, polygon, buildings=buildings)
        result.failed_jobs = [{"tile": "interior", "error": "inference failed"}]
        return result

    fake.run_area_and_wait = _run_with_failed_tile
    with pytest.raises(ClimateFetchError) as excinfo:
        _run(fake)
    assert "holey" in str(excinfo.value) or "failed" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# Raw grid, not a scalar (Anti-pattern guard)
# --------------------------------------------------------------------------- #
def test_returns_raw_grid_not_scalar():
    """The returned merged_grid is 2-D (rows of cells), NOT a single float mean."""
    merged_grid, bounds, _ = _run(FakeInfraredClient())
    # 2-D: a sequence of sequences (len-of-len), not a scalar.
    assert hasattr(merged_grid, "__len__")
    assert len(merged_grid) > 0
    assert hasattr(merged_grid[0], "__len__")  # each row is itself a sequence
    assert len(merged_grid[0]) > 0
    assert not isinstance(merged_grid, (int, float))
    # bounds is the 4-tuple WGS84 extent.
    assert len(bounds) == 4


def test_returned_grid_carries_nan_outside_polygon():
    """The raw grid preserves NaN (outside-polygon) cells — not zero-filled."""
    merged_grid, _, _ = _run(FakeInfraredClient())
    flat = [c for row in merged_grid for c in row]
    assert any(isnan(c) for c in flat)  # NaN border survives in the raw grid
