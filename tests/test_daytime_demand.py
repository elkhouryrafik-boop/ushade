"""DAYCROWD-01 — daytime demand formula (BASE tier, no marker).

The continuous daytime sim is driven by a per-(hour, stage) demand weight::

    demand[hour, stage] = capacity_floor(stage) × draw(stage) × active(hour, stage) × occupancy(hour)

where ``capacity_floor`` is ``GOAL_WEIGHT_BY_CLASS.get(cls, GOAL_WEIGHT_DEFAULT)`` (REUSED from the
night model — same capacity-class floors), ``draw`` is the organiser's optional 1-5 ordinal pull,
``active`` is ``1.0`` while the stage is inside its ``active_hours`` else ``ACTIVE_BASELINE`` (the
NAMED low-but-nonzero people-mill pull — never 0, never 1.0), and ``occupancy`` is the site-wide
fraction-of-peak from ``occupancy_curve_2026.json``.

These tests run in the BASE tier (no jupedsim): the daytime demand helper is a pure
numpy/stdlib transform. They are DESIGNED-RED at Wave 0 — they import the not-yet-written
``crowd.daytime_demand`` (Plan 02 turns them GREEN). They COLLECT cleanly: the only import-time
failure is the genuinely-absent helper module, surfaced via a skip-guard so every behaviour is
NAMED now and the file never errors on a typo.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path

import pytest

# The NAMED anti-tuning constant the formula reads (NOT an inline 0.1) — imported from the ONE
# place it lives (crowd.constants), so a tuned-to-pass literal would diverge from this assertion.
from crowd.constants import ACTIVE_BASELINE, DAYTIME_HOURS, GOAL_WEIGHT_BY_CLASS, GOAL_WEIGHT_DEFAULT

# Wave-0 RED seam: the daytime demand helper does not exist until Plan 02. Skip-guard so the file
# COLLECTS cleanly (the RED is asserted at call-time, not as a collection ImportError/typo). Plan 02
# drops this guard's effect by shipping crowd.daytime_demand.
_HELPER_PRESENT = importlib.util.find_spec("crowd.daytime_demand") is not None
pytestmark = pytest.mark.skipif(
    not _HELPER_PRESENT,
    reason="crowd.daytime_demand absent — Wave-0 RED scaffold (GREEN at Plan 02)",
)

if _HELPER_PRESENT:  # pragma: no cover - exercised once Plan 02 ships the helper
    from crowd.daytime_demand import daytime_demand_table  # noqa: F401

_DATA = Path(__file__).resolve().parents[1] / "src" / "crowd" / "data"
_PROGRAM = json.loads((_DATA / "daytime_program_2026.json").read_text(encoding="utf-8"))
_OCCUPANCY = json.loads((_DATA / "occupancy_curve_2026.json").read_text(encoding="utf-8"))


def test_formula_matches_capacity_floor_times_draw_times_active_times_occupancy():
    """One hand-computed (hour, stage) cell equals floor × draw × active × occupancy.

    Pick Occident at 15:00 (active that hour, draw=5) on the default 'late' profile. The expected
    cell is the product of the four named factors over the COMMITTED data files — no fudge.
    """
    from crowd.daytime_demand import daytime_demand_table

    table = daytime_demand_table(program=_PROGRAM, occupancy=_OCCUPANCY)
    hour, stage = "15:00", "Occident"
    cls = "main"  # capacity class the demo assigns Occident; floor via the night model's map
    floor = GOAL_WEIGHT_BY_CLASS.get(cls, GOAL_WEIGHT_DEFAULT)
    draw = _PROGRAM["stage_program"][stage]["draw"]
    active = 1.0  # 15:00 ∈ Occident.active_hours
    occ = _OCCUPANCY["profiles"][_OCCUPANCY["default_profile"]]["occupancy"][DAYTIME_HOURS.index(hour)]
    expected = floor * draw * active * occ
    assert table[(hour, stage)] == pytest.approx(expected)


def test_active_baseline_is_named_constant_0_1():
    """An INACTIVE stage's active() factor is ACTIVE_BASELINE (the NAMED constant); active → 1.0.

    Plenitude is live ONLY at 19:00/20:00 — at 09:00 it is inactive, so its active() factor must be
    EXACTLY ``ACTIVE_BASELINE`` (read from crowd.constants, not a tuned inline 0.1). At 19:00 it is
    active → factor 1.0. Asserting the RATIO isolates active() from the occupancy/floor/draw factors.
    """
    from crowd.daytime_demand import active_factor

    assert active_factor("Plenitude", "09:00", program=_PROGRAM) == ACTIVE_BASELINE
    assert active_factor("Plenitude", "19:00", program=_PROGRAM) == 1.0


def test_missing_program_raises_hard_error():
    """No organiser program → hard ValueError. NO assumed fallback rotation (program is REQUIRED)."""
    from crowd.daytime_demand import daytime_demand_table

    with pytest.raises(ValueError):
        daytime_demand_table(program=None, occupancy=_OCCUPANCY)


def test_int_001_stage_names_match():
    """INT-001: every stage in the daytime program is a real geojson / night-table stage name.

    A program stage that does not match the committed stage set would silently model a ghost crowd
    (T-16-03 spoofing). Assert the 7 demo program stages are a SUBSET of the geojson stage names.
    """
    geojson = json.loads(
        (Path(__file__).resolve().parents[1] / "viz" / "data" / "festival_map_2026.geojson").read_text(
            encoding="utf-8"
        )
    )
    geo_names = {
        f["properties"]["name"]
        for f in geojson.get("features", [])
        if "name" in f.get("properties", {})
    }
    program_stages = set(_PROGRAM["stage_program"].keys())
    missing = program_stages - geo_names
    assert not missing, f"daytime program stages not in geojson (INT-001 spoofing risk): {missing}"


def test_night_signature_frozen():
    """The FROZEN night demand signature is untouched (the daytime model is ADDITIVE, never a rewrite).

    ``crowd.demand.goal_weights_for_slice`` must keep its exact ``(stage_names, capacity_classes, *,
    day, hour_block, table=None)`` signature — the daytime helper lives in a NEW module and never
    edits the night path (T-16-NG).
    """
    from crowd.demand import goal_weights_for_slice

    sig = inspect.signature(goal_weights_for_slice)
    params = list(sig.parameters.values())
    names = [p.name for p in params]
    assert names == ["stage_names", "capacity_classes", "day", "hour_block", "table"]
    kinds = {p.name: p.kind for p in params}
    assert kinds["day"] == inspect.Parameter.KEYWORD_ONLY
    assert kinds["hour_block"] == inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["table"].default is None
