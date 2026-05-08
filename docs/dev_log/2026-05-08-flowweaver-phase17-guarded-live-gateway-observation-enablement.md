# FlowWeaver Phase 17 — Guarded Live Gateway Observation Enablement Dev Log

## Task Background

狗哥 approved starting Phase 17 after Phase 16 PR #53 was merged into `feature/sachima-channel` and the canonical branch was synchronized.

```text
Base branch: feature/sachima-channel
Base merge commit: edc3c600a2414df730c191d713ed921e8a732b73
Implementation branch: feat/flowweaver-phase17-guarded-live-gateway-observation-enablement
Implementation worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase17-guarded-live-gateway-observation-enablement
```

## Implementation Target

Phase 17 implements the next default-off helper after Phase 16:

```text
exact Phase 16 operator-decision artifact
  + static default-off guarded-enablement policy descriptor
  -> safe Phase 17 guarded enablement contract artifact
  -> ready_for_guarded_live_gateway_observation_validation
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
No guarded enablement authorization accepted or emitted.
No operator approval-token material accepted or emitted.
No Temporal client, Worker, WorkflowEnvironment, service lifecycle, daemon, socket, subprocess, task queue, namespace, address, or service lifecycle.
No payload-carrying Temporal Signals.
No raw prompt/tool/card/media/platform/Gateway/runtime/callback material in reports or artifacts.
```

## Files Added

```text
docs/plans/2026-05-08-flowweaver-phase17-guarded-live-gateway-observation-enablement.md
docs/dev_log/2026-05-08-flowweaver-phase17-guarded-live-gateway-observation-enablement.md
docs/runbooks/flowweaver-live-gateway-observation-guarded-enablement.md
gateway/flowweaver_live_gateway_observation_guarded_enablement.py
tests/gateway/test_flowweaver_live_gateway_observation_guarded_enablement.py
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

Created `tests/gateway/test_flowweaver_live_gateway_observation_guarded_enablement.py` first, defining import/default-off boundaries, exact Phase 16 decision consumption, safe guarded-enablement contract projection, guarded-enablement policy validation, no-live/no-raw constraints, hostile subclass rejection, internally consistent noncanonical prior-phase rejection, and source forbidden-surface scans.

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_guarded_enablement.py -q
14 failed
Expected RED: missing Phase 17 Gateway helper module import
```

After fresh-context review found exact-boolean gaps, added blocker regression tests for integer boolean impersonators (`1`/`0`) in Phase 16 and Phase 17 policy fields.

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_guarded_enablement.py::test_phase17_rejects_integer_boolean_impersonators -q
1 failed
Expected RED: integer boolean impersonators were accepted
```

### GREEN

Added `gateway/flowweaver_live_gateway_observation_guarded_enablement.py` as a pure synchronous Gateway-side helper, then tightened primitive validation so exact contract values accept only plain `str`, `bool`, `None`, `dict`, and `list` values, not integer boolean impersonators.

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_guarded_enablement.py -q
15 passed in 1.21s
```

## Implementation Notes

- The module imports only `hashlib.sha256`.
- The entrypoint is synchronous and keyword-only:

```text
prepare_flowweaver_live_gateway_observation_guarded_enablement(...)
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

- The helper consumes exact Phase 16 decision shape and rejects missing fields, extra production fields, reordered approval lists, mutated nested decision values, mutated derived ids/digests, internally consistent noncanonical upstream ids, side effects, unsafe raw material, and private platform-like identifiers.
- The helper accepts a static guarded-enablement policy only. It rejects guarded enablement authorization, live enablement, approval-token material, config/registry writes, Gateway restart, adapter calls, Temporal lifecycle, raw material, and side effects.

## Verification Results

Focused Phase 17 contract:

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_guarded_enablement.py -q
15 passed in 1.21s
```

Phase 11–17 regression:

```text
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_live_gateway_observation_guarded_enablement.py \
  tests/gateway/test_flowweaver_live_gateway_observation_operator_decision.py \
  tests/gateway/test_flowweaver_live_gateway_observation_manual_review.py \
  tests/gateway/test_flowweaver_live_gateway_observation_enablement.py \
  tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py \
  tests/gateway/test_flowweaver_controlled_gateway_observation.py \
  tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py \
  -q
246 passed in 1.60s
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
38 passed in 2.64s
```

Static checks:

```text
py_compile: PASS
ruff: PASS
warning only: top-level ruff settings are deprecated in favor of lint section

git diff --check: PASS
FINAL_PHASE17_GUARDED_ENABLEMENT_SAFETY_GUARD: PASS changed_files=9 impl_files=1
```

## Fresh-Context Review

First independent blocker review found exact boolean validation gaps:

```text
VERDICT: BLOCKERS
- Integer boolean impersonators (`1`/`0`) were accepted in exact Phase 16 and Phase 17 policy fields.
```

Final blocker-only review returned PASS after strict primitive validation and RED regression tests:

```text
VERDICT: PASS
```
