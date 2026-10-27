"""Phase-4 Structural-Geometry stage orchestrator (GEOM-01/04/05/06).

The single Wave-3 spine — a clone of ``core.core.run_core_stage`` crossed to the geom seam.
It wires the Wave-2 request assembler + the injected Rhino.Compute client (Fake | Reference |
Live) + the Wave-3 ``decode_mesh`` into a cache-first, fail-safe, validate-then-write pipeline
keyed on the Phase-3 footprint hash, and emits:

* ``structure.gltf`` + ``structure.obj``  — the decoded mesh (metres + Y-up + origin-translated);
* ``gh_response.json``                     — the FROZEN contract artifact (ajv/jsonschema-valid);
* ``gh_meta.json``                         — the NON-contract sidecar (egress / mass-balance /
                                             certification-needs / shadow-coverage / PREVIEW label);
* ``provenance.json``                      — MERGED ledger labelling Karamba "live-only,
                                             pre-screening, requires engineering sign-off" (GEOM-04).

ORCHESTRATOR DECISION (RESEARCH §Architectural Responsibility Map): the authoritative Wave-1 RED
tests (``tests/test_geom_stage.py`` / ``test_geom_e2e.py`` / ``test_geom_provenance.py``) import
``from geom.geom import run_gh_stage`` and call it directly with a Python ``client`` whose
``.solve(gh_request)`` returns a ``gh_response`` dict. So the spine is PYTHON and the decode is the
in-process ``geom.decode.decode_mesh`` (NOT a child-process bridge) — the tests are authoritative
over the plan prose's Node/child-process sketch. The plan's defence-in-depth re-validation survives:
``decode_mesh``'s own ``python -m geom.decode`` CLI re-validates the gh_response when the LIVE/Node
path persists it, and this spine ajv/jsonschema-validates the response on receipt regardless.

Determinism (GEOM-05): zero randomness — the gh_response is produced by the injected client
(recorded fixture / PREVIEW generator / live solve) and the decode is a pure transform, so two
fresh runs over the same footprint produce byte-identical ``structure.gltf``.

Fail-safe (T-04-11): a solve / decode / validation failure marks the stage NOT done, persists the
not-done manifest (resume re-runs), and writes NO partial artifact.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from shapely.ops import unary_union  # BASE dep (shapely) — NO rhino3dm pulled into the gate path

from geom.constants import (
    FLOW_BUFFER_M,
    GRID_SPACING_M,
    PEAK_SUN_HOUR,
    PREVIEW_LABEL,
)
from geom.decode import DecodeResult, decode_mesh
from geom.request import build_gh_request, sun_vector
from geom.shadow_sim import _footprint_polygon, _project, _roof_polygons, shadow_coverage
from manifest.manifest import Manifest, content_hash
from provenance.ledger import ProvenanceLedger
from validate.validate import validate

_STAGE = "gh_response"
_GH_RESPONSE_NAME = "gh_response.json"
_GH_META_NAME = "gh_meta.json"
_GLTF_NAME = "structure.gltf"
_OBJ_NAME = "structure.obj"
_SIDECAR_VERSION = "1.0.0-sidecar"

#: GEOM-04 provenance vocabulary — the structural result is NEVER "certified"/"engineer-approved".
_KARAMBA_LABEL = "live-only, pre-screening, requires engineering sign-off"

#: GEOM-06 acceptance input — the demo must confirm >= this footprint-shadow coverage at peak sun.
COVERAGE_FLOOR = 0.80


class RhinoComputeError(RuntimeError):
    """Typed solve/decode failure mirroring ``geom.client.RhinoComputeError`` so the
    fail-stage-NOT-done test can ``pytest.raises`` against a stable name in this spine."""


class _SolveClient(Protocol):
    """The seam every injectable client satisfies (FakeRhinoClient / ReferenceGeometryClient...)."""

    def solve(self, gh_request: dict) -> dict: ...


# --------------------------------------------------------------------------- #
# Manifest persistence — clone of core.core._load_manifest (no restore ctor).
# The stage is keyed on the OUTPUT DIRECTORY (the tests pass an arbitrary out_dir,
# not a project id), so the manifest lives at <out_dir>/manifest.json and the
# project_id is the out_dir's leaf name (purely cosmetic — the cache key is the hash).
# --------------------------------------------------------------------------- #
def _load_manifest(out_dir: Path) -> Manifest:
    """Load a persisted ``manifest.json`` under ``out_dir`` if present, else a fresh one.

    Cache-across-calls hinges on this: the FIRST ``run_gh_stage`` writes the manifest with
    ``gh_response`` done; a SECOND call reloads that state so ``is_reusable`` can short-circuit
    to a cache hit with ZERO solve (clone ``core.core._load_manifest`` / ``crowd.crowd``).
    """
    m = Manifest(out_dir.name, out_dir.parent)
    # Force the project_dir to BE out_dir (the leaf may not equal project_id semantics).
    m.project_dir = out_dir
    manifest_path = out_dir / "manifest.json"
    if not manifest_path.exists():
        return m
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return m  # corrupt manifest -> treat as fresh (everything re-runs)
    if "created_at" in data:
        m.created_at = data["created_at"]
    for st in data.get("stages", []):
        name = st.get("name")
        if name in m._stages:  # only restore known stages (DAG order is fixed)
            m._stages[name].update(st)
    return m


def _default_client() -> _SolveClient:
    """The DEMO DEFAULT client (no EC2): the PREVIEW reference generator, in-process.

    Lazy-imported so ``import geom.geom`` stays light and never pulls the live axios path.
    ``RHINO_LIVE`` opt-in (the EC2 path) is owned by the Node ``geom.client`` seam; this
    Python spine defaults to the LABELLED PREVIEW generator (RESEARCH §Faithful-vs-mock).
    """
    from geom.reference_generator import build_reference  # noqa: PLC0415 (lazy)

    class _ReferencePreviewClient:
        """Adapts ``build_reference`` to the ``.solve(gh_request) -> gh_response`` seam."""

        def solve(self, gh_request: dict) -> dict:
            footprint = gh_request.get("IN_Footprint")
            flow_vectors = gh_request.get("IN_FlowVectors", [])
            return build_reference(footprint, flow_vectors)["gh_response"]

    return _ReferencePreviewClient()


def run_gh_stage(
    footprint: dict,
    flow_vectors: list[dict],
    *,
    client: _SolveClient | None = None,
    out_dir: Path | str,
    brief_date: str | None = None,
) -> dict:
    """Run the structural-geometry stage: cache-first solve -> decode -> validate-then-write.

    Args:
        footprint: the ``footprint.json`` dict (``{schema_version, crs, polygons}``) — its
            content_hash IS the Phase-3 footprint cache key (RESEARCH).
        flow_vectors: the crowd_grid flow-vector list (``[{origin,destination}, ...]``) — already
            the frozen ``gh_request`` line shape, NO reshape.
        client: the injected solve seam. ``None`` -> the PREVIEW ``ReferenceGeometryClient`` default
            (no EC2). Tests inject ``FakeRhinoClient``; ``LiveRhinoClient`` is the Node ``RHINO_LIVE``
            opt-in.
        out_dir: directory the four artifacts + ``manifest.json`` live under (the cache lives here).
        brief_date: the brief date the deterministic sun vector is computed for (default the
            Parc-del-Fòrum demo date in ``request.sun_vector``).

    Returns:
        A dict carrying the decoded geometry summary + provenance text (the
        ``test_geom_provenance`` gate reads the Karamba label from this dict).

    Raises:
        RhinoComputeError on a solve / decode / validation failure — the stage is left NOT done,
        the not-done manifest is persisted (resume re-runs), and NO partial artifact is written.
    """
    out = Path(out_dir)
    sun = sun_vector(brief_date)

    # ── 1) CACHE CHECK ────────────────────────────────────────────────────────
    # The Phase-3 footprint hash is the cache key, folded with every tunable geom constant
    # (retuning ANY pre-run constant must be a MISS — Pitfall D / MN-02).
    input_hash = content_hash(
        {
            "footprint": content_hash(footprint),
            "flow_vectors": content_hash(flow_vectors),
            "sun": [round(c, 12) for c in sun],
            "flow_buffer_m": FLOW_BUFFER_M,
            "grid_spacing_m": GRID_SPACING_M,  # generative PREVIEW tunable (MJ-02)
            "peak_sun_hour": PEAK_SUN_HOUR,
        }
    )
    m = _load_manifest(out)
    if (
        m.is_reusable(_STAGE, input_hash, _STAGE)
        and (out / _GLTF_NAME).exists()
        and (out / _OBJ_NAME).exists()
    ):
        # Cache hit: serve the persisted artifacts with ZERO solve. Re-emit the derived
        # sidecar + provenance (mirrors core.py / crowd.py WR-02), then return.
        gh_response = json.loads((out / _GH_RESPONSE_NAME).read_text(encoding="utf-8"))
        # MJ-01: the two decoded meshes (structure.gltf/.obj) are served downstream (Phase 6
        # render, the UI) but were gated by bare `.exists()` — a truncated/tampered gltf would
        # serve as a valid hit (the T-03-08 lesson, applied to all three artifacts). Decode is
        # deterministic + cheap vs a solve, so pass out_dir=out: the write OVERWRITES and thereby
        # re-verifies the on-disk meshes from the (already hash-checked) gh_response.
        result = decode_mesh(gh_response["OUT_Mesh"]["b64"], out_dir=out)
        return _finalize(out, footprint, flow_vectors, gh_response, result, sun)

    # ── 2) MISS: mark running, solve + decode, fail-safe on ANY error ─────────
    m.mark_running(_STAGE)
    if client is None:
        client = _default_client()
    try:
        gh_request = build_gh_request(footprint, flow_vectors, sun)  # validates (validate-then-solve)
        gh_response = client.solve(gh_request)
        # ajv/jsonschema-validate the gh_response ON RECEIPT, before any write (T-04-17).
        validate(gh_response, "gh_response")

        # Decode in-process. NOTE: the LIVE/Node path persists gh_response.json and re-validates
        # it inside `python -m geom.decode` (defence-in-depth, WARNING 7); this in-process spine
        # has already validated it on receipt above.
        result = decode_mesh(gh_response["OUT_Mesh"]["b64"], out_dir=out)
    except Exception as exc:
        # Failure-safe: stage NOT done, NO partial artifact. Persist the not-done manifest so
        # resume re-runs, then surface a typed error (clone core.py lines 133-138).
        m.mark_failed(_STAGE)
        m.write(out / "manifest.json")
        _remove_partial(out)
        # A client's own RhinoComputeError (the seam's typed failure — same name across the Node
        # geom.client + the test conftest) propagates UNWRAPPED so callers catch a stable type;
        # any other failure (decode/validation) is wrapped into this module's RhinoComputeError.
        if type(exc).__name__ == "RhinoComputeError":
            raise
        raise RhinoComputeError(f"gh stage failed: {exc}") from exc

    # ── 3) VALIDATE-THEN-WRITE: gh_response.json (decoded artifacts already on disk) ──
    out.mkdir(parents=True, exist_ok=True)
    (out / _GH_RESPONSE_NAME).write_text(json.dumps(gh_response, indent=2), encoding="utf-8")
    m.mark_done(_STAGE, _GH_RESPONSE_NAME, input_hash, content_hash(gh_response))
    m.write(out / "manifest.json")

    # ── 4) SIDECAR + PROVENANCE + shadow coverage ────────────────────────────
    return _finalize(out, footprint, flow_vectors, gh_response, result, sun)


# --------------------------------------------------------------------------- #
# Finalize: sidecar + merged provenance + the returned summary dict.
# Called on BOTH the miss path and the cache-hit path (re-emit, idempotent).
# --------------------------------------------------------------------------- #
def _finalize(
    out: Path,
    footprint: dict,
    flow_vectors: list[dict],
    gh_response: dict,
    result: DecodeResult,
    sun: tuple[float, float, float] | list[float],
) -> dict:
    coverage, coverage_basis = _coverage(footprint, result, sun)
    # GEOM-06 floor: REPORT (never raise) — cloning the Phase-3 infeasibility.json discipline so a
    # shortfall is on-disk and honest, but the PREVIEW demo still produces a structure (MJ-04).
    _report_coverage_floor(out, coverage, coverage_basis)
    _write_sidecar(out, footprint, flow_vectors, gh_response, coverage, coverage_basis, result, sun)
    prov = _write_provenance(out, gh_response, coverage, coverage_basis)
    return {
        "gh_response": gh_response,
        "bbox_span_m": list(result.bbox_span_m),
        "shadow_coverage_pct": coverage,
        "shadow_coverage_basis": coverage_basis,
        "provenance": prov,
        "preview_label": PREVIEW_LABEL,
        "karamba": _KARAMBA_LABEL,
    }


def _coverage(
    footprint: dict,
    result: DecodeResult,
    sun: tuple[float, float, float] | list[float],
) -> tuple[float, str]:
    """Deterministic offline shadow coverage of the footprint at peak sun (GEOM-06).

    MJ-04: project the ACTUAL decoded mesh triangles (``result.roof_faces_m`` — the real roof,
    origin-translated to the footprint min-corner) onto the ground along the sun vector, NOT the
    mesh bounding-box rectangle. A bbox rectangle scores ≈1.0 by construction regardless of the real
    roof shape — a vacuous measurement in a project whose discipline is honest labelling. Projecting
    the real faces measures what the decoded roof actually shades.

    Returns ``(coverage, basis)`` where ``basis`` is the HONEST provenance label of how the number
    was computed: ``"roof-mesh-projection"`` when real decoded faces were available, or
    ``"bbox-projection PREVIEW-grade"`` as the labelled fallback (so Phase 5b never consumes a
    bbox-grade number as a roof-mesh measurement).
    """
    roof_faces = getattr(result, "roof_faces_m", None)
    if roof_faces:
        return shadow_coverage(roof_faces, footprint, sun), "roof-mesh-projection"

    # Labelled fallback — no decoded faces available (older DecodeResult). Project the bbox rect
    # but say so honestly: bbox-projection PREVIEW-grade, NOT a roof-mesh measurement.
    span_x, span_z = float(result.bbox_span_m[0]), float(result.bbox_span_m[1])
    roof = [(0.0, 0.0), (span_x, 0.0), (span_x, span_z), (0.0, span_z)]
    return shadow_coverage(roof, footprint, sun), "bbox-projection PREVIEW-grade"


def _projected_shadow_polygon(
    footprint: dict,
    result: DecodeResult,
    sun: tuple[float, float, float] | list[float],
) -> dict:
    """Q1 (Phase-5b): the origin-translated projected-shadow polygon as PLAIN coordinates.

    The Phase-5b cooling-acceptance gate's GATE-01 coverage criterion needs the REAL projected
    shadow over the priority cells — but it must stay BASE-TIER (shapely-only, NO rhino3dm). The
    roof faces live in ``OUT_Mesh.b64`` (rhino3dm to decode), so the cleanest base-tier path is for
    THIS Phase-4 stage — which has already decoded the mesh — to persist the projected shadow as
    plain coords into the ``gh_meta.json`` sidecar. The gate then consumes coordinates, never the
    mesh (Q1 decision; the OUT_Mesh-decode-in-gate fallback was REJECTED because it pulls rhino3dm
    into the gate tier).

    This reproduces the SAME projection + frame as ``geom._coverage`` / ``shadow_sim.shadow_coverage``
    so the persisted polygon is byte-consistent with the ``shadow_coverage_pct`` already recorded:

      * project each roof face ring onto z=0 along ``sun`` via the shadow_sim recipe
        ``(x - z*sx/sz, y - z*sy/sz)``, then ``unary_union`` → the shadow geometry;
        basis ``"roof-mesh-projection"`` when real decoded faces are available, else the labelled
        ``"bbox-projection PREVIEW-grade"`` fallback (project the bbox rectangle).
      * The roof polygons are already in the near-origin frame (decode origin-translates the mesh to
        the footprint min-corner; the PREVIEW roof is built at (0,0)) — the SAME frame
        ``shadow_coverage`` puts the footprint in after translating it by ``-footprint_min_corner``.
        We record that ``min_corner_m`` so the gate can translate its priority-cell centres by the
        SAME offset before intersecting (translate-both discipline — Pitfall 8). Per-disjoint-polygon
        exteriors are kept (``polygons_xy_m``) so disjoint shade is preserved (never hull-collapsed).

    Returns:
        ``{"basis": str, "min_corner_m": [minx, miny], "polygons_xy_m": [[[x, y], ...], ...]}``.
        ``polygons_xy_m`` is a list of exterior coordinate rings (one per disjoint shadow polygon).
    """
    fp = _footprint_polygon(footprint)
    minx, miny, _maxx, _maxy = fp.bounds

    roof_faces = getattr(result, "roof_faces_m", None)
    if roof_faces:
        rings = _roof_polygons(roof_faces)
        basis = "roof-mesh-projection"
    else:
        # Labelled fallback — no decoded faces (older DecodeResult). Project the bbox rectangle.
        span_x, span_z = float(result.bbox_span_m[0]), float(result.bbox_span_m[1])
        rings = _roof_polygons(
            [(0.0, 0.0), (span_x, 0.0), (span_x, span_z), (0.0, span_z)]
        )
        basis = "bbox-projection PREVIEW-grade"

    shadows = [_project(ring, sun) for ring in rings]
    shadows = [s for s in shadows if s.is_valid and s.area > 0]

    polygons_xy_m: list[list[list[float]]] = []
    if shadows:
        shadow = unary_union(shadows)
        # unary_union yields a Polygon or MultiPolygon; normalize to a list of per-polygon exteriors
        # so disjoint shade survives (never collapsed to a single hull).
        geoms = list(getattr(shadow, "geoms", [shadow]))
        for g in geoms:
            exterior = getattr(g, "exterior", None)
            if exterior is not None:
                polygons_xy_m.append([[float(x), float(y)] for x, y in exterior.coords])

    return {
        "basis": basis,
        "min_corner_m": [float(minx), float(miny)],
        "polygons_xy_m": polygons_xy_m,
    }


def _report_coverage_floor(out: Path, coverage: float, coverage_basis: str) -> None:
    """REPORT (never raise) a GEOM-06 coverage shortfall below ``COVERAGE_FLOOR`` (MJ-04).

    Clones the Phase-3 ``infeasibility.json`` report-not-silent discipline: if the measured coverage
    is below the floor, write ``coverage_shortfall.json`` so the shortfall is on-disk and honest —
    but DO NOT raise, so the PREVIEW demo still produces a structure (the floor is a Phase-5b
    acceptance input, not a hard PREVIEW gate). A run at/above the floor removes any stale report so
    contradictory on-disk state never persists.
    """
    out.mkdir(parents=True, exist_ok=True)
    report = out / "coverage_shortfall.json"
    if coverage < COVERAGE_FLOOR:
        report.write_text(
            json.dumps(
                {
                    "schema_version": _SIDECAR_VERSION,
                    "stage": _STAGE,
                    "shadow_coverage_pct": round(coverage, 6),
                    "coverage_floor": COVERAGE_FLOOR,
                    "coverage_basis": coverage_basis,
                    "human_readable": (
                        f"Shadow coverage {coverage:.3f} is below the {COVERAGE_FLOOR} floor "
                        f"(basis: {coverage_basis}). REPORTED not raised — PREVIEW still produces "
                        "a structure; this is a Phase-5b cooling-acceptance input, not a PREVIEW gate."
                    ),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    else:
        report.unlink(missing_ok=True)


def _remove_partial(out: Path) -> None:
    """Remove any decoded artifact a half-finished decode may have written (no partial on failure).

    Also clears any prior ``coverage_shortfall.json`` (MJ-04) so a failed re-run never leaves a
    coverage report describing a structure that is no longer on disk (contradictory-state discipline).
    """
    for name in (_GLTF_NAME, _OBJ_NAME, _GH_RESPONSE_NAME, "coverage_shortfall.json"):
        (out / name).unlink(missing_ok=True)


def _write_sidecar(
    out: Path,
    footprint: dict,
    flow_vectors: list[dict],
    gh_response: dict,
    coverage: float,
    coverage_basis: str,
    result: DecodeResult,
    sun: tuple[float, float, float] | list[float],
) -> None:
    """Write the NON-contract ``gh_meta.json`` sidecar (clone core.py ``_write_sidecar``).

    Carries the instructor extras the FROZEN ``gh_response`` (additionalProperties:false) cannot
    hold — egress clearance, the rented/recovered/new mass-balance, certification-needs, the shadow
    coverage, and the PREVIEW label. Deliberately NOT validated against any frozen schema (it is not
    a contract artifact); ``schema_version`` is the sidecar marker ``1.0.0-sidecar`` (T-04-13).

    Q1 (Phase-5b): also carries ``shadow_polygon_m`` — the origin-translated projected-shadow polygon
    as PLAIN coordinates (basis + ``min_corner_m`` + per-disjoint-polygon exteriors). This is the
    base-tier Phase-5b GATE-01 input: it lets ``src/acceptance/coverage.py`` compute projected-shadow
    ∩ priority-cell coverage WITHOUT pulling rhino3dm into the gate (consume coords, never re-decode
    the mesh). The polygon shares the frame ``shadow_coverage`` uses (translate by
    ``-min_corner_m``), so the gate translates its priority-cell centres by the SAME offset.
    """
    bom = gh_response["OUT_BOM"]
    sidecar = {
        "schema_version": _SIDECAR_VERSION,
        "stage": _STAGE,
        "preview_label": PREVIEW_LABEL,
        "egress": {
            # Annotatable on a plan/section: every culled route keeps a full egress lane clear.
            "clearance_width_m": FLOW_BUFFER_M * 2,
            "flow_vector_count": len(flow_vectors),
        },
        "mass_balance": {
            # Material Recovery Inventory inputs — ASSUMED-grade, labelled, for the Phase-5/7
            # EN 15804+A2 table (instructor). The Phase-5 carbon stage owns the real values.
            "label": "ASSUMED",
            "scaffold_kg_rented": 0.0,
            "membrane_m2_recovered": 0.0,
            "fixings_kg_new": 0.0,
        },
        "certification_needs": [
            "wind-load certification",
            "engineering stamp",
            "on-site heat-safety sign-off",
        ],
        "shadow_coverage_pct": coverage,
        # MJ-04: honest provenance of HOW coverage was measured — "roof-mesh-projection" (real
        # decoded faces) or "bbox-projection PREVIEW-grade" (labelled fallback). Phase 5b must not
        # consume a bbox-grade number as a roof-mesh measurement.
        "shadow_coverage_basis": coverage_basis,
        "coverage_floor": COVERAGE_FLOOR,
        # Q1 (Phase-5b GATE-01): the projected shadow as plain coords, origin-translated to the SAME
        # min-corner shadow_coverage uses — consumed base-tier by src/acceptance/coverage.py so the
        # gate never re-decodes the mesh (no rhino3dm in the gate tier).
        "shadow_polygon_m": _projected_shadow_polygon(footprint, result, sun),
        "bom": {"pillars": bom["pillars"], "membrane_m2": bom["membrane_m2"]},
        "note": (
            "non-contract sidecar; PREVIEW/ASSUMED-grade. Karamba is live-only pre-screening, "
            "NOT certification. The frozen gh_response is never amended (additionalProperties:false)."
        ),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / _GH_META_NAME).write_text(json.dumps(sidecar, indent=2), encoding="utf-8")


def _write_provenance(
    out: Path, gh_response: dict, coverage: float, coverage_basis: str
) -> dict:
    """Emit ``provenance.json`` for the geom stage, MERGING with any existing ledger (GEOM-04/05).

    MERGES (clone core.py ``_write_provenance``): entries from OTHER stages (the crowd stage's
    ``crowd_density`` tier, the climate UTCI sourcing, the core score) are preserved; only this
    stage's own prior entries are replaced. The whole merged ledger is validated against the frozen
    contract before write.

    Tiers (GEOM-04, never "certified"/"engineer-approved"):
      * ``geometry`` DERIVED — from the PREVIEW generator (live solve would be GROUNDED);
      * ``bom``      DERIVED — pillar count + membrane m² from the PREVIEW grid;
      * ``karamba``  ASSUMED — "live-only, pre-screening, requires engineering sign-off";
      * ``sun_vector`` ASSUMED — peak-sun-hour A1;
      * ``shadow_coverage_pct`` DERIVED — deterministic offline shadow projection (GEOM-06).
    """
    prov_path = out / "provenance.json"
    prior_entries: list[dict] = []
    if prov_path.exists():
        try:
            prior_entries = [
                e
                for e in json.loads(prov_path.read_text(encoding="utf-8")).get("entries", [])
                if e.get("stage") != _STAGE
            ]
        except (OSError, json.JSONDecodeError):
            prior_entries = []  # corrupt ledger -> rebuild with this stage's entries only

    bom = gh_response["OUT_BOM"]
    ledger = ProvenanceLedger()
    ledger.derived(
        "geometry",
        PREVIEW_LABEL,
        source=(
            "PREVIEW reference geometry (offline stand-in for the live Rhino/Grasshopper solve); "
            "decoded to metres + Y-up + origin-translated .gltf/.obj"
        ),
        stage=_STAGE,
    )
    ledger.derived(
        "bom",
        {"pillars": bom["pillars"], "membrane_m2": bom["membrane_m2"]},
        source="DERIVED-preview from the PREVIEW pillar grid after the FAITHFUL flow-cull",
        stage=_STAGE,
    )
    ledger.assumed(
        "karamba",
        _KARAMBA_LABEL,
        source=(
            "Karamba is live-only, pre-screening — NOT certification; requires wind-load "
            "certification + an engineering sign-off (GEOM-04). Never run offline."
        ),
        stage=_STAGE,
    )
    ledger.assumed(
        "sun_vector",
        "peak-sun-hour (A1)",
        source="deterministic IN_SunVector at PEAK_SUN_HOUR over Parc del Fòrum (ASSUMED A1)",
        stage=_STAGE,
    )
    ledger.derived(
        "shadow_coverage_pct",
        round(coverage, 4),
        # MJ-04: label HONESTLY by the actual basis — "roof-mesh-projection" projects the real
        # decoded faces; "bbox-projection PREVIEW-grade" is the labelled fallback. Never claim a
        # roof-mesh measurement when the number came from the bbox rectangle.
        source=(
            f"deterministic offline shadow projection ({coverage_basis}) onto the footprint plane "
            f"at peak sun; reported against the {COVERAGE_FLOOR} GEOM-06 floor (report-not-raise)"
        ),
        stage=_STAGE,
        unit="fraction",
    )

    artifact = ledger.to_artifact()
    artifact["entries"] = prior_entries + artifact["entries"]
    validate(artifact, "provenance_ledger")  # validate the WHOLE merged ledger before write
    out.mkdir(parents=True, exist_ok=True)
    prov_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return artifact
