# FlowWeaver Phase 29 — Stub Activity Implementation

## Goal

Implement the three future FlowWeaver Activity units as ordinary synchronous, non-production callable stubs after the Phase 28 implementation validation gate.

## Architecture

Phase 29 consumes a caller-provided Phase 28 implementation validation contract descriptor and a caller-provided Phase 28 implementation validation report. It validates those exact prior artifacts and returns sanitized implementation metadata for plain callable stubs.

Phase 29 adds callable Python functions, but they are not Temporal Activities. They perform strict input validation and return deterministic stub results only.

## Scope

Phase 29 creates only:

- `gateway/flowweaver_stub_activity_implementation.py`
- `tests/gateway/test_flowweaver_stub_activity_implementation.py`
- `docs/runbooks/flowweaver-stub-activity-implementation.md`
- this plan and the paired dev log
- changed-file allowlist maintenance in existing FlowWeaver guard tests only if required

The strongest allowed verdict is:

```text
ready_for_local_temporal_stub_activity_orchestration
```

That verdict means a later Phase 30 may request separate approval to wrap the stubs in local Temporal Activity orchestration. It does not approve Temporal SDK wiring in Phase 29, worker lifecycle, real agent/tool execution, Gateway delivery, ACK control, production config writes, Gateway restart, service lifecycle, or production behavior.

## Entry Points

```python
def describe_flowweaver_stub_activity_implementation_contract() -> dict[str, object]: ...
def validate_flowweaver_stub_activity_implementation_report(value: object) -> dict[str, object]: ...
def build_flowweaver_stub_activity_implementation_report(*, implementation_validation_descriptor: object, implementation_validation_report: object) -> dict[str, object]: ...

def validate_claim_check_ref(*, claim_check_ref: object, policy_descriptor: object) -> dict[str, object]: ...
def execute_agent_turn(*, execution_request: object, validated_claim: object) -> dict[str, object]: ...
def deliver_artifact(*, artifact: object, delivery_plan: object) -> dict[str, object]: ...
```

## Stub Activity Units

The fixed callable stub sequence is:

```text
validate_claim_check_ref
execute_agent_turn
deliver_artifact
```

Each callable returns only sanitized status metadata and `side_effects: []`.

## Validation Rules

P29 must verify:

- the Phase 28 implementation validation contract descriptor exactly matches the producer shape;
- the Phase 28 implementation validation report exactly validates through the Phase 28 validator;
- the consumed Phase 28 verdict is `ready_for_separately_approved_stub_activity_implementation`;
- the callable stub function names exactly match `validate_claim_check_ref`, `execute_agent_turn`, `deliver_artifact`;
- the implementation policy remains `plain_callable_stubs_only`;
- the validation policy remains `exact_inputs_sanitized_stub_outputs`;
- all side-effect lists are empty;
- errors fail closed to sanitized report or stub result codes;
- valid Phase 28 error reports are converted to sanitized P29 error reports instead of indexing success-only fields;
- every dict key gate uses exact key validation before canonical reads;
- no full prior report, execution request, raw prompt/message/tool/card/media/platform/private id/callback/credential/raw exception material is echoed.

## Boundary Rules

- No Temporal SDK imports.
- No `Client`, `Worker`, `WorkflowEnvironment`, `@activity.defn`, `workflow.execute_activity`, retry objects, timeout SDK objects, or task queues.
- No `@activity.defn` wrappers; P29 functions are plain Python stubs only.
- No call to `build_flowweaver_stub_activity_implementation_validation_report`.
- No call to `build_flowweaver_stub_activity_implementation_design_report`.
- No call to `build_flowweaver_stub_activity_boundary_contract_validation_report`.
- No call to `build_flowweaver_stub_activity_boundary_contract_report`.
- No call to `build_flowweaver_stub_activity_orchestration_validation_report`.
- No call to `orchestrate_flowweaver_stub_activities`.
- No prototype imports.
- No Gateway hook changes.
- No Gateway adapter access or mutation.
- No production config writes.
- No Gateway restart requirement.
- No real Temporal Activity execution.
- No real agent or tool execution.
- No real delivery ACK updates.
- No real send/edit/render/callback control.
- No file, claim-check storage, subprocess, socket, Docker, daemon, external service, or service startup.
- No logs or prints.
- No raw prompt/message/tool/card/media/platform/private id/callback/credential/raw exception material in outputs, fixtures, reports, docs, or user-visible output.

## Acceptance

Phase 29 is accepted only if:

- RED/GREEN tests prove the module was absent before implementation and then passes;
- the builder accepts exact caller-provided P28 descriptor/report and returns only sanitized high-level implementation metadata;
- malformed P28 descriptor/report inputs fail closed without echoing raw material;
- valid P28 error reports are rejected as sanitized P29 error reports;
- callable stubs return deterministic safe results for canonical inputs;
- malformed/raw/hostile inputs fail closed with stable sanitized result codes;
- exact-key, hostile-subclass, no-escape, side-effect, and report-shape gates are covered by tests;
- source scans prove no Temporal SDK, Worker lifecycle, Gateway wiring, prototype import, real execution, delivery, ACK, storage, file, subprocess, socket, Docker, daemon, service, log, or print escape hatch;
- local FlowWeaver verification passes;
- Codex blocker review returns PASS;
- PR CI is green and merged.

## Verification

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_implementation.py -q
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```
