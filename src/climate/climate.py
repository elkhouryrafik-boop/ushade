"""Climate Layer orchestrator — ``run_climate_stage`` (CLIMATE-01..04, the Phase 2a spine).

This is the integration seam that wires the three Phase-2a parts into one cache-first
stage:

    fetch_utci (Plan 03, the paid network seam)
        -> grid_to_utci_artifact (Plan 02, the grid -> master-lattice transform)
            -> validate-then-write projects/<id>/utci_grid.json (manifest-gated)
                -> provenance ledger (UTCI GROUNDED; weather source labelled)

Correctness properties this function owns (the four truths Plan 04 proves):

  1. CACHE-FIRST. The manifest decides whether to call at all: a cache hit on the
     ``(site, date, hour_band)`` input hash returns the persisted artifact with ZERO
     live calls (T-02a-13 cost DoS; ``test_cache_hit_no_live_call``).
  2. FAILURE-SAFE. A ``ClimateFetchError`` leaves the ``utci_grid`` manifest stage NOT
     done and writes NO artifact — resume re-runs it, never a half-written grid
     (T-02a-11; ``test_failure_leaves_stage_not_done``).
  3. VALIDATE-THEN-WRITE. ``validate(artifact, "utci_grid")`` runs BEFORE any byte hits
     disk, so an invalid/partial grid can never be persisted (T-02a-11; mirrors Phase 1
     ``writeParsedBrief``).
  4. NEVER-SILENT PROVENANCE. UTCI is recorded GROUNDED; an EPW-sourced run records the
     weather source explicitly in the ledger — labelled, never silently substituted
     (T-02a-12; ``test_weather_epw_fallback_labelled``).

karpathy: one linear orchestration function. The manifest owns resume, the budget owns
the live-call cap, the SDK owns transport retry — so there is no DAG engine and no retry
loop here. The API key is NEVER read, assigned, or logged in this module.
"""

from __future__ import annotations

import json
import weakref
from pathlib import Path

# pythonpath=["src"] (pyproject) makes the sibling packages importable bare.
from climate.infrared_client import (
    LIVE_CALL_CAP,
    PEAK_HEAT_HOUR_BAND,
    ClimateFetchError,
    LiveCallBudget,
    fetch_utci,
)
from climate.lattice import CELL_SIZE_M, grid_to_utci_artifact
from manifest.manifest import Manifest, content_hash
from provenance.ledger import ProvenanceLedger
from validate.validate import validate

_STAGE = "utci_grid"
_ARTIFACT_NAME = "utci_grid.json"

# A per-client live-dispatch ledger so the LiveCallBudget cap is a backstop ACROSS calls
# that share one client (CCA-F P2: cap as a backstop, not the primary terminator). Keyed
# weakly on the client object so it is GC-friendly and test-isolated (each fresh client
# starts at zero). One dispatch is counted per cache-MISS run; a cache HIT counts nothing.
_LIVE_DISPATCHES: "weakref.WeakKeyDictionary[object, int]" = weakref.WeakKeyDictionary()


# --------------------------------------------------------------------------- #
# Fixed-site geometry (v1: the brief supplies only the date; the site is fixed)
# --------------------------------------------------------------------------- #
def _polygon_ring(site_polygon: dict) -> list[list[float]]:
    """Extract the outer [lon, lat] ring from a GeoJSON Feature/Polygon (closed ring)."""
    geom = site_polygon.get("geometry", site_polygon)
    coords = geom["coordinates"]
    return coords[0]  # outer ring of a Polygon (RFC 7946 [lon, lat] order)


def _site_centroid(site_polygon: dict) -> tuple[float, float]:
    """Mean of the ring vertices -> a (lon, lat) drive point for the sun position.

    The exact centroid is not load-bearing for the SDK call (it drives sun position over
    a ~600 m site); the mean of the boundary vertices is a stable, deterministic point.
    """
    ring = _polygon_ring(site_polygon)
    # A GeoJSON ring repeats the first vertex as its last; drop the duplicate for the mean.
    pts = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
    lon = sum(p[0] for p in pts) / len(pts)
    lat = sum(p[1] for p in pts) / len(pts)
    return lon, lat


def _site_input_hash(site_polygon: dict, date) -> str:
    """The cache key: content hash of (site ring, date, hour band).

    A changed site OR date OR band -> changed hash -> cache MISS -> correct re-run
    (manifest Pitfall D: content hash of inputs, never an mtime/exists check).
    """
    inputs = {
        "site_hash": content_hash(_polygon_ring(site_polygon)),
        "date": str(date),
        "hour_band": list(PEAK_HEAT_HOUR_BAND),
    }
    return content_hash(inputs)


# --------------------------------------------------------------------------- #
# Manifest persistence (resume across process / across calls)
# --------------------------------------------------------------------------- #
def _load_manifest(project_id: str, project_root: Path) -> Manifest:
    """Load a persisted ``manifest.json`` if present, else a fresh manifest.

    Resume / cache-across-calls hinges on this: the FIRST ``run_climate_stage`` writes
    the manifest with ``utci_grid`` done; a SECOND call reloads that state so
    ``is_reusable`` can short-circuit to a cache hit with no live call. ``Manifest`` has
    no constructor for an existing state, so we restore the stage records by hand.
    """
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


def _client_factory_from(client):
    """Adapt a concrete client INSTANCE into the ``client_factory`` ``fetch_utci`` wants.

    The Plan-01 ``FakeInfraredClient`` (and the real ``InfraredClient``) are context
    managers; ``fetch_utci`` calls the factory once and uses the returned object in a
    ``with``. The orchestrator's public surface takes an already-built ``client`` (the
    test injection point), so we wrap it in a zero-arg factory. ``None`` falls through to
    ``fetch_utci``'s default lazy real-SDK loader.
    """
    if client is None:
        return None
    return lambda: client


# --------------------------------------------------------------------------- #
# The stage
# --------------------------------------------------------------------------- #
def run_climate_stage(
    project_id: str,
    date,
    *,
    site_polygon: dict,
    client=None,
    projects_root: Path | str | None = None,
    weather_mode: str = "auto",
) -> dict:
    """Run the climate stage: cache-first fetch -> shape -> validate-then-write -> ground.

    Args:
        project_id: the run id; artifacts live under ``<projects_root>/<project_id>/``.
        date: the brief's date (``datetime.date`` or ISO ``YYYY-MM-DD`` string). Drives
            the single-month, peak-heat-band TimePeriod (Plan 03).
        site_polygon: the fixed-site Parc del Forum boundary (GeoJSON Feature/Polygon,
            WGS84 closed ring). v1 supplies only the date; the site is fixed.
        client: an OPTIONAL concrete infrared client (the offline test injects a
            ``FakeInfraredClient``). ``None`` -> the real SDK is lazily loaded by
            ``fetch_utci`` (production path).
        projects_root: where ``<project_id>/`` lives (default ``projects/``).
        weather_mode: ``"auto"`` (infrared, labelled EPW on a 500), ``"epw"``, or
            ``"infrared"`` (no fallback). Passed straight through to ``fetch_utci``.

    Returns:
        The ``utci_grid`` artifact dict (contract-valid), with an extra ``_weather_source``
        provenance label attached to the RETURNED dict only (never written to disk — the
        on-disk artifact is the clean, contract-valid grid).

    Raises:
        ClimateFetchError / RuntimeError: on any fetch failure (stage left NOT done, no
            artifact written) or the live-call cap being exceeded.
    """
    project_root = Path(projects_root) if projects_root is not None else Path("projects")
    input_hash = _site_input_hash(site_polygon, date)

    # ── 1) CACHE CHECK (manifest decides whether to call at all) ──────────────
    m = _load_manifest(project_id, project_root)
    if m.is_reusable(_STAGE, input_hash, _STAGE):
        # Cache hit: load and return the persisted artifact with ZERO live calls
        # (T-02a-13; ``test_cache_hit_no_live_call`` asserts run_count stays 1).
        artifact_path = m.project_dir / _ARTIFACT_NAME
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        cached_source = _read_cached_weather_source(m.project_dir)
        if cached_source != "infrared":
            # Same never-silent label discipline as the live path; the on-disk artifact
            # stays clean (the EPW label lives in the per-project replay cache file).
            artifact["_weather_source"] = cached_source
        return artifact

    # ── 2) LIVE-CALL CAP (backstop ACROSS calls sharing a client) ─────────────
    # Count this cache-MISS dispatch against the per-client budget BEFORE we run, so a
    # runaway loop of distinct-date misses trips the cap (CCA-F P2; ``test_live_call_cap``).
    if client is not None:
        prior = _LIVE_DISPATCHES.get(client, 0)
        budget = LiveCallBudget(cap=LIVE_CALL_CAP)
        budget.n = prior
        budget.record("run_climate_stage")  # raises ClimateFetchError("...cap...") past cap
        _LIVE_DISPATCHES[client] = prior + 1

    # ── 3) MISS: mark running, fetch, fail-safe on error ──────────────────────
    m.mark_running(_STAGE)
    lon, lat = _site_centroid(site_polygon)
    polygon = site_polygon.get("geometry", site_polygon)
    client_factory = _client_factory_from(client)
    try:
        merged_grid, bounds, weather_source = fetch_utci(
            lat=lat,
            lon=lon,
            polygon=polygon,
            date=date,
            weather_mode=weather_mode,
            # A generous per-fetch budget: the orchestrator-level cap above is the real
            # backstop; this one only guards a single fetch's internal preview+run pair.
            budget=LiveCallBudget(cap=LIVE_CALL_CAP * 2),
            client_factory=client_factory,
        )
    except ClimateFetchError:
        # Failure-safe: stage NOT done, NO artifact written (T-02a-11). Persist the
        # not-done manifest so resume re-runs this stage, then surface the typed error.
        m.mark_failed(_STAGE)
        m.write()
        raise

    # ── 4) SHAPE (Plan 02: crop -> project once -> resample 6 m -> emit cells) ─
    artifact = grid_to_utci_artifact(merged_grid, bounds)

    # ── 5) VALIDATE-THEN-WRITE (the gate: invalid never reaches disk) ─────────
    validate(artifact, _STAGE)  # raises BEFORE any write (mirrors Phase 1)
    m.project_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = m.project_dir / _ARTIFACT_NAME
    artifact_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    output_hash = content_hash(artifact)
    m.mark_done(_STAGE, _ARTIFACT_NAME, input_hash, output_hash)
    m.write()

    # Secondary replay cache: persist the weather source label so a cache-HIT re-run can
    # report it too (makes a forced re-run free; per-project, never global).
    _write_cached_weather_source(m.project_dir, weather_source)

    # ── 6) PROVENANCE (UTCI GROUNDED; weather source labelled, never silent) ──
    ledger = ProvenanceLedger()
    utci_values = [c["utci_c"] for c in artifact["cells"]]
    mean_utci = round(sum(utci_values) / len(utci_values), 4) if utci_values else None
    ledger.grounded(
        "baseline_utci_c",
        mean_utci,
        source=f"infrared.city UTCI ({weather_source})",
        stage=_STAGE,
        unit="celsius",
    )
    if weather_source != "infrared":
        # EPW-sourced run: record the substitution EXPLICITLY (T-02a-12, never silent).
        # Still GROUNDED data (real measured Barcelona weather), different source string.
        ledger.grounded(
            "weather_source",
            weather_source,
            source=f"weather fallback ({weather_source}); infrared weather endpoint degraded",
            stage=_STAGE,
        )
    # The band + cell size are conventions — record them ASSUMED (never as grounded data).
    ledger.assumed(
        "peak_heat_hour_band",
        list(PEAK_HEAT_HOUR_BAND),
        source="ASSUMED A1 — 12:00-16:00 peak-heat window (PRD silent on the exact band)",
        stage=_STAGE,
    )
    ledger.assumed(
        "cell_size_m",
        CELL_SIZE_M,
        source="ASSUMED — 6.0 m master-lattice resolution (CONTRACT-03, CONTEXT Q1)",
        stage=_STAGE,
        unit="metre",
    )
    ledger.write(m.project_dir / "provenance.json")

    # Attach the weather-source label to the RETURNED dict ONLY when it is a non-infrared
    # (EPW) source — the never-silent provenance label the EPW test reads. On the default
    # infrared path the returned dict stays the clean, contract-valid grid (the on-disk
    # artifact is ALWAYS clean — the schema's additionalProperties:false forbids the key).
    if weather_source != "infrared":
        artifact["_weather_source"] = weather_source
    return artifact


# --------------------------------------------------------------------------- #
# Secondary per-project weather-source replay cache
# --------------------------------------------------------------------------- #
_WEATHER_SOURCE_FILE = "utci_weather_source.txt"


def _write_cached_weather_source(project_dir: Path, weather_source: str) -> None:
    """Persist the weather source label next to the artifact (per-project, never global)."""
    (project_dir / _WEATHER_SOURCE_FILE).write_text(weather_source, encoding="utf-8")


def _read_cached_weather_source(project_dir: Path) -> str:
    """Read the persisted weather source label; default to ``infrared`` if absent."""
    path = project_dir / _WEATHER_SOURCE_FILE
    if path.exists():
        return path.read_text(encoding="utf-8").strip() or "infrared"
    return "infrared"
