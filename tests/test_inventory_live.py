"""Opt-in LIVE inventory-scraper smoke tests for the Phase-5 Material Recovery Inventory.

These are the ONLY tests in the Phase-5 suite that touch a real third-party source over the
network. They are gated with ``@pytest.mark.skipif(not os.getenv("HEATGUARD_LIVE_SCRAPE"), ...)``
so the DEFAULT run — the one CI and contributors execute with no flag — SKIPS them entirely:
no network, the offline suite stays green (mirror ``test_climate_live.py`` /
``describe.skipIf(!ANTHROPIC_API_KEY)``).

Pitfall 8 (NO mock data): each adapter must return >=1 REAL listing OR a LABELLED
``unavailable`` status — NEVER a synthetic/seeded listing. A flaky source is reported
unavailable, never faked.

NOTE (Plan 02): ``run_inventory_stage`` is the assumed entrypoint; ``client=None`` (or
``fetcher=None``) selects the production path — the adapter lazily imports the real fetch
library and reads any scrape/geocode key from the env (``${ORS_API_KEY}`` etc., never a
literal, never logged). If Plan 02 picks different names, update in lock-step.

To run it locally (opt-in):
    HEATGUARD_LIVE_SCRAPE=1 pytest tests/test_inventory_live.py -q
"""

from __future__ import annotations

import os

import pytest

_LIVE = os.getenv("HEATGUARD_LIVE_SCRAPE")

# Confirmed-live shade/structure sources (2026-06-22 supplier hunt): the Joomla scaffold
# source + verified EU/UK Shopify feeds carrying genuine shade-capable stock. The retired
# apparel shops (thefabricsales/fabricsight) are excluded from the smoke set.
_LIVE_SOURCES = ["exoandamiajes", "proflextruss", "tarpaulinsuppliesuk", "tarpaulinsuk"]


@pytest.mark.skipif(
    not _LIVE,
    reason="no HEATGUARD_LIVE_SCRAPE — opt-in live scraper smoke skipped (default suite offline)",
)
@pytest.mark.parametrize("source_id", _LIVE_SOURCES)
def test_live_source_returns_real_or_labelled_unavailable(source_id, tmp_path):
    """LIVE (opt-in): each real adapter returns >=1 REAL listing OR a LABELLED unavailable
    status — never a synthetic listing (Pitfall 8)."""
    from inventory.inventory import run_inventory_stage  # RED until Plan 02

    snapshot = run_inventory_stage(
        source_id,
        fetcher=None,  # production path: real adapter, key from env (never a literal)
        projects_root=tmp_path,
    )
    assert snapshot["status"] in ("live", "stale_snapshot", "unavailable"), (
        "a live run must carry a labelled status, never an unlabelled empty result"
    )
    if snapshot["status"] == "live":
        assert snapshot["listings"], (
            "a 'live' status must carry >=1 real listing (never an empty 'live')"
        )
    else:
        # A flaky/blocked source is reported unavailable or a labelled stale snapshot —
        # never faked. That is a PASS for the never-silent-drop discipline.
        assert snapshot["status"] in ("stale_snapshot", "unavailable")
