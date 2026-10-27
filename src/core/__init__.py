"""Deterministic placement core package (v2.0 regenerative pivot).

A pure, offline, deterministic compute layer (NO AI, NO network, NO randomness of its
own): it crosses the climate UTCI grid with the crowd-density field and selects a RANKED
set of shade structures via a Maximal-Covering Location formulation — the bounded
submodular greedy (``placement.py``) or the exact HiGHS ILP / multi-snapshot robust
engine (``placement_ilp/``), persisted through ``placement_stage.run_placement_stage``.
The output is the contract-valid ``structure_zones.json`` (ranked ZONES, never footprint
polygons — drawing the footprint is a design act the human architect owns, PLACE-09).

Phase 14 (Plan 04, D-05/D-06): the original Phase-3 greedy coupling — ``score.py``
(per-cell ``score = crowd_density * max(utci_c - 26, 0)`` funding), ``footprint.py``
(shade polygons), and the ``core.py`` orchestrator (``run_core_stage`` → ``score_grid``
+ ``footprint``) — has been RETIRED. It was SUPERSEDED by the ranked-zone placer at the
v2.0 "AI proposes, human commits" pivot and removed once the canonical pipeline migrated
off it (the API full-run now runs ``run_placement_stage``; the geometry stage that
consumed ``footprint.json`` retired with it).

The LLM designs nothing here (CLAUDE.md non-negotiable) — this is the deterministic moat:
crowd × heat coupling resolved by a bounded MCLP heuristic / exact solve, NEVER claimed
to be a best-coverage solution (CORE-05, Pitfall 10 — the honesty-vocab guard, re-anchored
in ``tests/test_placement_stage.py``, holds over this package).

``constants.py`` imports nothing heavy (pure floats) so it loads with NO crowd extra.
"""
