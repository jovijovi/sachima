# FlowWeaver Phase 32 Controlled Delivery Activity and ACK Reconciliation Plan

## Scope

Approved phase: Phase 32 only.

Branch/worktree:

```text
feat/flowweaver-phase32-delivery-ack-activity
/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase32-delivery-ack-activity
```

Strongest allowed verdict:

```text
ready_for_narrow_ai_flow_pilot_request
```

This phase adds a controlled, non-production/staging artifact delivery and ACK reconciliation Activity boundary after Phase 31 controlled agent execution. It does not approve production Gateway wiring, production delivery enablement, Gateway-owned Worker lifecycle, config writes, Gateway restart, platform adapter mutation, or broad production rollout.

Temporal payload conversion may reorder dictionary keys across Workflow/Activity history. P32 therefore keeps public direct-call validators strict and uses separate Workflow/Activity-internal canonicalization for Temporal-decoded payloads and results.

## Objective

Add an explicit injected delivery surface and runtime ACK reconciliation surface so sanitized Phase 31 artifact metadata can be delivered in local/staging tests while preserving durable safety:

- only safe runtime ids, artifact refs, delivery refs, counts, statuses, digests, and stable error codes cross Workflow/Activity boundaries;
- ACK updates are emitted only for initialized runtime delivery slots;
- ACK replay/duplicates are idempotent;
- rich-card delivery never sets or implies final-text delivery;
- failure, timeout, cancellation, and disabled paths preserve delivery state and do not suppress final text.

## Allowed Behavior

Phase 32 may:

- define a safe delivery Activity request/result/snapshot/report contract;
- define an explicit caller-injected delivery surface boundary;
- define an explicit caller-injected runtime ACK reconciliation surface;
- build a Temporal Activity wrapper from those supplied surfaces;
- run a local/staging Workflow harness in tests;
- emit sanitized ACK update metadata for initialized delivery slots only;
- reconcile ACKs with stable `applied`, `duplicate`, or `rejected` results;
- inspect local Temporal history for no-leak behavior.

## Forbidden Behavior

Phase 32 must not:

- modify `gateway/run.py`;
- import or mutate `gateway/platforms/**`;
- instantiate Gateway adapter factories;
- write production config;
- restart Gateway;
- own Worker, service, daemon, Docker, socket, or subprocess lifecycle;
- create `Client.connect` factories;
- extend or modify the Phase 31 workflow;
- execute new agent/tool scope;
- assume production adapters are safe by default;
- invent ACK targets not initialized by the request;
- merge rich-card delivery state with final-text delivery state;
- persist or display raw prompt/tool/card/media/platform/private id/callback/credential/raw exception material.

## Planned Files

```text
gateway/flowweaver_delivery_activity.py
tests/gateway/test_flowweaver_delivery_activity.py
tests/integration/test_flowweaver_phase32_delivery_activity_ack_reconciliation.py
docs/runbooks/flowweaver-delivery-activity-ack-reconciliation.md
docs/plans/2026-05-09-flowweaver-phase32-delivery-activity-ack-reconciliation.md
docs/dev_log/2026-05-09-flowweaver-phase32-delivery-activity-ack-reconciliation.md
```

Guard maintenance only if required:

```text
tests/gateway/test_flowweaver_agent_execution_activity.py
tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py
```

## Public Entrypoints

```python
def describe_flowweaver_delivery_activity_contract() -> dict[str, object]: ...
def build_flowweaver_delivery_activity_request(...) -> dict[str, object]: ...
def validate_flowweaver_delivery_activity_request(value: object) -> dict[str, object]: ...
async def deliver_controlled_artifact(..., delivery_surface: Callable, runtime_control_surface: object) -> dict[str, object]: ...
def build_deliver_artifact_activity(*, delivery_surface: Callable, runtime_control_surface: object) -> Callable: ...
def validate_flowweaver_delivery_activity_result(value: object) -> dict[str, object]: ...
def validate_flowweaver_delivery_activity_snapshot(value: object) -> dict[str, object]: ...
def build_flowweaver_delivery_activity_report(...) -> dict[str, object]: ...
def validate_flowweaver_delivery_activity_report(value: object) -> dict[str, object]: ...
```

Local/staging Workflow harness:

```text
FlowWeaverDeliveryActivityWorkflow
```

## TDD Plan

1. RED: add focused tests importing the new module and asserting the delivery/ACK boundary.
2. GREEN: implement the smallest explicit injected delivery surface and runtime ACK reconciliation boundary.
3. Add disabled/default-off tests proving zero delivery/runtime calls.
4. Add ACK target tests proving initialized-slot-only and deterministic prefix behavior.
5. Add duplicate replay, rich-card/final-text separation, failure, timeout, and cancellation tests.
6. Add local Temporal Worker tests proving history bytes and JSON do not contain raw material.
7. Maintain prior phase changed-file guards with exact P32 paths only.
8. Run focused P32 tests, P30/P31 integration regression, FlowWeaver regression, static scans, and independent blocker reviews.

## Verification Commands

```bash
scripts/run_tests.sh tests/gateway/test_flowweaver_delivery_activity.py -q
$HOME/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= tests/integration/test_flowweaver_phase32_delivery_activity_ack_reconciliation.py -q
$HOME/.hermes/hermes-agent/venv/bin/python -m pytest -o addopts= -n 4 tests/integration/test_flowweaver_phase31_agent_execution_activity.py tests/integration/test_flowweaver_phase32_delivery_activity_ack_reconciliation.py -q
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase5*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```
