# FlowWeaver Stub Activity Orchestration Runbook

## Purpose

Phase 23 defines a pure synchronous stub orchestration boundary for future delivery / agent execution work.

The Phase 23 verdict is:

```text
ready_for_stub_activity_orchestration_validation
```

This means a later phase may validate the stub orchestration helper. It does not enable production behavior.

## Current Module

Use:

```python
from gateway.flowweaver_stub_activity_orchestration import (
    describe_flowweaver_stub_activity_orchestration_contract,
    orchestrate_flowweaver_stub_activities,
    validate_flowweaver_stub_activity_orchestration_result,
)
```

The helper consumes the Phase 22 contract descriptor and a `FlowWeaverExecutionRequest`, then returns sanitized stub metadata only.

## Stub Sequence

```text
validate_claim_check_ref
execute_agent_turn
deliver_artifact
```

All three entries are planned/stubbed metadata. Phase 23 does not execute Temporal Activities, Hermes Agent turns, tools, Gateway delivery, or delivery acknowledgements.

## Outputs

The orchestration result includes:

- a fixed activity sequence;
- a safe canonical `FlowWeaverExecutionRequest` copy whose single claim-check input kind is `agent_input`;
- a P22-built `FlowWeaverExecutionResult`;
- a P22-built `FlowWeaverProgressSnapshot`;
- `delivery_ack_updates: []`;
- stable checks and forbidden-side-effect metadata;
- `side_effects: []`.

## Boundaries

- No Temporal client construction.
- No Worker lifecycle.
- No Gateway hook changes.
- No Gateway adapter access or mutation.
- No production config writes.
- No Gateway restart requirement.
- No real agent or tool execution.
- No real delivery ACK updates; `delivery_ack_updates` must remain empty.
- No real send/edit/render/callback control.
- No file, subprocess, socket, Docker, daemon, or service startup.
- No raw prompt, message text, tool output, card JSON, media path, platform/private id, callback payload, credential-shaped value, or raw exception text in returned objects, logs, fixtures, reports, docs, or user-visible output.

## Verification

Run:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_stub_activity_orchestration.py -q
```

Before PR, also run the relevant FlowWeaver gateway regression slice and Codex blocker review.
