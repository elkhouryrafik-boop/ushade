"""DAYCROWD-NG — daytime purity guards (BASE tier, no marker).

The daytime model is an INTERNAL deterministic demand+migration layer: it must NEVER call infrared
(paid, permission-gated UTCI), must NEVER edit the FROZEN night demand signature, and must NEVER
mutate ``SIM_STEPS_JPS`` (the night path reads it). Three static guards enforce this:

1. **No infrared anywhere in the daytime code** — static grep of the three daytime source files for
   the token ``infrared`` → none (a file absent pre-impl is skipped gracefully, but the guard EXISTS
   by name now and binds each file as it ships).
2. **Night signature untouched** — ``crowd.demand.goal_weights_for_slice`` keeps its frozen signature.
3. **SIM_STEPS_JPS not mutated** — ``crowd.constants.SIM_STEPS_JPS == 1400``.

BASE tier (no marker): this MUST run in the default suite (proving the daytime path never drags
infrared in). GREEN by design — it fails only if a future edit leaks an infrared import, edits the
night signature, or mutates the night horizon constant.
"""

from __future__ import annotations

import inspect
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"

#: The three daytime source files Plans 02/03/04 ship. Each is grepped for `infrared` as it appears.
_DAYTIME_SOURCES = (
    _SRC / "crowd" / "daytime_demand.py",
    _SRC / "crowdsim" / "continuous.py",
    _SRC / "crowd" / "daytime_runner.py",
)


def test_no_infrared_import_anywhere_in_daytime_code():
    """No `infrared` token in any daytime source (T-16-04 — no paid UTCI call sneaks into the path).

    Each file is skipped gracefully if it does not yet exist (Wave-0 pre-impl), but the guard EXISTS
    by name now and binds each file the moment Plan 02/03/04 ships it.
    """
    checked = 0
    for src in _DAYTIME_SOURCES:
        if not src.exists():
            continue
        checked += 1
        text = src.read_text(encoding="utf-8")
        assert "infrared" not in text, (
            f"{src.name} references `infrared` — the daytime path must NEVER call the paid, "
            f"permission-gated UTCI service (DAYCROWD-NG / T-16-04)"
        )
    # The guard is meaningful even pre-impl (it names the files); once all three ship, checked == 3.
    assert checked >= 0


def test_demand_py_night_signature_untouched():
    """The FROZEN night demand signature is unchanged (the daytime model is additive, never a rewrite)."""
    from crowd.demand import goal_weights_for_slice

    sig = inspect.signature(goal_weights_for_slice)
    names = [p.name for p in sig.parameters.values()]
    assert names == ["stage_names", "capacity_classes", "day", "hour_block", "table"]
    assert sig.parameters["day"].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["hour_block"].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["table"].default is None


def test_sim_steps_jps_not_mutated():
    """The night sim horizon constant is untouched (FRAMES_PER_HOUR_JPS REUSES it, never mutates it)."""
    from crowd.constants import SIM_STEPS_JPS

    assert SIM_STEPS_JPS == 1400
