"""Set-times demand-model tests — pure (json + numpy + constants), BASE suite (Plan 02.1-02).

``src/crowd/demand.py`` + the committed ``src/crowd/data/set_times_2026.json`` make stage
assignment time-weighted by REAL 2026 artist popularity (RESEARCH §Q5 — set times ARE published
+ scrapeable → IN SCOPE). The table is HAND-TRANSCRIBED from the official lineup + Clashfinder
``ps26`` (sourced + dated in a ``_meta`` block); popularity weights are ORDINAL (1–5) and ASSUMED.

The model is the demo's capacity-class FLOOR (``GOAL_WEIGHT_BY_CLASS``) MULTIPLIED by the active
headliner's popularity for the (stage, day, hour_block) slice (1.0 when no headliner is on that
stage in that slice). One representative Saturday-headliner-peak slice is the documented default
for the deterministic single-snapshot rollout (RESEARCH §Q5/A8).

These tests assert the plan's behaviour list (well-formed table, sourced+dated provenance,
class×popularity combination, determinism) and a STATIC purity guard. All run under
``pytest -q -m "not crowd"`` — pure, no crowd extra.
"""

from __future__ import annotations

import json
from pathlib import Path

from crowd.constants import GOAL_WEIGHT_BY_CLASS, GOAL_WEIGHT_DEFAULT
from crowd.demand import goal_weights_for_slice, load_set_times

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SET_TIMES_PATH = _REPO_ROOT / "src" / "crowd" / "data" / "set_times_2026.json"
_VIZ_DATA = _REPO_ROOT / "viz" / "data"


def _geojson_stage_names() -> set[str]:
    festival = json.loads((_VIZ_DATA / "festival_map_2026.geojson").read_text(encoding="utf-8"))
    return {
        f["properties"]["name"]
        for f in festival["features"]
        if f["properties"].get("layer") == "stage"
    }


# --------------------------------------------------------------------------- #
# Table well-formedness + provenance
# --------------------------------------------------------------------------- #
def test_set_times_table_well_formed():
    """Every row has the 5 required fields; ~20 headliner rows; stage_names ⊆ geojson stages."""
    table = load_set_times()
    rows = table["rows"]
    assert 15 <= len(rows) <= 30, f"expected ~20 headliner rows, got {len(rows)}"

    geojson_stages = _geojson_stage_names()
    for r in rows:
        for field in ("day", "hour_block", "stage_name", "headliner", "popularity_weight"):
            assert field in r, f"row missing {field!r}: {r}"
        assert isinstance(r["popularity_weight"], int)
        assert 1 <= r["popularity_weight"] <= 5, f"popularity_weight out of 1–5: {r}"
        assert r["stage_name"] in geojson_stages, (
            f"stage_name {r['stage_name']!r} not in geojson stages (map variants in transcription)"
        )


def test_set_times_sourced_and_dated():
    """The JSON carries a _meta block with source URLs + a transcription date + ASSUMED tier."""
    table = load_set_times()
    meta = table["_meta"]
    assert "source" in meta and len(meta["source"]) >= 1
    # Sources are URLs (official lineup + Clashfinder ps26).
    assert any("clashfinder" in s.lower() for s in meta["source"])
    assert any("primaverasound" in s.lower() for s in meta["source"])
    assert meta.get("transcribed_on") == "2026-06-10"
    assert meta.get("tier") == "ASSUMED"


# --------------------------------------------------------------------------- #
# Goal-weight combination (capacity-class × active-headliner popularity)
# --------------------------------------------------------------------------- #
def test_goal_weights_combine_class_and_popularity():
    """Per stage: class weight × active-headliner popularity (1.0 when no headliner in slice)."""
    import numpy as np

    table = load_set_times()
    # Pick a slice that has at least one headliner row.
    sample = table["rows"][0]
    day, hour_block = sample["day"], sample["hour_block"]
    active_stage = sample["stage_name"]
    pop = sample["popularity_weight"]

    # Find a stage GENUINELY idle in this (day, hour_block) slice — no headliner row for it.
    slice_stages = {
        r["stage_name"] for r in table["rows"] if r["day"] == day and r["hour_block"] == hour_block
    }
    idle_stage = next(s for s in ("Port", "Schwarzkopf", "Plenitude") if s not in slice_stages)

    # Two-stage probe: the active headliner stage (main) + the idle stage (no headliner this slice).
    stage_names = [active_stage, idle_stage]
    classes = ["main", "secondary"]
    w = goal_weights_for_slice(stage_names, classes, day=day, hour_block=hour_block)
    assert isinstance(w, np.ndarray)
    assert w.shape == (2,)

    # Active headliner stage: class weight × popularity.
    expected_active = GOAL_WEIGHT_BY_CLASS.get("main", GOAL_WEIGHT_DEFAULT) * pop
    assert w[0] == float(expected_active)
    # Idle stage in this slice → popularity 1.0 → just the class floor.
    expected_idle = GOAL_WEIGHT_BY_CLASS.get("secondary", GOAL_WEIGHT_DEFAULT) * 1.0
    assert w[1] == float(expected_idle)


def test_default_class_weight_when_class_unknown():
    """An unknown capacity class falls back to GOAL_WEIGHT_DEFAULT × popularity."""
    table = load_set_times()
    sample = table["rows"][0]
    w = goal_weights_for_slice(
        [sample["stage_name"]], ["promenade"], day=sample["day"], hour_block=sample["hour_block"]
    )
    expected = GOAL_WEIGHT_DEFAULT * sample["popularity_weight"]
    assert w[0] == float(expected)


def test_demand_deterministic():
    """Same slice + same table → identical weight vector (no RNG, pure)."""
    table = load_set_times()
    sample = table["rows"][0]
    args = dict(day=sample["day"], hour_block=sample["hour_block"])
    stages = [sample["stage_name"], "Auditori Rockdelux", "Port"]
    classes = ["main", "indoor", "secondary"]
    w1 = goal_weights_for_slice(stages, classes, **args)
    w2 = goal_weights_for_slice(stages, classes, **args)
    assert (w1 == w2).all()


# --------------------------------------------------------------------------- #
# Purity guard (static — demand.py imports json/numpy/constants only)
# --------------------------------------------------------------------------- #
def test_demand_is_pure():
    """demand.py imports json/numpy/constants only — NO torch/SB3/gymnasium in the text."""
    text = (_REPO_ROOT / "src" / "crowd" / "demand.py").read_text(encoding="utf-8")
    for forbidden in ("torch", "stable_baselines3", "gymnasium"):
        assert forbidden not in text, f"demand.py must be pure — found {forbidden!r}"
