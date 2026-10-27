"""GATE-01/02/03 — cache-first / fail-safe stage integration (DESIGNED-RED, Wave 0).

Designed-RED: imports ``from acceptance.acceptance import ...`` at module level, so collection
ERRORS with ``ModuleNotFoundError: No module named 'acceptance.acceptance'`` until the Wave-3 spine
ships. That collection error IS the Wave-0 success state; do NOT stub to pass.

Integration over a tmp COPY of ``projects/primavera-demo`` (clone the selection-stage shape):
read persisted artifacts → pure transforms → validate-then-write ``acceptance.json`` + sidecar →
ledger → ``manifest.mark_done``. Cache-first (a 2nd run does zero recompute) and fail-safe (an
INTERNAL error marks the stage NOT done; a FAIL verdict is ``mark_done``, never ``mark_failed``).

Load-bearing assertion (RESEARCH §GATE-03, Pitfall 6 + A6):
  * test_cache_first_and_fail_safe — the stage is cache-first; a FAIL verdict is a SUCCESSFUL
    stage outcome (written + mark_done), and ONLY an internal error takes the fail-safe path.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

# DESIGNED-RED import: errors at collection until acceptance.acceptance ships (Wave 3).
from acceptance.acceptance import MissingUpstreamArtifact, run_acceptance_stage

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEMO_DIR = _REPO_ROOT / "projects" / "primavera-demo"


def _copy_demo(tmp_path: Path) -> Path:
    """A writable tmp copy of the demo project (never mutate the real project)."""
    dst = tmp_path / "primavera-demo"
    shutil.copytree(_DEMO_DIR, dst)
    return dst


def test_cache_first_and_fail_safe(tmp_path):
    """The stage is cache-first; a FAIL is persisted (mark_done), fail-safe is internal-error-only."""
    project = _copy_demo(tmp_path)

    result = run_acceptance_stage(project_dir=project)
    acceptance_path = project / "acceptance.json"
    assert acceptance_path.exists(), "the verdict must be written (PASS or FAIL)"
    verdict = json.loads(acceptance_path.read_text(encoding="utf-8"))
    assert verdict["verdict"] in ("PASS", "FAIL"), verdict

    # Whatever the verdict, it is a SUCCESSFUL stage outcome — the stage is marked done, NOT failed
    # (a FAIL is never swallowed by the fail-safe — A6 / Pitfall 6).
    assert result.get("stage_done") is True, result
    assert result.get("stage_failed") is not True, result

    # Cache-first: a 2nd run over the unchanged project does zero recompute (clone selection cache).
    second = run_acceptance_stage(project_dir=project)
    assert second.get("cache_hit") is True, "a 2nd unchanged run must be a cache hit"


def test_missing_baseline_writes_no_partial_artifact(tmp_path):
    """MJ-01 — validate-then-write atomicity: a utci_grid stripped of ``baseline_utci_c`` is an
    INTERNAL error that must surface BEFORE any ``acceptance.json`` reaches disk.

    The sidecar baseline mean is derived from ``utci_grid.baseline_utci_c``. If that derivation can
    raise, it must run BEFORE the first write — otherwise the verdict file lands on disk while the
    stage is marked NOT done (a verdict-on-disk + stage-not-done contradiction). This proves no
    partial artifact is left behind.
    """
    project = _copy_demo(tmp_path)
    acceptance_path = project / "acceptance.json"

    # Force the COMPUTE path (not the cache): the demo ships a precomputed verdict + manifest, and
    # the cache key does not cover utci_grid — clear both so the stage recomputes and reaches the
    # baseline derivation. Assert acceptance.json is absent at start so its presence later == a write.
    acceptance_path.unlink(missing_ok=True)
    (project / "manifest.json").unlink(missing_ok=True)
    assert not acceptance_path.exists()

    # Strip the persisted baseline from every cell — _baseline_mean_c must then raise.
    utci_path = project / "utci_grid.json"
    grid = json.loads(utci_path.read_text(encoding="utf-8"))
    for cell in grid["cells"]:
        cell.pop("baseline_utci_c", None)
    utci_path.write_text(json.dumps(grid), encoding="utf-8")

    with pytest.raises(MissingUpstreamArtifact):
        run_acceptance_stage(project_dir=project)

    assert not acceptance_path.exists(), (
        "no partial acceptance.json may be written when the baseline derivation raises — "
        "all inputs must be validated/derived before the first byte hits disk (MJ-01)"
    )
