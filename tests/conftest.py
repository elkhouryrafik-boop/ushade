"""Shared synthetic fixtures for all Phase 0 contract tests.

Real pipeline artifacts do not exist until Phases 1-5. These pure-Python
fixtures model a tiny 3x3 master lattice so downstream plans (02-05) can assert
the *math and alignment* contracts (lattice equality, the (1 - tau) cooling
direction, no hardcoded secrets) before any real data is produced.

Conventions enforced here mirror the contracts (see 00-RESEARCH.md):
  - canonical CRS is UTM 31N / EPSG:32631, units metre (never 25831)
  - the infrared UTCI grid is the master lattice; crowd/score grids snap to it
  - every numeric field is unit-suffixed (x_m, utci_c, cell_size_m, ...)
  - utci_c values span 24-34 so some cells are < 26 (the "drop < 26 C" cells)

karpathy: minimal, no fixture-factory framework, no file I/O beyond reading the
frozen materials.json once for the tau slice.
"""

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

# Repo root = parent of tests/. materials.json is frozen (10 entries).
_REPO_ROOT = Path(__file__).resolve().parent.parent
_MATERIALS_PATH = _REPO_ROOT / "data" / "materials.json"
_CONTRACTS_DIR = _REPO_ROOT / "contracts"
_DEFS_DIR = _CONTRACTS_DIR / "_defs"


def load_schema(name: str) -> dict:
    """Load a contract schema by file name (e.g. 'utci_grid.schema.json')."""
    return json.loads((_CONTRACTS_DIR / name).read_text(encoding="utf-8"))


def build_defs_registry() -> Registry:
    """Build a referencing.Registry from contracts/_defs/*.json.

    The shared crs/lattice defs self-key by their embedded ``$id`` (the absolute
    ``https://heatguard/contracts/_defs/<name>.schema.json`` URIs the spatial
    schemas ``$ref``). This is the supported jsonschema >=4.18 mechanism — never
    the deprecated RefResolver (see 00-RESEARCH.md Code Examples).
    """
    registry = Registry()
    for path in sorted(_DEFS_DIR.glob("*.json")):
        resource = Resource.from_contents(
            json.loads(path.read_text(encoding="utf-8"))
        )
        registry = resource @ registry
    return registry


def validator_for(name: str) -> Draft202012Validator:
    """Draft202012Validator for a contract schema, _defs-registry-backed."""
    return Draft202012Validator(load_schema(name), registry=build_defs_registry())


@pytest.fixture
def defs_registry() -> Registry:
    """Registry resolving the shared _defs/crs + _defs/lattice $refs."""
    return build_defs_registry()

# 3x3 lattice, row-major. utci_c spans 24.0 .. 34.0 so cells 0,1 are < 26 C.
_UTCI_C_GRID = [
    [24.0, 25.5, 27.0],
    [28.5, 30.0, 31.0],
    [32.0, 33.0, 34.0],
]
# A small uniform offset gives a plausible no-shade baseline per cell.
_BASELINE_OFFSET_C = 0.5
# Crowd density (agents per cell) — denser toward the hot corner.
_CROWD_AGENTS_GRID = [
    [0.0, 2.0, 5.0],
    [3.0, 8.0, 12.0],
    [6.0, 14.0, 20.0],
]


@pytest.fixture
def master_lattice():
    """The authoritative 3x3 lattice the UTCI grid sets and others snap to."""
    return {
        "origin_x_m": 0.0,
        "origin_y_m": 0.0,
        "cell_size_m": 10.0,
        "cols": 3,
        "rows": 3,
    }


@pytest.fixture
def crs_utm31n():
    """Canonical CRS: UTM 31N / EPSG:32631, metres. Never ETRS89/25831."""
    return {"epsg": 32631, "units": "metre"}


def _cell_coords(lattice, col, row):
    x_m = lattice["origin_x_m"] + (col + 0.5) * lattice["cell_size_m"]
    y_m = lattice["origin_y_m"] + (row + 0.5) * lattice["cell_size_m"]
    return x_m, y_m


@pytest.fixture
def valid_utci_grid(master_lattice, crs_utm31n):
    """Master-lattice UTCI grid with per-cell utci_c + baseline_utci_c."""
    cells = []
    for row in range(master_lattice["rows"]):
        for col in range(master_lattice["cols"]):
            x_m, y_m = _cell_coords(master_lattice, col, row)
            utci_c = _UTCI_C_GRID[row][col]
            cells.append(
                {
                    "x_m": x_m,
                    "y_m": y_m,
                    "utci_c": utci_c,
                    "baseline_utci_c": utci_c + _BASELINE_OFFSET_C,
                }
            )
    return {
        "schema_version": "1.0.0",
        "crs": crs_utm31n,
        "lattice": master_lattice,
        "cells": cells,
    }


@pytest.fixture
def matching_crowd_grid(master_lattice, crs_utm31n):
    """Crowd grid on the SAME lattice (deep-equal) — the alignment POSITIVE case."""
    cells = []
    for row in range(master_lattice["rows"]):
        for col in range(master_lattice["cols"]):
            x_m, y_m = _cell_coords(master_lattice, col, row)
            cells.append(
                {
                    "x_m": x_m,
                    "y_m": y_m,
                    "crowd_density_agents_per_cell": _CROWD_AGENTS_GRID[row][col],
                }
            )
    return {
        "schema_version": "1.0.0",
        "crs": crs_utm31n,
        "lattice": copy.deepcopy(master_lattice),
        "cells": cells,
    }


@pytest.fixture
def mismatched_crowd_grid(matching_crowd_grid):
    """Identical to matching_crowd_grid except cell_size_m=12.0 — the lattice-drift
    NEGATIVE case. Proves the alignment smoke test catches drift."""
    drifted = copy.deepcopy(matching_crowd_grid)
    drifted["lattice"]["cell_size_m"] = 12.0
    return drifted


@pytest.fixture
def materials_tau_slice():
    """solar_transmissivity values read verbatim from data/materials.json.

    Datasheet-sourced values (2026-06-22, CRISP-DM Phase 2): pvc 0.01 (billboard vinyl
    is near-blockout, Innotech SC450 opacity 99%), hdpe 0.40 (mid-grade agri shade net),
    recycled_pe 0.00 (opaque laminated woven PE tarp). Used by the (1 - tau) cooling-
    direction gate test (higher tau => less cooling). The ordering recycled_pe < pvc <
    hdpe is preserved, so the direction assertions below still hold."""
    materials = json.loads(_MATERIALS_PATH.read_text(encoding="utf-8"))["materials"]
    by_id = {m["id"]: m["solar_transmissivity"] for m in materials}
    tau = {
        "pvc": by_id["membr-pvc-billboard-vinyl"],
        "hdpe": by_id["membr-hdpe-shade-net"],
        "recycled_pe": by_id["membr-recycled-pe-tarp"],
    }
    # Guard against silent materials.json drift — datasheet-sourced contract values.
    assert tau == {"pvc": 0.01, "hdpe": 0.40, "recycled_pe": 0.0}
    return tau


# Phase 2.2: FastAPI endpoint test fixtures (mock_climate, mock_crowd) — torch-free
from conftest_api import mock_climate, mock_crowd  # noqa: F401


# ─────────────────────────────────────────────────────────────────────────────
# Phase 13 — synthetic tied-optima lattice for the exact ILP-MCLP scaffold
# ─────────────────────────────────────────────────────────────────────────────
#
# Site-generality (D-15): Parc del Forum is the test FIXTURE, not the target. These
# synthetic lattices are deliberately SMALL and NON-Forum (6x6 cells, 0-origin, 10 m
# cells — Forum is 153x139 @ 6 m). Determinism (D-12), the greedy cross-check (D-10),
# and the ceiling guard (D-13) are proven HERE on a tiny hand-computable instance and
# are valid for ANY lattice size — nothing below is keyed to a Forum dimension.

_ILP_LATTICE_6x6 = {
    "origin_x_m": 0.0,
    "origin_y_m": 0.0,
    "cell_size_m": 10.0,
    "cols": 6,
    "rows": 6,
}


def _ilp_cell_center(lattice, col, row):
    x_m = lattice["origin_x_m"] + (col + 0.5) * lattice["cell_size_m"]
    y_m = lattice["origin_y_m"] + (row + 0.5) * lattice["cell_size_m"]
    return x_m, y_m


def _build_ilp_inputs(lattice, utci_by_rc, crowd_by_rc):
    """Assemble {utci, crowd} grid dicts (build_demand's input shape) from per-(row,col)
    dict overrides. Cells absent from a dict default to utci_c=24.0 (sub-26 => dropped) and
    crowd_density=0.0, so only the engineered hot+busy cells carry positive demand."""
    utci_cells, crowd_cells = [], []
    for row in range(lattice["rows"]):
        for col in range(lattice["cols"]):
            x_m, y_m = _ilp_cell_center(lattice, col, row)
            utci_cells.append(
                {"x_m": x_m, "y_m": y_m, "utci_c": utci_by_rc.get((row, col), 24.0)}
            )
            crowd_cells.append(
                {
                    "x_m": x_m,
                    "y_m": y_m,
                    "crowd_density_agents_per_cell": crowd_by_rc.get((row, col), 0.0),
                }
            )
    crs = {"epsg": 32631, "units": "metre"}
    utci = {"schema_version": "1.0.0", "crs": crs, "lattice": lattice, "cells": utci_cells}
    crowd = {
        "schema_version": "1.0.0",
        "crs": crs,
        "lattice": copy.deepcopy(lattice),
        "cells": crowd_cells,
    }
    return {"utci": utci, "crowd": crowd}


@pytest.fixture
def synthetic_tied_lattice():
    """A SMALL, site-general MCLP instance engineered to have TIED optima + a greedy trap.

    Returns ``{"lattice", "tied", "trap"}``:

    * ``tied`` — {utci, crowd} on the 6x6 lattice with TWO disjoint demand clusters of
      IDENTICAL total weight, far enough apart that with k=1 either cluster's centre is an
      equally-optimal pick. A naive solver could return EITHER; the in-objective lexicographic
      ``(row,col,index)`` tiebreak (D-12) must pick the SAME one byte-identically every run.
      This is the determinism witness — proven here, valid for any lattice size (D-15).

    * ``trap`` — {utci, crowd} where the GREEDY's first-pick is provably sub-optimal for k=2
      UNDER A NEIGHBOURHOOD COVERAGE MODEL (a disc that reaches the orthogonal neighbours, e.g.
      ``RadiusCoverage(11.0)`` on the 10 m lattice — see ``_ILP_TRAP_RADIUS_M``). A horizontal
      hot line of five cells in row 2 ``(2,0)..(2,4)``: the centre candidate at ``(2,2)`` covers
      the three fat middle cells ``(2,1),(2,2),(2,3)`` and so wins the greedy's myopic first pick,
      after which its best second pick overlaps; meanwhile the pair of candidates at ``(2,1)`` and
      ``(2,3)`` jointly covers the WHOLE line (all five cells) for strictly more weight. The exact
      ILP must therefore beat the greedy here (D-10 — proves the ILP does real work, not echoing
      the greedy). NOTE: a single-cell coverage model (e.g. ``RadiusCoverage(6.0)``, which on a
      10 m lattice reaches only the candidate's own cell) makes max-coverage = "pick the top-k
      cells", for which the greedy is already optimal — so there is NO trap. The trap only bites
      under a multi-cell coverage model; the test passes ``_ILP_TRAP_RADIUS_M`` accordingly.

    Site-generality (D-15): NON-Forum dimensions; the cross-check / determinism contracts hold
    for ANY rows x cols. Coverage uses ``RadiusCoverage`` so the demand clusters are hand-sized
    to the disc footprint.
    """
    lat = copy.deepcopy(_ILP_LATTICE_6x6)

    # Two symmetric hot+busy clusters (rows 0-1 cols 0-1) and (rows 4-5 cols 4-5), identical
    # weights => with k=1 a tie between the two cluster centres (determinism witness).
    tied_utci = {}
    tied_crowd = {}
    for (r0, c0) in ((0, 0), (4, 4)):
        for dr in (0, 1):
            for dc in (0, 1):
                tied_utci[(r0 + dr, c0 + dc)] = 30.0  # excess = 4.0
                tied_crowd[(r0 + dr, c0 + dc)] = 5.0
    tied = _build_ilp_inputs(lat, tied_utci, tied_crowd)

    # Trap (under a neighbourhood coverage model, _ILP_TRAP_RADIUS_M): a horizontal hot line of 5
    # cells in row 2. The centre candidate (2,2) covers the 3 fat middle cells (greedy grabs it
    # first for max marginal), then its best second pick overlaps; the pair (2,1)+(2,3) covers the
    # WHOLE line (all 5 cells) for strictly more weight. With k=2 the exact ILP beats the greedy.
    trap_utci = {}
    trap_crowd = {}
    for rc, w in {
        (2, 1): 10.0, (2, 2): 10.0, (2, 3): 10.0,         # fat middle 3 — the centre lure
        (2, 0): 9.0, (2, 4): 9.0,                          # line ends — only reachable by (2,1)/(2,3)
    }.items():
        trap_utci[rc] = 30.0
        trap_crowd[rc] = w
    trap = _build_ilp_inputs(lat, trap_utci, trap_crowd)

    # ── Phase 14: a far-stage region for the teeth-test (D-03) ──────────────────────────
    # Two demand clusters at KNOWN distances on the SAME 6x6 / 10 m lattice so the teeth-test
    # (Plan 03) is hand-verifiable:
    #
    #   * NEAR cluster — cells (0,0),(0,1),(1,0),(1,1). Centres (5,5),(15,5),(5,15),(15,15) m;
    #     near centroid ~= (10,10) m. High density (5.0) — always wins the as-cached selection.
    #   * FAR  cluster — cells (5,4),(5,5),(4,5). Centres (45,55),(55,55),(55,45) m; far centroid
    #     ~= (51.7,51.7) m. The far corner cell (5,5) sits sqrt(45^2+45^2) ~= 63.6 m from the near
    #     centroid — beyond a far-stage band relative to the near cluster, and it is the UNDER-served
    #     far stage (density 1.0 in the as-cached world, so it loses the k=1/k=2 selection).
    #
    # As-cached: the NEAR cluster dominates the k=1/k=2 selection. A far-stage density spike
    # (multiply the FAR cluster by ``_FAR_STAGE_SPIKE``) lets the FAR cluster compete, so >=1
    # zone's selected-set membership changes => >=1 robust/conditional label flips. That flip
    # (NOT symmetric noise) is exactly what the teeth-test asserts (D-03 / RESEARCH A3).
    fs_utci = {}
    fs_crowd = {}
    for rc in ((0, 0), (0, 1), (1, 0), (1, 1)):  # NEAR cluster (close to centroid)
        fs_utci[rc] = 30.0   # excess = 4.0
        fs_crowd[rc] = 5.0
    for rc in ((5, 4), (5, 5), (4, 5)):           # FAR cluster (the under-served far stage)
        fs_utci[rc] = 30.0   # excess = 4.0
        fs_crowd[rc] = 1.0
    far_stage = _build_ilp_inputs(lat, fs_utci, fs_crowd)

    return {"lattice": lat, "tied": tied, "trap": trap, "far_stage": far_stage}


#: Far-stage demand spike (multiplicative) the teeth-test applies onto the ``far_stage`` FAR
#: cluster to force a robust/conditional label flip (mirrors the ``_ILP_TRAP_RADIUS_M`` named-
#: constant pattern: a documented constant the test passes in). The as-cached FAR cluster
#: (density 1.0) loses to the NEAR cluster (density 5.0); spiking the FAR cluster by this factor
#: lets it compete, flipping >=1 zone's selected-set membership (proves the family is NOT
#: symmetric noise — D-03 / RESEARCH A3). Sized > the near/far density ratio (5.0) so the flip
#: is unambiguous and hand-verifiable.
_FAR_STAGE_SPIKE = 8.0


#: Coverage radius (m) under which the ``synthetic_tied_lattice["trap"]`` instance is a genuine
#: greedy trap: a disc that reaches the orthogonal neighbours of a candidate's own cell on the
#: 10 m lattice (own + 4 neighbours), so candidate coverage OVERLAPS and the submodular greedy can
#: be lured into a sub-optimal first pick. (A 6 m disc reaches only the own cell — no overlap, no
#: trap. See the trap docstring above.)
_ILP_TRAP_RADIUS_M = 11.0
