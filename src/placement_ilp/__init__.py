"""Phase 13 Exact ILP-MCLP placer package — the EARNED-optimal engine.

This package is deliberately placed OUTSIDE ``src/core/``. The honesty firewall
(``tests/test_core.py::test_no_optimal_vocab``) globs ``src/core/*.py`` and forbids the
word "optimal" there — the greedy core makes NO best-coverage claim (CORE-05). This package
is the SOLE source tree in the repo legitimately allowed the word "optimal": it solves the
Maximal-Covering-Location MCLP to PROVEN optimality via ``scipy.optimize.milp`` (HiGHS) and
emits a falsifiable optimality certificate (``mip_gap == 0 => proven_optimal``), per the
2026-06-20 AMEND-01 amendment that scoped the lock to ``src/core/`` only.

Import discipline (D-02 — mirror ``crowd.crowd``'s SB3/torch quarantine): this ``__init__``
is intentionally IMPORT-LIGHT. It re-exports NOTHING from the (Plan-03) solver submodule at
module load, because that submodule pulls scipy and that would make ``import placement_ilp``
(or, worse, the greedy default path through ``core.placement_stage``) drag scipy in eagerly.
scipy is a base dependency (always installed) but the scipy.optimize.milp import lives INSIDE
``solve_mclp_exact``, deferred to the ``engine="ilp"`` cache-miss / solve path. So:

    import placement_ilp                       # cheap; pulls NO scipy
    from placement_ilp.mclp import solve_...   # Plan 03; lazy-imports scipy inside the solver

``pyproject.toml``'s ``pythonpath = ["src", "."]`` makes ``placement_ilp`` importable as a
sibling top-level package alongside ``core`` / ``crowd`` / ``climate``.
"""
