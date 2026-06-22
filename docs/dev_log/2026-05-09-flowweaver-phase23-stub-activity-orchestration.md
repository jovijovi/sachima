# Dev Log — FlowWeaver Phase 23 Stub Activity Orchestration

## Scope

Approved phase: Phase 23 (P23).

Implementation branch/worktree:

```text
feat/flowweaver-phase23-stub-activity-orchestration
/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase23-stub-activity-orchestration
```

## Guardrails

Strongest allowed verdict:

```text
ready_for_stub_activity_orchestration_validation
```

- No Temporal client construction.
- No Worker lifecycle.
- No Gateway hook changes.
- No platform adapter mutation.
- No production config writes.
- No Gateway restart requirement.
- No real agent or tool execution.
- No real delivery ACK updates; `delivery_ack_updates` must stay `[]`.
- No real send/edit/render/callback control.
- No file, subprocess, socket, Docker, daemon, or service startup.
- No raw prompt/message/tool/card/media/platform/private id/callback/credential/raw exception material in outputs, logs, fixtures, reports, docs, or user-visible output.

## Codex Scope Precheck

Codex read-only architecture/scope review returned:

```text
VERDICT: PASS
BLOCKERS:
- none
```

Key enforced scope from Codex:

- P23 is safe only as a pure synchronous stub orchestration helper.
- Validate the P22 descriptor and `FlowWeaverExecutionRequest` before producing a result.
- Fixed sequence only: `validate_claim_check_ref`, `execute_agent_turn`, `deliver_artifact`.
- Return P22-built `FlowWeaverExecutionResult` and `FlowWeaverProgressSnapshot`.
- Return `delivery_ack_updates: []`.
- Do not modify Gateway hooks, Temporal clients, Workers, real agent/tool execution, real delivery, or ACK control.

## RED Evidence

Initial RED command:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_orchestration.py -q
```

Result:

```text
ModuleNotFoundError: No module named 'gateway.flowweaver_stub_activity_orchestration'
```

This proved the new P23 stub orchestration module was absent before implementation.

## GREEN Evidence

Focused Phase 23 test:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_orchestration.py -q
```

Result:

```text
35 passed in 1.13s
```

FlowWeaver contract/guard neighbor slice:

```bash
scripts/run_tests.sh \
  tests/gateway/test_flowweaver_stub_activity_orchestration.py \
  tests/gateway/test_flowweaver_delivery_agent_execution_contract.py \
  tests/gateway/test_flowweaver_temporal_observation_bridge.py \
  tests/gateway/test_flowweaver_temporal_observation_validation_gate.py \
  tests/gateway/test_flowweaver_production_shadow_observation.py \
  tests/gateway/test_flowweaver_shadow_publisher.py \
  tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py \
  -q
```

Result:

```text
174 passed in 1.62s
```

All FlowWeaver gateway tests plus Phase 5C runtime contract:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```

Result:

```text
420 passed in 3.94s
```

## Verification Log

Additional focused guard probe:

```bash
scripts/run_tests.sh \
  tests/integration/test_flowweaver_phase5h_local_temporal_worker_reconciliation.py \
  tests/integration/test_flowweaver_phase5i_start_signature_parity.py \
  tests/integration/test_flowweaver_phase5j_activity_claim_check_boundary.py \
  tests/integration/test_flowweaver_phase5k_runtime_control_surface.py \
  tests/prototypes/test_flowweaver_phase5c_tool_surface.py \
  -q
```

Result:

```text
3 passed in 1.35s
```

Static/local checks:

```text
python -m py_compile targeted changed Python files => pass
python -m ruff check targeted changed Python files => pass
警告：pyproject 顶层 ruff linter settings deprecated；这是既有配置警告，不是 P23 新失败。
git diff --check => pass
staged added-line security scan => pass
```

## Review / Safety Gate

Final Codex blocker review initially returned `BLOCK` because `_validate_single_stub_request` accepted a P22-valid but noncanonical claim-check `kind` such as `message text`, which could then be echoed inside `execution_request`.

Blocker fix:

- added a RED regression for `kind: message text` proving the pre-fix code did not raise;
- tightened P23 stub request validation so the single claim-check input kind must be exactly `agent_input`;
- documented the canonical input-kind boundary in the plan and runbook.

Fix verification:

```text
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_orchestration.py::test_phase23_rejects_p22_valid_noncanonical_claim_kind_without_echoing_value -q
=> 1 passed in 1.07s

scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_orchestration.py -q
=> 36 passed in 1.14s
```

Codex blocker-only re-review after the fix returned:

```text
VERDICT: PASS
BLOCKERS:
- none
NOTES:
- none
```
