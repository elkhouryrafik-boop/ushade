"""Opt-in LIVE infrared.city fetch test for ``run_climate_stage`` (Plan 02a-04 Task 2).

This is the ONE test in the Phase-2a suite that touches the real infrared.city API (a
paid call + quota). It is gated with
``@pytest.mark.skipif(not os.getenv("INFRARED_API_KEY"), ...)`` so the DEFAULT run — the
one CI and contributors execute with no key — SKIPS it entirely: no network, no key, the
suite stays green and SDK-free (threat T-02a-14, mirroring the Phase-1 ``parser.live``
``describe.skipIf`` pattern). When a real key IS present in the environment it runs the
PRODUCTION path (``client=None`` -> ``fetch_utci`` lazily loads the real SDK, which reads
``INFRARED_API_KEY`` from the env itself) against the fixed Parc del Forum polygon.

Secrets (T-02a-14): the key is read from the environment ONLY — never hardcoded, never
logged, never passed as a literal. ``skipif`` means "no key -> no call", so the absence
of a key can never produce a failed run (only a SKIP).

To run it locally (opt-in):
    INFRARED_API_KEY=... pytest tests/test_climate_live.py -q
"""

from __future__ import annotations

import os

import pytest

from conftest_climate import load_site_polygon

from climate.climate import run_climate_stage
from validate.validate import validate

# A fixed test date in the Barcelona summer (single-month TimePeriod, peak-heat band).
LIVE_DATE = "2026-06-15"


@pytest.mark.skipif(
    not os.getenv("INFRARED_API_KEY"),
    reason="no INFRARED_API_KEY — opt-in live infrared fetch skipped (default suite stays network-free)",
)
def test_live_infrared_fetch_builds_valid_grid(tmp_path):
    """LIVE (opt-in): the real infrared path emits a contract-valid utci_grid.

    ``client=None`` selects the production path — ``fetch_utci`` lazily imports the real
    SDK, which reads ``INFRARED_API_KEY`` from the environment. The returned artifact must
    validate against the master ``utci_grid`` contract and carry the no-shade baseline
    (``baseline_utci_c == utci_c`` at emit, CLIMATE-04).
    """
    artifact = run_climate_stage(
        project_id="live-smoke",
        date=LIVE_DATE,
        site_polygon=load_site_polygon(),
        client=None,  # production path: real SDK reads the key from env (never a literal)
        projects_root=tmp_path,
    )

    # The single source-of-truth validator must accept the live result.
    validate(artifact, "utci_grid")
    assert artifact["cells"], "a live run must produce a non-empty master lattice"
    for cell in artifact["cells"]:
        assert cell["baseline_utci_c"] == cell["utci_c"], (
            "baseline_utci_c is the frozen no-shade denominator; equal to utci_c at emit"
        )
