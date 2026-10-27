"""Phase 2b Crowd Simulation (DRL) package.

Mirrors ``src/climate``: a pure ``gymnasium`` env (``env.py``), the single named-constants
module (``constants.py``), and — in later plans — a fixed-seed ``train.py`` (Wave-0
regeneration), a pure ``grid.py`` trajectory->lattice transform, and a ``run_crowd_stage``
orchestrator. The torch/SB3-requiring code is import-guarded so the base offline suite
stays torch-free (the ``crowd`` optional extra + ``crowd`` pytest marker — T-02b-02).

``constants.py`` imports nothing heavy (pure ints/floats) so it loads with NO crowd extra
installed — it is the single source of the PRD/ASSUMED acceptance numbers (T-02b-01).
"""
