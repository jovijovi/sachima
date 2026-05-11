# FlowWeaver PE-1D / PE-2 Readiness Decision Packet

## Status

Decision packet only. This document does **not** enable PE-2, switch PE-1 to live/default-on, write production config, restart or reload Gateway, mutate platform adapters, start Temporal services or Workers, or authorize production delivery/agent execution.

Branch/worktree:

```text
feat/flowweaver-pe1d-pe2-readiness-decision-packet
/home/ubuntu/workspace/hermes/worktrees/sachima/feat-flowweaver-pe1d-pe2-readiness-decision-packet
```

Base evidence branch:

```text
feature/sachima-channel @ 0833544b2a4e
```

## Executive Decision

| Request | Decision | Reason |
|---|---|---|
| Continue current PE-1 controlled local Sachima observation | **GO** | PE-1A, PE-1B, and PE-1C prove loopback signed ingress, sanitized observation, fail-closed probes, no-leak scan, and rollback. |
| PE-1D longer controlled local observation window | **CONDITIONAL GO FOR SEPARATE APPROVAL** | Evidence supports a longer loopback-only observation window, still Sachima-only, no send URL, no real external ingress, no PE-2/live/default-on. |
| Fake-send / simulator UI loop design | **CONDITIONAL GO FOR SEPARATE APPROVAL** | This is the safest next behavior-bearing proof before real external ingress or any delivery control. It must use a fake/local send target only. |
| PE-2 design packet | **CONDITIONAL GO FOR DESIGN ONLY** | Enough evidence exists to draft a PE-2 design/readiness contract, but not to implement or operate PE-2. |
| PE-2 implementation, live/default-on, or real external ingress | **NO-GO** | We still lack longer-window evidence, fake-send/simulator loop evidence, explicit external ingress exposure approval, and operator monitoring/rollback acceptance. |
| Production delivery control or production agent/tool execution expansion | **NO-GO** | PE-1 is observation-only; delivery and agent/tool execution remain separate production phases. |
| Production config write, Gateway restart/reload, platform adapter mutation | **SEPARATE EXPLICIT APPROVAL REQUIRED** | This packet is docs plus guard maintenance only and cannot approve operational changes. |

Recommended next gate:

```text
PE-1D: Longer controlled Sachima local observation window, loopback-only, observation-only.
```

Secondary planning gate after PE-1D evidence:

```text
PE-2 design packet only: fake-send/simulator UI or controlled external-ingress design, not implementation.
```

## Evidence Matrix

| Evidence | Result | Decision impact |
|---|---:|---|
| Production Enablement Decision Packet | `conditional_go_for_pe1_controlled_sachima_production_shadow_observation` | PE-1 was correctly separated from direct production activation. |
| PE-1 code PR #74 | merged at `0833544b2a4e`; focused `4 passed`; Phase21/33 `22 passed`; integration `9 passed`; FlowWeaver regression `715 passed`; CI green | Code side is stable for exact Sachima-only observation gating. |
| PE-1A controlled local ingress smoke | PASS; unsigned/bad signature rejected; non-allowlisted user did not start observation; no-leak PASS; no real send URL | A controlled Sachima turn can reach Gateway without widening delivery scope. |
| PE-1B short-window observation | PASS; `3` signed allowlisted turns recorded; negative probes produced zero observation deltas; duplicate message ID produced no extra observation | Short-window behavior is stable and fail-closed. |
| PE-1C rollback drill | PASS; disabled config resolved to `allow_platforms=[]`; fake runtime call count `0`; config restored exactly; restore observation `4 -> 5`; workflows `4 -> 5` | Rollback switch is proven and observation resumes after exact restore. |
| Runtime hook scope | attached; operations exactly `start_transaction`, `query_transaction`; Temporal service/Worker `false` | Runtime surface remains observation-only and Gateway-owned lifecycle is absent. |
| Current forbidden boundaries | PE-2/live/default-on `false`; real external ingress `false`; delivery control `false`; production agent/tool execution expansion `false` | PE-2 cannot be treated as approved by PE-1 evidence. |

## PE-2 Readiness Assessment

PE-2 is **not ready for implementation or live/default-on operation**.

PE-2 is ready only for a separate design packet if that packet keeps these constraints:

1. No live/default-on switch.
2. No real external ingress until separately approved.
3. No real delivery control; use fake/local send targets first.
4. No production agent/tool execution expansion.
5. No Gateway-owned Temporal Client, Worker, task queue, service, daemon, Docker process, socket, or subprocess lifecycle.
6. Exact Sachima allowlist remains `[sachima]`; duplicates, extra platforms, missing values, hostile list/string subclasses, or forged policies fail closed.
7. Observation data remains sanitized labels, counters, refs, digests, statuses, and stable error codes only.
8. Rollback must stop new starts via config disable, allowlist removal, runtime surface removal, or reverting the phase.

## Evidence Required Before Any PE-2 Implementation Request

Before requesting PE-2 implementation, collect all of:

- a PE-1D longer controlled window with more than short-window volume and repeated negative probes;
- fake-send or simulator UI evidence proving the loop can render/store assistant replies without real external delivery;
- no-leak scans over observation, runtime state, fake-send transcripts, docs, and logs;
- duplicate/replay evidence across same-session and rapid consecutive turns;
- operator runbook for start, pause, rollback, restore, and evidence extraction;
- explicit approval boundaries for external ingress exposure, config write, restart/reload, and runtime/simulator ownership;
- fresh-context blocker reviews focused on accidental live enablement, delivery mutation, agent execution expansion, raw material leakage, and lifecycle ownership.

## PE-1D Minimal Shape

PE-1D should be the next behavior-bearing phase. It should run a longer controlled local observation window with:

- Sachima loopback ingress only: `127.0.0.1:8788/webhook/sachima`;
- HMAC required;
- narrow allowed local test user;
- `SACHIMA_ALLOW_ALL_USERS=false`;
- `SACHIMA_SEND_URL` absent;
- exact PE-1 config shape: `enabled=true`, `platform_allowlist=[sachima]`, `timeout_ms=250`;
- positive signed turns plus unsigned, bad-signature, non-allowlisted, duplicate, and disabled-policy probes;
- observation/workflow deltas matching only accepted allowlisted turns;
- no-leak scan and runtime operations check;
- no Temporal service or Worker startup.

PE-1D may produce an evidence packet. It must not change production config or restart Gateway unless those operational actions are separately approved for that phase.

## Explicit Non-Approvals

This packet does **not** approve:

```text
pe2_live_default_on
pe2_implementation
real_external_sachima_ingress
production_delivery_control
production_agent_tool_execution_expansion
production_config_write
gateway_restart_or_reload
platform_adapter_mutation
gateway_owned_temporal_lifecycle
```

## Required Approval Texts

To run the recommended next observation window:

```text
approve_pe1d_longer_controlled_sachima_local_observation_window
```

To write a later PE-2 design packet only:

```text
approve_pe2_design_packet_only_no_implementation
```

To do any operational or live-facing work later, approvals must be named separately:

```text
approve_real_external_sachima_ingress
approve_production_config_write
approve_gateway_restart_or_reload
approve_fake_send_or_simulator_target
approve_external_runtime_control_surface
approve_external_temporal_service_or_worker_if_used
```

## Verification Commands for This Packet

```bash
git diff --check
python -m py_compile gateway/flowweaver_production_shadow_observation.py gateway/flowweaver_ai_flow_pilot.py
python -m pytest -q tests/gateway/test_flowweaver_pe1_controlled_sachima_shadow_observation.py
python -m pytest -q tests/gateway/test_flowweaver_production_shadow_observation.py tests/gateway/test_flowweaver_ai_flow_pilot.py
python -m pytest -o addopts= -n 4 -q tests/integration/test_flowweaver_phase21_production_shadow_observation.py tests/integration/test_flowweaver_phase33_ai_flow_pilot.py
scripts/run_tests.sh tests/gateway/test_flowweaver_*.py tests/integration/test_flowweaver_phase5*.py tests/prototypes/test_flowweaver_phase5c_runtime_client_contract.py -q
```

## Decision Outcome

```text
pe1d_readiness_conditional_go_for_longer_controlled_local_observation
pe2_design_conditional_go_for_design_packet_only
pe2_implementation_no_go
pe2_live_default_on_no_go
```

Final handoff: PE-1 evidence is strong enough to continue controlled observation. It is not strong enough to make PE-2 live. The next move should be one more behavior-bearing, loopback-only PE-1D window, then a PE-2 design packet if that window stays clean.
