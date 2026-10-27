"""GATE-03 — the wired cooling-acceptance gate stage (a structural clone of
``selection.run_selection_stage``).

The honesty keystone made executable. ``build_verdict`` is the pure both-required
comparator the tests drive directly; ``run_acceptance_stage`` clones the
selection-stage cache-first / validate-then-write / fail-safe seam for the wired stage:
load the persisted upstream artifacts -> GATE-01 projected-shadow coverage -> GATE-02
(1-tau) mean delta over the SAME shaded priority cells -> assemble the BOTH-REQUIRED
7-field verdict -> validate-then-write ``acceptance.json`` -> write the Comfort-Gap
``acceptance_meta.json`` sidecar -> append the provenance ledger -> ``mark_done``.

THE LOAD-BEARING HONESTY RULE (A6 / Pitfall 6 — the never-silently-ship-a-FAIL
non-negotiable): a FAIL verdict is a SUCCESSFUL stage outcome — the artifact is WRITTEN
with ``verdict:"FAIL"`` and ``mark_done`` runs. The fail-safe (``mark_failed``, no
artifact) is reserved for GENUINE INTERNAL ERRORS only (a missing upstream artifact, a
validation crash, a tampered threshold). A FAIL routed through the fail-safe = a silent
not-run = the exact violation; ``test_fail_persisted`` + ``test_cache_first_and_fail_safe``
guard it.

BOTH-REQUIRED (Pitfall 5): PASS iff ``coverage_pct >= Y_pct and utci_delta_c >= X_c`` —
the ``and`` is structural; an ``or`` is forbidden by the plan grep.

BASE TIER — NON-NEGOTIABLE: shapely / jsonschema / numpy + the ``acceptance.*`` transforms
only. NO rhino3dm / torch / infrared / live import is reachable from this module — the gate
consumes persisted coordinates + the byte-stable baseline, never re-decodes the mesh and
never re-runs the climate sim.
"""

from __future__ import annotations

import json
from pathlib import Path

# pythonpath=["src","."] (pyproject) makes the sibling packages importable bare.
from manifest.manifest import Manifest, content_hash
from provenance.ledger import ProvenanceLedger
from validate.validate import validate

from acceptance.comfort_gap import build_sidecar
from acceptance.constants import IDEAL_DELTA_C_ASSUMED
from acceptance.coverage import _shadow_geometry, priority_cells, priority_shadow_coverage
from acceptance.delta import mean_shaded_delta
from acceptance.thresholds import load_thresholds

from shapely.affinity import translate
from shapely.geometry import Point

# --------------------------------------------------------------------------- #
# Stage identity (clone selection's module constants)
# --------------------------------------------------------------------------- #
_STAGE = "acceptance_verdict"
_CONTRACT = "acceptance_verdict"
_SCHEMA_VERSION = "1.0.0"
_ARTIFACT_NAME = "acceptance.json"
_META_NAME = "acceptance_meta.json"
_LEDGER_NAME = "acceptance_ledger.json"
#: The persisted base the GATE-02 denominator points at (schema ``baseline_ref``).
_BASELINE_REF = "utci_grid.json#baseline_utci_c"

#: The deterministic demo brief date (A5) — the SAME one Phase 4 projected the shadow with,
#: so the sidecar baseline conditions name the matching peak-sun band.
_DEFAULT_BRIEF_DATE = "2026-06-14"

#: The five persisted upstream artifacts the gate consumes (bare stems). A missing REQUIRED
#: artifact is an INTERNAL ERROR (the fail-safe path), NEVER a FAIL verdict.
_REQUIRED_INPUTS = ("utci_grid", "score_grid", "footprint", "material_selection", "gh_meta")


class MissingUpstreamArtifact(FileNotFoundError):
    """A REQUIRED persisted upstream artifact is absent.

    A genuine INTERNAL error (the fail-safe path: ``mark_failed`` + raise), NEVER a FAIL
    verdict. A FAIL means "the geometry was evaluated and did not cool enough"; a missing
    input means "the gate could not run" — the two must never be conflated (A6).
    """


# --------------------------------------------------------------------------- #
# The pure both-required comparator (GATE-03)
# --------------------------------------------------------------------------- #
def build_verdict(
    *,
    coverage_pct: float,
    utci_delta_c: float,
    X_c: float,
    Y_pct: float,
    baseline_ref: str = _BASELINE_REF,
) -> dict:
    """Assemble the frozen 7-field ``acceptance_verdict`` dict (BOTH-REQUIRED, Pitfall 5).

    ``passed = coverage_pct >= Y_pct and utci_delta_c >= X_c`` — the ``and`` is the
    both-required gate (NEVER ``or``): any single soft criterion is a FAIL. All four
    quadrants (both -> PASS, coverage-only -> FAIL, delta-only -> FAIL, neither -> FAIL)
    are exercised by ``test_both_required``.

    The returned dict carries EXACTLY the schema's 7 fields with the schema's NAMES
    (``utci_delta_c`` / ``X_c`` / ``Y_pct`` / ``verdict`` / ``baseline_ref``) — the
    conceptual CONTEXT names (``pass`` / ``utci_delta``) would fail validate-then-write
    against ``additionalProperties:false`` (Pitfall 7).
    """
    passed = coverage_pct >= Y_pct and utci_delta_c >= X_c
    return {
        "schema_version": _SCHEMA_VERSION,
        "coverage_pct": coverage_pct,
        "utci_delta_c": utci_delta_c,
        "X_c": X_c,
        "Y_pct": Y_pct,
        "verdict": "PASS" if passed else "FAIL",
        "baseline_ref": baseline_ref,
    }


#: Plan-prose alias — the plan names the comparator ``compute_verdict``; the test contract
#: names it ``build_verdict``. One implementation, two import names (no second comparator).
compute_verdict = build_verdict


# --------------------------------------------------------------------------- #
# Persisted-artifact loaders (clone selection's read discipline)
# --------------------------------------------------------------------------- #
def _read_artifact(project_dir: Path, stem: str) -> dict:
    """Read ``<project_dir>/<stem>.json`` or raise the typed internal-error (fail-safe path)."""
    path = project_dir / f"{stem}.json"
    if not path.exists():
        raise MissingUpstreamArtifact(
            f"required upstream artifact {path.name!r} is absent from {project_dir} — "
            "the gate cannot run (an INTERNAL error / fail-safe, never a FAIL verdict, A6)"
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - defensive
        raise MissingUpstreamArtifact(
            f"upstream artifact {path.name!r} is unreadable/corrupt: {exc}"
        ) from exc


def _load_upstream(project_dir: Path) -> dict:
    """Load the five persisted upstream artifacts (raises on any missing — internal error)."""
    return {stem: _read_artifact(project_dir, stem) for stem in _REQUIRED_INPUTS}


def _baseline_mean_c(utci_grid: dict) -> float:
    """The GROUNDED no-shade baseline mean UTCI over the persisted grid (sidecar anchor)."""
    cells = utci_grid.get("cells", []) if isinstance(utci_grid, dict) else utci_grid
    vals = [float(c["baseline_utci_c"]) for c in cells if "baseline_utci_c" in c]
    if not vals:
        raise MissingUpstreamArtifact(
            "utci_grid carries no persisted baseline_utci_c — the GATE-02 denominator is "
            "missing (an internal error, never a FAIL verdict, Pitfall 4)"
        )
    return sum(vals) / len(vals)


def _shaded_priority(priority: list[dict], shadow_polygon_m: dict) -> list[dict]:
    """The priority cells whose centre lies inside the PROJECTED shadow (GATE-01 ∩ set).

    GATE-01 and GATE-02 MUST operate over the SAME shaded cell set (baseline_spec): coverage
    counts how many priority cells are shaded, delta cools exactly those shaded cells. This
    reuses ``coverage._shadow_geometry`` (the SAME frame-aware translate-both discipline as
    ``priority_shadow_coverage``) so the shaded set the delta consumes is byte-consistent with
    the coverage ratio — never a second, drifting shadow test.
    """
    shadow, (ox, oy) = _shadow_geometry(shadow_polygon_m)
    shaded: list[dict] = []
    for c in priority:
        pt = translate(Point(c["x_m"], c["y_m"]), xoff=-ox, yoff=-oy)
        # intersects() subsumes contains() for a Point (interior + boundary); the disjunction was
        # redundant (NT-01) — boundary-centre cells are still credited.
        if shadow.intersects(pt):
            shaded.append(dict(c))
    return shaded


def _join_baseline(cells: list[dict], utci_grid: dict) -> list[dict]:
    """Carry the persisted ``baseline_utci_c`` onto cells keyed by ``(x_m, y_m)``.

    The score_grid priority cells carry ``{x_m, y_m, score}`` only; the byte-stable baseline
    lives in ``utci_grid.json``. Joining it (never re-deriving it — Pitfall 4) makes the
    grounded-baseline delta path available and lets the ledger label the baseline GROUNDED.
    """
    ucells = utci_grid.get("cells", []) if isinstance(utci_grid, dict) else utci_grid
    index = {
        (round(float(c["x_m"]), 6), round(float(c["y_m"]), 6)): float(c["baseline_utci_c"])
        for c in ucells
        if "baseline_utci_c" in c
    }
    out: list[dict] = []
    for c in cells:
        key = (round(float(c["x_m"]), 6), round(float(c["y_m"]), 6))
        joined = dict(c)
        if key in index:
            joined["baseline_utci_c"] = index[key]
        out.append(joined)
    return out


# --------------------------------------------------------------------------- #
# The wired stage (cache-first, validate-then-write, fail-safe) — A6 keystone
# --------------------------------------------------------------------------- #
def run_acceptance_stage(
    project_id: str | None = None,
    parsed_brief: dict | None = None,
    marked_cells: list | None = None,
    *,
    project_dir: Path | str | None = None,
    projects_root: Path | str | None = None,
    brief_date: str | None = None,
) -> dict:
    """Run the cooling-acceptance gate over a persisted project (GATE-01/02/03).

    Resolves the project directory from EITHER ``project_dir`` (the integration-test path:
    a writable tmp copy of ``projects/primavera-demo``) OR ``project_id`` + ``projects_root``
    (the plan/orchestrator path). Clones ``selection.run_selection_stage``:

      1. CACHE-FIRST: a 2nd run over an unchanged project re-validates the on-disk
         ``acceptance.json`` and returns it with ``cache_hit=True`` (zero recompute).
      2. COMPUTE (fail-safe): load upstream -> X/Y via ``load_thresholds()`` -> GATE-01
         coverage -> GATE-02 (1-tau) delta over the SAME shaded set -> ``build_verdict``.
      3. VALIDATE-THEN-WRITE: ``validate(verdict, "acceptance_verdict")`` BEFORE a byte hits
         disk, then write ``acceptance.json`` (PASS or FAIL — a FAIL is a successful outcome).
      4. SIDECAR + LEDGER: write the Comfort-Gap ``acceptance_meta.json`` + the provenance
         ledger (coverage DERIVED, delta DERIVED, baseline GROUNDED, ideal_delta ASSUMED).
      5. ``mark_done`` — even on FAIL. The ``except`` / ``mark_failed`` branch runs ONLY on a
         genuine internal error; a FAIL verdict NEVER reaches it (A6 / Pitfall 6).

    Returns a stage-result dict: ``{verdict, coverage_pct, utci_delta_c, X_c, Y_pct,
    stage_done, stage_failed, cache_hit, acceptance_path, meta_path}``.
    """
    # ── resolve the project directory + a Manifest over it ────────────────────
    if project_dir is not None:
        project_dir = Path(project_dir)
        project = project_dir.name
        root = project_dir.parent
    else:
        if project_id is None:
            raise ValueError("run_acceptance_stage requires either project_dir or project_id")
        project = project_id
        root = Path(projects_root) if projects_root is not None else Path("projects")
        project_dir = root / project

    manifest = _load_manifest(project, root)
    artifact_path = project_dir / _ARTIFACT_NAME
    meta_path = project_dir / _META_NAME
    date = brief_date or _DEFAULT_BRIEF_DATE

    # ── input_hash over the gate's real inputs (clone selection's content_hash) ─
    # Loaded up front so the cache key reflects the upstream the verdict depends on. A missing
    # required artifact here is an INTERNAL error (fail-safe), never a FAIL.
    upstream = _load_upstream(project_dir)
    tau = float(upstream["material_selection"]["solar_transmissivity"])
    input_hash = content_hash(
        {
            "footprint": upstream["footprint"],
            "score_grid": upstream["score_grid"],
            "shadow_polygon_m": upstream["gh_meta"].get("shadow_polygon_m"),
            "tau": tau,
            "ideal_delta_c": IDEAL_DELTA_C_ASSUMED,
            "baseline_ref": _BASELINE_REF,
            "brief_date": date,
        }
    )

    # ── 1) CACHE CHECK (clone selection): unchanged inputs + a valid artifact = hit ──
    if manifest.is_reusable(_STAGE, input_hash) and artifact_path.exists():
        try:
            cached = json.loads(artifact_path.read_text(encoding="utf-8"))
            validate(cached, _CONTRACT)
            return _result(cached, stage_done=True, stage_failed=False, cache_hit=True,
                           acceptance_path=artifact_path, meta_path=meta_path)
        except (OSError, json.JSONDecodeError):
            pass  # corrupt cache -> fall through and recompute

    # ── 2) COMPUTE (fail-safe) ────────────────────────────────────────────────
    try:
        # X/Y from the frozen, content-hashed thresholds — NEVER inlined; raises on tamper
        # (a genuine internal error -> fail-safe; a tuned threshold can never force a PASS).
        thresholds = load_thresholds()
        X_c = float(thresholds["x_utci_reduction_c"])
        Y_pct = float(thresholds["y_coverage_pct"])

        # The shadow polygon was projected by Phase 4 using sun_vector(date) for this SAME brief
        # date (A5) and persisted as gh_meta.shadow_polygon_m — the gate consumes those coords and
        # NEVER re-projects (no second sun_vector call here; that would be dead computation, MN-01).
        shadow_polygon_m = upstream["gh_meta"]["shadow_polygon_m"]  # KeyError -> internal error

        # GATE-01: projected-shadow coverage over the funded priority cells (Q2 dual path).
        priority = priority_cells(upstream["score_grid"], upstream["footprint"], marked_cells)
        priority = _join_baseline(priority, upstream["utci_grid"])
        cov_result = priority_shadow_coverage(priority, shadow_polygon_m)
        coverage_pct = cov_result["coverage_pct"]

        # GATE-02: (1-tau) mean delta over the SAME shaded priority set (consistency, baseline_spec).
        shaded = _shaded_priority(priority, shadow_polygon_m)
        utci_delta_c = mean_shaded_delta(shaded, ideal_delta_c=IDEAL_DELTA_C_ASSUMED, tau=tau)

        # GATE-03: the both-required 7-field verdict (PASS or FAIL — both are successful outcomes).
        verdict = build_verdict(
            coverage_pct=coverage_pct,
            utci_delta_c=utci_delta_c,
            X_c=X_c,
            Y_pct=Y_pct,
        )

        # Derive every sidecar/ledger input BEFORE the first byte hits disk — validate-then-write
        # atomicity (MJ-01): if _baseline_mean_c raises (a malformed utci_grid with no persisted
        # baseline_utci_c), it is an INTERNAL error that must surface with NO partial acceptance.json
        # on disk — never a verdict-written + stage-not-done contradiction.
        baseline_mean = _baseline_mean_c(upstream["utci_grid"])

        # ── 3) VALIDATE-THEN-WRITE: a FAIL takes this SAME path (it is written + mark_done) ──
        validate(verdict, _CONTRACT)  # rejects any extra/missing/misnamed key BEFORE the write
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(verdict, indent=2), encoding="utf-8")

        # ── 4a) SIDECAR: the instructor Comfort-Gap extras (NON-contract, never validated) ──
        sidecar = build_sidecar(
            utci_delta_c=utci_delta_c,
            coverage_pct=coverage_pct,
            baseline_mean_c=baseline_mean,
            material_selection=upstream["material_selection"],
            brief_date=date,
            coverage_basis=shadow_polygon_m.get("basis", "roof-mesh-projection"),
        )
        meta_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")

        # ── 4b) PROVENANCE (coverage/delta DERIVED, baseline GROUNDED, ideal_delta ASSUMED) ──
        ledger = ProvenanceLedger()
        ledger.derived(
            "coverage_pct",
            coverage_pct,
            "projected-shadow ∩ funded priority cells (GATE-01); shadow_polygon_m from Phase-4 geom",
            _STAGE,
            unit="percent",
            formula="100 * shaded_priority / priority",
        )
        ledger.derived(
            "utci_delta_c",
            utci_delta_c,
            "(1-tau) ideal geometric cooling over the shaded priority cells (GATE-02); ideal_delta ASSUMED",
            _STAGE,
            unit="celsius",
            formula="mean(ideal_delta_c * (1 - tau))",
            inputs=["ideal_delta_c", "solar_transmissivity", "baseline_utci_c"],
        )
        ledger.grounded(
            "baseline_utci_c",
            round(baseline_mean, 6),
            "persisted infrared.city no-shade baseline mean over the UTCI grid (utci_grid.json)",
            _STAGE,
            unit="celsius",
        )
        ledger.assumed(
            "ideal_delta_c",
            IDEAL_DELTA_C_ASSUMED,
            "tau=0 full-shade geometric peak-hour cooling magnitude (Q3); no grounded shaded sim persisted",
            _STAGE,
            unit="celsius",
        )
        ledger.write(project_dir / _LEDGER_NAME)

        # ── 5) mark_done — even on FAIL (the FAIL is a SUCCESSFUL stage outcome, A6) ──
        output_hash = content_hash(verdict)
        manifest.mark_done(_STAGE, _ARTIFACT_NAME, input_hash, output_hash)
        manifest.write()

        return _result(verdict, stage_done=True, stage_failed=False, cache_hit=False,
                       acceptance_path=artifact_path, meta_path=meta_path)

    except Exception:
        # Fail-safe: leave the stage NOT done, write no partial verdict (mirror selection).
        # INTERNAL ERRORS ONLY — a FAIL verdict NEVER reaches here (it is written + mark_done above).
        if hasattr(manifest, "mark_failed"):
            try:
                manifest.mark_failed(_STAGE)
                manifest.write()
            except Exception:
                pass
        raise


def _result(
    verdict: dict,
    *,
    stage_done: bool,
    stage_failed: bool,
    cache_hit: bool,
    acceptance_path: Path,
    meta_path: Path,
) -> dict:
    """The stage-result dict (the integration test reads stage_done / stage_failed / cache_hit)."""
    return {
        "verdict": verdict["verdict"],
        "coverage_pct": verdict["coverage_pct"],
        "utci_delta_c": verdict["utci_delta_c"],
        "X_c": verdict["X_c"],
        "Y_pct": verdict["Y_pct"],
        "stage_done": stage_done,
        "stage_failed": stage_failed,
        "cache_hit": cache_hit,
        "acceptance_path": str(acceptance_path),
        "meta_path": str(meta_path),
        "acceptance": verdict,
    }


def _load_manifest(project_id: str, project_root: Path) -> Manifest:
    """Load a persisted manifest if present, else a fresh one (clone selection._load_manifest)."""
    m = Manifest(project_id, project_root)
    manifest_path = m.project_dir / "manifest.json"
    if not manifest_path.exists():
        return m
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return m
    if "created_at" in data:
        m.created_at = data["created_at"]
    for st in data.get("stages", []):
        name = st.get("name")
        if name in m._stages:
            m._stages[name].update(st)
    return m
