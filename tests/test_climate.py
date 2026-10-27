"""RED test scaffold for the Climate Layer — CLIMATE-01..04 + CONTRACT-03 (Wave 0).

These tests are EXPECTED TO FAIL RED at collection: the module under test
(``climate.climate.run_climate_stage``) does NOT exist yet. Plan 03 wires the real
import + implementation; this scaffold locks the contract every later plan is verified
against. The fixtures (fake SDK client, recorded UTCI response, site polygon) are real
and live in ``tests/conftest_climate.py`` (imported below, NOT auto-discovered — pytest
only auto-loads ``conftest.py``, so this module imports the helpers explicitly).

Grid convention under test (RESEARCH Pitfall 1): row 0 = SOUTH, col 0 = WEST, NaN =
outside polygon. The <26 C drop is a SCORE-time filter (Phase 3), NOT a write-time drop
(RESEARCH Pitfall 2) — ``test_sub26_cells_preserved`` guards that.

NOTE (Plan 03): ``run_climate_stage`` is the assumed entrypoint name. If Plan 03 picks a
different name/signature, update the import + call sites here in lock-step.
"""

from __future__ import annotations

import math

import pytest

from conftest_climate import (
    FakeInfraredClient,
    load_recorded_utci_response,
    load_site_polygon,
)

# RED: this import fails until Plan 03 ships src/climate/climate.py. The whole module
# fails at collection — correct for a Wave 0 scaffold (RESEARCH §Wave 0 Gaps).
from climate.climate import run_climate_stage  # noqa: E402

# A fixed brief date drives the single-month TimePeriod (RESEARCH Pitfall 3).
BRIEF_DATE = "2026-06-15"


# --------------------------------------------------------------------------- #
# CLIMATE-01 — fetch builds a contract-valid grid + correct call sequence
# --------------------------------------------------------------------------- #
def test_fetch_builds_valid_grid(tmp_path):
    """CLIMATE-01: the stage run with the fake client emits a contract-valid utci_grid."""
    from validate.validate import validate

    fake = FakeInfraredClient()
    artifact = run_climate_stage(
        project_id="test",
        date=BRIEF_DATE,
        site_polygon=load_site_polygon(),
        client=fake,
        projects_root=tmp_path,
    )
    # Must validate against the master utci_grid contract (validate raises on failure).
    validate(artifact, "utci_grid")
    assert artifact["cells"], "artifact must carry at least one cell"


def test_call_sequence_contract(tmp_path):
    """CLIMATE-01: SAME single-month TimePeriod to both calls; preview gets analysis_type."""
    fake = FakeInfraredClient()
    run_climate_stage(
        project_id="test",
        date=BRIEF_DATE,
        site_polygon=load_site_polygon(),
        client=fake,
        projects_root=tmp_path,
    )
    # Pitfall 4: the SAME TimePeriod instance must reach filter_weather_data and
    # run_area_and_wait — a mismatch corrupts the result silently.
    assert fake.weather.last_time_period is fake.last_run_time_period
    tp = fake.last_run_time_period
    # Single-month window only (Pitfall 3): start_month == end_month.
    assert tp.start_month == tp.end_month
    # preview_area must be called with a non-None analysis_type or UTCI tiles undercount ~4x.
    assert fake.last_preview_analysis_type is not None


# --------------------------------------------------------------------------- #
# CLIMATE-02 — <26 C cells preserved in the artifact (drop is score-time)
# --------------------------------------------------------------------------- #
def test_sub26_cells_preserved(tmp_path):
    """CLIMATE-02: the known <26 C cell from the fixture is PRESENT in artifact cells."""
    fake = FakeInfraredClient()
    artifact = run_climate_stage(
        project_id="test",
        date=BRIEF_DATE,
        site_polygon=load_site_polygon(),
        client=fake,
        projects_root=tmp_path,
    )
    # The fixture seeds a 24.5 C interior cell; it must survive into the artifact
    # (Pitfall 2: the <26 drop is a Phase-3 Score-input filter, not data destruction).
    assert any(
        c["utci_c"] < 26.0 for c in artifact["cells"]
    ), "a <26 C cell must be preserved for the Phase 5b baseline"


# --------------------------------------------------------------------------- #
# CLIMATE-03 — cache, live-call cap, EPW fallback, fail-not-done
# --------------------------------------------------------------------------- #
def test_cache_hit_no_live_call(tmp_path):
    """CLIMATE-03: a second run on an unchanged (site, date) makes ZERO new live calls."""
    fake = FakeInfraredClient()
    common = dict(
        project_id="test",
        date=BRIEF_DATE,
        site_polygon=load_site_polygon(),
        client=fake,
        projects_root=tmp_path,
    )
    run_climate_stage(**common)
    run_climate_stage(**common)  # cache hit — must NOT dispatch a second live run
    assert fake.run_count == 1, "cache hit must not spend a live run_area_and_wait call"


def test_live_call_cap_raises(tmp_path):
    """CLIMATE-03: forcing >3 live dispatches raises RuntimeError mentioning the cap."""
    fake = FakeInfraredClient()
    with pytest.raises(RuntimeError, match="cap"):
        # Distinct dates bypass the cache so each forces a live dispatch; the 4th
        # must trip the LiveCallBudget(cap=3) backstop.
        for i in range(4):
            run_climate_stage(
                project_id="test",
                date=f"2026-06-1{i}",
                site_polygon=load_site_polygon(),
                client=fake,
                projects_root=tmp_path,
            )


def test_weather_epw_fallback_labelled(tmp_path):
    """CLIMATE-03: weather 500 -> EPW fallback still produces a grid AND a labelled source."""
    fake = FakeInfraredClient(weather_500=True)
    artifact = run_climate_stage(
        project_id="test",
        date=BRIEF_DATE,
        site_polygon=load_site_polygon(),
        client=fake,
        projects_root=tmp_path,
    )
    # The run still yields a grid (never fabricated) and records a non-infrared weather
    # source in provenance — labelled, never silently substituted.
    assert artifact["cells"], "EPW fallback must still produce a grid"
    assert artifact.get("_weather_source") not in (None, "infrared"), (
        "EPW-sourced weather must be explicitly labelled in provenance"
    )


def test_failure_leaves_stage_not_done(tmp_path):
    """CLIMATE-03: AreaRunError -> manifest stage NOT done and NO artifact file written."""
    fake = FakeInfraredClient(raise_area_error=True)
    with pytest.raises(RuntimeError):
        run_climate_stage(
            project_id="test",
            date=BRIEF_DATE,
            site_polygon=load_site_polygon(),
            client=fake,
            projects_root=tmp_path,
        )
    # No partial artifact on failure (Pitfall 7).
    assert not (tmp_path / "test" / "utci_grid.json").exists()


# --------------------------------------------------------------------------- #
# CLIMATE-04 — per-cell no-shade baseline emitted (== utci_c at emit)
# --------------------------------------------------------------------------- #
def test_baseline_emitted(tmp_path):
    """CLIMATE-04: every cell carries baseline_utci_c == utci_c at emit time."""
    fake = FakeInfraredClient()
    artifact = run_climate_stage(
        project_id="test",
        date=BRIEF_DATE,
        site_polygon=load_site_polygon(),
        client=fake,
        projects_root=tmp_path,
    )
    assert artifact["cells"]
    for cell in artifact["cells"]:
        assert cell["baseline_utci_c"] == cell["utci_c"], (
            "baseline_utci_c is the frozen no-shade denominator; equal to utci_c at emit"
        )


# --------------------------------------------------------------------------- #
# CONTRACT-03 — master lattice descriptor (EPSG:32631, no lat/lon leak)
# --------------------------------------------------------------------------- #
def test_master_lattice_descriptor(tmp_path):
    """CONTRACT-03: lattice has all 5 keys, cell_size_m==6.0, CRS 32631, projected metres."""
    fake = FakeInfraredClient()
    artifact = run_climate_stage(
        project_id="test",
        date=BRIEF_DATE,
        site_polygon=load_site_polygon(),
        client=fake,
        projects_root=tmp_path,
    )
    lattice = artifact["lattice"]
    assert set(lattice) >= {"origin_x_m", "origin_y_m", "cell_size_m", "cols", "rows"}
    assert lattice["cell_size_m"] == 6.0, "master resolution locked at 6.0 m (Open Q1)"
    assert artifact["crs"] == {"epsg": 32631, "units": "metre"}
    # No lat/lon leak (Pitfall 1): projected EPSG:32631 metres are O(100k+), never
    # degree-magnitude. At least one cell must read as projected metres, not degrees.
    assert any(
        abs(c["x_m"]) > 180 for c in artifact["cells"]
    ), "cells must be projected metres (no lon/lat leak)"
    # Sanity: no NaN coordinates leaked through the crop.
    assert all(
        not math.isnan(c["x_m"]) and not math.isnan(c["y_m"]) for c in artifact["cells"]
    )
