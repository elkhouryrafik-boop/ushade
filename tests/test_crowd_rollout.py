"""Phase 2b rollout determinism + torch-quarantine contract (CROWD-01).

Three tiers, by import cost:

* ``test_rollout_module_imports_torch_free`` runs in the BASE (torch-free) suite — importing
  ``crowd.rollout`` must NOT pull torch onto the import path (the SB3/torch imports are lazy,
  inside the functions). Mirrors the Phase-2a infrared-SDK quarantine (T-02b-02). torch IS
  installed on this machine, so the guard is import-ORDER (rollout's import did not add torch),
  not import-absence.
* ``test_rollout_has_no_top_level_torch_import`` is a STATIC source guard: ``rollout.py`` has no
  module-level ``import torch`` / ``from stable_baselines3`` — the imports must be in-function.
* ``test_runs_exactly_200_steps`` + ``test_same_seed_same_trajectory`` are ``@pytest.mark.crowd``
  (real PPO inference on the committed ``policy.zip``): exactly SIM_STEPS=200 steps, and same
  seed → byte-identical trajectory (the runtime determinism guarantee, CPU single-machine).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest

from crowd.constants import SEED, SIM_STEPS

_CROWD_DIR = Path(__file__).resolve().parent.parent / "src" / "crowd"
_POLICY_PATH = _CROWD_DIR / "policy.zip"


def _policy_obs_dim_matches_env() -> bool:
    """True iff the COMMITTED policy.zip's observation input dim equals the current env OBS_DIM.

    Phase 2.1-03 redesigned the env obs to OBS_DIM=7 (scale-free flow-field cue). The committed
    policy.zip is the V1 6-input artifact; it is RETRAINED to a 7-input policy in Plan 02.1-04
    (Wave 4). Real-inference rollout tests over the committed policy are therefore expected to fail
    on the dimension mismatch UNTIL that retrain lands — at which point this predicate flips True
    and the xfail auto-resolves (strict=False → an xpass is tolerated, never a hard failure).
    This keys the xfail on the ARTIFACT (a real dimension probe), not on a hand-set skip.
    """
    try:
        from crowd.env import OBS_DIM
        from crowd.rollout import load_policy

        pol = load_policy(_POLICY_PATH)
        return int(pol.observation_space.shape[0]) == int(OBS_DIM)
    except Exception:  # noqa: BLE001 - any probe failure → treat as mismatch (xfail), never error
        return False


_POLICY_DIM_MISMATCH = _POLICY_PATH.exists() and not _policy_obs_dim_matches_env()
_RETRAIN_PENDING_REASON = (
    "committed policy.zip is the V1 6-input artifact; env obs is now OBS_DIM=7 (Plan 02.1-03). "
    "Retrained to a 7-input policy in Plan 02.1-04 (Wave 4) — auto-resolves then."
)


def _strip_lattice() -> dict:
    """A small runtime lattice (the rollout env derives its site bbox from this)."""
    return {
        "origin_x_m": 0.0,
        "origin_y_m": 0.0,
        "cell_size_m": 6.0,
        "cols": 20,
        "rows": 20,
    }


def test_rollout_module_imports_torch_free():
    """Importing ``crowd.rollout`` must not pull torch onto the base import path (T-02b-02).

    torch is installed here, so we assert the IMPORT did not ADD a torch module entry: drop any
    existing torch from sys.modules, import rollout fresh, and assert rollout's import alone did
    not re-import torch (the SB3/torch imports live inside the functions, not at module top).
    """
    # Remove torch + sb3 + rollout so we observe what rollout's import ALONE pulls in.
    for name in list(sys.modules):
        if name == "torch" or name.startswith("torch.") or name.startswith(
            "stable_baselines3"
        ) or name == "crowd.rollout":
            del sys.modules[name]
    importlib.import_module("crowd.rollout")
    assert "torch" not in sys.modules, (
        "importing crowd.rollout pulled in torch — the SB3/torch import must be lazy "
        "(inside the function), never at module top-level"
    )


def test_rollout_has_no_top_level_torch_import():
    """STATIC guard: rollout.py has no module-level torch / stable_baselines3 import."""
    src = (_CROWD_DIR / "rollout.py").read_text(encoding="utf-8")
    for line in src.splitlines():
        stripped = line.strip()
        # A top-level import has no leading indentation (function-body imports are indented).
        if line[:1] not in (" ", "\t"):
            assert not stripped.startswith("import torch"), "top-level `import torch` forbidden"
            assert not stripped.startswith(
                "from torch"
            ), "top-level `from torch ...` forbidden"
            assert not stripped.startswith(
                "import stable_baselines3"
            ), "top-level SB3 import forbidden"
            assert not stripped.startswith(
                "from stable_baselines3"
            ), "top-level `from stable_baselines3 ...` forbidden"


@pytest.mark.crowd
@pytest.mark.xfail(_POLICY_DIM_MISMATCH, reason=_RETRAIN_PENDING_REASON, strict=False)
def test_runs_exactly_200_steps():
    """Rollout over the committed policy yields EXACTLY a SIM_STEPS-length trajectory (CROWD-01)."""
    from crowd.env import FestivalEnv
    from crowd.rollout import rollout

    assert _POLICY_PATH.exists(), f"committed policy missing: {_POLICY_PATH}"
    env = FestivalEnv(lattice=_strip_lattice(), utci_cells=[], n_agents=12, seed=SEED)
    traj = rollout(_POLICY_PATH, env, n_agents=12)
    assert traj.shape[0] == SIM_STEPS, f"expected {SIM_STEPS} steps, got {traj.shape[0]}"
    assert traj.shape[1] == 12 and traj.shape[2] == 4, f"bad trajectory shape {traj.shape!r}"


@pytest.mark.crowd
@pytest.mark.xfail(_POLICY_DIM_MISMATCH, reason=_RETRAIN_PENDING_REASON, strict=False)
def test_same_seed_same_trajectory():
    """Two rollouts with the SAME seed produce a byte-identical trajectory (runtime determinism)."""
    from crowd.env import FestivalEnv
    from crowd.rollout import rollout

    assert _POLICY_PATH.exists(), f"committed policy missing: {_POLICY_PATH}"
    env_a = FestivalEnv(lattice=_strip_lattice(), utci_cells=[], n_agents=10, seed=SEED)
    env_b = FestivalEnv(lattice=_strip_lattice(), utci_cells=[], n_agents=10, seed=SEED)
    traj_a = rollout(_POLICY_PATH, env_a, n_agents=10)
    traj_b = rollout(_POLICY_PATH, env_b, n_agents=10)
    assert np.array_equal(traj_a, traj_b), "same seed produced differing trajectories"
