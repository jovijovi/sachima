# FlowWeaver AI FLOW Pilot Runbook

## Purpose

Phase 33 runs a narrow local/staging AI FLOW pilot that composes Phase 31 controlled agent execution and Phase 32 controlled artifact delivery/ACK reconciliation.

This runbook is not a production activation guide.

## Required Inputs

- Safe runtime transaction id and workflow id with matching `runtime_tx_` values.
- Safe intent id with `runtime_intent_` prefix.
- Claim-check ref containing only safe ref, kind, count, size, and checksum hint.
- Runtime artifact ref with `runtime_artifact_` prefix.
- Initialized delivery slots using deterministic `runtime_delivery_N` refs.
- Explicit pilot policy.
- Explicit caller-registered test/staging executor, delivery surface, and runtime ACK reconciler.

## Operator Flow

1. Build a Phase 33 pilot request with `build_flowweaver_ai_flow_pilot_request(...)`.
2. Register `FlowWeaverAIFlowPilotWorkflow` on the local/staging test Worker.
3. Register Phase 33 no-throw wrappers with `build_flowweaver_ai_flow_pilot_activity_wrappers(...)` around the existing claim-check Activity, Phase 31 `execute_agent_turn`, and Phase 32 `deliver_artifact`.
4. Ensure the wrapped Phase 31 `execute_agent_turn` uses a caller-injected executor.
5. Ensure the wrapped Phase 32 `deliver_artifact` uses caller-injected delivery and runtime ACK surfaces.
6. Start the workflow only on the Phase 33 local/staging task queue.
7. Query the sanitized snapshot until a terminal pilot status appears.
8. Inspect the decision packet.
   - `pilot_completed` may carry `ready_for_separate_production_enablement_decision`.
   - Any non-completed, disabled, failed, timed-out, cancelled, rejected, partial, or in-flight status must carry `not_ready_for_production_enablement`.
9. Do not enable production behavior unless a later separate production-enablement plan is approved.

## Terminal Statuses

```text
pilot_completed
disabled
agent_execution_failed
partially_delivered
timed_out
cancelled
rejected
```

## Rollback / Kill Switch

The default rollback checklist is:

```text
disable_pilot_policy
preserve_canonical_branch
rerun_clean_verification
```

The kill-switch reference is:

```text
rollback_phase33_disable_pilot
```

Rollback means stopping the pilot path and preserving evidence. It does not delete production data, restart Gateway, or mutate platform adapters.

## Production Boundaries

Phase 33 does not approve:

- production Gateway wiring;
- production delivery enablement;
- production agent execution;
- production config writes;
- Gateway restart;
- platform adapter mutation;
- Gateway-owned Worker lifecycle.

## No-Leak Verification

Check all returned snapshots, reports, decision packets, history JSON, and serialized event bytes for absence of raw prompt/tool/card/media/platform/private id/callback/credential/raw exception material.

Use the Phase 33 no-throw wrappers for all caller-supplied Activities; do not register raw caller Activities directly on the Phase 33 Worker, because an uncaught Activity exception would be persisted by Temporal before workflow-level sanitization can run.

The only allowed durable material is safe runtime ids, claim-check refs, artifact refs, delivery refs, counts, digests, statuses, stable error codes, labels, and empty side-effect lists.
