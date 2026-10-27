# PRD Amendment — Material Recovery Inventory is an AVAILABILITY layer (D-11)

**Date:** 2026-06-15
**Phase:** 5 — Material Selection & Transport Carbon
**Decision:** D-11 (CONTEXT.md), folding in `.planning/INSTRUCTOR-FEEDBACK.md` §Phase 5
**Status:** ACCEPTED — records that the Material Recovery Inventory does NOT violate the
frozen-database non-negotiable (MAT-06).

---

## Summary (the one-line claim)

The Phase-5 **Material Recovery Inventory** is an **AVAILABILITY layer over the 10 frozen
`data/materials.json` material types** — it adds **NO new materials**, never mutates a frozen
field, and binds every live listing to one of the 10 frozen ids via a deterministic
classifier. **This is NOT a freeze violation.**

## Why this note exists

`FESTCOOL_PRD.md` §"PHASE 5: Material Selection & Carbon Accounting" and `CLAUDE.md`
§Non-negotiables hold the material database **frozen**: `data/materials.json` carries
**exactly 10 entries (5 structural + 5 membrane)**, Parc del Fòrum / Barcelona, with **no
add/remove without a PRD amendment**.

The 2026-06-11 instructor review (`.planning/INSTRUCTOR-FEEDBACK.md` §Phase 5) folded in a
**NEW SCOPE** — a real-data Material Recovery Inventory ("named, not conceived", NO mock
data). The instructor's own words capture the boundary verbatim:

> "τ values stay from frozen `materials.json` — the inventory is an AVAILABILITY layer over
> the 10 frozen material types, **not new materials** (requires small PRD amendment note,
> **not a freeze violation**)."

This document **is** that small amendment note.

## What the inventory does — and does NOT — do

The inventory layer **MAY**:

- Scrape live sources (Exoandamiajes scaffold; The Fabric Sales / FabricSight textile
  deadstock; etc.) and record real listings (`source_url`, `fetched_at`, qty, price).
- **Bind** each listing to one of the **10 frozen ids** via a *deterministic* classifier
  (keyword + dimension rules — never an LLM/"best guess"); ambiguous listings are
  **rejected with a reason**, never silently dropped and never assigned to a frozen type by
  guess.
- **Gate** material selection on availability (consult `/inventory/query` BEFORE choosing;
  unavailable min-carbon → next-lowest-carbon candidate → else an infeasibility report).
- Carry a DERIVED geocoded **road distance** (supplier → Parc del Fòrum) for transport
  carbon, labelled DERIVED.

The inventory layer **MUST NOT**:

- Add an 11th material, or remove any of the 10. **MAT-06 stays intact.**
- Mutate any frozen field — `solar_transmissivity` (τ), `theme`, `lca_profile.distance_km`,
  `unit_mass_kg`, `cost_per_unit` all stay read from the frozen `data/materials.json`. τ in
  particular is **never** sourced from a listing — it is always the frozen value (membrane
  suitability/UV/weight remain ASSUMED-until-datasheet, but τ is frozen-DB-authoritative).
- **Re-rank** the candidate set by price or availability. The sort key stays
  **transport-carbon only** (PRD §Phase 5 "select index 0"); availability only **filters**.

## Freeze invariant (the testable claim)

> `data/materials.json` carries exactly 10 entries (5 STRUCT + 5 MEMBR); the inventory layer
> binds listings to those 10 ids and never adds, removes, or mutates one.

This invariant is guarded by `tests/test_selection.py::test_materials_frozen_count`
(MAT-06) and by the deterministic classifier's reject-with-reason discipline
(`tests/test_inventory.py::test_classifier_rejects_ambiguous` /
`test_never_silent_drop_conservation`, D-09). Because the binding is rules-only, **"if the
LLM is removed, which decision changes? None"** — the inventory is reproducible and adds no
design authority.

## References

- `FESTCOOL_PRD.md` §"PHASE 5: Material Selection & Carbon Accounting" (the frozen-DB +
  soft-filter + "select index 0" clauses) and the 2026-06-09 Golden-Rule `(1 − τ)` amendment.
- `.planning/INSTRUCTOR-FEEDBACK.md` §"Phase 5 — Material Selection & Transport Carbon"
  (the "availability layer over the 10 frozen material types, not new materials … not a
  freeze violation" sentence this note records).
- `.planning/phases/05-material-selection-transport-carbon/05-CONTEXT.md` §D-08, §D-11.
- `CLAUDE.md` §Non-negotiables ("frozen materials.json … no add/remove without a PRD
  amendment").
