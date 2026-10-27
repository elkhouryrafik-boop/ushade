"""Diagnostic: raw Rhino.Compute solve of festcool_structure.gh — dump every RH_OUT param.

Tells you whether RH_OUT:OUT_Mesh is ABSENT (no such output param on the canvas) or PRESENT
BUT EMPTY (param exists, but the Python `mesh` output isn't feeding it — the renamed-stdout bug).
Reuses the exact request + tree builders the real spine uses, then calls EvaluateDefinition
directly and prints the param names / branch / data-item counts instead of parsing the contract.

Run (from repo root, geom extra installed, compute up on :6500, .env present):

    python scripts/debug_live_response.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
for p in (str(_REPO / "src"), str(_REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from dotenv import load_dotenv

    load_dotenv(_REPO / ".env")
except ImportError:
    pass

_DEMO = _REPO / "projects" / "primavera-demo"
_BRIEF_DATE = "2026-06-14"


def main() -> int:
    from geom.geom import build_gh_request, sun_vector
    from geom.live_client import ComputeRhinoClient, _load_geom_sdk

    footprint = json.loads((_DEMO / "footprint.json").read_text(encoding="utf-8"))
    flow_vectors = json.loads((_DEMO / "crowd_grid.json").read_text(encoding="utf-8"))["flow_vectors"]

    rhino3dm, Util, Grasshopper = _load_geom_sdk()
    client = ComputeRhinoClient()
    print(f"gh   = {client.gh_path}")
    print(f"url  = {client.url}")

    Util.url = client.url if client.url.endswith("/") else client.url + "/"
    if client._api_key:
        Util.apiKey = client._api_key

    gh_request = build_gh_request(footprint, flow_vectors, sun_vector(_BRIEF_DATE))
    trees = client._build_trees(gh_request, rhino3dm, Grasshopper)

    response = Grasshopper.EvaluateDefinition(client.gh_path, trees)

    # Dump the FULL raw response for inspection + surface any solve errors/warnings the
    # Python component emitted (this is where an exception in the script shows up).
    dump = _REPO / "scripts" / "_live_response.json"
    dump.write_text(json.dumps(response, indent=2), encoding="utf-8")
    print(f"full response written to {dump}")
    if isinstance(response, dict):
        print(f"top-level keys: {list(response.keys())}")
        for key in ("errors", "warnings"):
            arr = response.get(key)
            if arr:
                print(f"\n!! {key.upper()} ({len(arr)}):")
                for e in arr:
                    print(f"   - {e}")

    if not isinstance(response, dict) or "values" not in response:
        print("\n!! response carried no 'values' — definition not solving / RH_OUT wiring broken")
        print(json.dumps(response, indent=2)[:2000])
        return 1

    print(f"\n{'PARAM (ParamName)':45} {'branches':>9} {'items':>7}")
    print("-" * 65)
    for val in response["values"]:
        name = str(val.get("ParamName", "<none>"))
        tree = val.get("InnerTree") or {}
        items = sum(len(b) for b in tree.values())
        print(f"{name:45} {len(tree):>9} {items:>7}")

    names = [str(v.get("ParamName", "")) for v in response["values"]]
    wanted = ["RH_OUT:OUT_Mesh", "RH_OUT:OUT_Pillars", "RH_OUT:OUT_Membrane_m2"]
    print("\nContract params expected by live_client._parse_response:")
    for w in wanted:
        hit = next((v for v in response["values"] if str(v.get("ParamName", "")) == w), None)
        if hit is None:
            short = w.split(":")[-1]
            alt = [n for n in names if n.split(":")[-1] == short]
            print(f"  {w:26} ABSENT" + (f"  (similar: {alt})" if alt else "  (no similar nickname)"))
        else:
            items = sum(len(b) for b in (hit.get("InnerTree") or {}).values())
            print(f"  {w:26} {'OK' if items else 'PRESENT-BUT-EMPTY'} ({items} item/s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
