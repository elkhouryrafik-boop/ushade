"""Wave-0 designed-RED scaffold — GEOM-06 Bill of Materials + mass-balance sidecar.

Behaviour map (CONTEXT.md + RESEARCH §Phase Requirements -> Test Map):

  * GEOM-06  test_bom_is_contract_valid          OUT_BOM {pillars>=0, membrane_m2>=0} satisfies
  *                                              the frozen gh_response contract
  * GEOM-06  test_gh_meta_carries_mass_balance    the gh_meta sidecar carries rented/recovered/new
  *                                              mass-balance fields (Material Recovery Inventory)

RED mechanism (clone tests/test_crowd_grid.py lines 9-16): ``geom.reference_generator`` lands in
Wave 2, so each test ``skipif``-guards on its absence + imports lazily; the skips lift when the
generator ships, becoming the GREEN gate. Needs the geom extra (rhino3dm mesh) so
``@pytest.mark.geom`` + importorskip.
"""

from __future__ import annotations

import importlib.util

import pytest

pytest.importorskip("rhino3dm")

from conftest_geom import load_footprint, load_flow_vectors  # noqa: E402  (explicit import)

pytestmark = pytest.mark.geom

_REF_AVAILABLE = importlib.util.find_spec("geom.reference_generator") is not None
_needs_ref = pytest.mark.skipif(
    not _REF_AVAILABLE, reason="src/geom/reference_generator.py lands in Wave 2 (RED scaffold)"
)


@_needs_ref
def test_bom_is_contract_valid():
    """GEOM-06: the generated gh_response's OUT_BOM is contract-valid (pillars>=0, membrane_m2>=0)."""
    from geom.reference_generator import build_reference
    from src.validate.validate import validate

    ref = build_reference(load_footprint(), load_flow_vectors())
    validate(ref["gh_response"], "gh_response")
    bom = ref["gh_response"]["OUT_BOM"]
    assert bom["pillars"] >= 0
    assert bom["membrane_m2"] >= 0


@_needs_ref
def test_gh_meta_carries_mass_balance():
    """GEOM-06: the gh_meta sidecar carries the rented/recovered/new mass-balance fields."""
    from geom.reference_generator import build_reference

    ref = build_reference(load_footprint(), load_flow_vectors())
    meta = ref["gh_meta"]
    for field in ("rented", "recovered", "new"):
        assert field in meta["mass_balance"], f"gh_meta.mass_balance must carry '{field}'"
