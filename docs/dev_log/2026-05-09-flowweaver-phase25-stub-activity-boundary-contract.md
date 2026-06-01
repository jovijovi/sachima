# Dev Log — FlowWeaver Phase 25 Stub Activity Boundary Contract

## Scope

Approved phase: Phase 25 (P25).

Implementation branch/worktree:

```text
feat/flowweaver-phase25-stub-activity-boundary-contract
/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase25-stub-activity-boundary-contract
```

## Guardrails

Strongest allowed verdict:

```text
ready_for_stub_activity_boundary_contract_validation
```

- No Temporal SDK imports.
- No `Client`, `Worker`, `WorkflowEnvironment`, `@activity.defn`, `workflow.execute_activity`, retry objects, or timeout SDK objects.
- No call to `orchestrate_flowweaver_stub_activities`.
- No call to `build_flowweaver_stub_activity_orchestration_validation_report`.
- No prototype imports; Phase 5J is historical evidence only.
- No Gateway hook changes.
- No platform adapter mutation/access.
- No production config writes.
- No Gateway restart requirement.
- No real Temporal Activity execution.
- No real agent or tool execution.
- No real delivery ACK updates.
- No real send/edit/render/callback control.
- No file, subprocess, socket, Docker, daemon, external service, or service startup.
- No logs or prints.
- No raw prompt/message/tool/card/media/platform/private id/callback/credential/raw exception material in outputs, logs, fixtures, reports, docs, or user-visible output.

## Codex Scope Precheck

Codex read-only architecture/scope review returned:

```text
VERDICT: PASS
BLOCKERS:
- none
```

Recommended P25 scope:

- pure synchronous `gateway/flowweaver_stub_activity_boundary_contract.py` design/report module;
- consume caller-provided exact Phase 24 validation contract + report;
- return sanitized metadata for future `validate_claim_check_ref`, `execute_agent_turn`, and `deliver_artifact` Activity interfaces;
- freeze field lists, allowed statuses/error codes, claim-check-only payload policy, metadata-only timeout/retry policy, separate approvals, and forbidden side effects;
- do not create runtime Activity functions.

## RED Evidence

Initial RED command:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_boundary_contract.py -q
```

Result:

```text
ModuleNotFoundError: No module named 'gateway.flowweaver_stub_activity_boundary_contract'
```

This proved the new P25 boundary contract module was absent before implementation.

## GREEN Evidence

Focused P25 test:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_boundary_contract.py -q
```

Result:

```text
33 passed in 1.61s
```

Codex blocker review later found one fail-closed gap: a syntactically valid Phase 24 error report was accepted by the Phase 24 validator but lacked `verdict`, causing P25 to raise `KeyError` instead of returning a sanitized error report. Added RED regression and fixed it.

Focused P25 retest after blocker fix:

```text
test_phase25_rejects_phase24_error_report_with_sanitized_error_report => 1 passed
full P25 focused file => 34 passed
```

## Verification Log

FlowWeaver gateway regression slice:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```

Result:

```text
489 passed in 4.81s
```

Static/local checks:

```text
python -m py_compile targeted changed Python files => pass
python -m ruff check targeted changed Python files => pass
警告：pyproject 顶层 ruff linter settings deprecated；这是既有配置警告，不是 P25 新失败。
git diff --cached --check => pass
staged added-line security scan => pass
```

## Review / Safety Gate

Initial Codex blocker review returned:

```text
VERDICT: BLOCK
BLOCKERS:
1. Phase 24 error-report shape was accepted by the upstream validator but lacked success-only `verdict`; P25 raised `KeyError` instead of returning sanitized `invalid_phase24_validation_report`.
```

Fix:

- Added `test_phase25_rejects_phase24_error_report_with_sanitized_error_report`.
- Confirmed RED before fix.
- Updated P25 builder to reject non-success Phase 24 reports before indexing success-only fields.

Blocker-only Codex re-review returned:

```text
VERDICT: PASS
BLOCKERS:
- none
```
