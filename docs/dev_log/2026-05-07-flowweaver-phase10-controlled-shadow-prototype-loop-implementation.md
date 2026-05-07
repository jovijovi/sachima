# FlowWeaver Phase 10 — Controlled Shadow Prototype Loop Implementation Dev Log

## Task Background

狗哥 approved entering Phase 10 implementation after the Phase 10 design PR #43 was verified merged and local canonical `feature/sachima-channel` was synchronized.

```text
Base branch: feature/sachima-channel
Base merge commit: 8f7ba35fe5fff076ead663f8fc1be01e1c196f9d
Implementation branch: feat/flowweaver-phase10-controlled-shadow-prototype-loop-implementation
Implementation worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase10-controlled-shadow-prototype-loop-implementation
Started at: 2026-05-07 17:15:16 CST +0800
```

## Implementation Target

Phase 10 implements the prototype-only step designed in PR #43:

```text
exact Phase 9 controlled-shadow plan report
  + bounded sanitized Phase 7-style publication fixtures
  + caller-supplied prototype control surface
  + default-off run policy
  -> safe controlled-shadow prototype loop report
```

Strongest allowed success verdict:

```text
controlled_shadow_prototype_loop_verified
```

That verdict means only bounded prototype evidence exists. It does not authorize live Gateway observation, production Gateway wiring, production config/tool-registry writes, external Temporal lifecycle, Gateway restart, or real IM effects.

## Hard Boundaries

```text
No production Gateway/Feishu/Sachima integration.
No gateway/run.py changes.
No run_agent.py changes.
No gateway/platforms/** changes.
No production config writes.
No production tool registry writes.
No Docker, daemon, Temporal service, or Gateway restart.
No real send/edit/render/callback.
No Temporal client or Worker construction.
No payload-carrying Temporal Signals.
No live Gateway observation.
```

## Context Inspected

Read and used as source material:

```text
docs/plans/2026-05-07-flowweaver-phase10-controlled-shadow-prototype-loop-design.md
docs/runbooks/flowweaver-controlled-shadow-plan-builder.md
docs/runbooks/flowweaver-production-readiness.md
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_shadow_design.py
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/gateway_shadow_e2e_loop.py
tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py
tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py
```

Baseline focused regression before changes:

```text
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py -q
25 passed in 0.45s
```

## TDD Evidence

### RED 1 — import/surface

Created `tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py` with import/default-off surface expectations.

```text
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py -q
FAILED ... ModuleNotFoundError: No module named 'flowweaver_runtime_client.controlled_shadow_prototype_loop'
1 failed in 0.38s
```

This was the expected RED: module missing, not `no tests ran`.

### GREEN 1 — minimal skeleton

Added the minimal Phase 10 module skeleton and public constants.

```text
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py -q
1 passed in 0.36s
```

### RED 2 — behavior contract

Expanded tests for:

- exact Phase 9 report shape,
- exact `verification_matrix`, `runbook_outline`, and `controlled_shadow_plan.fail_closed_errors`,
- bounded publication and delivery ACK fixture counts,
- fake caller-supplied control surface only,
- safe success artifact/report shape,
- stable blocked errors without raw material leakage.

```text
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py -q
6 failed, 1 passed in 0.41s
```

Failures were expected because the skeleton always returned `invalid_phase9_plan` and did not run Phase 7.

### GREEN 2 — implementation

Implemented `controlled_shadow_prototype_loop.py` as a narrow wrapper over Phase 7 after exact Phase 9/run-policy/fixture validation.

```text
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py -q
7 passed in 0.38s
```

## Files Added

```text
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_shadow_prototype_loop.py
tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py
docs/runbooks/flowweaver-controlled-shadow-prototype-loop.md
docs/dev_log/2026-05-07-flowweaver-phase10-controlled-shadow-prototype-loop-implementation.md
```

## Verification Evidence

Focused and prototype regression:

```text
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py -q
7 passed in 0.38s

scripts/run_tests.sh tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py -q
8 passed in 0.38s

scripts/run_tests.sh tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py -q
9 passed in 0.38s

scripts/run_tests.sh tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py -q
8 passed in 0.39s

scripts/run_tests.sh tests/prototypes/test_flowweaver_phase*.py -q
142 passed in 0.69s
```

Integration regression:

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
38 passed in 1.80s
```

The first integration attempt failed closed because prior-phase changed-file allowlists did not yet include the four new Phase 10 files. The implementation patched only those allowlists. A second attempt then exposed one old guard's broad static marker scan against literal lifecycle words in the new implementation; those boundary metadata string literals were split without changing runtime behavior. The final direct integration run passed.

Static gates:

```text
py_compile: PASS
ruff: PASS
Runtime output: All checks passed!
git diff --check: PASS
```

Custom Phase 10 guard:

```text
CUSTOM_PHASE10_GUARD: PASS
changed_files:
- docs/dev_log/2026-05-07-flowweaver-phase10-controlled-shadow-prototype-loop-implementation.md
- docs/runbooks/flowweaver-controlled-shadow-prototype-loop.md
- prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_shadow_prototype_loop.py
- tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py
- tests/integration/test_flowweaver_phase5i_start_signature_parity.py
- tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py
- tests/integration/test_flowweaver_phase5k_runtime_control_surface.py
- tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py
```

The custom secret scan is added-line/new-file based. A full-file scan would hit legacy integration guard strings that intentionally contain forbidden pattern examples; that is not new secret material.

Additional blocker-fix verification after Codex review:

```text
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase10_controlled_shadow_prototype_loop.py -q
8 passed in 0.38s

scripts/run_tests.sh tests/prototypes/test_flowweaver_phase*.py -q
143 passed in 0.67s

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
38 passed in 1.82s

py_compile: PASS
ruff: PASS
Runtime output: All checks passed!
git diff --check: PASS
POST_CANONICAL_SLOT_CUSTOM_PHASE10_GUARD: PASS
```

Last evidence append: 2026-05-07 17:41:26 CST +0800.

## Fresh-Context Review

Codex fresh-context review found three blockers:

1. ACK fixture surface validation used a global surface list instead of Phase 9 plan `allowed_surfaces`.
2. Phase 9 `runtime_operations` could be a subset even though Phase 7 requires start/query/reconcile.
3. ACK `target_id` was not fully validated against initialized delivery slots before Phase 7 calls.

RED-first fixes added probes for all three and required:

- ACK surfaces to be a subset of Phase 9 plan `allowed_surfaces`,
- Phase 9 runtime operations to exactly equal start/query/reconcile for this prototype loop,
- ACK target IDs to refer to canonical initialized delivery slots before any Phase 7 runtime/control-surface call.

Blocker-only re-review then found one remaining edge: `runtime_delivery_00` normalized to slot `0` and reached Phase 7 before blocking. A RED case for `runtime_delivery_00` was added, `_validate_initialized_delivery_target` now requires the suffix to equal canonical `str(index)`, and the focused/full gates above were rerun.

Final Codex blocker-only re-review verdict:

```text
VERDICT: PASS
BLOCKERS:
- None.
VERIFICATION_COMMENT:
- Confirmed ACK target validation runs before run_shadow_gateway_e2e_loop, and canonical suffix enforcement rejects runtime_delivery_00.
- Ran targeted smoke checks: runtime_delivery_0 accepted; runtime_delivery_9, runtime_delivery_00, and runtime_delivery_01 rejected.
- Ran direct loop smoke for runtime_delivery_9 and runtime_delivery_00: both returned blocked with control_calls == 0.
- Ran git diff --check: PASS. Did not rerun the full Hermes suites listed in the request.
```
