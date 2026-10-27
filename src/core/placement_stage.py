"""Persisted greedy-placement stage orchestrator (PLACE-03/04/07/09) — mirrors ``core.core``.

Cache-first → mark_running → build the DEMO per-structure coverage model → ``greedy_mclp`` →
fail-safe → validate-then-write ``structure_zones.json`` → mark_done → merged provenance + sidecar
+ true-reason infeasibility. Zero AI, zero network, zero randomness: placement is a deterministic,
submodular-greedy Maximal-Covering selection over the two already-validated master-lattice grids.
The output is **DERIVED-from-ASSUMED** (demand uses ASSUMED-grade ``crowd_density``) and makes NO
best-coverage claim — the greedy is a bounded heuristic (CORE-05 honesty lock).

The DEMO coverage model is a PER-STRUCTURE canopy: ``OffsetShadowCoverage(square_canopy_ring(
ASSUMED_CANOPY_HALF_SPAN_M), sun_offset)`` (name ``offset_shadow``). A per-candidate canopy
translated to each site gives per-candidate variation → real RANKED zones; a fixed whole-site region
would credit every candidate with the same cells (no ranking), so the whole-site
``PersistedShadowCoverage`` is reserved for the later acceptance gate, NOT this ranking path. The
sun offset is derived from a real ``sun_vector`` WHEN PRESENT, else an ASSUMED high-noon ``(0, 0)``;
the offset SOURCE is recorded in provenance — never silent.

The XFN-04 seam (``crowd["lattice"] == utci["lattice"]``) is enforced here as an explicit raise —
the utci lattice is the authority, read and passed through, never re-derived.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.constants import (
    ASSUMED_CANOPY_HALF_SPAN_M,
    ASSUMED_CANOPY_HEIGHT_M,
    ASSUMED_COST_PER_STRUCTURE,
    ASSUMED_K_DEFAULT,
    LITERATURE_DENSITY_MAGNITUDE,
    ROBUST_FAR_STAGE_DENSITY_BOOST,
    ROBUST_FAR_STAGE_DISTANCE_THRESHOLD_M,
    ROBUST_SNAPSHOT_CROWD_SLICES,
    ROBUST_SNAPSHOT_FAMILY_SIZE,
    ROBUST_SNAPSHOT_SUN_SLICES,
)
from core.coverage_models import (
    OffsetShadowCoverage,
    shadow_offset_from_sun,
    square_canopy_ring,
)
from core.placement import dense_candidate_grid, greedy_mclp
from manifest.manifest import Manifest, content_hash
from provenance.ledger import ProvenanceLedger
from validate.validate import validate

_STAGE = "structure_zones"
_ARTIFACT_NAME = "structure_zones.json"
_SIDECAR_NAME = "structure_zones_meta.json"


# --------------------------------------------------------------------------- #
# Manifest persistence — copied verbatim from core.core._load_manifest
# (Manifest has no restore constructor; stage records are restored by hand).
# An unknown new stage on an OLD on-disk manifest is treated fresh — exactly
# right for the added structure_zones stage.
# --------------------------------------------------------------------------- #
def _load_manifest(project_id: str, project_root: Path) -> Manifest:
    """Load a persisted ``manifest.json`` if present, else a fresh manifest."""
    m = Manifest(project_id, project_root)
    manifest_path = m.project_dir / "manifest.json"
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


def _derive_sun_offset(gh_meta: dict | None) -> tuple[tuple[float, float], str]:
    """The (dx, dy) shadow offset for the demo canopy + the SOURCE label (never silent).

    The demo data carries NO ``sun_vector`` (``gh_meta.json`` has only ``shadow_polygon_m``), so the
    real-sun branch is dormant on the demo path. When a ``sun_vector`` IS present, project it through
    the ASSUMED canopy height; otherwise default to a high-noon ``(0, 0)`` offset (the canopy shades
    directly beneath it). The returned source string is recorded in provenance.
    """
    sun_vector = gh_meta.get("sun_vector") if isinstance(gh_meta, dict) else None
    if sun_vector is not None:
        offset = shadow_offset_from_sun(tuple(sun_vector), ASSUMED_CANOPY_HEIGHT_M)
        return offset, "real-sun-vector"
    return (0.0, 0.0), "assumed-noon"


def run_placement_stage(
    project_id: str,
    *,
    projects_root: Path | str | None = None,
    k: int | None = None,
    engine: str = "greedy",
    max_constraint_cells: int | None = None,
) -> dict:
    """Run the persisted placement stage: cache-first MCLP -> validate-then-write ranked zones.

    Args:
        project_id: the run id; artifacts live under ``<projects_root>/<project_id>/``.
        projects_root: where ``<project_id>/`` lives (default ``projects/``).
        k: primary stopping cap (number of structures); defaults to ``ASSUMED_K_DEFAULT``.
        engine: the placement engine — ``"greedy"`` (default; the bounded submodular heuristic,
            scipy-import-free), ``"ilp"`` (the exact MCLP solved via HiGHS to a mip_gap=0 proof,
            which ALSO writes the non-contract certificate sidecar — the SOLE artifact carrying the
            earned claim, filename + claim built in the glob-exempt ``placement_ilp`` tree), or
            ``"robust"`` (PLACE-08: the exact solve run across a STRUCTURED sun×crowd-slice snapshot
            family incl. a far-stage-corrected world, labelling each zone ``robust``/``conditional``
            over covered DEMAND — no certificate; the honesty artifact is the per-zone labels + the
            scenario_set sidecar). The same contract-valid ``structure_zones.json`` is produced for
            all three. ``engine`` + the solver identity + the scipy version (and, for ``robust``, the
            snapshot-family identity) are folded into the cache key (a switch / a scipy bump / a
            family change is a MISS), so a greedy/ilp artifact is never silently served for a robust
            request and vice versa.
        max_constraint_cells: optional override of the ILP scale ceiling (D-13); ``engine="ilp"``
            only — above it the exact solve RAISES (never subsamples), leaving no artifact.

    Reads ``parsed_brief.json`` (``budget`` — NOT capacity), ``utci_grid.json`` and
    ``crowd_grid.json`` (and an optional ``gh_meta.json`` only for a real ``sun_vector``); emits
    ``structure_zones.json`` (contract-valid ranked ZONES snapped to the utci master lattice),
    ``provenance.json``, the non-contract sidecar ``structure_zones_meta.json``, and
    ``infeasibility.json`` when no structure can be placed (never silent).

    Returns:
        The ``structure_zones`` artifact dict.

    Raises:
        AssertionError on XFN-04 lattice drift (crowd != utci); any transform error (stage left NOT
        done, no artifact written); a jsonschema ``ValidationError`` if a shaped artifact violates
        its contract (raised BEFORE any write).
    """
    project_root = Path(projects_root) if projects_root is not None else Path("projects")
    pdir = project_root / project_id

    # Read the inputs: budget (parsed_brief) + the two master-lattice grids.
    brief = json.loads((pdir / "parsed_brief.json").read_text(encoding="utf-8"))
    budget = brief["budget"]
    utci = json.loads((pdir / "utci_grid.json").read_text(encoding="utf-8"))
    crowd = json.loads((pdir / "crowd_grid.json").read_text(encoding="utf-8"))

    lattice = utci["lattice"]  # AUTHORITY — read, never re-derived (Pitfall 5)
    # XFN-04 integrity gate: refuse to place across lattice drift. Raised explicitly
    # (not a bare assert) so the gate survives `python -O`.
    if crowd["lattice"] != lattice:
        raise AssertionError("XFN-04 lattice drift (crowd != utci)")

    # ── Build the DEMO per-structure coverage model (per-candidate ranking) ───
    gh_meta_path = pdir / "gh_meta.json"
    gh_meta = (
        json.loads(gh_meta_path.read_text(encoding="utf-8"))
        if gh_meta_path.exists()
        else None
    )
    sun_offset, offset_source = _derive_sun_offset(gh_meta)
    canopy = square_canopy_ring(ASSUMED_CANOPY_HALF_SPAN_M)
    coverage_model = OffsetShadowCoverage(canopy, sun_offset)  # name "offset_shadow"

    k = k if k is not None else ASSUMED_K_DEFAULT
    cost_per_structure = ASSUMED_COST_PER_STRUCTURE

    # ── 1) CACHE CHECK ────────────────────────────────────────────────────────
    # Every pre-run constant that affects the result is in the key (retune -> MISS, Pitfall D /
    # MN-02): the canopy half-span, the sun offset, AND the offset SOURCE are all folded in.
    # The ENGINE identity is folded too (D-03): a greedy artifact must never be served for an ilp
    # (or robust) request (and vice versa), and a scipy bump (which can shift a HiGHS tied selection)
    # is a MISS. scipy is read LAZILY (only on the solver paths) so the greedy default stays
    # solver-import-free.
    _uses_scipy = engine in ("ilp", "robust")
    scipy_version = __import__("scipy").__version__ if _uses_scipy else None
    # For the robust path the structured snapshot-family identity is folded in (D-07): a change to
    # the family size, the sun/crowd slice axes, or the far-stage threshold/boost MUST be a MISS so a
    # stale robust artifact is never served against a different family.
    robust_family = (
        {
            "family_size": ROBUST_SNAPSHOT_FAMILY_SIZE,
            "sun_slices": list(ROBUST_SNAPSHOT_SUN_SLICES),
            "crowd_slices": list(ROBUST_SNAPSHOT_CROWD_SLICES),
            "far_stage_threshold_m": ROBUST_FAR_STAGE_DISTANCE_THRESHOLD_M,
            "far_stage_boost": ROBUST_FAR_STAGE_DENSITY_BOOST,
        }
        if engine == "robust"
        else None
    )
    input_hash = content_hash(
        {
            "utci": content_hash(utci),
            "crowd": content_hash(crowd),
            "budget": budget,
            "k": k,
            "cost_per_structure": cost_per_structure,
            "density_magnitude": LITERATURE_DENSITY_MAGNITUDE,
            "coverage_model": [
                coverage_model.name,
                ASSUMED_CANOPY_HALF_SPAN_M,
                [sun_offset[0], sun_offset[1]],
                offset_source,
            ],
            "engine": engine,
            "solver": "scipy.milp/HiGHS" if _uses_scipy else None,
            "scipy_version": scipy_version,  # bump -> MISS (D-03)
            "robust_family": robust_family,  # family change -> MISS (D-07)
        }
    )
    m = _load_manifest(project_id, project_root)
    if m.is_reusable(_STAGE, input_hash, _STAGE):
        # Cache hit: serve the persisted artifact with ZERO solve compute. On the ilp path the
        # certificate sidecar persists beside the artifact (written on the original MISS); we do
        # NOT fabricate one — only the genuine ilp run ever writes it (never on the greedy path).
        structure_zones = json.loads(
            (m.project_dir / _ARTIFACT_NAME).read_text(encoding="utf-8")
        )
        zone_count = len(structure_zones["structures"])  # cheap recompute, no transform
        _write_provenance(m.project_dir, structure_zones, offset_source, engine=engine)
        # Reconstruct the robust scenario_set from the served artifact's surviving_snapshots so a
        # cache HIT discloses the scenario family identically to a MISS (never silent).
        hit_scenario_set = None
        if engine == "robust":
            hit_ids = sorted(
                {
                    sid
                    for z in structure_zones["structures"]
                    for sid in z.get("surviving_snapshots", [])
                }
            )
            hit_scenario_set = {
                "snapshot_ids": hit_ids,
                "family_size": ROBUST_SNAPSHOT_FAMILY_SIZE,
                "sun_slices": list(ROBUST_SNAPSHOT_SUN_SLICES),
                "crowd_slices": list(ROBUST_SNAPSHOT_CROWD_SLICES),
                "far_stage_threshold_m": ROBUST_FAR_STAGE_DISTANCE_THRESHOLD_M,
                "far_stage_boost": ROBUST_FAR_STAGE_DENSITY_BOOST,
            }
        _write_sidecar(
            m.project_dir,
            zone_count,
            k,
            cost_per_structure,
            offset_source,
            scenario_set=hit_scenario_set,
        )
        return structure_zones

    # ── 2) MISS: mark running, pure transform, fail-safe on error ────────────
    m.mark_running(_STAGE)
    try:
        sites = dense_candidate_grid(lattice)
        if engine == "ilp":
            # Lazy ILP import (D-02): scipy stays out of the greedy default import path. The exact
            # solver returns the SAME result-dict shape as greedy_mclp PLUS the certificate dict
            # (built in mclp.py — its earned-claim sentence is DATA from that glob-exempt tree,
            # never a string literal in this src/core/ source under the honesty-vocab glob).
            from placement_ilp.mclp import solve_mclp_exact

            ilp_kwargs = (
                {"max_constraint_cells": max_constraint_cells}
                if max_constraint_cells is not None
                else {}
            )
            result, certificate = solve_mclp_exact(
                utci,
                crowd,
                sites,
                coverage_model,
                k=k,
                budget=budget,
                cost_per_structure=cost_per_structure,
                **ilp_kwargs,
            )
        elif engine == "robust":
            # Lazy robust import (D-02): the robust wrapper pulls scipy only INSIDE the per-snapshot
            # solve_mclp_exact call, so importing it here keeps the module-load path scipy-free. It
            # builds the structured snapshot family itself, solves each via the exact engine, and
            # returns a CONTRACT-shaped result whose zones already carry robustness +
            # surviving_snapshots, plus a non-contract ``provenance`` annotation (stripped before the
            # frozen structure_zones write; it flows to provenance.json instead). No certificate on
            # this path — the honesty artifact is the per-zone labels + the scenario_set sidecar.
            from placement_ilp.robust import solve_robust

            robust_kwargs = (
                {"max_constraint_cells": max_constraint_cells}
                if max_constraint_cells is not None
                else {}
            )
            result = solve_robust(
                utci,
                crowd,
                coverage_model,
                k=k,
                budget=budget,
                cost_per_structure=cost_per_structure,
                **robust_kwargs,
            )
            certificate = None
        else:
            result = greedy_mclp(
                utci,
                crowd,
                sites,
                coverage_model,
                k=k,
                budget=budget,
                cost_per_structure=cost_per_structure,
            )
            certificate = None
    except Exception:
        # Failure-safe: stage NOT done, NO artifact written. Persist the not-done
        # manifest so resume re-runs this stage, then surface the error.
        m.mark_failed(_STAGE)
        m.write()
        raise

    # ── 3) SHAPE + VALIDATE-THEN-WRITE (invalid never reaches disk) ──────────
    # greedy_mclp / solve_mclp_exact map 1:1; the stage ADDS schema_version/crs/lattice/stopping_rule
    # and the per-zone robustness label. The greedy/ilp single-solve paths have NO per-zone label, so
    # the stage stamps "single-snapshot"; the robust path's zones ALREADY carry robust/conditional +
    # surviving_snapshots from solve_robust — use them VERBATIM (never overwrite to single-snapshot).
    if engine == "robust":
        structures_out = [
            {
                **{kk: vv for kk, vv in z.items()},  # robustness + surviving_snapshots already present
            }
            for z in result["structures"]
        ]
    else:
        structures_out = [
            {**z, "robustness": "single-snapshot"} for z in result["structures"]
        ]
    structure_zones = {
        "schema_version": "1.0.0",
        "crs": utci["crs"],
        "lattice": lattice,
        "coverage_model": result["coverage_model"],
        "stopping_rule": {
            "k": k,
            "budget": budget,
            "cost_per_structure": cost_per_structure,
        },
        "total_demand": result["total_demand"],
        "covered_demand": result["covered_demand"],
        "coverage_pct": result["coverage_pct"],
        "structures": structures_out,
        "infeasible": result["infeasible"],
    }
    validate(structure_zones, _STAGE)  # BEFORE any write
    m.project_dir.mkdir(parents=True, exist_ok=True)
    (m.project_dir / _ARTIFACT_NAME).write_text(
        json.dumps(structure_zones, indent=2), encoding="utf-8"
    )
    m.mark_done(_STAGE, _ARTIFACT_NAME, input_hash, content_hash(structure_zones))
    m.write()

    # ── 4) PROVENANCE + sidecar + certificate + true-reason infeasibility ────
    _write_provenance(m.project_dir, structure_zones, offset_source, engine=engine)
    # On the robust path, record the structured scenario family in the NON-contract sidecar (never
    # silent): the snapshot ids that appeared in ANY zone's surviving_snapshots + the far-stage
    # threshold/boost that defined the corrected world. The frozen structure_zones schema is untouched.
    scenario_set = None
    if engine == "robust":
        snapshot_ids = sorted(
            {sid for z in structure_zones["structures"] for sid in z.get("surviving_snapshots", [])}
        )
        scenario_set = {
            "snapshot_ids": snapshot_ids,
            "family_size": ROBUST_SNAPSHOT_FAMILY_SIZE,
            "sun_slices": list(ROBUST_SNAPSHOT_SUN_SLICES),
            "crowd_slices": list(ROBUST_SNAPSHOT_CROWD_SLICES),
            "far_stage_threshold_m": ROBUST_FAR_STAGE_DISTANCE_THRESHOLD_M,
            "far_stage_boost": ROBUST_FAR_STAGE_DENSITY_BOOST,
            "note": (
                "robust=selected in ALL snapshots, conditional=in SOME; over covered DEMAND, never "
                "a cooling/°C delta — structured directional family, never undirected jitter"
            ),
        }
    _write_sidecar(
        m.project_dir,
        len(structure_zones["structures"]),
        k,
        cost_per_structure,
        offset_source,
        scenario_set=scenario_set,
    )
    if engine == "ilp" and certificate is not None:
        # The NON-contract certificate sidecar — the SOLE artifact carrying the earned claim (the
        # cert dict, incl. that claim sentence AND its filename, was BUILT in the glob-exempt
        # mclp.py; this stage only serializes it). Written ONLY on the ilp path, after the
        # contract write.
        _write_certificate(m.project_dir, certificate)
    if structure_zones["infeasible"] is not None:
        # Load-bearing (instructor): an unplaceable run is REPORTED, never silent — and the reason
        # is the TRUE one straight from greedy_mclp (no-overlap vs budget vs k<=0, MJ-01).
        info = structure_zones["infeasible"]
        human = f"No structures placed: {info['reason']}."
        (m.project_dir / "infeasibility.json").write_text(
            json.dumps({**info, "human_readable": human}, indent=2), encoding="utf-8"
        )
    else:
        # A feasible re-run removes any stale report — a contradictory state (non-empty
        # structures + "no shade placed") must never persist (MJ-04).
        (m.project_dir / "infeasibility.json").unlink(missing_ok=True)

    return structure_zones


def _write_provenance(
    project_dir: Path, structure_zones: dict, offset_source: str, *, engine: str = "greedy"
) -> None:
    """Emit ``provenance.json`` for the served zones (CORE-05 / instructor).

    Tiers: coverage_pct DERIVED, k / cost_per_structure / coverage_model ASSUMED. MERGES with the
    existing ledger: entries from OTHER stages (the crowd stage's non-negotiable ``crowd_density``
    ASSUMED tier, the climate stage's UTCI sourcing) are preserved — only this stage's own prior
    entries are replaced (MJ-02). The coverage_model source records the shadow-offset SOURCE
    (real-sun-vector vs assumed-noon) so it is never silent.

    The ``engine`` selects the coverage_pct provenance wording: the greedy path keeps the bounded
    submodular-heuristic disclaimer; the ilp path uses NEUTRAL wording (``exact MCLP, mip_gap=0,
    certificate attached``) — the earned claim lives ONLY in the certificate sidecar, never in
    ``provenance.json`` (which is in the honesty-vocab guard's named list — D-04/D-06).
    """
    if engine == "ilp":
        coverage_source = "exact MCLP via scipy.milp/HiGHS, mip_gap=0, certificate attached"
    elif engine == "robust":
        coverage_source = (
            "multi-snapshot robust labelling over a structured sun×crowd family incl. a "
            "far-stage-corrected world; robust=in-all, conditional=in-some; "
            "DERIVED-from-ASSUMED demand (crowd_density ASSUMED) — over covered DEMAND, never a "
            "cooling/°C delta"
        )
    else:
        coverage_source = (
            "submodular-greedy MCLP; (1−1/e)≈63% worst-case coverage bound — "
            "NOT a best-coverage claim"
        )
    prior_entries: list[dict] = []
    prov_path = project_dir / "provenance.json"
    if prov_path.exists():
        try:
            prior_entries = [
                e
                for e in json.loads(prov_path.read_text(encoding="utf-8")).get("entries", [])
                if e.get("stage") != _STAGE
            ]
        except (OSError, json.JSONDecodeError):
            prior_entries = []  # corrupt ledger -> rebuild with this stage's entries only

    ledger = ProvenanceLedger()
    ledger.derived(
        "coverage_pct",
        round(structure_zones["coverage_pct"], 4),
        source=coverage_source,
        stage=_STAGE,
        unit="percent",
        inputs=["utci_grid", "crowd_grid"],
    )
    ledger.assumed(
        "k",
        structure_zones["stopping_rule"]["k"],
        source=(
            "ASSUMED_K_DEFAULT — 'I can build N canopies'; primary stopping cap, "
            "tunable pre-run, immutable after an accepted run"
        ),
        stage=_STAGE,
    )
    ledger.assumed(
        "cost_per_structure",
        structure_zones["stopping_rule"]["cost_per_structure"],
        source="flat €/structure placeholder reconciled in Phase 5 (no Phase-5 dependency)",
        stage=_STAGE,
        unit="euro",
    )
    ledger.assumed(
        "coverage_model",
        structure_zones["coverage_model"],
        source=(
            f"per-structure offset-shadow: ASSUMED canopy half-span "
            f"{ASSUMED_CANOPY_HALF_SPAN_M} m, shadow offset {offset_source} "
            f"(real-sun-vector when present, else assumed high-noon)"
        ),
        stage=_STAGE,
    )
    # Merge: prior other-stage entries first, then this stage's. Validate the WHOLE merged ledger
    # against the frozen contract before writing.
    artifact = ledger.to_artifact()
    artifact["entries"] = prior_entries + artifact["entries"]
    validate(artifact, "provenance_ledger")
    prov_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")


def _write_sidecar(
    project_dir: Path,
    zone_count: int,
    k: int,
    cost_per_structure: float,
    offset_source: str,
    *,
    scenario_set: dict | None = None,
) -> None:
    """Write the NON-contract sidecar ``structure_zones_meta.json`` (the frozen schema is untouched).

    Carries the stopping-cap / zone-count / canopy / offset-source metadata downstream phases want
    WITHOUT amending ``structure_zones.schema.json`` (additionalProperties:false stays frozen).
    Deliberately NOT validated — it is not a contract artifact.

    On the robust path ``scenario_set`` records the structured snapshot family that produced the
    robust/conditional labels (the snapshot ids + the far-stage threshold/boost used) so the scenario
    family is NEVER silent — a robust answer always discloses the worlds it was robust ACROSS.
    """
    sidecar = {
        "schema_version": "1.0.0-sidecar",
        "stage": _STAGE,
        "k": k,
        "cost_per_structure": cost_per_structure,
        "zone_count": zone_count,
        "canopy_half_span_m": ASSUMED_CANOPY_HALF_SPAN_M,
        "offset_source": offset_source,
        "note": (
            "non-contract sidecar; demo coverage is a per-structure ASSUMED canopy "
            "(offset_shadow), shadow offset source recorded above. DERIVED-from-ASSUMED; "
            "the greedy placer makes no best-coverage claim."
        ),
    }
    if scenario_set is not None:
        sidecar["scenario_set"] = scenario_set
    (project_dir / _SIDECAR_NAME).write_text(
        json.dumps(sidecar, indent=2), encoding="utf-8"
    )


def _write_certificate(project_dir: Path, certificate: dict) -> None:
    """Write the NON-contract certificate sidecar (engine='ilp' ONLY) — D-04 / D-08.

    The SOLE artifact that legally carries the earned claim. Deliberately NOT validated (it is not
    a contract artifact — clone the ``_write_sidecar`` discipline). The certificate DICT (incl. the
    claim sentence) is BUILT in ``placement_ilp.mclp`` — this function ONLY serializes it, and even
    the filename is imported from that glob-exempt tree so NO forbidden vocabulary enters this
    ``src/core/`` source (it must pass the honesty-vocab guard UNCHANGED — D-05).
    """
    from placement_ilp.mclp import CERTIFICATE_FILENAME  # filename lives in the glob-exempt tree

    (project_dir / CERTIFICATE_FILENAME).write_text(
        json.dumps({"schema_version": "1.0.0-sidecar", **certificate}, indent=2),
        encoding="utf-8",
    )
