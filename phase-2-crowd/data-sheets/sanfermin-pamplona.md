# Data sheet — San Fermín / Pamplona plaza crowd density (Spain)

1. **Motivation.** Nature 2025 study of extreme crowd packing in the Plaza Consistorial before the San Fermín opening (chupinazo) — a real Spanish high-density event. Zenodo 10.5281/zenodo.14050598 (supersedes paywalled PNAS 2021).
2. **Composition.** Spatial density field (head-detection) + velocity field (PIV), multi-year footage (2019, 2022, 2023, 2024). Avg ~6, peak ~9 ped/m².
3. **Collection.** Fixed overhead video of the packed plaza; CV head detection + particle-image-velocimetry for the velocity field.
4. **Pre-processing (we must do).** Read density/velocity arrays; align PIV ~1.5 m windows; use as a density-ceiling reference (no reprojection needed if used as scalar bounds).
5. **Uses.** ✅ **max-packing / danger-threshold sanity** — confirm our sim never exceeds physically observed densities (~9 ped/m²); anchor the high-density tail Fruin/Still also bound. ✗ Confined plaza pre-event packing ≠ open festival lawn with stages — NOT a model for our spatial distribution.
6. **Distribution.** Open via Zenodo DOI. Verified reachable (PMC11798876).
7. **Maintenance.** Archived dataset + paper; stable DOI.
8. **Limitations.** One confined geometry, one event type (static packing, not flowing/dwelling festival crowd); Spanish but not a music festival; extreme-density regime only.
