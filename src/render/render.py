"""The Phase-6 render stage — ``run_render_stage`` (cache-first, validate-then-write, fail-safe).

Pipeline (PRD Phase 6):
  1. ALWAYS generate the ControlNet conditioning map from the Phase-4 ``structure.obj``
     (depth or canny) — the real geometry lock (preprocess.py). Written every run.
  2. Assemble the dynamic prompt from Phase-1 theme + Phase-5 selected material (the
     instructor demand: recovered-textile materiality + scaffold couplers must be NAMED so
     the design appears in the render).
  3. If a render client is available (injected, or live ``FAL_KEY`` + opt-in), call FLUX.1
     Depth/Canny ControlNet at ``conditioning_scale = 1.0`` -> ``render_url`` -> build a
     contract-valid ``render.json`` (validate-then-write) -> provenance -> mark_done.
  4. With NO client/key: write a LABELLED pending sidecar (``render_meta.json``) carrying the
     conditioning-map path + assembled prompt, and DO NOT write ``render.json``. A render_url
     is NEVER fabricated (honesty non-negotiable; mirrors the climate live-deferred HUMAN-UAT
     pattern). The /api/artifacts/{id}/render endpoint keeps serving the labelled stub.

karpathy: clones the selection/climate stage seam exactly — one cache key, validate before
any byte hits disk, fail-safe leaves the stage NOT done with no partial artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

from manifest.manifest import Manifest, content_hash
from provenance.ledger import ProvenanceLedger
from validate.validate import validate

from render.fal_client import (
    CONDITIONING_SCALE_LOCKED,
    FalRenderClient,
    RenderError,
    live_render_enabled,
)
from render.preprocess import write_controlnet_input

_STAGE = "render"
_CONTRACT = "render"
_SCHEMA_VERSION = "1.0.0"
_ARTIFACT_NAME = "render.json"
_META_NAME = "render_meta.json"  # non-contract pending sidecar (never validate()-d)
_CONTROL_INPUT_NAME = "render_controlnet_input.png"
_PROMPT_NAME = "render_prompt.txt"
_OBJ_NAME = "structure.obj"

_DEFAULT_MODEL = "depth"
_DEFAULT_DENOISE = 0.75  # PRD denoising_strength (rich textures without changing shapes)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_MATERIALS_PATH = _REPO_ROOT / "data" / "materials.json"

# PRD Phase 6 negative prompt (MANDATORY) — geometry-distortion guardrail.
NEGATIVE_PROMPT = (
    "geometric distortions, extra pillars, floating elements, broken roof, "
    "cartoon, sketchy, low quality render"
)


def _material_name(selected_id: str | None) -> str:
    """Resolve a material id -> human name from the frozen 10 (best-effort, never crashes)."""
    if not selected_id:
        return "reclaimed local material"
    try:
        materials = json.loads(_MATERIALS_PATH.read_text(encoding="utf-8"))["materials"]
        for m in materials:
            if m.get("id") == selected_id:
                return m.get("name", selected_id)
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    return selected_id


def assemble_prompt(parsed_brief: dict | None, selection: dict | None) -> str:
    """Build the positive prompt from Phase-1 theme + Phase-5 material (PRD template + instructor).

    The instructor's hardest critique ("I cannot find your project in it") is answered by
    NAMING the recovered-textile materiality (patchwork seams, varied panels) + visible
    rented scaffold couplers + human scale — not a generic new-fabric canopy.
    """
    theme = (parsed_brief or {}).get("theme") or "natural"
    material = _material_name((selection or {}).get("selected_id"))
    return (
        "Architectural photography, aerial view, music festival crowd underneath. "
        f"Shade structure clad in {material}, {theme} design style. "
        "Recovered-textile membrane with patchwork seams and varied salvaged panels, "
        "rented scaffold nodes and couplers visible, human scale. "
        "Summer sky, cinematic lighting, 8k, hyperrealistic."
    )


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_manifest(project_id: str, project_root: Path) -> Manifest:
    """Load the persisted manifest if present, else a fresh one (mirror selection stage)."""
    manifest = Manifest(project_id, project_root)
    path = manifest.project_dir / "manifest.json"
    existing = _load_json(path)
    if existing:
        for st in existing.get("stages", []):
            name = st.get("name")
            if name in manifest._stages:  # noqa: SLF001 (same-package idiom as selection)
                manifest._stages[name].update(st)
        if existing.get("created_at"):
            manifest.created_at = existing["created_at"]
    return manifest


def run_render_stage(
    project_id: str,
    *,
    projects_root: Path | str | None = None,
    client=None,
    model: str = _DEFAULT_MODEL,
    denoising_strength: float = _DEFAULT_DENOISE,
) -> dict:
    """Run the render stage. Returns a status dict:

      - rendered=True  -> a contract-valid ``render.json`` was written (live/injected client).
      - rendered=False -> labelled pending; conditioning map + prompt written, NO render_url.

    Never raises for the no-key case (that is the normal demo path); raises only on a real
    internal error, leaving the stage NOT done with no partial ``render.json``.
    """
    project_root = Path(projects_root) if projects_root is not None else Path("projects")
    manifest = _load_manifest(project_id, project_root)
    project_dir = manifest.project_dir
    artifact_path = project_dir / _ARTIFACT_NAME
    obj_path = project_dir / _OBJ_NAME

    parsed_brief = _load_json(project_dir / "parsed_brief.json") or {}
    selection = _load_json(project_dir / "material_selection.json") or {}
    prompt = assemble_prompt(parsed_brief, selection)

    if not obj_path.exists():
        raise RenderError(f"no {_OBJ_NAME} for project {project_id!r} — run the geometry stage first")

    # Geometry content hash → a corrected structure is a cache MISS, never a stale render.
    geom_hash = content_hash(obj_path.read_text(encoding="utf-8"))
    input_hash = content_hash(
        {
            "geom": geom_hash,
            "selected_id": selection.get("selected_id"),
            "theme": parsed_brief.get("theme"),
            "model": model,
            "denoise": denoising_strength,
            "prompt": prompt,
        }
    )

    # ── 1) CACHE CHECK (only a real render.json is cacheable) ─────────────────
    if manifest.is_reusable(_STAGE, input_hash) and artifact_path.exists():
        cached = _load_json(artifact_path)
        if cached is not None:
            try:
                validate(cached, _CONTRACT)
                return {"rendered": True, "render": cached, "cached": True}
            except Exception:
                pass  # corrupt cache -> fall through and recompute

    # ── 2) COMPUTE ────────────────────────────────────────────────────────────
    try:
        # (a) ALWAYS write the ControlNet conditioning map + prompt — the real geometry lock.
        control_path = write_controlnet_input(
            obj_path, project_dir / _CONTROL_INPUT_NAME, model=model
        )
        (project_dir / _PROMPT_NAME).write_text(prompt, encoding="utf-8")

        # (b) Decide the render client: explicit inject > live opt-in > none (pending).
        render_client = client
        if render_client is None and live_render_enabled():
            render_client = FalRenderClient()

        if render_client is None:
            # No key / no client -> labelled pending. NEVER fabricate a render_url.
            meta = {
                "schema_version": "1.0.0-pending",
                "stage": _STAGE,
                "status": "pending_live",
                "model": model,
                "conditioning_scale": CONDITIONING_SCALE_LOCKED,
                "denoising_strength": denoising_strength,
                "controlnet_input": _CONTROL_INPUT_NAME,
                "prompt_ref": _PROMPT_NAME,
                "negative_prompt": NEGATIVE_PROMPT,
                "note": (
                    "ControlNet conditioning map generated; live FLUX.1 render pending a "
                    "fal.ai FAL_KEY (HEATGUARD_LIVE_RENDER). No image URL is fabricated — "
                    "the dashboard shows the labelled stub until a real render runs."
                ),
            }
            (project_dir / _META_NAME).write_text(json.dumps(meta, indent=2), encoding="utf-8")
            return {
                "rendered": False,
                "status": "pending_live",
                "controlnet_input": str(control_path),
                "prompt": prompt,
                "meta": meta,
            }

        # (c) Live/injected render -> real render_url.
        render_url = render_client.render(
            control_image_path=str(control_path),
            prompt=prompt,
            negative_prompt=NEGATIVE_PROMPT,
            model=model,
            conditioning_scale=CONDITIONING_SCALE_LOCKED,
            denoising_strength=denoising_strength,
        )

        artifact = {
            "schema_version": _SCHEMA_VERSION,
            "render_url": render_url,
            "conditioning_scale": CONDITIONING_SCALE_LOCKED,
            "denoising_strength": denoising_strength,
            "model": model,
            "prompt_ref": _PROMPT_NAME,
        }

        # ── 3) VALIDATE-THEN-WRITE ────────────────────────────────────────────
        validate(artifact, _CONTRACT)
        artifact_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

        # ── 4) PROVENANCE (render_url GROUNDED from fal; the lock is an ASSUMED convention) ──
        ledger = ProvenanceLedger()
        ledger.grounded(
            "render_url",
            render_url,
            "fal.ai FLUX.1 ControlNet render output (Phase 6)",
            _STAGE,
        )
        ledger.assumed(
            "conditioning_scale",
            CONDITIONING_SCALE_LOCKED,
            "PRD lock — absolute structural compliance (render matches Rhino geometry)",
            _STAGE,
        )
        ledger.write(project_dir / "render_ledger.json")

        # ── 5) mark_done ──────────────────────────────────────────────────────
        output_hash = content_hash(artifact)
        manifest.mark_done(_STAGE, _ARTIFACT_NAME, input_hash, output_hash)
        manifest.write()
        return {"rendered": True, "render": artifact, "cached": False}

    except Exception:
        # Fail-safe: leave the stage NOT done, write no partial render.json (mirror selection).
        if hasattr(manifest, "mark_failed"):
            try:
                manifest.mark_failed(_STAGE)
                manifest.write()
            except Exception:
                pass
        raise
