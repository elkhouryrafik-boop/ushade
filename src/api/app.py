"""FastAPI backend — Phase 2.2 Console UI: Heat & Crowd Live.

Exposes exactly 5 endpoints that wire the real pipeline into the heatguard-ai-console:
  POST /api/run/{project_id}              — start climate + crowd stages
  GET  /api/status/{project_id}           — poll stage completion states
  GET  /api/artifacts/{project_id}/heat   — WGS84 heat cells (demo_heat.json)
  GET  /api/artifacts/{project_id}/crowd  — WGS84 crowd grid (demo_crowd_grid.json)
  GET  /api/artifacts/{project_id}/trajectories — agent trajectories (demo_trajectories.json)

Security:
  T-2.2-01: project_id is regex-validated [a-z0-9-]+ — Path(...) never receives ".." (path traversal)
  T-2.2-02: policy_path is a repo constant in run_crowd_stage — never user input (see crowd.py)
  T-2.2-03: CORSMiddleware allows http://localhost:5173 explicitly (console dev origin)
  T-2.2-04: VITE_GOOGLE_MAPS_API_KEY is client-side only; this service never reads or returns it
  T-2.2-05: All secrets read from env vars (CCA-F P7 / XFN-02); none returned in responses

CCA-F P1/P2:
  Crowd rollout completion is gated on the ACTUAL run_crowd_stage return value — never on
  elapsed time. The _run_status["crowd_grid"] is set to "done" ONLY after run_crowd_stage()
  returns (the function itself returns when the rollout finishes writing crowd_grid.json).
  The old fixed 4.2 s timer in SimulationView.tsx is replaced by polling this endpoint.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# CWD-independent root: derive REPO_ROOT from this file's location so the service
# works regardless of the working directory the process is started from (Pitfall 4).
# src/api/app.py → src/api/ → src/ → REPO_ROOT
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROJECTS_ROOT = REPO_ROOT / "projects"
VIZ_DATA_DIR = REPO_ROOT / "viz" / "data"

# The stage modules use flat imports (`from climate... / from crowd...`) that resolve
# only when src/ is on sys.path (pytest does this via pythonpath=["src"]). Ensure it
# here too so `python -m uvicorn src.api.app:app --port 8000` and
# `python -c "from src.api.app import app"` both work from any CWD.
_SRC_DIR = str(REPO_ROOT / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402

# T-2.2-01: project_id must match this pattern — never allows ".." path traversal.
PROJECT_ID_PATTERN = re.compile(r"^[a-z0-9-]+$")

# D-10 / T-05-14: /inventory/query param-validation patterns (clone the project_id
# discipline). location is a plain token — no "..", no "/", no "\" — so it can never
# traverse outside PROJECTS_ROOT when it folds into a snapshot directory lookup.
LOCATION_PATTERN = re.compile(r"^[a-z0-9 -]{1,64}$")

# D-10 / T-05-14: material_class is validated against a FIXED allow-list — the two frozen
# material classes from data/materials.json (struct + membr). An unknown class -> 422.
# Common aliases are folded onto the canonical class so a caller asking for "membrane"
# or "structural" is still validated (not silently rejected) — the allow-list stays closed.
_MATERIAL_CLASS_ALIASES = {
    "struct": "struct",
    "structural": "struct",
    "membr": "membr",
    "membrane": "membr",
}

# The frozen material-id prefix per canonical class (data/materials.json ids are
# "struct-*" / "membr-*"). Used to filter the availability view by material_class.
_CLASS_ID_PREFIX = {"struct": "struct-", "membr": "membr-"}

_LOG = logging.getLogger("heatguard.api")

# Real stage functions — imported at module level (they are torch-free at import
# time; torch is only loaded inside run_crowd_stage's miss path).
# The service MUST be launched from the repo root as:
#   python -m uvicorn src.api.app:app --port 8000
# (bare `uvicorn src.api.app:app` may not put src/ on sys.path — always use `python -m`).
from climate.climate import run_climate_stage  # noqa: E402
from crowd.crowd import run_crowd_stage  # noqa: E402

# Phase 14 (Plan 04, D-05/D-06): the full-run orchestrator chains the canonical
# placement stage after climate + crowd. ``run_placement_stage(engine="robust")``
# emits the ranked ``structure_zones.json`` (the SOLE placer post-pivot) — it
# SUPERSEDES the retired greedy ``core.core`` placer (score_grid + footprint).
# Imported at module level so the test suite can monkeypatch it on this module
# (app_module.run_placement_stage).
#
# The geometry stage (``geom.geom``, old step 4) RETIRES with the v2.0
# pivot ("AI proposes, human commits" — Rhino dropped): ``structure_zones`` emits
# ranked ZONES, not footprint polygons (PLACE-09), so there is no footprint to feed
# Grasshopper. The render stage stays a cosmetic, non-blocking sidecar.
from core.placement_stage import run_placement_stage  # noqa: E402
from render.render import run_render_stage  # noqa: E402

# Shared WGS84 emitters (single source of truth — the demo generator AND these
# live endpoints project the per-run UTM artifacts to lon/lat through the SAME
# code path, so the live map matches the demo exactly). De-mock: heat/crowd are
# projected on the fly from the real projects/<id>/{utci_grid,crowd_grid}.json.
from crowd.wgs84_export import crowd_grid_payload, emit_heat, emit_structure_zones  # noqa: E402
from climate.weather_forecast import (  # noqa: E402
    fetch_weather_context,
    _DEFAULT_LAT as _FORUM_LAT,
    _DEFAULT_LON as _FORUM_LON,
)

# Load the fixed-site boundary (WGS84) from the committed geojson.
# Used by run_climate_stage as site_polygon. Read once at startup.
_BOUNDARY_PATH = REPO_ROOT / "viz" / "data" / "boundary_2026.geojson"


def _load_site_polygon() -> dict:
    """Load the Parc del Fòrum WGS84 boundary from the committed geojson.

    boundary_2026.geojson's polygon carries TWO rings (outer boundary + an
    interior hole). The infrared SDK only accepts single-ring polygons, and
    run_climate_stage's cache key hashes the OUTER ring only — so we strip the
    polygon down to its outer ring here. Passing the raw 2-ring polygon makes
    a climate cache MISS escalate into a live-call PolygonValidationError.
    """
    data = json.loads(_BOUNDARY_PATH.read_text(encoding="utf-8"))
    # boundary_2026.geojson is a FeatureCollection — take its first Feature.
    feature = data["features"][0] if data.get("type") == "FeatureCollection" else data
    geom = feature.get("geometry", feature)
    outer_ring = geom["coordinates"][0]
    return {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "Polygon", "coordinates": [outer_ring]},
    }


_SITE_POLYGON: dict = _load_site_polygon()

# In-memory run status — keyed by project_id. Fine for a single-user demo.
# StageStatus values: "pending" | "running" | "done" | "failed"
_run_status: dict[str, dict[str, str]] = {}

# Single-thread executor so only one rollout runs at a time (demo constraint).
# The main asyncio event loop stays responsive for status polling.
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="heatguard-stage")

# ------------------------------------------------------------------ #
# FastAPI app
# ------------------------------------------------------------------ #
app = FastAPI(title="HeatGuard Phase 2.2 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    # T-2.2-03: console dev origins only (localhost AND its 127.0.0.1 alias —
    # LW-03: the two are distinct origins; omitting the alias breaks direct
    # calls if a future change bypasses the Vite proxy, e.g. VITE_API_URL).
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def _reject_traversal_artifact_paths(request, call_next):
    """T-07-03: reject a path-traversal-shaped project_id on /api/artifacts/* with 422.

    A URL like ``/api/artifacts/..%2Fetc/material_selection`` is decoded to
    ``/api/artifacts/../etc/material_selection`` BEFORE routing — so the artifact
    route (single-segment {project_id}) never matches and the request would 404 at
    the router, BYPASSING _validated_project_id. We inspect the raw ASGI path first:
    the segment immediately after ``/api/artifacts/`` must match [a-z0-9-]+, else 422
    (the same fail-closed contract _validated_project_id enforces inside the handlers).
    """
    path = request.scope.get("path", "")
    prefix = "/api/artifacts/"
    if path.startswith(prefix):
        candidate = path[len(prefix):].split("/", 1)[0]
        if not PROJECT_ID_PATTERN.match(candidate):
            return JSONResponse(
                status_code=422,
                content={"detail": "project_id must match [a-z0-9-]+"},
            )
    return await call_next(request)


# ------------------------------------------------------------------ #
# Path-param validation helper
# ------------------------------------------------------------------ #
def _validated_project_id(project_id: str) -> str:
    """T-2.2-01: Reject project_id that is not [a-z0-9-]+.

    FastAPI path params accept any string including ".." — we enforce the regex
    explicitly so projects_root / project_id can never traverse outside PROJECTS_ROOT.
    """
    if not PROJECT_ID_PATTERN.match(project_id):
        raise HTTPException(
            status_code=422,
            detail="project_id must match [a-z0-9-]+",
        )
    return project_id


def _validated_inventory_query(
    material_class: str, min_qty: str, location: str
) -> tuple[str, int, str]:
    """D-10 / T-05-14: validate the /inventory/query params, cloning the project_id
    discipline. Returns ``(canonical_class, min_qty_int, location)`` or raises 422.

    - ``material_class`` must resolve (via the closed alias map) to a frozen class
      {struct, membr} — an unknown class is a 422, never silently widened.
    - ``min_qty`` is coerced to int and must be >= 0 — negative / non-numeric is a 422
      (bounded parse, no unbounded scan: T-05-16).
    - ``location`` must match the plain-token regex (no "..", no "/" or "\\") so it can
      never traverse outside PROJECTS_ROOT (T-05-14 path-traversal mitigation).

    The detail strings carry ONLY the offending param NAME and the rule — never an env
    secret, never the raw value echoed back into the response (T-05-15).
    """
    canonical = _MATERIAL_CLASS_ALIASES.get(material_class.strip().lower())
    if canonical is None:
        raise HTTPException(
            status_code=422,
            detail="material_class must be one of {struct, membr}",
        )

    try:
        qty = int(str(min_qty).strip())
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=422,
            detail="min_qty must be a non-negative integer",
        )
    if qty < 0:
        raise HTTPException(
            status_code=422,
            detail="min_qty must be a non-negative integer",
        )

    loc = location.strip().lower()
    if not LOCATION_PATTERN.match(loc):
        raise HTTPException(
            status_code=422,
            detail="location must match [a-z0-9 -]{1,64} (no path separators)",
        )

    return canonical, qty, loc


def _load_inventory_availability(project_id: str) -> list[dict]:
    """Read the persisted per-source ``latest.json`` snapshots for a project and return a
    flat availability view (NEVER a live scrape — T-05-16: the endpoint serves cached
    snapshots only; the cache-first stage owns the live fetch).

    Reads ONLY ``projects/<project_id>/inventory/<source>/latest.json`` — it touches no
    env var and no secret (T-05-15). A missing inventory dir yields an empty view (the
    selection has simply not been run yet), never a 500.
    """
    inv_dir = PROJECTS_ROOT / project_id / "inventory"
    view: list[dict] = []
    if not inv_dir.is_dir():
        return view
    for latest in sorted(inv_dir.glob("*/latest.json")):
        try:
            snap = json.loads(latest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source_url = snap.get("source_url", "")
        for listing in snap.get("listings", []):
            view.append(
                {
                    "material_id": listing.get("material_id"),
                    "availability": listing.get("availability"),
                    "qty_available": listing.get("qty_available"),
                    "distance_km": listing.get("distance_km"),
                    "distance_tier": listing.get("distance_tier"),
                    "source_url": listing.get("source_url", source_url),
                }
            )
    return view


# ------------------------------------------------------------------ #
# Background task
# ------------------------------------------------------------------ #
async def _do_run(project_id: str) -> None:
    """Run climate (cache-first, ~instant) then crowd (real rollout, minutes).

    CCA-F P1/P2: crowd_grid status is set to "done" ONLY when run_crowd_stage() returns.
    Never set by elapsed time, never by text matching — gated on the actual return value
    of the synchronous Python function that writes crowd_grid.json.
    """
    loop = asyncio.get_running_loop()
    # MD-01: the status entry is seeded by the /api/run endpoint BEFORE this task
    # is queued (synchronously, so the in-flight guard sees it immediately).
    # Never reset it here — that would corrupt a concurrent run's state machine.
    _run_status.setdefault(project_id, {"utci_grid": "running", "crowd_grid": "pending"})
    try:
        # Climate: cache-first — returns immediately on cache hit (~ms)
        await loop.run_in_executor(
            _EXECUTOR,
            lambda: run_climate_stage(
                project_id,
                "2026-06-14",  # Primavera preset date
                site_polygon=_SITE_POLYGON,
                projects_root=PROJECTS_ROOT,
            ),
        )
        _run_status[project_id]["utci_grid"] = "done"
    except Exception:
        # Never swallow stage failures silently — the status endpoint reports
        # "failed", and the server log carries the actual traceback (CCA-F P6).
        _LOG.exception("climate stage failed for %s", project_id)
        _run_status[project_id]["utci_grid"] = "failed"
        _run_status[project_id]["crowd_grid"] = "failed"
        return

    _run_status[project_id]["crowd_grid"] = "running"
    try:
        # Crowd: real SIM_STEPS_V2=1400 × 650 agents — takes minutes on CPU.
        # run_in_executor keeps the asyncio event loop unblocked so /api/status
        # responds to frontend polls throughout the rollout.
        await loop.run_in_executor(
            _EXECUTOR,
            lambda: run_crowd_stage(
                project_id,
                projects_root=PROJECTS_ROOT,
            ),
        )
        # CCA-F P1/P2 compliance: "done" is set HERE — after the function returns.
        _run_status[project_id]["crowd_grid"] = "done"
    except Exception:
        _LOG.exception("crowd stage failed for %s", project_id)
        _run_status[project_id]["crowd_grid"] = "failed"


# The status keys the FULL pipeline reports, in dependency order. One key per stage;
# the orchestrator flips each to "done" ONLY on the stage fn's return.
#
# Phase 14 (Plan 04, D-05/D-06): the pipeline is climate -> crowd -> placement. The
# greedy ``score_grid`` stage is RETIRED (superseded by the ranked ``structure_zones``
# placer) and the geometry/material/acceptance chain — which was anchored on the
# retired ``footprint.json``/``gh_meta.json`` the v2.0 pivot dropped ("AI proposes,
# human commits") — retires with it. The honest pipeline ends at the canonical
# placement output; cladding + the cooling-acceptance gate await the human-committed
# geometry (a future phase), never a fabricated footprint.
_FULL_STAGE_KEYS = (
    "utci_grid",         # 1. run_climate_stage
    "crowd_grid",        # 2. run_crowd_stage
    "structure_zones",   # 3. run_placement_stage(engine="robust")  (the SOLE placer, D-06)
)


def _seed_full_status() -> dict[str, str]:
    """All pipeline stage keys defaulted to 'pending' (the never-run shape)."""
    return {k: "pending" for k in _FULL_STAGE_KEYS}


def _load_parsed_brief(project_id: str, body: dict | None) -> dict:
    """Build the parsed_brief for the run (A2 — direct field passthrough, NOT the LLM parser).

    ROADMAP 2.2 SC1 precedent: "direct field passthrough acceptable; LLM parser wiring
    may land in Phase 7." If the body supplies the 4 typed fields they are passed through
    verbatim; any field the body omits falls back to the persisted
    ``projects/<id>/parsed_brief.json`` (the demo brief). The LLM parser is NOT added as a
    blocking stage here (PRD §6 — the LLM never designs; parse-only, deferred).
    """
    body = body or {}
    persisted: dict = {}
    brief_path = PROJECTS_ROOT / project_id / "parsed_brief.json"
    if brief_path.exists():
        try:
            persisted = json.loads(brief_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            persisted = {}
    merged = dict(persisted)
    for field in ("capacity", "budget", "date", "theme", "festival_start", "festival_end"):
        if body.get(field) is not None:
            merged[field] = body[field]
    return merged


def _site_polygon_from_body(body: dict | None) -> dict:
    """Thread a body-supplied boundary_geojson outer ring as site_polygon, else _SITE_POLYGON.

    Mirrors _load_site_polygon's outer-ring extraction (the infrared SDK only accepts a
    single-ring polygon, and run_climate_stage hashes the OUTER ring only).
    """
    body = body or {}
    boundary = body.get("boundary_geojson")
    if not boundary:
        return _SITE_POLYGON
    try:
        feature = (
            boundary["features"][0]
            if boundary.get("type") == "FeatureCollection"
            else boundary
        )
        geom = feature.get("geometry", feature)
        outer_ring = geom["coordinates"][0]
        return {
            "type": "Feature",
            "properties": {},
            "geometry": {"type": "Polygon", "coordinates": [outer_ring]},
        }
    except (KeyError, IndexError, TypeError):
        # A malformed boundary falls back to the committed site polygon rather than 500.
        _LOG.warning("boundary_geojson malformed for run; using default _SITE_POLYGON")
        return _SITE_POLYGON


async def _do_full_run(
    project_id: str,
    *,
    parsed_brief: dict | None = None,
    brief_date: str | None = None,
    site_polygon: dict | None = None,
) -> None:
    """Run the FULL pipeline: climate -> crowd -> placement (structure_zones).

    Modelled on _do_run: each synchronous stage fn is dispatched via
    ``loop.run_in_executor(_EXECUTOR, lambda: …)`` so the asyncio loop stays responsive
    for status polls, with a try/except-per-stage that logs the traceback (CCA-F P6) and
    marks the stage "failed" on an INTERNAL error.

    CCA-F P1/P2: each ``_run_status[project_id][key]`` flips to "done" ONLY on the stage
    fn's actual return — never on elapsed time, never on text. The status entry is seeded
    by the /api/run endpoint synchronously BEFORE this task is queued (MD-01).

    Phase 14 (Plan 04, D-05/D-06): step 3 is the canonical ranked-zone placer
    ``run_placement_stage(engine="robust")`` — it SUPERSEDES the retired greedy
    greedy ``core.core`` placer (score_grid + footprint). The downstream geometry -> material ->
    acceptance chain, which required the retired ``footprint.json``/``gh_meta.json``
    (dropped by the v2.0 "AI proposes, human commits" pivot), retires with the placer;
    cladding + the cooling-acceptance gate await the human-committed geometry of a future
    phase, never a fabricated footprint. The render stays a cosmetic, non-blocking sidecar.
    """
    loop = asyncio.get_running_loop()
    brief = parsed_brief if parsed_brief is not None else _load_parsed_brief(project_id, None)
    date = brief_date or brief.get("date") or "2026-06-14"
    polygon = site_polygon if site_polygon is not None else _SITE_POLYGON
    _run_status.setdefault(project_id, _seed_full_status())

    # ── 1) climate ────────────────────────────────────────────────────────────
    _run_status[project_id]["utci_grid"] = "running"
    try:
        await loop.run_in_executor(
            _EXECUTOR,
            lambda: run_climate_stage(
                project_id, date, site_polygon=polygon, projects_root=PROJECTS_ROOT
            ),
        )
        _run_status[project_id]["utci_grid"] = "done"
    except Exception:
        _LOG.exception("climate stage failed for %s", project_id)
        _run_status[project_id]["utci_grid"] = "failed"
        return

    # ── 2) crowd ──────────────────────────────────────────────────────────────
    _run_status[project_id]["crowd_grid"] = "running"
    try:
        await loop.run_in_executor(
            _EXECUTOR,
            lambda: run_crowd_stage(project_id, projects_root=PROJECTS_ROOT),
        )
        _run_status[project_id]["crowd_grid"] = "done"
    except Exception:
        _LOG.exception("crowd stage failed for %s", project_id)
        _run_status[project_id]["crowd_grid"] = "failed"
        return

    # ── 3) placement (D-06: the canonical ranked-zone placer; robustness layer) ─
    _run_status[project_id]["structure_zones"] = "running"
    try:
        await loop.run_in_executor(
            _EXECUTOR,
            lambda: run_placement_stage(
                project_id, projects_root=PROJECTS_ROOT, engine="robust"
            ),
        )
        _run_status[project_id]["structure_zones"] = "done"
    except Exception:
        _LOG.exception("placement stage failed for %s", project_id)
        _run_status[project_id]["structure_zones"] = "failed"
        return

    # ── render (Phase 6 — COSMETIC, non-blocking) ─────────────────────────────
    # The render is the last, cosmetic step: it is NOT one of the six stepper stages
    # (_FULL_STAGE_KEYS) and a render failure must NEVER regress the run. It ALWAYS writes
    # the ControlNet conditioning map; it writes a contract render.json only with a live
    # FAL_KEY (HEATGUARD_LIVE_RENDER) — otherwise it degrades to a labelled pending sidecar
    # and NEVER fabricates an image url. So we swallow every render error here by design.
    try:
        await loop.run_in_executor(
            _EXECUTOR,
            lambda: run_render_stage(project_id, projects_root=PROJECTS_ROOT),
        )
    except Exception:
        _LOG.exception("render stage (cosmetic) failed for %s — run unaffected", project_id)


# ------------------------------------------------------------------ #
# Endpoints
# ------------------------------------------------------------------ #

@app.post("/api/run/{project_id}")
async def run_stages(project_id: str, background_tasks: BackgroundTasks, request: Request):
    """Start the FULL pipeline for project_id (Phase 14 / D-06).

    Returns immediately with {project_id, status: "started"}. The actual run
    proceeds in the background; poll GET /api/status/{project_id} for progress
    across the pipeline stages (utci_grid, crowd_grid, structure_zones). The
    greedy score_grid + the geometry/material/acceptance chain retired with the
    v2.0 pivot; structure_zones is the canonical placement output.

    Brief input (A2 — direct field passthrough, NOT the LLM parser): the frontend
    posts an OPTIONAL JSON body ``{capacity?, budget?, date?, theme?, boundary_geojson?}``.
    Any omitted field falls back to the persisted parsed_brief.json (PRD §6 — the LLM
    never designs; parser wiring is deferred). A body-less POST runs the full demo brief.

    MD-01: idempotent for in-flight runs — if any stage is still "running" or
    "pending", the re-trigger returns {status: "already_running"} WITHOUT
    resetting _run_status or queuing a second rollout (a double-POST must not
    regress the stepper or stack a second rollout on the executor).

    T-2.2-01: project_id is validated against [a-z0-9-]+ before use.
    """
    _validated_project_id(project_id)

    # Parse the optional JSON body — a body-less or non-JSON POST is the demo path.
    body: dict | None = None
    try:
        raw = await request.body()
        if raw:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                body = parsed
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = None

    current = _run_status.get(project_id, {})
    if any(v in ("running", "pending") for v in current.values()):
        return JSONResponse({"project_id": project_id, "status": "already_running"})

    parsed_brief = _load_parsed_brief(project_id, body)
    site_polygon = _site_polygon_from_body(body)
    brief_date = parsed_brief.get("date")

    # Seed ALL six status keys synchronously BEFORE queuing the task so a second POST
    # in the gap between this ack and the background task starting is also rejected.
    _run_status[project_id] = _seed_full_status()
    background_tasks.add_task(
        _do_full_run,
        project_id,
        parsed_brief=parsed_brief,
        brief_date=brief_date,
        site_polygon=site_polygon,
    )
    return JSONResponse({"project_id": project_id, "status": "started"})


@app.get("/api/status/{project_id}")
def get_status(project_id: str):
    """Return stage completion states.

    Response shape: {"utci_grid": "pending"|"running"|"done"|"failed",
                     "crowd_grid": "pending"|"running"|"done"|"failed"}

    The frontend ProgressiveStepper polls this every 2 seconds and advances its
    step index only when the relevant stage transitions to "done" — never on time.
    T-2.2-01: project_id validated.
    """
    _validated_project_id(project_id)
    return _run_status.get(project_id, _seed_full_status())


@app.get("/api/artifacts/{project_id}/heat")
def get_heat_artifact(project_id: str):
    """Return WGS84 heat cells for THIS run, projected on the fly from utci_grid.json.

    De-mock (was: static viz/data/demo_heat.json regardless of run). The climate stage
    writes projects/<id>/utci_grid.json (UTM31N contract artifact); we project its cells
    to WGS84 lon/lat through the SAME ``emit_heat`` the demo generator uses, so the live
    heat layer reflects the run's actual site. Falls back to the labelled demo file ONLY
    when this run has no utci_grid yet (older project / pre-climate) — never silently.
    T-2.2-01: project_id validated.
    """
    _validated_project_id(project_id)
    utci_path = PROJECTS_ROOT / project_id / "utci_grid.json"
    if utci_path.exists():
        utci = _read_project_json(project_id, "utci_grid.json")
        return JSONResponse(emit_heat(utci["cells"], utci["lattice"]))
    # Honest fallback: no per-run heat yet — serve the Primavera demo, labelled as such.
    path = VIZ_DATA_DIR / "demo_heat.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(str(path), media_type="application/json",
                        headers={"X-Heatguard-Source": "demo-fallback"})


@app.get("/api/artifacts/{project_id}/crowd")
def get_crowd_artifact(project_id: str):
    """Return WGS84 crowd grid (density + dwell_zones + flow_vectors) for THIS run.

    De-mock: projected on the fly from projects/<id>/crowd_grid.json (the UTM contract
    artifact the crowd stage writes) via the shared ``crowd_grid_payload`` emitter —
    same shape the demo produced. Labelled demo fallback when no per-run grid exists yet.
    T-2.2-01: project_id validated.
    """
    _validated_project_id(project_id)
    crowd_path = PROJECTS_ROOT / project_id / "crowd_grid.json"
    if crowd_path.exists():
        cg = _read_project_json(project_id, "crowd_grid.json")
        return JSONResponse(crowd_grid_payload(cg))
    path = VIZ_DATA_DIR / "demo_crowd_grid.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(str(path), media_type="application/json",
                        headers={"X-Heatguard-Source": "demo-fallback"})


@app.get("/api/artifacts/{project_id}/trajectories")
def get_trajectories(project_id: str):
    """Return THIS run's WGS84 per-step agent trajectory (projects/<id>/trajectories.json).

    De-mock: the crowd stage now persists the real per-agent rollout for the drawn site
    (``run_crowd_stage`` → trajectories.json, WGS84, stride-bounded). FileResponse streams
    it chunked (does not block the event loop / load the whole file into memory — Pitfall 5).
    Labelled demo fallback ONLY when this run has no persisted trajectory yet.
    T-2.2-01: project_id validated.
    """
    _validated_project_id(project_id)
    run_path = PROJECTS_ROOT / project_id / "trajectories.json"
    if run_path.exists():
        return FileResponse(str(run_path), media_type="application/json")
    path = VIZ_DATA_DIR / "demo_trajectories.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(str(path), media_type="application/json",
                        headers={"X-Heatguard-Source": "demo-fallback"})


@app.get("/api/artifacts/{project_id}/structure_zones")
def get_structure_zones(project_id: str):
    """Return THIS run's ranked shade-priority zones in WGS84 (the placement output).

    The placer writes projects/<id>/structure_zones.json (UTM31N ranked ZONES — the
    SOLE placer post-pivot, D-06). We project each zone center to lon/lat and emit a
    square footprint (side = sqrt(area_m2)) via the shared ``emit_structure_zones``
    emitter, so the Placement stage renders the real ranked footprints on the canvas
    and the side list mirrors them. Honest 404 (never fabricated) when this run has no
    structure_zones yet (pre-placement / climate-only). T-2.2-01: project_id validated.
    """
    _validated_project_id(project_id)
    zones = _read_project_json(project_id, "structure_zones.json")
    return JSONResponse(emit_structure_zones(zones))


# ------------------------------------------------------------------ #
# Phase 7 (Plan 02) terminal-artifact endpoints (FE-04)
#
# Each serves the REAL per-project projects/<id>/ artifacts (unlike the demo
# heat/crowd/trajectories routes that read viz/data/). Discipline cloned from
# get_heat_artifact: _validated_project_id FIRST (T-07-03 path-traversal -> 422),
# then resolve PROJECTS_ROOT / <id> / <file>, then 404 with a GENERIC detail that
# never echoes an internal absolute path (T-07-04). No env var / secret is read
# or returned by any of these (T-05-15 discipline).
# ------------------------------------------------------------------ #

def _read_project_json(project_id: str, filename: str) -> dict:
    """Read projects/<id>/<filename> as JSON; raise 404 (generic detail) if absent/corrupt.

    The 404 detail is a fixed "artifact not found" string — it NEVER includes the
    resolved absolute path (T-07-04 info-disclosure mitigation).
    """
    path = PROJECTS_ROOT / project_id / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact not found")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=404, detail="artifact not found")


@app.get("/api/artifacts/{project_id}/material_selection")
def get_material_selection(project_id: str):
    """Serve the persisted material_selection.json (the chosen membrane + carbon/cost basis)."""
    _validated_project_id(project_id)
    path = PROJECTS_ROOT / project_id / "material_selection.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(str(path), media_type="application/json")


@app.get("/api/artifacts/{project_id}/acceptance")
def get_acceptance(project_id: str):
    """Serve the cooling-acceptance verdict, MERGING acceptance.json with its Comfort-Gap
    sidecar acceptance_meta.json into ``{...verdict_fields, meta:{...}}``.

    D-11 / T-07-06: the verdict (PASS or FAIL) is served VERBATIM — a FAIL is never
    rewritten to PASS or hidden. acceptance_meta.json may be absent -> meta:{} (never 500).
    """
    _validated_project_id(project_id)
    verdict = _read_project_json(project_id, "acceptance.json")
    meta_path = PROJECTS_ROOT / project_id / "acceptance_meta.json"
    meta: dict = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
    return JSONResponse({**verdict, "meta": meta})


@app.get("/api/artifacts/{project_id}/bom")
def get_bom(project_id: str):
    """Serve the bill-of-materials projection of gh_meta.json (bom + egress + certs + coverage)."""
    _validated_project_id(project_id)
    gh_meta = _read_project_json(project_id, "gh_meta.json")
    return JSONResponse(
        {
            "bom": gh_meta.get("bom", {}),
            "egress": gh_meta.get("egress", {}),
            "certification_needs": gh_meta.get("certification_needs", []),
            "shadow_coverage_pct": gh_meta.get("shadow_coverage_pct"),
        }
    )


# Phase 14 (Plan 04, D-05/D-06): the /api/artifacts/{id}/footprint endpoint RETIRED
# with the geometry stage. ``footprint.json`` was produced by the now-deleted greedy
# ``core.core`` stage; the canonical placer emits ranked ZONES, not footprint polygons
# (PLACE-09), and the v2.0 pivot dropped Rhino ("AI proposes, human commits"). No
# footprint geometry is fabricated. The structure_zones artifact is the placement output;
# a future phase serves the human-committed geometry (see /api/artifacts/{id}/geometry,
# the GLB endpoint, which now honestly 404s until that producer lands).


@app.get("/api/artifacts/{project_id}/render")
def get_render(project_id: str):
    """RENDER STUB (D-03) — the render is a labelled placeholder until Phase 6.

    Returns ``{render_url: null, status: "pending", phase: 6, note: …}`` — DELIBERATELY
    NOT the contract-valid render shape (contracts/render.schema.json REQUIRES render_url +
    conditioning_scale=1.0 for a COMPLETED render; the UI must never show a fabricated
    render). T-07-05: no S3 cred / signed URL is returned — Phase 6 writes the real
    render.json. If a real projects/<id>/render.json already exists, serve its render_url.
    """
    _validated_project_id(project_id)
    project_dir = PROJECTS_ROOT / project_id
    render_path = project_dir / "render.json"
    if render_path.exists():
        try:
            real = json.loads(render_path.read_text(encoding="utf-8"))
            return JSONResponse(
                {
                    "render_url": real.get("render_url"),
                    "status": "done",
                    "phase": 6,
                    "model": real.get("model"),
                    "conditioning_scale": real.get("conditioning_scale"),
                }
            )
        except (OSError, json.JSONDecodeError):
            pass  # corrupt real render -> fall through to the stub

    # Phase 6 pending: a real ControlNet conditioning map exists (the geometry lock that
    # WOULD be fed to FLUX.1), but no live FAL_KEY ran the photoreal render yet. Surface the
    # map (labelled) so the dashboard shows real geometry evidence — never a fabricated render.
    meta_path = project_dir / "render_meta.json"
    if meta_path.exists() and (project_dir / "render_controlnet_input.png").exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return JSONResponse(
                {
                    "render_url": None,
                    "status": "pending_live",
                    "phase": 6,
                    "model": meta.get("model"),
                    "conditioning_scale": meta.get("conditioning_scale"),
                    "controlnet_input_url": f"/api/artifacts/{project_id}/render-input",
                    "note": (
                        "ControlNet conditioning input (geometry lock) ready — live FLUX.1 "
                        "render pending a fal.ai key. No render is fabricated."
                    ),
                    "schema_version": "1.0.0-pending",
                }
            )
        except (OSError, json.JSONDecodeError):
            pass
    return JSONResponse(
        {
            "render_url": None,
            "status": "pending",
            "phase": 6,
            "note": "render pending — Phase 6",
            "schema_version": "1.0.0-stub",
        }
    )


@app.get("/api/artifacts/{project_id}/render-input")
def get_render_input(project_id: str):
    """Serve the Phase-6 ControlNet conditioning map PNG (depth/canny geometry lock).

    This is a REAL pipeline artifact — the depth/canny map derived from the Rhino geometry
    that FLUX.1 is constrained by at conditioning_scale=1.0. It is NOT a photorealistic
    render; the dashboard labels it as the conditioning input.
    """
    _validated_project_id(project_id)
    path = PROJECTS_ROOT / project_id / "render_controlnet_input.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="no conditioning map for this project")
    return FileResponse(str(path), media_type="image/png")


@app.get("/api/artifacts/{project_id}/geometry")
def get_geometry(project_id: str):
    """Serve the decoded shade-structure mesh as a self-contained binary GLB.

    Mirrors get_render_input: path-traversal-guarded FIRST (422), honest 404 on a
    missing artifact, no secret in the response (T-08-01/T-08-02). The .glb is
    self-contained (Plan 01 added the file_type='glb' export in decode.py), so the
    browser needs no companion .bin fetch — drei useGLTF loads it directly. The
    response is the file bytes and nothing else (no env/cred read or logged).

    Phase 14 (Plan 04, D-05/D-06) note: the geometry stage (``geom.geom``) that
    produced ``structure.glb`` RETIRED with the v2.0 "AI proposes, human commits"
    pivot — the full-run no longer generates a mesh. This endpoint therefore now
    HONESTLY 404s for runs without a pre-committed ``structure.glb`` (it never
    fabricates geometry). The frontend StructuralView/Viewport3D loses its live data
    source until a future phase wires the human-committed geometry producer; the 404
    is the honest empty-state, not a silent break.
    """
    _validated_project_id(project_id)  # T-08-01: 422 BEFORE any fs path is built
    path = PROJECTS_ROOT / project_id / "structure.glb"
    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(str(path), media_type="model/gltf-binary")


@app.get("/api/weather")
def get_weather(
    date: str | None = None,
    lat: float = _FORUM_LAT,   # Parc del Fòrum canonical centroid (geom.constants)
    lon: float = _FORUM_LON,
):
    """Return Open-Meteo weather context for a festival date and location.

    Three scenarios (all labelled ASSUMED — informational only, never gates Phase 5b):
      - Past / near:     measured archive data.
      - 1–16 days ahead: operational forecast.
      - > 16 days ahead: 5-year historical climate normals with best_case / worst_case.

    Query params:
      date (str, optional): ISO "YYYY-MM-DD". Defaults to today.
      lat  (float, optional): WGS84 latitude.  Defaults to Parc del Fòrum centroid.
      lon  (float, optional): WGS84 longitude. Defaults to Parc del Fòrum centroid.
    """
    from datetime import date as _date
    target_date = date or _date.today().isoformat()
    return JSONResponse(fetch_weather_context(target_date, lat=lat, lon=lon))


@app.get("/api/site/festival-schema")
def get_festival_schema():
    """Serve the committed Primavera site schema — the SAME geojson the crowd sim
    loads (``viz/data/festival_map_2026.geojson`` 19 stages + 2 entrances + amenities,
    and ``boundary_2026.geojson`` the site outline).

    The frontend workspace 'Load Primavera preset' renders this as the on-map festival
    layout, so what the operator places matches the layout the simulation flows agents
    across 1:1 (single source of truth; no fabricated/placeholder coordinates).
    """
    festival_path = VIZ_DATA_DIR / "festival_map_2026.geojson"
    boundary_path = VIZ_DATA_DIR / "boundary_2026.geojson"
    if not festival_path.exists() or not boundary_path.exists():
        raise HTTPException(status_code=404, detail="site schema not found")
    try:
        festival = json.loads(festival_path.read_text(encoding="utf-8"))
        boundary = json.loads(boundary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="site schema unreadable") from exc
    return JSONResponse(
        {
            "boundary": boundary,
            "features": festival.get("features", []),
            "source": "viz/data/festival_map_2026.geojson + boundary_2026.geojson",
            "schema_version": "1.0.0",
        }
    )


@app.get("/api/artifacts/{project_id}/provenance")
def get_provenance(project_id: str):
    """Serve the MERGED provenance ledger across the per-stage ledgers (A4).

    Merges provenance.json, selection_ledger.json, acceptance_ledger.json (any subset
    present) into one ``{schema_version, entries:[...]}``. Each entry keeps its ``stage``;
    on a (stage,key) collision the later stage wins but BOTH stay — entries are namespaced
    by stage+key, NEVER silently dropped. Missing ledgers are skipped, never 500.
    """
    _validated_project_id(project_id)
    merged: dict[tuple, dict] = {}
    schema_version = "1.0.0"
    for ledger_name in ("provenance.json", "selection_ledger.json", "acceptance_ledger.json"):
        path = PROJECTS_ROOT / project_id / ledger_name
        if not path.exists():
            continue
        try:
            ledger = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        schema_version = ledger.get("schema_version", schema_version)
        for entry in ledger.get("entries", []):
            ns_key = (entry.get("stage"), entry.get("key"))
            merged[ns_key] = entry  # later stage wins on a (stage,key) collision
    return JSONResponse({"schema_version": schema_version, "entries": list(merged.values())})


@app.get("/inventory/query")
def inventory_query(
    material_class: str,
    min_qty: str = "0",
    location: str = "barcelona",
    project_id: str = "primavera-demo",
):
    """D-10: Material Recovery Inventory availability view over the REAL persisted snapshots.

    GET /inventory/query?material_class=<struct|membr>&min_qty=<int>=0>&location=<token>

    The instructor-named tool surface the selection gate consults (D-06: consult
    /inventory/query BEFORE choosing). It serves the cache-first ``run_inventory_stage``
    output (the per-source ``latest.json`` snapshots) — it NEVER triggers a live scrape
    per request (T-05-16) and NEVER reads, returns, or logs an env secret such as
    ${ORS_API_KEY} (T-05-15: the routing module owns the geocoder key; this endpoint
    touches only persisted snapshots on disk).

    Validation (clone of the _validated_project_id discipline):
      - material_class against the fixed {struct, membr} allow-list   -> 422 on miss
      - min_qty coerced to int >= 0 (bounded parse)                   -> 422 on negative/non-numeric
      - location a plain token (no "..", no "/" / "\\")               -> 422 on traversal

    project_id is itself regex-validated so the snapshot lookup can never traverse
    outside PROJECTS_ROOT.
    """
    _validated_project_id(project_id)
    canonical_class, qty_floor, _loc = _validated_inventory_query(
        material_class, min_qty, location
    )

    prefix = _CLASS_ID_PREFIX[canonical_class]
    view = _load_inventory_availability(project_id)

    def _passes(entry: dict) -> bool:
        mid = entry.get("material_id") or ""
        if not mid.startswith(prefix):
            return False
        qty = entry.get("qty_available")
        # qty_available may be null (unknown qty) — D-07: unknown is NOT excluded by a
        # positive floor; only an explicit number below the floor is filtered out.
        if qty_floor > 0 and isinstance(qty, (int, float)) and qty < qty_floor:
            return False
        return True

    listings = [e for e in view if _passes(e)]
    return JSONResponse(
        {
            "project_id": project_id,
            "material_class": canonical_class,
            "min_qty": qty_floor,
            "count": len(listings),
            "availability": listings,
        }
    )


# ====================================================================== #
# Marketplace — binding-reserve holds (MKT-03 / MKT-06)
# ----------------------------------------------------------------------
# The stateful supply half: a hold that BINDS. Backed by the SQLite
# HoldStore (src/marketplace/holds.py) — atomic guarded decrement (no
# double-booking), lazy TTL expiry (no scheduler), supplier confirm, and
# an append-only event log. A SINGLE shared store instance is process-wide
# (its internal RLock serializes the one connection across the FastAPI
# threadpool); cross-process atomicity comes from SQLite's single writer.
# ====================================================================== #
from pydantic import BaseModel, Field  # noqa: E402
from marketplace.holds import (  # noqa: E402
    HoldError,
    HoldNotFound,
    HoldStore,
    IdempotencyConflict,
    IllegalTransition,
    InsufficientStock,
    UnknownListing,
)
from marketplace import catalog as _catalog  # noqa: E402
from marketplace.suppliers import SupplierNotFound, SupplierStore  # noqa: E402

# Marketplace ids (listing/organiser/supplier/idempotency/hold) — a closed character
# set so a path/query id can never traverse or inject (clone the _validated_project_id
# discipline). hold ids are uuid4().hex (32 lowercase hex) and fit this set.
_MK_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")

_HOLD_STORE: HoldStore | None = None
_SUPPLIER_STORE: SupplierStore | None = None
_MARKETPLACE_DB = PROJECTS_ROOT / "marketplace.db"


def _hold_store() -> HoldStore:
    """Lazily build the process-wide hold store (DB under PROJECTS_ROOT)."""
    global _HOLD_STORE
    if _HOLD_STORE is None:
        PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
        _HOLD_STORE = HoldStore(_MARKETPLACE_DB)
    return _HOLD_STORE


def _supplier_store() -> SupplierStore:
    """Lazily build the process-wide supplier registry (same DB file as holds)."""
    global _SUPPLIER_STORE
    if _SUPPLIER_STORE is None:
        PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
        _SUPPLIER_STORE = SupplierStore(_MARKETPLACE_DB)
    return _SUPPLIER_STORE


def _mk_id(value: str, field: str) -> str:
    if not _MK_ID.match(value or ""):
        raise HTTPException(status_code=422, detail=f"invalid {field}")
    return value


def _store_call(fn):
    """Run a store call, mapping its typed failures onto honest HTTP statuses.

    InsufficientStock -> 409 (the no-double-book rejection, with remaining stock);
    IllegalTransition -> 409; UnknownListing/HoldNotFound -> 404; IdempotencyConflict
    -> 422; any other HoldError -> 400. Never a bare 500 for a domain rejection.
    """
    try:
        return fn()
    except InsufficientStock as e:
        raise HTTPException(status_code=409, detail={
            "error": "insufficient_stock", "listing_id": e.listing_id,
            "requested": e.qty, "available": e.available,
        })
    except IllegalTransition as e:
        raise HTTPException(status_code=409, detail={"error": "illegal_transition", "message": str(e)})
    except (UnknownListing, HoldNotFound) as e:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": str(e)})
    except IdempotencyConflict as e:
        raise HTTPException(status_code=422, detail={"error": "idempotency_conflict", "message": str(e)})
    except HoldError as e:
        raise HTTPException(status_code=400, detail={"error": "hold_error", "message": str(e)})


class _RegisterListingBody(BaseModel):
    listing_id: str = Field(pattern=_MK_ID.pattern)
    total_units: float = Field(gt=0)
    material_id: str = ""
    supplier_id: str = ""
    unit: str = ""
    source_url: str = ""


class _PlaceHoldBody(BaseModel):
    listing_id: str = Field(pattern=_MK_ID.pattern)
    organiser_id: str = Field(pattern=_MK_ID.pattern)
    qty: float = Field(gt=0)
    idempotency_key: str = Field(pattern=_MK_ID.pattern)
    supplier_id: str | None = None
    ttl_seconds: int | None = Field(default=None, gt=0, le=86400)


class _ConfirmBody(BaseModel):
    supplier_id: str | None = None


class _CancelBody(BaseModel):
    organiser_id: str | None = None


@app.post("/api/marketplace/listings", status_code=201)
def register_listing(body: _RegisterListingBody):
    """Seed/register a listing's bindable pool (the marketplace populates this from the
    inventory snapshots; an unknown-quantity listing is seeded total_units=1 = exclusive
    lock by the caller). Idempotent — re-registering never wipes live holds."""
    _store_call(lambda: _hold_store().register_listing(
        body.listing_id, total_units=body.total_units, material_id=body.material_id,
        supplier_id=body.supplier_id, unit=body.unit, source_url=body.source_url,
    ))
    return _store_call(lambda: _hold_store().availability(body.listing_id))


@app.post("/api/marketplace/holds", status_code=201)
def place_hold(body: _PlaceHoldBody):
    """Place a binding hold (atomic, no double-book). 409 if stock is insufficient."""
    kw = {} if body.ttl_seconds is None else {"ttl_seconds": body.ttl_seconds}
    return _store_call(lambda: _hold_store().place_hold(
        listing_id=body.listing_id, organiser_id=body.organiser_id, qty=body.qty,
        idempotency_key=body.idempotency_key, supplier_id=body.supplier_id, **kw,
    ))


@app.get("/api/marketplace/holds")
def list_holds(organiser_id: str):
    """Holds for one organiser (live remaining-seconds computed read-time)."""
    _mk_id(organiser_id, "organiser_id")
    return {"organiser_id": organiser_id, "holds": _hold_store().list_for_organiser(organiser_id)}


@app.get("/api/marketplace/holds/incoming")
def incoming_holds(supplier_id: str):
    """The supplier inbox: holds awaiting confirm + active ones (the supplier screen)."""
    _mk_id(supplier_id, "supplier_id")
    return {"supplier_id": supplier_id, "holds": _hold_store().list_for_supplier(supplier_id)}


@app.get("/api/marketplace/holds/{hold_id}")
def get_hold(hold_id: str):
    _mk_id(hold_id, "hold_id")
    hold = _hold_store().get_hold(hold_id)
    if hold is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "hold_id": hold_id})
    return hold


@app.post("/api/marketplace/holds/{hold_id}/confirm")
def confirm_hold(hold_id: str, body: _ConfirmBody | None = None):
    _mk_id(hold_id, "hold_id")
    sup = body.supplier_id if body else None
    return _store_call(lambda: _hold_store().confirm_hold(hold_id, supplier_id=sup))


@app.post("/api/marketplace/holds/{hold_id}/decline")
def decline_hold(hold_id: str, body: _ConfirmBody | None = None):
    _mk_id(hold_id, "hold_id")
    sup = body.supplier_id if body else None
    return _store_call(lambda: _hold_store().decline_hold(hold_id, supplier_id=sup))


@app.post("/api/marketplace/holds/{hold_id}/cancel")
def cancel_hold(hold_id: str, body: _CancelBody | None = None):
    _mk_id(hold_id, "hold_id")
    org = body.organiser_id if body else None
    return _store_call(lambda: _hold_store().cancel_hold(hold_id, organiser_id=org))


@app.post("/api/marketplace/holds/{hold_id}/collect")
def collect_hold(hold_id: str):
    _mk_id(hold_id, "hold_id")
    return _store_call(lambda: _hold_store().collect_hold(hold_id))


@app.get("/api/marketplace/listings/{listing_id}/availability")
def listing_availability(listing_id: str):
    _mk_id(listing_id, "listing_id")
    return _store_call(lambda: _hold_store().availability(listing_id))


@app.get("/api/marketplace/materials")
def marketplace_materials(
    project_id: str = "primavera-demo",
    lon: float = _catalog._SITE_LONLAT[0],
    lat: float = _catalog._SITE_LONLAT[1],
    radius_km: float = 15.0,
    group: str = "archetype",
):
    """The canonical serve view the frontend MaterialsProvider consumes.

    Joins the persisted inventory snapshots to the 10 frozen archetypes, computes
    transport carbon, derives supplier pins, applies the radius filter, and SEEDS the
    bindable hold pools so a subsequent ``POST /api/marketplace/holds`` binds real stock.
    Returns ``{status, asOf, items}`` (status is weakest-input-wins — never a fake live;
    no snapshots => honest ``unavailable`` with an empty list).
    """
    _validated_project_id(project_id)
    if radius_km <= 0 or radius_km > 500:
        raise HTTPException(status_code=422, detail="radius_km out of range")
    if group not in ("archetype", "listing"):
        raise HTTPException(status_code=422, detail="group must be 'archetype' or 'listing'")
    result = _catalog.build_catalog(
        project_id, center=(lon, lat), radius_km=radius_km, group=group,
        projects_root=PROJECTS_ROOT, store=_hold_store(),
    )
    return {
        "status": result["status"], "asOf": result["as_of"], "items": result["items"],
        "count": result["count"], "listingCount": result["listing_count"],
        "rawCount": result["raw_count"],  # listings before variant-dedup (transparency)
    }


@app.get("/api/marketplace/catalogue")
def marketplace_catalogue(project_id: str = "primavera-demo"):
    """The FULL material catalogue (every archetype) with datasheet-sourced specs +
    per-field provenance tiers. The Materials stage renders this so the organiser sees
    the whole reclaimed-material reference; ``bindable`` items carry a live listing a
    hold can reserve, the rest are honest REFERENCE entries (real specs, no live stock)."""
    _validated_project_id(project_id)
    result = _catalog.reference_catalogue(
        project_id, projects_root=PROJECTS_ROOT, store=_hold_store(),
    )
    return {
        "status": result["status"], "asOf": result["as_of"], "items": result["items"],
        "count": result["count"], "bindableCount": result["bindable_count"],
    }


class _SupplierBody(BaseModel):
    supplier_id: str = Field(pattern=_MK_ID.pattern)
    name: str = Field(min_length=1, max_length=200)
    contact_email: str = ""
    town: str = ""


@app.post("/api/marketplace/suppliers", status_code=201)
def register_supplier(body: _SupplierBody):
    """Onboard a supplier (MKT-01). ``verified`` is always False here — trust is a
    separate admin gate, never self-asserted at onboarding."""
    return _supplier_store().register(
        body.supplier_id, name=body.name, contact_email=body.contact_email, town=body.town,
    )


@app.get("/api/marketplace/suppliers")
def list_suppliers():
    return {"suppliers": _supplier_store().list()}


@app.get("/api/marketplace/suppliers/{supplier_id}")
def get_supplier(supplier_id: str):
    _mk_id(supplier_id, "supplier_id")
    try:
        return _supplier_store().get(supplier_id)
    except SupplierNotFound:
        raise HTTPException(status_code=404, detail={"error": "not_found", "supplier_id": supplier_id})


@app.get("/api/marketplace/suppliers/{supplier_id}/listings")
def supplier_listings(supplier_id: str):
    """A supplier's listing pools with live held/available split (their 'My listings')."""
    _mk_id(supplier_id, "supplier_id")
    return {"supplier_id": supplier_id, "listings": _hold_store().listings_for_supplier(supplier_id)}
