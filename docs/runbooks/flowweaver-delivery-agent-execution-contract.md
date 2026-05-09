# FlowWeaver Delivery / Agent Execution Contract Runbook

## Purpose

This runbook defines the Phase 22 contract gate between:

- Temporal-owned orchestration state;
- Hermes Agent execution through a future Activity boundary;
- Gateway-owned rendering and delivery.

The Phase 22 verdict is:

```text
ready_for_stub_activity_orchestration
```

This means Phase 23 may implement stub Activities. It does not enable production behavior.

## Current Contract Module

Use:

```python
from gateway.flowweaver_delivery_agent_execution_contract import (
    build_flowweaver_delivery_ack_update,
    build_flowweaver_execution_request,
    build_flowweaver_execution_result,
    build_flowweaver_progress_snapshot,
    describe_flowweaver_delivery_agent_execution_contract,
    validate_flowweaver_delivery_agent_execution_contract,
)
```

The module must remain pure:

- no runtime Worker/service lifecycle;
- no Gateway hook changes;
- no production config writes;
- no real agent execution;
- no real delivery ACK updates;
- no async event-loop ownership;
- no Temporal client construction;
- no Gateway adapter access;
- no file, subprocess, socket, send, edit, render, or callback control.

## Contract Shapes

The descriptor returned by `describe_flowweaver_delivery_agent_execution_contract()` freezes exact ordered fields for:

- `FlowWeaverExecutionRequest`
- `FlowWeaverExecutionResult`
- `FlowWeaverDeliveryAckUpdate`
- `FlowWeaverProgressSnapshot`

Consumers must validate the descriptor with `validate_flowweaver_delivery_agent_execution_contract()` before relying on it.

## Claim-Check and Raw-Material Policy

The contract is references-only. Future raw prompts, tool outputs, card JSON, media material, platform identifiers, callback payloads, credentials, and raw exception text must be represented as safe claim-check references outside this contract.

Raw field names may appear only as explicit metadata in `forbidden_material`. Raw values must not appear in returned objects, logs, review evidence, or user-visible output.

## Canonical ID Rules

- `transaction_id` is canonical.
- `workflow_id` is a transport alias and must equal `transaction_id`.
- `intent_id`, `delivery_id`, and `artifact_ref` use strict unpadded numeric suffixes.
- Reject padded aliases such as `runtime_delivery_00`.
- Reject platform/private/raw-looking identifiers.

## Separate Approvals Required

Phase 22 does not approve these actions:

- live config writes
- Gateway restart
- production enablement
- real send/edit/render/callback control
- real agent/tool execution

If a future phase needs one of these, stop and request explicit 狗哥 approval.

## Verification

Run:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_delivery_agent_execution_contract.py -q
```

Before PR, also run the relevant FlowWeaver gateway regression slice and Codex blocker review.
