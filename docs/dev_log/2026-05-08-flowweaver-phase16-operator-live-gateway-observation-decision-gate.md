# FlowWeaver Phase 16 — Operator Live Gateway Observation Decision Gate Dev Log

## Task Background

狗哥 approved starting Phase 16 after Phase 15 PR #52 was merged into `feature/sachima-channel` and the canonical branch was synchronized.

```text
Base branch: feature/sachima-channel
Base merge commit: a6c50a72adca1c925199f947a33207d65e156ef2
Implementation branch: feat/flowweaver-phase16-operator-live-gateway-observation-decision-gate
Implementation worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase16-operator-live-gateway-observation-decision-gate
```

## Implementation Target

Phase 16 implements the next default-off helper after Phase 15:

```text
exact Phase 15 manual review artifact
  + static default-off operator-decision policy descriptor
  -> safe Phase 16 operator-decision gate artifact
  -> ready_for_guarded_live_gateway_observation_enablement_implementation
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
No operator approval-token material accepted or emitted.
No Temporal client, Worker, WorkflowEnvironment, service lifecycle, daemon, socket, subprocess, task queue, namespace, address, or service lifecycle.
No payload-carrying Temporal Signals.
No raw prompt/tool/card/media/platform/Gateway/runtime/callback material in reports or artifacts.
```

## Files Added

```text
docs/plans/2026-05-08-flowweaver-phase16-operator-live-gateway-observation-decision-gate.md
docs/dev_log/2026-05-08-flowweaver-phase16-operator-live-gateway-observation-decision-gate.md
docs/runbooks/flowweaver-live-gateway-observation-operator-decision.md
gateway/flowweaver_live_gateway_observation_operator_decision.py
tests/gateway/test_flowweaver_live_gateway_observation_operator_decision.py
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

Created `tests/gateway/test_flowweaver_live_gateway_observation_operator_decision.py` first, defining import/default-off boundaries, exact Phase 15 review consumption, safe operator-decision gate artifact projection, operator-decision policy validation, no-live/no-raw constraints, hostile subclass rejection, and source forbidden-surface scans.

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_operator_decision.py -q
12 failed
Expected RED: missing Phase 16 Gateway helper module import
```

After fresh-context review found Phase 15 exactness gaps, added blocker regression tests for tampered Phase 15 ids, internally consistent noncanonical upstream ids, and raw-marker `manual_review.safe_digest` values.

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_operator_decision.py -q
1 failed, 13 passed
Expected RED: internally consistent noncanonical Phase 15 ids were accepted
```

### GREEN

Added `gateway/flowweaver_live_gateway_observation_operator_decision.py` as a pure synchronous Gateway-side helper, then tightened Phase 15 exactness validation to canonical chain ids plus recomputed Phase 15 `review_id` and `manual_review.safe_digest`.

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_operator_decision.py -q
14 passed in 1.18s
```

## Implementation Notes

- The module imports only `hashlib.sha256`.
- The entrypoint is synchronous and keyword-only:

```text
prepare_flowweaver_live_gateway_observation_operator_decision(...)
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

- The helper consumes exact Phase 15 review shape and rejects missing fields, extra production fields, reordered approval lists, mutated nested review values, mutated derived ids/digests, side effects, unsafe raw material, and private platform-like identifiers.
- The helper accepts a static operator-decision policy only. It rejects recorded/approved operator decisions, live enablement, approval-token material, config/registry writes, Gateway restart, adapter calls, Temporal lifecycle, raw material, and side effects.

## Verification Results

Focused Phase 16 contract:

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_live_gateway_observation_operator_decision.py -q
14 passed in 1.18s
```

Phase 11–16 regression:

```text
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_live_gateway_observation_operator_decision.py \
  tests/gateway/test_flowweaver_live_gateway_observation_manual_review.py \
  tests/gateway/test_flowweaver_live_gateway_observation_enablement.py \
  tests/prototypes/test_flowweaver_phase13_live_gateway_observation_enablement_design.py \
  tests/gateway/test_flowweaver_controlled_gateway_observation.py \
  tests/prototypes/test_flowweaver_phase11_controlled_gateway_observation_design.py \
  -q
231 passed in 1.47s
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
38 passed in 2.60s
```

Static checks:

```text
py_compile: PASS
ruff: PASS
warning only: top-level ruff settings are deprecated in favor of lint section

git diff --check: PASS
FINAL_PHASE16_OPERATOR_DECISION_SAFETY_GUARD: PASS changed_files=9 impl_files=1
```

## Fresh-Context Review

First independent blocker review found Phase 15 exactness gaps:

```text
VERDICT: BLOCKERS
- Tampered Phase 15 derived ids and `manual_review.safe_digest` were not rejected strongly enough.
```

Second blocker-only review found one remaining exactness blocker:

```text
VERDICT: BLOCKERS
- Internally consistent but noncanonical Phase 15 upstream ids could still be accepted.
```

Final blocker-only review returned PASS after adding canonical Phase 15 chain-id checks plus recomputation tests:

```text
VERDICT: PASS
- Phase 16 exact-checks canonical Phase 15 chain ids.
- Phase 16 recomputes Phase 15 `review_id` and `manual_review.safe_digest`.
- Focused tests passed and ad-hoc tamper probes were blocked.
```
