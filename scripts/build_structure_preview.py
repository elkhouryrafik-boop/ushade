"""PREVIEW 3D structure builder — pure Python, NO Rhino.Compute / Grasshopper / rhino3dm.

Why this exists
---------------
The live Rhino.Compute + Grasshopper path (``run_live_geom.py`` + ``festcool_structure.gh``)
is heavyweight to stand up. The committed PREVIEW fallback (``reference_generator``) already
runs offline, BUT its mesh is a FLAT footprint quad (z=0) — so the Three.js viewport's
``StructureModel`` measures a zero vertical extent, marks the geometry DEGENERATE, and shows an
empty "pending" state. The structure looks fake because the mesh has no height.

This script keeps the GROUNDED half and fixes the visual half, with zero Rhino:

* pillar XY positions  -> FAITHFUL  : real shapely flow-cull on the real footprint + flow vectors
                                      (reuses ``reference_generator`` — the same grounded code path)
* membrane_m2 / pillars -> DERIVED  : footprint area + surviving-pillar count (unchanged BOM math)
* 3D extrusion          -> PREVIEW  : pillars extruded to ``PILLAR_H_M`` boxes + a roof slab at the
                                      top. Honestly approximate (boxes + flat slab), NOT certified —
                                      exactly the claim ``reference_generator`` already makes.

Output (metres, Y-up, origin-translated to the footprint min-corner — identical convention to
``geom.decode``): ``structure.glb`` / ``.gltf`` / ``.obj`` written into the demo project dir, so the
existing ``/api/project/<id>/geometry`` endpoint and the React viewport render it unchanged.

Run (from repo root):

    PYTHONPATH="src;." python scripts/build_structure_preview.py

trimesh + numpy are the only heavy deps and both are already installed (the ``geom`` extra's
trimesh). No network, no compute server.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import trimesh

_REPO = Path(__file__).resolve().parents[1]
for p in (str(_REPO / "src"), str(_REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

import json

from geom.reference_generator import _footprint_polygon, _grid_points, cull_grid

# --- PREVIEW extrusion constants (visual only — labelled PREVIEW, never certified) -----------
PILLAR_H_M = 5.0      # roof height (m) — matches the GH-script ASSUMED H
PILLAR_SECTION_M = 0.6  # square pillar side (m) — visible at venue scale
ROOF_THICK_M = 0.4    # roof slab thickness (m)

_DEMO = _REPO / "projects" / "primavera-demo"


def _load_inputs() -> tuple[dict, list[dict]]:
    footprint = json.loads((_DEMO / "footprint.json").read_text(encoding="utf-8"))
    flow_vectors = json.loads(
        (_DEMO / "crowd_grid.json").read_text(encoding="utf-8")
    )["flow_vectors"]
    return footprint, flow_vectors


def _yup_box(cx: float, cz: float, half_x: float, half_z: float, y0: float, y1: float):
    """Axis-aligned box in glTF Y-up frame (X/Z horizontal, Y vertical).

    cx/cz are the horizontal centre (already origin-translated metres); y0/y1 are the
    vertical span. Returns a trimesh.Trimesh.
    """
    extents = (half_x * 2.0, y1 - y0, half_z * 2.0)
    box = trimesh.creation.box(extents=extents)
    box.apply_translation((cx, (y0 + y1) / 2.0, cz))
    return box


def build() -> dict:
    footprint, flow_vectors = _load_inputs()

    # --- GROUNDED: real footprint union + grid + faithful flow-cull (reused, unchanged) ---
    poly = _footprint_polygon(footprint)
    candidates = _grid_points(poly)
    survivors = cull_grid(candidates, flow_vectors)
    if not survivors:
        raise SystemExit("flow-cull removed every pillar — nothing to extrude")

    # Origin-translate to footprint min-corner (decode.py convention).
    minx, miny, _maxx, _maxy = poly.bounds
    half = PILLAR_SECTION_M / 2.0

    parts: list[trimesh.Trimesh] = []

    # --- PREVIEW: extrude each surviving pillar to a vertical box ---
    for (x, y) in survivors:
        parts.append(
            _yup_box(x - minx, y - miny, half, half, 0.0, PILLAR_H_M)
        )

    # --- PREVIEW: roof slab over each disjoint shade patch (sits on top of the pillars) ---
    geoms = poly.geoms if hasattr(poly, "geoms") else [poly]
    for patch in geoms:
        pminx, pminy, pmaxx, pmaxy = patch.bounds
        cx = (pminx + pmaxx) / 2.0 - minx
        cz = (pminy + pmaxy) / 2.0 - miny
        hx = (pmaxx - pminx) / 2.0
        hz = (pmaxy - pminy) / 2.0
        if hx <= 0 or hz <= 0:
            continue
        parts.append(
            _yup_box(cx, cz, hx, hz, PILLAR_H_M, PILLAR_H_M + ROOF_THICK_M)
        )

    mesh = trimesh.util.concatenate(parts)

    span = mesh.bounds[1] - mesh.bounds[0]  # [x, y(vertical), z]
    membrane_m2 = float(poly.area)

    _DEMO.mkdir(parents=True, exist_ok=True)
    glb = _DEMO / "structure.glb"
    mesh.export(str(_DEMO / "structure.obj"))
    mesh.export(str(_DEMO / "structure.gltf"))
    mesh.export(str(glb), file_type="glb")

    return {
        "pillars": len(survivors),
        "membrane_m2": round(membrane_m2, 1),
        "bbox_span_m": [round(float(s), 1) for s in span],
        "glb": str(glb),
        "glb_bytes": glb.stat().st_size,
    }


if __name__ == "__main__":
    result = build()
    print(json.dumps(result, indent=2))
    sx, sy, sz = result["bbox_span_m"]
    if min(sx, sy, sz) < 1e-3:
        sys.exit("DEGENERATE: a bbox axis is ~0 — viewport would mark this a placeholder")
    print(
        f"\nOK — real 3D PREVIEW structure: {result['pillars']} pillars, "
        f"{result['membrane_m2']} m2 membrane, span {sx}x{sy}x{sz} m (X x Y-vert x Z)."
    )
