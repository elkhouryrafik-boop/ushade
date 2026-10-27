"""Phase-6 render pipeline tests (RENDER-01..06) — fully offline.

The network seam (fal.ai FLUX.1 ControlNet) is faked; the conditioning-map preprocessor
(PIL, no GL) runs for real. The load-bearing honesty assertions:
  1. conditioning_scale is LOCKED to 1.0 in any written render.json (geometry compliance).
  2. with no key/client the stage is LABELLED pending and NEVER fabricates a render_url.
  3. the conditioning map is deterministic (the cache key depends on it).
  4. the prompt NAMES the recovered-textile materiality + scaffold (instructor demand).

These run in the base offline suite (Pillow is base; fal SDK is never imported).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from render.fal_client import CONDITIONING_SCALE_LOCKED, RenderError
from render.preprocess import conditioning_map, load_obj, write_controlnet_input
from render.render import NEGATIVE_PROMPT, assemble_prompt, run_render_stage

# A simple flat roof quad (mirrors the GH structure.obj export: XZ plane, height along Y).
_OBJ = """# test geometry
v 0.0 0.0 0.0
v 588.0 0.0 0.0
v 588.0 0.0 768.0
v 0.0 0.0 768.0
f 1 2 3
f 1 3 4
"""

_BRIEF = {"schema_version": "1.0.0", "capacity": 65000, "budget": 150000,
          "date": "2026-06-14", "theme": "maritime"}
_SELECTION = {"schema_version": "1.1.0", "selected_id": "membr-pe-yacht-shrinkwrap",
              "is_membrane": True, "selection_basis": "transport_carbon_min"}


class FakeRenderClient:
    """Offline stand-in for FalRenderClient — records calls, returns a deterministic url."""

    def __init__(self, url: str = "https://fal.test/render/demo.png"):
        self.url = url
        self.calls: list[dict] = []

    def render(self, *, control_image_path, prompt, negative_prompt, model,
               conditioning_scale, denoising_strength) -> str:
        self.calls.append({
            "control_image_path": control_image_path, "prompt": prompt,
            "negative_prompt": negative_prompt, "model": model,
            "conditioning_scale": conditioning_scale, "denoising_strength": denoising_strength,
        })
        return self.url


def _project(tmp_path: Path, *, obj: str = _OBJ) -> tuple[str, Path]:
    """Create a tmp project dir with the render-stage inputs; return (project_id, root)."""
    root = tmp_path / "projects"
    pdir = root / "demo"
    pdir.mkdir(parents=True)
    (pdir / "structure.obj").write_text(obj, encoding="utf-8")
    (pdir / "parsed_brief.json").write_text(json.dumps(_BRIEF), encoding="utf-8")
    (pdir / "material_selection.json").write_text(json.dumps(_SELECTION), encoding="utf-8")
    return "demo", root


# --------------------------------------------------------------------------- #
# Preprocess — OBJ parse + deterministic conditioning map
# --------------------------------------------------------------------------- #
def test_load_obj_parses_geometry(tmp_path):
    obj_path = tmp_path / "s.obj"
    obj_path.write_text(_OBJ, encoding="utf-8")
    verts, faces = load_obj(obj_path)
    assert verts.shape == (4, 3)
    assert faces == [(0, 1, 2), (0, 2, 3)]


def test_conditioning_map_is_nontrivial_and_deterministic(tmp_path):
    """Depth map has both black bg and lit structure, and re-renders byte-identical."""
    obj_path = tmp_path / "s.obj"
    obj_path.write_text(_OBJ, encoding="utf-8")
    a = write_controlnet_input(obj_path, tmp_path / "a.png", model="depth")
    b = write_controlnet_input(obj_path, tmp_path / "b.png", model="depth")
    bytes_a = Path(a).read_bytes()
    assert bytes_a == Path(b).read_bytes(), "conditioning map must be deterministic"
    # The image must contain background (0) AND structure (>0) — not an empty/black frame.
    verts, faces = load_obj(obj_path)
    img = conditioning_map(verts, faces, model="depth")
    px = set(img.getdata())
    assert 0 in px and any(p > 0 for p in px), "map must show structure on a black bg"


def test_depth_and_canny_differ(tmp_path):
    obj_path = tmp_path / "s.obj"
    obj_path.write_text(_OBJ, encoding="utf-8")
    verts, faces = load_obj(obj_path)
    depth = list(conditioning_map(verts, faces, model="depth").getdata())
    canny = list(conditioning_map(verts, faces, model="canny").getdata())
    assert depth != canny, "depth (filled) and canny (outline) must differ"


# --------------------------------------------------------------------------- #
# Prompt assembly (instructor: the design must appear in the render)
# --------------------------------------------------------------------------- #
def test_prompt_carries_material_theme_and_recovered_textile():
    prompt = assemble_prompt(_BRIEF, _SELECTION)
    assert "maritime" in prompt
    assert "PE Yacht" in prompt or "yacht" in prompt.lower() or "shrinkwrap" in prompt.lower()
    assert "patchwork" in prompt.lower() and "scaffold" in prompt.lower()


def test_negative_prompt_has_mandatory_guardrails():
    for term in ("geometric distortions", "extra pillars", "floating elements", "broken roof"):
        assert term in NEGATIVE_PROMPT


# --------------------------------------------------------------------------- #
# Stage — live/injected client writes a contract-valid render.json
# --------------------------------------------------------------------------- #
def test_run_render_stage_with_client_writes_contract_render(tmp_path):
    project_id, root = _project(tmp_path)
    client = FakeRenderClient()
    result = run_render_stage(project_id, projects_root=root, client=client, model="depth")

    assert result["rendered"] is True
    render = result["render"]
    # Contract-valid + conditioning_scale LOCKED.
    from validate.validate import validate
    validate(render, "render")
    assert render["conditioning_scale"] == CONDITIONING_SCALE_LOCKED == 1.0
    assert render["render_url"] == client.url
    assert render["model"] == "depth"

    pdir = root / project_id
    assert (pdir / "render.json").exists()
    assert (pdir / "render_controlnet_input.png").exists()
    # render_url is GROUNDED in the ledger.
    ledger = json.loads((pdir / "render_ledger.json").read_text(encoding="utf-8"))
    grounded = {e["key"]: e["tier"] for e in ledger["entries"]}
    assert grounded.get("render_url") == "GROUNDED"
    # The manifest render stage is done.
    manifest = json.loads((pdir / "manifest.json").read_text(encoding="utf-8"))
    render_stage = next(s for s in manifest["stages"] if s["name"] == "render")
    assert render_stage["status"] == "done"


# --------------------------------------------------------------------------- #
# Stage — no key/client -> labelled pending, NEVER a fabricated render_url
# --------------------------------------------------------------------------- #
def test_run_render_stage_no_client_is_pending_never_fabricates(tmp_path):
    project_id, root = _project(tmp_path)
    result = run_render_stage(project_id, projects_root=root, client=None)

    assert result["rendered"] is False
    assert result["status"] == "pending_live"
    pdir = root / project_id
    # NO contract render.json (the endpoint keeps serving the labelled stub).
    assert not (pdir / "render.json").exists()
    # The conditioning map + prompt + labelled meta DO exist.
    assert (pdir / "render_controlnet_input.png").exists()
    assert (pdir / "render_prompt.txt").exists()
    meta = json.loads((pdir / "render_meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "pending_live"
    assert meta["conditioning_scale"] == 1.0
    # Honesty: no render_url KEY and no fabricated http(s) image url in the pending sidecar.
    assert "render_url" not in meta
    assert "http://" not in json.dumps(meta) and "https://" not in json.dumps(meta)


def test_cache_hit_skips_second_render(tmp_path):
    project_id, root = _project(tmp_path)
    client = FakeRenderClient()
    run_render_stage(project_id, projects_root=root, client=client)
    assert len(client.calls) == 1
    second = run_render_stage(project_id, projects_root=root, client=client)
    assert second.get("cached") is True
    assert len(client.calls) == 1, "a cache hit must not re-dispatch the render"


# --------------------------------------------------------------------------- #
# The conditioning_scale lock is enforced in the client, before any SDK/key use
# --------------------------------------------------------------------------- #
def test_fal_client_rejects_non_unit_conditioning_scale():
    from render.fal_client import FalRenderClient
    with pytest.raises(RenderError, match="conditioning_scale must be 1.0"):
        FalRenderClient().render(
            control_image_path="x.png", prompt="p", negative_prompt="n",
            model="depth", conditioning_scale=0.8, denoising_strength=0.75,
        )
