"""The two highest-risk-seam smoke test (XFN-04).

Phase 0 has no pipeline code yet — but the two seams that make "optimized" and
"cooler" falsifiable must be loud test failures the moment they're violated:

  SEAM 1 — climate x crowd lattice (T-00-12, Pitfall 5, existential):
    the greedy core multiplies the UTCI grid by the crowd grid cell-for-cell. If
    the two lattices drift (different origin/cell_size/cols/rows), the product is
    meaningless but silent. This seam asserts lattice EQUALITY (positive) +
    MISMATCH discrimination (negative) + canonical CRS == 32631 + no lat/lon leak.

  SEAM 2 — material tau -> acceptance gate (T-00-13, Pitfall 3, load-bearing honesty):
    the Phase 5b cooling delta scales by (1 - solar_transmissivity). Invert that and
    a leakier membrane reports MORE cooling — the gate lies. This seam asserts the
    (1 - tau) direction is monotonic (higher tau => less cooling) with the `3.6`
    worked example, using the REAL tau values from data/materials.json, and that a
    structural material (tau == null) is never used as a membrane cooling input.

Fixtures (valid_utci_grid, matching_crowd_grid, mismatched_crowd_grid,
materials_tau_slice) come from tests/conftest.py (Plan 01).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# SEAM 1 — climate x crowd lattice alignment (the highest-value contract test)
# ---------------------------------------------------------------------------


def test_seam1_matching_lattices_are_equal(valid_utci_grid, matching_crowd_grid):
    """POSITIVE: a correctly-snapped crowd grid shares the utci master lattice.

    Deep-equality of the lattice object IS the alignment contract — the greedy
    core may only multiply grids whose lattices are identical.
    """
    assert matching_crowd_grid["lattice"] == valid_utci_grid["lattice"]


def test_seam1_mismatched_lattice_is_caught(valid_utci_grid, mismatched_crowd_grid):
    """NEGATIVE: a drifted lattice (cell_size_m=12.0) must FAIL the equality.

    Proves the smoke test genuinely discriminates — without this, the positive
    assertion could pass vacuously and lattice drift would slip through silently.
    """
    assert mismatched_crowd_grid["lattice"] != valid_utci_grid["lattice"]
    # Pin the exact source of the drift so a future refactor can't mask it.
    assert mismatched_crowd_grid["lattice"]["cell_size_m"] == 12.0
    assert valid_utci_grid["lattice"]["cell_size_m"] == 10.0


def test_seam1_canonical_crs_is_utm31n(valid_utci_grid):
    """The master grid is EPSG:32631 (UTM31N), never the ETRS89 25831 variant."""
    assert valid_utci_grid["crs"]["epsg"] == 32631
    assert valid_utci_grid["crs"]["epsg"] != 25831
    assert valid_utci_grid["crs"]["units"] == "metre"


def test_seam1_no_latlon_leak_in_cell_coords(valid_utci_grid):
    """No cell x_m/y_m falls in the lat/lon range — a coord in 41.x/2.x is a CRS
    leak (Pitfall 5): metres got swapped for degrees somewhere upstream.

    Parc del Forum is 41.41 N / 2.22 E; in UTM31N metres those become ~6-digit
    eastings/northings, so any cell coordinate sitting in [1.5, 3.5] (lon) or
    [40.5, 42.5] (lat) is the smoking gun of a degree leak.
    """
    lon_band = (1.5, 3.5)
    lat_band = (40.5, 42.5)
    for cell in valid_utci_grid["cells"]:
        x_m, y_m = cell["x_m"], cell["y_m"]
        for coord in (x_m, y_m):
            assert not (lon_band[0] <= coord <= lon_band[1]), (
                f"coord {coord} sits in the lon band — CRS leak"
            )
            assert not (lat_band[0] <= coord <= lat_band[1]), (
                f"coord {coord} sits in the lat band — CRS leak"
            )


# ---------------------------------------------------------------------------
# SEAM 2 — material tau -> acceptance gate (the (1 - tau) direction)
# ---------------------------------------------------------------------------


def _cooling(ideal_delta_c: float, tau: float) -> float:
    """The Golden-Rule (amended 2026-06-09) cooling correction: a membrane that
    transmits a fraction tau of solar delivers ideal*(1 - tau) of the ideal
    (opaque-shade) cooling. Higher tau (leakier) => less cooling."""
    return ideal_delta_c * (1.0 - tau)


def test_seam2_higher_tau_yields_less_cooling(materials_tau_slice):
    """DIRECTION: with the REAL tau (PVC 0.01 < HDPE 0.40), the lower-tau membrane
    must cool MORE. If someone inverts (1 - tau) the gate would report the leakier
    HDPE as the better cooler — this assertion makes that a loud failure."""
    ideal = 6.0
    pvc = _cooling(ideal, materials_tau_slice["pvc"])  # tau 0.01
    hdpe = _cooling(ideal, materials_tau_slice["hdpe"])  # tau 0.40
    assert pvc > hdpe  # higher tau (HDPE) => less cooling


def test_seam2_worked_example_3_6(materials_tau_slice):
    """The 00-RESEARCH worked example: 6.0 C ideal through HDPE (tau 0.40) yields
    exactly 3.6 C of corrected cooling."""
    assert materials_tau_slice["hdpe"] == 0.40
    assert round(_cooling(6.0, 0.40), 6) == 3.6


def test_seam2_recycled_pe_is_the_best_cooler(materials_tau_slice):
    """Recycled PE (tau 0.00, opaque) is the least transmissive of the three => the most
    cooling — a second point on the monotonic (1 - tau) curve."""
    ideal = 6.0
    recycled = _cooling(ideal, materials_tau_slice["recycled_pe"])  # tau 0.00
    pvc = _cooling(ideal, materials_tau_slice["pvc"])  # tau 0.01
    hdpe = _cooling(ideal, materials_tau_slice["hdpe"])  # tau 0.40
    assert recycled > pvc > hdpe


def test_seam2_structural_null_tau_is_never_a_membrane_input():
    """A structural material carries solar_transmissivity == null. Feeding null
    into (1 - tau) is a category error — structural items are not overhead shade,
    so they must be EXCLUDED from the membrane-cooling input, not coerced to 0."""
    import json
    from pathlib import Path

    materials_path = Path(__file__).resolve().parent.parent / "data" / "materials.json"
    materials = json.loads(materials_path.read_text(encoding="utf-8"))["materials"]

    structural = [m for m in materials if m["type"] == "STRUCT"]
    assert structural, "expected structural materials in the frozen DB"
    # Every structural material has null tau (cannot be a membrane cooling input).
    for m in structural:
        assert m["solar_transmissivity"] is None

    # The membrane-cooling input is exactly the materials with a non-null tau.
    cooling_inputs = [m for m in materials if m["solar_transmissivity"] is not None]
    assert all(m["type"] == "MEMBR" for m in cooling_inputs)
    # None of the structural (null-tau) materials leak into the cooling input set.
    structural_ids = {m["id"] for m in structural}
    assert not (structural_ids & {m["id"] for m in cooling_inputs})
