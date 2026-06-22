# FlowWeaver Agent Execution Activity Runbook

## Scope

This runbook covers Phase 31 only: controlled non-production agent/tool execution through an injected executor Activity.

It is not production Gateway wiring and it is not production agent execution.

## Core Symbols

Module:

```text
gateway/flowweaver_agent_execution_activity.py
```

Core symbols:

- `FlowWeaverAgentExecutionActivityWorkflow`
- `build_execute_agent_turn_activity`
- `build_flowweaver_agent_execution_request`
- `execute_controlled_agent_turn`
- `validate_flowweaver_agent_execution_request`
- `validate_flowweaver_agent_execution_result`
- `validate_flowweaver_agent_execution_snapshot`
- `build_flowweaver_agent_execution_activity_report`

## Operator Rules

Allowed only in local/staging tests unless a later phase grants broader approval.

Do not use this phase to:

- connect production Gateway to agent execution;
- instantiate global `AIAgent` objects;
- introduce hidden executor factories;
- start or supervise Workers from Gateway;
- write production config;
- restart Gateway;
- mutate platform adapters;
- render, send, edit, callback, or ACK real messages;
- persist raw prompt/tool/model/platform/private/callback/credential material.

## Safe Request Pattern

Build the request from safe refs only:

```python
request = build_flowweaver_agent_execution_request(
    transaction_id="runtime_tx_phase31_example",
    workflow_id="runtime_tx_phase31_example",
    intent_id="runtime_intent_0",
    claim_check_ref={
        "ref": "claim_ref_phase31_0",
        "kind": "agent_input",
        "count": 1,
        "size": 128,
        "checksum_hint": "sha256:" + ("a" * 64),
    },
    artifact_ref="runtime_artifact_0",
)
```

The request contains safe ids, one claim-check ref, policy metadata, one planned artifact ref, execution policy metadata, and a digest. It must not contain raw prompt text, tool output, model response bodies, card JSON, media paths, platform/private ids, callback payloads, credentials, or raw exceptions.

## Injected Executor Pattern

Build the Activity with an explicit executor:

```python
activity_func = build_execute_agent_turn_activity(executor=my_controlled_executor)
```

The executor receives only:

```text
transaction_id
workflow_id
intent_id
claim_check_ref
artifact_ref
execution_mode
executor_policy
execution_digest
```

The executor may load raw material internally through the claim-check reference, but the Activity returns only sanitized result metadata.

## Local Test Harness Pattern

Use `WorkflowEnvironment.start_time_skipping()` and `Worker(...)` only in integration tests. Register:

```python
workflows=[FlowWeaverAgentExecutionActivityWorkflow]
activities=[
    validate_claim_check_ref_activity,
    build_execute_agent_turn_activity(executor=fake_executor),
]
```

The module itself must not construct Worker or WorkflowEnvironment.

## Result Semantics

Success returns:

```text
status: executed
artifact_ref: runtime_artifact_...
artifact_kind: controlled_agent_result
counts: executor_calls/tool_calls/output_items
output_digest: sha256:<64 lowercase hex>
error_code: None
retry_class: none
side_effects: []
```

Safe failure paths:

```text
executor_failed -> retry_class transient
executor_timeout -> retry_class transient
executor_cancelled -> retry_class non_retryable
executor_auth_config_failure -> retry_class non_retryable
invalid_agent_execution_request -> retry_class non_retryable
unsafe_material -> retry_class non_retryable
```

Raw exception text is never echoed.

## Verification

Focused unit:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_agent_execution_activity.py -q
```

Focused integration:

```bash
$HOME/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= tests/integration/test_flowweaver_phase31_agent_execution_activity.py -q
```

Integration with xdist:

```bash
$HOME/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 tests/integration/test_flowweaver_phase31_agent_execution_activity.py -q
```

Regression:

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase5*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```

## Expected Evidence

- Executor is injected, observable, and bounded.
- Invalid or unsafe claim data fails before executor calls.
- Executor success returns only artifact refs, counts, digest, status, and stable error codes.
- Executor exceptions, timeout, and cancellation are sanitized.
- History JSON and serialized event bytes contain no raw material keys or values.
- Delivery surfaces remain absent.
- Gateway source, platform adapters, production config, and service lifecycle remain untouched.
