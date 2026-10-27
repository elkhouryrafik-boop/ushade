"""The JuPedSim crowd engine (Phase 15, D-06) — lazy-imported by ``crowd.crowd``.

This package is the live crowd microsimulation: ``simulation.py`` drives JuPedSim's Collision-Free
Speed Model behind the UNCHANGED ``run_crowd_stage`` shell, ``mapping.py`` maps the FROZEN festival
layer (gates/stages/popularity) onto JuPedSim primitives, and ``adapter.py`` finite-differences the
per-step positions into the FROZEN ``(steps × agents × 4)`` trajectory array ``build_crowd_grid``
consumes. The heavy ``jupedsim``/``shapely`` backends are imported INSIDE function bodies only
(``simulation.py``'s factory) so ``import crowdsim.*`` stays light and the base-tier purity guard
holds (T-15-05) — mirror of the ``crowd``/``geom`` lazy-import quarantine.
"""
