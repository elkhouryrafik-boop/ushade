"""Fixture loaders for the Phase-5b cooling-acceptance-gate suite (imported BY NAME).

Like ``conftest_geom.py`` / ``conftest_inventory.py``, this module is NOT auto-loaded (pytest only
auto-loads ``conftest.py``) — the gate tests import it explicitly. It exists so the Wave-2/3 gate
transforms (``acceptance.coverage`` / ``acceptance.delta`` / ``acceptance.thresholds`` /
``acceptance.comfort_gap`` / ``acceptance.acceptance``) can be unit-tested against the persisted
``projects/primavera-demo`` artifacts + tiny deterministic synthetic sets — no network, no torch,
no rhino3dm.

BASE TIER — NON-NEGOTIABLE: no rhino3dm / torch / infrared import anywhere in this module or the
gate tests. GATE-01 consumes the Q1 ``gh_meta.shadow_polygon_m`` plain-coords sidecar field (never
re-decodes the mesh); GATE-02 reads the persisted ``baseline_utci_c`` (never re-runs the sim).

karpathy: plain loaders + tiny dicts, no fixture-factory framework, no mock library.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_DEMO_DIR = _REPO_ROOT / "projects" / "primavera-demo"
_THRESHOLDS_PATH = _REPO_ROOT / "acceptance" / "thresholds.json"


# --------------------------------------------------------------------------- #
# Persisted-artifact loaders
# --------------------------------------------------------------------------- #
def load_demo(name: str) -> dict:
    """Read a persisted ``projects/primavera-demo/<name>.json`` artifact.

    ``name`` is the bare stem (``"utci_grid"``, ``"score_grid"``, ``"footprint"``,
    ``"material_selection"``, ``"gh_meta"``). The gate is a pure consumer of these on-disk
    contract artifacts (clone ``selection.py`` reads).
    """
    stem = name[:-5] if name.endswith(".json") else name
    return json.loads((_DEMO_DIR / f"{stem}.json").read_text(encoding="utf-8"))


def load_thresholds() -> dict:
    """The FROZEN ``acceptance/thresholds.json`` (X=4, Y=70, content_sha256)."""
    return json.loads(_THRESHOLDS_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Synthetic deterministic sets (known answers — the load-bearing assertions)
# --------------------------------------------------------------------------- #
def synthetic_priority_set() -> dict:
    """A tiny deterministic priority set + a known shadow polygon → a KNOWN coverage ratio.

    Four priority cells at integer centres; the shadow polygon (in the same near-origin frame)
    covers exactly 3 of the 4 → coverage = 75 %. ``min_corner_m`` is the offset the gate must
    translate the cell centres by (here (0, 0): the cells are already near-origin) — the synthetic
    set keeps the frame trivial so the coverage MATH is what is under test, not the translation.

    The 4th cell ``(50, 50)`` lies OUTSIDE the shadow but could sit UNDER a footprint — it is the
    Pitfall-12 trap (shadow ≠ footprint): a correct gate must NOT credit it.
    """
    return {
        # baseline_utci_c included so the same fixture drives the GATE-02 delta tests.
        "cells": [
            {"x_m": 1.0, "y_m": 1.0, "baseline_utci_c": 31.0},  # inside shadow
            {"x_m": 2.0, "y_m": 1.0, "baseline_utci_c": 31.0},  # inside shadow
            {"x_m": 1.0, "y_m": 2.0, "baseline_utci_c": 31.0},  # inside shadow
            {"x_m": 50.0, "y_m": 50.0, "baseline_utci_c": 31.0},  # OUTSIDE shadow (Pitfall 12)
        ],
        "shadow_polygon_m": {
            "basis": "synthetic",
            "min_corner_m": [0.0, 0.0],
            # a 3x3 box around the origin covering the first three cells, NOT the (50,50) cell
            "polygons_xy_m": [[[0.0, 0.0], [3.0, 0.0], [3.0, 3.0], [0.0, 3.0], [0.0, 0.0]]],
        },
        "expected_coverage_pct": 75.0,
        "expected_shaded_count": 3,
        "expected_priority_count": 4,
    }


def known_tau_membrane(tau: float) -> dict:
    """A material_selection-shaped dict with a KNOWN ``solar_transmissivity`` (the (1-τ) input).

    Carries ``cost_total_eur`` so the €/°C sidecar test can drive the placeholder-disclosure path
    (the demo cost is 0.0 — a misleading 0 must be disclosed, not printed bare).
    """
    return {
        "solar_transmissivity": tau,
        "cost_total_eur": 0.0,
        "selected_id": "membr-pe-yacht-shrinkwrap",
        "cooling_correction_factor": 1.0 - tau,
    }


def mutated_thresholds_copy(tmp_path: Path, x: int = 3) -> Path:
    """Write a TAMPERED copy of ``acceptance/thresholds.json`` into ``tmp_path``.

    The value block is mutated (``x_utci_reduction_c`` 4 → ``x``) but ``content_sha256`` is left
    UNCHANGED — exactly the post-run-tuning attack (threat T-00-06 / Pitfall 3). The runtime gate
    loader MUST recompute the hash and RAISE on this copy. NEVER mutate the real frozen file — this
    writes to ``tmp_path`` only (mirror conftest_geom's tmp discipline).
    """
    thresholds = load_thresholds()
    thresholds["x_utci_reduction_c"] = x  # tamper the value, leave the stored hash stale
    dst = tmp_path / "thresholds.json"
    dst.write_text(json.dumps(thresholds, indent=2), encoding="utf-8")
    return dst


def projected_shadow_from_gh_meta(gh_meta: dict) -> dict:
    """Extract the Q1 base-tier GATE-01 input from a ``gh_meta.json`` dict.

    Returns ``{"polygons_xy_m": [...], "min_corner_m": [minx, miny], "basis": str}`` — the plain
    coords + the translation offset the gate applies to the priority-cell centres. Raises a clear
    KeyError if the (older) sidecar predates the Q1 ``shadow_polygon_m`` field.
    """
    return gh_meta["shadow_polygon_m"]


# --------------------------------------------------------------------------- #
# pytest fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def demo_utci_grid() -> dict:
    """The persisted primavera-demo UTCI grid (GROUNDED baseline_utci_c per cell)."""
    return load_demo("utci_grid")


@pytest.fixture
def demo_score_grid() -> dict:
    """The persisted primavera-demo score grid (score = density·max(utci-26, 0))."""
    return load_demo("score_grid")


@pytest.fixture
def demo_footprint() -> dict:
    """The persisted primavera-demo footprint (the funded/marked priority cells' polygons)."""
    return load_demo("footprint")


@pytest.fixture
def demo_material_selection() -> dict:
    """The persisted primavera-demo material selection (τ = 0.4, cost_total_eur = 0.0)."""
    return load_demo("material_selection")


@pytest.fixture
def frozen_thresholds() -> dict:
    """The frozen X=4 / Y=70 thresholds dict (with content_sha256)."""
    return load_thresholds()


@pytest.fixture
def synthetic_priority() -> dict:
    """The 3-of-4-shaded synthetic priority set (known 75 % coverage)."""
    return synthetic_priority_set()
