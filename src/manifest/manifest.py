"""Manifest state machine + resume-from-last-good-stage (CONTRACT-07 / XFN-03).

The ``projects/<id>/manifest.json`` is HeatGuard's resume mechanism. Each pipeline
stage records its status and the content hashes of its inputs and output. A halted
run resumes from the FIRST stage whose cache check fails — never past a stage whose
upstream changed (Resume algorithm steps 1-4, 00-RESEARCH §Artifact DAG & Resume
Manifest).

The load-bearing correctness property (Pitfall 9 / Pitfall D / T-00-09): the cache
key is the **content hash of the inputs**, NOT "the file exists". A changed brief ->
changed ``input_hash`` -> cache MISS -> correct re-run + all downstream invalidated.
A cached artifact is additionally re-validated against its pinned contract before
reuse, so a corrupt/edited artifact is a miss even if the hashes line up.

TIER NOTE (deliberate, recorded — objective + 00-RESEARCH §Architectural
Responsibility Map): the Architectural Responsibility Map assigns manifest /
run-lifecycle to the NODE orchestrator. Phase 0 intentionally ships the CANONICAL
manifest logic + resume tests in PYTHON (this file) because the Phase-0 contract
tests and the resume-correctness proof live in pytest. The Node orchestrator in
Phase 1+ will OWN the runtime manifest writes, implemented against this SAME
manifest contract/algorithm. There is deliberately no ``manifest.ts`` in Phase 0 —
nothing in Phase 0 consumes it from Node (karpathy: no code without a consumer).
This is a deferred-ownership decision, not a tier violation.

REUSE: adapts CoolSpend ``sdk_client.py``'s geometry-SHA-256 disk-cache pattern
(content hash of inputs, not mtime) to the per-stage artifact cache (REUSE.md).

karpathy: a single ``Manifest`` class — no generic DAG engine, no scheduler. The
stage ORDER is a fixed list (the pipeline is linear); "downstream" = "later in the
list".
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

# pythonpath=["src"] (pyproject) makes the sibling validator importable as ``validate``.
from validate.validate import is_valid as _artifact_is_valid

# The pipeline DAG, in execution order. "Downstream of X" = every stage after X.
#
# Phase 14 (Plan 04, D-05/D-06): the greedy per-cell scoring + shade-polygon stages
# RETIRED with the v2.0 pivot — ``structure_zones`` (the ranked-zone MCLP placer at
# position 4, right after crowd_grid) is the SOLE canonical placement output. The
# downstream geometry/material/acceptance stages stay in the DAG for any future
# human-committed geometry path, but the API full-run no longer chains them (the
# cladding/cooling-proof chain awaits committed geometry, not a fabricated polygon).
STAGE_ORDER: tuple[str, ...] = (
    "parsed_brief",
    "utci_grid",
    "crowd_grid",
    "structure_zones",
    "gh_response",
    "material_selection",
    "acceptance_verdict",
    "render",
)

# Stage status vocabulary.
PENDING = "pending"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
_STATUSES = (PENDING, RUNNING, DONE, FAILED)


def content_hash(obj) -> str:
    """SHA-256 over a CANONICAL JSON serialization of ``obj``.

    Canonicalization (``sort_keys=True``, compact separators) makes the hash stable
    regardless of key order or incidental whitespace — the same recipe
    ``acceptance/HASHING.md`` documents for the thresholds tripwire. This is the
    cache key: a changed input changes the hash (Pitfall D — never an mtime/exists
    check).
    """
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    """UTC ISO-8601 timestamp (e.g. completed_at)."""
    return datetime.now(timezone.utc).isoformat()


class Manifest:
    """Stage-status state machine persisted to ``projects/<id>/manifest.json``.

    A fresh manifest has every stage ``pending``. Marking a stage done records its
    ``input_hash`` + ``output_hash`` + ``completed_at``. ``is_reusable`` decides a
    cache hit/miss from content hashes + artifact re-validation; ``invalidate_from``
    resets a stage and all downstream stages to pending; ``resume_point`` returns the
    first non-reusable stage.
    """

    def __init__(self, project_id: str, project_root: Path | str | None = None) -> None:
        self.project_id = project_id
        # Where the artifacts + manifest.json live (gitignored projects/<id>/).
        root = Path(project_root) if project_root is not None else Path("projects")
        self.project_dir = root / project_id
        self.created_at = _now_iso()
        # stage name -> stage record. Fresh = all pending, no hashes.
        self._stages: dict[str, dict] = {
            name: {
                "name": name,
                "status": PENDING,
                "artifact": None,
                "input_hash": None,
                "output_hash": None,
                "completed_at": None,
            }
            for name in STAGE_ORDER
        }

    # ── status accessors ──────────────────────────────────────────────────────
    def stage(self, name: str) -> dict:
        self._require_stage(name)
        return self._stages[name]

    def status(self, name: str) -> str:
        return self.stage(name)["status"]

    def _require_stage(self, name: str) -> None:
        if name not in self._stages:
            raise KeyError(f"unknown stage {name!r}; valid stages: {STAGE_ORDER}")

    def _downstream_of(self, name: str) -> list[str]:
        """The given stage and every LATER stage in DAG order."""
        self._require_stage(name)
        idx = STAGE_ORDER.index(name)
        return list(STAGE_ORDER[idx:])

    # ── transitions ───────────────────────────────────────────────────────────
    def mark_running(self, name: str) -> None:
        self.stage(name)["status"] = RUNNING

    def mark_failed(self, name: str) -> None:
        self.stage(name)["status"] = FAILED

    def mark_done(
        self, name: str, artifact_path: str, input_hash: str, output_hash: str
    ) -> dict:
        """Record a completed stage: status=done + hashes + completed_at."""
        st = self.stage(name)
        st["status"] = DONE
        st["artifact"] = artifact_path
        st["input_hash"] = input_hash
        st["output_hash"] = output_hash
        st["completed_at"] = _now_iso()
        return st

    def invalidate_from(self, name: str) -> list[str]:
        """Reset ``name`` and every downstream stage to pending; clear their hashes.

        Called when a stage's input changed (Resume algorithm step 2). Returns the
        list of invalidated stage names.
        """
        invalidated = self._downstream_of(name)
        for s in invalidated:
            st = self._stages[s]
            st["status"] = PENDING
            st["artifact"] = None
            st["input_hash"] = None
            st["output_hash"] = None
            st["completed_at"] = None
        return invalidated

    # ── cache decision (the load-bearing correctness logic) ───────────────────
    def is_reusable(
        self, name: str, current_input_hash: str, schema_name: str | None = None
    ) -> bool:
        """True iff the stage's cached artifact may be reused without re-running.

        Reusable IFF ALL hold (any failure -> cache MISS -> re-run + invalidate):
          1. status == done
          2. the on-disk artifact exists AND its content_hash == stored output_hash
             (NOT "file exists" — Pitfall D)
          3. the artifact still validates against its pinned contract (``schema_name``)
          4. stored input_hash == current_input_hash (upstream unchanged)
        """
        st = self.stage(name)

        # (1) only a completed stage can be reused
        if st["status"] != DONE:
            return False

        # (4) upstream/input must be unchanged
        if st["input_hash"] != current_input_hash:
            return False

        # (2) the artifact must exist and hash to the recorded output (content-based)
        artifact_path = st["artifact"]
        if not artifact_path:
            return False
        path = self._resolve_artifact(artifact_path)
        if not path.exists():
            return False
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if content_hash(artifact) != st["output_hash"]:
            return False

        # (3) the cached artifact must still satisfy its contract
        if schema_name is not None and not _artifact_is_valid(artifact, schema_name):
            return False

        return True

    def resume_point(
        self, current_input_hashes: dict[str, str], schema_names: dict[str, str] | None = None
    ) -> str | None:
        """First stage whose cache check fails, scanning in DAG order.

        ``current_input_hashes`` maps stage name -> the hash of its current inputs.
        Stages absent from the map are treated as not-reusable (must run). Returns
        the stage name to resume from, or ``None`` if every stage is reusable.
        """
        schema_names = schema_names or {}
        for name in STAGE_ORDER:
            if name not in current_input_hashes:
                return name
            if not self.is_reusable(
                name, current_input_hashes[name], schema_names.get(name)
            ):
                return name
        return None

    def _resolve_artifact(self, artifact_path: str) -> Path:
        """Resolve a stored artifact reference to a filesystem path.

        Absolute paths are used as-is; bare names resolve under ``project_dir``.
        """
        p = Path(artifact_path)
        return p if p.is_absolute() else (self.project_dir / p)

    # ── serialization ─────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "created_at": self.created_at,
            "stages": [self._stages[name] for name in STAGE_ORDER],
        }

    def write(self, path: Path | str | None = None) -> Path:
        """Persist manifest.json (default: ``project_dir/manifest.json``)."""
        out = Path(path) if path is not None else (self.project_dir / "manifest.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return out
