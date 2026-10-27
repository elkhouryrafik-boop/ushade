"""Gate-gaming tripwire (CONTRACT-04 / threat T-00-06).

`acceptance/thresholds.json` locks X = 4 °C and Y = 70 % with a content hash over
the *value block*. These tests recompute that hash exactly the way it was authored
(see acceptance/HASHING.md) and assert it matches. If anyone edits a threshold value
after `declared_on` to make a run pass, the recomputed hash diverges and this test
goes RED — post-hoc tuning becomes a test failure, not a judgment call.

karpathy: no fixtures, no parametrization — read the file, recompute, assert.
"""

import hashlib
import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_THRESHOLDS_PATH = _REPO_ROOT / "acceptance" / "thresholds.json"


def _load_thresholds() -> dict:
    return json.loads(_THRESHOLDS_PATH.read_text(encoding="utf-8"))


def _recompute_content_sha256(thresholds: dict) -> str:
    """Recompute the content hash exactly as acceptance/HASHING.md specifies:
    sha256 over canonical JSON of ONLY the {x_utci_reduction_c, y_coverage_pct}
    value block (sort_keys=True, separators=(",", ":"))."""
    value_block = {
        "x_utci_reduction_c": thresholds["x_utci_reduction_c"],
        "y_coverage_pct": thresholds["y_coverage_pct"],
    }
    canonical = json.dumps(value_block, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def test_content_hash_matches_value_block():
    """The stored content_sha256 equals the hash recomputed over the value block.

    THIS IS THE TRIPWIRE: mutate x_utci_reduction_c (e.g. 4 -> 3) or y_coverage_pct
    in acceptance/thresholds.json and the recomputed hash no longer matches the
    stored one, so this assertion fails. (Do not leave the file mutated.)
    """
    thresholds = _load_thresholds()
    recomputed = _recompute_content_sha256(thresholds)
    assert recomputed == thresholds["content_sha256"], (
        "thresholds.json value block was changed without updating content_sha256 "
        "(gate gaming / T-00-06): "
        f"recomputed={recomputed} stored={thresholds['content_sha256']}"
    )


def test_locked_threshold_values():
    """X = 4 °C, Y = 70 %, immutable flag set, and a declared_on date is present."""
    thresholds = _load_thresholds()
    assert thresholds["x_utci_reduction_c"] == 4, thresholds
    assert thresholds["y_coverage_pct"] == 70, thresholds
    assert thresholds["immutable"] is True, thresholds
    assert thresholds.get("declared_on"), "declared_on must be present and non-empty"
    assert thresholds["declared_on"] == "2026-06-10", thresholds
