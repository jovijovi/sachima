# FlowWeaver Phase 25 — Stub Activity Boundary Contract

## Goal

Define a pure synchronous boundary contract for future stub Activity interfaces after the Phase 24 validation gate.

## Architecture

Phase 25 consumes a caller-provided Phase 24 validation contract descriptor and a caller-provided Phase 24 validation report. It validates those exact prior artifacts, then returns sanitized metadata describing the future Activity boundary for `validate_claim_check_ref`, `execute_agent_turn`, and `deliver_artifact`.

Phase 25 is contract design only. It does not create Temporal Activities, execute Activities, call an agent, call tools, render or send Gateway output, update delivery ACKs, or own any runtime lifecycle.

## Scope

Phase 25 creates only:

- `gateway/flowweaver_stub_activity_boundary_contract.py`
- `tests/gateway/test_flowweaver_stub_activity_boundary_contract.py`
- `docs/runbooks/flowweaver-stub-activity-boundary-contract.md`
- this plan and the paired dev log
- changed-file allowlist maintenance in existing FlowWeaver guard tests only if required

The strongest allowed verdict is:

```text
ready_for_stub_activity_boundary_contract_validation
```

That verdict means a later phase may validate this boundary contract. It does not approve real Activity implementation, Temporal SDK wiring, agent/tool execution, Gateway delivery, ACK control, production config writes, service lifecycle, or restart.

## Entry Points

```python
def describe_flowweaver_stub_activity_boundary_contract() -> dict[str, object]: ...
def validate_flowweaver_stub_activity_boundary_contract_report(value: object) -> dict[str, object]: ...
def build_flowweaver_stub_activity_boundary_contract_report(*, validation_contract_descriptor: object, validation_report: object) -> dict[str, object]: ...
```

## Contract Content

The Phase 25 report must freeze metadata for these future interfaces:

```text
validate_claim_check_ref
execute_agent_turn
deliver_artifact
```

Each interface must define:

- exact input field names;
- exact result field names;
- allowed statuses;
- stable error codes;
- claim-check/reference-only payload policy;
- metadata-only timeout and retry policy labels;
- `side_effects: []`.

## Validation Rules

P25 must verify:

- the Phase 24 validation contract descriptor exactly matches the producer shape;
- the Phase 24 validation report exactly validates through the Phase 24 validator;
- the consumed Phase 24 verdict is `ready_for_stub_activity_boundary_contract_design`;
- the boundary report has exact top-level fields and ordered nested lists;
- each Activity interface is exact and sanitized;
- payload policy permits only canonical references and safe ids, not raw payload material;
- execution policy is metadata only and cannot instantiate SDK retry/timeout objects;
- all side-effect lists are empty;
- errors fail closed to sanitized report codes;
- no full prior report, execution request, raw prompt/message/tool/card/media/platform/private id/callback/credential/raw exception material is echoed.

## Boundary Rules

- No Temporal SDK imports.
- No `Client`, `Worker`, `WorkflowEnvironment`, `@activity.defn`, `workflow.execute_activity`, retry objects, or timeout SDK objects.
- No call to `orchestrate_flowweaver_stub_activities`.
- No call to `build_flowweaver_stub_activity_orchestration_validation_report`.
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

Phase 25 is accepted only if:

- RED/GREEN tests prove the module was absent before implementation and then passes;
- the builder accepts exact caller-provided P24 descriptor/report and returns only sanitized high-level boundary metadata;
- malformed P24 descriptor/report inputs fail closed without echoing raw material;
- interface shape, payload policy, execution policy, side-effect, and no-escape gates are covered by tests;
- source scans prove no runtime lifecycle, real execution, Gateway wiring, prototype import, or orchestrator/builder escape hatch;
- local FlowWeaver verification passes;
- Codex blocker review returns PASS;
- PR CI is green and merged.

## Verification

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_boundary_contract.py -q
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```
