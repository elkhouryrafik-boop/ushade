"""Contract conformance for the PURE crowd_grid transform (CROWD-02/03/04).

The artifact ``build_crowd_grid`` emits must validate against the FROZEN
``contracts/crowd_grid.schema.json`` — we reuse the single-source ``validate(artifact,
"crowd_grid")`` from ``src/validate`` (the SAME validator the runtime + Node use), never
a hand-rolled shape check (RESEARCH §Don't Hand-Roll). These tests are torch-free (no
``crowd`` marker): grid.py is pure, so they belong to the base suite and lock the contract
every later plan is verified against.
"""

from __future__ import annotations

import pytest

from conftest_crowd import synthetic_trajectory, tiny_lattice
from crowd.grid import build_crowd_grid
from validate.validate import validate


def test_artifact_valid():
    """The built crowd_grid validates against the frozen contract (no raise)."""
    artifact = build_crowd_grid(synthetic_trajectory(), tiny_lattice())
    validate(artifact, "crowd_grid")  # raises ValidationError on any violation


def test_dwell_polygon_min_three_points():
    """Every emitted dwell_zone.polygon has >=3 point_m (contract minItems: 3)."""
    artifact = build_crowd_grid(synthetic_trajectory(), tiny_lattice())
    zones = artifact["dwell_zones"]
    assert zones, "the known still-agent cluster must produce >=1 dwell zone"
    for zone in zones:
        assert len(zone["polygon"]) >= 3
        for point in zone["polygon"]:
            assert set(point) == {"x_m", "y_m"}, "polygon vertex must be a point_m"


def test_flow_vector_shape():
    """Every flow_vector has exactly origin + destination, each a point_m (contract)."""
    artifact = build_crowd_grid(synthetic_trajectory(), tiny_lattice())
    flows = artifact["flow_vectors"]
    assert flows, "the known major groups must produce >=1 flow vector"
    for flow in flows:
        assert set(flow) == {"origin", "destination"}
        assert set(flow["origin"]) == {"x_m", "y_m"}
        assert set(flow["destination"]) == {"x_m", "y_m"}


def test_cells_density_non_negative():
    """crowd_density_agents_per_cell >= 0 on every cell (contract minimum: 0)."""
    artifact = build_crowd_grid(synthetic_trajectory(), tiny_lattice())
    assert artifact["cells"], "a populated trajectory must snap to >=1 cell"
    for cell in artifact["cells"]:
        assert cell["crowd_density_agents_per_cell"] >= 0
        assert set(cell) == {"x_m", "y_m", "crowd_density_agents_per_cell"}


def test_off_contract_artifact_rejected():
    """T-02b-09: a tampered artifact (extra key) is REJECTED — the validator discriminates."""
    artifact = build_crowd_grid(synthetic_trajectory(), tiny_lattice())
    artifact["cells"][0]["bogus_field"] = 1  # additionalProperties: false
    with pytest.raises(Exception):
        validate(artifact, "crowd_grid")
