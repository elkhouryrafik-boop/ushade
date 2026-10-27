# Success Criteria

## Business success

| Criterion | Numerical threshold | Deadline | Owner |
|---|---|---|---|
| Material ranking (cooling×carbon×cost) is defensible — every number traceable to a source or labelled DECLARED | 100% of spec fields carry a provenance tier | this milestone | owner (Rafik) |
| Organiser-facing material cards show no unsourced "fact" | 0 spec numbers presented without tier in UI/PDF | this milestone | owner |

## Data-product success

| Criterion | Numerical threshold | Verification method |
|---|---|---|
| **Spec coverage** | ≥ 90% of (material × {transmissivity, mass, thickness, cost, distance, mode_factor}) fields are GROUNDED or DERIVED (≤ 10% DECLARED) | count tiers in provenance ledger |
| **Transmissivity realism** | every `solar_transmissivity` within the physically-valid 0–1 band AND consistent with a cited shade-factor / openness datasheet | per-field source check |
| **Transport factor** | `transport_mode_factor` = a cited DEFRA/EPD road-freight value (not the 0.10 placeholder) for 100% of materials | metadata audit vs source |
| **Distance correctness** | every `distance_km` is supplier-town→**Parc del Fòrum** (not Plaça dels Àngels) | recompute road route, compare |
| **Reproducibility** | every sourced number reproducible from its cited URL/datasheet at audit | clean re-check of 3 random fields |
| **Classifier binding** | 100% of archetypes have a matching deterministic classifier rule | existing `test_materials_catalog_invariants` |

**Counterfactual test:** if a spec stays DECLARED, the organiser must see it flagged and the ranking must still be honest — a DECLARED transmissivity cannot silently win the cooling rank as if measured.
