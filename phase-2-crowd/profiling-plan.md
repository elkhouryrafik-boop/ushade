# Phase 2 (crowd) — Profiling Plan

Run before trusting any source for calibration/validation. Per dataset, the 8 checks:

## Lyon Fête des Lumières (MADRAS, Zenodo 13830435)
1. **Shape/dtypes** — trajectory rows (agent_id, t, x, y); confirm count ≈7,000 agents.
2. **Missing** — track fragmentation / gaps where overhead view occludes; structured at frame edges?
3. **Numeric** — x/y range vs the 48 m-tower scene extent; density distribution (PedPy Voronoi) — confirm peak ≈4 ped/m².
4. **Categorical** — scene/sequence ids; which are attractor-egress vs corridor flow.
5. **Spatial coverage** — bounding box; is there open-area dwell or only road outflow? (HyPedSim used two exit roads.)
6. **Temporal** — frame rate (10–30 Hz), clip durations, peak vs off-peak coverage.
7. **Cross-field** — coordinate units (metres, with homography?) consistent; velocities = finite-diff of positions.
8. **Bridging** — reproject to UTM31; resample to our 1 s / 6 m lattice; compute Voronoi density via PedPy → comparable to our `crowd_grid` field.

## Jülich Pedestrian Dynamics Archive
1–4. Per-experiment trajectory files (HDF5/txt/JSON); confirm geometry (corridor/bottleneck/BaSiGo entrance), participant counts (up to 926).
5. Geometry extent (lab metres) — NOT venue-scale; use for FD only.
6. 25 fps; run durations.
7. PeTrack sub-metre accuracy; units metres.
8. **Bridge:** PedPy Voronoi density–velocity FD → compare against JuPedSim CFSM emergent FD at ±20% (the physics gate).

## San Fermín / Pamplona (Zenodo 14050598)
1–4. Density-field + PIV-velocity arrays; head-detection counts.
5. Plaza 50×20 m; confined — high-density tail only.
6. Multi-year footage (2019/22/23/24); pre-event packing window.
7. PIV window ~1.5 m; density people/m².
8. **Bridge:** use as max-packing ceiling check (does our sim ever exceed observed 9 ped/m²? it should not).

**Cross-source rule:** never join two density fields without reprojecting to a common CRS (UTM31N for our site) and matching the density estimator (Voronoi, via PedPy) — a pixel-count map and a Voronoi field are not comparable.
