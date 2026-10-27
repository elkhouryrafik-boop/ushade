# Phase 2 — Brief Revisit (Step 10)

**Question:** Can we ground every material's engineering specs in real datasheets/EPDs so the cooling×carbon×cost ranking is defensible?

**Answer: YES, with two labelled caveats.**

- **Physical specs (areal mass, thickness, transmissivity, waterproof):** GROUNDED or DERIVED for **16/16** archetypes from real manufacturer datasheets (Serge Ferrari, Innotech, Gale/Coolaroo, Polyfab, extremtextil Dacron, shademesh.org, EPAL, S-Polytec recycled HDPE, Global Truss F34 TÜV table, EN 39 scaffold, IPE 200 section table, COR-TEN sheet, Hermeq fence, Alpha-Tex carpet).
- **Transport carbon factor:** GROUNDED — DEFRA/DESNZ 2024 "All HGVs, average laden" = **0.09752 kgCO₂e/tonne·km** (replaces the 0.10 placeholder; validates it as near-exact).
- **Distances:** DERIVED — real OSRM road routes, supplier-town centroid → Parc del Fòrum (fixes the old Plaça-dels-Àngels baseline).

**Cancellation criterion (≥3 of 6 atlas archetypes ungroundable): NOT triggered — 0 of 6 ungroundable.** All six have real product datasheets.

## The two caveats (carried as DECLARED tiers, never hidden)
1. **Recycled-content claim** for `membr-recycled-shade-cloth` (best datasheet = Polyfab Architec 400, *virgin* HDPE knit) and `membr-recycled-pe-tarp` (Tarpaflex SKU not explicitly recycled) is DECLARED. Physical specs are GROUNDED/DERIVED from the virgin-equivalent; the *recycled* attribute is the estimate. Genuine recycled alt for shade-cloth = Serge Ferrari Soltis 502 Proof (100% recycled PES) but weaker public numeric specs.
2. **`cost_per_unit`** stays on the reclaim/rental basis (the schema's stated definition) and is mostly DECLARED — most datasheets give *new-buy* prices (a different basis), recorded in the ledger as reference. Several supplier prices were behind JS configurators (uncitable statically).

**Conclusion:** Proceed. The cooling term (transmissivity) and carbon term (mass × distance × DEFRA factor) — the two numbers the ranking actually turns on — are now real and sourced. Cost remains the weakest dimension (reclaim-market opacity) and is honestly labelled.
