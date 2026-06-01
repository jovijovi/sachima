# FlowWeaver Phase 27 — Stub Activity Implementation Design

## Goal

Design the future stub Activity implementation shape after the Phase 26 boundary validation gate, without implementing callable Activities or runtime behavior.

## Architecture

Phase 27 consumes a caller-provided Phase 26 boundary contract validation descriptor and a caller-provided Phase 26 validation report. It validates those exact prior artifacts and returns sanitized metadata describing how a later, separately approved phase may implement stub Activity functions for `validate_claim_check_ref`, `execute_agent_turn`, and `deliver_artifact`.

Phase 27 is design only. It does not define Temporal Activities, execute Activities, call an agent, call tools, render or send Gateway output, update delivery ACKs, or own any runtime lifecycle.

## Scope

Phase 27 creates only:

- `gateway/flowweaver_stub_activity_implementation_design.py`
- `tests/gateway/test_flowweaver_stub_activity_implementation_design.py`
- `docs/runbooks/flowweaver-stub-activity-implementation-design.md`
- this plan and the paired dev log
- changed-file allowlist maintenance in existing FlowWeaver guard tests only if required

The strongest allowed verdict is:

```text
ready_for_stub_activity_implementation_validation
```

That verdict means a later phase may validate the stub Activity implementation design. It does not approve real Activity implementation, Temporal SDK wiring, worker lifecycle, agent/tool execution, Gateway delivery, ACK control, production config writes, service lifecycle, or restart.

## Entry Points

```python
def describe_flowweaver_stub_activity_implementation_design_contract() -> dict[str, object]: ...
def validate_flowweaver_stub_activity_implementation_design_report(value: object) -> dict[str, object]: ...
def build_flowweaver_stub_activity_implementation_design_report(*, boundary_contract_validation_descriptor: object, boundary_contract_validation_report: object) -> dict[str, object]: ...
```

## Design Content

The P27 report must freeze sanitized design metadata for future implementation units:

```text
validate_claim_check_ref
execute_agent_turn
deliver_artifact
```

Each design unit must define:

- exact activity name;
- implementation mode label, not callable code;
- accepted input and result field names;
- allowed statuses and stable error codes;
- claim-check/reference-only payload policy;
- no real agent/tool/Gateway/ACK effects;
- `side_effects: []`.

## Validation Rules

P27 must verify:

- the Phase 26 validation contract descriptor exactly matches the producer shape;
- the Phase 26 validation report exactly validates through the Phase 26 validator;
- the consumed Phase 26 verdict is `ready_for_stub_activity_implementation_design`;
- the design unit names exactly match the validated Phase 26 activity interface names;
- the P27 report has exact top-level fields and ordered nested lists;
- the P27 report summarizes only sanitized metadata, not full prior artifacts;
- all side-effect lists are empty;
- errors fail closed to sanitized report codes;
- a valid Phase 26 error report is handled explicitly and converted to a sanitized P27 error report instead of indexing success-only fields;
- every dict key gate uses exact key validation before canonical reads;
- no full prior report, execution request, raw prompt/message/tool/card/media/platform/private id/callback/credential/raw exception material is echoed.

## Boundary Rules

- No Temporal SDK imports.
- No `Client`, `Worker`, `WorkflowEnvironment`, `@activity.defn`, `workflow.execute_activity`, retry objects, or timeout SDK objects.
- No callable implementation of `validate_claim_check_ref`, `execute_agent_turn`, or `deliver_artifact`; those names may appear only as sanitized metadata.
- No call to `build_flowweaver_stub_activity_boundary_contract_validation_report`.
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

Phase 27 is accepted only if:

- RED/GREEN tests prove the design module was absent before implementation and then passes;
- the builder accepts exact caller-provided P26 descriptor/report and returns only sanitized high-level design metadata;
- malformed P26 descriptor/report inputs fail closed without echoing raw material;
- interface design, implementation policy, verification policy, side-effect, exact-key, and no-escape gates are covered by tests;
- source scans prove no runtime lifecycle, real execution, Gateway wiring, prototype import, callable Activity definitions, or builder/orchestrator escape hatch;
- local FlowWeaver verification passes;
- Codex blocker review returns PASS;
- PR CI is green and merged.

## Verification

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_implementation_design.py -q
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```
