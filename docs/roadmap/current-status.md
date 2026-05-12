# Sachima Roadmap Current Status

> Living dashboard. This file tracks the current roadmap position and drift guards for Sachima / FlowWeaver work. It does not replace the canonical roadmap.

```text
last_updated: 2026-05-12
base_branch: feature/sachima-channel
current_base_sha: 1f587a0b0355f7eb18a2cdff64bc1bc93ea109dd
current_position: P4 next — Controlled external ingress design packet
```

## Canonical references

- North star: `GOAL.md`
- Gap basis: `docs/sachima-final-goal-gap-analysis.md`
- Canonical roadmap: `docs/plans/2026-05-11-sachima-final-goal-phase-development-plan.md`
- PE-2 design packet: `docs/plans/2026-05-12-flowweaver-pe2-design-packet.md`
- Latest PE-2A dev log: `docs/dev_log/2026-05-12-flowweaver-pe2a-controlled-runtime-fake-delivery.md`

## How to use this file

Before any roadmap, phase, PR, CI, merge, review, or next-phase-readiness work:

1. Read this file.
2. Read the canonical roadmap linked above.
3. Read the latest relevant dev log and evidence links below.
4. State the current phase, next allowed request, explicit non-approvals, and open tails before changing files.

If this file is stale or contradicts a requested task, stop and report the drift risk.

## Current phase map

| Phase | Status | Evidence / decision | Strongest current meaning |
|---|---|---|---|
| P1 — PE-1D longer controlled local observation | Done | PE-1D evidence path listed below; PR #78 governance validation, merge `8ad7f90f9e96afd6740508bd89df062f1eeb9f1e` | Ready for fake-send / PE-2 design evidence use; exact default-port behavior remains WATCH |
| P2 — Fake-send / simulator delivery loop | Done | PR #79 design, PR #80 implementation; merge `10486c7c585974dce3f37c74437ada3419d67904` for implementation | Fake delivery and ACK semantics proven locally; does not approve real delivery |
| P3 — PE-2 design packet only | Done | PR #81, merge `84f6a9010d72fe6ab3a0dac4ecaea3c3fb252ddf` | May request separately approved PE-2A implementation; not live or real ingress |
| Bridge — PE-2A controlled runtime + fake delivery | Done | PR #82, merge `1f587a0b0355f7eb18a2cdff64bc1bc93ea109dd` | Controlled local runtime-delivery bridge proven with fake delivery; does not approve real external ingress |
| P4 — Controlled external ingress | Next | Not started | Next allowed work is design packet only unless separately approved |
| P5 — Production durable runtime integration | Pending | Not started | Blocked until P4/P5 approvals and runtime design gates |
| P6 — Controlled AI FLOW execution | Pending | Not started | Blocked until durable runtime and safety gates |
| P7 — Real delivery and ACK closure | Pending | Not started | Blocked until fake/local delivery and AI FLOW gates are production-ready and separately approved |
| P8 — Product / ops hardening | Pending | Not started | Blocked until limited live pilot readiness |

## Latest merged PRs

| PR | Purpose | Merge commit | Notes |
|---|---|---|---|
| #78 | Validate phase-gate drift control for PE-1D | `8ad7f90f9e96afd6740508bd89df062f1eeb9f1e` | Docs / governance validation |
| #79 | Phase B fake-send simulator plan | `d1dc4602777a51570f5981b02c9c8a1b7c18847e` | Docs-only plan |
| #80 | Phase B fake-send simulator implementation | `10486c7c585974dce3f37c74437ada3419d67904` | Fake-send / simulator implementation |
| #81 | PE-2 design packet | `84f6a9010d72fe6ab3a0dac4ecaea3c3fb252ddf` | Design-only packet |
| #82 | PE-2A controlled runtime fake delivery bridge | `1f587a0b0355f7eb18a2cdff64bc1bc93ea109dd` | Controlled local runtime + fake delivery implementation |

## Evidence index

Runtime evidence stays outside PR payloads unless a phase explicitly approves versioning it.

| Phase | Evidence |
|---|---|
| PE-1D | `/home/ubuntu/workspace/hermes/outputs/sachima/pe1d-longer-controlled-local-observation/pe1d_controlled_observation_evidence.json` |
| PE-1D summary | `/home/ubuntu/workspace/hermes/outputs/sachima/pe1d-longer-controlled-local-observation/pe1d_controlled_observation_summary.md` |
| Phase B | `/home/ubuntu/workspace/hermes/outputs/sachima/phase-b-fake-send-simulator/phase_b_fake_send_simulator_evidence.json` |
| PE-2A | `/home/ubuntu/workspace/hermes/outputs/sachima/pe2a-controlled-runtime-fake-delivery/pe2a_controlled_runtime_fake_delivery_evidence.json` |
| PE-2A post-merge | `/home/ubuntu/workspace/hermes/outputs/sachima/pe2a-controlled-runtime-fake-delivery/pe2a_controlled_runtime_fake_delivery_postmerge_evidence.json` |

## Open tails

| ID | Class | Description | Blocks current phase? | Blocks next phase? | Required before | Acceptance method | Status |
|---|---|---|---:|---:|---|---|---|
| ROADMAP-WATCH-8788 | WATCH | PE-1D used fallback loopback `18788` because default `8788` was occupied by an existing Gateway. Exact default-port behavior is not proven for external ingress or live claims. | No | No | Real external ingress, exact-port live claim, or maintenance-window work | Separate maintenance-window approval and exact-port rerun without opportunistic Gateway restart | Open |
| ROADMAP-NEXT-P4-DESIGN | NEXT_PHASE | Controlled external ingress should start with a design packet before implementation. | No | Yes | P4 implementation request | Design packet, threat model, explicit approval/non-approval boundaries, review blockers zero | Open |
| ROADMAP-WATCH-STATUS-DASHBOARD | WATCH | This dashboard is the living progress index and must be updated after roadmap/phase closure. | No | No | Any claim of phase closure or next-phase readiness | Update this file or explain N/A in the PR | Open |

## Explicit non-approvals

The current state does not approve any of the following:

```text
real_external_sachima_ingress
real_external_delivery
production_delivery_control
production_agent_tool_execution_expansion
production_config_write
gateway_restart_or_reload
platform_adapter_mutation
gateway_owned_temporal_lifecycle
real_send_api_or_external_im_call
external_temporal_service_or_worker_startup
live_or_default_on_behavior
public_webhook_exposure
reverse_proxy_or_tls_config_write
```

## Next allowed request

Recommended next work:

```text
P4 controlled external ingress design packet only
```

Suggested approval text:

```text
approve_external_ingress_design_packet_no_implementation_no_live_no_real_delivery
```

This approval would allow docs/design work for P4 only. It would not approve implementation, public exposure, Gateway restart/reload, production config writes, real external delivery, real AI FLOW execution, or Temporal service/Worker lifecycle.

## Drift guard

Do not infer any of these from the completed phases:

- PE-2A fake delivery success does not prove real delivery safety.
- Loopback/synthetic ingress success does not prove public external ingress safety.
- A design packet does not approve implementation.
- A local runtime bridge does not approve production durable runtime ownership.
- ACK evidence from fake-send does not approve real IM ACK reconciliation.
- Completed PRs do not close open `WATCH` tails unless this file records the closure.
- A roadmap/phase PR is not complete if this file should have changed and did not.

## Completion rule for agents

A roadmap or phase task is not complete until:

- tests, reviews, and evidence pass where applicable;
- PR / merge / post-merge status is recorded where applicable;
- this file reflects the new phase state;
- remaining tails are classified as `BLOCKER`, `NEXT_PHASE`, `WATCH`, or `PARKED`.
