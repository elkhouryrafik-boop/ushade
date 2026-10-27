"""Wave 0 harness sentinel.

Proves the pytest runner + shared conftest fixtures are wired and importable
before any contract tests exist. Downstream plans (02-05) add the real contract
tests; this keeps the greenfield suite green (pytest exit 0, not 5/no-tests).
"""


def test_harness_runs():
    assert True


def test_fixtures_importable(
    master_lattice,
    valid_utci_grid,
    matching_crowd_grid,
    mismatched_crowd_grid,
    materials_tau_slice,
):
    """Smoke-prove the shared conftest fixtures load and carry the contract shape
    downstream plans (02-05) depend on. Not the real contract tests — just wiring."""
    assert master_lattice["cols"] == 3 and master_lattice["rows"] == 3
    assert len(valid_utci_grid["cells"]) == 9
    assert valid_utci_grid["crs"]["epsg"] == 32631
    # positive alignment case: same lattice object
    assert matching_crowd_grid["lattice"] == valid_utci_grid["lattice"]
    # negative drift case: cell_size_m diverges
    assert mismatched_crowd_grid["lattice"]["cell_size_m"] == 12.0
    assert mismatched_crowd_grid["lattice"] != valid_utci_grid["lattice"]
    # tau slice verbatim from materials.json (datasheet-sourced 2026-06-22)
    assert materials_tau_slice == {"pvc": 0.01, "hdpe": 0.40, "recycled_pe": 0.0}
