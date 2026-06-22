# FlowWeaver Phase 28 — Stub Activity Implementation Validation

## Goal

Validate the Phase 27 stub Activity implementation design and produce a sanitized readiness report for a later, separately approved stub Activity implementation phase.

## Architecture

Phase 28 consumes a caller-provided Phase 27 implementation design contract descriptor and a caller-provided Phase 27 implementation design report. It validates those exact prior artifacts and returns sanitized validation metadata only.

Phase 28 is validation only. It does not define callable Activities, execute Activities, import Temporal SDK APIs, call an agent, call tools, render or send Gateway output, update delivery ACKs, write config, restart services, or own runtime lifecycle.

## Scope

Phase 28 creates only:

- `gateway/flowweaver_stub_activity_implementation_validation.py`
- `tests/gateway/test_flowweaver_stub_activity_implementation_validation.py`
- `docs/runbooks/flowweaver-stub-activity-implementation-validation.md`
- this plan and the paired dev log
- changed-file allowlist maintenance in existing FlowWeaver guard tests only if required

The strongest allowed verdict is:

```text
ready_for_separately_approved_stub_activity_implementation
```

That verdict means a later phase may request separate approval to implement non-production stub Activity functions. It does not approve Temporal SDK wiring, worker lifecycle, real agent/tool execution, Gateway delivery, ACK control, production config writes, service lifecycle, restart, or production behavior.

## Entry Points

```python
def describe_flowweaver_stub_activity_implementation_validation_contract() -> dict[str, object]: ...
def validate_flowweaver_stub_activity_implementation_validation_report(value: object) -> dict[str, object]: ...
def build_flowweaver_stub_activity_implementation_validation_report(*, implementation_design_contract_descriptor: object, implementation_design_report: object) -> dict[str, object]: ...
```

## Validation Content

The P28 report records only:

- P28 type/version/verdict;
- consumed Phase 27 verdict;
- exact activity design unit names;
- sanitized validation summary;
- exact boolean checks;
- stable error code on failure;
- `side_effects: []`.

## Validation Rules

P28 must verify:

- the Phase 27 implementation design contract descriptor exactly matches the producer shape;
- the Phase 27 implementation design report exactly validates through the Phase 27 validator;
- the consumed Phase 27 verdict is `ready_for_stub_activity_implementation_validation`;
- the activity design unit names are exactly `validate_claim_check_ref`, `execute_agent_turn`, `deliver_artifact`;
- the implementation policy remains `design_only_no_callable_activities`;
- the verification policy remains `metadata_static_validation_only`;
- all side-effect lists are empty;
- errors fail closed to sanitized report codes;
- valid Phase 27 error reports are converted to sanitized P28 error reports instead of indexing success-only fields;
- every dict key gate uses exact key validation before canonical reads;
- no full prior report, execution request, raw prompt/message/tool/card/media/platform/private id/callback/credential/raw exception material is echoed.

## Boundary Rules

- No Temporal SDK imports.
- No `Client`, `Worker`, `WorkflowEnvironment`, `@activity.defn`, `workflow.execute_activity`, retry objects, or timeout SDK objects.
- No callable implementation of `validate_claim_check_ref`, `execute_agent_turn`, or `deliver_artifact`; those names may appear only as sanitized metadata.
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
- No file, subprocess, socket, Docker, daemon, external service, or service startup.
- No logs or prints.
- No raw prompt/message/tool/card/media/platform/private id/callback/credential/raw exception material in outputs, fixtures, reports, docs, or user-visible output.

## Acceptance

Phase 28 is accepted only if:

- RED/GREEN tests prove the validation module was absent before implementation and then passes;
- the builder accepts exact caller-provided P27 descriptor/report and returns only sanitized high-level validation metadata;
- malformed P27 descriptor/report inputs fail closed without echoing raw material;
- valid P27 error reports are rejected as sanitized P28 error reports;
- exact-key, hostile-subclass, no-escape, side-effect, and report-shape gates are covered by tests;
- source scans prove no runtime lifecycle, real execution, Gateway wiring, prototype import, callable Activity definitions, or builder/orchestrator escape hatch;
- local FlowWeaver verification passes;
- Codex blocker review returns PASS;
- PR CI is green and merged.

## Verification

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_implementation_validation.py -q
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```
