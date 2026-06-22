# FlowWeaver Production Enablement Decision Packet

## Status

Decision packet only. This document does **not** enable production behavior, write config, restart Gateway, mutate platform adapters, start services, or authorize live delivery/agent execution. The implementation scope is documentation plus exact changed-file guard allowlist maintenance only.

Branch/worktree:

```text
docs/flowweaver-production-enablement-decision-packet
/home/ubuntu/workspace/hermes/worktrees/sachima/docs-flowweaver-production-enablement-decision-packet
```

Base evidence branch:

```text
feature/sachima-channel @ f5eaabe64
```

## Executive Decision

| Request | Decision | Reason |
|---|---|---|
| Default-on production rollout | **NO-GO** | Phase 33 proves a controlled local/staging AI FLOW pilot, not broad production safety. |
| Production delivery control | **NO-GO** | Real send/edit/render/callback control still needs a separate implementation plan, live evidence, and rollback gate. |
| Production Temporal-backed agent/tool execution | **NO-GO** | P31 proves injected controlled execution boundaries, not production agent executor ownership. |
| Controlled Sachima production-shadow observation | **CONDITIONAL GO FOR SEPARATE APPROVAL** | Existing Phase 21 sidecar plus Phase 29-33 evidence are enough to request a narrow, default-off shadow enablement phase. |
| Production config write / Gateway restart | **SEPARATE EXPLICIT APPROVAL REQUIRED** | This packet is docs-only and cannot approve operational changes. |

Recommended next phase:

```text
Production Enablement PE-1: Controlled Sachima production-shadow observation enablement.
```

PE-1 should be default-off, Sachima-allowlisted only, observation-only, bounded by timeout, and backed by an externally managed runtime control surface. It should not control user-visible delivery or production agent/tool execution.

## Evidence Summary

| Evidence | Result | Decision impact |
|---|---:|---|
| Phase 21 production-shadow observation-only | Gateway gate 14 passed; integration 5 passed; runtime/gateway regression 16 passed; final review PASS | A default-off observation-only Gateway sidecar already exists and has rollback/kill-switch semantics. |
| Phase 29 stub Activity implementation | focused 53 passed; FlowWeaver regression 674 passed; final Codex + independent reviews PASS | Plain callable Activity seams fail closed against hostile, cyclic, deep, and raw-looking input. |
| Phase 30 local Temporal stub Activity orchestration | focused 9 passed; FlowWeaver regression 674 passed; review PASS | Local/staging Temporal Activity orchestration preserves safe history/snapshot contracts. |
| Phase 31 controlled agent execution Activity | unit 10 passed; integration 2 passed; P30+P31 11 passed; FlowWeaver regression 684 passed; reviews PASS | Agent/tool execution is allowed only behind injected controlled executor boundaries and sanitized result contracts. |
| Phase 32 controlled delivery/ACK Activity | unit+integration 19 passed; P30+P31+P32 13 passed; FlowWeaver regression 703 passed; reviews PASS | Delivery/ACK is separated from agent execution, initialized-slot-only, and rich-card/final-text-safe. |
| Phase 33 AI FLOW pilot | unit 8 passed; integration 8 passed; P30-P33 21 passed; FlowWeaver regression 711 passed; final reviews PASS | The combined pilot can produce sanitized snapshots and a decision packet, but only for a later separate enablement decision. |
| Sachima channel docs | webhook signing, dedupe, outbound send API, media safety, smoke tests documented | Sachima is a plausible narrow platform for PE-1, but operational config/restart remains separately approved. |

## Non-Negotiable Boundaries

PE-1 must keep all of these true:

1. Default disabled.
2. Explicit platform allowlist; first candidate platform is `sachima` only.
3. Gateway does not create Temporal clients, Workers, namespaces, task queues, services, daemons, Docker processes, sockets, or subprocess lifecycle.
4. Gateway uses only caller-supplied runtime control surfaces.
5. Observation failure or timeout cannot alter final response delivery behavior.
6. No production delivery control, no real ACK invention, and no platform adapter mutation.
7. No production Temporal-backed agent/tool execution.
8. No raw prompt, message text, tool output, card JSON, media path/bytes, platform/private identifiers, callback payloads, credentials, connection strings, or raw exception text in runtime requests, Temporal history, snapshots, logs, fixtures, docs evidence, or user-visible output.
9. No production config write or Gateway restart without a separately named approval.
10. Rollback must stop new observation starts without requiring a second deployment.

## Required PE-1 Approval Checklist

Before PE-1 starts, 狗哥 must approve these exact items:

```text
approve_pe1_controlled_sachima_shadow_observation_design
approve_pe1_docs_and_tests_only_first
```

Before any operational enablement, 狗哥 must additionally approve each item that applies:

```text
approve_production_config_write
approve_gateway_restart_or_reload
approve_sachima_platform_allowlist
approve_external_runtime_control_surface
approve_external_temporal_service_or_worker_if_used
```

This packet does not grant any of those operational approvals by itself.

## PE-1 Minimal Shape

PE-1 should produce a plan/dev-log/PR that proves:

- exact flag shape and default-off behavior;
- Sachima allowlist gating;
- runtime-control-surface injection only;
- bounded timeout and sanitized failure counters;
- no mutation to `response`, `delivery_state`, `already_sent`, `should_skip_final_text`, or adapter send behavior;
- no raw material in observation envelope, logs, Temporal history, or serialized event bytes;
- rollback by disabling flag, removing allowlist, or removing injected runtime surface;
- focused tests plus FlowWeaver regression;
- fresh-context blocker reviews.

## Rollback / Kill Switch

Any one of these must stop new observation starts:

1. Set `flowweaver.production_shadow_observation.enabled=false`.
2. Remove `sachima` from `flowweaver.production_shadow_observation.platform_allowlist`.
3. Remove the injected runtime control surface.
4. Stop externally managed Temporal Worker/runtime surface if used.
5. Revert PE-1 PR or operational config change if needed.

Rollback must not delete production data, mutate platform adapters, invent delivery ACKs, or require raw payload inspection.

## Decision Outcome

```text
conditional_go_for_pe1_controlled_sachima_production_shadow_observation
```

This means: begin a separately approved PE-1 plan/implementation for controlled Sachima production-shadow observation.

It does **not** mean:

```text
default_on_rollout
production_delivery_control
production_agent_execution
production_config_write
gateway_restart
platform_adapter_mutation
```

## Verification Commands for This Packet

```bash
git diff --check
python -m py_compile gateway/flowweaver_ai_flow_pilot.py gateway/flowweaver_production_shadow_observation.py
python -m pytest -q tests/gateway/test_flowweaver_ai_flow_pilot.py tests/gateway/test_flowweaver_production_shadow_observation.py
python -m pytest -o addopts= -n 4 -q tests/integration/test_flowweaver_phase33_ai_flow_pilot.py tests/integration/test_flowweaver_phase21_production_shadow_observation.py
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase5*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```

## Final Handoff

If this packet is accepted, the next user-facing approval request should be:

```text
Approve PE-1 only: controlled Sachima production-shadow observation design/implementation, default-off and observation-only.
```

Do not approve default-on production, production delivery control, or production agent/tool execution in the same step.
