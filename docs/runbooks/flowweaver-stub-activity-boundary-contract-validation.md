# FlowWeaver Stub Activity Boundary Contract Validation Runbook

Phase 26 validates the Phase 25 pure synchronous stub Activity boundary contract. It consumes Phase 25 boundary artifacts and returns sanitized validation metadata only.

The Phase 26 verdict is:

```text
ready_for_stub_activity_implementation_design
```

This means a later phase may design the stub Activity implementation. It does not enable production behavior.

## Usage

```python
from gateway.flowweaver_stub_activity_boundary_contract import (
    describe_flowweaver_stub_activity_boundary_contract,
    validate_flowweaver_stub_activity_boundary_contract_report,
)
from gateway.flowweaver_stub_activity_boundary_contract_validation import (
    build_flowweaver_stub_activity_boundary_contract_validation_report,
    describe_flowweaver_stub_activity_boundary_contract_validation_contract,
    validate_flowweaver_stub_activity_boundary_contract_validation_report,
)
```

Inputs:

- a Phase 25 stub Activity boundary contract descriptor;
- a Phase 25 stub Activity boundary contract report.

The P26 builder validates both inputs and returns only high-level validation metadata. It must not echo the full P25 descriptor, P25 report, execution request, raw message text, tool output, card JSON, media path, platform/private IDs, callback payloads, credentials, or raw exception text.

## Validation Surface

The validation report records only:

- P26 report type/version/verdict;
- consumed Phase 25 verdict;
- exact Activity interface names;
- sanitized validation summary;
- exact boolean checks;
- stable error code on failure;
- `side_effects: []`.

## Hard Boundaries

- No Temporal SDK imports.
- No `Client`, `Worker`, `WorkflowEnvironment`, `@activity.defn`, `workflow.execute_activity`, retry objects, or timeout SDK objects.
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

Invalid Phase 25 contract descriptors return:

```text
invalid_phase25_boundary_contract
```

Invalid Phase 25 reports, including valid Phase 25 error-report shapes, return:

```text
invalid_phase25_boundary_contract_report
```

Errors are sanitized and must not echo raw user, platform, credential, callback, media, card, tool, or exception material.

## Verification

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_boundary_contract_validation.py -q
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```
