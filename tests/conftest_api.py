"""Wave 0 conftest for FastAPI endpoint tests.

Provides mock_run_climate_stage and mock_run_crowd_stage fixtures that return
immediately (no torch/SB3/network). Injected via monkeypatch in test_api.py.
"""
import json
import pytest
from pathlib import Path


FAKE_UTCI_ARTIFACT = {
    "schema_version": "1.0.0",
    "site_id": "parc-del-forum",
    "date": "2026-06-14",
    "cell_size_m": 6.0,
    "crs": "EPSG:32631",
    "baseline_utci_c": 22.7,
    "cells": [{"x_m": 0.0, "y_m": 0.0, "utci_c": 22.7}],
    "lattice": {"origin_x_m": 0.0, "origin_y_m": 0.0, "cell_size_m": 6.0, "crs": "EPSG:32631"},
    "weather_source": "ASSUMED",
    "provenance": {"utci": "GROUNDED"},
}

FAKE_CROWD_ARTIFACT = {
    "schema_version": "1.0.0",
    "site_id": "parc-del-forum",
    "cells": [{"x_m": 0.0, "y_m": 0.0, "density": 0.1}],
    "dwell_zones": [],
    "flow_vectors": [],
    "lattice": {"origin_x_m": 0.0, "origin_y_m": 0.0, "cell_size_m": 6.0, "crs": "EPSG:32631"},
    "provenance": {"crowd_density": "ASSUMED"},
    "sim_seed": 1789,
}


@pytest.fixture()
def mock_climate(monkeypatch):
    """Replace run_climate_stage with a fast stub returning FAKE_UTCI_ARTIFACT."""
    import src.api.app as app_module

    def _fake_run_climate(project_id, date, *, site_polygon, projects_root=None, **kw):
        return FAKE_UTCI_ARTIFACT

    monkeypatch.setattr(app_module, "run_climate_stage", _fake_run_climate)
    return _fake_run_climate


@pytest.fixture()
def mock_crowd(monkeypatch):
    """Replace run_crowd_stage with a fast stub returning FAKE_CROWD_ARTIFACT."""
    import src.api.app as app_module

    def _fake_run_crowd(project_id, *, projects_root=None, **kw):
        return FAKE_CROWD_ARTIFACT

    monkeypatch.setattr(app_module, "run_crowd_stage", _fake_run_crowd)
    return _fake_run_crowd
