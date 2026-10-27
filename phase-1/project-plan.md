# Project Plan — Material Data Layer (CRISP-DM)

**Tool posture:** Python (pythonpath=src) + pytest; web research via firecrawl/WebSearch; existing `routing.py` (OSRM/Nominatim) for distances. No commercial tools. €0.

| Phase | Work | Duration | Decision gate |
|---|---|---|---|
| **0 — acquisition** | List the 16 archetypes + the spec fields each needs; identify candidate datasheet/EPD sources per material class | short | Source list exists per material |
| **2 — Data Understanding (`earn-the-data`)** | Hunt + vet a real datasheet/EPD per (material × spec); score on the 5-dim rubric; draft data sheets; flag which archetypes can't be grounded | main effort | **GATE: ≥4 of 6 atlas-added archetypes grounded, else trigger cancellation criterion (trim catalogue)** |
| **3 — Data Preparation** | Write sourced specs into `data/materials.json`; build the per-field provenance ledger; fix distance baseline to Fòrum; replace 0.10 transport factor with cited DEFRA value | medium | Every spec field has a tier + source |
| **4 — Modeling** | (Mostly existing) confirm cooling/carbon/cost selection consumes the new specs unchanged; no algorithm change | short | Selection runs on real specs |
| **5 — Evaluation** | Validate transmissivity in 0–1 + consistent with cited shade %; sanity-check carbon/cost ranges; reproduce 3 random fields from sources; run test suite | medium | Success criteria met |
| **6 — Deployment** | Commit; update HANDOFF + memory; surface provenance tiers in UI/PDF (or hand off that UI task) | short | Numbers shipped with tiers |

**Quality gates:** the Phase-2 grounding gate (cancellation), the Phase-3 "every field tiered" gate, the Phase-5 reproducibility check. The project ends/reframes at the Phase-2 gate if data can't support real specs.
