# FlowWeaver Phase 12 — Controlled Gateway Observation Hook Implementation Dev Log

## Task Background

狗哥 approved implementing Phase 12 after Phase 11 implementation PR #46 was merged and local canonical `feature/sachima-channel` was synchronized.

```text
Base branch: feature/sachima-channel
Base merge commit: b7e142dcbc1a8c30b723221c7bd0f885a88d5f58
Implementation branch: feat/flowweaver-phase12-controlled-gateway-observation-hook
Implementation worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase12-controlled-gateway-observation-hook
Started at: 2026-05-07 22:55:55 CST +0800
```

## Implementation Target

Phase 12 implements the next default-off Gateway-side seam proposed by Phase 11:

```text
exact Phase 11 design report
  + sanitized shadow runtime publication summary
  + sanitized delivery state summary
  + sanitized progress snapshot summary
  + enabled = False
  -> safe Phase 12 observation hook report
  -> ready_for_live_gateway_observation_enablement_design
```

This remains pure and side-effect-free. It does not wire live Gateway behavior.

## Hard Boundaries Preserved

```text
No gateway/run.py changes.
No run_agent.py changes.
No gateway/platforms/** changes.
No production config writes.
No production tool registry writes.
No Gateway restart.
No real send/edit/render/callback.
No live Gateway observation enablement.
No Temporal client, Worker, WorkflowEnvironment, Docker, daemon, socket, subprocess, task queue, namespace, address, or service lifecycle.
No payload-carrying Temporal Signals.
No raw prompt/tool/card/media/platform/Gateway/runtime/callback material in reports or artifacts.
```

## Files Added

```text
gateway/flowweaver_controlled_gateway_observation.py
tests/gateway/test_flowweaver_controlled_gateway_observation.py
docs/runbooks/flowweaver-controlled-gateway-observation-hook.md
docs/dev_log/2026-05-07-flowweaver-phase12-controlled-gateway-observation-hook.md
```

## TDD Evidence

### RED

Created `tests/gateway/test_flowweaver_controlled_gateway_observation.py` first, defining import/default-off boundaries, exact Phase 11 evidence consumption, safe summary projection, live-enable rejection, no-live/no-raw constraints, and source forbidden-surface scans.

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_controlled_gateway_observation.py -q
ERROR tests/gateway/test_flowweaver_controlled_gateway_observation.py
Expected RED: ModuleNotFoundError: No module named 'gateway.flowweaver_controlled_gateway_observation'
```

### GREEN

Added `gateway/flowweaver_controlled_gateway_observation.py` as a pure synchronous helper. First GREEN attempts exposed overly broad scanner behavior around approved policy labels and runbook approval markers. Patched the scanner to distinguish exact policy/approval metadata from live runtime requests, matching the project's prior lesson that forbidden-material names in policy metadata are not leaks.

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_controlled_gateway_observation.py -q
25 passed in 0.40s
```

## Implementation Notes

- The module imports only `hashlib.sha256`.
- The entrypoint is synchronous and keyword-only:

```text
build_flowweaver_controlled_gateway_observation(...)
```

- `enabled` must be exactly `False`; live enablement requests fail closed with `live_observation_requested`.
- Success output uses only stable labels, counts, checks, digests, approval labels, and stable error codes.
- Blocked output contains only safe fields:

```text
type
version
ok = False
verdict = blocked
phase
error_code
side_effects = []
```

- The helper consumes exact Phase 11 report shape and rejects missing fields, extra production fields, reordered/duplicated approval lists, side effects, unsafe raw material, and private platform-like identifiers.
- The helper accepts sanitized summaries only. It rejects platform payload keys, raw prompt/tool/card/media/runtime/callback material, private chat/user/message identifiers, and side effects.

## Verification Results

Initial focused verification:

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_controlled_gateway_observation.py -q
25 passed in 0.40s
```

The direct hermetic integration chain initially failed on existing Phase 5H/5I/5J/5K changed-file invariant allowlists. Root cause: Phase 12 intentionally adds a new pure Gateway helper, focused Gateway tests, runbook, and dev log. Patched only those allowlists for the exact Phase 12 files; no forbidden `gateway/run.py`, `run_agent.py`, `gateway/platforms/**`, config, registry, or Temporal lifecycle paths were added.

Final verification after Codex blocker fix:

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_controlled_gateway_observation.py -q
32 passed in 0.40s

scripts/run_tests.sh tests/gateway/test_flowweaver_controlled_gateway_observation.py tests/prototypes/test_flowweaver_phase*.py -q
235 passed in 0.81s

TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 \
  tests/integration/test_flowweaver_phase7_gateway_shadow_e2e_loop.py \
  tests/integration/test_flowweaver_phase6_gateway_ack_shadow_bridge.py \
  tests/integration/test_flowweaver_phase5k_runtime_control_surface.py \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py \
  tests/integration/test_flowweaver_phase5c_runtime_client_temporal.py \
  tests/integration/test_flowweaver_phase5b_temporal_workflow.py \
  -q
38 passed in 1.80s

py_compile: PASS
ruff: PASS
git diff --check: PASS
FINAL_PHASE12_HOOK_SAFETY_GUARD: PASS
```

## Codex Fresh-Context Review

Initial Codex blocker review returned BLOCK:

```text
VERDICT: BLOCK

BLOCKERS:
- gateway/flowweaver_controlled_gateway_observation.py did not enforce the exact Phase 11 output shape for nested policy/plan values. Mutated Phase 11 nested values such as artifact_policy.log_policy, artifact_policy.forbidden_material, rollback_policy.rollback_mode, rollback_policy.kill_switch_required, observation_inputs, runtime_operations, and extra approval_refs still returned ok=True.
```

Fix applied:

- Added RED regression tests for the nested Phase 11 exact-shape blockers.
- Tightened Phase 12 validation for Phase 11 `controlled_gateway_observation_plan`, `artifact_policy`, and `rollback_policy` exact values.
- Re-ran focused, regression, direct integration, static, diff, and safety guard verification.

Codex blocker-only re-review returned PASS:

```text
VERDICT: PASS

BLOCKERS:
- None.

NON_BLOCKING_NOTES:
- None.

VERIFICATION_COMMENT:
Inspected git status, the requested diff scope plus untracked Phase 12 file contents, modified integration allowlist diffs, and source scans for production Gateway wiring/runtime imports; ran direct mutation probes for the original nested Phase 11 blocker cases and reran the focused Phase 12 wrapper test with TMPDIR=/dev/shm, which reported 32 passed, so the blocker is fixed and no live Gateway/Temporal/raw-output regression is present.
```
