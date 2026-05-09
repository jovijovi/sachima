# FlowWeaver Phase 26 — Stub Activity Boundary Contract Validation

## Goal

Validate the Phase 25 stub Activity boundary contract before any implementation design or runtime wiring starts.

## Architecture

Phase 26 consumes a caller-provided Phase 25 boundary contract descriptor and a caller-provided Phase 25 boundary contract report. It validates those exact prior artifacts, checks that the descriptor/report pair is internally consistent, and returns a sanitized validation report only.

Phase 26 is validation only. It does not create Temporal Activities, execute Activities, call an agent, call tools, render or send Gateway output, update delivery ACKs, or own any runtime lifecycle.

## Scope

Phase 26 creates only:

- `gateway/flowweaver_stub_activity_boundary_contract_validation.py`
- `tests/gateway/test_flowweaver_stub_activity_boundary_contract_validation.py`
- `docs/runbooks/flowweaver-stub-activity-boundary-contract-validation.md`
- this plan and the paired dev log
- changed-file allowlist maintenance in existing FlowWeaver guard tests only if required

The strongest allowed verdict is:

```text
ready_for_stub_activity_implementation_design
```

That verdict means a later phase may design the stub Activity implementation. It does not approve real Activity implementation, Temporal SDK wiring, agent/tool execution, Gateway delivery, ACK control, production config writes, service lifecycle, or restart.

## Entry Points

```python
def describe_flowweaver_stub_activity_boundary_contract_validation_contract() -> dict[str, object]: ...
def validate_flowweaver_stub_activity_boundary_contract_validation_report(value: object) -> dict[str, object]: ...
def build_flowweaver_stub_activity_boundary_contract_validation_report(*, boundary_contract_descriptor: object, boundary_contract_report: object) -> dict[str, object]: ...
```

## Validation Rules

P26 must verify:

- the Phase 25 boundary contract descriptor exactly matches the producer shape;
- the Phase 25 boundary contract report exactly validates through the Phase 25 validator;
- the consumed Phase 25 verdict is `ready_for_stub_activity_boundary_contract_validation`;
- Phase 25 descriptor/report activity interfaces, payload policy, and execution policy agree exactly;
- the P26 report has exact top-level fields and ordered nested lists;
- the P26 report summarizes only sanitized metadata, not full prior artifacts;
- all side-effect lists are empty;
- errors fail closed to sanitized report codes;
- a valid Phase 25 error report is handled explicitly and converted to a sanitized P26 error report instead of indexing success-only fields;
- no full prior report, execution request, raw prompt/message/tool/card/media/platform/private id/callback/credential/raw exception material is echoed.

## Boundary Rules

- No Temporal SDK imports.
- No `Client`, `Worker`, `WorkflowEnvironment`, `@activity.defn`, `workflow.execute_activity`, retry objects, or timeout SDK objects.
- No call to `build_flowweaver_stub_activity_boundary_contract_report`.
- No call to `build_flowweaver_stub_activity_orchestration_validation_report`.
- No call to `orchestrate_flowweaver_stub_activities`.
- No prototype imports; Phase 5J is historical evidence only.
- No Gateway hook changes.
- No Gateway adapter access or mutation.
- No production config writes.
- No Gateway restart requirement.
- No real Temporal Activity execution.
- No real agent or tool execution.
- No real delivery ACK updates.
- No real send/edit/render/callback control.
- No file, subprocess, socket, Docker, daemon, external service, or service startup.
- No logs or prints.
- No raw prompt/message/tool/card/media/platform/private id/callback/credential/raw exception material in outputs, fixtures, reports, docs, or user-visible output.

## Acceptance

Phase 26 is accepted only if:

- RED/GREEN tests prove the validation module was absent before implementation and then passes;
- the builder accepts exact caller-provided P25 descriptor/report and returns only sanitized high-level validation metadata;
- malformed P25 descriptor/report inputs fail closed without echoing raw material;
- interface consistency, payload policy, execution policy, side-effect, and no-escape gates are covered by tests;
- source scans prove no runtime lifecycle, real execution, Gateway wiring, prototype import, or builder/orchestrator escape hatch;
- local FlowWeaver verification passes;
- Codex blocker review returns PASS;
- PR CI is green and merged.

## Verification

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_boundary_contract_validation.py -q
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```
