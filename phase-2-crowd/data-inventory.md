# Phase 2 (crowd) — Data Inventory: festival crowd-density calibration

**Decision unit:** per-cell crowd **density** (people/m² or agents per ~6 m lattice cell) over a festival-scale outdoor venue (~hundreds of m, Parc del Fòrum), at representative peak times, with stage/attractor structure. Two uses: (a) **fit** the ASSUMED inputs (stage popularity weights, gate spawn split, agent count, dwell reach radius), (b) **validate** the simulated density field. Goal: can `crowd_density` honestly move ASSUMED → DERIVED?

All sources below were verified at primary source (2026-06-22); reachability flagged. Rubric 0–3 per dim: Provenance / Resolution / Coverage / Licensing / Bias.

## Tier 1 — real metric people/m² (USE)

| Source | What | Spatial / temporal | Density? | EU? | Licence | Rubric (P/R/C/L/B) | Verdict |
|---|---|---|---|---|---|---|---|
| **Lyon Fête des Lumières (MADRAS)** — Zenodo 10.5281/zenodo.13830435 ✅ | ~7,000 REAL festival pedestrian trajectories + attractor egress, 48 m tower + overhead | per-person, 10–30 Hz; density to ~4 ped/m² | **YES** | **FR** | CC-BY 4.0 | 3/2/2/3/2 = **12** | **Best festival-realism match.** Validates method + magnitudes; not our site/geometry |
| **Jülich Pedestrian Dynamics Archive** — ped.fz-juelich.de ✅ | Controlled-experiment trajectories (corridor, bottleneck, stadium entrance, BaSiGo concert-hall entrance) | sub-metre, 25 fps; Voronoi people/m² + FD | **YES** | **DE** | CC-BY 4.0 | 3/3/1/3/2 = **12** | **Gold-standard physics.** FD / speed-density gate; native to PedPy. Lab, not venue |
| **San Fermín / Pamplona plaza** — Zenodo 10.5281/zenodo.14050598 ✅ (Nature 2025) | Density field (head-detect) + velocity (PIV), packed plaza pre-event | ~1.5 m PIV windows, 50×20 m; **avg ~6, peak ~9 ped/m²** | **YES** | **ES** | open (Zenodo) | 3/3/1/3/1 = **11** | **High-density TAIL reference** (Spain). Confined plaza ≠ open lawn |
| **PedPy** (tool) — github.com/PedestrianDynamics/PedPy ✅ | Computes Voronoi density/velocity from trajectories; reads JuPedSim format | n/a | bridge | EU | MIT | — | **Bridge tool** — turns any trajectory set + our sim output into a comparable density field |
| **Fruin LOS / G.K. Still** — gkstill.com ✅ | Field-measured density thresholds (LOS, critical 2–3, jam 3.5–5.3 ped/m²) | per-area anchors | YES | — | educational | — | **Absolute ceilings / sanity bounds** |

## Tier 2 — Spain/EU mobility + counters (TEMPORAL / MACRO PRIORS ONLY)

| Source | What | Floor | Density? | Use |
|---|---|---|---|---|
| MITMA Big-Data movilidad ✅ (method PDF; data 403) | telco OD flows + presence, hourly | **census district (3,909 areas)** | flows | macro hourly demand prior; venue sits in ONE cell |
| INE Estudios de movilidad ✅ | telco OD presence, 12×/day (ended 2021) | ~15,000-person cells | presence | too coarse for venue |
| Zurich hystreet ✅ / TfL NUMBAT ✅ / Renfe BCN franja ✅ | laser/gate line counts, hourly | line/gate | headcount | time-of-day SHAPE prior only |

## Tier 3 — Barcelona Open Data / festivals (HEADCOUNT TOTALS, NOT DENSITY)

- **La Mercè** ✅ (CC-BY) — annual attendees per activity, no coords/time. Totals sanity only.
- **BCN `aforaments`** ✅ — vehicles+bikes only, monthly averages. Wrong target (schema template only).
- **a demo festival / Sónar** — annual headcount + capacity only (Primavera 20 ha, capacity 75–95k). Magnitude upper bound only.
- **Vodafone / MWC Smart Steps** — exists in papers; **NOT open** (council/researcher bilateral, privacy-gated). UNVERIFIED at primary (403).

## Tier 4 — CV crowd-counting (IMAGES, not metric /m²)

ShanghaiTech ✅, UCF-QNRF, NWPU-Crowd ✅, JHU-CROWD++, FDST ✅, Mall ✅ — output heads/pixel, **no metric ground density** without homography (only WorldExpo'10 + Venice ship geometry; both tiny/single-view). Useful to train a counter that survives extreme density; output stays ASSUMED.

## The honest finding
**No public dataset gives a per-cell people/m² field over an open festival-scale venue with stage structure — least of all our site (Parc del Fòrum).** That spatial-allocation truth lives only in data the festival ORGANISER holds (RFID/turnstile per gate, per-zone counts, Wi-Fi heatmaps). What the open EU/Spain data CAN do: validate the **local physics** (Jülich FD) and **density magnitudes / max packing** (Lyon, Pamplona, Fruin) — i.e. confirm the sim is physically realistic, not that our specific stage allocation is correct.
