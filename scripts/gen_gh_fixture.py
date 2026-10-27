"""One-shot generator for the recorded, contract-valid ``gh_response`` fixture.

The default offline geom suite (FakeRhinoClient seam) needs a RECORDED ``gh_response``
whose ``OUT_Mesh.b64`` decodes (via rhino3dm) to a small-but-venue-scaled mesh, so the
Wave-3 decode + bbox-sanity tests exercise a TRUE path without a live Rhino.Compute call.

This script is the committed, deterministic source for ``tests/fixtures/gh_response/
valid_primavera.json``. It lazy-imports rhino3dm INSIDE the build function (mirror of the
``decode.py``/``reference_generator.py`` lazy-import discipline) so merely importing this
module — or running ``--help`` — does not require the ``geom`` extra. It builds a coarse
``GRID_SPACING_M`` box-grid quad mesh spanning the real ``primavera-demo`` footprint bbox
(translated to the origin, the Y-up metres frame a decoded venue mesh lives in), serialises
the mesh to its rhino3dm JSON archive, base64-encodes that, and writes the frozen-shape
``gh_response``.

Usage:
    python scripts/gen_gh_fixture.py            # (re)generate + write the fixture
    python scripts/gen_gh_fixture.py --check    # rebuild + assert contract-valid + venue-scaled,
                                                # but do NOT overwrite (CI gate)

No secret is read or written here (XFN-02): the fixture is pure geometry.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_FOOTPRINT = _REPO_ROOT / "projects" / "primavera-demo" / "footprint.json"
_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "gh_response" / "valid_primavera.json"

# Make src/ importable so `from geom.constants import ...` resolves under bare `python`.
sys.path.insert(0, str(_REPO_ROOT / "src"))

from geom.constants import BBOX_MAX_M, BBOX_MIN_M, GRID_SPACING_M  # noqa: E402


def _footprint_bbox() -> tuple[float, float, float, float]:
    """(min_x, min_y, span_x, span_y) over every vertex of the real demo footprint (m, EPSG:32631)."""
    data = json.loads(_FOOTPRINT.read_text(encoding="utf-8"))
    xs = [p["x_m"] for poly in data["polygons"] for p in poly]
    ys = [p["y_m"] for poly in data["polygons"] for p in poly]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def _build_mesh_b64() -> str:
    """Build a coarse origin-translated venue-scaled quad mesh and return its base64 archive.

    rhino3dm is LAZY-imported here so importing this module is geom-extra-free.
    """
    import rhino3dm  # lazy — only the live/generate path needs the geom extra

    _, _, span_x, span_y = _footprint_bbox()
    # Coarse box-grid over [0, span_x] x [0, span_y], one quad per GRID_SPACING_M cell.
    n_cols = max(1, int(span_x // GRID_SPACING_M))
    n_rows = max(1, int(span_y // GRID_SPACING_M))
    step_x = span_x / n_cols
    step_y = span_y / n_rows

    mesh = rhino3dm.Mesh()
    # (n_cols+1) x (n_rows+1) grid of vertices, Y-up metres, origin-translated.
    for r in range(n_rows + 1):
        for c in range(n_cols + 1):
            mesh.Vertices.Add(c * step_x, r * step_y, 0.0)
    width = n_cols + 1
    for r in range(n_rows):
        for c in range(n_cols):
            a = r * width + c
            b = a + 1
            d = a + width
            e = d + 1
            mesh.Faces.AddFace(a, b, e, d)

    archive = mesh.Encode()  # rhino3dm JSON archive dict
    raw = json.dumps(archive).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def build_gh_response() -> dict:
    """Assemble the frozen-shape ``gh_response`` over the recorded venue mesh."""
    b64 = _build_mesh_b64()
    _, _, span_x, span_y = _footprint_bbox()
    n_cols = max(1, int(span_x // GRID_SPACING_M))
    n_rows = max(1, int(span_y // GRID_SPACING_M))
    pillars = (n_cols + 1) * (n_rows + 1)
    # Coarse PREVIEW membrane area = the gridded venue footprint area (m^2). Demo-only.
    membrane_m2 = round(span_x * span_y, 3)
    return {
        "schema_version": "1.0.0",
        "OUT_Mesh": {"b64": b64},
        "OUT_BOM": {"pillars": int(pillars), "membrane_m2": float(membrane_m2)},
    }


def _assert_contract_valid_and_scaled(obj: dict) -> None:
    """Validate against the frozen gh_response schema and assert the mesh bbox is venue-scaled."""
    from validate.validate import validate

    validate(obj, "gh_response")

    import rhino3dm  # lazy

    archive = json.loads(base64.b64decode(obj["OUT_Mesh"]["b64"]))
    mesh = rhino3dm.CommonObject.Decode(archive)
    bb = mesh.GetBoundingBox()
    span_x = bb.Max.X - bb.Min.X
    span_y = bb.Max.Y - bb.Min.Y
    for axis, span in (("x", span_x), ("y", span_y)):
        if not (BBOX_MIN_M <= span <= BBOX_MAX_M):
            raise AssertionError(
                f"decoded mesh {axis}-span {span:.1f} m outside venue bounds "
                f"[{BBOX_MIN_M}, {BBOX_MAX_M}] m"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="rebuild + assert contract-valid + venue-scaled WITHOUT overwriting the fixture",
    )
    args = parser.parse_args(argv)

    obj = build_gh_response()
    _assert_contract_valid_and_scaled(obj)

    if args.check:
        # Confirm the committed fixture matches a fresh deterministic rebuild's contract +
        # scaling (the bytes themselves are not byte-pinned — rhino3dm archives carry a
        # version stamp — but the fixture on disk must independently pass the same gate).
        on_disk = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        _assert_contract_valid_and_scaled(on_disk)
        print("fixture contract-valid + venue-scaled (--check OK)")
        return 0

    _FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    _FIXTURE.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {_FIXTURE.relative_to(_REPO_ROOT)} "
          f"(pillars={obj['OUT_BOM']['pillars']}, membrane_m2={obj['OUT_BOM']['membrane_m2']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
