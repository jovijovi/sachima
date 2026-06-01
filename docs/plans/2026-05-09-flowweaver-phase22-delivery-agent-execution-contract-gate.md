# FlowWeaver Phase 22 — Delivery / Agent Execution Contract Gate

## Goal

Freeze the boundary between Temporal-owned orchestration, Hermes Agent execution, and Gateway delivery before Phase 23 adds stub Activity orchestration.

## Scope

Phase 22 creates a pure contract gate only:

- `gateway/flowweaver_delivery_agent_execution_contract.py`
- `tests/gateway/test_flowweaver_delivery_agent_execution_contract.py`
- `docs/runbooks/flowweaver-delivery-agent-execution-contract.md`
- this plan and the paired dev log

The strongest allowed verdict is:

```text
ready_for_stub_activity_orchestration
```

That verdict is weaker than production activation. It only means Phase 23 may add stub Activity orchestration in a separate PR.

## Contract Objects

Phase 22 freezes exact ordered fields for:

- `FlowWeaverExecutionRequest`
- `FlowWeaverExecutionResult`
- `FlowWeaverDeliveryAckUpdate`
- `FlowWeaverProgressSnapshot`

The contract requires exact list order. Missing, extra, reordered, duplicated, and bogus values in contract lists are rejected by tests.

## Boundary Rules

- No runtime Worker/service lifecycle.
- No Gateway hook changes.
- No production config writes.
- No real agent execution.
- No real delivery ACK updates.
- No Temporal client, Gateway adapter, file write, subprocess, socket, service, render, send, edit, or callback control.
- Claim-check references only for future raw material.
- Raw field names may appear only inside explicit policy metadata such as `forbidden_material`; raw values must not appear in returned contract objects.

## Canonical IDs

- `transaction_id` is the canonical runtime transaction identifier.
- `workflow_id` is only a transport alias and must equal `transaction_id` in Phase 22 objects.
- `runtime_intent_0`, `runtime_delivery_0`, and `runtime_artifact_0` use strict unpadded numeric suffixes.
- Padded aliases such as `runtime_delivery_00` are rejected.

## Separate Approvals Required

These are not approved by Phase 22 and need separate 狗哥 approval:

- live config writes
- Gateway restart
- production enablement
- real send/edit/render/callback control
- real agent/tool execution

## Acceptance

Phase 22 is accepted only if:

- contract module remains pure and synchronous;
- RED/GREEN tests cover exact contract lists, raw-value rejection, canonical ID aliases, and docs approvals;
- local verification passes;
- Codex blocker review returns PASS;
- PR CI is green and merged.
