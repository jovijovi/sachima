# FlowWeaver Phase 9 — Controlled Shadow Implementation Dev Log

## Task Background

狗哥 approved Phase 9 implementation after Phase 9 design PR #41 was merged into `feature/sachima-channel`.

```text
Base branch: feature/sachima-channel
Base merge commit: 3f80266ef499c06ab3459951991a214ecb417937
Implementation branch: feat/flowweaver-phase9-controlled-shadow-implementation
Implementation worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase9-controlled-shadow-implementation
```

The approved design target is a pure, synchronous, prototype-only plan builder:

```text
build_flowweaver_controlled_shadow_plan(...)
```

It consumes an exact safe Phase 8 readiness report plus static descriptors for shadow scope, Gateway observation boundary, runtime execution boundary, artifact policy, and rollback policy. It returns only a controlled-shadow prototype plan and verification evidence.

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
```

The strongest successful verdict for this phase is:

```text
ready_for_controlled_shadow_prototype
```

That verdict means only that the static prototype plan contract is internally safe. It does not authorize production activation, live Gateway observation, runtime lifecycle ownership, or real IM effects.

## TDD Evidence

RED was written before implementation:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py -q
```

Expected RED result:

```text
8 failed
ModuleNotFoundError: No module named 'flowweaver_runtime_client.controlled_shadow_design'
```

GREEN after implementing the pure builder:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py -q
```

Observed focused result:

```text
8 passed in 0.38s
```

## Implementation Summary

New prototype module:

```text
prototypes/flowweaver_phase5c_runtime_client/src/flowweaver_runtime_client/controlled_shadow_design.py
```

New focused tests:

```text
tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py
```

New runbook:

```text
docs/runbooks/flowweaver-controlled-shadow-plan-builder.md
```

The builder is intentionally lifecycle-free:

- imports no Gateway modules,
- imports no platform adapters,
- imports no Temporal runtime modules,
- creates no clients, workers, subprocesses, sockets, services, or registry/config writers,
- returns plain dictionaries only.

## Contract Summary

Accepted success input:

- exact Phase 8 success report shape,
- `ready_for_controlled_shadow_design` from Phase 8,
- `side_effects: []`,
- required Phase 8 checks all true,
- required separate approvals present,
- candidate runtime operations restricted to `start_transaction`, `query_transaction`, and `reconcile_delivery_ack`,
- sanitized surfaces only.

Rejected inputs include:

- missing or extra Phase 8 report fields,
- failed or wrong-verdict Phase 8 reports,
- workflow/transaction ID mismatch,
- live Gateway observation intent,
- adapter import or platform payload allowance,
- runtime client/worker/service lifecycle hints,
- payload-carrying signal intent,
- raw prompt/tool/card/media/platform material outside explicit policy metadata,
- unsafe artifact fields,
- missing rollback plan or kill switch,
- production config, registry, restart, service, or real delivery intent.

## Debugging Notes

Two sanitizer edge cases were fixed during GREEN:

1. Policy metadata fields such as `forbidden_material` and `runbook_outline` are allowed as policy names/values, but raw material in unknown leak surfaces remains rejected.
2. `artifact_policy.allowed_fields` is validated by the artifact policy contract so unsafe field names produce `artifact_policy_violation`, while unknown raw values still produce `unsafe_material`.

This matches the Phase 8 lesson: forbidden-material names in policy metadata are not themselves leaks; raw values in actual outputs or unknown surfaces are leaks.

## Verification Plan

Before commit/PR, run:

```bash
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py -q
scripts/run_tests.sh tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py -q
scripts/run_tests.sh \
  tests/prototypes/test_flowweaver_phase9_controlled_shadow_design.py \
  tests/prototypes/test_flowweaver_phase8_production_readiness_gate.py \
  tests/prototypes/test_flowweaver_phase7_gateway_shadow_e2e_loop.py \
  tests/prototypes/test_flowweaver_phase6_gateway_ack_shadow_bridge.py \
  tests/prototypes/test_flowweaver_phase5k_runtime_control_surface.py \
  tests/prototypes/test_flowweaver_phase5k_mcp_control_surface.py \
  tests/prototypes/test_flowweaver_phase5j_activity_contract.py \
  tests/prototypes/test_flowweaver_phase5i_start_signature_contract.py \
  tests/prototypes/test_flowweaver_phase5g_delivery_cardinality.py \
  tests/prototypes/test_flowweaver_phase5f_local_runtime_reconciliation.py \
  tests/prototypes/test_flowweaver_phase5e_local_publish_adapter.py \
  tests/prototypes/test_flowweaver_phase5e_variable_runtime_ids.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  tests/prototypes/test_flowweaver_phase5c_tool_adapter.py \
  tests/prototypes/test_flowweaver_phase5c_mcp_server_surface.py \
  tests/prototypes/test_flowweaver_phase5c_tool_surface.py \
  tests/prototypes/test_flowweaver_phase5b_temporal_payloads.py \
  -q
```

Integration regression must use direct hermetic pytest; `scripts/run_tests.sh` intentionally ignores `tests/integration/**`.

Pending final gates:

- Codex fresh-context review.

## Verification Results

Focused and regression commands:

```text
FOCUSED_PHASE9: 8 passed in 0.38s
PHASE8_COMPAT: 9 passed in 0.37s
PROTOTYPE_REGRESSION: 135 passed in 0.83s
INTEGRATION_REGRESSION: 38 passed in 1.82s
```

Static and safety gates:

```text
python -m py_compile: PASS
ruff: All checks passed!
git diff --check: PASS
changed-file allowlist: PASS
production-surface guard: PASS
required marker scan: PASS
added-line/new-file secret-shaped scan: PASS
```

Integration guard allowlists were updated in these existing tests because they intentionally fail closed on any new FlowWeaver prototype files:

```text
tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py
tests/integration/test_flowweaver_phase5i_start_signature_parity.py
tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py
tests/integration/test_flowweaver_phase5k_runtime_control_surface.py
```

A full-file secret-shaped scan initially flagged pre-existing forbidden-pattern strings inside an integration guard. That was a scanner false positive because the requesting-code-review rule is to scan added lines; the corrected added-line/new-file scan passed.

## Codex Fresh-Context Review

Initial Codex review returned `BLOCK` with two blockers:

1. Phase 8 readiness report validation was not exact enough: duplicate `required_separate_approvals`, non-Phase-8 `fail_closed_errors`, and arbitrary `runbook_outline` values could pass.
2. Policy metadata exceptions were too broad: extra secret-shaped/raw values under Phase 8 `candidate_contract.forbidden_material` or Phase 9 `artifact_policy.forbidden_material` could pass.

TDD fix path:

```text
RED blocker tests: 2 failed, 6 passed
GREEN focused after fix: 8 passed in 0.37s
```

Fix summary:

- Added exact Phase 8 ordered approval and runbook fixtures to the contract test.
- Added RED cases for duplicate approvals, wrong/unsafe runbook entries, bogus Phase 8 fail-closed errors, and extra unsafe forbidden-material entries.
- Tightened `controlled_shadow_design.py` to require exact Phase 8 approval/runbook/fail-closed/forbidden-material lists.
- Replaced broad policy-value sanitizer skip with path-aware allowlists that only exempt known legitimate policy names while still scanning unknown extras.

Fresh verification after blocker fix:

```text
FOCUSED_PHASE9: 8 passed in 0.38s
PHASE8_COMPAT: 9 passed in 0.38s
PROTOTYPE_REGRESSION: 135 passed in 0.65s
INTEGRATION_REGRESSION: 38 passed in 1.82s
python -m py_compile: PASS
ruff: All checks passed!
git diff --check: PASS
changed-file allowlist: PASS
production-surface guard: PASS
required marker scan: PASS
added-line/new-file secret-shaped scan: PASS
```

A combined prototype regression command with guessed file names produced `no tests ran`; that result was explicitly discarded and replaced with the actual `tests/prototypes/test_flowweaver_phase*.py` run above.

Pending final gate:

- Codex blocker-only re-review of the two fixed blockers and adjacent sanitizer/report-contract regressions.

Codex blocker-only re-review result:

```text
VERDICT: PASS
BLOCKERS: none
NON_BLOCKING_NOTES:
- Legitimate policy metadata names still pass, extra unsafe forbidden-material values are rejected, and raw allowed_fields fails with artifact_policy_violation.
- Integration changes remain narrow allowlist additions; no production/Gateway/Temporal lifecycle surface was added.
```
