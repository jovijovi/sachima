# FlowWeaver Stub Activity Implementation Design Runbook

Phase 27 defines a pure synchronous design for future stub Activity implementation units. It consumes Phase 26 boundary validation artifacts and returns sanitized design metadata only.

The Phase 27 verdict is:

```text
ready_for_stub_activity_implementation_validation
```

This means a later phase may validate the stub Activity implementation design. It does not enable production behavior.

## Usage

```python
from gateway.flowweaver_stub_activity_boundary_contract_validation import (
    describe_flowweaver_stub_activity_boundary_contract_validation_contract,
    validate_flowweaver_stub_activity_boundary_contract_validation_report,
)
from gateway.flowweaver_stub_activity_implementation_design import (
    build_flowweaver_stub_activity_implementation_design_report,
    describe_flowweaver_stub_activity_implementation_design_contract,
    validate_flowweaver_stub_activity_implementation_design_report,
)
```

Inputs:

- a Phase 26 stub Activity boundary contract validation descriptor;
- a Phase 26 stub Activity boundary contract validation report.

The P27 builder validates both inputs and returns only high-level implementation design metadata. It must not echo the full P26 descriptor, P26 report, execution request, raw message text, tool output, card JSON, media path, platform/private IDs, callback payloads, credentials, or raw exception text.

## Design Surface

The design report records only:

- P27 report type/version/verdict;
- consumed Phase 26 verdict;
- exact future stub Activity implementation unit names;
- sanitized implementation policy;
- sanitized verification policy;
- exact boolean checks;
- stable error code on failure;
- `side_effects: []`.

## Hard Boundaries

- No Temporal SDK imports.
- No `Client`, `Worker`, `WorkflowEnvironment`, `@activity.defn`, `workflow.execute_activity`, retry objects, or timeout SDK objects.
- No callable implementation of `validate_claim_check_ref`, `execute_agent_turn`, or `deliver_artifact`; those names may appear only as sanitized metadata.
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

Invalid Phase 26 contract descriptors return:

```text
invalid_phase26_boundary_contract_validation_contract
```

Invalid Phase 26 validation reports, including valid Phase 26 error-report shapes, return:

```text
invalid_phase26_boundary_contract_validation_report
```

Errors are sanitized and must not echo raw user, platform, credential, callback, media, card, tool, or exception material.

## Verification

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_implementation_design.py -q
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```
