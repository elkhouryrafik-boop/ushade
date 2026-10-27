# Glossary

| Term | Meaning |
|---|---|
| **solar_transmissivity** | Fraction 0–1 of solar radiation that PASSES THROUGH the membrane (= 1 − shade_factor). 0 = opaque, 1 = fully transparent. Drives the cooling correction (PRD §1 Golden Rule). For open nets it ≈ openness ratio. `null` for opaque structural-only materials. |
| **shade_factor / shade %** | Datasheet term = fraction BLOCKED. transmissivity = 1 − shade_factor. (Datasheets quote shade %, we store transmissivity — the conversion is a frequent error source.) |
| **areal density / areal mass** | Datasheet mass per unit area (g/m²). `unit_mass_kg` for an `m2` material = areal_density/1000; for a `metre` material (beam/tube) it's mass per linear metre. |
| **transport_mode_factor** | kgCO₂e per tonne-kilometre for the freight mode (road HGV). The 0.10 in the file is a PLACEHOLDER to be replaced by a cited DEFRA/EPD value. |
| **Transport carbon** | `2 × distance_km × mass_tonnes × transport_mode_factor` (round trip; manufacturing=0, recycled cut-off). Transport-only by project rule. |
| **GROUNDED / DERIVED / DECLARED** | Provenance tiers. GROUNDED = directly from a real datasheet/EPD/supplier/atlas. DERIVED = computed from grounded inputs (e.g. road route, areal-mass×thickness). DECLARED = honest estimate where no source exists, explicitly labelled. |
| **archetype** | One material *type* row in materials.json. Many scraped/onboarded listings bind to one archetype via the classifier. |
| **STRUCT / MEMBR** | Structural (frame/beam/tube) vs membrane (sheet/net/cloth) class. Coarse classifier split. |
| **site baseline** | Distances must be to **Parc del Fòrum** (41.4106, 2.2203), the deployment site — NOT the atlas's **Plaça dels Àngels** (41.3826, 2.1670) anchor (~6 km apart). |
| **reclaimed / recycled cut-off** | LCA boundary (ISO 14044 §4.3.4): a reclaimed material enters carbon-free of its first life; only transport to site counts. |
