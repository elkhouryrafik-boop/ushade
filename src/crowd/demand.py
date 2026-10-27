"""Set-times demand model — committed schedule table → per-stage goal-weight vector.

The owner wanted a "really good" model, and RESEARCH §Q5 confirmed the 2026 set times ARE
published + scrapeable (official lineup + Clashfinder ``ps26``), so the demand model is IN
SCOPE. This module turns the committed, hand-transcribed, sourced-and-dated
``src/crowd/data/set_times_2026.json`` into a deterministic per-stage goal weight: the demo's
capacity-class FLOOR (``GOAL_WEIGHT_BY_CLASS``) MULTIPLIED by the active headliner's ORDINAL
popularity (1.0 when no headliner is on that stage in that schedule slice). A stage with The xx
or Olivia Rodrigo pulls more agents than a club stage with an unknown DJ at the same hour.

PROVENANCE (honesty): the JSON is data, NOT a live scrape on the pipeline path
(CLAUDE.md — no live deps in the deterministic core; threat T-02.1-05). Its ``_meta`` block
carries the source URLs, the transcription date (2026-06-10) and the ``ASSUMED`` tier. The
ordinal popularity weights REFINE demand and do NOT gate acceptance (threat T-02.1-04) — a wrong
weight cannot make the stage-reach gate falsely pass.

REPRESENTATIVE SLICE (RESEARCH §Q5/A8): the deterministic rollout is a single snapshot, so the
demand profile is ONE schedule slice. The committed default is **Saturday, hour_block "22:00"**
(``_meta.default_slice``) — the busiest co-active headliner block (My Bloody Valentine on Estrella
Damm + Olivia Rodrigo on Occident, rolling into The xx and Gorillaz), the profile that most
stresses the shade decision. Multi-hour temporal demand is deferred (out of scope per CONTEXT).

PURITY CONTRACT — this module is PURE: ``json`` + ``numpy`` + the project ``constants``. It
imports NONE of the heavy crowd-extra ML stack; a static guard in ``tests/test_demand.py`` greps
this file's text for the forbidden tokens (kept in the TEST, not here). ``PYTHONUTF8=1`` matters
for the ``read_text`` of the table (accented headliner / stage names).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from crowd.constants import GOAL_WEIGHT_BY_CLASS, GOAL_WEIGHT_DEFAULT

#: Default committed table path (repo-relative).
DEFAULT_SET_TIMES_PATH = Path(__file__).resolve().parent / "data" / "set_times_2026.json"


def load_set_times(path=None) -> dict:
    """Read the committed set-times table.

    Args:
        path: optional override (str/Path) for the JSON file; default is the committed
            ``src/crowd/data/set_times_2026.json``.

    Returns:
        The parsed table: ``{"_meta": {...}, "rows": [{day, hour_block, stage_name, headliner,
        popularity_weight}, ...]}``. ``PYTHONUTF8=1`` matters for the accented names.
    """
    p = Path(path) if path is not None else DEFAULT_SET_TIMES_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def _popularity_index(table: dict) -> dict[tuple[str, str, str], int]:
    """Build a ``(day, hour_block, stage_name) -> popularity_weight`` lookup from the table rows."""
    return {
        (r["day"], r["hour_block"], r["stage_name"]): int(r["popularity_weight"])
        for r in table["rows"]
    }


def goal_weights_for_slice(
    stage_names,
    capacity_classes,
    *,
    day: str,
    hour_block: str,
    table: dict | None = None,
) -> np.ndarray:
    """Per-stage demand goal weight for one schedule slice (capacity-class × headliner popularity).

    For each stage ``i``::

        weight[i] = GOAL_WEIGHT_BY_CLASS.get(class[i], GOAL_WEIGHT_DEFAULT)
                    × popularity(stage_name[i], day, hour_block)   # 1.0 if no headliner this slice

    The result is deterministic (no RNG) and pure. It feeds the env's weighted goal assignment
    (Plan 03) exactly as the demo's capacity-class-only weights did, but now time-weighted by real
    artist popularity for the documented representative slice.

    Args:
        stage_names: iterable of stage names (must match the geojson / table stage names).
        capacity_classes: iterable of capacity classes, aligned with ``stage_names``.
        day: schedule day key (e.g. ``"Sat"``).
        hour_block: schedule hour-block key (e.g. ``"22:00"``).
        table: optional pre-loaded table (else the committed default is loaded).

    Returns:
        A ``float64`` ``np.ndarray`` of per-stage demand weights, same order as ``stage_names``.
    """
    tbl = table if table is not None else load_set_times()
    pop_index = _popularity_index(tbl)

    weights = []
    for name, cls in zip(stage_names, capacity_classes):
        class_floor = GOAL_WEIGHT_BY_CLASS.get(cls, GOAL_WEIGHT_DEFAULT)
        popularity = pop_index.get((day, hour_block, name), 1.0)  # 1.0 when no headliner this slice
        weights.append(float(class_floor) * float(popularity))
    return np.asarray(weights, dtype=np.float64)
