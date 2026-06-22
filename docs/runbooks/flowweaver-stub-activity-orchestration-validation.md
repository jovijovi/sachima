# FlowWeaver Stub Activity Orchestration Validation Runbook

## Purpose

Phase 24 validates a caller-provided Phase 23 stub Activity orchestration artifact and returns a sanitized high-level validation report.

The Phase 24 verdict is:

```text
ready_for_stub_activity_boundary_contract_design
```

This means a later phase may design the next stub Activity boundary contract. It does not enable production behavior.

## Current Module

Use:

```python
from gateway.flowweaver_stub_activity_orchestration_validation import (
    build_flowweaver_stub_activity_orchestration_validation_report,
    describe_flowweaver_stub_activity_orchestration_validation_contract,
    validate_flowweaver_stub_activity_orchestration_validation_report,
)
```

The builder consumes:

- a Phase 23 stub Activity orchestration contract descriptor;
- an already-built Phase 23 orchestration result.

The builder does not call the Phase 23 orchestrator. Callers must provide the artifact they want validated.

## Validated Inputs

The validation report checks:

- exact Phase 23 contract descriptor;
- exact Phase 23 orchestration result shape;
- fixed stub sequence: `validate_claim_check_ref`, `execute_agent_turn`, `deliver_artifact`;
- single canonical claim-check input kind `agent_input`;
- `delivery_ack_updates: []`;
- all side-effect lists remain empty;
- no raw/private/credential-shaped material is echoed.

## Outputs

The validation report includes only high-level metadata:

- P24 report type/version/verdict;
- the consumed Phase 23 verdict;
- validated activity names/statuses;
- safe counts for input refs, artifacts, and deliveries;
- boolean checks;
- stable error code on failure;
- `side_effects: []`.

It must not include the full execution request, raw messages, tool outputs, card JSON, media paths, platform/private IDs, callback payloads, credential-shaped values, or raw exception text.

## Boundaries

- No Temporal client construction.
- No Worker lifecycle.
- No `WorkflowEnvironment`.
- No Gateway hook changes.
- No Gateway adapter access or mutation.
- No production config writes.
- No Gateway restart requirement.
- No real Temporal Activity execution.
- No real agent or tool execution.
- No real delivery ACK updates.
- No real send/edit/render/callback control.
- No file, subprocess, socket, Docker, daemon, or service startup.
- No call to `orchestrate_flowweaver_stub_activities` from the P24 production module.

## Verification

Run:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_orchestration_validation.py -q
```

Before PR, also run the relevant FlowWeaver gateway regression slice and Codex blocker review.
