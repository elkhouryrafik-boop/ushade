"""Phase-5b Cooling-Acceptance-Gate package — the project's honesty keystone.

This is the ONLY place "it cools" becomes falsifiable: a deterministic, offline gate
that reads already-persisted Phase 2a/3/4/5 artifacts (utci_grid, score_grid, footprint,
gh_meta, material_selection), recomputes projected-shadow coverage over the funded
priority cells (GATE-01), applies the (1 - tau) UTCI delta over the byte-stable
baseline (GATE-02), and writes a both-required PASS/FAIL verdict (GATE-03).

BASE TIER — NON-NEGOTIABLE: nothing in this package may import rhino3dm, torch, or
infrared (the live SDK). The gate consumes PERSISTED/decoded geometry as plain
coordinates (the Q1 `gh_meta.shadow_polygon_m` sidecar field), never re-decodes the
mesh, and never re-runs the climate sim. Keeping it base-tier is what lets every gate
test run in the offline `pytest -m "not crowd and not geom"` suite.
"""
