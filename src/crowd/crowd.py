"""Crowd Layer orchestrator — ``run_crowd_stage`` (CROWD-01/04, the Phase 2b spine).

This is the integration seam that wires the three Phase-2b parts into one cache-first
stage — the line-for-line analogue of ``run_climate_stage``:

    rollout (Plan 02, the lazy-SB3 inference seam)
        -> build_crowd_grid (Plan 03, the trajectory -> master-lattice transform)
            -> validate-then-write projects/<id>/crowd_grid.json (manifest-gated)
                -> provenance ledger (crowd_density ASSUMED; sim seed logged)

Correctness properties this function owns (the truths Plan 04 proves):

  1. CACHE-FIRST. The manifest decides whether to call at all: a cache hit on the
     ``(capacity, lattice, seed)`` input hash returns the persisted artifact with ZERO
     rollout compute (T-02b-11 stale-cache; ``test_cache_hit_no_compute`` asserts the
     injected rollout call-counter stays at 1).
  2. FAILURE-SAFE. A rollout/transform failure leaves the ``crowd_grid`` manifest stage
     NOT done and writes NO artifact — resume re-runs it, never a half-written grid
     (T-02b-12; ``test_failure_leaves_stage_not_done``).
  3. VALIDATE-THEN-WRITE. ``validate(artifact, "crowd_grid")`` runs BEFORE any byte hits
     disk, so an invalid/partial grid can never be persisted (mirrors run_climate_stage).
  4. NEVER-SILENT PROVENANCE. crowd_density is recorded ASSUMED by default via
     ``ledger.crowd_density(...)`` which HARD-CODES the ASSUMED tier (CLAUDE.md
     non-negotiable). It is promoted to DERIVED (source ``MODEL_CARD.md``) ONLY when the
     benchmark-produced, policy-bound artifact ``src/crowd/benchmark_result.json`` proves the
     Weidmann FD benchmark passed AGAINST THE EXACT policy.zip bytes being rolled out — its
     recorded ``policy_sha256`` must match the SHA-256 of the policy actually used AND
     ``passed`` must be true. There is NO caller-supplied flip flag: a boolean a caller can set
     freely is not validation (CR-01 / acceptance integrity, T-02b-16). If the artifact is
     absent, stale (hash mismatch), or red, crowd_density stays ASSUMED — NEVER flipped while
     the benchmark is red. The fixed sim seed is logged ASSUMED (T-02b-13;
     ``test_provenance_crowd_density_assumed``).

LATTICE AUTHORITY (CONTRACT-03 / T-02b-08): the lattice is READ from utci_grid.json and
passed UNCHANGED to ``build_crowd_grid`` — never re-derived. ``build_crowd_grid`` emits the
SAME object, so ``crowd_grid.lattice`` is byte-equal to ``utci_grid.lattice`` (the XFN-04
climate x crowd alignment seam).

PURITY / QUARANTINE (T-02b-14): ``stable_baselines3`` / ``torch`` are NEVER imported at this
module's top level — ``rollout`` (which lazy-imports SB3) is imported INSIDE the cache-MISS
path, so ``import crowd.crowd`` is torch-free and the cache/fail-safe tests inject a fake
policy and run in the base suite. ``FestivalEnv`` imports ``gymnasium`` (a crowd-extra dep),
so the default ``env_factory`` is ALSO lazy-imported inside the miss path; an injected
``env_factory`` keeps the integration tests gymnasium-free too.

karpathy: one linear orchestration function. The manifest owns resume; the rollout owns
determinism; build_crowd_grid owns the transform — so there is no DAG engine and no retry
loop here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np  # base dep (torch-free); used only for the grid-handoff downsample

# pythonpath=["src"] (pyproject) makes the sibling packages importable bare.
# AGENT_RADIUS_M / SIM_STEPS_JPS / STEP_DT_JPS_S are plain ints/floats (torch-free, jupedsim-free):
# they fold into the JuPedSim cache fingerprint (_jupedsim_fingerprint) — importing them does NOT
# pull jupedsim, so the module-import purity guard (no top-level jupedsim/torch) stays green.
from crowd.constants import (
    AGENT_DIVISOR,
    AGENT_RADIUS_M,
    GRID_STILLPOINT_BUDGET,
    SEED,
    SIM_STEPS_JPS,
    STEP_DT_JPS_S,
)
from crowd.grid import build_crowd_grid
from crowd.wgs84_export import trajectories_payload
from crowd.site import (
    DEFAULT_BOUNDARY_PATH,
    DEFAULT_FESTIVAL_PATH,
    DEFAULT_NOGO_PATH,
)
from manifest.manifest import Manifest, content_hash
from provenance.ledger import ProvenanceLedger
from validate.validate import validate

_STAGE = "crowd_grid"
_ARTIFACT_NAME = "crowd_grid.json"
#: WGS84 per-step agent trajectory for the live map (de-mock — served by the
#: /api/artifacts/{id}/trajectories endpoint). Written beside the cached artifact.
_TRAJECTORIES_NAME = "trajectories.json"

# The committed FD-passing PPO weights (Plan 02). Resolved relative to this module so the
# default production path works regardless of the process CWD.
_POLICY_FILENAME = "policy.zip"

# The benchmark-produced, policy-bound provenance artifact (CR-01). ``tests/test_crowd_benchmark.py``
# writes this on a GREEN FD gate: {policy_sha256, bench_tol, densities, measured, reference,
# passed, measured_on}. ``run_crowd_stage`` reads it and promotes crowd_density to DERIVED ONLY
# when its recorded policy hash matches the policy.zip bytes actually rolled out AND passed is
# true. No caller flag can flip the tier — only this artifact can (acceptance integrity).
_BENCHMARK_RESULT_FILENAME = "benchmark_result.json"

# The JuPedSim density-validation artifact (2026-06-22). ``scripts/crowd_validation/
# run_lyon_validation.py`` writes this on a GREEN distribution gate vs the REAL measured Lyon
# MADRAS festival density (Zenodo 10.5281/zenodo.13830435, CC-BY 4.0): {passed, engine_fingerprint,
# observed, simulated, ...}. ``_crowdsim_benchmark_is_green`` reads it and promotes the crowd-density
# MAGNITUDE tier to DERIVED ONLY when passed is true AND its engine fingerprint matches the live
# CFSM engine identity (jupedsim version + model + agent radius). No caller flag can flip it — only
# the machine-emitted artifact can (acceptance integrity, mirror of the PPO gate, CR-01).
_CROWDSIM_BENCHMARK_FILENAME = "benchmark_result_crowdsim.json"


def _crowdsim_engine_fingerprint() -> str:
    """Engine IDENTITY string the Lyon validation must match to certify THIS engine.

    Binds the DERIVED promotion to the engine that was validated, NOT to the validation
    scenario's agent count/seed (those are Lyon-specific). A jupedsim version bump or an
    AGENT_RADIUS_M change (both alter emergent density) invalidates the green artifact → the tier
    snaps back to ASSUMED. jupedsim is lazy-imported (version only); absent wheel → 'unavailable'
    so the offline base tier never imports it AND can never spuriously match.
    """
    try:
        import jupedsim as jps  # noqa: PLC0415 (lazy — keeps base-tier import jupedsim-free)

        ver = getattr(jps, "__version__", "unknown")
    except Exception:
        ver = "unavailable"
    return f"jupedsim={ver};model=CollisionFreeSpeedModel;radius={AGENT_RADIUS_M}"


def _crowdsim_benchmark_is_green() -> bool:
    """True ONLY if benchmark_result_crowdsim.json proves the density-distribution gate passed
    AGAINST THIS engine identity. A missing/edited artifact, a fingerprint mismatch (engine/radius
    drift), or passed != true keeps crowd_density ASSUMED — the non-negotiable floor."""
    path = Path(__file__).resolve().parent / _CROWDSIM_BENCHMARK_FILENAME
    if not path.exists():
        return False
    try:
        res = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return res.get("passed") is True and res.get("engine_fingerprint") == _crowdsim_engine_fingerprint()


def _default_policy_path() -> Path:
    """Path to the committed ``policy.zip`` (frozen FD-passing PPO weights, Plan 02)."""
    return Path(__file__).resolve().parent / _POLICY_FILENAME


def _benchmark_result_path() -> Path:
    """Path to the benchmark-produced provenance artifact next to this module (CR-01)."""
    return Path(__file__).resolve().parent / _BENCHMARK_RESULT_FILENAME


# The committed real-site geometry layer files (INPUTS, 259d3fb) — explicit runtime inputs whose
# CONTENT-HASH folds into the manifest cache key so a corrected layout is a cache MISS (T-02.1-15).
_SITE_GEOJSON_PATHS = (DEFAULT_FESTIVAL_PATH, DEFAULT_BOUNDARY_PATH, DEFAULT_NOGO_PATH)


def _site_content_hash(lattice: dict) -> str:
    """Content-hash of the site geometry: the three committed geojson layers + the READ lattice.

    The site files (festival map / boundary / blockers) are EXPLICIT runtime inputs: a corrected
    layout MUST invalidate the cache (no stale grid served under a changed site — T-02.1-15). We
    hash the RAW bytes of each committed geojson (cheap, torch-free, no shapely parse needed) plus
    the lattice descriptor the blocked-cell rasterisation depends on — so a layout edit OR a
    lattice change is a cache miss. ``content_hash`` gives the same canonical-JSON digest the rest
    of the input key uses. Missing files hash as an explicit sentinel (still deterministic; the
    real-site run would fail loudly downstream, never serve a stale grid).
    """
    parts = []
    for p in _SITE_GEOJSON_PATHS:
        try:
            parts.append(_sha256_bytes(Path(p).read_bytes()))
        except OSError:
            parts.append(f"MISSING:{Path(p).name}")
    return content_hash({"site_geojson": parts, "lattice": lattice})


def _sha256_bytes(data: bytes) -> str:
    """SHA-256 hex digest of raw bytes (torch-free — pure hashlib)."""
    return hashlib.sha256(data).hexdigest()


def _policy_sha256(policy_path) -> str | None:
    """SHA-256 of the policy.zip bytes, or ``None`` for an injected in-memory policy object.

    An injected policy object (the torch-free integration tests) has no on-disk bytes to hash,
    so it can NEVER match a recorded benchmark hash — it stays ASSUMED, which is correct: a fake
    policy was never benchmarked. Only a real, hashable policy.zip can be promoted.
    """
    if policy_path is None:
        policy_path = _default_policy_path()
    if hasattr(policy_path, "predict"):  # injected in-memory policy — no bytes to bind
        return None
    p = Path(policy_path)
    if not p.exists():
        return None
    return _sha256_bytes(p.read_bytes())


def _benchmark_is_green(policy_path) -> bool:
    """True ONLY if benchmark_result.json proves the FD gate passed against THIS policy.zip.

    The DERIVED promotion is gated here, not on any caller flag (CR-01). Returns True iff:
      1. ``benchmark_result.json`` exists next to this module and parses, AND
      2. its recorded ``policy_sha256`` equals the SHA-256 of the policy.zip bytes being rolled
         out (so a retrained/swapped policy that has not been re-benchmarked stays ASSUMED), AND
      3. ``passed`` is true.
    Any failure (missing artifact, hash mismatch, red gate, injected non-hashable policy) keeps
    crowd_density ASSUMED — the non-negotiable floor.
    """
    res_path = _benchmark_result_path()
    if not res_path.exists():
        return False
    try:
        res = json.loads(res_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    current_hash = _policy_sha256(policy_path)
    if current_hash is None:
        return False  # injected/missing policy — never promotable
    return res.get("policy_sha256") == current_hash and res.get("passed") is True


# --------------------------------------------------------------------------- #
# Manifest persistence (resume across process / across calls) — copied from
# run_climate_stage's _load_manifest shape (Manifest has no restore constructor).
# --------------------------------------------------------------------------- #
def _load_manifest(project_id: str, project_root: Path) -> Manifest:
    """Load a persisted ``manifest.json`` if present, else a fresh manifest.

    Cache-across-calls hinges on this: the FIRST ``run_crowd_stage`` writes the manifest
    with ``crowd_grid`` done; a SECOND call reloads that state so ``is_reusable`` can
    short-circuit to a cache hit with ZERO rollout compute. ``Manifest`` has no constructor
    for an existing state, so we restore the stage records by hand (identical to
    ``climate.climate._load_manifest``).
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


def _downsample_for_grid(traj):
    """Stride-downsample the rollout trajectory at the GRID HANDOFF, anchoring the terminal frame.

    The site-native runtime rolls SIM_STEPS_V2 × N still-points (910k at the real N=650). The
    dwell-DBSCAN's pairwise neighbourhood is O(still-points²) memory; left unbounded it would OOM
    at the real scale (T-02.1-18). When ``steps × agents`` exceeds ``GRID_STILLPOINT_BUDGET`` we
    stride-subsample the LEADING (step) axis so the still-point count fits the budget, then ANCHOR
    the terminal frame (append the last step if the stride skipped it) — density snaps to the FINAL
    positions, and dwell clusters survive subsampling (a dwell run spans many steps, A6). grid.py is
    NEVER edited: it still receives a ``(steps × agents × 4)`` array (CONTRACT — the transform is
    horizon-agnostic; the downsample is purely an orchestrator/handoff concern, RESEARCH §FROZEN).

    Returns the (possibly downsampled) trajectory unchanged when it is already within budget.
    """
    arr = np.asarray(traj)
    steps = arr.shape[0]
    agents = arr.shape[1] if arr.ndim >= 2 else 1
    est_points = steps * agents
    if est_points <= GRID_STILLPOINT_BUDGET or steps <= 1:
        return arr
    stride = int(np.ceil(est_points / GRID_STILLPOINT_BUDGET))
    # Stride-subsample the step axis, then ANCHOR the terminal frame (density snaps to it).
    idx = np.unique(np.concatenate([np.arange(0, steps, stride), [steps - 1]]))
    return arr[idx]


def _default_env_factory():
    """The default SITE-NATIVE env factory (Plan 02.1-05): builds the REAL-site ``FestivalEnv``.

    Returns a factory ``(*, lattice, utci_cells, n_agents, seed) -> FestivalEnv`` that loads the
    committed site geometry (19 real stages + 2 entrances + 13 impassable blockers via
    ``load_site_geometry`` on the READ lattice), applies demand-weighted goals for the documented
    representative slice (capacity-class floor × headliner popularity — refines demand, does NOT
    gate acceptance: threat T-02.1-04), and constructs the env on the V2 SITE path
    (``site_geometry=...`` → real gates/stages, blocked-cell revert, per-goal flow-field cache,
    seeded staggered arrivals). This is the SAME geometry ``conftest_crowd.build_real_site_env``
    and the V2 demo roll the committed ``policy.zip`` through.

    gymnasium / the site loader / the demand table are lazy-imported INSIDE the factory (never at
    module top) so ``import crowd.crowd`` stays free of gymnasium/SB3/torch. An injected
    ``env_factory`` bypasses this entirely (the torch-free integration tests inject a synthetic env).
    """
    from crowd.demand import goal_weights_for_slice, load_set_times
    from crowd.env import FestivalEnv
    from crowd.site import load_site_geometry

    def _factory(*, lattice, utci_cells=None, n_agents=1, seed=SEED):
        geo = load_site_geometry(lattice=lattice)  # real committed geojson defaults

        # Demand-weighted goals for the committed representative slice (capacity-class × headliner
        # popularity). Refines demand only; a wrong weight cannot make any gate pass (T-02.1-04).
        table = load_set_times()
        slice_meta = table["_meta"]["default_slice"]
        names = [m["name"] for m in geo["stage_meta"]]
        classes = [m["class"] for m in geo["stage_meta"]]
        geo["goal_weights"] = list(
            goal_weights_for_slice(
                names, classes,
                day=slice_meta["day"], hour_block=slice_meta["hour_block"], table=table,
            )
        )

        return FestivalEnv(
            lattice=lattice,
            utci_cells=utci_cells,
            n_agents=int(n_agents),
            seed=seed,
            site_geometry=geo,
        )

    return _factory


# --------------------------------------------------------------------------- #
# The stage
# --------------------------------------------------------------------------- #
# The model card that DOCUMENTS the Weidmann FD validation — the DERIVED-promotion source
# string (Plan 05). crowd_density is trusted (DERIVED) only because the FD benchmark passes;
# this card is the auditable provenance for that trust.
_MODEL_CARD = "MODEL_CARD.md"


def _jupedsim_fingerprint(sim_factory=None) -> dict:
    """Cache fingerprint for the live crowd ENGINE — replaces the dead PPO policy-SHA term.

    The crowd field is a pure function of the engine identity: a ``jupedsim`` version bump or a
    CFSM model-param change MUST be a clean cache MISS (T-15-07 — a stale grid can never be served
    under a changed engine), exactly mirroring the old ``policy.zip`` SHA → MISS-on-retrain
    discipline. ``jupedsim`` is lazy-imported HERE (only on a real run) so importing this module
    stays jupedsim-free (the Plan-01 purity guard).

    When ``sim_factory`` is INJECTED (the base-tier tests), there is no real engine to fingerprint
    and jupedsim is not installed — return a STATIC ``"injected"`` fingerprint so the base test
    never imports jupedsim AND the cache key stays stable across the two calls of the cache-hit
    proof (mirror of the ``_policy_sha256(...) or "injected"`` idiom).
    """
    model_params = {
        "sim_steps": SIM_STEPS_JPS,
        "radius": AGENT_RADIUS_M,
        "dt": STEP_DT_JPS_S,
    }
    if sim_factory is not None:
        # Injected engine (tests): a static, jupedsim-free fingerprint — stable across calls.
        return {
            "engine": "jupedsim",
            "version": "injected",
            "model": "CollisionFreeSpeedModel",
            "model_params": model_params,
            "seed": SEED,
        }
    # Read the installed jupedsim version via importlib.metadata rather than importing the wheel:
    # the shell must carry no jupedsim-import token at all (the Plan-01 static purity guard
    # quarantines the wheel inside src/crowdsim/). ``version(...)`` reads the dist metadata without
    # loading the native extension, and is reached ONLY on a real run.
    from importlib.metadata import version  # lazy (stdlib)

    return {
        "engine": "jupedsim",
        "version": version("jupedsim"),
        "model": "CollisionFreeSpeedModel",
        "model_params": model_params,
        "seed": SEED,
    }


def _default_sim_factory():
    """Thin lazy seam to the live JuPedSim CFSM engine (Plan 02, ``src/crowdsim/``).

    Lazy-imports ``crowdsim.simulation`` (which itself lazy-imports ``jupedsim``/``shapely`` INSIDE
    its factory body), so this is reached ONLY on the cache-MISS path of a real run — ``import
    crowd.crowd`` stays free of jupedsim/torch (the purity guard). Returns the engine's
    ``(*, lattice, utci_cells, n_agents, seed) -> (steps×agents×4)`` factory.
    """
    from crowdsim.simulation import _default_sim_factory as _f  # lazy: pulls jupedsim only here

    return _f()


def run_crowd_stage(
    project_id: str,
    *,
    projects_root: Path | str | None = None,
    policy_path=None,
    env_factory=None,  # accepted-but-ignored on the live path (back-compat; legacy PPO)
    sim_factory=None,  # NEW injection seam (default -> lazy jupedsim, crowdsim.simulation)
) -> dict:
    """Run the crowd stage: cache-first JuPedSim sim -> transform -> validate-then-write -> label.

    LIVE PATH (D-06): the crowd field is produced by the JuPedSim CFSM engine
    (``crowdsim.simulation._default_sim_factory``), lazy-imported on the cache-MISS path. The
    legacy PPO rollout (``policy_path``/``env_factory``) is the DORMANT, reversible fallback (D-04)
    — it is NOT called on the live path.

    Args:
        project_id: the run id; artifacts live under ``<projects_root>/<project_id>/``.
        projects_root: where ``<project_id>/`` lives (default ``projects/``).
        sim_factory: OPTIONAL injected callable ``(*, lattice, utci_cells, n_agents, seed) ->
            (steps×agents×4) ndarray`` (the JuPedSim engine seam). The base-tier tests inject a
            torch/jupedsim-free synthetic factory so cache/fail-safe/provenance are proven WITHOUT
            jupedsim installed. ``None`` -> the lazily-imported live JuPedSim engine (production).
        policy_path: ACCEPTED-BUT-IGNORED on the live path (legacy-PPO back-compat). The live
            ``app.py`` passes neither this nor ``env_factory`` (verified) — kept only so older
            tests injecting them still import. The PPO stack is dormant (D-04).
        env_factory: ACCEPTED-BUT-IGNORED on the live path (legacy-PPO back-compat; see above).

    Provenance is NOT a caller choice (CR-01) and never promotes on the live path: crowd_density is
    ALWAYS recorded ASSUMED, Fruin/Still-anchored (CROWD-09) — the JuPedSim CFSM supplies spatial
    DISTRIBUTION only, the magnitude is literature-anchored, and NO FD benchmark validates it. The
    ``_benchmark_is_green`` DERIVED gate stays bound to the dormant PPO reference and is never
    reached here. The fixed sim seed is logged ASSUMED.

    Returns:
        The ``crowd_grid`` artifact dict (contract-valid): ``schema_version``, ``crs``,
        ``lattice`` (the SAME object read from utci_grid.json — XFN-04 byte-equality),
        ``cells``, ``dwell_zones``, ``flow_vectors``.

    Raises:
        Any rollout/transform error (stage left NOT done, no artifact written), or a
        ``jsonschema`` ``ValidationError`` if the shaped artifact violates the contract
        (raised BEFORE any write).
    """
    project_root = Path(projects_root) if projects_root is not None else Path("projects")
    pdir = project_root / project_id

    # Read the inputs: capacity (parsed_brief) + lattice authority (utci_grid).
    brief = json.loads((pdir / "parsed_brief.json").read_text(encoding="utf-8"))
    utci = json.loads((pdir / "utci_grid.json").read_text(encoding="utf-8"))
    lattice = utci["lattice"]  # AUTHORITY — passed UNCHANGED to build_crowd_grid (CONTRACT-03)
    capacity = brief["capacity"]
    n = max(1, capacity // AGENT_DIVISOR)  # PRD: N = capacity / 100 (named constant)

    # ── 1) CACHE CHECK (manifest decides whether to run the sim at all) ───────
    # The crowd field is a pure function of (capacity, lattice, seed, ENGINE, SITE GEOMETRY). Fold
    # the JuPedSim ENGINE identity (T-15-07: a jupedsim version / CFSM model-param change → cache
    # MISS, never a stale PPO-fingerprinted grid served under JuPedSim — replaces the dead policy-SHA
    # term) AND the site-geometry content-hash (Plan 02.1-05 / T-02.1-15: the real gates/stages/
    # blockers are EXPLICIT inputs, so a corrected layout → cache MISS) into the key.
    site_fp = _site_content_hash(lattice)
    input_hash = content_hash(
        {
            "capacity": capacity,
            "lattice": lattice,
            "seed": SEED,
            "engine": _jupedsim_fingerprint(sim_factory),  # REPLACES "policy": policy_fp (T-15-07)
            "site_geometry": site_fp,
        }
    )
    m = _load_manifest(project_id, project_root)
    if m.is_reusable(_STAGE, input_hash, _STAGE):
        # Cache hit: load and return the persisted artifact with ZERO sim compute
        # (T-02b-11; ``test_cache_hit_no_compute`` asserts the sim-build counter stays at 1).
        artifact_path = m.project_dir / _ARTIFACT_NAME
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        # Re-emit provenance on the cache hit too — crowd_density is ALWAYS ASSUMED/Fruin-Still on
        # the JuPedSim path (CROWD-09), so the persisted tier always reflects the live-path floor.
        _write_provenance(m.project_dir, artifact)
        return artifact

    # ── 2) MISS: mark running, JuPedSim sim -> transform, fail-safe on error ──
    m.mark_running(_STAGE)
    try:
        # The live JuPedSim CFSM engine (D-06). ``_default_sim_factory`` lazy-imports
        # ``crowdsim.simulation`` (which lazy-imports jupedsim/shapely INSIDE its body), so the
        # heavy native wheel is reached ONLY here on the cache MISS — never at module top. An
        # injected ``sim_factory`` (base-tier tests) bypasses jupedsim entirely. The factory returns
        # the FULL ``(steps×agents×4)`` array (the same contract the dormant PPO rollout returned),
        # so the ``trajectories.json`` write below and the FROZEN ``build_crowd_grid`` are unchanged.
        factory = sim_factory or _default_sim_factory()
        traj = factory(lattice=lattice, utci_cells=utci["cells"], n_agents=n, seed=SEED)
        # DOWNSAMPLE at the grid HANDOFF (an orchestrator concern; grid.py stays FROZEN). At the real
        # N=650 the per-step still-point count blows the DBSCAN pairwise-memory budget (T-02.1-18);
        # stride-downsample the trajectory BEFORE build_crowd_grid with the TERMINAL frame ANCHORED
        # (density snaps to the final positions). grid.py still receives a (steps×agents×4) array —
        # just fewer rows; the transform is never edited (T-02.1-16).
        grid_traj = _downsample_for_grid(traj)
        artifact = build_crowd_grid(grid_traj, lattice)  # FROZEN — numpy + sklearn
    except Exception:
        # Failure-safe: stage NOT done, NO artifact written (T-02b-12). Persist the
        # not-done manifest so resume re-runs this stage, then surface the error.
        m.mark_failed(_STAGE)
        m.write()
        raise

    # ── 3) VALIDATE-THEN-WRITE (the gate: invalid never reaches disk) ─────────
    validate(artifact, _STAGE)  # raises BEFORE any write (mirrors run_climate_stage)
    m.project_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = m.project_dir / _ARTIFACT_NAME
    artifact_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    # Persist the WGS84 per-step agent trajectory for the live map (de-mock: the
    # SimulationView crowd animation reads THIS, not viz/data/demo_*). The full
    # per-agent trajectory (`traj`) exists ONLY on this cache-MISS path — crowd_grid.json
    # keeps density, not frames — so it must be written here, beside the cached
    # artifact, BEFORE mark_done so a write failure is failure-safe (stage not done,
    # resume re-sims and rewrites both). Same shared emitter as the demo generator.
    (m.project_dir / _TRAJECTORIES_NAME).write_text(
        json.dumps(trajectories_payload(traj, "JuPedSim CFSM site-native run"), separators=(",", ":")),
        encoding="utf-8",
    )

    output_hash = content_hash(artifact)
    m.mark_done(_STAGE, _ARTIFACT_NAME, input_hash, output_hash)
    m.write()

    # ── 4) PROVENANCE (crowd_density: ALWAYS ASSUMED + Fruin/Still on the JuPedSim path) ──────────
    _write_provenance(m.project_dir, artifact)

    return artifact


#: The JuPedSim-path crowd_density source string (CROWD-09 / Pitfall 5.6). The CFSM supplies the
#: spatial DISTRIBUTION of agents; the per-cell density MAGNITUDE is literature-anchored (Fruin
#: Level-of-Service / G.K. Still crowd-dynamics density bands), NOT measured and NOT FD-validated —
#: so the number stays ASSUMED forever on this path. It MUST reference Fruin/Still and contain NONE
#: of the dead PPO-benchmark concepts (Weidmann / policy.zip / MODEL_CARD), which validated the
#: RETIRED PPO speed-law, not the CFSM distribution.
_JUPEDSIM_DENSITY_SOURCE = (
    "JuPedSim Collision-Free Speed Model (CFSM) site-native simulation — FIELD tier ASSUMED "
    "(weakest-input-wins). The per-cell density MAGNITUDE is anchored to the Fruin pedestrian "
    "Level-of-Service bands and the G.K. Still crowd-dynamics density scale (and may be DERIVED-"
    "validated — see crowd_density_magnitude), but the SPATIAL ALLOCATION (which cells are busy) is "
    "ASSUMED (see crowd_spatial_allocation: real set-times timetable + organiser capacity drive it; "
    "popularity ordinal + spawn split are assumptions; no site data). So the per-cell field a "
    "consumer reads stays ASSUMED."
)

#: DERIVED source — used ONLY when the Lyon validation gate is green for this engine identity.
#: The density MAGNITUDE/distribution is validated against REAL measured festival crowd data.
_JUPEDSIM_DENSITY_SOURCE_DERIVED = (
    "JuPedSim CFSM crowd-density MAGNITUDE validated against the REAL measured MADRAS Lyon Fête-des-"
    "Lumières festival density (Zenodo 10.5281/zenodo.13830435, CC-BY 4.0): on the real Lyon walkable "
    "geometry with the observed population, the simulated density distribution matches the measured "
    "one within ±50% on mean/p90/p99 and respects the Fruin ≤6 ped/m² jam ceiling "
    "(benchmark_result_crowdsim.json, engine-fingerprint-bound). DERIVED for MAGNITUDE only — the "
    "site-specific SPATIAL ALLOCATION at Parc del Fòrum remains ASSUMED (see crowd_spatial_allocation)."
)


def _write_provenance(project_dir: Path, artifact: dict) -> None:
    """Emit ``provenance.json`` for the served crowd_grid — ALWAYS ASSUMED on the JuPedSim path.

    On the live JuPedSim path (D-06) crowd_density is ALWAYS recorded ASSUMED via
    ``ledger.crowd_density(...)`` (which HARD-CODES the tier — CLAUDE.md non-negotiable) with the
    Fruin/Still source string: the CFSM supplies spatial DISTRIBUTION only, the magnitude is
    literature-anchored, and NO FD benchmark validates it (CROWD-09 / Pitfall 5.6). The
    ``_benchmark_is_green`` DERIVED promotion stays bound to the DORMANT PPO reference (D-04) and is
    NEVER reached here — so the live path can never leak a Weidmann/policy.zip/MODEL_CARD source nor
    promote past ASSUMED (T-15-08). Called on BOTH the cache-miss and cache-hit paths so the
    persisted tier always reflects the live-path floor.
    """
    ledger = ProvenanceLedger()
    densities = [c["crowd_density_agents_per_cell"] for c in artifact["cells"]]
    mean_density = round(sum(densities) / len(densities), 4) if densities else 0.0

    # FIELD-level crowd_density is ALWAYS ASSUMED — weakest-input-wins: the per-cell field combines a
    # density MAGNITUDE (validatable) with a SPATIAL ALLOCATION (which cells are busy) that is ASSUMED,
    # so the field a downstream consumer reads stays ASSUMED (the non-negotiable floor; placement
    # therefore stays ASSUMED — XFN merge contract preserved). The hard-coded helper enforces it.
    ledger.crowd_density(
        mean_density,
        stage=_STAGE,
        source=_JUPEDSIM_DENSITY_SOURCE,
        unit="agents-per-cell",
    )
    # SUB-CLAIM: the density MAGNITUDE is promoted DERIVED (a SEPARATE entry — never the field tier)
    # only when the Lyon validation is green for THIS engine identity. This records the honest win
    # (magnitudes validated vs a real measured festival) without overclaiming the field/allocation.
    if _crowdsim_benchmark_is_green():
        ledger.derived(
            "crowd_density_magnitude",
            mean_density,
            source=_JUPEDSIM_DENSITY_SOURCE_DERIVED,
            stage=_STAGE,
            unit="agents-per-cell",
        )
    # SPATIAL ALLOCATION — ALWAYS ASSUMED (real timetable + capacity drive it, but popularity
    # ordinal + spawn split are assumptions and no site data validates Parc-del-Fòrum allocation).
    ledger.assumed(
        "crowd_spatial_allocation",
        "set-times timetable (GROUNDED) x organiser capacity (input) x popularity ordinal (ASSUMED) "
        "x gate spawn split (ASSUMED)",
        source="agent goals follow the REAL Primavera set_times_2026.json schedule and the organiser "
        "capacity input; the per-stage popularity ordinal (1-5) and 85/15 gate split are assumptions; "
        "no open data measures crowd density inside Parc del Forum, so WHICH cells are busiest is ASSUMED.",
        stage=_STAGE,
    )
    ledger.assumed(
        "sim_seed",
        SEED,
        source="fixed runtime inference seed (logged — same seed => byte-identical density field)",
        stage=_STAGE,
    )
    ledger.write(project_dir / "provenance.json")
