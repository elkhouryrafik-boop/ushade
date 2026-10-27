"""The ONE place every Phase-5b ASSUMED / named constant lives (mirrors ``geom.constants``).

Every downstream Phase-5b module (``coverage.py``, ``delta.py``, ``thresholds.py``,
``comfort_gap.py``, ``acceptance.py``) and every gate test imports its constants from
here — the numbers are NEVER inlined. The gate is the project's honesty keystone, so the
discipline here is strict: each constant is named once and labelled by its true tier.

CRITICAL — NO X/Y THRESHOLD LITERAL HERE (anti-pattern, threat T-05b-01). The acceptance
thresholds X = 4 °C and Y = 70 % live ONLY in ``acceptance/thresholds.json`` (frozen,
content-hashed) and the runtime loader (Plan 02). A second ``4`` / ``70`` copy in
``src/acceptance/`` would be a drift vector that the threshold drift-guard could not catch
(it guards the frozen file, not a stray constant). The drift-guard grep in the plan's
acceptance criteria enforces the absence of such a literal here.

This module imports nothing heavy (pure floats/strings/tuples) so it loads with NO geom/
crowd extra installed — base tier (mirror of ``geom.constants`` loading rhino3dm-free).

Provenance tiers are tagged inline (same discipline as ``geom.constants`` /
``core.constants``):

* ``[ASSUMED]`` — Claude's-discretion / no-grounded-source defaults; immutable after an
  accepted run (acceptance-integrity discipline, mirrors the Phase-0 X/Y lock).
* ``[CITED: ...]`` — verbatim venue/site numbers sourced from ``geom.constants`` /
  ``baseline_spec.md``.
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# Ideal (tau=0, full-shade) geometric cooling  [ASSUMED]  — Q3 decision (locked)
# ─────────────────────────────────────────────────────────────────────────────

#: The tau=0 full-shade geometric peak-hour UTCI reduction a cell gets from being FULLY
#: shaded by an opaque canopy (°C). [ASSUMED] — Q3 (locked).
#:
#: ASSUMED-grade, NOT grounded: the codebase persists NO grounded shaded-sim field. The
#: demo ``utci_grid.json`` has ``utci_c == baseline_utci_c`` (no shaded field was ever
#: injected), so there is nothing grounded to read back as a shaded UTCI. The faithful,
#: deterministic, offline method (CONTEXT D-03 + ``acceptance/baseline_spec.md``) is the
#: analytical ``(1 - tau)`` application over the persisted byte-stable baseline, fed THIS
#: assumed geometric-cooling magnitude.
#:
#: This value is the ``geometric_cooling`` argument threaded into
#: ``selection.cooling.cooling_estimate(geometric_cooling, tau)`` — tau enters via
#: ``cooling_correction_factor`` ONLY (never a second ``(1 - tau)`` site in the gate).
#: The resulting ΔUTCI is DERIVED — an arithmetic of an ASSUMED input (this constant) ×
#: a GROUNDED baseline — and MUST NEVER be labelled GROUNDED (threat T-05b-03). Flip this
#: constant to a GROUNDED source ONLY when a real shaded sim lands.
#:
#: Value rationale: 8.0 °C is a conservative peak-hour opaque-canopy shade benefit. It is
#: DECLARED here, not back-fitted in the orchestrator to make the demo pass. Direction
#: check (proving the wiring is exercised, NOT tuned): with the demo membrane tau = 0.4 →
#: ``cooling_correction_factor(0.4) = 0.6`` → ``actual_delta = 8.0 · 0.6 = 4.8`` °C, which
#: clears X = 4 °C — so the demo CAN pass the delta criterion through the real (1 - tau)
#: path, not through a tuned threshold.
IDEAL_DELTA_C_ASSUMED: float = 8.0

# ─────────────────────────────────────────────────────────────────────────────
# Baseline-conditions sidecar labels  [ASSUMED / CITED]  — D-05
# ─────────────────────────────────────────────────────────────────────────────

#: The peak-heat band the baseline conditions are stated over, for the D-05 sidecar
#: (``acceptance_meta.json``). [ASSUMED] mirrors ``geom.PEAK_SUN_HOUR = 14`` (the midpoint
#: of the climate ``PEAK_HEAT_HOUR_BAND = (12, 16)``) so the gate's baseline band matches
#: the heat grid + geometry solar assumption. Named here so it is never inlined.
PEAK_BAND_LABEL: str = "12-16 local (midpoint 14)"

#: The ``acceptance_meta.json`` sidecar schema marker. [ASSUMED] cloned from
#: ``geom._SIDECAR_VERSION`` so the non-contract sidecar is recognisable as PREVIEW/ASSUMED-
#: grade and never mistaken for a frozen contract artifact.
SIDECAR_VERSION: str = "1.0.0-sidecar"

#: Site name for the baseline-conditions-inline sidecar (D-05) so the number is falsifiable
#: on its face. [CITED: geom.constants / baseline_spec.md — Parc del Fòrum, Barcelona].
SITE_NAME: str = "Parc del Fòrum, Barcelona"

#: Site centroid (lat, lon, WGS84) for the baseline-conditions sidecar. [CITED]
#: Mirrors ``geom.constants.PARC_DEL_FORUM_LATLON`` — that module is the source of truth;
#: the literal is repeated here only so this base-tier constants module needs no geom
#: import. If geom.constants ever moves the venue, update both (the comment is the link).
SITE_LATLON: tuple[float, float] = (41.4106, 2.2270)
