# FlowWeaver Temporal Stub Activity Orchestration Runbook

## Scope

Phase 30 proves local/staging Temporal orchestration for Phase 29 plain stubs. It is not production wiring.

## Public Surface

Module:

```text
gateway/flowweaver_temporal_stub_activity_orchestration.py
```

Core symbols:

- `FlowWeaverTemporalStubActivityWorkflow`
- `validate_claim_check_ref_activity`
- `execute_agent_turn_activity`
- `deliver_artifact_activity`
- `build_flowweaver_temporal_stub_activity_start_payload`
- `start_or_reconcile_flowweaver_temporal_stub_activity_workflow`
- `validate_flowweaver_temporal_stub_activity_snapshot`
- `build_flowweaver_temporal_stub_activity_orchestration_report`

## Operator Rules

Allowed only in local/staging tests unless a later phase grants broader approval.

Do not use this phase to:

- connect Gateway to Temporal production;
- start, supervise, or deploy a Worker from Gateway;
- write config;
- restart Gateway;
- mutate platform adapters;
- execute real agents/tools;
- render/send/edit/callback/ACK real messages.

## Safe Start Pattern

Build a start payload from safe refs only:

```python
payload = build_flowweaver_temporal_stub_activity_start_payload(
    transaction_id="runtime_tx_phase30_example",
    workflow_id="runtime_tx_phase30_example",
    intent_id="runtime_intent_0",
    claim_check_ref={
        "ref": "claim_ref_phase30_0",
        "kind": "agent_input",
        "count": 1,
        "size": 128,
        "checksum_hint": "sha256:" + ("a" * 64),
    },
    artifact_ref="runtime_artifact_0",
    delivery_ref="runtime_delivery_0",
)
```

The payload contains safe ids, refs, counts, statuses, and a digest only. It must not contain raw prompt text, tool output, card JSON, media path, platform/private ids, callback payloads, credentials, or raw exceptions.

## Local Test Harness Pattern

Use `WorkflowEnvironment.start_time_skipping()` and `Worker(...)` only in integration tests. Register exactly:

```python
workflows=[FlowWeaverTemporalStubActivityWorkflow]
activities=[
    validate_claim_check_ref_activity,
    execute_agent_turn_activity,
    deliver_artifact_activity,
]
```

The module itself must not construct Worker or WorkflowEnvironment.

## Duplicate Start Semantics

`start_or_reconcile_flowweaver_temporal_stub_activity_workflow(...)` accepts a caller-supplied Temporal client.

- First safe start returns `status: started`.
- Duplicate start with the same workflow-observable safe payload returns `status: duplicate` only after querying and validating the existing snapshot.
- Duplicate start with a mismatched safe payload returns `error_code: duplicate_start_payload_mismatch` and does not echo raw exception text.

## Cancellation

The workflow exposes the `cancel` update. A safe `runtime_event_...` id marks the workflow snapshot `cancelled` and returns a sanitized final snapshot.

## Verification

Focused integration:

```bash
$HOME/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py -q
```

The canonical wrapper excludes integration tests by design, so `no tests ran` from `scripts/run_tests.sh` is not a pass or fail for the integration harness.

Regression:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase5*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```

## Expected Evidence

- Activity sequence is exactly `validate_claim_check_ref`, `execute_agent_turn`, `deliver_artifact`.
- Snapshots contain only safe ids, refs, statuses, counts, digests, retry policy, and stable error codes.
- History JSON and serialized event bytes contain no raw material sentinels or forbidden raw-surface keys.
- Gateway source has no Worker/WorkflowEnvironment construction, no client connection factory, no platform adapter imports, no config writes, no real agent/tool execution, and no delivery/ACK effects.
