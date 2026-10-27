"""DAYCROWD-03/04 — the daytime DATA ARTIFACT orchestrator (timestamps + per-hour density).

This is the consumable end of Phase 16: a PURE orchestrator that turns the persistent migrating
continuous run (``crowdsim.continuous.run_continuous_daytime``, Plan 03) into the artifact the
frontend will later read — ONE moving timeline keyed to REAL festival wall-clock (09:00→20:00) with
an honest magnitude label. Three jobs:

1. **Per-hour density on the FROZEN 6 m lattice (DAYCROWD-03).** For each of the 11 daytime
   intervals, slice ``FRAMES_PER_HOUR_JPS`` recorded frames out of the continuous trajectory and run
   the FROZEN ``crowd.grid.build_crowd_grid`` on the SAME lattice object read from ``utci_grid.json``
   (XFN-04 byte-equality — the lattice is the AUTHORITY, passed UNCHANGED, never re-derived,
   CONTRACT-03). The worst (busiest) HOUR falls out of comparing the per-hour fields.

2. **Timestamped emit, no ``% maxT`` (DAYCROWD-03).** Emit the continuous trajectory via
   ``crowd.wgs84_export.emit_daytime_trajectories`` so the payload carries a ``timestamps`` sidecar
   (length == recorded frames, monotonic) — frame ``i``'s wall-clock is derivable PURELY from
   ``timestamps[i]``; the frontend rewrite that kills the modulo clock is a NON-GOAL of this phase,
   but this EMITS the artifact that makes the kill possible. ``test_daytime_emit`` asserts it.

3. **Honest magnitude tier (DAYCROWD-04).** MIRROR ``crowd.crowd._crowdsim_benchmark_is_green`` —
   read ``src/crowd/benchmark_result_crowdsim.json`` (the EXISTING Lyon MADRAS harness output,
   engine-fingerprint-bound): ``passed is True`` AND fingerprint matches the live engine → label the
   occupancy-plateau MAGNITUDE ``DERIVED``; else ``ASSUMED``. The crowd_density FIELD stays
   DERIVED-from-ASSUMED regardless — the spatial allocation at Parc del Fòrum is ASSUMED (the
   non-negotiable floor; never promoted by a green gate). Never hard-pass; record the tier honestly.

DETERMINISM (DAYCROWD-04 limb): two same-seed ``run_daytime`` calls produce a BYTE-IDENTICAL
per-hour density field. Determinism is asserted at the INTEGER ``snap_to_lattice`` field (the
``build_crowd_grid`` output), NOT raw CFSM positions — the integer snap quantises sub-cell ODE float
jitter away (Pitfall 4.3). The continuous run is seeded; the per-hour slice + FROZEN grid transform
are pure, so the field is reproducible.

NO NIGHT-CACHE REUSE (Pitfall 6, RESEARCH Open Q1 RESOLVED): this is a SIBLING explicit-run path —
it does NOT read or reuse ``run_crowd_stage``'s persisted night ``crowd_grid``/manifest, so a stale
night grid can NEVER be served under a daytime request. The run is explicit every time. (If a future
task DOES persist a daytime manifest, the input hash MUST fold the daytime program + profile + the
daytime horizon — Pitfall 6 — but the chosen path here is no-night-cache-reuse.)

LAZY-IMPORT QUARANTINE (mirror ``crowd.crowd`` / ``crowdsim.continuous``): ``crowdsim.continuous``
(which pulls jupedsim/shapely on its run path) is imported INSIDE ``run_daytime``, NEVER at module
top — ``import crowd.daytime_runner`` stays engine-free (the base-tier purity guard, DAYCROWD-NG).

PURITY (DAYCROWD-NG): the daytime path NEVER calls the paid, permission-gated UTCI service — a
static guard greps this file for that token and finds none. Named constants only
(``FRAMES_PER_HOUR_JPS`` / ``DAYTIME_HOURS`` / ``SEED`` from ``crowd.constants``) — never an inline
literal (anti-tuning, CLAUDE.md non-negotiable).
"""

from __future__ import annotations

import json
from pathlib import Path

from crowd.constants import DAYTIME_HOURS, FRAMES_PER_HOUR_JPS, SEED

#: The Lyon-validation artifact next to ``crowd.crowd`` (engine-fingerprint-bound). Read to decide
#: the occupancy-plateau MAGNITUDE tier — mirror of ``crowd.crowd._CROWDSIM_BENCHMARK_FILENAME``.
_CROWDSIM_BENCHMARK_FILENAME = "benchmark_result_crowdsim.json"

#: Honest tier labels for the emergent persons/m² magnitude (the occupancy plateau). The FIELD tier
#: (which cells are busy) stays ASSUMED regardless — only the MAGNITUDE can be promoted by a green
#: Lyon gate. Mirrors the source strings in ``crowd.crowd`` (kept short here — provenance discipline
#: lives in the ledger; this records the run-level verdict honestly in the returned artifact).
_MAGNITUDE_DERIVED = (
    "DERIVED — emergent persons/m² magnitude validated vs the REAL measured MADRAS Lyon festival "
    "density (benchmark_result_crowdsim.json, engine-fingerprint-bound, ±50% on mean/p90/p99, Fruin "
    "≤6 ped/m² ceiling). MAGNITUDE only; the spatial ALLOCATION at Parc del Fòrum stays ASSUMED."
)
_MAGNITUDE_ASSUMED = (
    "ASSUMED — the emergent persons/m² magnitude is not validated against this engine identity "
    "(benchmark_result_crowdsim.json absent, stale/fingerprint-mismatch, or red). Fruin/Still "
    "literature-anchored only; never hard-passed."
)


def _crowdsim_engine_fingerprint() -> str:
    """Engine IDENTITY string the Lyon validation must match — MIRROR of ``crowd.crowd``.

    Binds the magnitude promotion to the engine that was validated (jupedsim version + model +
    agent radius), NOT to the Lyon scenario. jupedsim is lazy-imported (version only) so reading the
    tier never drags the engine into the base tier; an absent wheel reads ``'unavailable'`` and can
    never spuriously match a recorded green fingerprint.
    """
    try:
        import jupedsim as jps  # noqa: PLC0415 — lazy, keeps base-tier import jupedsim-free

        ver = getattr(jps, "__version__", "unknown")
    except Exception:
        ver = "unavailable"
    from crowd.constants import AGENT_RADIUS_M

    return f"jupedsim={ver};model=CollisionFreeSpeedModel;radius={AGENT_RADIUS_M}"


def _magnitude_tier() -> tuple[str, str]:
    """Return ``("DERIVED"|"ASSUMED", source_string)`` for the occupancy-plateau magnitude.

    MIRROR of ``crowd.crowd._crowdsim_benchmark_is_green``: promote to DERIVED ONLY when
    ``benchmark_result_crowdsim.json`` exists, parses, ``passed is True`` AND its ``engine_fingerprint``
    matches the LIVE engine identity. A missing/edited artifact, a fingerprint mismatch (engine/radius
    drift), or ``passed != true`` keeps the magnitude ASSUMED — the non-negotiable floor, NEVER
    hard-passed. The FIELD tier stays DERIVED-from-ASSUMED independently of this.
    """
    path = Path(__file__).resolve().parent / _CROWDSIM_BENCHMARK_FILENAME
    if not path.exists():
        return "ASSUMED", _MAGNITUDE_ASSUMED
    try:
        res = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "ASSUMED", _MAGNITUDE_ASSUMED
    green = res.get("passed") is True and res.get("engine_fingerprint") == _crowdsim_engine_fingerprint()
    return ("DERIVED", _MAGNITUDE_DERIVED) if green else ("ASSUMED", _MAGNITUDE_ASSUMED)


def _hour_density_signature(crowd_grid: dict) -> float:
    """A scalar busyness signature for a per-hour density field (to rank the worst HOUR).

    Sums the per-cell ``crowd_density_agents_per_cell`` over the lattice — a deterministic, integer-
    snapped total (no float jitter; the snap quantises it). The hour with the largest signature is
    the busiest (the worst hour the shade placer would prioritise). Pure read, no mutation.
    """
    return float(sum(c["crowd_density_agents_per_cell"] for c in crowd_grid.get("cells", [])))


def run_daytime(
    project_id: str,
    *,
    projects_root=None,
    program: dict | None = None,
    occupancy: dict | None = None,
    profile: str | None = None,
    seed: int = SEED,
) -> dict:
    """Run the continuous migrating daytime sim → timestamped emit + per-hour density artifact.

    The DAYCROWD-03/04 orchestrator. SIBLING explicit-run path (no night-cache reuse, Pitfall 6):

    1. Read the lattice from ``<projects_root>/<project_id>/utci_grid.json`` (the AUTHORITY — passed
       UNCHANGED to ``build_crowd_grid``; CONTRACT-03 / XFN-04 byte-equality).
    2. Run ``crowdsim.continuous.run_continuous_daytime`` (Plan 03) → ONE ``(steps × agents × 4)``
       continuous migrating trajectory. ``steps == FRAMES_PER_HOUR_JPS × (len(DAYTIME_HOURS) - 1)``.
    3. Per-hour density: slice each ``FRAMES_PER_HOUR_JPS`` interval and run FROZEN
       ``build_crowd_grid`` on the SAME lattice object → one density field per daytime hour; the
       busiest HOUR falls out of comparing the per-hour signatures.
    4. Emit the trajectory via ``emit_daytime_trajectories`` (the ``timestamps`` sidecar — wall-clock
       from ``timestamps[i]``, no ``% maxT``) with the per-interval hour-boundary frames.
    5. Label the emergent persons/m² MAGNITUDE honestly (DERIVED on a green Lyon gate for this engine
       identity, else ASSUMED); the FIELD stays DERIVED-from-ASSUMED (spatial allocation ASSUMED).

    ``crowdsim.continuous`` is lazy-imported HERE (it pulls jupedsim/shapely on its run path) so
    ``import crowd.daytime_runner`` stays engine-free (DAYCROWD-NG base-tier purity).

    Args:
        project_id: project dir name under ``projects_root`` (carries ``parsed_brief.json`` +
            ``utci_grid.json`` — the conftest seeds it from the committed real-site inputs).
        projects_root: the projects root path (required for the explicit run).
        program: organiser daytime stage program (else the continuous run loads the committed one).
        occupancy: pre-loaded occupancy curve (else the committed default is loaded downstream).
        profile: arrival profile (else the curve's default).
        seed: continuous-run spawn seed (the migration selection is RNG-free).

    Returns:
        A dict with: ``timestamps`` (length == ``n_frames``, monotonic, 09:00→20:00),
        ``n_frames``, ``hour_boundaries``, ``lattice`` (the SAME object passed to every
        ``build_crowd_grid``), ``per_hour_density`` (one entry per daytime hour, each carrying that
        same ``lattice`` — XFN-04), ``worst_hour`` + ``worst_hour_index``, ``trajectory_emit`` (the
        WGS84 payload), and ``magnitude_tier`` / ``magnitude_source`` (the honest DERIVED/ASSUMED
        label) + ``field_tier`` (always DERIVED-from-ASSUMED).
    """
    if projects_root is None:
        raise ValueError("run_daytime requires projects_root (explicit sibling run; no night cache)")

    # LAZY — keeps `import crowd.daytime_runner` jupedsim/shapely-free (DAYCROWD-NG base-tier purity).
    from crowd.grid import build_crowd_grid
    from crowd.wgs84_export import emit_daytime_trajectories
    from crowdsim.continuous import run_continuous_daytime

    pdir = Path(projects_root) / project_id
    utci = json.loads((pdir / "utci_grid.json").read_text(encoding="utf-8"))
    lattice = utci["lattice"]  # AUTHORITY — passed UNCHANGED to build_crowd_grid (CONTRACT-03/XFN-04)

    # ── 1) ONE persistent migrating continuous run (Plan 03) — (steps × agents × 4) ──────────────
    traj = run_continuous_daytime(project_id, projects_root=projects_root, seed=seed)

    n_intervals = len(DAYTIME_HOURS) - 1

    # ── 2) Per-hour density on the FROZEN 6 m lattice (the SAME lattice object → XFN-04 identity) ─
    per_hour_density: list[dict] = []
    for h_idx in range(n_intervals):
        lo = h_idx * FRAMES_PER_HOUR_JPS
        hi = (h_idx + 1) * FRAMES_PER_HOUR_JPS
        hour_slice = traj[lo:hi]
        crowd_grid = build_crowd_grid(hour_slice, lattice)  # FROZEN — same lattice obj, integer snap
        per_hour_density.append(
            {
                "hour": DAYTIME_HOURS[h_idx],
                "hour_index": h_idx,
                "lattice": crowd_grid["lattice"],  # IS `lattice` (build_crowd_grid emits it verbatim)
                "cells": crowd_grid["cells"],
                "dwell_zones": crowd_grid["dwell_zones"],
                "flow_vectors": crowd_grid["flow_vectors"],
                "density_signature": _hour_density_signature(crowd_grid),
            }
        )

    # The busiest HOUR falls out of comparing the per-hour density signatures (the worst hour the
    # shade placer prioritises). Ties resolved by earliest hour (max picks the first on equal keys).
    worst = max(per_hour_density, key=lambda h: (h["density_signature"], -h["hour_index"]))
    worst_hour = worst["hour"]
    worst_hour_index = worst["hour_index"]

    # ── 3) Timestamped emit (wall-clock from timestamps[i], no % maxT) — hour boundaries per interval
    hour_boundary_frames = [h * FRAMES_PER_HOUR_JPS for h in range(len(DAYTIME_HOURS))]
    trajectory_emit = emit_daytime_trajectories(
        traj,
        label=f"daytime continuous migrating crowd — {project_id}",
        stride=_daytime_stride(traj.shape[0]),
        hour_boundary_frames=hour_boundary_frames,
        note="continuous migrating daytime crowd; persons/m² magnitude per magnitude_tier; "
        "stage/entrance positions INDICATIVE +/-30 m",
    )

    # ── 4) Honest magnitude tier (DAYCROWD-04) — DERIVED on a green Lyon gate, else ASSUMED ──────
    magnitude_tier, magnitude_source = _magnitude_tier()

    return {
        "project_id": project_id,
        "timestamps": trajectory_emit["timestamps"],
        "n_frames": trajectory_emit["n_steps_recorded"],
        "hour_boundaries": trajectory_emit["hour_boundaries"],
        "lattice": lattice,
        "per_hour_density": per_hour_density,
        "worst_hour": worst_hour,
        "worst_hour_index": worst_hour_index,
        "trajectory_emit": trajectory_emit,
        # Honesty (CLAUDE.md non-negotiable): the FIELD tier is ALWAYS DERIVED-from-ASSUMED (spatial
        # allocation at Parc del Fòrum is ASSUMED — never promoted by a green magnitude gate); only the
        # emergent persons/m² MAGNITUDE may be DERIVED (validated vs Lyon).
        "magnitude_tier": magnitude_tier,
        "magnitude_source": magnitude_source,
        "field_tier": "DERIVED-from-ASSUMED",
        "seed": seed,
    }


def _daytime_stride(n_steps: int) -> int:
    """The step-downsample stride for the daytime emit — 1 when the run is already short.

    The full continuous run is ``FRAMES_PER_HOUR_JPS × 11`` recorded frames; a smoke/test run can be
    short. The timestamps sidecar is correct for ANY stride (``daytime_timestamps`` accounts for it),
    so a stride of 1 is the honest default — no frames dropped, the wall-clock index stays exact. A
    later size-budget pass can raise this without changing the timestamps contract.
    """
    return 1 if n_steps > 0 else 1
