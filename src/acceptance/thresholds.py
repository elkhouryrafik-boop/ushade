"""Runtime X/Y loader + content-hash drift-guard (GATE-03 integrity, D-01).

The acceptance thresholds **X = 4 °C** (``x_utci_reduction_c``) and **Y = 70 %**
(``y_coverage_pct``) live in ONE place only: the frozen, content-hashed
``acceptance/thresholds.json``. This module is the gate's SINGLE runtime source of those
values — they are NEVER inlined as literals anywhere in ``src/acceptance/`` (a second copy
would be a drift vector the hash-guard could not catch; ``test_gate_reads_xy_from_loader``
enforces the absence).

Why a RUNTIME guard on top of the static ``tests/test_thresholds_immutable.py``: the static
test only fires when the suite runs. ``load_thresholds`` recomputes the canonical-JSON
sha256 over the ``{x_utci_reduction_c, y_coverage_pct}`` value block on EVERY load and
RAISES ``ThresholdDriftError`` if it diverges from the stored ``content_sha256`` — so a
post-run X/Y tuning (e.g. 4 -> 3 to make a borderline run pass) fails AT RUN TIME, not only
in a test. This is the anti-gate-gaming tripwire (threat T-00-06 / T-05b-04, Pitfall 3).

BASE TIER: stdlib only. The hash recipe is NOT re-implemented here — it is delegated to
``manifest.content_hash`` (the SAME canonical-JSON ``sort_keys=True, separators=(",",":")``
sha256 the ``acceptance/HASHING.md`` recipe and the static tripwire use, verified to produce
the byte-identical value-block hash). One recipe, one source.
"""

from __future__ import annotations

import json
from pathlib import Path

# manifest.content_hash is the canonical sort_keys/compact sha256 over a JSON object — the
# SAME recipe acceptance/HASHING.md documents for the threshold tripwire. Reuse it so the
# drift-guard math has exactly ONE source (never a second hashlib call to drift from it).
from manifest.manifest import content_hash

# Repo layout: src/acceptance/thresholds.py -> repo root is three parents up.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_THRESHOLDS_PATH = _REPO_ROOT / "acceptance" / "thresholds.json"


class ThresholdDriftError(Exception):
    """The on-disk threshold value block no longer matches its stored ``content_sha256``.

    Raised by ``load_thresholds`` when a recomputed canonical-JSON hash of
    ``{x_utci_reduction_c, y_coverage_pct}`` diverges from the file's ``content_sha256`` —
    i.e. someone edited X or Y after ``declared_on`` without (and they CANNOT legitimately)
    re-locking the hash. This is the runtime gate-gaming tripwire (threat T-00-06). Typed so
    the orchestrator can distinguish an integrity failure from any other I/O error (P6).
    """


def _recompute_hash(thresholds: dict) -> str:
    """Recompute the value-block content hash exactly as ``acceptance/HASHING.md`` specifies.

    The hash covers ONLY ``{x_utci_reduction_c, y_coverage_pct}`` — ``schema_version``,
    ``declared_on``, ``immutable`` and ``x_hash_input`` are deliberately outside it, so the
    gate VALUES are the only thing locked. Delegated to ``manifest.content_hash`` (canonical
    ``sort_keys=True, separators=(",",":")`` sha256) so the recipe lives in one place.
    """
    value_block = {
        "x_utci_reduction_c": thresholds["x_utci_reduction_c"],
        "y_coverage_pct": thresholds["y_coverage_pct"],
    }
    return content_hash(value_block)


def load_thresholds(path: Path | str | None = None) -> dict:
    """Load X/Y from the frozen ``acceptance/thresholds.json``, raising on a hash drift.

    Returns the parsed thresholds dict (``{"x_utci_reduction_c": 4, "y_coverage_pct": 70,
    ...}``) — the gate's ONLY source of X and Y. NO inline ``4``/``70`` lives anywhere in the
    gate package; the values come from this file every run.

    Reads the real frozen file by default; ``path`` lets a test point at a tampered copy
    (NEVER mutate the real file). RAISES ``ThresholdDriftError`` if the recomputed value-block
    sha256 != the stored ``content_sha256`` — the runtime anti-gate-gaming tripwire (T-00-06):
    a post-run X/Y tuning fails HERE, not only in the static test.
    """
    threshold_path = Path(path) if path is not None else _THRESHOLDS_PATH
    thresholds = json.loads(threshold_path.read_text(encoding="utf-8"))

    recomputed = _recompute_hash(thresholds)
    stored = thresholds.get("content_sha256")
    if recomputed != stored:
        raise ThresholdDriftError(
            "acceptance thresholds value block was changed without re-locking "
            "content_sha256 (gate-gaming / threat T-00-06): the recomputed hash "
            f"{recomputed!r} != stored {stored!r}. X/Y are immutable post-declaration "
            "(acceptance/HASHING.md); a tuned threshold is rejected at RUN TIME."
        )
    return thresholds
