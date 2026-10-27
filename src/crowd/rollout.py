"""SUPERSEDED 2026-06-21 (Phase 15): JuPedSim (src/crowdsim/) is the live crowd engine.
This PPO stack is a DORMANT, reversible reference (D-04) — importable but NOT called on the
live path. Do not delete; do not wire. Kept because the JuPedSim festival→primitive mapping is
only MEDIUM-confidence until proven on the real site across runs.

Deterministic inference rollout — the (formerly) ONLY crowd code on the runtime pipeline path
(CROWD-01); the live runtime path now uses the JuPedSim CFSM engine (D-06).

``rollout(policy_path, env, n_agents)`` loads the frozen PPO policy, seeds every RNG, and runs
EXACTLY ``SIM_STEPS`` (=200, the named PRD constant) deterministic per-agent predictions over the
festival env, recording the per-step trajectory. Inference only — NO training, NO file I/O.

Decentralised per-agent inference (the 02b-02 Option-A design): each step the env yields ONE
observation per agent (``env.observe_all()`` → ``(n_agents, OBS_DIM)``); the shared policy is
applied with a single batched ``model.predict(..., deterministic=True)`` → ``(n_agents, 2)``; the
env integrates all agents simultaneously (``env.step_all``). This is the same per-agent congestion
response the Weidmann FD gate validated in training — so the runtime crowd field is produced by the
benchmark-passing policy, agent by agent.

Determinism (RESEARCH §Determinism): ``set_random_seed(SEED)`` seeds python/numpy/torch (CPU);
``env.reset(seed=SEED)`` seeds spawns; ``deterministic=True`` makes ``predict`` a pure function of
the observation. On one CPU machine the same seed therefore yields a byte-identical trajectory
(``test_same_seed_same_trajectory``). CPU-only (``device="cpu"``) — no CUDA divergence.

Purity / quarantine (T-02b-02): stable_baselines3 / torch are LAZY-imported INSIDE ``rollout`` (and
``load_policy``), never at module top-level — so ``import crowd.rollout`` does NOT pull torch onto
the base import path (mirrors the Phase-2a infrared-SDK lazy-import quarantine). Importing this
module is cheap and torch-free; only CALLING ``rollout`` requires the ``crowd`` extra.
"""

from __future__ import annotations

import numpy as np

from crowd.constants import SEED, SIM_STEPS, SIM_STEPS_V2


def load_policy(policy_path):
    """Load the frozen PPO policy on CPU (SB3 lazy-imported — keeps the base suite torch-free)."""
    from stable_baselines3 import PPO  # lazy: optional `crowd` dep, never module-top

    return PPO.load(str(policy_path), device="cpu")


def rollout(policy_path, env, n_agents=None, *, seed: int = SEED, steps: int = SIM_STEPS) -> np.ndarray:
    """Run EXACTLY ``steps`` deterministic per-agent steps; return the trajectory.

    Args:
        policy_path: path to the committed ``policy.zip`` (frozen PPO weights). May also be an
            already-loaded policy object exposing ``predict(obs, deterministic=True)`` (the
            torch-free Plan-04 integration test injects a fake policy here).
        env: a ``FestivalEnv`` (or compatible) exposing ``reset``, ``observe_all``, ``step_all``,
            ``snapshot``.
        n_agents: accepted for API symmetry with the orchestrator (the env already holds its own
            agent count); unused beyond a sanity note — the env's N drives the rollout.
        seed: the fixed runtime seed (defaults to the named ``SEED``).
        steps: the rollout HORIZON (named constant, never inlined). Defaults to ``SIM_STEPS``
            (=200) — the V1 corridor/benchmark harness's PRD backstop, UNCHANGED for back-compat.
            The site-native RUNTIME path (Plan 02.1-05) passes ``steps=SIM_STEPS_V2`` (=1400, the
            measured far-stage travel horizon — RESEARCH §Q2). Both are named module constants:
            ``SIM_STEPS`` for the corridor harness, ``SIM_STEPS_V2`` for the real-site runtime; the
            loop's terminator is this argument, never an inlined literal.

    Returns:
        ``np.ndarray`` of shape ``(steps, n_agents, 4)`` — per-step per-agent ``[x, y, vx, vy]``
        (the trajectory grid.py consumes). The leading axis is EXACTLY ``steps`` by construction:
        ``SIM_STEPS`` (200) for the V1 corridor harness, ``SIM_STEPS_V2`` (1400) for the runtime.
    """
    # SIM_STEPS_V2 is imported so the named runtime horizon is documented at this module's import
    # surface (the runtime caller passes it explicitly); the default keeps the V1 SIM_STEPS backstop.
    _ = SIM_STEPS_V2  # referenced for the named-constant contract (see docstring); no behaviour.

    # Accept either a path (load it) or an already-loaded/injected policy object.
    # SB3 import is ONLY triggered when loading a real policy from a path — keeps
    # the base (torch-free) test tier safe when a fake policy object is injected directly.
    if hasattr(policy_path, "predict"):
        model = policy_path
    else:
        from stable_baselines3.common.utils import set_random_seed  # lazy: crowd dep
        set_random_seed(seed)  # seeds python `random`, numpy, torch (CPU) in one call
        model = load_policy(policy_path)

    env.reset(seed=seed)  # seeded spawns → reproducible first state
    traj: list[np.ndarray] = []
    for _step in range(steps):  # EXACTLY `steps` (a named constant; the loop's only terminator)
        obs_all = env.observe_all()  # (n_agents, OBS_DIM): one observation per agent
        actions, _ = model.predict(obs_all, deterministic=True)  # pure fn of obs → reproducible
        env.step_all(actions)  # integrate all agents simultaneously (decentralised step)
        traj.append(env.snapshot())  # (n_agents, 4): x, y, vx, vy

    return np.stack(traj, axis=0)  # (steps, n_agents, 4)
