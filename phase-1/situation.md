# Situation — Resources, Requirements, Assumptions, Constraints

## Resources
- **People:** Rafik (owner, decisions + verification); Claude Code session (research + implementation). No external SMEs this pass.
- **Data sources (named):**
  - `barcelona_materials_atlas.md` (NatureGooddest, 2026-05-15) — streams, operators, distances, TRL. GROUNDED for *which materials exist locally*.
  - Manufacturer datasheets / EPDs (web) — for specs: Serge Ferrari, Mehler, Sattler (technical membranes/shade); Dacron/Contender/Dimension-Polyant (sailcloth); ArcelorMittal / generic IPE tables (steel I-beam); HDPE sheet suppliers (Röchling, Gom, Direct Plastics); shade-cloth knit suppliers (Coolaroo, Gale Pacific, agricultural net makers).
  - DEFRA 2024 freight GHG conversion factors (road HGV) — for `transport_mode_factor`.
  - OSRM/Nominatim (existing `src/inventory/routing.py`) — for road distance to Fòrum.
- **Compute/software:** local Python (pythonpath=src), pytest, httpx; web research via firecrawl/WebSearch. Budget: €0.

## Requirements
- **Schedule:** near-term (this milestone).
- **Comprehensibility:** every spec explainable to a non-technical organiser + auditable by a sceptical professor (Naboni review context).
- **Legal/ethical:** cite sources; don't misrepresent a category average as a product spec; **honesty non-negotiables** (CLAUDE.md): label ASSUMED/DECLARED, carbon transport-only, no greenwash, LLM-never-designs (specs are sourced/derived, not model-invented).
- **Deployment env:** in-repo JSON consumed by existing FastAPI + React app.

## Assumptions
- Town-centroid origin is an acceptable distance granularity (no exact supplier address available).
- A material-class datasheet (e.g. "PVC-coated polyester shade membrane") is representative enough for an archetype that pools many real listings.
- Reclaimed material reuses a virgin-product datasheet's *physical* specs (mass/thickness/transmissivity) faithfully; only carbon uses the recycled cut-off (manufacturing=0).

## Constraints
- **In scope:** the 16 archetypes' engineering specs + provenance ledger; distance baseline fix; transport_mode_factor sourcing.
- **Out of scope (explicit):**
  1. NOT changing the placement/cooling/selection algorithms (only their material inputs).
  2. NOT live-scraping new supplier feeds (Lever 1 stays — separate sourcing problem).
  3. NOT adding apparel/dressmaking materials.
  4. NOT building the supplier-onboarding catalog wiring this pass (deferred until specs are real).
