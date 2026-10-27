"""crowd_density provenance on the JuPedSim path (CROWD-09 + 2026-06-22 Lyon density gate).

Two honest branches, both deterministic (the gate is monkeypatched, so the test never depends on
the committed benchmark artifact or on jupedsim being installed):

  - NOT green  → crowd_density is ASSUMED, Fruin/Still-anchored; source must NOT reference the dead
                 PPO concepts (Weidmann / policy.zip / MODEL_CARD — Pitfall 5.6).
  - green      → the density MAGNITUDE promotes to DERIVED (validated against the REAL measured Lyon
                 MADRAS festival density), while the SPATIAL ALLOCATION stays ASSUMED (real timetable
                 + organiser capacity drive it, but popularity ordinal + spawn split are assumed and
                 no open data validates the Parc-del-Fòrum allocation).

BASE tier (NO ``crowdsim`` marker): driven via an injected torch/jupedsim-free ``sim_factory``.
"""

from __future__ import annotations

import json

from conftest_crowdsim import crowdsim_real_site_project, fake_sim_factory
import crowd.crowd as crowd_mod
from crowd.crowd import run_crowd_stage

_FORBIDDEN_SOURCE_TOKENS = ("Weidmann", "policy.zip", "MODEL_CARD")


def test_crowd_density_assumed_floor_when_benchmark_not_green(tmp_path, monkeypatch):
    """The non-negotiable floor: with the Lyon gate NOT green, crowd_density is ASSUMED with a
    Fruin/Still source (no dead-PPO tokens), and spatial allocation is ASSUMED."""
    monkeypatch.setattr(crowd_mod, "_crowdsim_benchmark_is_green", lambda: False)
    pdir = crowdsim_real_site_project(tmp_path, "prov-assumed", capacity=800)
    run_crowd_stage("prov-assumed", projects_root=tmp_path, sim_factory=fake_sim_factory())

    prov = json.loads((pdir / "provenance.json").read_text(encoding="utf-8"))
    entries = {e["key"]: e for e in prov["entries"]}
    crowd_entries = [e for e in prov["entries"] if e["key"] == "crowd_density"]
    assert crowd_entries and all(e["tier"] == "ASSUMED" for e in crowd_entries)
    for e in crowd_entries:
        for tok in _FORBIDDEN_SOURCE_TOKENS:
            assert tok not in e["source"], f"JuPedSim crowd_density source must not cite {tok!r}"
    assert "crowd_density_magnitude" not in entries, "no DERIVED magnitude when the gate is red"
    assert entries["crowd_spatial_allocation"]["tier"] == "ASSUMED"
    assert entries["sim_seed"]["tier"] == "ASSUMED"


def test_crowd_density_magnitude_derived_when_benchmark_green(tmp_path, monkeypatch):
    """With the Lyon gate green, the density MAGNITUDE is DERIVED (validated vs real measured
    festival data) while the SPATIAL ALLOCATION stays ASSUMED — the honest split."""
    monkeypatch.setattr(crowd_mod, "_crowdsim_benchmark_is_green", lambda: True)
    pdir = crowdsim_real_site_project(tmp_path, "prov-derived", capacity=800)
    run_crowd_stage("prov-derived", projects_root=tmp_path, sim_factory=fake_sim_factory())

    prov = json.loads((pdir / "provenance.json").read_text(encoding="utf-8"))
    entries = {e["key"]: e for e in prov["entries"]}
    assert entries["crowd_density_magnitude"]["tier"] == "DERIVED", (
        "magnitude must promote DERIVED on a green Lyon benchmark"
    )
    assert "Lyon" in entries["crowd_density_magnitude"]["source"]
    # FIELD tier + allocation stay ASSUMED even when green (weakest-input-wins; placement contract).
    assert entries["crowd_density"]["tier"] == "ASSUMED", (
        "the FIELD crowd_density stays ASSUMED (allocation is assumed) — only the MAGNITUDE sub-claim "
        "promotes; this keeps downstream placement honestly ASSUMED"
    )
    assert entries["crowd_spatial_allocation"]["tier"] == "ASSUMED"
