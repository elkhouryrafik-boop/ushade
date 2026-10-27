"""PREVIEW reference-geometry generator — the LABELLED offline stand-in for the absent Rhino host.

This is the Python half of Phase 4 (GEOM-02 / GEOM-06). It carries exactly ONE faithful,
GROUNDED sub-capability — the shapely flow-vector cull — and surrounds it with a deterministic,
honestly PREVIEW-labelled reference solve that produces a contract-valid ``gh_response``
(``OUT_Mesh`` + ``OUT_BOM``) so it is a drop-in for ``FakeRhinoClient`` / the live solve. It makes
NO engineering claim: Karamba is named "live-only, pre-screening, requires engineering sign-off",
never "certified". This is the structural analogue of the climate stage's LABELLED EPW fallback
and the crowd stage's ASSUMED-grade routing.

Provenance honesty (RESEARCH §Faithful-vs-mock table):

* Flow-vector buffer cull (GEOM-02)  -> FAITHFUL (shapely buffer + contains)  -> GROUNDED-geometry
* Column extrude / roof tilt          -> APPROXIMATED (boxes + plane)           -> PREVIEW
* Karamba thicken (GEOM-04)           -> NOT RUN offline                        -> live-only pre-screening
* BOM pillar count / membrane m2      -> DERIVED from the preview grid          -> DERIVED-preview

``shapely`` is a BASE dependency (imported at module top). ``rhino3dm`` is the optional ``geom``
extra — it is lazy-imported inside ``build_reference`` (clone of ``infrared_client._load_sdk``) so
that merely importing this module is dependency-free and the base pytest suite stays green.

The module also exposes a ``python -m geom.reference_generator --input --output`` CLI bridge that
the Node ``ReferenceGeometryClient`` invokes via ``execFile``: read a ``gh_request`` JSON, build the
PREVIEW ``gh_response``, re-validate it (defence-in-depth, WARNING 7 / T-04-16), write it atomically,
exit 0; on ANY error write a short message to stderr and exit 1 (Node maps non-zero -> RhinoComputeError).
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from shapely.geometry import LineString, Point, Polygon  # BASE dep — NOT lazy
from shapely.ops import unary_union

from geom.constants import (
    FLOW_BUFFER_M,
    GRID_SPACING_M,
    PREVIEW_LABEL,
)

_SCHEMA_VERSION = "1.0.0"
_KARAMBA_PROVENANCE = "live-only, pre-screening, requires engineering sign-off"


class ReferenceGenerateError(Exception):
    """Typed error raised when the PREVIEW reference solve cannot be produced.

    Carries its cause so the CLI bridge can surface a short message to stderr and the
    Node ``ReferenceGeometryClient`` can map a non-zero exit to ``RhinoComputeError``.
    """


# --------------------------------------------------------------------------- #
# Lazy geom-extra loader (clone of infrared_client._load_sdk)
# --------------------------------------------------------------------------- #
def _load_geom_sdk():
    """Lazily import rhino3dm (the ``geom`` extra). Never imported at module top.

    Raises ``ReferenceGenerateError`` with an actionable install hint on ImportError so a
    missing extra surfaces as a typed reference-generator failure, not a bare ImportError —
    keeping the base offline suite dependency-free (mirror of ``_load_sdk`` / T-02a-10).
    """
    try:  # imported here, NEVER at module top
        import rhino3dm  # noqa: PLC0415  (intentional lazy import — keep base suite dep-free)
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise ReferenceGenerateError(
            "geom extra not installed — `pip install -e .[geom]` to build the PREVIEW reference mesh"
        ) from exc
    return rhino3dm


# --------------------------------------------------------------------------- #
# FAITHFUL sub-capability: shapely flow-vector cull (GEOM-02, GROUNDED-geometry)
# --------------------------------------------------------------------------- #
def _flow_lines(flow_vectors: list[dict]) -> list[LineString]:
    """Build shapely ``LineString``s from the gh_request / crowd_grid flow-vector shape.

    Each flow vector is ``{origin:{x_m,y_m}, destination:{x_m,y_m}}`` in EPSG:32631 metres.
    """
    lines: list[LineString] = []
    for fv in flow_vectors:
        o, d = fv["origin"], fv["destination"]
        lines.append(LineString([(o["x_m"], o["y_m"]), (d["x_m"], d["y_m"])]))
    return lines


def cull_grid(
    points: list[tuple[float, float]],
    flow_vectors: list[dict],
    buffer_m: float = FLOW_BUFFER_M,
) -> list[tuple[float, float]]:
    """FAITHFUL (GROUNDED-geometry): drop every candidate point within ``buffer_m`` of any route.

    Shade must never land on a crowd evacuation route (GEOM-02): a candidate pillar point that
    falls inside the ``buffer_m`` halo of ANY flow line is culled; a point clear of every route
    survives. This is real shapely ``buffer(...).contains(...)`` — the one offline sub-capability
    that is genuinely faithful (not PREVIEW).

    Args:
        points: candidate grid points ``[(x_m, y_m), ...]`` in EPSG:32631 metres.
        flow_vectors: the crowd_grid / gh_request flow-vector list (origin/destination dicts).
        buffer_m: half an egress-lane clearance (default ``FLOW_BUFFER_M``).

    Returns:
        The survivors — points clear of every buffered route, in input order.
    """
    buffers = [ln.buffer(buffer_m) for ln in _flow_lines(flow_vectors)]
    survivors: list[tuple[float, float]] = []
    for x, y in points:
        p = Point(x, y)
        if not any(b.contains(p) for b in buffers):
            survivors.append((x, y))
    return survivors


# --------------------------------------------------------------------------- #
# Footprint reshape (gh_request / footprint.json -> shapely)
# --------------------------------------------------------------------------- #
def _footprint_polygon(footprint: Any):
    """Union the footprint polygons into one shapely geometry (EPSG:32631 metres).

    Accepts the ``footprint.json`` shape ``{polygons: [[{x_m,y_m}, ...], ...]}`` or a raw list of
    rings. Returns the union AS-IS (Polygon or MultiPolygon): the real shade footprint is DISJOINT
    patches, and hulling them would inflate ``membrane_m2`` ~48x (venue hull vs actual shade) and
    lay pillars across unshaded ground. ``.bounds`` / ``.contains`` / ``.area`` all work on a
    MultiPolygon, so downstream code needs no single-Polygon guarantee.
    """
    if isinstance(footprint, dict):
        rings = footprint.get("polygons", [])
    else:
        rings = footprint
    polys: list[Polygon] = []
    for ring in rings:
        coords = [(pt["x_m"], pt["y_m"]) for pt in ring]
        if len(coords) >= 3:
            polys.append(Polygon(coords))
    if not polys:
        raise ReferenceGenerateError("footprint has no valid polygon ring")
    return unary_union(polys)


def _grid_points(footprint_poly, spacing_m: float = GRID_SPACING_M) -> list[tuple[float, float]]:
    """FAITHFUL: lay a coarse ``spacing_m`` lattice per shade patch; keep points inside it.

    The grid is anchored at EACH patch's own min-corner (a globally-anchored lattice walks
    right past patches narrower than the spacing — the real footprint is many small disjoint
    cell-unions). A patch that still catches no lattice point gets its ``representative_point``
    so every disjoint shade patch carries >= 1 candidate pillar (a roof with zero support is
    not a usable PREVIEW BOM).
    """
    geoms = footprint_poly.geoms if hasattr(footprint_poly, "geoms") else [footprint_poly]
    pts: list[tuple[float, float]] = []
    for patch in geoms:
        minx, miny, maxx, maxy = patch.bounds
        found = False
        y = miny
        while y <= maxy:
            x = minx
            while x <= maxx:
                if patch.contains(Point(x, y)):
                    pts.append((x, y))
                    found = True
                x += spacing_m
            y += spacing_m
        if not found:
            rp = patch.representative_point()
            pts.append((rp.x, rp.y))
    return pts


# --------------------------------------------------------------------------- #
# PREVIEW mesh build (APPROXIMATED — boxes + flat roof plane; rhino3dm lazy)
# --------------------------------------------------------------------------- #
def _build_preview_mesh_b64(footprint_poly: Polygon, pillar_pts: list[tuple[float, float]]) -> str:
    """APPROXIMATED (PREVIEW): build a coarse rhino3dm mesh of the footprint + serialize to base64.

    The mesh is the footprint quad laid flat at z=0 (origin-translated to the footprint min-corner so
    the decode test sees venue-scaled, near-origin coords). This is deliberately a coarse stand-in —
    the real column extrusion / roof tilt / Karamba thicken is live-only. Serialized via rhino3dm's
    ``Encode`` (-> dict -> JSON -> base64), the inverse of ``decode.py``.
    """
    rhino3dm = _load_geom_sdk()
    minx, miny, maxx, maxy = footprint_poly.bounds
    # Origin-translate so the PREVIEW mesh is venue-scaled near the origin (matches decode discipline).
    w = maxx - minx
    h = maxy - miny
    mesh = rhino3dm.Mesh()
    # Footprint quad, flat at z=0, in metres (Z-up like Rhino).
    mesh.Vertices.Add(0.0, 0.0, 0.0)
    mesh.Vertices.Add(w, 0.0, 0.0)
    mesh.Vertices.Add(w, h, 0.0)
    mesh.Vertices.Add(0.0, h, 0.0)
    mesh.Faces.AddFace(0, 1, 2, 3)
    encoded = mesh.Encode()
    raw = json.dumps(encoded).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


# --------------------------------------------------------------------------- #
# Reference solve (drop-in for FakeRhinoClient): {gh_response, gh_meta}
# --------------------------------------------------------------------------- #
def build_reference(footprint: Any, flow_vectors: list[dict]) -> dict:
    """Produce a contract-valid PREVIEW ``gh_response`` plus a LABELLED ``gh_meta`` sidecar.

    The ``gh_response`` is a drop-in for the live solve / ``FakeRhinoClient`` (frozen,
    ``additionalProperties:false``): ``OUT_Mesh.b64`` (coarse PREVIEW mesh) +
    ``OUT_BOM {pillars, membrane_m2}`` (pillars = surviving grid points after the FAITHFUL flow-cull;
    membrane_m2 = footprint area). EVERY byte is PREVIEW/ASSUMED-grade — the provenance lives in the
    ``gh_meta`` SIDECAR, never in the frozen ``gh_response`` (Pitfall: no instructor fields in the
    frozen contract). The sidecar carries:

    * ``label`` = PREVIEW and the per-sub-capability provenance honesty table;
    * ``karamba`` named "live-only, pre-screening, requires engineering sign-off" (never "certified");
    * ``egress`` — the culled routes + the ``clearance_m`` buffer (instructor: export evacuation routes);
    * ``mass_balance`` — rented/recovered/new Material Recovery Inventory inputs (ASSUMED placeholders,
      labelled, for the Wave-3 EN 15804+A2 sidecar).

    Returns ``{"gh_response": {...}, "gh_meta": {...}}``.
    """
    footprint_poly = _footprint_polygon(footprint)

    # FAITHFUL: candidate lattice inside the footprint, then cull points on any flow route.
    candidates = _grid_points(footprint_poly)
    survivors = cull_grid(candidates, flow_vectors, buffer_m=FLOW_BUFFER_M)
    culled = [p for p in candidates if p not in set(survivors)]

    pillars = len(survivors)
    membrane_m2 = float(footprint_poly.area)

    mesh_b64 = _build_preview_mesh_b64(footprint_poly, survivors)

    gh_response = {
        "schema_version": _SCHEMA_VERSION,
        "OUT_Mesh": {"b64": mesh_b64},
        "OUT_BOM": {"pillars": pillars, "membrane_m2": membrane_m2},
    }

    gh_meta = {
        "label": PREVIEW_LABEL,  # every byte here is PREVIEW/ASSUMED-grade
        "provenance": {
            "flow_cull": "FAITHFUL (shapely) — GROUNDED-geometry",
            "grid_inside_footprint": "FAITHFUL (shapely) — GROUNDED-geometry",
            "columns_roof": f"{PREVIEW_LABEL} (boxes + flat plane) — APPROXIMATED",
            "bom": "DERIVED-preview (from the PREVIEW grid)",
        },
        "karamba": {
            "status": _KARAMBA_PROVENANCE,  # never "certified" / "engineer-approved" (GEOM-04)
            "simulated_offline": False,
        },
        "egress": {
            # Instructor: export the culled evacuation routes + their clearance for the sidecar.
            "clearance_m": FLOW_BUFFER_M,
            "culled_points": culled,
            "flow_vector_count": len(flow_vectors),
        },
        "mass_balance": {
            # Material Recovery Inventory inputs — ASSUMED-grade placeholders, labelled (instructor
            # EN 15804+A2 rented/recovered/new split). The Wave-3 carbon sidecar owns the real values.
            "label": "ASSUMED",
            "rented": {"scaffold_kg": 0.0, "note": "ASSUMED placeholder — rented structural mass"},
            "recovered": {"membrane_m2": 0.0, "note": "ASSUMED placeholder — recovered membrane area"},
            "new": {"fixings_kg": 0.0, "note": "ASSUMED placeholder — newly procured fixings mass"},
        },
    }

    return {"gh_response": gh_response, "gh_meta": gh_meta}


# --------------------------------------------------------------------------- #
# CLI bridge: python -m geom.reference_generator --input <req> --output <resp>
# --------------------------------------------------------------------------- #
def _reshape_request(gh_request: dict) -> tuple[Any, list[dict]]:
    """Reshape a ``gh_request`` JSON into the (footprint, flow_vectors) ``build_reference`` expects.

    Accepts the frozen ``gh_request`` IN_ field names (``IN_Footprint`` / ``IN_FlowVectors``) and also
    the loader shapes (``polygons`` / ``flow_vectors``) so it is robust to either source.
    """
    footprint = gh_request.get("IN_Footprint") or gh_request.get("footprint") or gh_request
    flow_vectors = (
        gh_request.get("IN_FlowVectors")
        or gh_request.get("flow_vectors")
        or []
    )
    return footprint, flow_vectors


def _write_atomic(path: Path, payload: dict) -> None:
    """Write JSON atomically (temp file in the same dir, then replace) so a partial write is impossible."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with open(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="geom.reference_generator",
        description="Build a PREVIEW (LABELLED) contract-valid gh_response from a gh_request.",
    )
    parser.add_argument("--input", required=True, help="path to the gh_request JSON")
    parser.add_argument("--output", required=True, help="path to write the gh_response JSON")
    args = parser.parse_args(argv)

    try:
        gh_request = json.loads(Path(args.input).read_text(encoding="utf-8"))
        footprint, flow_vectors = _reshape_request(gh_request)
        result = build_reference(footprint, flow_vectors)
        gh_response = result["gh_response"]
        # Defence-in-depth: re-validate the response we produced (Node ajv-validates again, WARNING 7).
        from validate.validate import validate  # noqa: PLC0415 (deferred — keeps import-time light)

        validate(gh_response, "gh_response")
        _write_atomic(Path(args.output), gh_response)  # frozen gh_response ONLY (no gh_meta sidecar)
    except Exception as exc:  # noqa: BLE001 — any failure maps to a non-zero exit for the Node bridge
        sys.stderr.write(f"reference_generator failed: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via the Node bridge / CLI test
    raise SystemExit(_main())
