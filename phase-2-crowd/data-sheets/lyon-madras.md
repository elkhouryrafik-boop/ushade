# Data sheet — Lyon Fête des Lumières pedestrian trajectories (MADRAS)

1. **Motivation.** Collected by the MADRAS project to study dense crowd dynamics at a real mass event (Lyon Festival of Lights, ~150k/night). Zenodo 10.5281/zenodo.13830435; Nature Sci-Data paper PMC12043992.
2. **Composition.** ~7,000 pedestrian trajectories (id, t, x, y) from overhead + a 48 m tower camera; macro flows + micro attractor-egress. Density observed up to ~4 ped/m².
3. **Collection.** Video at a live festival, computer-vision tracking; 30 fps video / ~10 Hz trajectories.
4. **Pre-processing (we must do).** Reproject to UTM31N; resample to our 1 s frame / 6 m lattice; compute Voronoi density via PedPy. Confirm coordinate units (metres + homography).
5. **Uses.** ✅ validate sim density MAGNITUDES + general festival flow realism; ✅ method precedent (HyPedSim calibrated a sim to this exact festival via GA on per-zone outflow). ✗ NOT our site geometry — cannot validate Parc del Fòrum stage allocation; ✗ not a per-cell ground-truth for our spawn weights.
6. **Distribution.** Zenodo, CC-BY 4.0 (cite). Verified reachable 2026-06-22.
7. **Maintenance.** Static archived dataset + paper; stable DOI.
8. **Limitations.** Single site/event; density tops ~4 ped/m² (no extreme tail — use Pamplona for that); attractor structure is Lyon's light-installations, not music stages; CV tracking loses agents under occlusion.
