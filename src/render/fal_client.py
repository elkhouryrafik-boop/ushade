"""Live render seam — FLUX.1 Depth/Canny ControlNet via fal.ai.

Mirrors src/inventory's network-seam discipline (``InventoryFetchError`` + ``LiveFetchBudget``
+ lazy import). This is the ONLY run-path render client; the fake stand-in lives strictly
under tests/ (Pitfall 8). The offline suite NEVER touches the network — it injects a fake
client; a real render runs only with ``FAL_KEY`` set + ``HEATGUARD_LIVE_RENDER`` opt-in.

NON-NEGOTIABLES enforced here:
  - ``conditioning_scale = 1.0`` is a const lock (PRD; contracts/render.schema.json) — the
    caller passes it but a value != 1.0 is REJECTED here, so the geometry-compliance lock
    cannot be loosened by a typo.
  - ``FAL_KEY`` is read from env and NEVER logged / echoed (XFN-02 secrets discipline).
  - Base model is FLUX.1 (owner-approved 2026-06-16), NOT SDXL — the model ids below are the
    fal.ai FLUX ControlNet endpoints.
"""

from __future__ import annotations

import os

FAL_ENV = "FAL_KEY"
LIVE_RENDER_ENV = "HEATGUARD_LIVE_RENDER"
LIVE_RENDER_CAP = 3  # backstop against a render-call DoS (mirror LiveFetchBudget)

CONDITIONING_SCALE_LOCKED = 1.0  # PRD controlnet_conditioning_scale — absolute compliance.

# fal.ai FLUX.1 Control LoRA endpoints (TEXT-TO-IMAGE), keyed by conditioning type. FLUX,
# not SDXL (2026-06-16 base-model decision). Text-to-image (not img2img) so the prompt
# generates fresh material/lighting while the depth/canny map LOCKS the structure — the
# img2img variant takes the control map as its own init and just reproduces it. Verified
# against the fal API schema 2026-06-16.
_FAL_MODEL_ENDPOINTS = {
    "depth": "fal-ai/flux-control-lora-depth",
    "canny": "fal-ai/flux-control-lora-canny",
}


class RenderError(RuntimeError):
    """Typed wrapper for any render-seam failure.

    ``run_render_stage`` catches this to DEGRADE to a labelled pending render — never a
    fabricated render_url. Carries the original error as ``cause``.
    """

    def __init__(self, message: str, *, cause: BaseException | None = None):
        super().__init__(message)
        self.cause = cause


class LiveRenderBudget:
    """Counts LIVE render dispatches and raises past the cap (render-DoS backstop)."""

    def __init__(self, cap: int = LIVE_RENDER_CAP):
        self.cap = cap
        self.n = 0

    def record(self, label: str) -> None:
        self.n += 1
        if self.n > self.cap:
            raise RenderError(f"live-render cap {self.cap} exceeded at {label}")


class FalRenderClient:
    """Default LIVE render client: FLUX.1 Depth/Canny ControlNet on fal.ai.

    Lazy-imports ``fal_client`` inside ``render`` (NEVER at module top) so the offline suite
    imports ``render.*`` with no SDK installed. Returns the public ``render_url`` string, or
    raises ``RenderError``. The conditioning map is uploaded then passed as the ControlNet
    ``control_image_url`` so the geometry is locked.
    """

    def __init__(self, *, budget: LiveRenderBudget | None = None):
        self.budget = budget or LiveRenderBudget()

    def render(
        self,
        *,
        control_image_path: str,
        prompt: str,
        negative_prompt: str,
        model: str,
        conditioning_scale: float,
        denoising_strength: float,
    ) -> str:
        if model not in _FAL_MODEL_ENDPOINTS:
            raise RenderError(f"unknown ControlNet model {model!r}")
        # The lock is enforced here, not just trusted from the caller.
        if conditioning_scale != CONDITIONING_SCALE_LOCKED:
            raise RenderError(
                f"conditioning_scale must be {CONDITIONING_SCALE_LOCKED} (PRD lock); "
                f"got {conditioning_scale}"
            )
        key = os.environ.get(FAL_ENV)
        if not key:
            raise RenderError(f"{FAL_ENV} not set — live render unavailable")

        self.budget.record(model)
        try:
            import fal_client  # noqa: PLC0415  (lazy — offline suite never imports the SDK)

            # fal_client reads FAL_KEY from env itself; we never pass/log the secret.
            # The conditioning map is BOTH the img2img base and the control-lora image, so
            # the geometry locks the structure while the prompt drives material/lighting.
            # control_lora_strength = conditioning_scale (1.0) = absolute structural compliance.
            # FLUX has no negative-prompt input; negative_prompt is recorded in the prompt_ref
            # file for the audit trail but not sent to the model.
            control_url = fal_client.upload_file(control_image_path)
            arguments = {
                "prompt": prompt,
                "control_lora_image_url": control_url,
                "control_lora_strength": conditioning_scale,
                "guidance_scale": 3.5,
                "num_inference_steps": 28,
                "image_size": {"width": 768, "height": 512},
            }
            if model == "depth":
                # Our image ALREADY IS the depth map — do NOT let fal re-extract depth from
                # it (preprocess_depth defaults true). Pass it through as the control signal.
                arguments["preprocess_depth"] = False
            result = fal_client.subscribe(_FAL_MODEL_ENDPOINTS[model], arguments=arguments)
            images = (result or {}).get("images") or []
            if not images or not images[0].get("url"):
                raise RenderError("fal.ai returned no image url")
            return str(images[0]["url"])
        except RenderError:
            raise
        except Exception as exc:  # any SDK/HTTP error -> typed failure (never a fake url)
            raise RenderError(
                f"live render failed for model={model}: {type(exc).__name__}: {exc}",
                cause=exc,
            ) from exc


def live_render_enabled() -> bool:
    """True iff a real render should be attempted: ``FAL_KEY`` set AND opt-in flag on.

    Mirrors ``HEATGUARD_LIVE_ROUTING`` — the offline/demo path never touches the network
    even if a key happens to be present in the environment.
    """
    return bool(os.environ.get(FAL_ENV) and os.environ.get(LIVE_RENDER_ENV))
