"""Base-tier purity guard for the JuPedSim crowd swap (CROWD-06).

``import crowd.crowd`` must stay free of BOTH the legacy torch backend AND the new ``jupedsim``
wheel: the heavy engine is LAZY-imported inside ``src/crowdsim/`` (loaded only on the cache-MISS
path), so the DEFAULT offline suite runs green WITHOUT jupedsim installed (the established
``crowd``/``geom`` quarantine, T-15-01). This is the exact static-grep + dynamic-sys.modules
two-guard pattern from ``test_crowd_grid.py::test_grid_module_is_torch_free`` (lines 124-142),
re-targeted at the orchestrator shell with ``jupedsim`` added to the forbidden-token list.

This test is NOT ``crowdsim``-marked: it MUST run in the base tier (proving the base tier never
pulls jupedsim) even though jupedsim is not installed. It is GREEN by design — the shell is
already lazy; it fails only if a future edit leaks ``import jupedsim`` (or torch) to module top.
"""

from __future__ import annotations

import ast
import importlib
import pathlib
import sys

# The heavy backends that must NEVER be at the top level of the crowd orchestrator shell.
_FORBIDDEN = ("torch", "stable_baselines3", "gymnasium", "jupedsim")


def test_crowd_shell_is_jupedsim_and_torch_free():
    """``import crowd.crowd`` pulls neither torch NOR jupedsim — statically AND dynamically.

    (1) STATIC: the source of ``src/crowd/crowd.py`` contains no top-level ``import jupedsim``
        (nor a bare torch/SB3/gymnasium import token). (2) DYNAMIC: importing ``crowd.crowd``
        adds none of the forbidden backends to ``sys.modules``.
    """
    src = pathlib.Path(__file__).resolve().parents[1] / "src" / "crowd" / "crowd.py"
    text = src.read_text(encoding="utf-8")
    # TOP-LEVEL imports only. The approved pattern is a LAZY `import jupedsim` inside the
    # cache-miss function body (the line carries a noqa PLC0415 saying so), so a bare
    # substring test failed the exact code CROWD-06 asks for. Walk the module AST instead.
    tree = ast.parse(text)
    top_level: set[str] = set()
    for node in tree.body:  # module body only; nested lazy imports are the point
        if isinstance(node, ast.Import):
            top_level.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module.split(".")[0])
    eager = top_level.intersection(_FORBIDDEN)
    assert not eager, (
        f"crowd/crowd.py must not import {sorted(eager)} at module top level — those are "
        "lazy-imported inside the cache-miss path so the base suite stays backend-free (CROWD-06)."
    )

    # Drop any pre-imported heavy modules, then import the shell and assert it added none.
    for mod in _FORBIDDEN:
        sys.modules.pop(mod, None)
    importlib.import_module("crowd.crowd")
    for mod in _FORBIDDEN:
        assert mod not in sys.modules, (
            f"importing crowd.crowd must not import {mod!r} (base-suite purity, CROWD-06)"
        )
