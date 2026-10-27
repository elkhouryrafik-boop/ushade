"""Phase 6 — Strict Rendering Pipeline (ControlNet + FLUX.1).

Converts the Phase-4 Rhino/Grasshopper geometry into a marketable photorealistic
image WITHOUT ever letting the model alter the structural volumetrics. The lock is
``controlnet_conditioning_scale = 1.0`` (PRD Phase 6 / CLAUDE.md non-negotiable):
the render must match the Rhino geometry exactly.

Base model decision (2026-06-16, owner-approved — see PROJECT.md Key Decisions +
STACK.md): the diffusion base is **FLUX.1 (Depth/Canny ControlNet)**, NOT SDXL. The
binding requirement is the structure-lock contract, which is model-agnostic; FLUX.1
(Black Forest Labs) honors the identical contract with a generational quality jump.

Module layout (mirrors src/inventory's seam discipline):
  - ``preprocess`` — geometry .obj -> depth/canny ControlNet conditioning map (PIL,
    NO headless GL; deterministic + offline). This is the REAL map fed to ControlNet.
  - ``fal_client`` — the live FLUX.1 ControlNet network seam (fal.ai). LAZY-imports
    ``fal_client``; reads ``FAL_KEY`` from env, never logs it. Typed ``RenderError`` +
    ``LiveRenderBudget`` cap. The fake stand-in lives strictly under tests/ (Pitfall 8).
  - ``render`` — ``run_render_stage`` (cache-first, validate-then-write, fail-safe),
    cloning the climate/selection stage seam. Writes the conditioning map ALWAYS; writes
    a contract-valid ``render.json`` ONLY when a real render_url is produced (live key or
    injected client). With no key it degrades to a LABELLED pending sidecar — it NEVER
    fabricates a render_url (honesty non-negotiable; mirrors the climate live-deferred
    HUMAN-UAT pattern).
"""
