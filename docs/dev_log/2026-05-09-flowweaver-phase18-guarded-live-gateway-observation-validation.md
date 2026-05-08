# FlowWeaver Phase 18 — Guarded Live Gateway Observation Validation Dev Log

## Task Background

狗哥 approved starting Phase 18 after Phase 17 PR #54 was merged into `feature/sachima-channel` and the canonical branch was synchronized.

```text
Base branch: feature/sachima-channel
Base merge commit: 40d45a1dcb76cd5465d8171b2bf69ddf543fb514
Implementation branch: feat/flowweaver-phase18-guarded-live-gateway-observation-validation
Implementation worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase18-guarded-live-gateway-observation-validation
```

## Implementation Target

Phase 18 implements the next default-off helper after Phase 17:

```text
exact Phase 17 guarded-enablement artifact
  + static default-off guarded-validation policy descriptor
  -> safe Phase 18 guarded validation contract artifact
  -> ready_for_live_gateway_observation_enablement_separate_approval_request
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
No live enablement authorization accepted or emitted.
No operator approval-token material accepted or emitted.
No Temporal client, Worker, WorkflowEnvironment, service lifecycle, daemon, socket, subprocess, task queue, namespace, address, or service lifecycle.
No payload-carrying Temporal Signals.
No raw prompt/tool/card/media/platform/Gateway/runtime/callback material in reports or artifacts.
```

## Files Added

```text
docs/plans/2026-05-09-flowweaver-phase18-guarded-live-gateway-observation-validation.md
docs/dev_log/2026-05-09-flowweaver-phase18-guarded-live-gateway-observation-validation.md
docs/runbooks/flowweaver-live-gateway-observation-guarded-validation.md
gateway/flowweaver_live_gateway_observation_guarded_validation.py
tests/gateway/test_flowweaver_live_gateway_observation_guarded_validation.py
```

## Files Updated

```text
tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py
tests/integration/test_flowweaver_phase5i_start_signature_parity.py
tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py
tests/integration/test_flowweaver_phase5k_runtime_control_surface.py
```

## Codex Scope Review

Read-only Codex architecture review returned:

```text
VERDICT: PASS
SUCCESS_VERDICT: ready_for_live_gateway_observation_enablement_separate_approval_request
ENTRYPOINT: prepare_flowweaver_live_gateway_observation_guarded_validation(*, phase17_guarded_enablement, guarded_validation_policy)
```

## TDD Evidence

### RED

Created `tests/gateway/test_flowweaver_live_gateway_observation_guarded_validation.py` first, defining import/default-off boundaries, exact Phase 17 guarded-enablement consumption, safe validation contract projection, guarded-validation policy validation, no-live/no-raw constraints, hostile subclass rejection, internally consistent noncanonical prior-phase rejection, integer boolean impersonator rejection, and source forbidden-surface scans.

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_guarded_validation.py -q
15 failed
Expected RED: missing Phase 18 Gateway helper module import
```

### GREEN

Added `gateway/flowweaver_live_gateway_observation_guarded_validation.py` as a pure synchronous Gateway-side helper.

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_guarded_validation.py -q
15 passed in 1.21s
```

## Implementation Notes

- The module imports only `hashlib.sha256`.
- The entrypoint is synchronous and keyword-only:

```text
prepare_flowweaver_live_gateway_observation_guarded_validation(...)
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

- The helper consumes exact Phase 17 guarded-enablement shape and rejects missing fields, extra production fields, reordered approval lists, mutated nested validation values, mutated derived ids/digests, internally consistent noncanonical upstream ids, side effects, unsafe raw material, and private platform-like identifiers.
- The helper accepts a static guarded-validation policy only. It rejects approval-token material, live enablement, config/registry writes, Gateway restart, adapter calls, Temporal lifecycle, raw material, and side effects.

## Verification Results

Focused Phase 18 contract:

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_guarded_validation.py -q
15 passed in 1.21s
```

Phase 11–18 regression:

```text
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_live_gateway_observation_guarded_validation.py \
  tests/gateway/test_flowweaver_live_gateway_observation_guarded_enablement.py \
  tests/gateway/test_flowweaver_live_gateway_observation_operator_decision.py \
  tests/gateway/test_flowweaver_live_gateway_observation_manual_review.py \
  tests/gateway/test_flowweaver_live_gateway_observation_enablement.py \
  tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py \
  tests/gateway/test_flowweaver_controlled_gateway_observation.py \
  tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py \
  -q
261 passed in 1.74s
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
38 passed in 2.68s
```

Static checks:

```text
py_compile: PASS
ruff: PASS
warning only: top-level ruff settings are deprecated in favor of lint section

git diff --check: PASS
FINAL_PHASE18_GUARDED_VALIDATION_SAFETY_GUARD: PASS changed_files=9 impl_files=1
```

## Fresh-Context Review

Codex blocker-only review returned PASS:

```text
VERDICT: PASS
BLOCKERS:
- none
NOTES:
- Live diff stays within the Phase 18 helper/docs/tests and changed-file allowlists. No runtime Gateway wiring, platform adapter, production config, registry, restart, Temporal lifecycle, or live enablement surface was added.
```
