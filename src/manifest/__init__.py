"""Per-project artifact manifest + resume-from-last-good-stage (CONTRACT-07 / XFN-03).

`manifest.py` is the resume mechanism: a stage-status state machine persisted to
`projects/<id>/manifest.json` with content-hash cache keys (NOT file existence —
Pitfall D / T-00-09). On an input change, the changed stage and ALL downstream
stages are invalidated to pending, so a stale artifact from a different brief can
never be silently reused.

TIER NOTE (deliberate, recorded): the Architectural Responsibility Map assigns the
projects/<id>/ manifest + run-lifecycle to the NODE orchestrator. Phase 0 ships the
CANONICAL manifest logic + resume tests in PYTHON here (that is where the Phase-0
contract tests live); the Node orchestrator (Phase 1+) will OWN the runtime manifest
writes against this SAME contract/algorithm. No speculative manifest.ts in Phase 0
(karpathy: no code without a consumer).
"""
