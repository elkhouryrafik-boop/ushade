# Phase 2 (crowd) — Brief Revisit: can crowd_density become DERIVED?

**Question:** obtain real measured festival crowd-density data (EU/Spain) to calibrate the JuPedSim crowd field and promote `crowd_density` ASSUMED → DERIVED.

**Answer: PARTIALLY — and it must be split into three sub-claims (per the literature: RiMEA, ISO 20414, HyPedSim). Each promotes independently.**

| Sub-claim | What it asserts | Min real data | Open EU/Spain data covers it? | Verdict |
|---|---|---|---|---|
| **Local physics** | speed ↔ density obeys a real pedestrian law | Jülich FD (CC-BY) + Voronoi via PedPy | **YES — fully** | **DERIVABLE NOW.** Adopt a Voronoi-FD gate vs Weidmann ±20% (RiMEA-aligned), bound to the JuPedSim engine fingerprint. |
| **Magnitude** | how many people total | RFID/turnstile admit count (organiser) | NO (capacity = upper bound only) | **Stays ASSUMED** until organiser admit logs. Capacity is an honest bound. |
| **Spatial distribution** (which cells busy — drives shade) | the stage-popularity / spawn allocation | per-stage/zone observed counts AT THE SITE | **NO — no open dataset, our site or any** | **Stays ASSUMED.** Only organiser site data (RFID zone dwell / video outflow / Wi-Fi heatmap) can promote it. |

## Validation metric to adopt (when data arrives)
- **Physics:** Voronoi-based fundamental diagram within **±20%** of Weidmann (LOCKED, RiMEA core test). PedPy computes it natively from JuPedSim trajectories.
- **Spatial:** **GAME (Grid Average Mean Error)** on the per-cell lattice as primary (penalises right-total-wrong-place — the exact failure of the RED stage-reach gate), per-cell **RMSE + MAE** secondary. HyPedSim precedent (Lyon): genetic-algorithm calibration, fitness = mean normalised absolute error of simulated vs observed per-zone outflow; LOCK the threshold (≤0.20–0.30) pre-run, never tune to pass.

## Cheap upgrades that improve ASSUMED *now* (no site data, NOT DERIVED)
1. **Stage popularity weights** → replace the ordinal 1–5 hand table with **Spotify monthly-listeners / Songkick tracker counts** per headliner × set-time (free APIs; drops into `set_times_2026.json`). Best single upgrade — makes "where crowd gathers" evidence-informed.
2. **Dwell reach radius / cluster density** → bound by **Fruin critical density 2–3 ped/m²** instead of a guessed value.
3. **Magnitude** → keep ticketing **capacity as the honest upper bound**, labelled ASSUMED.
4. Optional weak spatial prior: geotagged-post DBSCAN per stage — log the sampling bias; ASSUMED-grade only.

## Verdict on the JuPedSim decision (the real question behind this hunt)
**JuPedSim was NOT a mistake — this hunt strengthens it.** The open EU validation data (Jülich, Lyon, Pamplona) is expressed in exactly the Voronoi-density terms that **PedPy — JuPedSim's own analysis library — produces natively.** No engine is better positioned to be validated against this data. Switching engines would not have changed the one true ceiling: **the spatial-allocation sub-claim is ASSUMED because no open data measures crowd density inside a specific festival — that is a data gap, not an engine flaw, and every simulator hits it identically.**

**Recommended path (honest, incremental):**
1. **Now:** Spotify/Songkick popularity weights + Fruin density bounds → ASSUMED becomes *evidence-informed* (better placement, same honest label).
2. **Cheap DERIVED win:** Voronoi-FD gate (Jülich + PedPy) → promote the **local-physics** sub-claim to DERIVED, standards-aligned. Document that magnitude + spatial stay ASSUMED.
3. **Only with organiser data:** per-zone counts → GAME gate → promote magnitude + spatial to DERIVED. This is the lever that retires the four ASSUMED inputs; it needs data only the festival holds.
