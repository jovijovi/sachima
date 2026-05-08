# FlowWeaver Phase 15 — Manual Live Gateway Observation Review Gate Dev Log

## Task Background

狗哥 approved starting Phase 15 after Phase 14 PR #49 and the context-overflow fix PR #51 were merged into `feature/sachima-channel` and the canonical branch was synchronized.

```text
Base branch: feature/sachima-channel
Base merge commit: f0330b4c5f2efb9f8b2342b6d889d401f5d1d19e
Implementation branch: feat/flowweaver-phase15-manual-live-gateway-observation-review-gate
Implementation worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase15-manual-live-gateway-observation-review-gate
```

## Implementation Target

Phase 15 implements the next default-off helper after Phase 14:

```text
exact Phase 14 enablement request artifact
  + static default-off review policy descriptor
  -> safe operator-decision review artifact
  -> ready_for_live_gateway_observation_enablement_operator_decision
```

This remains pure and side-effect-free. It does not wire or enable live Gateway behavior.

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
No real approval-token material accepted or emitted.
No Temporal client, Worker, WorkflowEnvironment, Docker, daemon, socket, subprocess, task queue, namespace, address, or service lifecycle.
No payload-carrying Temporal Signals.
No raw prompt/tool/card/media/platform/Gateway/runtime/callback material in reports or artifacts.
```

## Files Added

```text
docs/plans/2026-05-08-flowweaver-phase15-manual-live-gateway-observation-review-gate.md
docs/dev_log/2026-05-08-flowweaver-phase15-manual-live-gateway-observation-review-gate.md
docs/runbooks/flowweaver-live-gateway-observation-manual-review.md
gateway/flowweaver_live_gateway_observation_manual_review.py
tests/gateway/test_flowweaver_live_gateway_observation_manual_review.py
```

## Files Updated

```text
tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py
tests/integration/test_flowweaver_phase5i_start_signature_parity.py
tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py
tests/integration/test_flowweaver_phase5k_runtime_control_surface.py
```

## TDD Evidence

### RED

Created `tests/gateway/test_flowweaver_live_gateway_observation_manual_review.py` first, defining import/default-off boundaries, exact Phase 14 request consumption, safe operator-decision artifact projection, review-policy validation, no-live/no-raw constraints, hostile subclass rejection, and source forbidden-surface scans.

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_manual_review.py -q
42 failed
Expected RED: missing Phase 15 Gateway helper module import
```

### GREEN

Added `gateway/flowweaver_live_gateway_observation_manual_review.py` as a pure synchronous Gateway-side helper.

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_manual_review.py -q
42 passed in 1.18s
```

## Implementation Notes

- The module imports only `hashlib.sha256`.
- The entrypoint is synchronous and keyword-only:

```text
prepare_flowweaver_live_gateway_observation_manual_review(...)
```

- Success output uses only stable labels, checks, short safe digests, approval labels, kill-switch labels, rollback labels, and stable error codes.
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

- The helper consumes exact Phase 14 request shape and rejects missing fields, extra production fields, reordered approval lists, mutated nested review values, mutated derived ids/digests, side effects, unsafe raw material, and private platform-like identifiers.
- The helper accepts a static review policy only. It rejects approved/on states, approval-token material, config/registry writes, Gateway restart, adapter calls, Temporal lifecycle, raw material, and side effects.

## Verification Results

Focused Phase 15 contract:

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_manual_review.py -q
42 passed in 1.17s
```

Phase 11–15 regression:

```text
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_live_gateway_observation_manual_review.py \
  tests/gateway/test_flowweaver_live_gateway_observation_enablement.py \
  tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py \
  tests/gateway/test_flowweaver_controlled_gateway_observation.py \
  tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py \
  -q
217 passed in 1.42s
```

Direct hermetic integration chain:

```text
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
38 passed in 2.71s
```

Static checks:

```text
py_compile: PASS
ruff: PASS
git diff --check: PASS
FINAL_PHASE15_MANUAL_REVIEW_SAFETY_GUARD: PASS changed_files=9 impl_files=1
```

## Fresh-Context Review

Independent blocker review returned PASS:

```text
VERDICT: PASS

BLOCKERS:
- None.

NOTES:
- Changes limited to the expected 9 Phase 15 paths.
- Helper is synchronous/default-off, imports only hashlib.sha256, validates exact Phase 14 request shape, rejects unsafe/non-exact inputs, and emits sanitized blocked outputs.
- Review policy remains default-off and does not grant enablement.
- Docs consistently state Phase 15 does not authorize live Gateway behavior.
```
