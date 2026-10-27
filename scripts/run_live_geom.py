"""Operator smoke run — Phase 4 geometry stage against a LIVE local Rhino.Compute + Grasshopper.

This is the script you run AFTER (1) a compute server is up (Hops launches one on :6500), and
(2) you have authored ``festcool_structure.gh`` per ``04-LIVE-RHINO-RUNBOOK.md`` and pointed
``GH_DEFINITION_PATH`` at it. It injects ``geom.live_client.ComputeRhinoClient`` into the same
``run_gh_stage`` spine the PREVIEW demo uses, writes the four artifacts into a LIVE out-dir, and
prints a side-by-side diff against the committed PREVIEW baseline so you can see what the real
Grasshopper solve changed (pillar count, membrane area, bbox span, shadow coverage).

Run (from the repo root, with the geom extra installed and .env loaded):

    RHINO_COMPUTE_URL=http://localhost:6500/ \
    GH_DEFINITION_PATH=/abs/path/festcool_structure.gh \
    PYTHONPATH="src;." python scripts/run_live_geom.py

Exit 0 + a printed summary on success; exit 1 + the typed error on any failure (the stage is left
NOT done with no partial artifact, exactly like the PREVIEW path).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
for p in (str(_REPO / "src"), str(_REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Auto-load repo .env so GH_DEFINITION_PATH / RHINO_COMPUTE_URL resolve without manual export.
# Guarded: if python-dotenv is missing, fall back to whatever is already in the OS environment.
try:
    from dotenv import load_dotenv

    load_dotenv(_REPO / ".env")
except ImportError:
    pass

_DEMO = _REPO / "projects" / "primavera-demo"
_BRIEF_DATE = "2026-06-14"  # the Parc-del-Fòrum demo date (same as the PREVIEW baseline)


def _load_inputs() -> tuple[dict, list[dict]]:
    footprint = json.loads((_DEMO / "footprint.json").read_text(encoding="utf-8"))
    flow_vectors = json.loads((_DEMO / "crowd_grid.json").read_text(encoding="utf-8"))["flow_vectors"]
    return footprint, flow_vectors


def main() -> int:
    from geom.geom import run_gh_stage, RhinoComputeError
    from geom.live_client import ComputeRhinoClient

    footprint, flow_vectors = _load_inputs()
    out = _DEMO / "live"
    out.mkdir(parents=True, exist_ok=True)

    client = ComputeRhinoClient()  # config from env: GH_DEFINITION_PATH + RHINO_COMPUTE_URL
    print(f"→ live solve: gh={client.gh_path}  url={client.url}")
    print(f"  inputs: {len(footprint.get('polygons', []))} footprint polygons, "
          f"{len(flow_vectors)} flow vector(s), brief {_BRIEF_DATE}")

    try:
        result = run_gh_stage(footprint, flow_vectors, client=client, out_dir=out,
                              brief_date=_BRIEF_DATE)
    except RhinoComputeError as exc:
        print(f"\n✗ LIVE solve failed: {exc}", file=sys.stderr)
        print("  (stage left NOT done, no partial artifact — same fail-safe as PREVIEW)",
              file=sys.stderr)
        return 1

    gh_meta = json.loads((out / "gh_meta.json").read_text(encoding="utf-8"))
    live_bom = gh_meta["bom"]
    live_cov = gh_meta.get("shadow_coverage_pct")
    live_basis = result.get("shadow_coverage_basis", "?")

    # PREVIEW baseline (the committed demo artifacts) for the diff.
    base_meta = json.loads((_DEMO / "gh_meta.json").read_text(encoding="utf-8"))
    base_bom = base_meta["bom"]

    print("\n── LIVE vs PREVIEW ─────────────────────────────")
    print(f"  pillars       PREVIEW {base_bom['pillars']:>8}  |  LIVE {live_bom['pillars']:>8}")
    print(f"  membrane_m2   PREVIEW {base_bom['membrane_m2']:>8}  |  LIVE {live_bom['membrane_m2']:>8}")
    print(f"  shadow_cov    PREVIEW {base_meta.get('shadow_coverage_pct'):>8}  |  LIVE {live_cov:>8}"
          f"  ({live_basis})")
    print(f"  artifacts     {out}/structure.gltf + .obj + gh_response.json")
    print("\n✓ LIVE solve OK — this geometry is GROUNDED (real Grasshopper). Karamba verdict remains")
    print("  live-only pre-screening, NOT an engineering stamp.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
