# Decision Statement — Material Data Layer

> This data product (`data/materials.json`) will help a **festival/event organiser** (and the **architect** they hand the brief to) at a **festival-operations organisation** decide **which reclaimed Barcelona-local material to deploy as shade/structure at the hottest×busiest cells** **on-demand, once per event site** by **ranking candidate materials on cooling delivered (1 − solar_transmissivity), transport carbon (mass × distance × mode factor), and cost — every input number sourced and provenance-labelled.**

## Context

- HeatGuard/U-Shade crosses a real UTCI heat grid × a crowd-density field, places shade deterministically on hottest×busiest cells, then selects the lowest-transport-carbon **available** material to clad it (PRD §1 Golden Rule, amended 2026-06-09: cooling = geometry × (1 − solar_transmissivity); carbon = transport-only).
- The material layer is the input to that selection + the cooling/carbon/cost numbers the organiser sees and must defend upward (to a city, a sponsor, a safety officer).
- **Problem that triggered this phase:** the 6 atlas-sourced archetypes added 2026-06-22 carry **estimated** engineering specs (solar_transmissivity, unit_mass_kg, thickness_mm, max_span_meters, cost_per_unit). The streams/operators are atlas-GROUNDED; the specs are DECLARED guesses. A cooling/carbon/cost ranking built on invented specs is not defensible.
- **This phase's job:** replace estimated specs with real, datasheet/EPD-sourced numbers, each field provenance-labelled (GROUNDED = real datasheet/EPD/supplier; DECLARED = honest estimate where no source exists).
