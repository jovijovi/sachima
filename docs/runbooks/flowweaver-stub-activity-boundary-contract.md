# FlowWeaver Stub Activity Boundary Contract Runbook

## Purpose

Phase 25 defines a pure synchronous contract for future stub Activity interfaces. It consumes Phase 24 validation artifacts and returns sanitized boundary metadata only.

The Phase 25 verdict is:

```text
ready_for_stub_activity_boundary_contract_validation
```

This means a later phase may validate the boundary contract. It does not enable production behavior.

## Current Module

Use:

```python
from gateway.flowweaver_stub_activity_boundary_contract import (
    build_flowweaver_stub_activity_boundary_contract_report,
    describe_flowweaver_stub_activity_boundary_contract,
    validate_flowweaver_stub_activity_boundary_contract_report,
)
```

The builder consumes:

- a Phase 24 stub Activity orchestration validation contract descriptor;
- a Phase 24 validation report.

The builder does not call the Phase 24 report builder and does not call the Phase 23 orchestrator. Callers must provide the artifacts they want validated.

## Boundary Interfaces

P25 freezes metadata for these future Activity interfaces:

```text
validate_claim_check_ref
execute_agent_turn
deliver_artifact
```

For each interface, the contract records exact input fields, result fields, allowed statuses, stable error codes, reference-only payload policy, metadata-only timeout/retry policy, and `side_effects: []`.

## Outputs

The boundary report includes only high-level metadata:

- P25 report type/version/verdict;
- consumed Phase 24 verdict;
- interface names and safe field lists;
- payload policy summary;
- metadata-only execution policy labels;
- stable checks;
- stable error code on failure;
- `side_effects: []`.

It must not include the full Phase 24 report, full execution request, raw messages, tool outputs, card JSON, media paths, platform/private IDs, callback payloads, credential-shaped values, or raw exception text.

## Boundaries

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

## Verification

Run:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_boundary_contract.py -q
```

Before PR, also run the relevant FlowWeaver gateway regression slice and Codex blocker review.
