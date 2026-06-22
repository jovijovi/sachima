# FlowWeaver Stub Activity Implementation Validation Runbook

Phase 28 defines a pure synchronous validation gate for the Phase 27 stub Activity implementation design. It consumes Phase 27 design artifacts and returns sanitized validation metadata only.

The Phase 28 verdict is:

```text
ready_for_separately_approved_stub_activity_implementation
```

This means a later phase may request separate approval to implement stub Activity functions. It does not enable production behavior.

## Usage

```python
from gateway.flowweaver_stub_activity_implementation_design import (
    describe_flowweaver_stub_activity_implementation_design_contract,
    validate_flowweaver_stub_activity_implementation_design_report,
)
from gateway.flowweaver_stub_activity_implementation_validation import (
    build_flowweaver_stub_activity_implementation_validation_report,
    describe_flowweaver_stub_activity_implementation_validation_contract,
    validate_flowweaver_stub_activity_implementation_validation_report,
)
```

Inputs:

- a Phase 27 stub Activity implementation design descriptor;
- a Phase 27 stub Activity implementation design report.

The P28 builder validates both inputs and returns only high-level validation metadata. It must not echo the full P27 descriptor, P27 report, execution request, raw message text, tool output, card JSON, media path, platform/private IDs, callback payloads, credentials, or raw exception text.

## Validation Surface

The validation report records only:

- P28 report type/version/verdict;
- consumed Phase 27 verdict;
- exact future stub Activity design unit names;
- sanitized validation summary;
- exact boolean checks;
- stable error code on failure;
- `side_effects: []`.

## Hard Boundaries

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

## Error Behavior

Invalid Phase 27 contract descriptors return:

```text
invalid_phase27_stub_activity_implementation_design_contract
```

Invalid Phase 27 design reports, including valid Phase 27 error-report shapes, return:

```text
invalid_phase27_stub_activity_implementation_design_report
```

Errors are sanitized and must not echo raw user, platform, credential, callback, media, card, tool, or exception material.

## Verification

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_implementation_validation.py -q
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```
