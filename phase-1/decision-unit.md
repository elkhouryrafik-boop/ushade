# Decision Unit

The data product is a **material catalogue**, not a spatial map. The decision unit is the **material archetype** (one row per reclaimed material type that can serve as festival shade or structure).

| Axis | Unit | Justification |
|---|---|---|
| **Spatial** | 1 archetype = 1 supplier-town centroid → road distance to Parc del Fòrum (km, 1-decimal) | Transport carbon needs a real origin→site distance; town-centroid is the finest origin we can source without scraping an exact address. Site = Parc del Fòrum (41.4106, 2.2203), NOT the atlas's Plaça dels Àngels baseline. |
| **Temporal** | static (per-deployment refresh) | Material specs (mass, transmissivity, thickness) don't change hourly; carbon/cost refresh when a route or price is re-sourced. Catalogue is versioned, not time-series. |
| **Thematic** | per-archetype engineering specs: `solar_transmissivity` (0–1, dimensionless shade-pass fraction), `unit_mass_kg` (kg per metre/m²/unit), `thickness_mm`, `max_span_meters`, `cost_per_unit` (EUR), `transport_mode_factor` (kgCO₂e/tonne-km) | These five+ are exactly the inputs the cooling (1−transmissivity), carbon (mass×distance×factor), and cost rankings consume. No coarser unit works: the ranking is per-material. |

**Resolution rule (earn-the-data 2×):** each spec must be sourced at a granularity at least as fine as one archetype — i.e. a datasheet/EPD for *that material class*, not a category average across "plastics" or "metals."
