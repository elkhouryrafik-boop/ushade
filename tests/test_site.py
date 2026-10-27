"""Site-geometry loader tests — pure (numpy + shapely + crs), BASE suite (Plan 02.1-02).

``src/crowd/site.py`` promotes the DemoEnv prototype's site loading + walkability
rasterisation (``viz/run_demo_sim.py``) INTO src as pipeline code (RESEARCH §Architectural
Responsibility Map row 3). It turns the committed geojson into env geometry:

* 19 real stage goals (UTM31N) + their capacity-class goal weights;
* exactly two entrances, ordered ``[A general, B VIP]``;
* the impassable blocked-cell set (outside boundary ∪ inside any of the 13 blockers) on the
  READ utci lattice — the PRD "Obstacles flagged as impassable" honoured literally.

These tests assert the plan's behaviour list. The full-geojson load lives in ONE test
(``test_loads_19_stages_two_entrances``); the blocked/clear-cell ground truth uses the tiny
hand-built ``mini_site`` fixture (no full-geojson dependency). A STATIC purity guard greps the
module text for torch/SB3/gymnasium (the module is pure pipeline — no ML backend).

All tests run under ``pytest -q -m "not crowd"`` — numpy + shapely + crs, no crowd extra.
"""

from __future__ import annotations

from pathlib import Path

# conftest_crowd is imported EXPLICITLY (it is not auto-loaded — see its docstring).
from conftest_crowd import mini_site

from crowd.constants import GOAL_WEIGHT_BY_CLASS, GOAL_WEIGHT_DEFAULT
from crowd.site import build_blocked_cells, load_site_geometry

_REPO_ROOT = Path(__file__).resolve().parent.parent
_VIZ_DATA = _REPO_ROOT / "viz" / "data"


def _ll_to_cell(lon, lat, lattice):
    """Project a (lon, lat) to its (col, row) cell on a lattice (test helper)."""
    from crs.crs import to_utm31n

    x, y = to_utm31n(lon, lat)
    col = int((x - lattice["origin_x_m"]) // lattice["cell_size_m"])
    row = int((y - lattice["origin_y_m"]) // lattice["cell_size_m"])
    return col, row


# --------------------------------------------------------------------------- #
# Full-geojson load (the ONE real-file test)
# --------------------------------------------------------------------------- #
def test_loads_19_stages_two_entrances():
    """The committed geojson loads to 19 UTM31N stage goals + exactly two ordered entrances."""
    import json

    festival = json.loads((_VIZ_DATA / "festival_map_2026.geojson").read_text(encoding="utf-8"))
    boundary = json.loads((_VIZ_DATA / "boundary_2026.geojson").read_text(encoding="utf-8"))
    nogo = json.loads((_VIZ_DATA / "walkable_nogo_2026.geojson").read_text(encoding="utf-8"))
    # Read lattice (the master utci lattice, 139×153 @ 6 m).
    grid = json.loads(
        (_REPO_ROOT / "projects" / "primavera-demo" / "utci_grid.json").read_text(encoding="utf-8")
    )
    lattice = grid["lattice"]

    site = load_site_geometry(festival, boundary, nogo, lattice)

    # 19 real stages (layer == "stage"), UTM31N tuples.
    assert len(site["stages_utm"]) == 19
    assert len(site["stage_meta"]) == 19
    assert len(site["goal_weights"]) == 19
    for x, y in site["stages_utm"]:
        # UTM31N near Parc del Fòrum: easting ~434–436k, northing ~4584k.
        assert 430_000 < x < 440_000
        assert 4_580_000 < y < 4_590_000

    # Exactly two entrances, ordered [A general, B VIP].
    assert len(site["entrances_utm"]) == 2
    assert list(site["entrances_ll"].keys()) == ["A", "B"]

    # Goal weights come from the capacity-class table.
    classes = [m["class"] for m in site["stage_meta"]]
    for w, cls in zip(site["goal_weights"], classes):
        assert w == GOAL_WEIGHT_BY_CLASS.get(cls, GOAL_WEIGHT_DEFAULT)

    # Blocked-cell set is present and non-trivial.
    assert isinstance(site["blocked_cells"], set)
    assert len(site["blocked_cells"]) > 0


def test_entrances_ordered_a_general_b_vip():
    """Entrances are ordered [A general, B VIP] regardless of geojson feature order."""
    ms = mini_site()
    site = load_site_geometry(ms["festival"], ms["boundary"], ms["nogo"], ms["lattice"])
    # A is the general gate, B the VIP gate — both present, A first.
    assert list(site["entrances_ll"].keys()) == ["A", "B"]
    assert len(site["entrances_utm"]) == 2


# --------------------------------------------------------------------------- #
# Blocked-cell rasterisation (tiny hand-built ground truth)
# --------------------------------------------------------------------------- #
def test_blocked_cells_cover_blockers():
    """A cell-centre inside the blocker building AND a cell outside the boundary are blocked."""
    ms = mini_site()
    blocked = build_blocked_cells(ms["lattice"], ms["boundary"], ms["nogo"])

    # The known inside-blocker point's cell must be blocked.
    bc = _ll_to_cell(*ms["inside_blocker_ll"], ms["lattice"])
    assert bc in blocked, f"inside-blocker cell {bc} not flagged blocked"

    # A corner cell (origin (0,0)) is outside the boundary (one-cell margin) → blocked.
    assert (0, 0) in blocked, "outside-boundary corner cell not flagged blocked"


def test_blocked_excludes_clear_interior():
    """A cell-centre in open festival ground (inside boundary, off blockers) is NOT blocked."""
    ms = mini_site()
    blocked = build_blocked_cells(ms["lattice"], ms["boundary"], ms["nogo"])
    cc = _ll_to_cell(*ms["inside_clear_ll"], ms["lattice"])
    assert cc not in blocked, f"clear-interior cell {cc} was wrongly flagged blocked"


def test_blocked_count_sane_on_mini_site():
    """Blocked-cell count is a sane fraction of the mini lattice (>0, <100%)."""
    ms = mini_site()
    lattice = ms["lattice"]
    blocked = build_blocked_cells(lattice, ms["boundary"], ms["nogo"])
    total = lattice["cols"] * lattice["rows"]
    assert 0 < len(blocked) < total


def test_blocked_count_sane_full_lattice():
    """On the real 139×153 lattice the blocked-cell count is >0 and <100% of cells."""
    import json

    boundary = json.loads((_VIZ_DATA / "boundary_2026.geojson").read_text(encoding="utf-8"))
    nogo = json.loads((_VIZ_DATA / "walkable_nogo_2026.geojson").read_text(encoding="utf-8"))
    grid = json.loads(
        (_REPO_ROOT / "projects" / "primavera-demo" / "utci_grid.json").read_text(encoding="utf-8")
    )
    lattice = grid["lattice"]
    blocked = build_blocked_cells(lattice, boundary, nogo)
    total = lattice["cols"] * lattice["rows"]  # 139 × 153 = 21,267
    assert 0 < len(blocked) < total


# --------------------------------------------------------------------------- #
# Purity guard (static — site.py is pure pipeline, no ML backend)
# --------------------------------------------------------------------------- #
def test_site_is_pure():
    """site.py imports numpy + shapely + crs only — NO torch/SB3/gymnasium anywhere in the text."""
    text = (_REPO_ROOT / "src" / "crowd" / "site.py").read_text(encoding="utf-8")
    for forbidden in ("torch", "stable_baselines3", "gymnasium"):
        assert forbidden not in text, f"site.py must be pure — found {forbidden!r}"
