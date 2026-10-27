"""Offline tests for the NEW infrared usage: ground/veg overlays + diagnostic layers.

Covers the three pieces added when we stopped using infrared as UTCI-only:
  1. ``_fetch_optional_layers`` — ground-material + vegetation overlays are injected when
     the client exposes them, and skipped (None, None) when it does not (the SDK-free fake),
     so the existing offline UTCI seam is byte-unchanged.
  2. ``fetch_utci`` — passes ``vegetation`` / ``ground_materials`` to ``run_area_and_wait``
     only when present (the EMISSIVITY-0.97 fix the friend pointed at).
  3. ``grid_to_value_artifact`` — generic sibling of ``grid_to_utci_artifact`` lands a scalar
     analysis on the SAME 6 m master lattice under a caller-named value key.

The multi-analysis live builders need the real SDK types, so that test is
``importorskip``-guarded — the default SDK-free suite skips it.
"""

from __future__ import annotations

import datetime

import pytest

from climate.infrared_client import _fetch_optional_layers, fetch_utci
from climate.lattice import grid_to_utci_artifact, grid_to_value_artifact
from conftest_climate import (
    FakeInfraredClient,
    load_recorded_utci_response,
    load_site_polygon,
)

_DATE = datetime.date(2026, 7, 15)


def _polygon() -> dict:
    feature = load_site_polygon()
    return feature["geometry"] if "geometry" in feature else feature


# --------------------------------------------------------------------------- #
# Local overlay-exposing stub (NOT the shared fake — keeps conftest untouched)
# --------------------------------------------------------------------------- #
class _AreaStub:
    def __init__(self, features=None, layers=None):
        self.features = features
        self.layers = layers


class _LayerApiStub:
    """Mimics ``client.vegetation`` / ``client.ground_materials`` (``.get_area().features|layers``)."""

    def __init__(self, features=None, layers=None):
        self._area = _AreaStub(features=features, layers=layers)

    def get_area(self, polygon):
        return self._area


class _OverlayClient(FakeInfraredClient):
    """The success fake + ground/vegetation accessors + records run kwargs."""

    def __init__(self, *, veg=None, ground=None):
        super().__init__()
        self.vegetation = _LayerApiStub(features=veg)
        self.ground_materials = _LayerApiStub(layers=ground)
        self.last_run_kwargs: dict = {}

    def run_area_and_wait(self, payload, polygon, buildings=None, vegetation=None, ground_materials=None):
        self.last_run_kwargs = {"vegetation": vegetation, "ground_materials": ground_materials}
        return super().run_area_and_wait(payload, polygon, buildings=buildings)


# --------------------------------------------------------------------------- #
# 1) _fetch_optional_layers
# --------------------------------------------------------------------------- #
def test_optional_layers_absent_on_plain_fake():
    """The SDK-free fake exposes neither accessor -> (None, None): seam byte-unchanged."""
    assert _fetch_optional_layers(FakeInfraredClient(), _polygon()) == (None, None)


def test_optional_layers_fetched_when_exposed():
    """A client exposing .vegetation/.ground_materials returns their features/layers."""
    veg = {"tree_1": {"type": "Feature"}}
    ground = {"asphalt": {"type": "FeatureCollection", "features": []}}
    got_veg, got_ground = _fetch_optional_layers(
        _OverlayClient(veg=veg, ground=ground), _polygon()
    )
    assert got_veg == veg
    assert got_ground == ground


def test_optional_layers_empty_treated_as_none():
    """Empty dicts mean 'skip' (byo-inputs: {} == None) -> not injected."""
    assert _fetch_optional_layers(_OverlayClient(veg={}, ground={}), _polygon()) == (None, None)


# --------------------------------------------------------------------------- #
# 2) fetch_utci passes the overlays through
# --------------------------------------------------------------------------- #
def test_fetch_utci_injects_overlays_when_present():
    """The emissivity-0.97 fix: ground + vegetation reach run_area_and_wait."""
    veg = {"tree_1": {"type": "Feature"}}
    ground = {"asphalt": {"type": "FeatureCollection", "features": []}}
    client = _OverlayClient(veg=veg, ground=ground)
    fetch_utci(lat=41.41, lon=2.22, polygon=_polygon(), date=_DATE, client_factory=lambda: client)
    assert client.last_run_kwargs["vegetation"] == veg
    assert client.last_run_kwargs["ground_materials"] == ground


def test_fetch_utci_skips_overlays_when_absent():
    """No accessors -> kwargs never sent; original two-positional call preserved."""
    client = FakeInfraredClient()
    # Would raise TypeError if fetch_utci passed vegetation/ground_materials kwargs.
    merged_grid, bounds, src = fetch_utci(
        lat=41.41, lon=2.22, polygon=_polygon(), date=_DATE, client_factory=lambda: client
    )
    assert merged_grid is not None and src == "infrared"


# --------------------------------------------------------------------------- #
# 3) grid_to_value_artifact shares the master lattice, swaps the value key
# --------------------------------------------------------------------------- #
def test_value_artifact_shares_lattice_and_uses_key():
    resp = load_recorded_utci_response()
    grid, bounds = resp["merged_grid"], tuple(resp["bounds"])
    grid = [[float("nan") if c is None else float(c) for c in row] for row in grid]

    utci = grid_to_utci_artifact(grid, bounds)
    sun = grid_to_value_artifact(grid, bounds, value_key="sun_hours")

    # SAME master lattice (origin, cell size, dims) — every layer snaps identically.
    assert sun["lattice"] == utci["lattice"]
    assert len(sun["cells"]) == len(utci["cells"])
    # Value key swapped; no UTCI baseline twin on a generic layer.
    cell = sun["cells"][0]
    assert "sun_hours" in cell and "utci_c" not in cell and "baseline_utci_c" not in cell
    assert set(cell) == {"x_m", "y_m", "sun_hours"}


# --------------------------------------------------------------------------- #
# Live builders (need the real SDK types) — skipped in the SDK-free suite
# --------------------------------------------------------------------------- #
def test_diagnostic_specs_build_real_payloads():
    pytest.importorskip("infrared_sdk")
    from climate.multi_analysis import (
        DEFAULT_ANALYSES,
        _ANALYSIS_SPECS,
        _build_time_period,
        _load_diagnostic_sdk,
    )

    sdk = _load_diagnostic_sdk()
    tp = _build_time_period(sdk, _DATE, (9, 20))
    assert tp.start_month == tp.end_month  # single-month window

    # The geometry-only analysis (sun-hours) builds a real payload with NO weather.
    builder, atype_attr, needs_weather = _ANALYSIS_SPECS["direct_sun_hours"]
    payload = builder(sdk, 41.41, 2.22, tp, None)
    assert payload.analysis_type == sdk["AnalysesName"].direct_sun_hours
    assert needs_weather is False

    # The weather-driven analyses are wired (callable builder + need-weather flag); their
    # real payloads require non-empty weather arrays, so they're built live, not here.
    for key in ("solar_radiation", "tcs_heat_stress"):
        builder, atype_attr, needs_weather = _ANALYSIS_SPECS[key]
        assert callable(builder) and needs_weather is True
    assert set(DEFAULT_ANALYSES) == set(_ANALYSIS_SPECS)
