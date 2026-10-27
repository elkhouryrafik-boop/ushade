"""The ONE place every Phase-3 PRD/ASSUMED magic number lives (mirrors ``crowd.constants``).

Every downstream Phase-3 module (``score.py``, ``footprint.py``, ``core.py``) and every
Phase-3 test imports its constants from here — the numbers are NEVER inlined. Phase 3 is a
deterministic, budget-constrained GREEDY allocation stage: it sorts cells by priority and
marks them until the budget runs out. It makes no best-solution claim (CORE-05, Pitfall 10)
— there is no max-coverage / submodular machinery and no such vocabulary in this file.

This module imports nothing heavy (pure floats) so it loads with NO crowd/torch extra
installed — Phase 3 is a base-tier (torch-free) stage.

Two provenance tiers are tagged inline (same discipline as ``crowd.constants``):

* ``[CITED: ...]`` — verbatim PRD numbers. Immutable; never tune to pass a test.
* ``[ASSUMED ...]`` — Claude's-discretion defaults (CONTEXT.md §Claude's Discretion).
  Documented here; adjustable BEFORE any accepted run, immutable after (acceptance-integrity
  discipline — mirrors the Phase-0 X/Y lock).
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# PRD-EXACT constant  [CITED]
# ─────────────────────────────────────────────────────────────────────────────

#: UTCI comfort threshold (°C): heat excess is ``max(utci_c - COMFORT_THRESHOLD_C, 0)``, so a
#: cell at or below this contributes ZERO to its score (CORE-06 — a sub-threshold cell is never
#: funded). [CITED: PRD §Phase 3 / CLIMATE-02 drop threshold — 26 °C]. This MUST equal
#: ``crowd.constants.HEAT_THRESHOLD_C`` — it is the SAME PRD constant; do not let them drift.
COMFORT_THRESHOLD_C: float = 26.0

# ─────────────────────────────────────────────────────────────────────────────
# ASSUMED constants  [ASSUMED]  (Claude's discretion — documented, tunable pre-run)
# ─────────────────────────────────────────────────────────────────────────────

#: Flat per-m² placeholder cost (€/m²). [ASSUMED A2] reconciled against the SELECTED membrane's
#: real €/unit in Phase 5; creates ZERO dependency on Phase 5 output. Do NOT read materials.json
#: here (that would couple Phase 3 to material logic prematurely). Per-cell cost is the product
#: ``ASSUMED_COST_PER_M2 * CELL_AREA_M2``.
ASSUMED_COST_PER_M2: float = 25.0

#: Cell area (m²) = cell_size_m². [ASSUMED A2] derived from the 6 m master-lattice cell
#: (6 m × 6 m = 36 m²). Per-cell shade cost = ``ASSUMED_COST_PER_M2 × CELL_AREA_M2``.
CELL_AREA_M2: float = 36.0

#: Polygon simplification tolerance (m) for the footprint union. [ASSUMED A6] named here so it is
#: never an inline literal; ``0.0`` = no simplification (emit the exact cell-union exterior rings).
SIMPLIFY_TOL: float = 0.0

# ─────────────────────────────────────────────────────────────────────────────
# MCLP placer constants  [ASSUMED]  (the post-pivot multi-scenario placer)
# ─────────────────────────────────────────────────────────────────────────────

#: Literature crowd-density magnitude anchor (dimensionless). [ASSUMED] The crowd sim (JuPedSim)
#: gives the spatial DISTRIBUTION of demand; its absolute magnitude is NOT validated by any
#: microsim (standing crush density is unvalidated everywhere). This scalar anchors the demand
#: magnitude to crowd-science literature (Fruin Level-of-Service; G.K. Still) WITHOUT changing the
#: placement RANKING — the greedy/ILP selection is invariant to a positive global scale, so this
#: only rescales the reported absolute demand number. Identity (1.0) until calibrated against
#: Fruin/Still; documented + tunable pre-run, immutable after (acceptance-integrity, mirrors the
#: Phase-0 X/Y lock). Demand per cell = crowd_density · LITERATURE_DENSITY_MAGNITUDE · max(utci−26,0).
LITERATURE_DENSITY_MAGNITUDE: float = 1.0

# ─────────────────────────────────────────────────────────────────────────────
# Persisted placement-stage constants  [ASSUMED]  (Phase-12 run_placement_stage)
# ─────────────────────────────────────────────────────────────────────────────

#: Primary stopping cap: number of structures the placer recommends. [ASSUMED A3] — "I can build N
#: canopies." K cannot live in the FROZEN parsed_brief (4-field, additionalProperties:false), so it
#: defaults here as a stage param. Tunable pre-run, immutable after an accepted run (acceptance-
#: integrity, mirrors the Phase-0 X/Y lock). NEVER inline this literal.
ASSUMED_K_DEFAULT: int = 5

#: Flat €/structure placeholder for the budget SECONDARY cap. [ASSUMED A3] reconciled against the
#: selected membrane's real €/unit in Phase 5 (like ASSUMED_COST_PER_M2 — zero Phase-5 dependency).
#: Do NOT reuse ASSUMED_COST_PER_M2 * CELL_AREA_M2 — that is per-CELL, the wrong scale for a discrete
#: structure. Tunable pre-run, immutable after. NEVER inline this literal.
ASSUMED_COST_PER_STRUCTURE: float = 50_000.0

#: Half-side (m) of the square canopy footprint the DEMO per-structure coverage model shades — a
#: 24×24 m canopy. [ASSUMED A4 / PLACE-04] This is the per-candidate primitive for "what does ONE
#: structure shade": gh_meta carries only a WHOLE-SITE projection (no per-candidate canopy), so the
#: demo path builds OffsetShadowCoverage(square_canopy_ring(ASSUMED_CANOPY_HALF_SPAN_M), sun_offset).
#: Documented, tunable pre-run, immutable post-run. NEVER inline this literal.
ASSUMED_CANOPY_HALF_SPAN_M: float = 12.0

#: Canopy height (m) used ONLY to project a real per-cell ``sun_vector`` into a shadow offset
#: (``shadow_offset_from_sun``). [ASSUMED A4] The demo data carries NO sun_vector, so this branch is
#: dormant on the demo path (offset defaults to high-noon (0,0)); it exists so a future real-sun run
#: never inlines a height literal. Documented, tunable pre-run, immutable post-run.
ASSUMED_CANOPY_HEIGHT_M: float = 4.0

#: Radius (m) for the RadiusCoverage FALLBACK when gh_meta is absent. [ASSUMED A4] — typical festival
#: canopy effective shade radius (~6-12 m). NOTE: with the ASSUMED canopy as the per-candidate
#: primary, the demo no longer depends on gh_meta — the radius fallback is an edge-case alternate,
#: not the gh_meta-absent branch. Keep test literals (RadiusCoverage(6.0)) independent of this
#: production default. NEVER inline this literal.
ASSUMED_RADIUS_M: float = 8.0

# ─────────────────────────────────────────────────────────────────────────────
# Exact ILP-MCLP constants  [ASSUMED]  (Phase-13 src/placement_ilp exact solver)
# ─────────────────────────────────────────────────────────────────────────────

#: Hard scale guard for the exact ILP solve — the MAX constraint-matrix cells (n_demand × n_cand)
#: an exact MILP is allowed before it RAISES. [ASSUMED] Sized on the BINDING dimension (demand
#: cells × candidates), NOT raw candidate count (Forum 21,267x205 ~ 4.4M solves in 38 ms; 4x
#: stress 68M in 91 ms — this gives comfortable headroom over the 4x stress). On exceed the ILP
#: RAISES a clear site-agnostic "too large for exact solve, raise the ceiling or coarsen
#: step_cells" message — NEVER silently subsamples or degrades to greedy (D-13/D-15). Reads
#: rows/cols from the utci_grid artifact (never a Forum literal). Tunable pre-run, immutable
#: after an accepted run. NEVER inline this literal.
ILP_MAX_CONSTRAINT_CELLS: int = 50_000_000

#: Integer demand-weight scale S for the exact ILP objective. [ASSUMED] The tiebreak proof needs
#: integer weights (min coverage gap == 1). Demand weight per cell = crowd_density ·
#: LITERATURE_DENSITY_MAGNITUDE · max(utci-26,0) in ~[0.01, 75]; S=1000 preserves differences down
#: to ~0.001 weight as >=1 integer unit. The integerization is solver-INTERNAL only — the reported
#: covered_demand / cross-check compare on the REAL float weights (Pitfall 2). Tunable pre-run,
#: immutable after. NEVER inline this literal.
ILP_DEMAND_WEIGHT_SCALE: int = 1000

# ─────────────────────────────────────────────────────────────────────────────
# Multi-scenario robustness constants  [ASSUMED]  (Phase-14 src/placement_ilp/robust)
# ─────────────────────────────────────────────────────────────────────────────
#
# The snapshot-family definition lives HERE — the ONE place (D-01/D-07). robust.py NEVER
# inlines these literals; the structured family identity is recorded in the run sidecar
# (never silent). The robustness label is over covered DEMAND, not cooling/°C delivered.

#: Sun-position axis of the structured snapshot family. [ASSUMED D-01] Three plausible
#: sun positions that vary the offset-shadow geometry (OffsetShadowCoverage offset).
#: Names are descriptive labels, not timestamps — the real schedule slices arrive with
#: JuPedSim (Phase 15). Tunable pre-run, immutable after an accepted run (acceptance-
#: integrity, mirrors the Phase-0 X/Y lock). NEVER inline this literal.
ROBUST_SNAPSHOT_SUN_SLICES: tuple[str, ...] = ("morning", "mid-afternoon", "late-afternoon")

#: Crowd-time-slice axis of the structured snapshot family. [ASSUMED D-01] Three plausible
#: crowd-time slices that vary the demand distribution. NOT ±20% symmetric noise (D-01 —
#: explicitly rejected): the family is structured around the KNOWN far-stage bias. Tunable
#: pre-run, immutable after an accepted run (acceptance-integrity). NEVER inline this literal.
ROBUST_SNAPSHOT_CROWD_SLICES: tuple[str, ...] = ("early", "peak", "headliner")

#: The snapshot count N actually solved this run over the single cached crowd_grid. [ASSUMED A1]
#: Phase 14 solves N=4: the as-cached world + 3 structured deterministic perturbations INCLUDING
#: the far-stage-corrected world (the load-bearing member). The full 3×3 sun×crowd cross-product
#: (len(SUN_SLICES)·len(CROWD_SLICES) == 9) is the Phase-15 ceiling, materialized once JuPedSim
#: supplies real schedule slices; Phase 14 deliberately runs N=4 over the existing single cached
#: grid (synthetic structured perturbation — the only deterministic way to get a far-stage-
#: corrected world before JuPedSim). Tunable pre-run, immutable after an accepted run. NEVER
#: inline this literal.
ROBUST_SNAPSHOT_FAMILY_SIZE: int = 4

#: Far-stage distance threshold (m). [ASSUMED D-01/A3] A cell whose centre lies BEYOND this
#: distance from the demand centroid is "far-stage" — the known 54.8% far-stage-reach failure
#: region. The far-stage-corrected snapshot boosts density on these cells (a structured
#: DIRECTIONAL correction, NEVER ±20% symmetric noise). Tunable pre-run, immutable after an
#: accepted run (acceptance-integrity, mirrors the Phase-0 X/Y lock). NEVER inline this literal.
ROBUST_FAR_STAGE_DISTANCE_THRESHOLD_M: float = 200.0

#: Multiplicative density boost applied to far-stage cells in the far-stage-corrected world.
#: [ASSUMED A3] MUST be large enough to flip >=1 placement label (the teeth-test proves it —
#: a family that never flips a label fails D-03). This is a structured DIRECTIONAL correction
#: toward the under-served far stages, NEVER ±20% symmetric noise (D-01). Tunable pre-run,
#: immutable after an accepted run (acceptance-integrity). NEVER inline this literal.
ROBUST_FAR_STAGE_DENSITY_BOOST: float = 4.0
