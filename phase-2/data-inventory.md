# Phase 2 — Data Inventory (sourced material specs)

Decision unit: one **material archetype**; specs sourced from real datasheets/EPDs (Phase-2 `earn-the-data`). Full per-field citations in `data/materials_provenance.json`. Tiers: GROUNDED (real datasheet/standard) / DERIVED (computed from grounded inputs) / DECLARED (honest estimate, no source).

| material | type | mass | thick(mm) | span(m) | tau | dist(km) | factor | key source |
|---|---|---|---|---|---|---|---|---|
| Scaffold Tube 48.3 mm | STRUCT | 3.56 | 3.2 | 2.5 | - | 22.9 | 0.09752 | uniasen.com/standards/en39-scaffolding-tub |
| Aluminium Event Truss (H30V) | STRUCT | 6.6 | 2.0 | 12.0 | - | 4.0 | 0.09752 | globaltruss.com F34 segments |
| Euro Pallet (EPAL) | STRUCT | 25.0 | 144.0 | 1.2 | - | 13.3 | 0.09752 | epal-pallets.org |
| Heras Fence Panel | STRUCT | 17.0 | 38.0 | 3.5 | - | 10.0 | 0.09752 | hermeq.com |
| Stadium Chair (Portable) | STRUCT | 7.5 | 22.0 | 0.5 | - | 11.5 | 0.09752 | networldsports.co.uk |
| PVC Billboard Vinyl | MEMBR | 0.45 | 0.36 | 3.0 | 0.01 | 14.8 | 0.09752 | innotechdigital.com |
| Industrial Shade Net (HDPE) | MEMBR | 0.34 | 0.8 | 6.0 | 0.4 | 29.5 | 0.09752 | galecommercial.com |
| Recycled PE Tarpaulin | MEMBR | 0.25 | 0.3 | 6.0 | 0.0 | 13.3 | 0.09752 | tarpaflex.co.uk |
| PE Yacht Shrink-Wrap | MEMBR | 0.169 | 0.178 | 4.0 | 0.15 | 14.8 | 0.09752 | Marine Products Direct |
| PP Festival Carpet | MEMBR | 0.74 | 3.5 | 4.0 | - | 12.3 | 0.09752 | alpha-tex.com |
| Reclaimed Steel I-Beam | STRUCT | 22.4 | 5.6 | 6.0 | - | 13.3 | 0.09752 | EN 10365 / eurocodeapplied.com |
| Shipping-Container Corten Panel | STRUCT | 15.0 | 1.6 | 1.5 | - | 14.8 | 0.09752 | themetalstore / makeitfrom S355J2W |
| Reclaimed Marine Sailcloth (Dacron) | MEMBR | 0.17 | 0.25 | 5.0 | 0.05 | 14.8 | 0.09752 | = 5.01 oz/yd² |
| Polypropylene Cargo / Agri Net | MEMBR | 0.055 | 0.7 | 6.0 | 0.45 | 27.6 | 0.09752 | shademesh.org spec table |
| Recycled HDPE Sheet | MEMBR | 3.8 | 4.0 | 3.0 | 0.0 | 13.3 | 0.09752 | S-Polytec PE-HD Regenerat, 100% recycled / |
| Recycled Technical Shade-Cloth | MEMBR | 0.41 | 1.2 | 8.0 | 0.25 | 29.5 | 0.09752 | virgin-equivalent; recycled-content DECLAR |

**Coverage:** 100 spec fields tiered - GROUNDED 41, DERIVED 28, DECLARED 31 -> 69% GROUNDED+DERIVED.

**DECLARED concentration:** cost_per_unit (16, reclaim-market opaque) + a few engineering spans (no published load tables). The cooling term (tau) and carbon term (mass x distance x factor) are grounded.

**Cancellation check:** 0 of 6 atlas-added archetypes ungroundable (criterion = >=3). Caveats: recycled-content of shade-cloth & PE-tarp is DECLARED (physical specs from virgin-equivalent); cost on reclaim/rental basis.
