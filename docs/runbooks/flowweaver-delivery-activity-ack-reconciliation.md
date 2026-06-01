# FlowWeaver Delivery Activity and ACK Reconciliation Runbook

## Scope

This runbook covers Phase 32 only: controlled non-production/staging artifact delivery and ACK reconciliation through injected surfaces.

It is not production Gateway wiring, not production delivery enablement, and not a Gateway-owned Worker lifecycle.

## Core Symbols

Module:

```text
gateway/flowweaver_delivery_activity.py
```

Core symbols:

- `FlowWeaverDeliveryActivityWorkflow`
- `build_deliver_artifact_activity`
- `build_flowweaver_delivery_activity_request`
- `deliver_controlled_artifact`
- `validate_flowweaver_delivery_activity_request`
- `validate_flowweaver_delivery_activity_result`
- `validate_flowweaver_delivery_activity_snapshot`
- `build_flowweaver_delivery_activity_report`

## Operator Rules

Allowed only in local/staging tests unless a later phase grants broader approval.

Do not use this phase to:

- connect production Gateway to delivery control;
- instantiate Gateway platform adapters;
- introduce hidden delivery-surface factories;
- start or supervise Workers from Gateway;
- write production config;
- restart Gateway;
- mutate platform adapters;
- combine rich-card delivery state with final-text delivery state;
- create ACK updates for non-initialized delivery slots;
- persist raw platform/card/media/callback/credential material.

## Safe Request Pattern

Build the request from a sanitized Phase 31 result and initialized delivery slots:

```python
request = build_flowweaver_delivery_activity_request(
    transaction_id="runtime_tx_phase32_example",
    workflow_id="runtime_tx_phase32_example",
    intent_id="runtime_intent_0",
    agent_execution_result=phase31_result,
    initialized_delivery_slots=[
        {
            "delivery_ref": "runtime_delivery_0",
            "surface": "rich_card",
            "artifact_ref": "runtime_artifact_0",
            "required": True,
        },
        {
            "delivery_ref": "runtime_delivery_1",
            "surface": "final_text",
            "artifact_ref": "runtime_artifact_0",
            "required": True,
        },
    ],
    enabled=True,
)
```

The request contains safe ids, sanitized Phase 31 artifact metadata, initialized delivery slots, delivery policy metadata, required surfaces, and a digest. It must not contain raw prompt text, tool output, card JSON, media paths, platform/private ids, callback payloads, credentials, or raw exception text.

Temporal payload conversion may reorder dictionary keys after Workflow/Activity history serialization. Public direct-call validators remain strict about canonical field order; Workflow/Activity-internal validation accepts exact key sets at the Temporal boundary and immediately rebuilds canonical sanitized copies before downstream use.

## Injected Surface Pattern

Build the Activity with explicit surfaces:

```python
activity_func = build_deliver_artifact_activity(
    delivery_surface=my_controlled_delivery_surface,
    runtime_control_surface=my_runtime_ack_surface,
)
```

The delivery surface receives only:

```text
transaction_id
workflow_id
intent_id
artifact_ref
artifact_kind
initialized_delivery_slots
required_surfaces
delivery_policy
delivery_digest
```

The runtime control surface must expose:

```python
async def reconcile_delivery_ack(update: dict[str, object]) -> dict[str, object]: ...
```

It may return only sanitized statuses:

```text
applied
duplicate
rejected
```

## Result Semantics

Success returns:

```text
status: delivered
artifact_ref: runtime_artifact_...
delivery_refs: runtime_delivery_... list
surface_state: progress_card_sent / rich_cards_sent / final_text_sent / media_sent
ack_updates: sanitized runtime refs only
ack_results: applied/duplicate/rejected summaries
counts: delivery_calls / ack_updates / ack_applied / ack_duplicates / ack_rejected
error_code: None
retry_class: none
side_effects: []
```

Disabled/default-off returns no delivery or runtime calls:

```text
status: disabled
error_code: delivery_policy_disabled
delivery_refs: []
ack_updates: []
ack_results: []
surface_state.final_text_sent: False
```

Safe failure paths include:

```text
invalid_delivery_activity_request -> non_retryable
invalid_agent_execution_result -> non_retryable
invalid_delivery_slot -> non_retryable
delivery_policy_disabled -> non_retryable
delivery_surface_required -> non_retryable
runtime_control_surface_required -> non_retryable
uninitialized_ack_target -> non_retryable
delivery_target_mismatch -> non_retryable
invalid_ack_update -> non_retryable
unsafe_material -> non_retryable
delivery_cancelled -> non_retryable
delivery_surface_failed -> transient
delivery_surface_timeout -> transient
runtime_reconciliation_failed -> transient
unsafe_runtime_output -> transient
final_text_delivery_missing -> transient
```

Raw exception text is never echoed.

## Local Test Harness Pattern

Use `WorkflowEnvironment.start_time_skipping()` and `Worker(...)` only in integration tests. Register:

```python
workflows=[FlowWeaverDeliveryActivityWorkflow]
activities=[
    build_deliver_artifact_activity(
        delivery_surface=fake_delivery_surface,
        runtime_control_surface=fake_runtime_ack_surface,
    ),
]
```

The module itself must not construct Worker, WorkflowEnvironment, Client connections, Gateway adapters, or service lifecycle.

## Verification

Focused unit:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_delivery_activity.py -q
```

Focused integration:

```bash
$HOME/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= tests/integration/test_flowweaver_phase32_delivery_activity_ack_reconciliation.py -q
```

Regression:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase5*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```

## Expected Evidence

- Delivery surface is injected, observable, and bounded.
- Disabled policy makes zero delivery/runtime calls.
- ACK targets are initialized delivery slots only.
- Duplicate ACK replay is idempotent.
- Rich-card delivery does not set final-text delivery.
- Failure, timeout, and cancellation keep final text unsent unless explicitly delivered.
- History JSON and serialized event bytes contain no raw material keys or values.
- Gateway source, platform adapters, production config, and service lifecycle remain untouched.
