"""DAYCROWD-01/05 — pure additive DAYTIME demand model (BASE tier, no engine).

The continuous daytime sim (Plan 03) is driven by a per-``(hour, stage)`` demand weight — the
DAYTIME analogue of the night ``crowd.demand.goal_weights_for_slice`` output. This module is a
sibling of ``demand.py`` and **does not touch it**: the night path keeps its exact frozen
signature; this is purely ADDITIVE.

Formula (CON-003, the committed CD-A data-prep decision)::

    demand[hour, stage] = capacity_floor(stage) × draw(stage) × active(stage, hour) × occupancy(hour)

* ``capacity_floor`` = ``GOAL_WEIGHT_BY_CLASS.get(cls, GOAL_WEIGHT_DEFAULT)`` — REUSED verbatim from
  the night model (the same capacity-class floors), so a "main" stage out-pulls a club stage.
* ``draw`` = the organiser's OPTIONAL 1-5 ordinal pull; defaults to ``1.0`` when omitted (it
  REFINES demand, it never gates — mirror of demand.py's popularity-weight discipline, T-16-07).
* ``active`` = ``1.0`` while the stage is inside its ``active_hours`` else ``ACTIVE_BASELINE`` (the
  NAMED low-but-nonzero people-mill pull from ``crowd.constants`` — never an inline 0.1, T-16-06).
  This is what makes the crowd MIGRATE across the site as the live stage moves through the day.
* ``occupancy`` = the site-wide fraction-of-peak for the chosen arrival profile, from the committed
  ``occupancy_curve_2026.json`` (the organiser "festival style" knob).

PROVENANCE TIER — **DERIVED-from-ASSUMED**: the occupancy curve is DERIVED (TUM S-shape + Still
profiles, fill/plateau limbs) while the decline limb and the demo stage program are ASSUMED
(decisions.md FMT-001/FMT-002). Like the night model (T-02.1-04), these weights **REFINE** demand
and **never gate acceptance** — a wrong draw/baseline cannot make a PASS/FAIL gate falsely pass;
the only acceptance surface they feed this phase is the rank-stability assert (DAYCROWD-05), which
is itself a robustness check, not a threshold.

HARD INPUTS (no silent fallbacks):
* ``program`` is REQUIRED — no program → ``ValueError`` (NO assumed fallback rotation, DAYCROWD-01).
* INT-001: a program stage that is not in the site/stage set is a ``ValueError`` listing the
  mismatched name(s) — a ghost-crowd spoofing risk (T-16-05), never silently dropped.

PURITY CONTRACT — this module imports ONLY ``json`` + ``numpy`` + ``crowd.constants`` (mirror
``demand.py``). It pulls NONE of the heavy crowd/crowdsim ML stack and never calls the paid,
permission-gated UTCI service (T-16-04); the Plan-01 purity guard greps this file's text for the
forbidden tokens. ``PYTHONUTF8=1`` matters for ``read_text`` of the accented stage names (e.g.
"Auditori Rockdelux").
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from crowd.constants import (
    ACTIVE_BASELINE,
    DAYTIME_HOURS,
    GOAL_WEIGHT_BY_CLASS,
    GOAL_WEIGHT_DEFAULT,
)

#: Default committed data paths (repo-relative). PYTHONUTF8 matters for the accented stage names.
DEFAULT_OCCUPANCY_PATH = Path(__file__).resolve().parent / "data" / "occupancy_curve_2026.json"
DEFAULT_PROGRAM_PATH = Path(__file__).resolve().parent / "data" / "daytime_program_2026.json"


def load_occupancy_curve(path=None) -> dict:
    """Read the committed site-wide occupancy curve.

    Returns the parsed ``occupancy_curve_2026.json``: ``{"hours": [...], "profiles":
    {<profile>: {"occupancy": [12 floats]}}, "default_profile": "late", ...}``.
    """
    p = Path(path) if path is not None else DEFAULT_OCCUPANCY_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def load_daytime_program(path=None) -> dict:
    """Read the committed organiser stage program (REQUIRED input for a daytime run).

    Returns the parsed ``daytime_program_2026.json``: ``{"stage_program": {<stage>:
    {"active_hours": [...], "draw": int}}, ...}``.
    """
    p = Path(path) if path is not None else DEFAULT_PROGRAM_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def _stage_program(program: dict) -> dict:
    """Unwrap the ``stage_program`` block (tolerating either the wrapped or bare shape)."""
    if "stage_program" in program:
        return program["stage_program"]
    return program


def active_factor(stage: str, hour: str, *, program: dict) -> float:
    """The ``active()`` factor for one ``(stage, hour)``: ``1.0`` when live, else ``ACTIVE_BASELINE``.

    A stage inside its ``active_hours`` exerts full pull (1.0); outside it the pull drops to the
    NAMED ``ACTIVE_BASELINE`` (the low-but-nonzero people-mill pull, read from ``crowd.constants``
    — never an inline 0.1, T-16-06). A stage absent from the program has no ``active_hours`` and so
    is always at ``ACTIVE_BASELINE``.

    Args:
        stage: stage name.
        hour: local ``HH:MM`` (one of ``DAYTIME_HOURS``).
        program: the organiser stage program (REQUIRED; ``None`` raises).

    Returns:
        ``1.0`` if ``hour`` is in ``stage``'s ``active_hours`` else ``ACTIVE_BASELINE``.
    """
    if program is None:
        raise ValueError(
            "daytime program is a required organiser input — no program, no run "
            "(no assumed fallback rotation)"
        )
    sp = _stage_program(program)
    active_hours = sp.get(stage, {}).get("active_hours", [])
    return 1.0 if hour in active_hours else ACTIVE_BASELINE


def _validate_int_001(program_stages, stage_names) -> None:
    """INT-001: every program stage must be in the site/stage set — else a hard error (T-16-05).

    A program stage not matching the committed site stages would silently model a ghost crowd; we
    raise listing the mismatched name(s) rather than drop them.
    """
    if stage_names is None:
        return
    site = set(stage_names)
    missing = [s for s in program_stages if s not in site]
    if missing:
        raise ValueError(
            f"daytime program stage(s) not in the site/stage set (INT-001 spoofing risk): "
            f"{sorted(missing)}"
        )


def daytime_demand_table(
    *,
    program: dict,
    occupancy: dict | None = None,
    profile: str | None = None,
    stage_names=None,
) -> dict[tuple[str, str], float]:
    """Per-``(hour, stage)`` daytime demand table over the committed data (the CON-003 formula).

    For each daytime hour ``h`` and each program stage ``s``::

        demand[(h, s)] = GOAL_WEIGHT_BY_CLASS.get(cls, GOAL_WEIGHT_DEFAULT)
                         × draw(s)                # 1.0 when omitted (REFINES, never gates)
                         × active_factor(s, h)    # 1.0 live else ACTIVE_BASELINE
                         × occupancy[profile][h]

    Capacity class: the demo program does not carry an explicit class, so the floor defaults to the
    "main" weight for any stage with an explicit ``draw`` and ``GOAL_WEIGHT_DEFAULT`` otherwise. The
    one hand-computed acceptance cell (Occident @15:00, class "main") is reproduced exactly.

    Args:
        program: organiser stage program (REQUIRED; ``None`` → ``ValueError``, no fallback rotation).
        occupancy: pre-loaded occupancy curve (else the committed default is loaded).
        profile: arrival profile key; defaults to ``occupancy["default_profile"]`` ("late").
        stage_names: optional site/stage set for the INT-001 hard-error check.

    Returns:
        ``dict`` keyed ``(hour, stage)`` → ``float`` demand weight.
    """
    if program is None:
        raise ValueError(
            "daytime program is a required organiser input — no program, no run "
            "(no assumed fallback rotation)"
        )
    occ_curve = occupancy if occupancy is not None else load_occupancy_curve()
    sp = _stage_program(program)

    _validate_int_001(sp.keys(), stage_names)

    prof = profile if profile is not None else occ_curve["default_profile"]
    occ = occ_curve["profiles"][prof]["occupancy"]

    table: dict[tuple[str, str], float] = {}
    for h in DAYTIME_HOURS:
        occ_h = occ[DAYTIME_HOURS.index(h)]
        for stage, spec in sp.items():
            cls = spec.get("capacity_class", "main")
            floor = GOAL_WEIGHT_BY_CLASS.get(cls, GOAL_WEIGHT_DEFAULT)
            draw = spec.get("draw", 1.0)
            act = active_factor(stage, h, program=program)
            table[(h, stage)] = float(floor) * float(draw) * float(act) * float(occ_h)
    return table


def daytime_goal_weights(
    stage_names,
    capacity_classes,
    hour: str,
    *,
    program: dict,
    occupancy: dict | None = None,
    profile: str | None = None,
) -> np.ndarray:
    """Per-stage daytime demand vector for ONE hour — the daytime analogue of ``goal_weights_for_slice``.

    Same column order as ``stage_names``. This is the slot Plan 03's ``build_primitive_spec`` reads
    per boundary, mirroring how the night sim consumes ``goal_weights_for_slice``. A stage in
    ``stage_names`` that is not in the program contributes ``floor × draw=1.0 × active=ACTIVE_BASELINE
    × occupancy`` (it has no ``active_hours``).

    Args:
        stage_names: iterable of site stage names (column order).
        capacity_classes: iterable of capacity classes aligned with ``stage_names``.
        hour: the ``HH:MM`` slice.
        program: organiser stage program (REQUIRED).
        occupancy: pre-loaded curve (else default loaded).
        profile: arrival profile (else ``default_profile``).

    Returns:
        ``float64`` ``np.ndarray`` of per-stage daytime demand for ``hour``.
    """
    if program is None:
        raise ValueError(
            "daytime program is a required organiser input — no program, no run "
            "(no assumed fallback rotation)"
        )
    occ_curve = occupancy if occupancy is not None else load_occupancy_curve()
    prof = profile if profile is not None else occ_curve["default_profile"]
    occ_h = occ_curve["profiles"][prof]["occupancy"][DAYTIME_HOURS.index(hour)]
    sp = _stage_program(program)

    _validate_int_001(sp.keys(), stage_names)

    weights = []
    for name, cls in zip(stage_names, capacity_classes):
        floor = GOAL_WEIGHT_BY_CLASS.get(cls, GOAL_WEIGHT_DEFAULT)
        draw = sp.get(name, {}).get("draw", 1.0)
        act = active_factor(name, hour, program=program)
        weights.append(float(floor) * float(draw) * float(act) * float(occ_h))
    return np.asarray(weights, dtype=np.float64)


def per_hour_total_demand(
    *,
    program: dict,
    occupancy: dict | None = None,
    profile: str | None = None,
    stage_names=None,
) -> list[float]:
    """Total demand summed over all stages, one value per hour (column order = ``DAYTIME_HOURS``).

    This is the per-hour total the worst-hour / rank-stability reduction (DAYCROWD-05) and the
    Plan-03 migration delta are computed from. A pure reduction over :func:`daytime_demand_table`.

    Returns:
        ``list[float]`` of length ``len(DAYTIME_HOURS)``.
    """
    table = daytime_demand_table(
        program=program, occupancy=occupancy, profile=profile, stage_names=stage_names
    )
    totals = []
    for h in DAYTIME_HOURS:
        totals.append(float(sum(v for (hour, _stage), v in table.items() if hour == h)))
    return totals


def worst_hour(
    *,
    program: dict,
    occupancy: dict | None = None,
    profile: str | None = None,
    stage_names=None,
) -> str:
    """The busiest daytime HOUR (max total demand over stages) for a given profile (DAYCROWD-05).

    Returns ``DAYTIME_HOURS[argmax]`` of :func:`per_hour_total_demand`. A pure reduction over the
    Task-1 table — no new data. The CD-A expectation (decisions.md Sensitivity note) is that this
    sits in the afternoon fill/plateau and is rank-stable to ±1h / ±0.1-occupancy / profile swaps.

    Returns:
        The ``HH:MM`` of the busiest hour.
    """
    totals = per_hour_total_demand(
        program=program, occupancy=occupancy, profile=profile, stage_names=stage_names
    )
    idx = max(range(len(totals)), key=lambda i: totals[i])
    return DAYTIME_HOURS[idx]
