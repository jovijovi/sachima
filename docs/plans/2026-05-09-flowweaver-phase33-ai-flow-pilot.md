# FlowWeaver Phase 33 Narrow AI FLOW Pilot Plan

## Scope

Approved phase: Phase 33 only.

Branch/worktree:

```text
feat/flowweaver-phase33-ai-flow-pilot
/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-phase33-ai-flow-pilot
```

Strongest allowed verdict:

```text
ready_for_separate_production_enablement_decision
```

This verdict is not production readiness. It only means the controlled pilot evidence is sufficient for a later, separately approved production-enablement decision. Non-completed, disabled, failed, cancelled, timed-out, rejected, partial, or in-flight decision packets must use `not_ready_for_production_enablement` instead.

## Objective

Compose the already approved Phase 31 controlled agent execution Activity and Phase 32 controlled delivery/ACK Activity inside one narrow local/staging AI FLOW pilot workflow.

The pilot must produce sanitized transaction, intent, operation, artifact, delivery, rollback, and decision-packet state without production Gateway wiring or live platform effects.

## Allowed Behavior

Phase 33 may:

- define a local/staging pilot request, snapshot, report, and decision packet contract;
- run a local/staging Temporal workflow in tests;
- call the existing `validate_claim_check_ref`, `execute_agent_turn`, and `deliver_artifact` Activities through Phase 33 no-throw sanitized wrappers around caller-registered activities;
- require caller-injected executor, delivery surface, and runtime ACK reconciler;
- build Phase 31 and Phase 32 requests internally from sanitized refs/results;
- return sanitized progress and final snapshots;
- produce a rollback checklist and separate-approval decision packet.

## Forbidden Behavior

Phase 33 must not:

- modify `gateway/run.py`;
- import or mutate `gateway/platforms/**`;
- instantiate Gateway adapter factories;
- write production config;
- restart Gateway;
- own Worker, service, daemon, Docker, socket, or subprocess lifecycle outside tests;
- create `Client.connect` factories;
- instantiate `AIAgent` or hidden executor factories;
- enable production agent execution or production delivery;
- treat pilot success as automatic production enablement;
- persist or display raw prompt/tool/card/media/platform/private id/callback/credential/raw exception material.

## Planned Files

```text
gateway/flowweaver_ai_flow_pilot.py
tests/gateway/test_flowweaver_ai_flow_pilot.py
tests/integration/test_flowweaver_phase33_ai_flow_pilot.py
docs/runbooks/flowweaver-ai-flow-pilot.md
docs/plans/2026-05-09-flowweaver-phase33-ai-flow-pilot.md
docs/dev_log/2026-05-09-flowweaver-phase33-ai-flow-pilot.md
```

Guard maintenance only if required:

```text
tests/gateway/test_flowweaver_agent_execution_activity.py
tests/gateway/test_flowweaver_delivery_activity.py
tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py
```

## Public Entrypoints

```python
def describe_flowweaver_ai_flow_pilot_contract() -> dict[str, object]: ...
def build_flowweaver_ai_flow_pilot_request(...) -> dict[str, object]: ...
def validate_flowweaver_ai_flow_pilot_request(value: object) -> dict[str, object]: ...
def build_flowweaver_ai_flow_pilot_activity_wrappers(...) -> list[Callable[..., object]]: ...
def validate_flowweaver_ai_flow_pilot_snapshot(value: object) -> dict[str, object]: ...
def validate_flowweaver_ai_flow_pilot_decision_packet(value: object) -> dict[str, object]: ...
def build_flowweaver_ai_flow_pilot_report(...) -> dict[str, object]: ...
def validate_flowweaver_ai_flow_pilot_report(value: object) -> dict[str, object]: ...
```

Local/staging workflow harness:

```text
FlowWeaverAIFlowPilotWorkflow
```

## TDD Plan

1. RED: add focused tests importing the new module and asserting the P33 contract.
2. GREEN: implement the smallest exact request/snapshot/report/decision-packet validators.
3. Add integration tests for P31 -> P32 composition in one local/staging workflow.
4. Add default-off no-op test proving zero executor, delivery, and runtime calls.
5. Add agent failure/cancellation tests proving delivery is skipped and rollback state is sanitized.
6. Add ACK duplicate/idempotency test proving duplicate ACK results still produce a safe pilot decision.
7. Add history JSON and serialized event-byte no-leak tests, including an inner Activity exception case proving wrappers return sanitized non-ready snapshots instead of raw Temporal Activity failures.
8. Maintain prior phase changed-file guards with exact P33 paths only.
9. Run focused P33 tests, P30/P31/P32/P33 integration regression, FlowWeaver regression, static scans, and independent blocker reviews.

## Verification Commands

```bash
python -m pytest -q tests/gateway/test_flowweaver_ai_flow_pilot.py
python -m pytest -o addopts= -q tests/integration/test_flowweaver_phase33_ai_flow_pilot.py
python -m pytest -o addopts= -n 4 tests/integration/test_flowweaver_phase30_temporal_stub_activity_orchestration.py tests/integration/test_flowweaver_phase31_agent_execution_activity.py tests/integration/test_flowweaver_phase32_delivery_activity_ack_reconciliation.py tests/integration/test_flowweaver_phase33_ai_flow_pilot.py -q
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase5*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```
