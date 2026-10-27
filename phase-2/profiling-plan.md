# Phase 2 — Profiling / Validation Plan

Run these before trusting the material layer in a deployment (most are encoded as tests in `tests/test_selection.py::test_specs_provenance_and_validity` + `test_materials_catalog_invariants`).

1. **Shape & types** — 16 materials, each with the full schema; `_meta.count/structural/membrane` match the array. *(test: catalog_invariants)*
2. **Provenance completeness** — every (material × field) has a ledger entry in `data/materials_provenance.json` with a tier ∈ {GROUNDED,DERIVED,DECLARED} and a non-empty source. *(test: specs_provenance)*
3. **Transmissivity validity** — every non-null `solar_transmissivity` ∈ [0,1]; structural-only = null; opaque membranes ≈ 0. *(test: specs_provenance)*
4. **Carbon factor** — `transport_mode_factor == 0.09752` (DEFRA 2024) for all 16; the 0.10 placeholder is gone. *(test: specs_provenance + carbon_assumed_labelled)*
5. **Distance sanity** — every `distance_km` is a plausible road km to Parc del Fòrum (2–30 km for BCN-metro origins); spot-check 3 against OSRM.
6. **Mass realism** — areal-mass materials (m²) in 0.05–4 kg/m²; linear (metre) 3–25 kg/m; per-unit (pallet/chair/fence) 7–25 kg. Flag outliers.
7. **Cooling-direction monotonicity** — lower τ ⇒ more cooling; recycled_pe(0.0) > pvc(0.01) > hdpe(0.40). *(test: test_smoke_seams seam2)*
8. **Classifier bridge** — every archetype id binds from a representative listing; apparel never binds. *(tests: test_atlas_archetypes_bind, test_apparel_shrink_does_not_bind_yacht_shrinkwrap)*

**Tier audit cadence:** re-run the DECLARED→GROUNDED upgrade when (a) a real reclaim-market price is sourced for any `cost_per_unit`, or (b) a recycled-content datasheet replaces the virgin-equivalent for shade-cloth / PE-tarp.
