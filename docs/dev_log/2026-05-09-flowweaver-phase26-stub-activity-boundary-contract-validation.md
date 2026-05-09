# Dev Log — FlowWeaver Phase 26 Stub Activity Boundary Contract Validation

## Scope

Approved phase: Phase 26 (P26).

Implementation branch/worktree:

```text
feat/flowweaver-phase26-stub-activity-boundary-contract-validation
/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase26-stub-activity-boundary-contract-validation
```

## Guardrails

Strongest allowed verdict:

```text
ready_for_stub_activity_implementation_design
```

- No Temporal SDK imports.
- No `Client`, `Worker`, `WorkflowEnvironment`, `@activity.defn`, `workflow.execute_activity`, retry objects, or timeout SDK objects.
- No call to `build_flowweaver_stub_activity_boundary_contract_report`.
- No call to `build_flowweaver_stub_activity_orchestration_validation_report`.
- No call to `orchestrate_flowweaver_stub_activities`.
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

Recommended P26 scope:

- pure synchronous `gateway/flowweaver_stub_activity_boundary_contract_validation.py` validation/report module;
- consume caller-provided exact Phase 25 boundary contract descriptor + report;
- return sanitized metadata for boundary contract validation only;
- explicitly reject valid Phase 25 error-report shapes before indexing success-only fields;
- do not create runtime Activity functions or call P25/P24 builders/orchestrators.

## RED Evidence

Initial RED command:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_boundary_contract_validation.py -q
```

Result:

```text
ModuleNotFoundError: No module named 'gateway.flowweaver_stub_activity_boundary_contract_validation'
```

This proved the new P26 boundary contract validation module was absent before implementation.

## GREEN Evidence

Focused P26 test:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_boundary_contract_validation.py -q
```

Result:

```text
41 passed in 1.22s
```

One initial GREEN run exposed a test-harness issue: plain `dict` cannot represent duplicated top-level fields. The duplicated-top-level case was removed from that one parametrization; duplicate-list coverage remains in descriptor/report nested list tests.

## Verification Log

FlowWeaver gateway regression slice:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```

Result:

```text
532 passed in 4.89s
```

Static/local checks:

```text
python -m py_compile targeted changed Python files => pass
python -m ruff check targeted changed Python files => pass
warning: pyproject top-level ruff settings are deprecated; existing config warning, not a P26 failure.
git diff --check => pass
added-line security scan => pass
```

## Review / Safety Gate

Initial Codex blocker review returned:

```text
VERDICT: BLOCK
BLOCKERS:
1. P26 used normal equality for dict key exactness, allowing hostile str-subclass keys to pass validation before exact primitive checks.
```

Fix:

- Added hostile key RED regressions for P26 validation report keys and caller-provided P25 descriptor/report keys.
- Replaced dict key gates with exact key validation: length/order plus `type(key) is str` before canonical-key reads.
- Added plain-tree precheck before delegating caller-provided P25 reports to the P25 validator.

First blocker-only Codex re-review returned a narrower blocker:

```text
VERDICT: BLOCK
BLOCKERS:
1. The P26 error-report branch still used list equality before exact-key validation.
```

Fix:

- Added an exploding-key RED regression for the P26 error-report branch.
- Routed the error-report branch through the same exact-key helper.

Second blocker-only Codex re-review returned:

```text
VERDICT: PASS
BLOCKERS:
- none
NOTES:
- none
```
