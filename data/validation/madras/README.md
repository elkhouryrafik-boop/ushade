# MADRAS Lyon Fête-des-Lumières — crowd-density validation reference

Real measured festival crowd-density data used to validate U-Shade's JuPedSim CFSM
density magnitude (ASSUMED → DERIVED for the magnitude sub-claim). See `phase-2-crowd/`.

- **Source:** Zenodo DOI 10.5281/zenodo.13830435 (CC-BY 4.0); Nature Sci-Data PMC12043992.
- **Re-fetch** (the 33 MB raw zip is gitignored — re-download to reproduce):
  `curl -sL "https://zenodo.org/api/records/13830435/files/Data_Madras.zip/content" -o data/validation/madras/Data_Madras.zip`
- **Build the reference:** `python scripts/crowd_validation/build_lyon_reference.py`
  → `lyon_walkable.wkt` + `lyon_observed_density.json` (both committed).
- **Run the validation:** `PYTHONPATH=src python scripts/crowd_validation/run_lyon_validation.py`
  → on green writes `src/crowd/benchmark_result_crowdsim.json` (the tier-flip artifact).
