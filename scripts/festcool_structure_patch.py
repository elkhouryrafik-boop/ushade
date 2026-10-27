# festcool_structure — LIVE Grasshopper solve (Rhino 8 Python 3 Script component)
# Mirrors src/geom/reference_generator.py PREVIEW logic so the LIVE<->PREVIEW diff is meaningful.
# Inputs : footprint [Curve, List], flow [Curve, List], sun [Vector3d, Item]
# Outputs: mesh, pillars, membrane
# Karamba pre-screen (runbook B.2 step 6) is a SEPARATE optional native cluster, advisory only —
# it is NOT wired here and NOT in the frozen contract (OUT_Mesh + OUT_BOM only). Do not add it.

import Rhino.Geometry as rg

# --- Constants — KEEP IDENTICAL to src/geom/constants.py ---
GRID_SPACING_M = 12.0   # [ASSUMED A4] coarse demo grid
FLOW_BUFFER_M = 4.0     # [ASSUMED A2] half-lane clearance (constants.py = 4.0)
H = 5.0                 # [ASSUMED] roof height (m)

TOL = 0.001
PLANE = rg.Plane.WorldXY


# --- containment test — enum-free for Rhino 8 CPython robustness ---
# Curve.Contains(...) returns a PointContainmentType enum. Referencing
# rg.PointContainmentType.Inside throws under Rhino 8's CPython binding, so compare on the
# enum's integer value instead (Unset=0, Inside=1, Outside=2, Coincident=3).
def _is_inside(crv, pt):
    r = crv.Contains(pt, PLANE, TOL)
    try:
        return int(r) == 1
    except (TypeError, ValueError):
        return str(r).split(".")[-1] == "Inside"


# --- normalize inputs to lists ---
foot = footprint if isinstance(footprint, list) else ([footprint] if footprint else [])
flows = flow if isinstance(flow, list) else ([flow] if flow else [])

# --- 1. membrane area = sum of footprint patch areas (OUT_Membrane_m2) ---
membrane = 0.0
for crv in foot:
    amp = rg.AreaMassProperties.Compute(crv)
    if amp:
        membrane += amp.Area

# --- 3. candidate pillar grid per patch (12 m lattice, anchored at each patch min-corner) ---
candidates = []
for crv in foot:
    bb = crv.GetBoundingBox(True)
    found = False
    y = bb.Min.Y
    while y <= bb.Max.Y:
        x = bb.Min.X
        while x <= bb.Max.X:
            pt = rg.Point3d(x, y, 0.0)
            if _is_inside(crv, pt):
                candidates.append(pt)
                found = True
            x += GRID_SPACING_M
        y += GRID_SPACING_M
    if not found:  # fallback: >=1 pillar per disjoint patch (centroid)
        amp = rg.AreaMassProperties.Compute(crv)
        if amp:
            candidates.append(amp.Centroid)

# --- 4. egress cull: keep points whose min distance to EVERY flow line >= FLOW_BUFFER_M ---
def min_dist_to_flows(pt):
    best = float("inf")
    for ln in flows:
        ok, t = ln.ClosestPoint(pt)
        if ok:
            d = pt.DistanceTo(ln.PointAt(t))
            if d < best:
                best = d
    return best

survivors = [p for p in candidates if min_dist_to_flows(p) >= FLOW_BUFFER_M]

# --- 7. OUT_Mesh: roof (footprint @ z=H) + column boxes, joined into ONE mesh ---
#        Keep the footprint's own XY origin — do NOT scale, do NOT move to world origin.
out = rg.Mesh()
mp = rg.MeshingParameters.Default

# roof — planar mesh of each patch, raised by H
for crv in foot:
    roof = rg.Mesh.CreateFromPlanarBoundary(crv, mp, TOL)
    if roof:
        roof.Translate(0.0, 0.0, H)
        out.Append(roof)

# columns — 0.30 m square box from z=0 to z=H at each surviving pillar
half = 0.15
for p in survivors:
    box = rg.Box(PLANE,
                 rg.Interval(p.X - half, p.X + half),
                 rg.Interval(p.Y - half, p.Y + half),
                 rg.Interval(0.0, H))
    col = rg.Mesh.CreateFromBox(box, 1, 1, 1)
    if col:
        out.Append(col)

out.Faces.CullDegenerateFaces()
out.Normals.ComputeNormals()
out.Compact()

# --- outputs ---
mesh = out
pillars = len(survivors)
membrane = float(membrane)
