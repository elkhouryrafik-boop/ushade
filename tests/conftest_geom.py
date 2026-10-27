"""Reusable FAKE Rhino.Compute client + fixture loaders for the offline Geometry suite.

Like ``conftest_climate.py`` (the ``FakeInfraredClient`` recorded-fixture fake) crossed with
``conftest_core.py`` (explicit-import, NOT auto-loaded — pytest only auto-loads ``conftest.py``),
this module is imported BY NAME in the Phase-4 geom tests. It exists so the Wave-2/3 transforms
(``geom.reference_generator.cull_grid``/``build_reference``, ``geom.decode.decode_mesh``) and the
stage spine can be unit-tested against a RECORDED ``gh_response`` — no live Rhino.Compute call, no
network, no randomness.

The default geom test run never POSTs to EC2 (Pitfall T-04-03): ``FakeRhinoClient`` is a pure-Python
object that mimics the exact ``.solve(gh_request) -> gh_response`` surface ``src/geom`` will exercise.
It RECORDS the ``gh_request`` it was solved with (so the request-assembly contract tests can assert
the frozen IN_ fields) and returns the recorded ``gh_response`` fixture. ``raise_solve_error=True``
exercises the stage-NOT-done path (clone ``FakeInfraredClient.raise_area_error``).

NO rhino3dm / axios import at module top — heavy/geom-extra code is exercised only INSIDE the
functions under test (mirror ``conftest_core`` lines 42-43 / ``conftest_climate`` "no real SDK
import").

karpathy: one fake object, no mock framework, no real client import.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_GH_RESPONSE_FIXTURE = _TESTS_DIR / "fixtures" / "gh_response" / "valid_primavera.json"
_FOOTPRINT = _REPO_ROOT / "projects" / "primavera-demo" / "footprint.json"
_CROWD_GRID = _REPO_ROOT / "projects" / "primavera-demo" / "crowd_grid.json"


# --------------------------------------------------------------------------- #
# Fixture loaders
# --------------------------------------------------------------------------- #
def load_gh_response_fixture() -> dict:
    """Load the recorded, contract-valid ``gh_response`` fixture (the offline seam)."""
    return json.loads(_GH_RESPONSE_FIXTURE.read_text(encoding="utf-8"))


def load_footprint() -> dict:
    """Load the real primavera-demo footprint (85 polygons, EPSG:32631, ~588x768 m)."""
    return json.loads(_FOOTPRINT.read_text(encoding="utf-8"))


def load_flow_vectors() -> list[dict]:
    """Load the real primavera-demo flow vectors (already the gh_request line shape; NO reshape)."""
    return json.loads(_CROWD_GRID.read_text(encoding="utf-8"))["flow_vectors"]


# --------------------------------------------------------------------------- #
# Fake Rhino.Compute client surface
# --------------------------------------------------------------------------- #
class RhinoComputeError(RuntimeError):
    """Typed error mirroring the (Wave-2) ``geom.client.RhinoComputeError`` so the
    stage-NOT-done test can ``pytest.raises`` against a stable name even in the RED tier."""


class FakeRhinoClient:
    """Pure-Python stand-in for the live Rhino.Compute client (NO axios/rhino3dm import).

    Records the ``gh_request`` it was ``.solve()``-ed with so the offline request-assembly
    contract tests can assert the frozen IN_ fields + ``schema_version`` without any network.
    Returns the recorded ``gh_response`` fixture. Supports a context-manager protocol so
    ``with FakeRhinoClient() as c:`` mirrors the live client's usage.

    Args:
        raise_solve_error: when True, ``solve`` raises ``RhinoComputeError`` (simulates a live
            solve failure) so the fail-stage-NOT-done test fires.
    """

    def __init__(self, raise_solve_error: bool = False):
        self.raise_solve_error = raise_solve_error
        self.last_request: dict | None = None  # the gh_request the client was solved with
        self.solve_count = 0  # number of LIVE-equivalent solve dispatches

    # -- context manager -------------------------------------------------- #
    def __enter__(self) -> "FakeRhinoClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False  # do not suppress exceptions

    # -- call surface ----------------------------------------------------- #
    def solve(self, gh_request: dict) -> dict:
        """Record the request, return the recorded gh_response (or raise the typed error)."""
        self.last_request = copy.deepcopy(gh_request)
        self.solve_count += 1
        if self.raise_solve_error:
            raise RhinoComputeError("Rhino.Compute solve failed (every job errored)")
        return load_gh_response_fixture()


# --------------------------------------------------------------------------- #
# pytest fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def fake_rhino_client() -> FakeRhinoClient:
    """A fresh fake Rhino.Compute client (default success path)."""
    return FakeRhinoClient()


@pytest.fixture
def gh_response_fixture() -> dict:
    """The recorded, contract-valid gh_response fixture."""
    return load_gh_response_fixture()


@pytest.fixture
def demo_footprint() -> dict:
    """The real primavera-demo footprint."""
    return load_footprint()


@pytest.fixture
def demo_flow_vectors() -> list[dict]:
    """The real primavera-demo flow vectors (gh_request line shape, no reshape)."""
    return load_flow_vectors()
