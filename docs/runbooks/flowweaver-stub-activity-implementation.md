# FlowWeaver Stub Activity Implementation Runbook

Phase 29 defines plain synchronous, non-production callable stubs for the future FlowWeaver Activity units. The functions validate canonical safe inputs and return deterministic sanitized stub results only.

The Phase 29 verdict is:

```text
ready_for_local_temporal_stub_activity_orchestration
```

This means a later phase may request separate approval to wrap the stubs in local Temporal Activity orchestration. It does not enable production behavior.

## Usage

```python
from gateway.flowweaver_stub_activity_implementation import (
    build_flowweaver_stub_activity_implementation_report,
    deliver_artifact,
    describe_flowweaver_stub_activity_implementation_contract,
    execute_agent_turn,
    validate_claim_check_ref,
    validate_flowweaver_stub_activity_implementation_report,
)
```

Inputs for the implementation report builder:

- a Phase 28 stub Activity implementation validation descriptor;
- a Phase 28 stub Activity implementation validation report.

The P29 builder validates both inputs and returns only high-level implementation metadata. It must not echo the full P28 descriptor, P28 report, execution request, raw message text, tool output, card JSON, media path, platform/private IDs, callback payloads, credentials, or raw exception text.

## Callable Stubs

```text
validate_claim_check_ref -> execute_agent_turn -> deliver_artifact
```

`validate_claim_check_ref` validates a safe claim-check ref shape and returns:

```text
activity, status, claim_ref, error_code, side_effects
```

`execute_agent_turn` returns a stubbed artifact reference and does not execute a real agent or tool.

`deliver_artifact` returns a planned delivery reference and does not render, send, edit, callback, or update delivery ACKs.

## Hard Boundaries

- No Temporal SDK imports.
- No `Client`, `Worker`, `WorkflowEnvironment`, `@activity.defn`, `workflow.execute_activity`, retry objects, timeout SDK objects, or task queues.
- No `@activity.defn` wrappers; Phase 29 functions are plain Python stubs only.
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

## Error Behavior

Invalid Phase 28 contract descriptors return:

```text
invalid_phase28_stub_activity_implementation_validation_contract
```

Invalid Phase 28 validation reports, including valid Phase 28 error-report shapes, return:

```text
invalid_phase28_stub_activity_implementation_validation_report
```

Invalid callable stub inputs return sanitized per-activity result codes such as:

```text
invalid_claim_ref
noncanonical_claim_kind
invalid_agent_activity_input
invalid_delivery_activity_input
unsafe_material
```

Errors are sanitized and must not echo raw user, platform, credential, callback, media, card, tool, or exception material.

## Verification

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_implementation.py -q
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```
