# Product Card (draft) — `data/materials.json` material data layer

1. **What is this artifact?** A catalogue of reclaimed Barcelona-local materials usable as festival shade/structure, with per-material engineering specs (mass, thickness, span, shade transmissivity, cost) and a transport-carbon profile, each field provenance-labelled.

2. **Intended use:** Input to HeatGuard/U-Shade's deterministic material selection + the cooling/carbon/cost numbers shown to a festival organiser; ranks candidate materials for shade placement at hottest×busiest cells.

3. **Intended user:** A festival/event **organiser** (chooses + defends the shade plan) and the **architect** receiving the handoff brief.

4. **Out-of-scope uses (≥2):**
   - NOT a structural-engineering certification source — `max_span_meters` is an indicative planning figure, not a load calc; a real structure needs an engineer.
   - NOT a full cradle-to-grave LCA — carbon is **transport-only** (recycled cut-off, manufacturing=0); do not cite these numbers as total embodied carbon.
   - NOT an apparel/textile material guide.

5. **Known limitations (initial):** specs sourced from material-class datasheets (often virgin-product equivalents of the reclaimed item); some numbers DECLARED where no source exists (labelled); supplier origin is a town centroid, not an exact address; transmissivity from datasheet shade % (representative, deployment-dependent for knit nets).

6. **Provenance summary:** streams/operators GROUNDED to `barcelona_materials_atlas.md`; physical specs GROUNDED to manufacturer datasheets/EPDs or DERIVED; distances DERIVED (road route to Fòrum); carbon factor GROUNDED to DEFRA; gaps DECLARED + labelled. Full ledger filled in Phase 2/3.

7. **Versioning & contact:** `_meta.schema_version` + `_meta.specs_sourced_at`; maintained by the project author.
