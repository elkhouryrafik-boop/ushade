# No-Shade Baseline Specification (CONTRACT-05)

**Status:** definition only. Phase 0 ships the *contract* for the baseline; **no UTCI is
computed here**. The baseline is produced for real in Phase 2a (Climate Layer) and consumed
by the Phase 5b Cooling Acceptance Gate. This document fixes the denominator of the cooling
delta *before* any climate code exists, so the "it cools" claim is falsifiable, not
negotiable (threat T-00-08 — an undefined denominator makes ΔUTCI unprovable).

## WHAT — the no-shade baseline is

The **no-shade baseline** is the **raw per-cell infrared UTCI** for the fixed site
(Parc del Fòrum, Barcelona — 41.4106°N, 2.2203°E), the brief's date, and the peak-hour
heat band, computed with **no intervention geometry** in the scene. It is the heat field
the crowd would experience if HeatGuard placed nothing. It is a direct infrared.city model
output — there is no surrogate, no analytical proxy, and no second derivation.

## WHERE — it lives

The baseline is persisted per cell as **`utci_grid.baseline_utci_c`** (celsius), defined in
`contracts/utci_grid.schema.json` (the MASTER spatial artifact, CONTRACT-03). It is written
**byte-stable** to `projects/<id>/utci_grid.json` once, on first computation, and **never
re-derived from a second API call**. Every downstream stage (the greedy core, the Phase 5b
gate) reads the same persisted `baseline_utci_c` so the denominator cannot drift between
when shade is placed and when cooling is judged. The companion gate artifact
`contracts/acceptance_verdict.schema.json` references it via `baseline_ref`.

## WHICH CELLS — the delta covers

The Phase 5b cooling delta is measured **only** over the intersection of:

1. the **shaded footprint** (cells under placed shade geometry), and
2. the **real projected-shadow cells** (cells the shade actually casts shadow onto at the
   peak-hour sun vector).

That is, `delta cells = shaded-footprint ∩ real-shadow`. The delta is **not** measured over
raw footprint area, because a structure's footprint and the ground it actually shades differ
once the sun is off-zenith (Pitfall 12 — **shadow** overlap, not footprint area). Coverage
(the Y = 70 % criterion) counts only cells in this shadow intersection that are also
hot×busy (UTCI ≥ 26 °C and human density > 0).

## τ SCALING — the membrane correction (amended Golden Rule)

Cooling benefit is scaled by membrane transmissivity. A membrane that transmits solar load
cools less than an opaque one. Per cell, in the shadow intersection:

```
actual_delta_c = (baseline_utci_c − shaded_utci_c) · (1 − solar_transmissivity)
```

equivalently `actual_delta = ideal_delta · (1 − τ)`, where `τ = solar_transmissivity`
(`tau`) is the selected membrane's value from the frozen `data/materials.json`. Structural
materials carry `τ = null` and can never be the membrane; only the selected MEMBRANE's τ
enters this correction. Carbon stays material/transport-only and is **not** coupled here —
only the cooling side is re-coupled (PRD 2026-06-09 amendment).

## PROVENANCE — honesty tiers

- **baseline** (`baseline_utci_c`) = **GROUNDED** — a direct infrared.city model output for
  the real site/date/hour with no intervention.
- **shaded re-simulation** (`shaded_utci_c`, the post-placement re-sim) = **DERIVED** — it is
  computed from the baseline scene plus injected geometry, then τ-corrected.

These tiers are recorded in the provenance ledger
(`contracts/provenance_ledger.schema.json`, GROUNDED/DERIVED/ASSUMED/INVENTED enum).

## IMMUTABILITY — the locked gate

The acceptance thresholds **X = 4 °C** (`x_utci_reduction_c`) and **Y = 70 %**
(`y_coverage_pct`) are locked in `acceptance/thresholds.json`, dated `2026-06-10`, marked
`immutable`, and content-hashed. They are **immutable** post-run: any edit after
`declared_on` desynchronizes the stored `content_sha256` and trips
`tests/test_thresholds_immutable.py` RED. The baseline definition above is the fixed
denominator those thresholds are evaluated against; neither the thresholds nor this baseline
definition may be tuned to make a given run pass (anti-gate-gaming, PRD §6).
