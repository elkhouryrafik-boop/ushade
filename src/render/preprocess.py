"""Geometry preprocessing — Phase-4 ``.obj`` -> depth/canny ControlNet conditioning map.

PRD Phase 6 step 1-2: position a virtual camera at a 45° isometric bird's-eye view and
render the structure against a solid black background to produce a Depth Map (or a Canny
Edge Map). That map is what locks down the physical geometry boundaries for ControlNet.

This module does it with **PIL + numpy only — NO headless GL** (pyrender/OSMesa/EGL are a
genuine portability hazard on Windows). An orthographic isometric projection + painter's
rasterization is exact enough for the flat roof footprint the GH stage emits, and is fully
deterministic + offline (a re-run produces byte-identical pixels — the determinism the
``render`` cache key relies on). If a later GH stage emits a richer mesh, the same projector
renders it; only the camera constants would be revisited.

karpathy: a tiny OBJ vertex/face reader + one projection matrix + one rasterizer — no scene
graph, no material system. The map is geometry, not aesthetics; aesthetics is FLUX's job.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

# 45° azimuth, true-isometric elevation (atan(1/sqrt(2)) ≈ 35.264°) — PRD "45° isometric
# bird's-eye". Up axis is +Y (the GH .obj lays the roof in the XZ plane, height along Y).
_AZIMUTH_DEG = 45.0
_ELEVATION_DEG = math.degrees(math.atan(1.0 / math.sqrt(2.0)))

# Conditioning-map canvas. 768x512 landscape — a stable aspect for the aerial hero.
_DEFAULT_SIZE = (768, 512)
_MARGIN_PX = 24

# ControlNet conditioning types we emit (matches contracts/render.schema.json `model` enum).
MODELS = ("depth", "canny")


# --------------------------------------------------------------------------- #
# Minimal OBJ reader (v / f only — the GH export is triangulated, no normals/uv)
# --------------------------------------------------------------------------- #
def load_obj(path: Path | str) -> tuple[np.ndarray, list[tuple[int, ...]]]:
    """Read an ``.obj`` into ``(vertices Nx3 float array, faces list of 0-based index tuples)``.

    Supports ``v x y z`` and ``f a b c [...]`` (negative/relative indices and the
    ``v/vt/vn`` slash form are normalized). Comments/blank lines are skipped. Raises
    ``ValueError`` if no geometry is found (never returns an empty silhouette silently).
    """
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    text = Path(path).read_text(encoding="utf-8")
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "v" and len(parts) >= 4:
            verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif parts[0] == "f" and len(parts) >= 4:
            idx: list[int] = []
            for tok in parts[1:]:
                raw = tok.split("/", 1)[0]
                i = int(raw)
                # OBJ is 1-based; negative indices count back from the end.
                idx.append(i - 1 if i > 0 else len(verts) + i)
            faces.append(tuple(idx))
    if not verts or not faces:
        raise ValueError(f"no geometry parsed from {path!r} (need at least one v + one f)")
    return np.asarray(verts, dtype=float), faces


# --------------------------------------------------------------------------- #
# Isometric projection (orthographic; up = +Y)
# --------------------------------------------------------------------------- #
def _rotation() -> np.ndarray:
    """Rotate world so the camera looks along -Z' from a 45° iso bird's-eye."""
    az = math.radians(_AZIMUTH_DEG)
    el = math.radians(_ELEVATION_DEG)
    ca, sa = math.cos(az), math.sin(az)
    ce, se = math.cos(el), math.sin(el)
    ry = np.array([[ca, 0.0, sa], [0.0, 1.0, 0.0], [-sa, 0.0, ca]])  # azimuth about up(Y)
    rx = np.array([[1.0, 0.0, 0.0], [0.0, ce, -se], [0.0, se, ce]])  # tilt down about X'
    return rx @ ry


def project(verts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Project Nx3 world verts -> (Nx2 screen coords, N depth array).

    Screen coords are raw (un-fitted) units; ``depth`` is the camera-axis coordinate
    (LARGER = nearer the camera, after negating Z' so near→high). The rasterizer fits
    screen coords into the pixel canvas.
    """
    rot = _rotation()
    cam = verts @ rot.T
    screen = cam[:, :2].copy()
    depth = -cam[:, 2]  # negate so nearer (smaller Z') maps to a LARGER depth value
    return screen, depth


def _fit_to_canvas(screen: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Scale+translate screen coords to fit the canvas with a margin; flip Y to image space."""
    w, h = size
    mins = screen.min(axis=0)
    maxs = screen.max(axis=0)
    span = np.maximum(maxs - mins, 1e-9)
    scale = min((w - 2 * _MARGIN_PX) / span[0], (h - 2 * _MARGIN_PX) / span[1])
    # Centre the projected bbox in the canvas.
    offset = np.array([w, h]) / 2.0 - (mins + maxs) / 2.0 * scale
    px = screen * scale + offset
    px[:, 1] = h - px[:, 1]  # image Y grows downward
    return px


# --------------------------------------------------------------------------- #
# Rasterizers — depth (painter's, grayscale by depth) and canny (edge outline)
# --------------------------------------------------------------------------- #
def conditioning_map(
    verts: np.ndarray,
    faces: list[tuple[int, ...]],
    *,
    model: str = "depth",
    size: tuple[int, int] = _DEFAULT_SIZE,
):
    """Render the geometry to a ``PIL.Image`` ControlNet conditioning map on a black bg.

    ``model="depth"`` — faces filled grayscale by mean depth (near→white, far→dark grey),
    painter-sorted far→near so nearer faces overwrite. ``model="canny"`` — white face
    edges on black (the structural outline). Both lock the geometry boundary; FLUX must
    respect them at ``conditioning_scale = 1.0``.
    """
    if model not in MODELS:
        raise ValueError(f"unknown model {model!r}; expected one of {MODELS}")
    from PIL import Image, ImageDraw  # noqa: PLC0415  (lazy — keeps offline import light)

    screen, depth = project(verts)
    px = _fit_to_canvas(screen, size)

    img = Image.new("L", size, color=0)  # solid black background (PRD)
    draw = ImageDraw.Draw(img)

    # Per-face mean depth, normalized to [0,1] across the model.
    face_depth = np.array([float(depth[list(f)].mean()) for f in faces])
    lo, hi = float(face_depth.min()), float(face_depth.max())
    drange = max(hi - lo, 1e-9)

    if model == "depth":
        order = np.argsort(face_depth)  # far (small) -> near (large): painter's order
        for fi in order:
            f = faces[fi]
            poly = [tuple(px[i]) for i in f]
            # Map depth to [60, 255] so the structure is clearly above the black bg.
            shade = int(round(60 + 195 * (face_depth[fi] - lo) / drange))
            draw.polygon(poly, fill=shade)
    else:  # canny — outline only
        for f in faces:
            poly = [tuple(px[i]) for i in f]
            draw.line(poly + [poly[0]], fill=255, width=2)

    return img


def write_controlnet_input(
    obj_path: Path | str,
    out_path: Path | str,
    *,
    model: str = "depth",
    size: tuple[int, int] = _DEFAULT_SIZE,
) -> Path:
    """Load ``obj_path``, render its ``model`` conditioning map, save PNG to ``out_path``.

    Deterministic: same .obj + same model -> byte-identical PNG (the ``render`` cache and
    the determinism test depend on this). Returns the output ``Path``.
    """
    verts, faces = load_obj(obj_path)
    img = conditioning_map(verts, faces, model=model, size=size)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, format="PNG")
    return out
