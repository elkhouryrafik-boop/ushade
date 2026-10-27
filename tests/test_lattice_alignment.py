"""Master-lattice alignment contract (CONTRACT-03, T-00-03).

The highest-value contract test in the system: crowd/score grids must snap to
the utci_grid master lattice. Equality of the ``lattice`` object across spatial
artifacts IS the alignment contract. Asserted positively (matching grid) and
negatively (mismatched cell_size_m) so the equality check is proven to actually
discriminate drift (guards Pitfall C). Runs on the synthetic 3x3 fixtures from
Plan 01 — no real data needed.
"""

import pytest
from jsonschema.exceptions import ValidationError

from conftest import validator_for


def test_valid_utci_grid_validates(valid_utci_grid):
    """The master-lattice UTCI fixture validates against utci_grid.schema.json."""
    validator_for("utci_grid.schema.json").validate(valid_utci_grid)


def test_matching_crowd_grid_validates(matching_crowd_grid):
    """The aligned crowd fixture validates against crowd_grid.schema.json."""
    validator_for("crowd_grid.schema.json").validate(matching_crowd_grid)


def test_crowd_lattice_equals_utci_lattice(valid_utci_grid, matching_crowd_grid):
    """POSITIVE: crowd_grid.lattice deep-equals utci_grid.lattice (CONTRACT-03)."""
    assert matching_crowd_grid["lattice"] == valid_utci_grid["lattice"]


def test_mismatched_crowd_lattice_detected(valid_utci_grid, mismatched_crowd_grid):
    """NEGATIVE: a drifted lattice (cell_size_m=12.0) is NOT equal — drift caught."""
    assert mismatched_crowd_grid["lattice"] != valid_utci_grid["lattice"]
    assert mismatched_crowd_grid["lattice"]["cell_size_m"] == 12.0


def test_canonical_crs_is_32631(valid_utci_grid):
    """CRS is canonical UTM 31N / EPSG:32631 — never ETRS89/25831."""
    assert valid_utci_grid["crs"]["epsg"] == 32631
    assert valid_utci_grid["crs"]["epsg"] != 25831


def test_mismatched_crowd_grid_still_schema_valid(mismatched_crowd_grid):
    """Drift is a CONTRACT (equality) failure, not a SCHEMA failure: the drifted
    grid is still a structurally valid crowd_grid — proving the lattice-equality
    assertion (not the schema) is what catches drift."""
    # Schema validation passes (it is well-formed); only lattice equality fails.
    validator_for("crowd_grid.schema.json").validate(mismatched_crowd_grid)


def test_lattice_ref_is_load_bearing(valid_utci_grid):
    """Removing a required lattice key makes the artifact fail schema validation —
    confirms the shared lattice $ref is enforced, not cosmetic."""
    broken = {
        **valid_utci_grid,
        "lattice": {
            k: v
            for k, v in valid_utci_grid["lattice"].items()
            if k != "cell_size_m"
        },
    }
    with pytest.raises(ValidationError):
        validator_for("utci_grid.schema.json").validate(broken)
