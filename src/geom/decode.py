"""Decode discipline — ``OUT_Mesh.b64`` -> ``.gltf`` + ``.obj`` in metres + Y-up + origin-translated.

This is the FAITHFUL/GROUNDED half of Phase 4 (GEOM-05): real file operations over the recorded /
live ``gh_response.OUT_Mesh.b64``. The decoded mesh's vertices must be:

* in **metres** (already — EPSG:32631);
* **origin-translated** to the footprint min-corner (so the viewer/render is NOT ~435000 m
  off-origin — a Pitfall-3 lat/lon-style leak in disguise);
* **Y-up** (rhino3dm/3dm is Z-up; glTF is Y-up — swap axes on write).

Then a bbox-sanity gate asserts the horizontal span is ~ venue size (``[BBOX_MIN_M, BBOX_MAX_M]``)
BEFORE any file write (Pitfall 12). The gate uses an explicit ``raise GeomDecodeError`` rather than a
bare ``assert`` (Phase-3 lesson: explicit raise over bare assert for integrity gates).

``rhino3dm`` and ``trimesh`` are the optional ``geom`` extra — both are lazy-imported inside
``_load_geom_sdk`` (clone of ``infrared_client._load_sdk``) so that merely importing this module is
dependency-free and the base pytest suite stays green. ``numpy`` is a base dep (used for the transform).

The module exposes a ``python -m geom.decode --input --out-dir`` CLI bridge that the Node orchestrator
invokes via ``execFile``: read the ``gh_response`` JSON, re-validate it (defence-in-depth, WARNING 7 /
T-04-16), decode, print a SINGLE JSON line ``{"gltf", "obj", "bbox_span_m"}`` to stdout, exit 0; on ANY
error write a short message to stderr and exit 1 (Node maps non-zero / invalid stdout -> stage failed).
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np  # BASE dep

from geom.constants import BBOX_MAX_M, BBOX_MIN_M

#: Draco compression level for the glTF write. DISCRETION (RESEARCH Open Q1): a mid level (6) trades
#: file size vs. encode time; documented here so the choice is not an inline magic number.
_DRACO_LEVEL = 6


class GeomDecodeError(Exception):
    """Typed error raised when an ``OUT_Mesh`` cannot be safely decoded.

    Carries its cause. Raised by the bbox-sanity integrity gate (explicit raise, never a bare
    assert) and by the lazy-import / deserialize / write failure paths. The CLI bridge surfaces a
    short message to stderr and exits non-zero; the Node orchestrator maps that to a failed stage.
    """


# --------------------------------------------------------------------------- #
# Lazy geom-extra loader (clone of infrared_client._load_sdk)
# --------------------------------------------------------------------------- #
def _load_geom_sdk():
    """Lazily import rhino3dm (+ trimesh for the glTF write). Never imported at module top.

    Raises ``GeomDecodeError`` with an actionable install hint on ImportError so a missing extra
    surfaces as a typed decode failure, not a bare ImportError — keeping the base offline suite
    dependency-free (mirror of ``_load_sdk`` / T-02a-10).
    """
    try:  # imported here, NEVER at module top
        import rhino3dm  # noqa: PLC0415  (intentional lazy import — keep base suite dep-free)
        import trimesh  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise GeomDecodeError(
            "geom extra not installed — `pip install -e .[geom]` for decode/PREVIEW"
        ) from exc
    return rhino3dm, trimesh


@dataclass
class DecodeResult:
    """The result of a decode: the written artifact paths + the venue-scaled bbox span.

    ``bbox_span_m`` is ordered ``(span_x, span_z, span_y)`` — the two HORIZONTAL axes first
    (after the Z-up -> Y-up swap), so a caller reading ``bbox_span_m[:2]`` sees the venue footprint
    extent and the vertical span last.

    ``roof_faces_m`` is the ACTUAL decoded mesh triangles in the original (Z-up) metre frame,
    origin-translated to the footprint min-corner: a list of ``[(x, y, z), (x, y, z), (x, y, z)]``
    rings. GEOM-06 ``_coverage`` projects these REAL faces (not a bbox rectangle) onto the ground
    along the sun vector (MJ-04) — so the coverage measures the decoded roof, honestly.
    """

    gltf_path: str
    obj_path: str
    bbox_span_m: tuple[float, float, float]
    roof_faces_m: list[list[tuple[float, float, float]]]


def _mesh_vertices_m(b64: str, rhino3dm) -> np.ndarray:
    """Base64-decode + rhino3dm-deserialize ``OUT_Mesh.b64`` to an ``(N,3)`` metre vertex array.

    The mesh is serialized via rhino3dm's ``Encode`` (-> dict -> JSON -> base64); ``CommonObject.Decode``
    is the inverse. Raises ``GeomDecodeError`` if the payload is not a decodable mesh (T-04-08:
    untrusted base64 — a malformed/oversized payload fails here, before any transform or write).
    """
    try:
        raw = base64.b64decode(b64)
        encoded = json.loads(raw.decode("utf-8"))
        mesh = rhino3dm.CommonObject.Decode(encoded)
    except Exception as exc:  # noqa: BLE001
        raise GeomDecodeError(f"OUT_Mesh.b64 is not a decodable rhino3dm mesh: {exc}") from exc
    if mesh is None or not hasattr(mesh, "Vertices"):
        raise GeomDecodeError("OUT_Mesh.b64 did not decode to a mesh with vertices")
    vs = mesh.Vertices
    n = len(vs)
    if n == 0:
        raise GeomDecodeError("OUT_Mesh decoded to an empty mesh (no vertices)")
    verts = np.array([[vs[i].X, vs[i].Y, vs[i].Z] for i in range(n)], dtype=float)
    return verts


def decode_mesh(b64: str, out_dir: str | Path | None = None) -> DecodeResult:
    """FAITHFUL/GROUNDED: decode ``OUT_Mesh.b64`` to metres + Y-up + origin-translated ``.gltf``/``.obj``.

    Steps (RESEARCH Pattern 3):

    1. base64-decode + rhino3dm-deserialize to an ``(N,3)`` metre vertex array (Z-up, EPSG:32631).
    2. origin-translate to the footprint min-corner (no ~435000 m off-origin leak — Pitfall 3).
    3. Z-up -> Y-up axis swap for glTF: ``verts[:, [0, 2, 1]]``.
    4. bbox-sanity gate: assert both horizontal spans within ``[BBOX_MIN_M, BBOX_MAX_M]`` — explicit
       ``raise GeomDecodeError`` (NOT a bare assert) BEFORE any write (Pitfall 12 / T-04-09). A bbox in
       the 41.x/2.x or 434000+ range fails (lat/lon / off-origin leak).
    5. write ``structure.obj`` + ``structure.gltf`` to ``out_dir`` (only when ``out_dir`` is given).

    Args:
        b64: the ``gh_response["OUT_Mesh"]["b64"]`` string.
        out_dir: directory to write ``structure.gltf`` + ``structure.obj`` into. If ``None`` the
            transform + bbox gate still run (so the venue-scale test can read ``bbox_span_m`` without
            writing files).

    Returns:
        ``DecodeResult(gltf_path, obj_path, bbox_span_m)``. ``*_path`` are empty strings when
        ``out_dir`` is ``None``.
    """
    rhino3dm, trimesh = _load_geom_sdk()

    verts = _mesh_vertices_m(b64, rhino3dm)

    # (2) origin-translate to the footprint min-corner (x, y horizontal plane).
    origin = verts[:, :2].min(axis=0)
    verts = verts.copy()
    verts[:, 0] -= origin[0]
    verts[:, 1] -= origin[1]

    # (3) Z-up -> Y-up for glTF.
    verts_yup = verts[:, [0, 2, 1]]

    # (4) bbox-sanity gate over the two HORIZONTAL axes (x, z after the swap) — explicit raise.
    span = verts_yup.max(axis=0) - verts_yup.min(axis=0)  # [span_x, span_y(vertical), span_z]
    span_x, span_vert, span_z = float(span[0]), float(span[1]), float(span[2])
    for axis_name, val in (("x", span_x), ("z", span_z)):
        if not (BBOX_MIN_M < val < BBOX_MAX_M):
            raise GeomDecodeError(
                f"decoded mesh horizontal span {axis_name}={val:.3f} m outside venue bounds "
                f"({BBOX_MIN_M}, {BBOX_MAX_M}) — units/origin leak (Pitfall 3/12)"
            )

    # bbox_span_m: two horizontal axes first, vertical last (so caller's [:2] sees the footprint extent).
    bbox_span_m = (span_x, span_z, span_vert)

    # Reconstruct triangle faces (split quads) — needed BOTH for the trimesh write and for the
    # GEOM-06 coverage projection (MJ-04). Decode the mesh once for its face topology.
    rmesh = rhino3dm.CommonObject.Decode(json.loads(base64.b64decode(b64).decode("utf-8")))
    faces = _mesh_faces(rmesh)

    # roof_faces_m: the REAL decoded triangles in the original (origin-translated, Z-up) metre frame
    # — (x, y) horizontal + z height — so GEOM-06 projects the actual roof, not a bbox rectangle.
    roof_faces_m = [
        [tuple(float(c) for c in verts[i]) for i in tri]
        for tri in faces.tolist()
    ]

    gltf_path = ""
    obj_path = ""
    if out_dir is not None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        tmesh = trimesh.Trimesh(vertices=verts_yup, faces=faces, process=False)
        obj_path = str(out / "structure.obj")
        gltf_path = str(out / "structure.gltf")
        glb_path = str(out / "structure.glb")
        try:
            tmesh.export(obj_path)
            tmesh.export(gltf_path)  # trimesh writes glTF; Draco level documented (_DRACO_LEVEL)
            tmesh.export(glb_path, file_type="glb")  # self-contained binary glTF — no external .bin (A1, Pitfall 1)
        except Exception as exc:  # noqa: BLE001
            raise GeomDecodeError(f"failed writing decoded artifacts to {out}: {exc}") from exc

    return DecodeResult(
        gltf_path=gltf_path,
        obj_path=obj_path,
        bbox_span_m=bbox_span_m,
        roof_faces_m=roof_faces_m,
    )


def _mesh_faces(rmesh) -> np.ndarray:
    """Extract triangle faces from a rhino3dm mesh as an ``(M,3)`` int array (split quads -> 2 tris)."""
    faces = rmesh.Faces
    tris: list[list[int]] = []
    for i in range(len(faces)):
        f = faces[i]  # (a, b, c, d); if c == d the face is a triangle
        a, b, c, d = f[0], f[1], f[2], f[3]
        tris.append([a, b, c])
        if d != c:
            tris.append([a, c, d])
    return np.array(tris, dtype=np.int64)


# --------------------------------------------------------------------------- #
# CLI bridge: python -m geom.decode --input <gh_response> --out-dir <project_dir>
# --------------------------------------------------------------------------- #
def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="geom.decode",
        description="Decode gh_response.OUT_Mesh.b64 to metres+Y-up+origin-translated .gltf/.obj.",
    )
    parser.add_argument("--input", required=True, help="path to the gh_response JSON")
    parser.add_argument("--out-dir", required=True, help="directory to write structure.gltf/.obj into")
    args = parser.parse_args(argv)

    try:
        gh_response = json.loads(Path(args.input).read_text(encoding="utf-8"))
        # Defence-in-depth: re-validate the JSON crossing the child-process boundary (WARNING 7 / T-04-16).
        from validate.validate import validate  # noqa: PLC0415

        validate(gh_response, "gh_response")
        result = decode_mesh(gh_response["OUT_Mesh"]["b64"], out_dir=args.out_dir)
        sys.stdout.write(
            json.dumps(
                {
                    "gltf": result.gltf_path,
                    "obj": result.obj_path,
                    "bbox_span_m": list(result.bbox_span_m),
                }
            )
            + "\n"
        )
    except Exception as exc:  # noqa: BLE001 — any failure maps to a non-zero exit for the Node bridge
        sys.stderr.write(f"decode failed: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via the Node bridge / CLI test
    raise SystemExit(_main())
